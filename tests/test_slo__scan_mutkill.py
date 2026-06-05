"""Behaviour tests targeting surviving mutants in ``slo._scan``.

Pins the observable contract of :func:`scan_workspace`: which verdicts
get logged, the exact shape/keys of each violation ``finding``, the
durable audit row it writes (action, detail payload, actor role,
workspace scope), the sigma value threaded into the drift evaluation,
and the return dict keys — so dict-key, call-argument, branch, and
threshold mutations are caught.

The fixtures mirror ``tests/test_slo_mutkill.py``: they drive the
in-memory SQLite engine wired by the autouse ``_auth_db`` conftest
fixture through ``app.state.session_factory``.
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    AuditLog,
    DataProduct,
    DataProductStatistics,
    Workspace,
)
from pointlessql.services import slo as slo_service
from pointlessql.services.slo._scan import SLO_VIOLATION_ACTION


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str, *, workspace_id: int = 1) -> int:
    now = datetime.datetime.now(datetime.UTC)
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": [],
    }
    with _factory()() as session:
        row = DataProduct(
            workspace_id=workspace_id,
            catalog_name=catalog,
            schema_name=schema,
            steward_user_id=None,
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash=f"{catalog}_{schema}".ljust(64, "0"),
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
    when: datetime.datetime | None = None,
) -> None:
    created = when or datetime.datetime.now(datetime.UTC)
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


def _make_workspace(workspace_id: int) -> None:
    """Create an additional workspace so an FK-backed DP can live in it."""
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            Workspace(
                id=workspace_id,
                slug=f"ws{workspace_id}",
                name=f"Workspace {workspace_id}",
                description="",
                created_at=now,
            )
        )
        session.commit()


def _seed_failing_volume(catalog: str, schema: str, *, workspace_id: int = 1) -> int:
    """Seed a product whose declared volume SLO fails (5 rows < target)."""
    dp = _seed_dp(catalog, schema, workspace_id=workspace_id)
    _add_stats(dp, "t", row_count=5)
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        target_value=1000.0,
        table_name="t",
    )
    return dp


# ===========================================================================
# finding dict — exact key set (kills XX/uppercase key mutants)
# ===========================================================================


def test_violation_finding_has_exact_keys() -> None:
    # Kills the dict-key string mutations on table/target/comparator/unit
    # (and the surrounding slo_kind/observed keys): each key must be the
    # literal lowercase string the audit cockpit reads back.
    dp = _seed_failing_volume("scankeys", "v")
    summary = slo_service.scan_workspace(_factory(), workspace_id=1)
    mine = [v for v in summary["violations"] if v.get("ref") == "scankeys.v"]
    assert len(mine) == 1
    finding_keys = set(mine[0].keys())
    assert finding_keys == {
        "slo_kind",
        "table",
        "target",
        "observed",
        "comparator",
        "unit",
        "data_product_id",
        "ref",
    }
    assert mine[0]["table"] == "t"
    assert mine[0]["comparator"] == "gte"
    assert mine[0]["unit"] == "rows"
    assert mine[0]["data_product_id"] == dp


def test_audit_detail_payload_carries_finding_keys() -> None:
    # The audit row's detail JSON is the `finding` dict — kills the
    # `finding` -> None / removed-arg mutants (detail would be null) and
    # the dict-key mutants surfaced through the persisted payload.
    _seed_failing_volume("scandetail", "v")
    slo_service.scan_workspace(_factory(), workspace_id=1)
    with _factory()() as session:
        row = session.scalars(
            select(AuditLog).where(
                AuditLog.action == SLO_VIOLATION_ACTION,
                AuditLog.target == "data_product:scandetail.v",
            )
        ).one()
    assert row.detail is not None
    detail = json.loads(row.detail)
    assert set(detail.keys()) == {
        "slo_kind",
        "table",
        "target",
        "observed",
        "comparator",
        "unit",
    }
    assert detail["slo_kind"] == "volume"
    assert detail["table"] == "t"
    assert detail["observed"] == 5.0


# ===========================================================================
# audit row metadata — action, actor role, workspace scope
# ===========================================================================


def test_audit_row_actor_role_is_system() -> None:
    # Kills actor_role mutations: None (NULL insert / crash), removed
    # (falls back to log_action's "user" default), and the XX/uppercase
    # case mutations — the persisted role must be exactly "system".
    _seed_failing_volume("scanrole", "v")
    slo_service.scan_workspace(_factory(), workspace_id=1)
    with _factory()() as session:
        row = session.scalars(
            select(AuditLog).where(
                AuditLog.action == SLO_VIOLATION_ACTION,
                AuditLog.target == "data_product:scanrole.v",
            )
        ).one()
    assert row.actor_role == "system"


def test_audit_row_logged_under_scanned_workspace() -> None:
    # Kills `workspace_id=workspace_id` -> None (NULL insert) and the
    # dropped-kwarg mutant (falls back to log_action's default of 1).
    # The product lives in workspace 7, so the audit row must carry 7.
    _make_workspace(7)
    _seed_failing_volume("scanws", "v", workspace_id=7)
    slo_service.scan_workspace(_factory(), workspace_id=7)
    with _factory()() as session:
        rows = session.scalars(
            select(AuditLog).where(
                AuditLog.action == SLO_VIOLATION_ACTION,
                AuditLog.target == "data_product:scanws.v",
            )
        ).all()
    assert len(rows) == 1
    assert rows[0].workspace_id == 7


# ===========================================================================
# verdict filter loop — continue must not become break
# ===========================================================================


def test_passing_then_failing_slo_still_logs_failure() -> None:
    # Two SLOs on one product ordered so a *passing* verdict is iterated
    # before the failing one (completeness passes, volume fails; results
    # are emitted completeness-then-volume by table/kind ordering).  The
    # `continue` on a non-fail verdict must skip only that result; the
    # `break` mutant would abandon the loop and drop the later failure.
    dp = _seed_dp("scanloop", "v")
    _add_stats(dp, "t", row_count=5, shape={"columns": {"a": {"null_count": 0}}})
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="completeness",
        target_value=90.0,
        table_name="t",
    )
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        target_value=1000.0,
        table_name="t",
    )
    summary = slo_service.scan_workspace(_factory(), workspace_id=1)
    mine = [v for v in summary["violations"] if v.get("ref") == "scanloop.v"]
    kinds = {v["slo_kind"] for v in mine}
    # completeness passes (100% >= 90) so it is skipped; volume fails and
    # must still be recorded despite the earlier passing iteration.
    assert kinds == {"volume"}


# ===========================================================================
# sigma threading into the drift evaluation
# ===========================================================================


def _seed_drift_series(dp_id: int, table: str, counts: list[int]) -> None:
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    for i, c in enumerate(counts):
        _add_stats(dp_id, table, row_count=c, when=base + datetime.timedelta(minutes=i))


def test_statistical_shape_scan_threads_numeric_sigma() -> None:
    # A statistical_shape SLO routes through compute_drift, whose metric
    # builder evaluates `z > sigma`.  The `sigma=sigma` -> `sigma=None`
    # call-site mutant makes that comparison `z > None`, raising
    # TypeError and aborting the whole scan.  On real code the scan
    # completes and emits the drift verdict.
    dp = _seed_dp("scansigma", "v")
    _seed_drift_series(dp, "t", [10, 20, 30, 28])
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="statistical_shape",
        target_value=0.1,
        table_name="t",
    )
    summary = slo_service.scan_workspace(_factory(), workspace_id=1)
    mine = [v for v in summary["violations"] if v.get("ref") == "scansigma.v"]
    # observed worst z-score (~0.98) > target 0.1 under lte -> fail logged.
    assert len(mine) == 1
    assert mine[0]["slo_kind"] == "statistical_shape"
    assert mine[0]["observed"] == pytest.approx(8.0 / 8.164965809, rel=1e-6)


# ===========================================================================
# return dict — exact keys
# ===========================================================================


def test_scan_return_dict_has_exact_keys() -> None:
    # Kills `products_scanned` key XX/uppercase mutations.
    _seed_failing_volume("scanret", "v")
    summary = slo_service.scan_workspace(_factory(), workspace_id=1)
    assert set(summary.keys()) == {"products_scanned", "violations"}
    assert summary["products_scanned"] >= 1
    assert isinstance(summary["violations"], list)
