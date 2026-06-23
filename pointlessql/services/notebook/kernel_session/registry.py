"""Process-global :class:`KernelRegistry` + the :func:`drain` helper.

The registry maps ``(user_id, notebook_path) → KernelSession`` and is
created once during the FastAPI lifespan, attached to ``app.state``,
and torn down on shutdown. The ``drain`` coroutine yields messages
from a subscriber queue forever; it lives here rather than in the WS
handler so the await-on-queue idiom has a single documented home.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator
from pathlib import Path

from pointlessql.services.notebook.kernel_session.messages import KernelMessage
from pointlessql.services.notebook.kernel_session.session import KernelSession

logger = logging.getLogger(__name__)


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
        max_kernels: Hard cap on concurrently live kernels. When a new
            kernel would exceed it, the least-recently-active session is
            evicted first. ``0`` (the default) means unlimited.
    """

    def __init__(self, notebooks_dir: Path, *, max_kernels: int = 0) -> None:
        self._notebooks_dir = notebooks_dir
        self._max_kernels = max_kernels
        self._sessions: dict[tuple[int, str], KernelSession] = {}
        self._lock = asyncio.Lock()

    async def get_or_start(
        self,
        user_id: int,
        user_email: str,
        notebook_path: str,
        *,
        notebook_id: str | None = None,
        branch_name: str | None = None,
        workspace_id: int | None = None,
    ) -> KernelSession:
        """Return the kernel for ``(user_id, notebook_path)``, launching if absent.

        Args:
            user_id: Authenticated user id.
            user_email: Used as ``POINTLESSQL_PRINCIPAL`` on start.
            notebook_path: Relative notebook path (stable key).
            notebook_id: Phase-77.6 notebook UUID surfaced to the
                kernel via ``POINTLESSQL_NOTEBOOK_ID`` so binding
                lookups + future widget-resolve queries can address
                the notebook by its stable id.
            branch_name: Active Phase-102 branch binding surfaced via
                ``POINTLESSQL_BRANCH``; ``PQL._branch_remap`` reads
                it on every read / write to route the FQN to the
                bound branch schema.
            workspace_id: Active workspace surfaced via
                ``POINTLESSQL_WORKSPACE_ID`` so the in-kernel
                secrets getter resolves scopes against the right
                workspace.

        Returns:
            A running :class:`KernelSession`.
        """
        key = (user_id, notebook_path)
        async with self._lock:
            session = self._sessions.get(key)
            if session is None:
                await self._evict_for_capacity_locked()
                session = KernelSession(
                    user_email=user_email,
                    notebook_path=notebook_path,
                    cwd=self._notebooks_dir,
                    notebook_id=notebook_id,
                    branch_name=branch_name,
                    workspace_id=workspace_id,
                )
                await session.start()
                self._sessions[key] = session
            session.touch()
            return session

    async def _evict_for_capacity_locked(self) -> None:
        """Evict the least-recently-active kernel when at the cap.

        Must be called while holding :attr:`_lock`, right before a new
        session is inserted, so the live-kernel count never exceeds
        ``max_kernels``.  A no-op when the cap is disabled (``0``) or there
        is still headroom.
        """
        if self._max_kernels <= 0 or len(self._sessions) < self._max_kernels:
            return
        lru_key = min(self._sessions, key=lambda k: self._sessions[k].last_activity)
        victim = self._sessions.pop(lru_key)
        logger.info("kernel cap reached (%d) — evicting LRU session", self._max_kernels)
        await victim.shutdown()

    async def reap_idle(self, max_idle_seconds: float, *, now: float | None = None) -> int:
        """Shut down and forget kernels idle beyond ``max_idle_seconds``.

        Each kernel is an ipykernel subprocess held for the process
        lifetime; without reaping, every ``(user, notebook)`` pair leaks
        one for the life of the server. The background reaper calls this on
        a cadence so only kernels with a recently-active editor survive.

        Args:
            max_idle_seconds: Idle cutoff in seconds; a session whose last
                activity is older than this is reaped. Non-positive
                disables reaping (returns ``0``).
            now: Monotonic reference time; defaults to ``time.monotonic()``
                and is injectable so tests can advance the clock.

        Returns:
            The number of kernels shut down.
        """
        if max_idle_seconds <= 0:
            return 0
        cutoff = now if now is not None else time.monotonic()
        async with self._lock:
            stale = [
                (key, session)
                for key, session in self._sessions.items()
                if cutoff - session.last_activity > max_idle_seconds
            ]
            for key, _ in stale:
                del self._sessions[key]
        await asyncio.gather(
            *(session.shutdown() for _, session in stale),
            return_exceptions=True,
        )
        return len(stale)

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
