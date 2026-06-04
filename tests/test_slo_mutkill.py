"""Behaviour tests targeting surviving SLO mutants.

Pins exact observable outputs of the SLO layer — verdict boundaries,
the drift z-score arithmetic surfaced through the metric dicts, the
percentile interpolation, the evaluator roll-up, and the runtime
measurers — so that arithmetic / comparator / dict-key / branch
mutations in ``pointlessql.services.slo`` are caught.

The fixtures mirror ``tests/test_slo.py`` and ``tests/test_runtime_slo.py``:
they drive the in-memory SQLite engine wired by the autouse ``_auth_db``
conftest fixture through ``app.state.session_factory``.
"""

from __future__ import annotations

import datetime
import json

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    AuditLog,
    DataProduct,
    DataProductAvailabilityProbe,
    DataProductContractEvent,
    DataProductInputPort,
    DataProductQueryPerfSample,
    DataProductStatistics,
)
from pointlessql.services import slo as slo_service
from pointlessql.services.slo import _runtime as runtime_slo
from pointlessql.services.slo._drift import _z_score, compute_drift, max_drift_sigma
from pointlessql.services.slo._evaluate import (
    _completeness_pct,
    _verdict,
    evaluate_product,
)
from pointlessql.services.slo._interval_of_change import (
    IntervalOfChangeMeasurement,
    measure_interval_of_change,
    verdict_from_measurement,
)
from pointlessql.services.slo._scan import SLO_VIOLATION_ACTION


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str, *, sla_minutes: int | None = None) -> int:
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
            workspace_id=1,
            catalog_name=catalog,
            schema_name=schema,
            steward_user_id=None,
            version="1.0.0",
            description="",
            sla_minutes=sla_minutes,
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


# ===========================================================================
# _verdict — boundary + comparator + exact-string mutants
# ===========================================================================


def test_verdict_lte_boundary_equal_is_pass() -> None:
    # Kills `observed <= target` -> `observed < target`: at equality the
    # strict-less mutant would flip pass -> fail.
    assert _verdict(50.0, 50.0, "lte") == "pass"


def test_verdict_lte_over_target_is_fail() -> None:
    assert _verdict(51.0, 50.0, "lte") == "fail"


def test_verdict_gte_boundary_equal_is_pass() -> None:
    assert _verdict(50.0, 50.0, "gte") == "pass"


def test_verdict_gte_under_target_is_fail() -> None:
    assert _verdict(49.0, 50.0, "gte") == "fail"


def test_verdict_eq_equal_is_pass_unequal_is_fail() -> None:
    # Kills `observed == target` -> `observed != target`.
    assert _verdict(50.0, 50.0, "eq") == "pass"
    assert _verdict(50.0, 51.0, "eq") == "fail"


def test_verdict_unmeasured_requires_or_not_and() -> None:
    # Kills `observed is None or target is None` -> `... and ...`:
    # with only one None the `and` mutant would try the comparison and
    # crash / mis-verdict instead of returning "unmeasured".
    assert _verdict(None, 50.0, "lte") == "unmeasured"
    assert _verdict(50.0, None, "lte") == "unmeasured"


def test_verdict_exact_strings() -> None:
    # Kills uppercase / XX-wrapped string mutants on the literals.
    assert _verdict(1.0, 2.0, "lte") == "pass"
    assert _verdict(3.0, 2.0, "lte") == "fail"
    assert _verdict(None, None, "lte") == "unmeasured"


# ===========================================================================
# _completeness_pct — saturation + structure mutants
# ===========================================================================


def test_completeness_full_is_100_not_clamped_up() -> None:
    # All-non-null -> 100.0.  Kills `max(0.0, ...)` -> `max(1.0, ...)`
    # only indirectly; the direct kill is that 100.0 is returned, not 1.0.
    entry = {
        "row_count": 10,
        "shape": {"columns": {"a": {"null_count": 0}, "b": {"null_count": 0}}},
    }
    assert _completeness_pct(entry) == 100.0


def test_completeness_partial_fraction() -> None:
    # 10 rows x 2 cols = 20 cells, 5 null -> 75% complete.
    entry = {
        "row_count": 10,
        "shape": {"columns": {"a": {"null_count": 5}, "b": {"null_count": 0}}},
    }
    assert _completeness_pct(entry) == 75.0


def test_completeness_none_when_no_rows_or_no_columns() -> None:
    # Kills `not row_count or not columns` -> `... and ...`: with rows
    # present but zero columns the `and` mutant would not short-circuit
    # to None and would divide by zero instead.
    assert _completeness_pct({"row_count": 0, "shape": {"columns": {"a": {}}}}) is None
    assert _completeness_pct({"row_count": 10, "shape": {"columns": {}}}) is None


# ===========================================================================
# _z_score — arithmetic surfaced directly
# ===========================================================================


def test_z_score_empty_baseline_returns_zeros() -> None:
    # Kills the `n == 0` guard return tuple (0.0, observed, 0.0).
    z, mean, std = _z_score(42.0, [])
    assert (z, mean, std) == (0.0, 42.0, 0.0)


def test_z_score_known_values() -> None:
    # baseline [10, 20, 30]: mean 20, population std sqrt(200/3)=8.16497.
    # observed 28 -> z = |28-20| / 8.16497 = 0.97980.
    z, mean, std = _z_score(28.0, [10.0, 20.0, 30.0])
    assert mean == pytest.approx(20.0)
    assert std == pytest.approx(8.164965809, rel=1e-9)
    assert z == pytest.approx(8.0 / 8.164965809, rel=1e-9)


def test_z_score_zero_variance_match_is_zero_diverge_is_inf() -> None:
    z_match, mean, std = _z_score(5.0, [5.0, 5.0, 5.0])
    assert (z_match, mean, std) == (0.0, 5.0, 0.0)
    z_div, _, _ = _z_score(9.0, [5.0, 5.0, 5.0])
    assert z_div == float("inf")


# ===========================================================================
# compute_drift — baseline window, drift threshold, metric dict shape
# ===========================================================================


def _seed_drift_series(dp_id: int, table: str, counts: list[int]) -> None:
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    # counts[0] is the OLDEST; the latest (most-recent created_at) is last.
    for i, c in enumerate(counts):
        _add_stats(dp_id, table, row_count=c, when=base + datetime.timedelta(minutes=i))


def test_drift_metric_dict_exact_shape_and_values() -> None:
    dp = _seed_dp("drift", "shape")
    # baseline rows [10, 20, 30] then latest 28.
    _seed_drift_series(dp, "t", [10, 20, 30, 28])
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    assert drift["measured"] is True
    assert drift["baseline_n"] == 3
    rc = next(m for m in drift["metrics"] if m["metric"] == "row_count")
    # Exact keys present — kills XX-key / uppercase-key mutants.
    assert set(rc.keys()) == {"metric", "observed", "mean", "std", "z", "drifted"}
    assert rc["observed"] == 28.0
    assert rc["mean"] == pytest.approx(20.0)
    assert rc["std"] == pytest.approx(8.164965809, rel=1e-9)
    assert rc["z"] == pytest.approx(8.0 / 8.164965809, rel=1e-9)
    assert rc["drifted"] is False


def test_drift_threshold_is_strict_greater_not_geq() -> None:
    # Construct a series whose z-score on the latest equals sigma exactly,
    # so `z > sigma` is False but `z >= sigma` would be True.  Kills the
    # `drifted = z > sigma` -> `z >= sigma` mutant.
    # baseline [0, 0, 2, 2]: mean 1.0, variance 1.0, std 1.0.
    # observed 3.0 -> z = |3-1|/1 = 2.0 == sigma.
    dp = _seed_dp("drift", "thresh")
    _seed_drift_series(dp, "t", [0, 0, 2, 2, 3])
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    rc = next(m for m in drift["metrics"] if m["metric"] == "row_count")
    assert rc["z"] == pytest.approx(2.0)
    assert rc["drifted"] is False
    assert drift["drifted"] is False


def test_drift_baseline_excludes_only_latest() -> None:
    # Kills `baseline = snapshots[1:]` -> `snapshots[2:]`.  With a tiny
    # baseline of exactly two prior snapshots, dropping one would change
    # mean/std and (here) baseline_n.
    dp = _seed_dp("drift", "base")
    _seed_drift_series(dp, "t", [100, 200, 150])  # baseline [100, 200], latest 150
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    assert drift["baseline_n"] == 2
    rc = next(m for m in drift["metrics"] if m["metric"] == "row_count")
    assert rc["mean"] == pytest.approx(150.0)  # (100+200)/2


def test_drift_null_ratio_metric_present() -> None:
    # null_count drift on a column — exercises _null_ratios + the second
    # metric-dict builder.
    dp = _seed_dp("drift", "nulls")
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    for i, nulls in enumerate([0, 0, 0, 50]):
        shape = {"columns": {"a": {"null_count": nulls}}}
        _add_stats(dp, "t", row_count=100, shape=shape, when=base + datetime.timedelta(minutes=i))
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    nr = next(m for m in drift["metrics"] if m["metric"] == "null_ratio:a")
    assert nr["observed"] == pytest.approx(0.5)  # 50/100
    assert nr["mean"] == pytest.approx(0.0)
    assert nr["drifted"] is True
    assert drift["drifted"] is True


def test_drift_single_snapshot_unmeasured() -> None:
    dp = _seed_dp("drift", "single")
    _add_stats(dp, "t", row_count=100)
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t")
    assert drift == {
        "measured": False,
        "drifted": False,
        "baseline_n": 0,
        "metrics": [],
    }


def test_max_drift_sigma_picks_largest_finite() -> None:
    drift = {"metrics": [{"z": 1.0}, {"z": 3.5}, {"z": None}, {"z": 2.0}]}
    assert max_drift_sigma(drift) == 3.5
    assert max_drift_sigma({"metrics": []}) == 0.0


# ===========================================================================
# evaluate_product — roll-up arithmetic, dict keys, branch selection
# ===========================================================================


def test_evaluate_result_dict_exact_keys() -> None:
    dp = _seed_dp("eval", "keys")
    _add_stats(dp, "t", row_count=100)
    slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="volume", target_value=50.0, table_name="t"
    )
    result = evaluate_product(_factory(), data_product_id=dp)
    vol = next(r for r in result["results"] if r["slo_kind"] == "volume")
    assert set(vol.keys()) == {
        "slo_kind",
        "table",
        "target",
        "comparator",
        "unit",
        "observed",
        "verdict",
        "source",
        "measurable",
    }
    assert vol["table"] == "t"
    assert vol["target"] == 50.0
    assert vol["source"] == "declared"
    assert vol["measurable"] is True
    assert set(result.keys()) == {
        "data_product_id",
        "results",
        "passed",
        "failed",
        "unmeasured",
        "pass_rate",
    }
    assert result["data_product_id"] == dp


def test_evaluate_pass_rate_arithmetic() -> None:
    # One pass (volume>=50 with 100 rows), one fail (volume>=500), one
    # unmeasured (precision_accuracy declaration).  pass_rate = 1/2.
    # Kills `scored = passed + failed` -> `passed - failed` (would give 0
    # -> pass_rate None) and `passed / scored` -> `passed * scored`.
    dp = _seed_dp("eval", "rate")
    _add_stats(dp, "t", row_count=100)
    slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="volume", target_value=50.0, table_name="t"
    )
    slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="completeness", target_value=999.0, table_name="t"
    )
    _add_stats(
        dp,
        "t",
        row_count=100,
        shape={"columns": {"a": {"null_count": 0}}},
        when=datetime.datetime.now(datetime.UTC) + datetime.timedelta(seconds=1),
    )
    slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="precision_accuracy", target_value=99.0
    )
    result = evaluate_product(_factory(), data_product_id=dp)
    assert result["passed"] == 1
    assert result["failed"] == 1
    assert result["unmeasured"] == 1
    assert result["pass_rate"] == pytest.approx(0.5)


def test_evaluate_pass_rate_none_when_nothing_scored() -> None:
    dp = _seed_dp("eval", "noscore")
    slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="precision_accuracy", target_value=99.0
    )
    result = evaluate_product(_factory(), data_product_id=dp)
    assert result["pass_rate"] is None


def test_evaluate_disabled_slo_is_skipped_not_breaking_the_loop() -> None:
    # A disabled SLO appears before an enabled one (ordered by table/kind:
    # "completeness" < "volume").  Kills `continue` -> `break`: the break
    # mutant would skip the later enabled volume SLO entirely.
    dp = _seed_dp("eval", "disabled")
    _add_stats(dp, "t", row_count=100, shape={"columns": {"a": {"null_count": 0}}})
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="completeness",
        target_value=90.0,
        table_name="t",
        enabled=False,
    )
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        target_value=50.0,
        table_name="t",
        enabled=True,
    )
    result = evaluate_product(_factory(), data_product_id=dp)
    kinds = {r["slo_kind"] for r in result["results"]}
    assert "completeness" not in kinds  # disabled, skipped
    assert "volume" in kinds  # still evaluated despite the earlier skip
    vol = next(r for r in result["results"] if r["slo_kind"] == "volume")
    assert vol["verdict"] == "pass"


def test_evaluate_implicit_freshness_suppressed_by_declared_freshness() -> None:
    # Kills `has_declared_freshness` mutations: when an explicit freshness
    # SLO is declared, the implicit one (source=implicit_freshness) must
    # NOT be appended.
    dp = _seed_dp("eval", "fresh_override", sla_minutes=60)
    _add_stats(dp, "t", row_count=10)
    slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="freshness", target_value=120.0
    )
    result = evaluate_product(_factory(), data_product_id=dp)
    sources = [r["source"] for r in result["results"] if r["slo_kind"] == "freshness"]
    assert "implicit_freshness" not in sources
    assert sources == ["declared"]


def test_evaluate_implicit_freshness_present_without_declared() -> None:
    dp = _seed_dp("eval", "fresh_implicit", sla_minutes=60)
    _add_stats(dp, "t", row_count=10)
    result = evaluate_product(_factory(), data_product_id=dp)
    fresh = next(r for r in result["results"] if r["slo_kind"] == "freshness")
    assert fresh["source"] == "implicit_freshness"
    assert fresh["table"] is None
    assert fresh["target"] == 60.0
    assert fresh["measurable"] is True


def test_evaluate_lineage_observes_100_with_inputs_0_without() -> None:
    dp = _seed_dp("eval", "lineage")
    slo_service.declare_slo(_factory(), data_product_id=dp, slo_kind="lineage", target_value=100.0)
    result = evaluate_product(_factory(), data_product_id=dp)
    lin = next(r for r in result["results"] if r["slo_kind"] == "lineage")
    assert lin["observed"] == 0.0
    assert lin["verdict"] == "fail"
    with _factory()() as session:
        session.add(
            DataProductInputPort(
                data_product_id=dp,
                name="up",
                kind="upstream_product",
                source_ref="main.other",
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    result = evaluate_product(_factory(), data_product_id=dp)
    lin = next(r for r in result["results"] if r["slo_kind"] == "lineage")
    assert lin["observed"] == 100.0
    assert lin["verdict"] == "pass"


# ===========================================================================
# runtime _percentile_sorted — interpolation correctness
# ===========================================================================


def test_runtime_percentile_empty_and_single() -> None:
    assert runtime_slo._percentile_sorted([], 0.95) == 0.0
    assert runtime_slo._percentile_sorted([7.0], 0.95) == 7.0


def test_runtime_percentile_interpolates() -> None:
    # values [0, 10] at q=0.5 -> rank 0.5 -> 0*0.5 + 10*0.5 = 5.0.
    # Kills `lo + 1` -> `lo - 1`, `1 - frac` sign flips, and rank math.
    assert runtime_slo._percentile_sorted([0.0, 10.0], 0.5) == 5.0
    # [0, 100] at q=0.95 -> rank 0.95 -> 0*0.05 + 100*0.95 = 95.0.
    assert runtime_slo._percentile_sorted([0.0, 100.0], 0.95) == pytest.approx(95.0)


def test_runtime_percentile_p95_of_five() -> None:
    # [10, 20, 30, 40, 50] q=0.95 -> rank = 4*0.95 = 3.8 -> lo=3, hi=4,
    # frac 0.8 -> 40*0.2 + 50*0.8 = 48.0.
    assert runtime_slo._percentile_sorted([10.0, 20.0, 30.0, 40.0, 50.0], 0.95) == pytest.approx(
        48.0
    )


# ===========================================================================
# measure_availability — ratio, ok-filter, comparator, detail dict, scope
# ===========================================================================


def _seed_probes(dp_id: int, ok: int, fail: int, *, when: datetime.datetime | None = None) -> None:
    moment = when or datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        for _ in range(ok):
            session.add(
                DataProductAvailabilityProbe(
                    data_product_id=dp_id,
                    output_port_id=None,
                    port_kind="sql",
                    probed_at=moment,
                    latency_ms=5,
                    status="ok",
                )
            )
        for _ in range(fail):
            session.add(
                DataProductAvailabilityProbe(
                    data_product_id=dp_id,
                    output_port_id=None,
                    port_kind="sql",
                    probed_at=moment,
                    latency_ms=None,
                    status="fail",
                )
            )
        session.commit()


def test_availability_observed_percent_and_counts() -> None:
    dp = _seed_dp("avail", "pct")
    _seed_probes(dp, ok=3, fail=1)
    verdict, detail = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=70.0
    )
    # 3/4 -> 75.0.  Kills `ok / total` swap and the `* 100.0` constant.
    assert detail["observed_percent"] == pytest.approx(75.0)
    assert detail["ok_count"] == 3
    assert detail["total_count"] == 4
    assert detail["window_days"] == 7
    assert set(detail.keys()) == {
        "observed_percent",
        "ok_count",
        "total_count",
        "window_days",
    }
    assert verdict == "pass"  # 75 >= 70


def test_availability_gte_boundary_equal_is_pass() -> None:
    dp = _seed_dp("avail", "boundary")
    _seed_probes(dp, ok=3, fail=1)  # 75.0
    verdict, _ = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=75.0, comparator="gte"
    )
    # Kills `observed >= target` -> `observed > target`.
    assert verdict == "pass"


def test_availability_filters_status_ok_only() -> None:
    # All probes are "fail" -> observed 0 -> fail.  Kills `r.status == "ok"`
    # string mutations (would otherwise count everything as ok).
    dp = _seed_dp("avail", "allfail")
    _seed_probes(dp, ok=0, fail=4)
    verdict, detail = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=50.0
    )
    assert detail["ok_count"] == 0
    assert detail["observed_percent"] == 0.0
    assert verdict == "fail"


def test_availability_scopes_to_product() -> None:
    # Probes on a different product must not be counted.  Kills the
    # removal of the `data_product_id == data_product_id` where-clause.
    dp = _seed_dp("avail", "scoped")
    other = _seed_dp("avail", "other")
    _seed_probes(dp, ok=1, fail=1)  # this product: 50%
    _seed_probes(other, ok=10, fail=0)  # other product: would skew to ~92%
    _verdict_, detail = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=50.0
    )
    assert detail["total_count"] == 2
    assert detail["observed_percent"] == pytest.approx(50.0)


def test_availability_window_excludes_old_probes() -> None:
    # A probe older than the window must be excluded.  Kills the
    # `probed_at >= cutoff` filter removal / operator flip indirectly via
    # the count, and the window_days default.
    dp = _seed_dp("avail", "window")
    now = datetime.datetime.now(datetime.UTC)
    _seed_probes(dp, ok=1, fail=0, when=now)
    _seed_probes(dp, ok=0, fail=5, when=now - datetime.timedelta(days=30))
    _verdict_, detail = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=50.0, window_days=7
    )
    assert detail["total_count"] == 1  # only the recent ok probe
    assert detail["observed_percent"] == 100.0


def test_availability_unmeasured_without_probes() -> None:
    dp = _seed_dp("avail", "none")
    verdict, detail = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=99.0
    )
    assert verdict == "unmeasured"
    assert detail == {"reason": "no probes in window"}


# ===========================================================================
# measure_performance — p95 + detail dict
# ===========================================================================


def test_performance_p95_and_detail() -> None:
    dp = _seed_dp("perf", "p95")
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        for d in [10, 20, 30, 40, 50]:
            session.add(
                DataProductQueryPerfSample(
                    data_product_id=dp,
                    table_name="t",
                    started_at=now,
                    duration_ms=d,
                    status="ok",
                )
            )
        session.commit()
    verdict, detail = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=100.0
    )
    # sorted [10,20,30,40,50] p95 -> 48.0 (see percentile test).
    assert detail["observed_p95_ms"] == pytest.approx(48.0)
    assert detail["sample_count"] == 5
    assert set(detail.keys()) == {"observed_p95_ms", "sample_count"}
    assert verdict == "pass"  # 48 <= 100


def test_performance_lte_fail_when_over_target() -> None:
    dp = _seed_dp("perf", "slow")
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            DataProductQueryPerfSample(
                data_product_id=dp,
                table_name="t",
                started_at=now,
                duration_ms=5000,
                status="ok",
            )
        )
        session.add(
            DataProductQueryPerfSample(
                data_product_id=dp,
                table_name="t",
                started_at=now,
                duration_ms=6000,
                status="ok",
            )
        )
        session.commit()
    verdict, _ = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=1000.0
    )
    assert verdict == "fail"


def test_performance_excludes_non_ok_samples() -> None:
    # Only status="ok" samples count.  Kills the `status == "ok"` filter.
    dp = _seed_dp("perf", "errsamples")
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        session.add(
            DataProductQueryPerfSample(
                data_product_id=dp,
                table_name="t",
                started_at=now,
                duration_ms=10,
                status="ok",
            )
        )
        session.add(
            DataProductQueryPerfSample(
                data_product_id=dp,
                table_name="t",
                started_at=now,
                duration_ms=99999,
                status="timeout",
            )
        )
        session.commit()
    _verdict_, detail = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=1000.0
    )
    assert detail["sample_count"] == 1
    assert detail["observed_p95_ms"] == pytest.approx(10.0)


# ===========================================================================
# measure_precision_accuracy — null_ratio default + comparator
# ===========================================================================


def _seed_precision_stats(dp_id: int, table: str, null_ratio_max: float) -> None:
    with _factory()() as session:
        session.add(
            DataProductStatistics(
                data_product_id=dp_id,
                table_name=table,
                row_count=100,
                shape_json=json.dumps({"null_ratio_max": null_ratio_max}),
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()


def test_precision_observed_and_detail() -> None:
    dp = _seed_dp("prec", "obs")
    _seed_precision_stats(dp, "t", 0.02)
    verdict, detail = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name=None, target_value=0.05
    )
    assert detail["observed"] == pytest.approx(0.02)
    assert detail["target"] == pytest.approx(0.05)
    assert detail["comparator"] == "lte"
    assert verdict == "pass"


def test_precision_default_null_ratio_zero_when_key_missing() -> None:
    # Snapshot has no "null_ratio_max" key -> default 0.0 -> pass under any
    # positive lte target.  Kills `payload.get("null_ratio_max", 0.0)`
    # default change to 1.0 (which would flip pass -> fail).
    dp = _seed_dp("prec", "missing")
    with _factory()() as session:
        session.add(
            DataProductStatistics(
                data_product_id=dp,
                table_name="t",
                row_count=100,
                shape_json=json.dumps({"other": 1}),
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    verdict, detail = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name=None, target_value=0.05
    )
    assert detail["observed"] == 0.0
    assert verdict == "pass"


# ===========================================================================
# measure_runtime_kind dispatch
# ===========================================================================


def test_dispatch_unknown_kind_raises_valueerror() -> None:
    dp = _seed_dp("disp", "bad")
    with pytest.raises(ValueError):
        runtime_slo.measure_runtime_kind(
            _factory(), kind="nope", data_product_id=dp, target_value=0.0, comparator="lte"
        )


def test_dispatch_routes_performance_with_sample_window() -> None:
    dp = _seed_dp("disp", "perf")
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        for d in [100, 200, 300]:
            session.add(
                DataProductQueryPerfSample(
                    data_product_id=dp,
                    table_name="t",
                    started_at=now,
                    duration_ms=d,
                    status="ok",
                )
            )
        session.commit()
    verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="performance",
        data_product_id=dp,
        target_value=10000.0,
        comparator="lte",
    )
    assert verdict == "pass"
    assert "observed_p95_ms" in detail


# ===========================================================================
# interval_of_change verdict_from_measurement — boundary + detail
# ===========================================================================


def _measurement(median: float, p95: float = 0.0, n: int = 3) -> IntervalOfChangeMeasurement:
    return IntervalOfChangeMeasurement(
        median_minutes=median,
        p95_minutes=p95 or median,
        sample_size=n,
        last_write_at="2026-05-30T12:00:00+00:00",
    )


def test_ioc_verdict_lte_boundary_equal_is_pass() -> None:
    verdict, _ = verdict_from_measurement(_measurement(60.0), target_value=60.0, comparator="lte")
    assert verdict == "pass"  # kills `<= -> <`


def test_ioc_verdict_gte_boundary_equal_is_pass() -> None:
    verdict, _ = verdict_from_measurement(_measurement(60.0), target_value=60.0, comparator="gte")
    assert verdict == "pass"  # kills `>= -> >`


def test_ioc_verdict_detail_dict_exact() -> None:
    m = _measurement(60.0, p95=120.0, n=4)
    verdict, detail = verdict_from_measurement(m, target_value=100.0, comparator="lte")
    assert verdict == "pass"
    assert detail == {
        "observed": 60.0,
        "p95_minutes": 120.0,
        "sample_size": 4,
        "last_write_at": "2026-05-30T12:00:00+00:00",
    }


def test_ioc_verdict_none_measurement_unmeasured() -> None:
    verdict, detail = verdict_from_measurement(None, target_value=60.0, comparator="lte")
    assert verdict == "unmeasured"
    assert detail == {"reason": "fewer than 2 write events"}


def _seed_op() -> int:
    """Create one AgentRun + AgentRunOperation, return op_id."""
    import uuid

    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        run = AgentRun(
            id=str(uuid.uuid4()),
            workspace_id=1,
            notebook_path="seed.py",
            status="running",
            started_at=now,
        )
        session.add(run)
        session.flush()
        op = AgentRunOperation(
            workspace_id=1,
            agent_run_id=run.id,
            ordinal=0,
            op_name="update",
            params_json="{}",
            started_at=now,
        )
        session.add(op)
        session.commit()
        return int(op.id)


def test_ioc_measure_intervals_from_db() -> None:
    # End-to-end: write events spaced 30/60/90 minutes apart -> median 60.
    dp = _seed_dp("ioc", "db")
    op_id = _seed_op()
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    timestamps = [base]
    for delta in [30, 60, 90]:
        timestamps.append(timestamps[-1] + datetime.timedelta(minutes=delta))
    with _factory()() as session:
        for ts in timestamps:
            session.add(
                DataProductContractEvent(
                    agent_run_operation_id=op_id,
                    data_product_id=dp,
                    outcome="compliant",
                    details_json="{}",
                    created_at=ts,
                )
            )
        session.commit()
    m = measure_interval_of_change(_factory(), data_product_id=dp)
    assert m is not None
    assert m.median_minutes == pytest.approx(60.0)
    assert m.sample_size == 3


# ===========================================================================
# declare_slo — resolution defaults + product validation
# ===========================================================================


def test_declare_resolves_kind_default_comparator_and_unit() -> None:
    dp = _seed_dp("crud", "defaults")
    row = slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="volume", target_value=10.0
    )
    # volume's kind default is gte / rows.
    assert row.comparator == "gte"
    assert row.unit == "rows"
    assert row.table_name is None


def test_declare_strips_and_nulls_blank_table_name() -> None:
    # "  " -> None (product-wide).  Kills `table_name and table_name.strip()`
    # -> `table_name or table_name.strip()`.
    dp = _seed_dp("crud", "blanktable")
    row = slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="volume", target_value=10.0, table_name="   "
    )
    assert row.table_name is None


def test_declare_strips_surrounding_whitespace() -> None:
    dp = _seed_dp("crud", "striptable")
    row = slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="volume", target_value=10.0, table_name="  t  "
    )
    assert row.table_name == "t"


def test_declare_unknown_product_raises() -> None:
    # Kills `session.get(...) is None` -> `is not None`.
    with pytest.raises(ValueError):
        slo_service.declare_slo(
            _factory(), data_product_id=999999, slo_kind="volume", target_value=10.0
        )


def test_declare_explicit_unit_overrides_default() -> None:
    dp = _seed_dp("crud", "unitoverride")
    row = slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        target_value=10.0,
        unit="custom_unit",
    )
    assert row.unit == "custom_unit"


# ===========================================================================
# scan_workspace — failing verdicts logged to audit
# ===========================================================================


def test_scan_logs_only_failing_verdicts() -> None:
    dp = _seed_dp("scan", "fail")
    _add_stats(dp, "t", row_count=5)
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        target_value=1000.0,
        table_name="t",
    )
    summary = slo_service.scan_workspace(_factory(), workspace_id=1)
    mine = [v for v in summary["violations"] if v.get("ref") == "scan.fail"]
    assert len(mine) == 1
    assert mine[0]["slo_kind"] == "volume"
    assert mine[0]["data_product_id"] == dp
    assert mine[0]["observed"] == 5.0
    with _factory()() as session:
        rows = session.scalars(
            select(AuditLog).where(
                AuditLog.action == SLO_VIOLATION_ACTION,
                AuditLog.target == "data_product:scan.fail",
            )
        ).all()
    assert len(rows) == 1


def test_scan_passing_product_logs_nothing() -> None:
    dp = _seed_dp("scan", "pass")
    _add_stats(dp, "t", row_count=1000)
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        target_value=10.0,
        table_name="t",
    )
    summary = slo_service.scan_workspace(_factory(), workspace_id=1)
    mine = [v for v in summary["violations"] if v.get("ref") == "scan.pass"]
    assert mine == []
