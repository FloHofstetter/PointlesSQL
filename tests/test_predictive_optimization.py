"""Tests for predictive-optimization maintenance policies."""

from __future__ import annotations

import datetime
import uuid

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.exceptions import ValidationError
from pointlessql.models import Workspace
from pointlessql.services import predictive_optimization as po


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(slug=f"po-{uuid.uuid4().hex[:10]}", name="PO test", created_at=now)
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def test_set_validates_scope_depth() -> None:
    ws = _fresh_workspace()
    with pytest.raises(ValidationError, match="scope_type"):
        po.set_policy(_factory(), workspace_id=ws, scope_type="nope", scope_value="main")
    with pytest.raises(ValidationError, match="dotted part"):
        po.set_policy(_factory(), workspace_id=ws, scope_type="schema", scope_value="main")
    with pytest.raises(ValidationError, match="required"):
        po.set_policy(_factory(), workspace_id=ws, scope_type="catalog", scope_value="")


def test_set_is_upsert_and_lists() -> None:
    ws = _fresh_workspace()
    po.set_policy(
        _factory(), workspace_id=ws, scope_type="catalog", scope_value="main", vacuum=False
    )
    # Same scope again updates rather than duplicating.
    updated = po.set_policy(
        _factory(), workspace_id=ws, scope_type="catalog", scope_value="main", vacuum=True
    )
    assert updated["vacuum"] is True
    listed = po.list_policies(_factory(), workspace_id=ws)
    assert len(listed) == 1
    assert listed[0]["scope_value"] == "main"


def test_effective_resolves_most_specific_first() -> None:
    ws = _fresh_workspace()
    po.set_policy(
        _factory(), workspace_id=ws, scope_type="catalog", scope_value="main", optimize=True
    )
    po.set_policy(
        _factory(), workspace_id=ws, scope_type="schema", scope_value="main.sales", optimize=False
    )

    # A table under main.sales inherits the schema policy (beats catalog).
    eff = po.effective_policy(_factory(), workspace_id=ws, full_name="main.sales.orders")
    assert eff["matched_scope"] == "schema:main.sales"
    assert eff["optimize"] is False

    # A table in another schema falls back to the catalog policy.
    eff2 = po.effective_policy(_factory(), workspace_id=ws, full_name="main.ops.events")
    assert eff2["matched_scope"] == "catalog:main"
    assert eff2["optimize"] is True


def test_effective_default_when_no_policy() -> None:
    ws = _fresh_workspace()
    eff = po.effective_policy(_factory(), workspace_id=ws, full_name="other.x.y")
    assert eff["source"] == "default"
    assert eff["enabled"] is False
    assert eff["matched_scope"] is None


def test_table_policy_wins_and_delete() -> None:
    ws = _fresh_workspace()
    po.set_policy(_factory(), workspace_id=ws, scope_type="catalog", scope_value="c", enabled=True)
    tbl = po.set_policy(
        _factory(), workspace_id=ws, scope_type="table", scope_value="c.s.t", enabled=False
    )
    eff = po.effective_policy(_factory(), workspace_id=ws, full_name="c.s.t")
    assert eff["matched_scope"] == "table:c.s.t"
    assert eff["enabled"] is False
    assert po.delete_policy(_factory(), policy_id=tbl["id"], workspace_id=ws) is True
    assert po.delete_policy(_factory(), policy_id=tbl["id"], workspace_id=ws) is False


def test_delete_rejects_foreign_workspace() -> None:
    owner = _fresh_workspace()
    other = _fresh_workspace()
    policy = po.set_policy(_factory(), workspace_id=owner, scope_type="catalog", scope_value="keep")
    # Another workspace cannot delete the policy by its id.
    assert po.delete_policy(_factory(), policy_id=policy["id"], workspace_id=other) is False
    assert len(po.list_policies(_factory(), workspace_id=owner)) == 1
    assert po.delete_policy(_factory(), policy_id=policy["id"], workspace_id=owner) is True


def test_effective_policy_is_case_insensitive() -> None:
    # Unity Catalog names are case-insensitive: a policy set on a
    # mixed-case scope must resolve for a query in any case, and the
    # stored scope value is canonicalised to lowercase.
    ws = _fresh_workspace()
    created = po.set_policy(
        _factory(), workspace_id=ws, scope_type="schema", scope_value="Main.Sales", optimize=False
    )
    assert created["scope_value"] == "main.sales"

    eff = po.effective_policy(_factory(), workspace_id=ws, full_name="MAIN.sales.Orders")
    assert eff["matched_scope"] == "schema:main.sales"
    assert eff["optimize"] is False

    # A second write at a different case updates the same row (upsert),
    # rather than creating a case-variant duplicate.
    po.set_policy(
        _factory(), workspace_id=ws, scope_type="schema", scope_value="MAIN.SALES", optimize=True
    )
    listed = po.list_policies(_factory(), workspace_id=ws)
    assert len(listed) == 1
    assert listed[0]["optimize"] is True


@pytest.mark.asyncio
async def test_route_set_list_resolve(admin_client: httpx.AsyncClient) -> None:
    scope = f"cat{uuid.uuid4().hex[:8]}"
    created = await admin_client.post(
        "/api/admin/optimization",
        json={"scope_type": "catalog", "scope_value": scope, "vacuum": False},
    )
    assert created.status_code == 200, created.text
    pid = created.json()["policy"]["id"]

    listed = await admin_client.get("/api/admin/optimization")
    assert any(p["scope_value"] == scope for p in listed.json()["policies"])

    resolved = await admin_client.get(f"/api/admin/optimization/effective?table={scope}.s.t")
    assert resolved.json()["matched_scope"] == f"catalog:{scope}"

    deleted = await admin_client.delete(f"/api/admin/optimization/{pid}")
    assert deleted.json()["deleted"] is True


@pytest.mark.asyncio
async def test_route_page_renders(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/admin/optimization")
    assert resp.status_code == 200, resp.text
    assert "Predictive optimization" in resp.text


@pytest.mark.asyncio
async def test_route_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    resp = await non_admin_client.get("/api/admin/optimization")
    assert resp.status_code in {401, 403}
