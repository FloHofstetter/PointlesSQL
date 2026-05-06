"""One ipykernel subprocess wrapped as :class:`KernelSession`.

One ipykernel subprocess runs per ``(user_id, notebook_path)`` pair
— a VSCode-style identity model rather than Jupyter-classic-style-
per-tab.  Two browser tabs of the same ``.py`` share one kernel,
one namespace, one ``kernel_session_id``.

This module owns the lifecycle + ZMQ pump tasks; the registry
that maps ``(user_id, path) → KernelSession`` lives in
``registry.py``; message dataclasses live in ``messages.py``.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from pathlib import Path

from jupyter_client.asynchronous.client import AsyncKernelClient  # type: ignore[import-untyped]
from jupyter_client.manager import AsyncKernelManager  # type: ignore[import-untyped]

from pointlessql.services.kernel_session.messages import (
    KernelMessage,
    Subscription,
)

logger = logging.getLogger(__name__)

_KERNEL_READY_TIMEOUT = 30.0
_SHUTDOWN_TIMEOUT = 5.0
_BOOTSTRAP_TIMEOUT = 10.0


# Kernel-side helper that turns the WS ``execute_sql`` wrapper into
# a rich-mime DataFrame display + optional namespace binding.  The
# route already enforced privileges and resolved the
# ``approved_tables`` map to Delta storage locations; the kernel only
# has to register the views, run the query, materialise as pandas, and
# call ``display`` so the existing iopub → output_renderer.js path
# renders the table inline.  Errors raise normally so the kernel emits
# a standard ``error`` iopub message the toolbar already paints in red.
_NOTEBOOK_BOOTSTRAP_CODE = """\
def __pql_sql_run(query, *, approved_tables, result_var, max_rows):
    import pandas as pd
    from IPython.display import display
    from pointlessql.pql.pql import PQL

    res = PQL.sql(query, approved_tables=approved_tables, max_rows=max_rows)
    # SQLResult.columns is list[dict[str, str]] with ``name`` / ``type``
    # entries — pandas needs the bare names as the column index.
    column_names = [c.get("name") if isinstance(c, dict) else c for c in res.columns]
    df = pd.DataFrame(list(res.rows), columns=column_names)
    if result_var:
        globals()[result_var] = df
    display(df)
    return None
"""


class KernelSession:
    """One ipykernel subprocess, shared across tabs of the same notebook.

    Lifecycle:

    1. Constructor returns immediately; the subprocess is not yet
       running. Call :meth:`start` to launch.
    2. :meth:`start` spawns the kernel (env enriched with
       ``POINTLESSQL_PRINCIPAL``), waits for channels-ready, and
       kicks off the iopub + shell pump tasks.
    3. Clients call :meth:`subscribe` / :meth:`unsubscribe` around
       their connection lifetime; :meth:`execute`, :meth:`interrupt`,
       and :meth:`restart` mutate kernel state.
    4. :meth:`shutdown` tears the subprocess down gracefully
       (SIGTERM + 5 s timeout, then SIGKILL — mirrors
       :func:`jupyter._shutdown`).

    ``session_id`` is a stable UUID for the kernel instance; it
    bumps on :meth:`restart` so the ``notebook_outputs`` table can
    key the pre- and post-restart rows apart without relying on
    Jupyter's internal ``self._kc.session.session`` (which also
    changes on restart but is not as explicit).

    Args:
        user_email: Exported to the kernel subprocess as
            ``POINTLESSQL_PRINCIPAL`` so ``pql``-driven UC calls
            inside the notebook inherit the calling user's identity.
        notebook_path: Relative path the session is bound to —
            carried for log context only; the registry does the
            lookup keyed by ``(user_id, path)``.
        cwd: Working directory the kernel starts in. Almost
            always ``Settings.jupyter.notebooks_dir``.
    """

    def __init__(
        self,
        *,
        user_email: str,
        notebook_path: str,
        cwd: Path,
    ) -> None:
        self._user_email = user_email
        self._notebook_path = notebook_path
        self._cwd = cwd
        self._km: AsyncKernelManager | None = None
        self._kc: AsyncKernelClient | None = None
        self.session_id: str = str(uuid.uuid4())
        self._msg_to_content_hash: dict[str, str] = {}
        self._subscribers: set[Subscription] = set()
        self._iopub_task: asyncio.Task[None] | None = None
        self._shell_task: asyncio.Task[None] | None = None
        self._exec_lock = asyncio.Lock()

    async def start(self) -> None:
        """Launch the kernel subprocess and start the pump tasks.

        A one-shot bootstrap execute (silent, no history) runs
        between ``wait_for_ready`` and the pump tasks so the
        ``__pql_sql_run`` helper is defined before any user execute
        can race a SQL cell run.  Bootstrap failure is logged but
        does NOT abort the session — Python cells still work; SQL
        cells will surface the missing-name error themselves.
        """
        env = os.environ.copy()
        env["POINTLESSQL_PRINCIPAL"] = self._user_email
        km = AsyncKernelManager()
        await km.start_kernel(env=env, cwd=str(self._cwd))
        kc: AsyncKernelClient = km.client()
        kc.start_channels()
        await kc.wait_for_ready(timeout=_KERNEL_READY_TIMEOUT)
        self._km = km
        self._kc = kc
        await self._run_bootstrap(kc)
        self._iopub_task = asyncio.create_task(
            self._pump("iopub"),
            name=f"kernel-iopub-{self.session_id[:8]}",
        )
        self._shell_task = asyncio.create_task(
            self._pump("shell"),
            name=f"kernel-shell-{self.session_id[:8]}",
        )
        logger.info(
            "kernel started for %s notebook=%s session_id=%s",
            self._user_email,
            self._notebook_path,
            self.session_id,
        )

    async def _run_bootstrap(self, kc: AsyncKernelClient) -> None:
        """Define ``__pql_sql_run`` in the kernel before pumps start.

        Runs a single ``silent=True`` ``execute_request`` and drains
        shell messages until the matching ``execute_reply`` arrives.
        The pump tasks are NOT yet running, so we read shell directly.
        Iopub messages produced during bootstrap are ignored by the
        client (no subscribers yet) — exactly what we want for a
        helper definition.
        """
        msg_id: str = kc.execute(
            _NOTEBOOK_BOOTSTRAP_CODE,
            silent=True,
            store_history=False,
        )
        deadline = asyncio.get_running_loop().time() + _BOOTSTRAP_TIMEOUT
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                logger.warning(
                    "kernel bootstrap timed out for %s notebook=%s",
                    self._user_email,
                    self._notebook_path,
                )
                return
            try:
                raw = await asyncio.wait_for(kc.get_shell_msg(), timeout=remaining)
            except TimeoutError:
                logger.warning(
                    "kernel bootstrap timed out for %s notebook=%s",
                    self._user_email,
                    self._notebook_path,
                )
                return
            except Exception:  # noqa: BLE001 — jupyter_client raises varied exceptions
                logger.exception("kernel bootstrap shell read failed")
                return
            if raw.get("parent_header", {}).get("msg_id") != msg_id:
                continue
            status = raw.get("content", {}).get("status")
            if status != "ok":
                logger.warning(
                    "kernel bootstrap reply status=%s for %s notebook=%s",
                    status,
                    self._user_email,
                    self._notebook_path,
                )
            return

    async def _pump(self, channel: str) -> None:
        """Drain one ZMQ channel into every subscriber's queue.

        Args:
            channel: ``"iopub"`` or ``"shell"``.
        """
        assert self._kc is not None
        get_msg = self._kc.get_iopub_msg if channel == "iopub" else self._kc.get_shell_msg
        while True:
            try:
                raw = await get_msg()
            except asyncio.CancelledError:
                return
            except Exception:  # noqa: BLE001 — jupyter_client raises varied exceptions
                logger.exception("kernel %s pump error", channel)
                await asyncio.sleep(0.1)
                continue
            parent_msg_id = raw.get("parent_header", {}).get("msg_id")
            content_hash = self._msg_to_content_hash.get(parent_msg_id) if parent_msg_id else None
            msg = KernelMessage(
                content_hash=content_hash,
                channel=channel,
                msg_type=raw.get("msg_type", "unknown"),
                content=raw.get("content", {}) or {},
                metadata=raw.get("metadata", {}) or {},
                parent_msg_id=parent_msg_id,
            )
            queue_attr = channel
            for sub in list(self._subscribers):
                queue: asyncio.Queue[KernelMessage] = getattr(sub, queue_attr)
                try:
                    queue.put_nowait(msg)
                except asyncio.QueueFull:
                    logger.warning("subscriber queue full on %s — dropping message", channel)

    def subscribe(self) -> Subscription:
        """Register a new subscriber for iopub + shell streams.

        Returns:
            A subscription handle the caller reads from via
            ``sub.iopub.get()`` / ``sub.shell.get()``. Unsubscribe
            via :meth:`unsubscribe` when the client disconnects.
        """
        sub = Subscription()
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: Subscription) -> None:
        """Drop a subscriber handle.

        Args:
            sub: The handle :meth:`subscribe` returned.
        """
        self._subscribers.discard(sub)

    async def execute(self, code: str, content_hash: str) -> str:
        """Send an ``execute_request`` to the kernel.

        Args:
            code: Python source to execute.
            content_hash: The cell's content-hash identity — stored
                so iopub replies tagged with the matching
                ``parent_header.msg_id`` can be routed back to the
                right cell. The content-derived identity replaces an
                earlier UUID ``cell_id`` argument so the editor can
                drop the marker UUID without losing message-to-cell
                routing.

        Returns:
            The Jupyter message ID.
        """
        assert self._kc is not None
        async with self._exec_lock:
            msg_id: str = self._kc.execute(code, silent=False, store_history=True)
            self._msg_to_content_hash[msg_id] = content_hash
            return msg_id

    async def interrupt(self) -> None:
        """Send SIGINT to the kernel (``KeyboardInterrupt`` inside)."""
        assert self._km is not None
        await self._km.interrupt_kernel()

    async def restart(self) -> None:
        """Restart the kernel in place. Bumps :attr:`session_id`.

        Re-queues the ``__pql_sql_run`` bootstrap after the restart
        so SQL cells keep working post-restart without requiring the
        user to re-execute a setup cell.  Goes through the regular
        ``execute`` path (with a reserved ``__pql_``-prefixed
        content_hash so persistence skips it) instead of reading
        shell directly — the iopub / shell pump tasks are still
        alive across a restart and would otherwise consume the
        bootstrap reply before we could read it.  The kernel
        serialises execute_requests, so the next user SQL execute is
        guaranteed to see the helper defined.
        """
        assert self._km is not None
        await self._km.restart_kernel()
        self.session_id = str(uuid.uuid4())
        self._msg_to_content_hash.clear()
        await self.execute(_NOTEBOOK_BOOTSTRAP_CODE, "__pql_sql_bootstrap__")
        logger.info(
            "kernel restarted for %s notebook=%s new_session_id=%s",
            self._user_email,
            self._notebook_path,
            self.session_id,
        )

    async def shutdown(self) -> None:
        """Tear the kernel subprocess down gracefully.

        Graceful shutdown with a 5 s timeout, then hard kill.
        """
        for task in (self._iopub_task, self._shell_task):
            if task is not None and not task.done():
                task.cancel()
        if self._kc is not None:
            self._kc.stop_channels()
        if self._km is not None:
            try:
                await asyncio.wait_for(
                    self._km.shutdown_kernel(),
                    timeout=_SHUTDOWN_TIMEOUT,
                )
            except TimeoutError:
                logger.warning(
                    "kernel for %s did not stop in %.0f s — force-killing",
                    self._user_email,
                    _SHUTDOWN_TIMEOUT,
                )
                await self._km.shutdown_kernel(now=True)
        logger.info(
            "kernel shut down for %s notebook=%s",
            self._user_email,
            self._notebook_path,
        )
