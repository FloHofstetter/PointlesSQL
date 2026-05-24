"""branch promote-gate.

Coverage matrix for ``POST /api/branches/{fqn}/promote``:

* Gate OFF (default): promote proceeds without an endorsement
  check.
* Gate ON, no endorsement: returns 412.
* Gate ON, self-applied endorsement only: returns 412 (locked
  behaviour — endorsements must be peer-reviewed).
* Gate ON, peer-applied endorsement: promote proceeds.

The actual ``promote_branch_schema`` call is monkeypatched to a
dummy that returns a no-op success payload so the test does not
need a real soyuz-catalog backend.  The HTTP-boundary gate is
the production-shape test surface; promote-internals are
covered by the dedicated PQL branch tests.
"""

from __future__ import annotations

import datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api import branches_routes
from pointlessql.api.main import app
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.workspace._core import Workspace
from pointlessql.services.social._target_resolver import (
    get_or_create_target,
)

_BRANCH_FQN = "main.sales_gold__branch_77_3_test"


@pytest.fixture(autouse=True)
def stub_promote(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace ``promote_branch_schema`` + soyuz client with a no-op."""

    def _ok_promote(**_kwargs: Any) -> dict[str, Any]:
        return {"promoted": True, "branch_fqn": _BRANCH_FQN}

    monkeypatch.setattr(
        branches_routes, "promote_branch_schema", _ok_promote
    )

    def _stub_client(request: Any) -> tuple[Any, Any]:
        del request
        return (object(), object())

    monkeypatch.setattr(
        branches_routes, "_make_settings_client", _stub_client
    )


@pytest.fixture
def reset_gate() -> None:
    """Ensure ``branch_promote_requires_endorsement`` is OFF on each entry."""
    factory = app.state.session_factory
    with factory() as session:
        workspace = session.get(Workspace, 1)
        if workspace is not None:
            workspace.branch_promote_requires_endorsement = False
            session.commit()


def _enable_gate() -> None:
    factory = app.state.session_factory
    with factory() as session:
        workspace = session.get(Workspace, 1)
        assert workspace is not None
        workspace.branch_promote_requires_endorsement = True
        session.commit()


def _apply_branch_endorsement(applied_by_user_id: int) -> None:
    """Apply an active branch-approved-for-promotion endorsement."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="branch",
            ref=_BRANCH_FQN,
        )
        session.add(
            DataProductEndorsement(
                workspace_id=1,
                data_product_id=None,
                social_target_id=int(anchor.id),
                endorsement_type="branch-approved-for-promotion",
                applied_by_user_id=applied_by_user_id,
                applied_at=now,
                note_md="",
            )
        )
        session.commit()


def _admin_user_id() -> int:
    from pointlessql.models.auth import User

    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(
                select(User.id).where(User.email == "test@test.com")
            ).scalar_one()
        )


def _peer_user_id() -> int:
    """Return a second user id distinct from the admin."""
    from pointlessql.models.auth import User

    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(User.id)
            .where(User.email != "test@test.com")
            .order_by(User.id)
            .limit(1)
        ).scalar_one_or_none()
        if row is not None:
            return int(row)
        new_user = User(
            email="peer@test.com",
            display_name="Peer Reviewer",
            password_hash="x",
            is_admin=False,
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        return int(new_user.id)


@pytest.mark.asyncio
async def test_promote_passes_when_gate_off(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """Default workspace state: no gate, promote succeeds."""
    del reset_gate
    res = await admin_client.post(f"/api/branches/{_BRANCH_FQN}/promote")
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True


@pytest.mark.asyncio
async def test_promote_blocked_when_gate_on_and_no_endorsement(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """Gate ON + no endorsement: 412 Precondition Failed."""
    del reset_gate
    _enable_gate()
    res = await admin_client.post(f"/api/branches/{_BRANCH_FQN}/promote")
    assert res.status_code == 412, res.text
    assert "endorsement" in res.text.lower()


@pytest.mark.asyncio
async def test_promote_blocked_when_only_self_endorsed(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """Gate ON + self-endorsement: still 412 (peers required)."""
    del reset_gate
    _enable_gate()
    _apply_branch_endorsement(_admin_user_id())
    res = await admin_client.post(f"/api/branches/{_BRANCH_FQN}/promote")
    assert res.status_code == 412, res.text


@pytest.mark.asyncio
async def test_promote_passes_when_peer_endorsed(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """Gate ON + peer-applied endorsement: 200 OK."""
    del reset_gate
    _enable_gate()
    _apply_branch_endorsement(_peer_user_id())
    res = await admin_client.post(f"/api/branches/{_BRANCH_FQN}/promote")
    assert res.status_code == 200, res.text
    assert res.json()["ok"] is True
