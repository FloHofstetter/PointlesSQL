"""HTTP route tests for the editable workspace-level mesh canvas.

Covers the three thin adapters in
``pointlessql.api.mesh_canvas_routes``: load, save (which diffs the
client's edge set against the current ``upstream_product`` rows),
and validate (side-effect-free shape checks).
"""

from __future__ import annotations

import datetime

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import DataProduct, DataProductInputPort


def _seed_dp(*, schema_name: str, catalog: str = "main") -> int:
    now = datetime.datetime.now(datetime.UTC)
    factory = app.state.session_factory
    with factory.begin() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema_name,
            description="",
            version="1.0.0",
            sla_minutes=60,
            steward_user_id=None,
            contract_yaml_hash=f"hash_{schema_name}",
            contract_json="{}",
            last_loaded_at=now,
            created_at=now,
        )
        session.add(dp)
        session.flush()
        return dp.id


@pytest.mark.asyncio
async def test_mesh_canvas_load_empty(admin_client: httpx.AsyncClient) -> None:
    res = await admin_client.get("/api/mesh/canvas")
    assert res.status_code == 200, res.text
    body = res.json()
    assert "document" in body
    assert "edges" in body["document"]
    assert "nodes" in body["document"]


@pytest.mark.asyncio
async def test_mesh_canvas_save_creates_input_port(
    admin_client: httpx.AsyncClient,
) -> None:
    upstream = _seed_dp(schema_name="mesh_upstream_a")
    downstream = _seed_dp(schema_name="mesh_downstream_a")
    res = await admin_client.post(
        "/api/mesh/canvas",
        json={
            "document": {
                "nodes": [
                    {"dp_id": upstream, "ref": "main.mesh_upstream_a"},
                    {"dp_id": downstream, "ref": "main.mesh_downstream_a"},
                ],
                "edges": [
                    {
                        "id": "mesh_new_seed_a",
                        "source_dp_id": upstream,
                        "target_dp_id": downstream,
                    }
                ],
            }
        },
    )
    assert res.status_code == 200, res.text
    summary = res.json()["summary"]
    assert summary["added"] == 1
    factory = app.state.session_factory
    with factory() as session:
        port = session.execute(
            select(DataProductInputPort).where(
                DataProductInputPort.data_product_id == downstream,
                DataProductInputPort.kind == "upstream_product",
            )
        ).scalar_one()
        assert port.source_ref == "main.mesh_upstream_a"


@pytest.mark.asyncio
async def test_mesh_canvas_save_removes_stale_port(
    admin_client: httpx.AsyncClient,
) -> None:
    upstream = _seed_dp(schema_name="mesh_upstream_b")
    downstream = _seed_dp(schema_name="mesh_downstream_b")
    # Seed: create a binding first via the same save endpoint.
    await admin_client.post(
        "/api/mesh/canvas",
        json={
            "document": {
                "nodes": [
                    {"dp_id": upstream, "ref": "main.mesh_upstream_b"},
                    {"dp_id": downstream, "ref": "main.mesh_downstream_b"},
                ],
                "edges": [
                    {
                        "id": "mesh_new_seed_b",
                        "source_dp_id": upstream,
                        "target_dp_id": downstream,
                    }
                ],
            }
        },
    )
    # Now save again with NO edges → diff removes the prior port.
    res = await admin_client.post(
        "/api/mesh/canvas",
        json={
            "document": {
                "nodes": [
                    {"dp_id": upstream, "ref": "main.mesh_upstream_b"},
                    {"dp_id": downstream, "ref": "main.mesh_downstream_b"},
                ],
                "edges": [],
            }
        },
    )
    assert res.status_code == 200, res.text
    summary = res.json()["summary"]
    assert summary["removed"] >= 1
    factory = app.state.session_factory
    with factory() as session:
        remaining = (
            session.execute(
                select(DataProductInputPort).where(
                    DataProductInputPort.data_product_id == downstream,
                )
            )
            .scalars()
            .all()
        )
        assert not any(p.kind == "upstream_product" for p in remaining)


@pytest.mark.asyncio
async def test_mesh_canvas_validate_self_loop(
    admin_client: httpx.AsyncClient,
) -> None:
    dp = _seed_dp(schema_name="mesh_selfloop")
    res = await admin_client.post(
        "/api/mesh/canvas/validate",
        json={
            "document": {
                "nodes": [{"dp_id": dp, "ref": "main.mesh_selfloop"}],
                "edges": [
                    {
                        "id": "mesh_new_loop",
                        "source_dp_id": dp,
                        "target_dp_id": dp,
                    }
                ],
            }
        },
    )
    assert res.status_code == 200, res.text
    issues = res.json()["issues"]
    assert any("self-loop" in msg for msg in issues)


# ---------------------------------------------------------------------------
# Phase 162 — cross-workspace edges
# ---------------------------------------------------------------------------


def _seed_workspace(slug: str) -> int:
    """Create a workspace if it doesn't already exist; return its id."""
    from pointlessql.models import Workspace

    now = datetime.datetime.now(datetime.UTC)
    factory = app.state.session_factory
    with factory.begin() as session:
        existing = session.scalar(select(Workspace).where(Workspace.slug == slug))
        if existing is not None:
            return existing.id
        ws = Workspace(
            slug=slug,
            name=f"Test Workspace {slug}",
            created_at=now,
        )
        session.add(ws)
        session.flush()
        return ws.id


def _seed_dp_in_workspace(*, workspace_id: int, schema_name: str, catalog: str = "main") -> int:
    now = datetime.datetime.now(datetime.UTC)
    factory = app.state.session_factory
    with factory.begin() as session:
        dp = DataProduct(
            workspace_id=workspace_id,
            catalog_name=catalog,
            schema_name=schema_name,
            description="",
            version="1.0.0",
            sla_minutes=60,
            steward_user_id=None,
            contract_yaml_hash=f"hash_{schema_name}",
            contract_json="{}",
            last_loaded_at=now,
            created_at=now,
        )
        session.add(dp)
        session.flush()
        return dp.id


@pytest.mark.asyncio
async def test_mesh_canvas_creates_cross_workspace_edge(
    admin_client: httpx.AsyncClient,
) -> None:
    target_dp = _seed_dp(schema_name="mesh_xws_target")
    foreign_ws_id = _seed_workspace("marketing")
    upstream_dp = _seed_dp_in_workspace(workspace_id=foreign_ws_id, schema_name="foreign_src")
    res = await admin_client.post(
        "/api/mesh/canvas",
        json={
            "document": {
                "nodes": [
                    {"dp_id": target_dp, "ref": "main.mesh_xws_target"},
                    {
                        "dp_id": upstream_dp,
                        "ref": "main.foreign_src",
                        "workspace_slug": "marketing",
                    },
                ],
                "edges": [
                    {
                        "id": "mesh_new_xws",
                        "source_dp_id": upstream_dp,
                        "target_dp_id": target_dp,
                        "source_workspace_slug": "marketing",
                    }
                ],
            }
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["summary"]["added"] == 1
    factory = app.state.session_factory
    with factory() as session:
        ports = list(
            session.scalars(
                select(DataProductInputPort).where(
                    DataProductInputPort.data_product_id == target_dp,
                )
            )
        )
        xws_ports = [p for p in ports if p.source_workspace_id == foreign_ws_id]
        assert len(xws_ports) == 1


@pytest.mark.asyncio
async def test_mesh_canvas_picker_lists_cross_workspace_dps(
    admin_client: httpx.AsyncClient,
) -> None:
    foreign_ws_id = _seed_workspace("ops")
    _seed_dp_in_workspace(workspace_id=foreign_ws_id, schema_name="ops_users")
    res = await admin_client.get("/api/mesh/canvas/picker/ops")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["workspace_slug"] == "ops"
    refs = {entry["ref"] for entry in body["data_products"]}
    assert "main.ops_users" in refs


@pytest.mark.asyncio
async def test_mesh_canvas_picker_unknown_slug_404(
    admin_client: httpx.AsyncClient,
) -> None:
    res = await admin_client.get("/api/mesh/canvas/picker/no_such_workspace_xyz")
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_mesh_canvas_picker_non_admin_forbidden(
    non_admin_client: httpx.AsyncClient,
) -> None:
    _seed_workspace("sales")
    res = await non_admin_client.get("/api/mesh/canvas/picker/sales")
    assert res.status_code == 403, res.text


@pytest.mark.asyncio
async def test_mesh_canvas_existing_legacy_edges_unchanged(
    admin_client: httpx.AsyncClient,
) -> None:
    """Loading the mesh canvas after the alembic migration must round-trip clean."""
    upstream = _seed_dp(schema_name="mesh_legacy_up")
    target = _seed_dp(schema_name="mesh_legacy_dn")
    save_res = await admin_client.post(
        "/api/mesh/canvas",
        json={
            "document": {
                "nodes": [
                    {"dp_id": upstream, "ref": "main.mesh_legacy_up"},
                    {"dp_id": target, "ref": "main.mesh_legacy_dn"},
                ],
                "edges": [
                    {
                        "id": "mesh_legacy_new",
                        "source_dp_id": upstream,
                        "target_dp_id": target,
                    }
                ],
            }
        },
    )
    assert save_res.status_code == 200, save_res.text
    assert save_res.json()["summary"]["added"] == 1
    load_res = await admin_client.get("/api/mesh/canvas")
    edges = load_res.json()["document"]["edges"]
    legacy_edges = [e for e in edges if e["target_dp_id"] == target]
    assert legacy_edges
    assert legacy_edges[0]["source_workspace_slug"] is None
