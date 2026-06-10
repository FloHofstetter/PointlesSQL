"""Service-level objectives — declaration, drift, evaluation, scan.

Covers the data-mesh δ observability half: the SLO CRUD, the
statistical-shape drift detector over the self-generated statistics
history, the per-product evaluator (measurable verdicts + unmeasured
declarations + implicit freshness), the workspace scan that logs
failures to the audit log, the discovery ``slos.additional`` block, and
the steward/admin API gate.
"""

from __future__ import annotations

import datetime
import json

import httpx
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    AuditLog,
    DataProduct,
    DataProductInputPort,
    DataProductStatistics,
)
from pointlessql.services import slo as slo_service
from pointlessql.services.slo._scan import SLO_VIOLATION_ACTION


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str, *, sla_minutes: int | None = None, tables=None) -> int:
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
            sla_minutes=sla_minutes,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=now,
            created_at=now,
        )
        session.add(row)
        session.commit()
        return row.id


def _add_stats(
    dp_id: int,
    table: str,
    *,
    row_count: int,
    shape: dict | None = None,
    age_minutes: int = 0,
    when: datetime.datetime | None = None,
) -> None:
    created = when or (
        datetime.datetime.now(datetime.UTC) - datetime.timedelta(minutes=age_minutes)
    )
    with _factory()() as session:
        session.add(
            DataProductStatistics(
                data_product_id=dp_id,
                table_name=table,
                delta_log_version=1,
                row_count=row_count,
                shape_json=json.dumps(shape or {}),
                profile_kind="light",
                freshness_lag_minutes=None,
                created_at=created,
            )
        )
        session.commit()


# --------------------------------------------------------------------------
# CRUD
# --------------------------------------------------------------------------


def test_declare_list_delete_slo() -> None:
    dp_id = _seed_dp("main", "slo_crud")
    row = slo_service.declare_slo(
        _factory(), data_product_id=dp_id, slo_kind="volume", target_value=100.0
    )
    assert row.slo_kind == "volume"
    assert row.comparator == "gte"  # kind default
    rows = slo_service.list_slos(_factory(), data_product_id=dp_id)
    assert len(rows) == 1
    assert slo_service.delete_slo(_factory(), data_product_id=dp_id, slo_id=row.id) is True
    assert slo_service.list_slos(_factory(), data_product_id=dp_id) == []


def test_declare_slo_upserts_on_identity() -> None:
    dp_id = _seed_dp("main", "slo_upsert")
    slo_service.declare_slo(_factory(), data_product_id=dp_id, slo_kind="volume", target_value=10.0)
    slo_service.declare_slo(_factory(), data_product_id=dp_id, slo_kind="volume", target_value=50.0)
    rows = slo_service.list_slos(_factory(), data_product_id=dp_id)
    assert len(rows) == 1
    assert rows[0].target_value == 50.0


# --------------------------------------------------------------------------
# drift (G3)
# --------------------------------------------------------------------------


def test_drift_unmeasured_with_single_snapshot() -> None:
    dp_id = _seed_dp("main", "drift_single")
    _add_stats(dp_id, "t", row_count=100, age_minutes=1)
    drift = slo_service.compute_drift(_factory(), data_product_id=dp_id, table_name="t")
    assert drift["measured"] is False
    assert drift["drifted"] is False


def test_drift_flags_row_count_jump() -> None:
    dp_id = _seed_dp("main", "drift_jump")
    # stable baseline ~100, then a 10x jump.
    for i, rows in enumerate([100, 101, 99, 100, 102]):
        _add_stats(dp_id, "t", row_count=rows, age_minutes=60 - i)
    _add_stats(dp_id, "t", row_count=1000, age_minutes=0)
    drift = slo_service.compute_drift(_factory(), data_product_id=dp_id, table_name="t", sigma=2.0)
    assert drift["measured"] is True
    assert drift["drifted"] is True


def test_drift_stable_series_no_drift() -> None:
    dp_id = _seed_dp("main", "drift_stable")
    for i, rows in enumerate([100, 101, 99, 100, 102, 100]):
        _add_stats(dp_id, "t", row_count=rows, age_minutes=60 - i)
    drift = slo_service.compute_drift(_factory(), data_product_id=dp_id, table_name="t", sigma=3.0)
    assert drift["drifted"] is False


# --------------------------------------------------------------------------
# evaluate (G1)
# --------------------------------------------------------------------------


def test_evaluate_volume_pass_and_fail() -> None:
    dp_id = _seed_dp("main", "slo_vol")
    _add_stats(dp_id, "orders", row_count=100, age_minutes=1)
    slo_service.declare_slo(
        _factory(), data_product_id=dp_id, slo_kind="volume", target_value=50.0, table_name="orders"
    )
    result = slo_service.evaluate_product(_factory(), data_product_id=dp_id)
    volume = next(r for r in result["results"] if r["slo_kind"] == "volume")
    assert volume["verdict"] == "pass"

    slo_service.declare_slo(
        _factory(),
        data_product_id=dp_id,
        slo_kind="volume",
        target_value=500.0,
        table_name="orders",
    )
    result = slo_service.evaluate_product(_factory(), data_product_id=dp_id)
    volume = next(r for r in result["results"] if r["slo_kind"] == "volume")
    assert volume["verdict"] == "fail"


def test_evaluate_completeness() -> None:
    dp_id = _seed_dp("main", "slo_complete")
    shape = {"column_count": 2, "columns": {"a": {"null_count": 10}, "b": {"null_count": 0}}}
    _add_stats(dp_id, "t", row_count=100, shape=shape, age_minutes=1)  # 95% complete
    slo_service.declare_slo(
        _factory(), data_product_id=dp_id, slo_kind="completeness", target_value=90.0
    )
    result = slo_service.evaluate_product(_factory(), data_product_id=dp_id)
    comp = next(r for r in result["results"] if r["slo_kind"] == "completeness")
    assert comp["observed"] == 95.0
    assert comp["verdict"] == "pass"


def test_evaluate_unmeasured_for_declaration_only_kind() -> None:
    dp_id = _seed_dp("main", "slo_decl")
    slo_service.declare_slo(
        _factory(), data_product_id=dp_id, slo_kind="precision_accuracy", target_value=99.0
    )
    result = slo_service.evaluate_product(_factory(), data_product_id=dp_id)
    pa = next(r for r in result["results"] if r["slo_kind"] == "precision_accuracy")
    assert pa["verdict"] == "unmeasured"
    assert pa["measurable"] is False


def test_evaluate_implicit_freshness_from_sla() -> None:
    dp_id = _seed_dp("main", "slo_fresh", sla_minutes=60)
    _add_stats(dp_id, "t", row_count=10, age_minutes=5)
    result = slo_service.evaluate_product(_factory(), data_product_id=dp_id)
    fresh = next(r for r in result["results"] if r["slo_kind"] == "freshness")
    assert fresh["source"] == "implicit_freshness"
    assert fresh["verdict"] == "pass"


def test_evaluate_lineage_coverage() -> None:
    dp_id = _seed_dp("main", "slo_lin")
    slo_service.declare_slo(
        _factory(), data_product_id=dp_id, slo_kind="lineage", target_value=100.0
    )
    # No input ports declared → observed 0 → fail.
    result = slo_service.evaluate_product(_factory(), data_product_id=dp_id)
    lin = next(r for r in result["results"] if r["slo_kind"] == "lineage")
    assert lin["verdict"] == "fail"
    # Declare an input port → observed 100 → pass.
    with _factory()() as session:
        session.add(
            DataProductInputPort(
                data_product_id=dp_id,
                name="up",
                kind="upstream_product",
                source_ref="main.other",
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    result = slo_service.evaluate_product(_factory(), data_product_id=dp_id)
    lin = next(r for r in result["results"] if r["slo_kind"] == "lineage")
    assert lin["verdict"] == "pass"


# --------------------------------------------------------------------------
# scan (E9-equivalent) → audit log
# --------------------------------------------------------------------------


def test_scan_logs_violations_to_audit() -> None:
    dp_id = _seed_dp("main", "slo_scan")
    _add_stats(dp_id, "t", row_count=5, age_minutes=1)
    slo_service.declare_slo(
        _factory(), data_product_id=dp_id, slo_kind="volume", target_value=1000.0, table_name="t"
    )
    summary = slo_service.scan_workspace(_factory(), workspace_id=1)
    mine = [v for v in summary["violations"] if v.get("ref") == "main.slo_scan"]
    assert mine and mine[0]["slo_kind"] == "volume"
    with _factory()() as session:
        rows = session.scalars(
            select(AuditLog).where(
                AuditLog.action == SLO_VIOLATION_ACTION,
                AuditLog.target == "data_product:main.slo_scan",
            )
        ).all()
    assert len(rows) >= 1


# --------------------------------------------------------------------------
# API + discovery
# --------------------------------------------------------------------------


async def test_slo_mutation_requires_steward_or_admin() -> None:
    _seed_dp("main", "slo_gate")
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/main/slo_gate/slos",
            json={"slo_kind": "volume", "target_value": 1},
        )
    assert res.status_code in (401, 403)


async def test_slo_declare_and_evaluation_via_api() -> None:
    dp_id = _seed_dp("main", "slo_api")
    _add_stats(dp_id, "t", row_count=100, age_minutes=1)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.post(
            "/api/data-products/main/slo_api/slos",
            json={"slo_kind": "volume", "target_value": 50, "table": "t"},
        )
        assert res.status_code == 200, res.text
        res = await client.get("/api/data-products/main/slo_api/slo-evaluation")
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["passed"] >= 1


async def test_discovery_carries_slos_additional() -> None:
    dp_id = _seed_dp(
        "main",
        "slo_disco",
        tables=[{"name": "t", "columns": [{"name": "id", "type": "integer"}]}],
    )
    slo_service.declare_slo(_factory(), data_product_id=dp_id, slo_kind="volume", target_value=10.0)
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    ) as client:
        res = await client.get("/api/data-products/main/slo_disco/discovery")
    assert res.status_code == 200, res.text
    additional = res.json()["slos"]["additional"]
    assert any(s["slo_kind"] == "volume" for s in additional)
