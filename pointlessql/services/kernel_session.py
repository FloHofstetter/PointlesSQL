"""Per-notebook ipykernel subprocess manager for the native editor.

Phase 12.6 Sprint 59 — second layer of the native notebook story.
One ipykernel subprocess runs per ``(user_id, notebook_path)`` pair
(ADR 0001 "kernel identity" decision: VSCode-style, not Jupyter-
classic-style-per-tab). Two browser tabs of the same ``.py`` share
one kernel, one namespace, one ``kernel_session_id``.

The module has two halves:

* :class:`KernelSession` wraps a single kernel subprocess and
  exposes async iopub / shell streams as subscriber queues. A
  single pump task reads from ZMQ and fans out to every subscriber,
  which lets N browser tabs watch the same kernel without starving
  each other on the ZMQ queue.
* :class:`KernelRegistry` owns the dict of live sessions keyed by
  ``(user_id, notebook_path)``. Registered on ``app.state`` from
  the FastAPI lifespan so shutdown is coordinated with the rest of
  the app.

Sprint 59 deliberately stops at text / stream / error outputs
flowing ephemerally to the connected client. Sprint 60 persists
outputs in SQLite keyed by ``(file_path, cell_id,
kernel_session_id)`` — the schema is locked in ADR 0001 already,
so this sprint writes its in-memory shape against it without fuss.
"""

from __future__ import annotations

import asyncio
import logging
import os
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from jupyter_client.asynchronous.client import AsyncKernelClient  # type: ignore[import-untyped]
from jupyter_client.manager import AsyncKernelManager  # type: ignore[import-untyped]

logger = logging.getLogger(__name__)

_KERNEL_READY_TIMEOUT = 30.0
_SHUTDOWN_TIMEOUT = 5.0
_SUBSCRIBER_QUEUE_MAXSIZE = 1024


@dataclass
class KernelMessage:
    """A single iopub / shell message on its way from kernel to client.

    Attributes:
        cell_id: Source cell's UUID when the kernel's parent message
            originated from a tracked ``execute_request``. Kernel-
            initiated messages (status heartbeats, display from
            untracked code) carry ``None``.
        channel: ``"iopub"`` or ``"shell"``.
        msg_type: Raw Jupyter msg type (``stream``,
            ``execute_result``, ``display_data``, ``error``,
            ``status``, ``execute_input``, ``execute_reply``, …).
        content: Raw message content dict — structure varies by
            msg_type. See the Jupyter messaging spec.
        metadata: Raw metadata dict. Rare; usually empty.
        parent_msg_id: The ``execute_request`` msg_id this is a reply
            to, when applicable.
    """

    cell_id: str | None
    channel: str
    msg_type: str
    content: dict[str, Any]
    metadata: dict[str, Any]
    parent_msg_id: str | None


@dataclass(eq=False)
class _Subscription:
    """A pair of per-client queues fed by the session pump tasks.

    ``eq=False`` keeps the dataclass hashable by object identity so
    instances can live in the ``set[_Subscription]`` on
    :class:`KernelSession` without colliding on value-equality.
    """

    iopub: asyncio.Queue[KernelMessage] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAXSIZE)
    )
    shell: asyncio.Queue[KernelMessage] = field(
        default_factory=lambda: asyncio.Queue(maxsize=_SUBSCRIBER_QUEUE_MAXSIZE)
    )


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
    bumps on :meth:`restart` so Sprint-60's ``notebook_outputs``
    table can key the pre- and post-restart rows apart without
    relying on Jupyter's internal ``self._kc.session.session``
    (which also changes on restart but is not as explicit).

    Args:
        user_email: Exported to the kernel subprocess as
            ``POINTLESSQL_PRINCIPAL`` so ``pql``-driven UC calls
            inside the notebook inherit the Phase-3 identity.
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
        self._msg_to_cell: dict[str, str] = {}
        self._subscribers: set[_Subscription] = set()
        self._iopub_task: asyncio.Task[None] | None = None
        self._shell_task: asyncio.Task[None] | None = None
        self._exec_lock = asyncio.Lock()

    async def start(self) -> None:
        """Launch the kernel subprocess and start the pump tasks."""
        env = os.environ.copy()
        env["POINTLESSQL_PRINCIPAL"] = self._user_email
        km = AsyncKernelManager()
        await km.start_kernel(env=env, cwd=str(self._cwd))
        kc: AsyncKernelClient = km.client()
        kc.start_channels()
        await kc.wait_for_ready(timeout=_KERNEL_READY_TIMEOUT)
        self._km = km
        self._kc = kc
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

    async def _pump(self, channel: str) -> None:
        """Drain one ZMQ channel into every subscriber's queue.

        Args:
            channel: ``"iopub"`` or ``"shell"``.
        """
        assert self._kc is not None
        get_msg = (
            self._kc.get_iopub_msg if channel == "iopub" else self._kc.get_shell_msg
        )
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
            cell_id = (
                self._msg_to_cell.get(parent_msg_id) if parent_msg_id else None
            )
            msg = KernelMessage(
                cell_id=cell_id,
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
                    logger.warning(
                        "subscriber queue full on %s — dropping message", channel
                    )

    def subscribe(self) -> _Subscription:
        """Register a new subscriber for iopub + shell streams.

        Returns:
            A subscription handle the caller reads from via
            ``sub.iopub.get()`` / ``sub.shell.get()``. Unsubscribe
            via :meth:`unsubscribe` when the client disconnects.
        """
        sub = _Subscription()
        self._subscribers.add(sub)
        return sub

    def unsubscribe(self, sub: _Subscription) -> None:
        """Drop a subscriber handle.

        Args:
            sub: The handle :meth:`subscribe` returned.
        """
        self._subscribers.discard(sub)

    async def execute(self, code: str, cell_id: str) -> str:
        """Send an ``execute_request`` to the kernel.

        Args:
            code: Python source to execute.
            cell_id: The cell's UUID — stored so iopub replies
                tagged with the matching ``parent_header.msg_id``
                can be routed back to the right cell.

        Returns:
            The Jupyter message ID.
        """
        assert self._kc is not None
        async with self._exec_lock:
            msg_id: str = self._kc.execute(code, silent=False, store_history=True)
            self._msg_to_cell[msg_id] = cell_id
            return msg_id

    async def interrupt(self) -> None:
        """Send SIGINT to the kernel (``KeyboardInterrupt`` inside)."""
        assert self._km is not None
        await self._km.interrupt_kernel()

    async def restart(self) -> None:
        """Restart the kernel in place. Bumps :attr:`session_id`."""
        assert self._km is not None
        await self._km.restart_kernel()
        self.session_id = str(uuid.uuid4())
        self._msg_to_cell.clear()
        logger.info(
            "kernel restarted for %s notebook=%s new_session_id=%s",
            self._user_email,
            self._notebook_path,
            self.session_id,
        )

    async def shutdown(self) -> None:
        """Tear the kernel subprocess down gracefully.

        Mirrors :func:`pointlessql.services.jupyter._shutdown`:
        graceful shutdown with a 5 s timeout, then hard kill.
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


class KernelRegistry:
    """Process-global map of live kernels, keyed by ``(user_id, path)``.

    One instance lives on ``app.state.kernel_registry`` for the
    lifetime of the FastAPI process. The lifespan context manager
    creates it, hands it to the WS route handler, and calls
    :meth:`shutdown_all` on app exit to clean up every in-flight
    subprocess.

    Args:
        notebooks_dir: Kernel working directory root — the cwd
            every spawned kernel inherits.
    """

    def __init__(self, notebooks_dir: Path) -> None:
        self._notebooks_dir = notebooks_dir
        self._sessions: dict[tuple[int, str], KernelSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_start(
        self,
        user_id: int,
        user_email: str,
        notebook_path: str,
    ) -> KernelSession:
        """Return the kernel for ``(user_id, notebook_path)``, launching if absent.

        Args:
            user_id: Authenticated user id.
            user_email: Used as ``POINTLESSQL_PRINCIPAL`` on start.
            notebook_path: Relative notebook path (stable key).

        Returns:
            A running :class:`KernelSession`.
        """
        key = (user_id, notebook_path)
        async with self._lock:
            session = self._sessions.get(key)
            if session is None:
                session = KernelSession(
                    user_email=user_email,
                    notebook_path=notebook_path,
                    cwd=self._notebooks_dir,
                )
                await session.start()
                self._sessions[key] = session
            return session

    async def shutdown_all(self) -> None:
        """Tear down every live kernel. Called from the FastAPI lifespan."""
        sessions = list(self._sessions.values())
        self._sessions.clear()
        await asyncio.gather(
            *(s.shutdown() for s in sessions),
            return_exceptions=True,
        )


async def drain(
    queue: asyncio.Queue[KernelMessage],
) -> AsyncIterator[KernelMessage]:
    """Yield kernel messages forever until the caller cancels.

    Small helper kept here rather than in the WS handler so the
    await-on-queue pattern has a single, documented home.

    Args:
        queue: A subscriber queue returned from
            :meth:`KernelSession.subscribe`.

    Yields:
        Each :class:`KernelMessage` in arrival order.
    """
    while True:
        yield await queue.get()
