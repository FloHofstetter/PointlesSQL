"""Tests for the in-kernel secrets getter (env identity, ACLs, audit)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import AuditLog
from pointlessql.services import secret_runtime
from pointlessql.services import secret_scopes as svc

NON_ADMIN = "nonadmin@test.com"


@pytest.fixture(autouse=True)
def _kernel_env(monkeypatch):
    """Pretend to be a kernel subprocess of the test app."""
    monkeypatch.setattr(secret_runtime, "_factory", app.state.session_factory)
    monkeypatch.setenv("POINTLESSQL_PRINCIPAL", NON_ADMIN)
    monkeypatch.setenv("POINTLESSQL_WORKSPACE_ID", "1")


def _factory():
    return app.state.session_factory


def test_get_secret_roundtrip_and_audit() -> None:
    scope = svc.create_scope(
        _factory(), workspace_id=1, name="rt-kernel", description=None, principal=NON_ADMIN
    )
    svc.put_secret(_factory(), scope_id=scope.id, key="token", value="k3rn3l", principal=None)

    assert secret_runtime.get_secret("rt-kernel", "token") == "k3rn3l"

    with _factory()() as session:
        row = session.scalars(
            select(AuditLog)
            .where(AuditLog.action == "secret.accessed")
            .order_by(AuditLog.id.desc())
        ).first()
        assert row is not None
        assert row.target == "secret_scope:rt-kernel"
        assert "kernel" in (row.detail or "")
        assert row.user_email == NON_ADMIN


def test_get_secret_hides_ungranted_scope() -> None:
    scope = svc.create_scope(
        _factory(), workspace_id=1, name="rt-hidden", description=None, principal=None
    )
    svc.put_secret(_factory(), scope_id=scope.id, key="k", value="v", principal=None)
    with pytest.raises(LookupError, match="not found"):
        secret_runtime.get_secret("rt-hidden", "k")


def test_get_secret_missing_key_raises() -> None:
    svc.create_scope(
        _factory(), workspace_id=1, name="rt-nokey", description=None, principal=NON_ADMIN
    )
    with pytest.raises(LookupError, match="rt-nokey"):
        secret_runtime.get_secret("rt-nokey", "absent")


def test_get_secret_requires_principal(monkeypatch) -> None:
    monkeypatch.delenv("POINTLESSQL_PRINCIPAL")
    with pytest.raises(PermissionError):
        secret_runtime.get_secret("any", "thing")


def test_resolve_references_in_tree_walks_nested() -> None:
    scope = svc.create_scope(
        _factory(), workspace_id=1, name="rt-tree", description=None, principal=None
    )
    svc.put_secret(_factory(), scope_id=scope.id, key="pw", value="deep", principal=None)
    tree = {
        "url": "{{secrets/rt-tree/pw}}",
        "nested": {"items": ["plain", "{{secrets/rt-tree/pw}}"], "port": 5432},
    }
    out = svc.resolve_references_in_tree(_factory(), workspace_id=1, data=tree)
    assert out == {"url": "deep", "nested": {"items": ["plain", "deep"], "port": 5432}}
