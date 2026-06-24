"""Idle notebook kernels are reaped and the live-kernel count is capped.

Each ``(user, notebook)`` pair holds an ipykernel subprocess for the
process lifetime, so without reaping they accumulate and threaten PID /
memory exhaustion on shared deploys. These exercise the registry's idle
reaper, its LRU cap eviction, the per-session activity stamp, and the
background loop's disabled short-circuit — all without spawning a real
kernel subprocess.
"""

from __future__ import annotations

import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from pointlessql.api._bootstrap._loops._platform import _kernel_reaper_loop
from pointlessql.config import Settings
from pointlessql.services.notebook.kernel_session import KernelRegistry
from pointlessql.services.notebook.kernel_session.session import KernelSession


class _FakeSession:
    """A KernelSession stand-in exposing only what the registry touches."""

    def __init__(self, last_activity: float) -> None:
        self.last_activity = last_activity
        self.shutdown_called = False

    async def shutdown(self) -> None:
        self.shutdown_called = True

    def touch(self) -> None:
        self.last_activity = time.monotonic()


async def test_reap_idle_shuts_down_only_idle_sessions() -> None:
    """A session past the idle TTL is reaped; a recently-active one survives."""
    reg = KernelRegistry(notebooks_dir=Path("."))
    now = time.monotonic()
    idle = _FakeSession(now - 1000)
    active = _FakeSession(now)
    reg._sessions[(1, "idle.py")] = idle  # type: ignore[assignment]
    reg._sessions[(2, "active.py")] = active  # type: ignore[assignment]

    reaped = await reg.reap_idle(max_idle_seconds=600, now=now)

    assert reaped == 1
    assert idle.shutdown_called
    assert not active.shutdown_called
    assert (1, "idle.py") not in reg._sessions
    assert (2, "active.py") in reg._sessions


async def test_reap_idle_disabled_for_non_positive_ttl() -> None:
    """A non-positive TTL disables reaping entirely."""
    reg = KernelRegistry(notebooks_dir=Path("."))
    reg._sessions[(1, "x.py")] = _FakeSession(0.0)  # type: ignore[assignment]

    assert await reg.reap_idle(0) == 0
    assert (1, "x.py") in reg._sessions


async def test_cap_evicts_least_recently_active() -> None:
    """At the cap, the least-recently-active session is evicted first."""
    reg = KernelRegistry(notebooks_dir=Path("."), max_kernels=2)
    now = time.monotonic()
    lru = _FakeSession(now - 100)
    fresh = _FakeSession(now)
    reg._sessions[(1, "lru.py")] = lru  # type: ignore[assignment]
    reg._sessions[(2, "fresh.py")] = fresh  # type: ignore[assignment]

    await reg._evict_for_capacity_locked()

    assert lru.shutdown_called
    assert (1, "lru.py") not in reg._sessions
    assert (2, "fresh.py") in reg._sessions


async def test_cap_headroom_does_not_evict() -> None:
    """Below the cap nothing is evicted."""
    reg = KernelRegistry(notebooks_dir=Path("."), max_kernels=5)
    only = _FakeSession(time.monotonic())
    reg._sessions[(1, "a.py")] = only  # type: ignore[assignment]

    await reg._evict_for_capacity_locked()

    assert not only.shutdown_called


async def test_cap_disabled_never_evicts() -> None:
    """``max_kernels=0`` means unlimited — eviction is a no-op."""
    reg = KernelRegistry(notebooks_dir=Path("."), max_kernels=0)
    only = _FakeSession(time.monotonic())
    reg._sessions[(1, "a.py")] = only  # type: ignore[assignment]

    await reg._evict_for_capacity_locked()

    assert not only.shutdown_called


def test_session_touch_bumps_last_activity() -> None:
    """``touch`` advances the session's monotonic activity stamp."""
    session = KernelSession(user_email="u@x.com", notebook_path="n.py", cwd=Path("."))
    session.last_activity = 0.0

    session.touch()

    assert session.last_activity > 0.0


async def test_reaper_loop_returns_immediately_when_disabled() -> None:
    """With the TTL at 0 the background loop exits without ever reaping."""
    settings = Settings(jupyter={"kernel_idle_ttl_seconds": 0})
    registry = SimpleNamespace(reap_idle=AsyncMock())

    await _kernel_reaper_loop(registry, settings)

    registry.reap_idle.assert_not_awaited()
