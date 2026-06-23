"""Kernel-start failure reaps the subprocess instead of orphaning it.

When :meth:`KernelSession.start` has already spawned the ipykernel
subprocess but a later step fails — the readiness wait timing out is the
common case on a slow or dead kernel — the half-started kernel must be
torn down before the exception propagates.  Otherwise the process is
orphaned: ``KernelRegistry.get_or_start`` only records the session on
success, so nothing else can ever reach the kernel to reap it, and the
idle reaper never sees it.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pointlessql.services.notebook.kernel_session.session import KernelSession


async def test_readiness_timeout_reaps_kernel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A ``wait_for_ready`` timeout shuts the kernel down and re-raises.

    Proves the failure path does not leak the subprocess: ``shutdown_kernel``
    is invoked (the process is reaped) and the ZMQ channels are stopped,
    and the original ``TimeoutError`` still surfaces to the caller.
    """
    shutdown_now_flags: list[bool] = []

    fake_client = MagicMock()
    fake_client.start_channels = MagicMock()
    fake_client.stop_channels = MagicMock()
    fake_client.wait_for_ready = AsyncMock(side_effect=TimeoutError)

    class _FakeManager:
        async def start_kernel(self, **_kwargs: Any) -> None:
            return None

        def client(self) -> Any:
            return fake_client

        async def shutdown_kernel(self, now: bool = False) -> None:
            shutdown_now_flags.append(now)

    monkeypatch.setattr(
        "pointlessql.services.notebook.kernel_session.session.AsyncKernelManager",
        _FakeManager,
    )

    session = KernelSession(
        user_email="user@example.com",
        notebook_path="demo.py",
        cwd=tmp_path,
    )

    with pytest.raises(TimeoutError):
        await session.start()

    # The subprocess was reaped (shutdown_kernel ran) and the channels were
    # stopped — no orphaned kernel is left behind on the failure path.
    assert shutdown_now_flags, "kernel was not shut down on start failure"
    fake_client.stop_channels.assert_called_once()


async def test_bootstrap_failure_reaps_kernel(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A bootstrap-step crash after spawn also reaps the kernel.

    ``wait_for_ready`` succeeds but ``_run_bootstrap`` raises an unexpected
    error; the kernel must still be torn down before the error propagates.
    """
    shutdown_now_flags: list[bool] = []

    fake_client = MagicMock()
    fake_client.start_channels = MagicMock()
    fake_client.stop_channels = MagicMock()
    fake_client.wait_for_ready = AsyncMock()

    class _FakeManager:
        async def start_kernel(self, **_kwargs: Any) -> None:
            return None

        def client(self) -> Any:
            return fake_client

        async def shutdown_kernel(self, now: bool = False) -> None:
            shutdown_now_flags.append(now)

    monkeypatch.setattr(
        "pointlessql.services.notebook.kernel_session.session.AsyncKernelManager",
        _FakeManager,
    )
    monkeypatch.setattr(
        KernelSession,
        "_run_bootstrap",
        AsyncMock(side_effect=RuntimeError("bootstrap boom")),
    )

    session = KernelSession(
        user_email="user@example.com",
        notebook_path="demo.py",
        cwd=tmp_path,
    )

    with pytest.raises(RuntimeError, match="bootstrap boom"):
        await session.start()

    assert shutdown_now_flags, "kernel was not shut down on bootstrap failure"
    fake_client.stop_channels.assert_called_once()
