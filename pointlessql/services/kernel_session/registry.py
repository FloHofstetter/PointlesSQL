"""Process-global :class:`KernelRegistry` + the :func:`drain` helper.

The registry maps ``(user_id, notebook_path) → KernelSession`` and is
created once during the FastAPI lifespan, attached to ``app.state``,
and torn down on shutdown. The ``drain`` coroutine yields messages
from a subscriber queue forever; it lives here rather than in the WS
handler so the await-on-queue idiom has a single documented home.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

from pointlessql.services.kernel_session.messages import KernelMessage
from pointlessql.services.kernel_session.session import KernelSession


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
