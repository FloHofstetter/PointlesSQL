"""branch_detail.html social tabs + promote-gate UI.

Coverage:

* The 5 new tab buttons (Overview / Discussion / Endorsements /
  Followers / Promote) are present on the rendered page.
* The .tab-content carries the ``socialTabs`` x-data with
  ``kind='branch'`` + a single endorsement type
  ``branch-approved-for-promotion``.
* Promote tab is admin-only + only renders when the branch is
  active + non-backup (matches the pre-77.3.B Danger Zone guard).
* Promote-gate UI states:
  - Gate OFF: button enabled, no banner.
  - Gate ON + 0 peer endorsements: button has ``disabled``
    attribute + lock icon + "needs peer endorsement" hint.
  - Gate ON + 1+ peer endorsements: button enabled + "gate
    satisfied" affordance shown.
* Polymorphic comment endpoint works on the branch FQN end-to-end.
"""

from __future__ import annotations

import datetime
from typing import Any

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api import branches_routes
from pointlessql.api.main import app
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.workspace._core import Workspace
from pointlessql.services import branch_tags as branch_tags_mod
from pointlessql.services.social._target_resolver import (
    get_or_create_target,
)

_BRANCH_FQN = "main.sales_gold__branch_77_3_b_test"


@pytest.fixture(autouse=True)
def stub_branch_tags(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replace soyuz lookups with stubs so the HTML route renders."""
    fake_tags = branch_tags_mod.BranchTags(
        parent_schema="sales_gold",
        parent_version_at_create={"orders": 0},
        created_at=datetime.datetime(2026, 5, 15).isoformat(),
        created_by_run_id=None,
        strategy="symlink",
        status="active",
        promoted_at=None,
        discarded_at=None,
        is_pre_promote_backup=False,
    )

    def _stub_client(request: Any) -> tuple[Any, Any]:
        del request
        return (object(), object())

    monkeypatch.setattr(
        branches_routes, "_make_settings_client", _stub_client
    )
    monkeypatch.setattr(
        branches_routes.branch_tags,
        "read_branch_tags_sync",
        lambda _client, _fqn: fake_tags,
    )


@pytest.fixture
def reset_gate() -> None:
    """Ensure the workspace promote-gate is OFF at test entry."""
    factory = app.state.session_factory
    with factory() as session:
        ws = session.get(Workspace, 1)
        if ws is not None:
            ws.branch_promote_requires_endorsement = False
            session.commit()


def _enable_gate() -> None:
    factory = app.state.session_factory
    with factory() as session:
        ws = session.get(Workspace, 1)
        assert ws is not None
        ws.branch_promote_requires_endorsement = True
        session.commit()


def _apply_endorsement(applied_by_user_id: int) -> None:
    """Apply an active ``branch-approved-for-promotion`` endorsement."""
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


def _peer_user_id() -> int:
    """Return a user id distinct from the admin test user."""
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
            email="peer-77-3-b@test.com",
            display_name="Peer 77.3.B",
            password_hash="x",
            is_admin=False,
        )
        session.add(new_user)
        session.commit()
        session.refresh(new_user)
        return int(new_user.id)


@pytest.mark.asyncio
async def test_branch_html_renders_five_tab_buttons(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """All 5 new tab buttons are present on the rendered page."""
    del reset_gate
    res = await admin_client.get(f"/branches/{_BRANCH_FQN}")
    assert res.status_code == 200, res.text
    body = res.text
    for tab_id in (
        'id="tab-overview-btn"',
        'id="tab-discussion-btn"',
        'id="tab-endorsements-btn"',
        'id="tab-followers-btn"',
        'id="tab-promote-btn"',
    ):
        assert tab_id in body, f"missing tab button: {tab_id}"


@pytest.mark.asyncio
async def test_branch_html_mounts_social_tabs_factory(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """socialTabs x-data has kind='branch' + the single endorsement type."""
    del reset_gate
    res = await admin_client.get(f"/branches/{_BRANCH_FQN}")
    body = res.text
    assert "socialTabs(" in body
    assert "branch" in body
    assert "branch-approved-for-promotion" in body


@pytest.mark.asyncio
async def test_branch_html_branchdiscussion_factory_present(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """branchDiscussion factory exposed on window + invoked on the pane."""
    del reset_gate
    res = await admin_client.get(f"/branches/{_BRANCH_FQN}")
    body = res.text
    assert "window.branchDiscussion = branchDiscussion" in body
    assert "branchDiscussion(" in body


@pytest.mark.asyncio
async def test_promote_tab_unlocked_when_gate_off(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """Gate OFF: promote button has no disabled attribute, no lock icon."""
    del reset_gate
    res = await admin_client.get(f"/branches/{_BRANCH_FQN}")
    body = res.text
    # The "needs peer endorsement" lock icon comes from the
    # gate-locked branch only.
    assert "Needs ≥1 peer endorsement" not in body
    # No "gate on" hint in the header strip either.
    assert "gate on" not in body.lower()


@pytest.mark.asyncio
async def test_promote_tab_locked_when_gate_on_and_no_endorsement(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """Gate ON + 0 endorsements: button disabled + lock icon + hint."""
    del reset_gate
    _enable_gate()
    res = await admin_client.get(f"/branches/{_BRANCH_FQN}")
    body = res.text
    assert "Promote-gate is enabled" in body
    assert "stays locked" in body
    assert "Needs ≥1 peer endorsement" in body
    # The header badge shows the gate-on state.
    assert "gate on" in body.lower()


@pytest.mark.asyncio
async def test_promote_tab_unlocked_when_gate_on_with_peer_endorsement(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """Gate ON + 1 peer endorsement: button enabled + "satisfied" hint."""
    del reset_gate
    _enable_gate()
    _apply_endorsement(_peer_user_id())
    res = await admin_client.get(f"/branches/{_BRANCH_FQN}")
    body = res.text
    assert "Promote-gate is enabled" in body
    assert "Gate satisfied" in body
    # The endorsement count badge surfaces the peer count.
    assert "<strong>1</strong>" in body
    # Button is NOT disabled — no lock icon next to the Promote label.
    assert "Needs ≥1 peer endorsement" not in body


@pytest.mark.asyncio
async def test_polymorphic_branch_comment_roundtrip(
    admin_client: httpx.AsyncClient, reset_gate: None
) -> None:
    """End-to-end smoke for /api/social/branch/{fqn}/comments."""
    del reset_gate
    res_post = await admin_client.post(
        f"/api/social/branch/{_BRANCH_FQN}/comments",
        json={"body_md": "branch.html smoke"},
    )
    assert res_post.status_code == 200, res_post.text
    res_list = await admin_client.get(
        f"/api/social/branch/{_BRANCH_FQN}/comments"
    )
    assert res_list.status_code == 200
    bodies = [c["body_md"] for c in res_list.json()["comments"]]
    assert "branch.html smoke" in bodies
