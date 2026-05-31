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
