"""Quantum-ports, discovery, statistics + glossary — service + API + B7 hook.

Covers the data-mesh β layer: declared output/input ports, the
per-product semantic model, self-generated statistics (the write-time
stamping hook + read-back), the machine-readable discovery contract,
and the business glossary (admin CRUD + browse + per-column badges).
"""

from __future__ import annotations

import datetime
import json

import httpx
import pandas as pd
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import DataProduct, DataProductStatistics, User
from pointlessql.services import data_product_ports as ports_service
from pointlessql.services import data_product_semantic as semantic_service
from pointlessql.services import glossary as glossary_service
from pointlessql.services.agent_runs.operations._statistics import (
    record_statistics_after_commit,
)
from pointlessql.services.data_product_stats import light_shape, read_latest_statistics


def _factory():
    return app.state.session_factory


def _admin_user_id() -> int:
    with _factory()() as session:
        return session.scalar(select(User.id).where(User.email == "test@test.com"))


def _seed_dp(catalog: str, schema: str, *, steward_user_id: int | None = None, tables=None) -> int:
    """Insert a minimal DataProduct row with a valid contract; return its id."""
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
            steward_user_id=steward_user_id,
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


# ---------------------------------------------------------------------------
# service — ports
# ---------------------------------------------------------------------------


def test_output_port_crud_and_uniqueness() -> None:
    dp_id = _seed_dp("main", "ports_out")
    port = ports_service.create_output_port(
        _factory(), data_product_id=dp_id, name="parquet", kind="file", fmt="parquet"
    )
    assert port.kind == "file"
    assert [p.name for p in ports_service.list_output_ports(_factory(), data_product_id=dp_id)] == [
        "parquet"
    ]
    with pytest.raises(ValueError, match="already exists"):
        ports_service.create_output_port(
            _factory(), data_product_id=dp_id, name="parquet", kind="sql"
        )
    assert ports_service.delete_output_port(_factory(), data_product_id=dp_id, port_id=port.id)
    assert ports_service.list_output_ports(_factory(), data_product_id=dp_id) == []


def test_output_port_rejects_bad_kind() -> None:
    dp_id = _seed_dp("main", "ports_badkind")
    with pytest.raises(ValueError, match="kind"):
        ports_service.create_output_port(
            _factory(), data_product_id=dp_id, name="x", kind="bogus"
        )


def test_input_port_crud() -> None:
    dp_id = _seed_dp("main", "ports_in")
    port = ports_service.create_input_port(
        _factory(),
        data_product_id=dp_id,
        name="bronze",
        kind="upstream_product",
        source_ref="main.bronze",
    )
    assert port.source_ref == "main.bronze"
    rows = ports_service.list_input_ports(_factory(), data_product_id=dp_id)
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# service — semantic
# ---------------------------------------------------------------------------


def test_semantic_concepts_and_sample_sql() -> None:
    dp_id = _seed_dp("main", "sem")
    semantic_service.add_concept(
        _factory(), data_product_id=dp_id, concept="Order", maps_to="main.sem.orders.id"
    )
    with pytest.raises(ValueError, match="already declared"):
        semantic_service.add_concept(_factory(), data_product_id=dp_id, concept="Order")
    product = semantic_service.set_sample_sql(
        _factory(), data_product_id=dp_id, sql="SELECT 1"
    )
    assert product.sample_sql == "SELECT 1"
    cleared = semantic_service.set_sample_sql(_factory(), data_product_id=dp_id, sql="   ")
    assert cleared.sample_sql is None
    concepts = semantic_service.list_concepts(_factory(), data_product_id=dp_id)
    assert concepts[0].concept == "Order"


# ---------------------------------------------------------------------------
# service — glossary
# ---------------------------------------------------------------------------


def test_glossary_term_binding_and_reverse_lookup() -> None:
    term = glossary_service.create_term(
        _factory(), workspace_id=1, slug="net-rev", term="Net Revenue", definition="…"
    )
    glossary_service.bind_column(
        _factory(),
        term_id=term.id,
        catalog="main",
        schema="fin",
        table="ledger",
        column="net",
    )
    # idempotent re-bind.
    glossary_service.bind_column(
        _factory(),
        term_id=term.id,
        catalog="main",
        schema="fin",
        table="ledger",
        column="net",
    )
    assert len(glossary_service.list_bindings(_factory(), term_id=term.id)) == 1
    by_col = glossary_service.terms_for_column(
        _factory(), workspace_id=1, catalog="main", schema="fin", table="ledger", column="net"
    )
    assert [t.term for t in by_col] == ["Net Revenue"]
    by_schema = glossary_service.terms_for_schema(
        _factory(), workspace_id=1, catalog="main", schema="fin"
    )
    assert by_schema == {"ledger.net": ["Net Revenue"]}


def test_glossary_rejects_duplicate_slug() -> None:
    glossary_service.create_term(_factory(), workspace_id=1, slug="dup", term="Dup")
    with pytest.raises(ValueError, match="already exists"):
        glossary_service.create_term(_factory(), workspace_id=1, slug="dup", term="Dup2")


# ---------------------------------------------------------------------------
# B7 — light shape + write-time stamping hook + read-back
# ---------------------------------------------------------------------------


def test_light_shape_pandas() -> None:
    df = pd.DataFrame({"a": [1, 2, None], "b": ["x", "x", "y"]})
    shape = light_shape(df)
    assert shape["column_count"] == 2
    assert shape["columns"]["a"]["null_count"] == 1
    assert shape["columns"]["b"]["distinct"] == 2


def test_light_shape_unrecognised_frame_is_empty() -> None:
    assert light_shape(object()) == {}


def test_record_statistics_after_commit_inserts_and_noop() -> None:
    dp_id = _seed_dp("main", "stats_dp")
    # no-op when pending is None.
    record_statistics_after_commit(_factory(), op_id=1, target_table=None, pending=None)
    assert read_latest_statistics(_factory(), data_product_id=dp_id) == []
    # insert a snapshot.
    pending = (dp_id, "orders", 5, 42, {"column_count": 2, "columns": {}}, "light")
    record_statistics_after_commit(
        _factory(), op_id=1, target_table="main.stats_dp.orders", pending=pending
    )
    latest = read_latest_statistics(_factory(), data_product_id=dp_id)
    assert len(latest) == 1
    assert latest[0]["row_count"] == 42
    assert latest[0]["delta_log_version"] == 5


def test_read_latest_statistics_latest_per_table() -> None:
    dp_id = _seed_dp("main", "stats_latest")
    base = datetime.datetime(2026, 5, 29, 12, 0, tzinfo=datetime.UTC)
    with _factory()() as session:
        session.add_all(
            [
                DataProductStatistics(
                    data_product_id=dp_id,
                    agent_run_operation_id=None,
                    table_name="orders",
                    delta_log_version=1,
                    row_count=10,
                    shape_json="{}",
                    profile_kind="light",
                    created_at=base,
                ),
                DataProductStatistics(
                    data_product_id=dp_id,
                    agent_run_operation_id=None,
                    table_name="orders",
                    delta_log_version=2,
                    row_count=20,
                    shape_json="{}",
                    profile_kind="light",
                    created_at=base + datetime.timedelta(minutes=30),
                ),
                DataProductStatistics(
                    data_product_id=dp_id,
                    agent_run_operation_id=None,
                    table_name="customers",
                    delta_log_version=1,
                    row_count=5,
                    shape_json="{}",
                    profile_kind="light",
                    created_at=base,
                ),
            ]
        )
        session.commit()
    now = base + datetime.timedelta(minutes=90)
    latest = read_latest_statistics(_factory(), data_product_id=dp_id, now=now)
    by_table = {r["table_name"]: r for r in latest}
    assert by_table["orders"]["row_count"] == 20  # newer snapshot wins
    assert by_table["orders"]["freshness_lag_minutes"] == 60
    assert by_table["customers"]["row_count"] == 5


# ---------------------------------------------------------------------------
# API — discovery, ports/semantic gate, export guard, glossary
# ---------------------------------------------------------------------------


async def test_discovery_contract_shape() -> None:
    _seed_dp("main", "disco", tables=[{"name": "t", "columns": [{"name": "id", "type": "long"}]}])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/data-products/main/disco/discovery")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["uri"].startswith("urn:pointlessql:product:")
    assert body["uri"].endswith(":main:disco")
    assert body["discovery_version"] == "1.0"
    assert {"identity", "semantics", "output_ports", "input_ports", "tables", "slos",
            "statistics", "links"} <= set(body)
    assert body["tables"][0]["name"] == "t"


async def test_output_port_mutation_requires_steward_or_admin() -> None:
    _seed_dp("main", "gate_dp")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/main/gate_dp/output-ports",
            json={"name": "x", "kind": "file"},
        )
    assert res.status_code in (401, 403)


async def test_output_port_create_via_api_as_admin() -> None:
    _seed_dp("main", "admin_port_dp")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/main/admin_port_dp/output-ports",
            json={"name": "parquet", "kind": "file", "format": "parquet"},
        )
        assert res.status_code == 200, res.text
        listing = await client.get("/api/data-products/main/admin_port_dp/output-ports")
    assert listing.json()["output_ports"][0]["name"] == "parquet"


async def test_export_rejects_undeclared_table() -> None:
    _seed_dp("main", "exp_dp", tables=[{"name": "declared", "columns": []}])
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/data-products/main/exp_dp/export?table=undeclared")
    assert res.status_code == 400


async def test_glossary_admin_crud_and_browse() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        post = await client.post(
            "/api/admin/glossary", json={"slug": "churn", "term": "Churn", "definition": "…"}
        )
        assert post.status_code == 200, post.text
        term_id = post.json()["id"]
        bind = await client.post(
            f"/api/admin/glossary/{term_id}/bindings",
            json={"catalog": "main", "schema": "crm", "table": "users", "column": "churned"},
        )
        assert bind.status_code == 200
        browse = await client.get("/api/glossary")
        assert "churn" in {t["slug"] for t in browse.json()["terms"]}
        detail = await client.get("/api/glossary/churn")
        assert detail.json()["bindings"][0]["ref"] == "main.crm.users.churned"


async def test_glossary_admin_requires_admin() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.post("/api/admin/glossary", json={"slug": "x", "term": "X"})
    assert res.status_code in (401, 403)
