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

from pointlessql.services.notebook.kernel_session.messages import (
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
    from pointlessql.pql import PQL

    res = PQL.sql(query, approved_tables=approved_tables, max_rows=max_rows)
    # SQLResult.columns is list[dict[str, str]] with ``name`` / ``type``
    # entries — pandas needs the bare names as the column index.
    column_names = [c.get("name") if isinstance(c, dict) else c for c in res.columns]
    df = pd.DataFrame(list(res.rows), columns=column_names)
    if result_var:
        globals()[result_var] = df
    display(df)
    return None


# Variable Inspector helpers.
#
# `__pql_inspect__` emits a list of {name, type, repr, size?} dicts for
# every user-visible global as a custom-MIME ``display_data`` frame.
# The WS pump intercepts the MIME and forwards a ``variable_snapshot``
# notify to the browser instead of persisting it.  Calling silently
# after every successful cell run gives the editor a live namespace
# pane without polling.
def __pql_inspect__():
    import types
    from IPython.display import display

    out = []
    for k, v in list(globals().items()):
        if k.startswith("_") or k.startswith("__pql_"):
            continue
        if isinstance(v, types.ModuleType):
            continue
        if callable(v) and not isinstance(v, type):
            continue
        try:
            short = repr(v)
        except Exception as exc:  # noqa: BLE001
            short = f"<unreprable: {type(exc).__name__}>"
        if len(short) > 200:
            short = short[:197] + "..."
        entry = {"name": k, "type": type(v).__name__, "repr": short}
        try:
            shape = getattr(v, "shape", None)
            if isinstance(shape, tuple):
                entry["shape"] = [int(d) for d in shape]
            elif hasattr(v, "__len__") and not isinstance(v, (str, bytes)):
                entry["len"] = len(v)
        except Exception:  # noqa: BLE001
            pass
        out.append(entry)
    display({"application/x-pql-vars+json": out}, raw=True)
    return None


def __pql_inspect_detail__(varname):
    from IPython.display import display

    if not isinstance(varname, str) or not varname:
        return None
    if varname.startswith("_") or varname.startswith("__pql_"):
        return None
    if varname not in globals():
        return None
    v = globals()[varname]
    detail = {"name": varname, "type": type(v).__name__}
    try:
        detail["repr"] = repr(v)[:5000]
    except Exception as exc:  # noqa: BLE001
        detail["repr"] = f"<unreprable: {type(exc).__name__}>"
    try:
        if hasattr(v, "head") and callable(getattr(v, "head")):
            head_df = v.head(5)
            if hasattr(head_df, "_repr_html_"):
                detail["html"] = head_df._repr_html_()
    except Exception:  # noqa: BLE001
        pass
    display({"application/x-pql-vardetail+json": detail}, raw=True)
    return None


# magic-command helpers.  The WS pre-processor
# (``pointlessql.services.notebook.magic_commands``) rewrites every
# recognised ``%magic`` line into a call to one of these.  The helpers
# all use ``IPython.display.display`` so the iopub stream carries the
# rendered output exactly like a normal cell result — the existing
# ``output_renderer.js`` path handles it without further wiring.
def __pql_magic_md__(markdown_source):
    from IPython.display import Markdown, display

    display(Markdown(str(markdown_source)))
    return None


def __pql_magic_fs_ls__(path):
    import os as _os

    from IPython.display import display

    p = (path or ".").strip()
    if p.startswith("file://"):
        p = p[len("file://") :]
    try:
        entries = sorted(_os.listdir(p))
    except FileNotFoundError:
        display({"text/plain": f"%fs ls: no such path: {p!r}"}, raw=True)
        return None
    except PermissionError:
        display({"text/plain": f"%fs ls: permission denied: {p!r}"}, raw=True)
        return None
    rows = []
    for name in entries:
        full = _os.path.join(p, name)
        try:
            st = _os.stat(full)
            kind = "dir" if _os.path.isdir(full) else "file"
            rows.append({"name": name, "kind": kind, "size": int(st.st_size)})
        except OSError:
            rows.append({"name": name, "kind": "?", "size": 0})
    display({"application/x-pql-fs-ls+json": {"path": p, "entries": rows}}, raw=True)
    return None


def __pql_magic_timeit__(expr_source):
    import timeit as _timeit

    from IPython.display import display

    expr = str(expr_source)
    try:
        # First a single run to estimate; then repeat=3 with autoscaled
        # ``number`` so quick expressions get many iterations and slow
        # ones still finish promptly.
        single = _timeit.timeit(expr, globals=globals(), number=1)
        if single <= 0:
            number = 1_000_000
        else:
            number = max(1, int(0.1 / max(single, 1e-9)))
        runs = _timeit.repeat(expr, globals=globals(), repeat=3, number=number)
        best = min(runs) / number
    except Exception as exc:  # noqa: BLE001
        display({"text/plain": f"%timeit error: {type(exc).__name__}: {exc}"}, raw=True)
        return None

    if best < 1e-6:
        human = f"{best * 1e9:.1f} ns"
    elif best < 1e-3:
        human = f"{best * 1e6:.1f} µs"
    elif best < 1:
        human = f"{best * 1e3:.1f} ms"
    else:
        human = f"{best:.3f} s"
    display(
        {"text/plain": f"{human} per loop (best of 3; number={number})"},
        raw=True,
    )
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
        notebook_id: Optional notebook UUID surfaced to the kernel
            as ``POINTLESSQL_NOTEBOOK_ID`` so ``pql.context``
            resolves widget values and per-notebook permissions.
        branch_name: Optional branch binding surfaced as
            ``POINTLESSQL_BRANCH`` so Delta reads/writes scope to
            the chosen branch branch-aware notebooks.
    """

    def __init__(
        self,
        *,
        user_email: str,
        notebook_path: str,
        cwd: Path,
        notebook_id: str | None = None,
        branch_name: str | None = None,
    ) -> None:
        self._user_email = user_email
        self._notebook_path = notebook_path
        self._cwd = cwd
        # context the kernel needs but cell
        # source code shouldn't touch directly.  Surfaced as env vars
        # so PQL + pointlessql.pql.context pick them up on
        # ``import pointlessql.pql`` at kernel-start time.  Mid-session
        # binding edits aren't yet pushed (would require a per-execute
        # silent prelude); the panel UI documents the restart contract.
        self._notebook_id = notebook_id
        self._branch_name = branch_name
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
        # surface notebook context + active
        # branch binding so ``pointlessql.pql.context`` and
        # ``PQL._branch_remap`` see them on first import.
        if self._notebook_id:
            env["POINTLESSQL_NOTEBOOK_ID"] = self._notebook_id
        if self._branch_name:
            env["POINTLESSQL_BRANCH"] = self._branch_name
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

    async def execute(
        self,
        code: str,
        content_hash: str,
        *,
        silent: bool = False,
    ) -> str:
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
            silent: When ``True``, set ``store_history=False`` on
                the kernel request — the Variable Inspector polls
                use this so they don't push every probe onto
                IPython's ``_ih`` / ``_oh`` history lists (caught
                the inspector inflated
                ``In list[…]`` indefinitely).  Note: the Jupyter
                ``silent`` flag itself stays ``False`` because the
                inspector still needs its custom-MIME iopub frame
                to arrive — only history recording is suppressed.

        Returns:
            The Jupyter message ID.
        """
        assert self._kc is not None
        async with self._exec_lock:
            msg_id: str = self._kc.execute(
                code,
                silent=False,
                store_history=not silent,
            )
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
