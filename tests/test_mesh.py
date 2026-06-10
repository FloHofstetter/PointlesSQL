"""Mesh plane — emergent graph, polysemic identity, joins, PIT, health.

Covers the data-mesh δ interoperability half: the emergent graph built
from declared upstream input ports, the mesh-entity registry + column
bindings, the shared-entity join helper, the point-in-time read
resolver, the SLO-health rollup, and the entity/binding API gates.
"""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProduct, DataProductInputPort, DataProductStatistics
from pointlessql.services import mesh as mesh_service
from pointlessql.services import slo as slo_service


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str, *, tables=None) -> int:
    now = datetime.datetime.now(datetime.UTC)
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": tables or [],
    }
    with _factory()() as session:
        row = DataProduct(
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
            steward_user_id=None,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=now,
            created_at=now,
        )
        session.add(row)
        session.commit()
        return row.id


def _add_input_port(dp_id: int, name: str, source_ref: str) -> None:
    with _factory()() as session:
        session.add(
            DataProductInputPort(
                data_product_id=dp_id,
                name=name,
                kind="upstream_product",
                source_ref=source_ref,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()


# --------------------------------------------------------------------------
# emergent graph (G5)
# --------------------------------------------------------------------------


def test_graph_builds_edges_from_declared_upstreams() -> None:
    _seed_dp("mesh", "a")
    b_id = _seed_dp("mesh", "b")
    _add_input_port(b_id, "from_a", "mesh.a")
    graph = mesh_service.build_mesh_graph(_factory(), workspace_id=1)
    refs = {n["ref"] for n in graph["nodes"]}
    assert {"mesh.a", "mesh.b"} <= refs
    edge = [e for e in graph["edges"] if e["source"] == "mesh.a" and e["target"] == "mesh.b"]
    assert len(edge) == 1


def test_graph_ignores_dangling_source_ref() -> None:
    c_id = _seed_dp("mesh", "c")
    _add_input_port(c_id, "ghost", "mesh.does_not_exist")
    graph = mesh_service.build_mesh_graph(_factory(), workspace_id=1)
    assert not any(e["target"] == "mesh.c" for e in graph["edges"])


def test_local_mesh_neighbourhood_hop_limit() -> None:
    _seed_dp("hop", "a")
    b = _seed_dp("hop", "b")
    c = _seed_dp("hop", "c")
    _add_input_port(b, "from_a", "hop.a")
    _add_input_port(c, "from_b", "hop.b")
    local = mesh_service.build_local_mesh(_factory(), workspace_id=1, data_product_id=b, hops=1)
    refs = {n["ref"] for n in local["nodes"]}
    assert refs == {"hop.a", "hop.b", "hop.c"}
    assert local["center"] == "hop.b"


# --------------------------------------------------------------------------
# polysemic identity (F3)
# --------------------------------------------------------------------------


def test_entity_crud_and_schema_index() -> None:
    dp_id = _seed_dp("ent", "p")
    entity = mesh_service.create_entity(_factory(), workspace_id=1, name="Customer")
    assert entity.slug == "customer"
    mesh_service.add_binding(
        _factory(),
        mesh_entity_id=entity.id,
        data_product_id=dp_id,
        catalog="ent",
        schema="p",
        table="orders",
        column="customer_id",
    )
    index = mesh_service.entities_for_schema(_factory(), catalog="ent", schema="p")
    assert index[("orders", "customer_id")] == ["customer"]
    assert mesh_service.delete_entity(_factory(), workspace_id=1, entity_id=entity.id) is True
    # CASCADE removed the binding.
    assert mesh_service.entities_for_schema(_factory(), catalog="ent", schema="p") == {}


def test_create_entity_idempotent_on_slug() -> None:
    e1 = mesh_service.create_entity(_factory(), workspace_id=1, name="Order")
    e2 = mesh_service.create_entity(_factory(), workspace_id=1, name="Order")
    assert e1.id == e2.id


# --------------------------------------------------------------------------
# join helper (D5)
# --------------------------------------------------------------------------


def test_joinable_columns_across_products_sharing_an_entity() -> None:
    left = _seed_dp("join", "left")
    right = _seed_dp("join", "right")
    entity = mesh_service.create_entity(_factory(), workspace_id=1, name="Party")
    mesh_service.add_binding(
        _factory(),
        mesh_entity_id=entity.id,
        data_product_id=left,
        catalog="join",
        schema="left",
        table="orders",
        column="cust_id",
    )
    mesh_service.add_binding(
        _factory(),
        mesh_entity_id=entity.id,
        data_product_id=right,
        catalog="join",
        schema="right",
        table="customers",
        column="id",
    )
    suggestions = mesh_service.joinable_columns(
        _factory(), left_product_id=left, right_product_id=right
    )
    assert len(suggestions) == 1
    assert suggestions[0]["entity"]["slug"] == "party"
    assert "JOIN" in suggestions[0]["join_sql"]


def test_joinable_empty_when_no_shared_entity() -> None:
    left = _seed_dp("join2", "left")
    right = _seed_dp("join2", "right")
    assert (
        mesh_service.joinable_columns(_factory(), left_product_id=left, right_product_id=right)
        == []
    )


# --------------------------------------------------------------------------
# point-in-time (F2)
# --------------------------------------------------------------------------


class _FakeUC:
    """Minimal async UC stub returning no tables (no Delta IO in tests)."""

    async def list_tables(self, catalog: str, schema: str):
        del catalog, schema
        return []


async def test_resolve_as_of_rejects_naive_datetime() -> None:
    dp_id = _seed_dp("pit", "p", tables=[{"name": "t", "columns": []}])
    with pytest.raises(ValueError, match="timezone-aware"):
        await mesh_service.resolve_as_of(
            _factory(),
            _FakeUC(),  # type: ignore[arg-type]
            workspace_id=1,
            product_ids=[dp_id],
            when=datetime.datetime(2026, 1, 1),  # noqa: DTZ001 — naive on purpose
        )


async def test_resolve_as_of_returns_manifest() -> None:
    dp_id = _seed_dp("pit", "q", tables=[{"name": "t", "columns": []}])
    manifest = await mesh_service.resolve_as_of(
        _factory(),
        _FakeUC(),  # type: ignore[arg-type]
        workspace_id=1,
        product_ids=[dp_id],
        when=datetime.datetime.now(datetime.UTC),
    )
    assert "pit.q" in manifest["products"]
    # No UC table resolves → declared table maps to a null version.
    assert manifest["products"]["pit.q"]["tables"]["t"]["as_of_version"] is None


# --------------------------------------------------------------------------
# health rollup (G2)
# --------------------------------------------------------------------------


def test_mesh_health_marks_failing_product_red() -> None:
    dp_id = _seed_dp("health", "p")
    with _factory()() as session:
        session.add(
            DataProductStatistics(
                data_product_id=dp_id,
                table_name="t",
                delta_log_version=1,
                row_count=5,
                shape_json="{}",
                profile_kind="light",
                freshness_lag_minutes=None,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    slo_service.declare_slo(
        _factory(), data_product_id=dp_id, slo_kind="volume", target_value=1000.0, table_name="t"
    )
    health = mesh_service.mesh_health(_factory(), workspace_id=1)
    entry = next(p for p in health["products"] if p["ref"] == "health.p")
    assert entry["band"] == "red"
    assert entry["failed"] >= 1


# --------------------------------------------------------------------------
# API gates
# --------------------------------------------------------------------------


async def test_entity_registry_create_requires_admin() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.post("/api/admin/mesh-entities", json={"name": "X"})
    assert res.status_code in (401, 403)


async def test_entity_binding_requires_steward_or_admin() -> None:
    _seed_dp("bind", "gate")
    mesh_service.create_entity(_factory(), workspace_id=1, name="Thing")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/bind/gate/entities",
            json={"entity_slug": "thing", "table": "t", "column": "c"},
        )
    assert res.status_code in (401, 403)


async def test_mesh_graph_and_health_via_api() -> None:
    _seed_dp("mapi", "a")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        graph = await client.get("/api/mesh/graph")
        assert graph.status_code == 200, graph.text
        health = await client.get("/api/mesh/health")
        assert health.status_code == 200, health.text
        assert "summary" in health.json()


async def test_mesh_html_pages_render() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        for path in ("/mesh", "/mesh/health", "/mesh/entities", "/admin/mesh-entities"):
            res = await client.get(path)
            assert res.status_code == 200, f"{path}: {res.text[:200]}"


async def test_product_detail_renders_interop_and_slo_panels() -> None:
    _seed_dp("render", "p")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/data-products/render/p")
    assert res.status_code == 200, res.text[:300]
    assert "dataProductInterop(" in res.text
    assert "dataProductSloPanel(" in res.text
