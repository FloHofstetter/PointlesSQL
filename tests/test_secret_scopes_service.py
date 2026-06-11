"""Unit tests for the secret-scopes service (crypto, ACL ladder, refs)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.secret_scopes import SecretScopeSecret
from pointlessql.services import secret_scopes as svc


def _factory():
    return app.state.session_factory


# ---------------------------------------------------------------------------
# name validation + permission ladder
# ---------------------------------------------------------------------------


def test_validate_name_accepts_charset() -> None:
    assert svc.validate_name("  prod.api-keys_v2  ", what="scope name") == "prod.api-keys_v2"


@pytest.mark.parametrize("bad", ["", "  ", "with space", "a/b", "ü", "x" * 129])
def test_validate_name_rejects(bad: str) -> None:
    with pytest.raises(ValueError, match="scope name"):
        svc.validate_name(bad, what="scope name")


def test_permission_ladder() -> None:
    assert svc.permission_satisfies("MANAGE", "READ")
    assert svc.permission_satisfies("MANAGE", "MANAGE")
    assert svc.permission_satisfies("WRITE", "READ")
    assert not svc.permission_satisfies("READ", "WRITE")
    assert not svc.permission_satisfies("WRITE", "MANAGE")
    assert not svc.permission_satisfies(None, "READ")


# ---------------------------------------------------------------------------
# scope CRUD + creator grant
# ---------------------------------------------------------------------------


def test_create_scope_grants_creator_manage() -> None:
    scope = svc.create_scope(
        _factory(),
        workspace_id=1,
        name="svc-create-a",
        description="unit",
        principal="owner@test.com",
    )
    assert scope.id is not None
    assert (
        svc.resolve_permission(
            _factory(), scope_id=scope.id, principal="owner@test.com", is_admin=False
        )
        == "MANAGE"
    )
    assert (
        svc.resolve_permission(
            _factory(), scope_id=scope.id, principal="other@test.com", is_admin=False
        )
        is None
    )


def test_create_scope_rejects_duplicate() -> None:
    svc.create_scope(_factory(), workspace_id=1, name="svc-dup", description=None, principal=None)
    with pytest.raises(ValueError, match="already exists"):
        svc.create_scope(
            _factory(), workspace_id=1, name="svc-dup", description=None, principal=None
        )


def test_wildcard_grant_makes_scope_visible() -> None:
    scope = svc.create_scope(
        _factory(), workspace_id=1, name="svc-wild", description=None, principal=None
    )
    svc.put_acl(_factory(), scope_id=scope.id, principal="*", permission="READ")
    pairs = svc.list_scopes(_factory(), workspace_id=1, principal="anyone@test.com", is_admin=False)
    assert ("svc-wild", "READ") in [(s.name, p) for s, p in pairs]


# ---------------------------------------------------------------------------
# secrets — encryption at rest, value round-trip, caps
# ---------------------------------------------------------------------------


def test_put_secret_encrypts_at_rest_and_roundtrips() -> None:
    scope = svc.create_scope(
        _factory(), workspace_id=1, name="svc-crypto", description=None, principal=None
    )
    svc.put_secret(
        _factory(), scope_id=scope.id, key="token", value="hunter2", principal="o@test.com"
    )
    with _factory()() as session:
        row = session.scalar(
            select(SecretScopeSecret).where(SecretScopeSecret.scope_id == scope.id)
        )
        assert row is not None
        assert row.encrypted_value != "hunter2"
        assert "hunter2" not in row.encrypted_value
    assert svc.get_secret_value(_factory(), scope_id=scope.id, key="token") == "hunter2"


def test_put_secret_overwrite_updates_metadata() -> None:
    scope = svc.create_scope(
        _factory(), workspace_id=1, name="svc-overwrite", description=None, principal=None
    )
    svc.put_secret(_factory(), scope_id=scope.id, key="k", value="v1", principal="a@test.com")
    row = svc.put_secret(_factory(), scope_id=scope.id, key="k", value="v2", principal="b@test.com")
    assert row.created_by == "a@test.com"
    assert row.updated_by == "b@test.com"
    assert svc.get_secret_value(_factory(), scope_id=scope.id, key="k") == "v2"
    assert len(svc.list_secret_keys(_factory(), scope_id=scope.id)) == 1


def test_put_secret_rejects_oversized_value() -> None:
    scope = svc.create_scope(
        _factory(), workspace_id=1, name="svc-cap", description=None, principal=None
    )
    with pytest.raises(ValueError, match="exceeds"):
        svc.put_secret(
            _factory(),
            scope_id=scope.id,
            key="big",
            value="x" * (svc.MAX_SECRET_BYTES + 1),
            principal=None,
        )


def test_delete_scope_cascades() -> None:
    scope = svc.create_scope(
        _factory(), workspace_id=1, name="svc-cascade", description=None, principal="o@t.de"
    )
    svc.put_secret(_factory(), scope_id=scope.id, key="k", value="v", principal=None)
    assert svc.delete_scope(_factory(), scope_id=scope.id)
    with _factory()() as session:
        left = session.scalar(
            select(SecretScopeSecret).where(SecretScopeSecret.scope_id == scope.id)
        )
        assert left is None


# ---------------------------------------------------------------------------
# {{secrets/scope/key}} reference resolution
# ---------------------------------------------------------------------------


def test_resolve_secret_references_substitutes() -> None:
    scope = svc.create_scope(
        _factory(), workspace_id=1, name="svc-refs", description=None, principal=None
    )
    svc.put_secret(_factory(), scope_id=scope.id, key="pw", value="s3cret", principal=None)
    svc.put_secret(_factory(), scope_id=scope.id, key="user", value="flo", principal=None)
    out = svc.resolve_secret_references(
        _factory(),
        workspace_id=1,
        text="postgres://{{secrets/svc-refs/user}}:{{ secrets/svc-refs/pw }}@db/x",
    )
    assert out == "postgres://flo:s3cret@db/x"


def test_resolve_secret_references_unknown_scope_raises() -> None:
    with pytest.raises(ValueError, match="unknown secret scope"):
        svc.resolve_secret_references(_factory(), workspace_id=1, text="{{secrets/nope/pw}}")


def test_resolve_secret_references_unknown_key_raises() -> None:
    svc.create_scope(
        _factory(), workspace_id=1, name="svc-refs-miss", description=None, principal=None
    )
    with pytest.raises(ValueError, match="unknown secret key"):
        svc.resolve_secret_references(
            _factory(), workspace_id=1, text="{{secrets/svc-refs-miss/pw}}"
        )
