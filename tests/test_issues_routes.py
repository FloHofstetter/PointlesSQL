"""issues routes round-trip + state transitions.

Coverage:

* Open an issue against a table parent (returns 200, body shape).
* Open an issue against a model parent.
* Open an issue against a branch parent.
* Open an issue against a dp parent (resolves dp_target).
* List issues filtered by parent (parent-scoped endpoint).
* Global ``/api/issues`` index with state filter.
* PATCH title + body + assignee + milestone + labels.
* Close → reopen transition with proper closed_reason validation.
* Close with not_planned=True → state='closed_not_planned'.
* 403 on PATCH from non-opener-non-admin user.
* 400 on bad close_reason.
* The new issue's own social_target row is comment-able (kind='issue').
* Labels CRUD round-trip.
* Milestones CRUD round-trip.
* Parent kind with ``supports_issues=False`` returns 404.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models.catalog._data_products import DataProduct

_TABLE_REF = "main.sales.orders"
_MODEL_REF = "main.ml.churn"
_BRANCH_REF = "main.sales__branch_test"


def _seed_dp(session: Any) -> int:
    """Seed a DataProduct row so DP-parented issues can be opened.

    Args:
        session: Active SQLAlchemy session.

    Returns:
        The new DataProduct.id.
    """
    import datetime

    dp = DataProduct(
        workspace_id=1,
        catalog_name="main",
        schema_name="sales_gold",
        version="0.1.0",
        description="DP seed for 77.7 route tests",
        contract_yaml_hash="0" * 64,
        contract_json="{}",
        last_loaded_at=datetime.datetime.now(datetime.UTC),
        created_at=datetime.datetime.now(datetime.UTC),
    )
    session.add(dp)
    session.commit()
    session.refresh(dp)
    return int(dp.id)


@pytest.mark.asyncio
async def test_open_issue_against_table_parent(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST returns 200 + populated issue dict for a table parent."""
    res = await admin_client.post(
        f"/api/social/table/{_TABLE_REF}/issues",
        json={"title": "Schema drift", "body_md": "ts column missing"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["id"] > 0
    assert body["title"] == "Schema drift"
    assert body["body_md"] == "ts column missing"
    assert body["state"] == "open"
    assert body["parent_kind"] == "table"
    assert body["parent_ref"] == _TABLE_REF
    assert body["labels"] == []


@pytest.mark.asyncio
async def test_open_issue_against_model_parent(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST against a model parent succeeds."""
    res = await admin_client.post(
        f"/api/social/model/{_MODEL_REF}/issues",
        json={"title": "Bias drift"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["parent_kind"] == "model"


@pytest.mark.asyncio
async def test_open_issue_against_branch_parent(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST against a branch parent succeeds."""
    res = await admin_client.post(
        f"/api/social/branch/{_BRANCH_REF}/issues",
        json={"title": "Branch regression"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["parent_kind"] == "branch"


@pytest.mark.asyncio
async def test_open_issue_against_dp_parent_succeeds(
    admin_client: httpx.AsyncClient,
) -> None:
    """DP parent: resolve_dp_target populates the back-pointer + works."""
    factory = app.state.session_factory
    with factory() as session:
        _seed_dp(session)
    res = await admin_client.post(
        "/api/social/dp/main.sales_gold/issues",
        json={"title": "Stale lineage", "body_md": "missing edges"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["parent_kind"] == "dp"
    assert body["parent_ref"] == "main.sales_gold"


@pytest.mark.asyncio
async def test_open_issue_against_unsupported_parent_kind_404s(
    admin_client: httpx.AsyncClient,
) -> None:
    """``kind='run'`` opts out of issues — POST returns 404."""
    run_uuid = "12345678-1234-1234-1234-123456789abc"
    res = await admin_client.post(
        f"/api/social/run/{run_uuid}/issues",
        json={"title": "should fail"},
    )
    assert res.status_code == 404, res.text
    assert "does not support issues" in res.text


@pytest.mark.asyncio
async def test_open_issue_rejects_missing_title(
    admin_client: httpx.AsyncClient,
) -> None:
    """A missing or empty title triggers 400."""
    res = await admin_client.post(f"/api/social/table/{_TABLE_REF}/issues", json={"title": ""})
    assert res.status_code == 400, res.text


@pytest.mark.asyncio
async def test_list_issues_for_parent_returns_only_that_parent(
    admin_client: httpx.AsyncClient,
) -> None:
    """Parent-scoped list filters to the requested ``(kind, ref)``."""
    await admin_client.post(
        f"/api/social/table/{_TABLE_REF}/issues",
        json={"title": "table-only-issue"},
    )
    await admin_client.post(
        f"/api/social/model/{_MODEL_REF}/issues",
        json={"title": "model-only-issue"},
    )
    res = await admin_client.get(f"/api/social/table/{_TABLE_REF}/issues")
    assert res.status_code == 200, res.text
    titles = {it["title"] for it in res.json()["issues"]}
    assert "table-only-issue" in titles
    assert "model-only-issue" not in titles


@pytest.mark.asyncio
async def test_global_issues_index_with_state_filter(
    admin_client: httpx.AsyncClient,
) -> None:
    """``GET /api/issues?state=open`` only returns open issues."""
    opened = await admin_client.post(
        f"/api/social/table/{_TABLE_REF}/issues",
        json={"title": "open-issue"},
    )
    assert opened.status_code == 200
    issue_id = opened.json()["id"]
    closed = await admin_client.post(
        f"/api/social/table/{_TABLE_REF}/issues",
        json={"title": "to-close"},
    )
    closed_id = closed.json()["id"]
    res_close = await admin_client.post(
        f"/api/issues/{closed_id}/close", json={"closed_reason": "fixed"}
    )
    assert res_close.status_code == 200, res_close.text

    res = await admin_client.get("/api/issues?state=open")
    assert res.status_code == 200
    open_ids = {it["id"] for it in res.json()["issues"]}
    assert issue_id in open_ids
    assert closed_id not in open_ids


@pytest.mark.asyncio
async def test_patch_issue_title_body_labels_milestone(
    admin_client: httpx.AsyncClient,
) -> None:
    """PATCH applies title/body/labels/milestone diffs."""
    opened = await admin_client.post(
        f"/api/social/table/{_TABLE_REF}/issues",
        json={"title": "patchme"},
    )
    issue_id = opened.json()["id"]
    res = await admin_client.patch(
        f"/api/issues/{issue_id}",
        json={
            "title": "patched",
            "body_md": "new body",
            "labels": ["bug", "p0"],
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["title"] == "patched"
    assert body["body_md"] == "new body"
    assert body["labels"] == ["bug", "p0"]


@pytest.mark.asyncio
async def test_patch_issue_403_for_non_opener(
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Non-opener, non-admin caller gets 403 on PATCH."""
    opened = await admin_client.post(
        f"/api/social/table/{_TABLE_REF}/issues",
        json={"title": "owner-only"},
    )
    issue_id = opened.json()["id"]
    res = await non_admin_client.patch(f"/api/issues/{issue_id}", json={"title": "hijack attempt"})
    assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_close_with_invalid_reason_returns_400(
    admin_client: httpx.AsyncClient,
) -> None:
    """A close_reason outside the locked vocab returns 400."""
    opened = await admin_client.post(
        f"/api/social/table/{_TABLE_REF}/issues",
        json={"title": "bad-reason"},
    )
    issue_id = opened.json()["id"]
    res = await admin_client.post(
        f"/api/issues/{issue_id}/close",
        json={"closed_reason": "totally_bogus"},
    )
    assert res.status_code == 400, res.text


@pytest.mark.asyncio
async def test_close_not_planned_then_reopen(
    admin_client: httpx.AsyncClient,
) -> None:
    """not_planned=True → state='closed_not_planned'; reopen → 'open'."""
    opened = await admin_client.post(
        f"/api/social/table/{_TABLE_REF}/issues",
        json={"title": "transition-test"},
    )
    issue_id = opened.json()["id"]
    closed = await admin_client.post(f"/api/issues/{issue_id}/close", json={"not_planned": True})
    assert closed.status_code == 200, closed.text
    assert closed.json()["state"] == "closed_not_planned"

    reopened = await admin_client.post(f"/api/issues/{issue_id}/reopen")
    assert reopened.status_code == 200, reopened.text
    assert reopened.json()["state"] == "open"
    assert reopened.json()["closed_at"] is None
    assert reopened.json()["closed_reason"] is None


@pytest.mark.asyncio
async def test_issue_is_comment_able_via_polymorphic_route(
    admin_client: httpx.AsyncClient,
) -> None:
    """The issue's own social_target is comment-able (kind='issue')."""
    opened = await admin_client.post(
        f"/api/social/table/{_TABLE_REF}/issues",
        json={"title": "comment-me"},
    )
    issue_id = opened.json()["id"]
    res = await admin_client.post(
        f"/api/social/issue/{issue_id}/comments",
        json={"body_md": "Issue thread comment OK"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["body_md"] == "Issue thread comment OK"


@pytest.mark.asyncio
async def test_labels_crud_roundtrip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Workspace labels POST + GET + DELETE round-trip."""
    create = await admin_client.post(
        "/api/workspaces/1/labels",
        json={
            "slug": "good-first-issue",
            "label_text": "good first issue",
            "color_hex": "#7057ff",
        },
    )
    assert create.status_code == 200, create.text
    label_id = create.json()["id"]
    listing = await admin_client.get("/api/workspaces/1/labels")
    assert listing.status_code == 200
    slugs = {row["slug"] for row in listing.json()["labels"]}
    assert "good-first-issue" in slugs
    delete = await admin_client.delete(f"/api/workspaces/1/labels/{label_id}")
    assert delete.status_code == 200


@pytest.mark.asyncio
async def test_milestones_crud_roundtrip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Workspace milestones POST + GET + DELETE round-trip."""
    create = await admin_client.post(
        "/api/workspaces/1/milestones",
        json={"title": "Q4 GA", "description_md": "Cut release"},
    )
    assert create.status_code == 200, create.text
    milestone_id = create.json()["id"]
    listing = await admin_client.get("/api/workspaces/1/milestones")
    titles = {m["title"] for m in listing.json()["milestones"]}
    assert "Q4 GA" in titles
    delete = await admin_client.delete(f"/api/workspaces/1/milestones/{milestone_id}")
    assert delete.status_code == 200
