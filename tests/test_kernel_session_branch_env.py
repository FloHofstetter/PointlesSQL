"""start-time env injection.

The Phase 102 branch-aware notebook contract has two layers:

1. The :class:`~pointlessql.services.notebook.kernel_session.KernelSession`
   forwards ``POINTLESSQL_BRANCH`` into the subprocess env when a
   binding is active at kernel start.
2. Kernel-side, :func:`pointlessql.pql.context.current_branch` reads
   the env on first import and :meth:`PQL._branch_remap` consults
   it on every read / write.

Layer 2 is covered by ``TestPQLBranchRemap`` in ``test_pql.py``.
This module covers layer 1: when ``branch_name`` is passed to the
:class:`KernelSession` constructor, the kernel subprocess receives
``POINTLESSQL_BRANCH=<value>``.  We patch ``AsyncKernelManager`` to
capture the ``env`` kwarg rather than spawning a real kernel — the
kernel-start path is otherwise integration-tested in
``test_notebook_kernel_execute.py``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pointlessql.services.notebook.kernel_session.session import KernelSession


@pytest.fixture
def patched_kernel(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Replace ``AsyncKernelManager`` with a recorder.

    Returns a captured dict so the test can inspect what the
    session forwarded to the subprocess.  Bypasses bootstrap and
    pump-task creation — we only assert on the env handoff.
    """
    captured: dict[str, Any] = {}

    class _FakeManager:
        async def start_kernel(self, **kwargs: Any) -> None:
            captured["env"] = kwargs.get("env")
            captured["cwd"] = kwargs.get("cwd")

        def client(self) -> Any:
            client = MagicMock()
            client.start_channels = MagicMock()
            client.wait_for_ready = AsyncMock()
            client.execute = MagicMock(return_value="msg-bootstrap")
            client.get_shell_msg = AsyncMock(
                return_value={
                    "parent_header": {"msg_id": "msg-bootstrap"},
                    "content": {"status": "ok"},
                }
            )
            return client

    monkeypatch.setattr(
        "pointlessql.services.notebook.kernel_session.session.AsyncKernelManager",
        _FakeManager,
    )
    # Stub the pump tasks so start() returns without leaving
    # dangling asyncio tasks.
    monkeypatch.setattr(
        KernelSession, "_pump", AsyncMock(return_value=None), raising=True
    )
    return captured


async def test_branch_name_forwarded_as_env_var(
    tmp_path: Path, patched_kernel: dict[str, Any]
) -> None:
    """``branch_name`` set → ``POINTLESSQL_BRANCH`` lands in kernel env."""
    session = KernelSession(
        user_email="user@example.com",
        notebook_path="demo.py",
        cwd=tmp_path,
        notebook_id="nb-uuid-123",
        branch_name="feature_x",
    )
    await session.start()
    env = patched_kernel["env"]
    assert env is not None
    assert env["POINTLESSQL_BRANCH"] == "feature_x"
    assert env["POINTLESSQL_NOTEBOOK_ID"] == "nb-uuid-123"
    assert env["POINTLESSQL_PRINCIPAL"] == "user@example.com"


async def test_no_branch_omits_env_var(
    tmp_path: Path, patched_kernel: dict[str, Any]
) -> None:
    """``branch_name=None`` → key is NOT set (so context falls back).

    The kernel-side ``current_branch()`` returns ``None`` either
    when the env var is absent or empty; consciously *not* setting
    the var (rather than setting it to ``""``) keeps the contract
    aligned with the registry's ``binding is None`` branch.
    """
    session = KernelSession(
        user_email="user@example.com",
        notebook_path="demo.py",
        cwd=tmp_path,
        notebook_id="nb-uuid-123",
        branch_name=None,
    )
    await session.start()
    env = patched_kernel["env"]
    assert env is not None
    assert "POINTLESSQL_BRANCH" not in env
    # Notebook id still surfaces — Phase-99 widget-resolve uses it
    # independently of the Phase-102 branch wiring.
    assert env["POINTLESSQL_NOTEBOOK_ID"] == "nb-uuid-123"


async def test_branch_passes_through_when_notebook_id_missing(
    tmp_path: Path, patched_kernel: dict[str, Any]
) -> None:
    """Branch env-bridge does not depend on ``notebook_id`` being set.

    Replay-mode kernel spawns (see ``replay_worker.py``) set the
    branch directly without a notebook_id binding; the env-bridge
    must still surface ``POINTLESSQL_BRANCH``.
    """
    session = KernelSession(
        user_email="user@example.com",
        notebook_path="replay-tmp.py",
        cwd=tmp_path,
        notebook_id=None,
        branch_name="feature_y",
    )
    await session.start()
    env = patched_kernel["env"]
    assert env is not None
    assert env["POINTLESSQL_BRANCH"] == "feature_y"
    assert "POINTLESSQL_NOTEBOOK_ID" not in env


@patch(
    "pointlessql.services.notebook.kernel_session.session.AsyncKernelManager",
)
async def test_registry_propagates_branch_to_new_session(
    fake_manager_cls: MagicMock,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``KernelRegistry.get_or_start`` plumbs ``branch_name`` through.

    The WS open path resolves the active binding and passes
    ``branch_name`` to the registry; the registry passes it to
    ``KernelSession.__init__``; the session passes it to
    ``start_kernel(env=...)``.  This test exercises that chain
    end-to-end against a faked kernel manager.
    """
    from pointlessql.services.notebook.kernel_session.registry import KernelRegistry

    captured_env: dict[str, str] = {}

    class _FakeManager:
        async def start_kernel(self, **kwargs: Any) -> None:
            captured_env.update(kwargs.get("env") or {})

        def client(self) -> Any:
            client = MagicMock()
            client.start_channels = MagicMock()
            client.wait_for_ready = AsyncMock()
            client.execute = MagicMock(return_value="msg-bootstrap")
            client.get_shell_msg = AsyncMock(
                return_value={
                    "parent_header": {"msg_id": "msg-bootstrap"},
                    "content": {"status": "ok"},
                }
            )
            return client

    fake_manager_cls.side_effect = _FakeManager
    monkeypatch.setattr(
        KernelSession, "_pump", AsyncMock(return_value=None), raising=True
    )

    registry = KernelRegistry(notebooks_dir=tmp_path)
    await registry.get_or_start(
        user_id=42,
        user_email="alice@example.com",
        notebook_path="demo.py",
        notebook_id="nb-xyz",
        branch_name="rebind_target",
    )
    assert captured_env.get("POINTLESSQL_BRANCH") == "rebind_target"
    assert captured_env.get("POINTLESSQL_NOTEBOOK_ID") == "nb-xyz"
