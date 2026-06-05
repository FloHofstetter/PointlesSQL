"""Behaviour tests targeting surviving mutants in the SLO runtime layer.

This is the second of two complementary suites for
``pointlessql.services.slo._runtime``.  It pins:

* the ``eq`` comparator branch of :func:`measure_precision_accuracy`
  (verdict strings + the ``abs(observed - target) < 0.001`` arithmetic
  and threshold),
* the literal detail-dict keys / values and the ``or``-guard of
  :func:`measure_timeliness`,
* the full keyword wiring of :func:`measure_runtime_kind` — each kind's
  branch literal, the per-kind ``spec.get(...)`` lookups, and the
  ``target_value`` / ``comparator`` / ``window_days`` / ``sample_window``
  pass-through.

The fixtures mirror ``tests/test_slo_mutkill.py``: the in-memory SQLite
engine wired by the autouse ``_auth_db`` conftest fixture through
``app.state.session_factory``.
"""

from __future__ import annotations

import datetime
import json

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProductAvailabilityProbe,
    DataProductQueryPerfSample,
    DataProductStatistics,
)
from pointlessql.services.slo import _runtime as runtime_slo


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
    contract = {
        "name": f"{catalog}.{schema}",
        "version": "1.0.0",
        "description": "",
        "catalog": catalog,
        "schema_name": schema,
        "tables": [],
    }
    from pointlessql.models import DataProduct

    with _factory()() as session:
        row = DataProduct(
            workspace_id=1,
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


def _seed_precision_stats(
    dp_id: int, table: str, null_ratio_max: float, *, payload: dict | None = None
) -> None:
    shape = payload if payload is not None else {"null_ratio_max": null_ratio_max}
    with _factory()() as session:
        session.add(
            DataProductStatistics(
                data_product_id=dp_id,
                table_name=table,
                row_count=100,
                shape_json=json.dumps(shape),
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()


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


def _seed_perf(
    dp_id: int, durations: list[float], *, base: datetime.datetime | None = None
) -> None:
    """Seed ok perf samples; later list items get more-recent started_at."""
    start = base or datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    with _factory()() as session:
        for i, d in enumerate(durations):
            session.add(
                DataProductQueryPerfSample(
                    data_product_id=dp_id,
                    table_name="t",
                    started_at=start + datetime.timedelta(seconds=i),
                    duration_ms=d,
                    status="ok",
                )
            )
        session.commit()


# ===========================================================================
# measure_precision_accuracy — the eq-comparator branch
# ===========================================================================


def test_precision_eq_match_within_tolerance_is_pass() -> None:
    # observed == target exactly -> abs diff 0 < 0.001 -> "pass".
    # Kills "pass" -> "PASS"/"XXpassXX" on the eq branch.
    dp = _seed_dp("preceq", "match")
    _seed_precision_stats(dp, "t", 0.5)
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name=None, target_value=0.5, comparator="eq"
    )
    assert verdict == "pass"


def test_precision_eq_mismatch_is_fail_exact_string() -> None:
    # observed far from target -> "fail".  Kills "fail" -> "FAIL"/"XXfailXX"
    # on the eq branch, and the abs/threshold mutants that would mis-pass.
    dp = _seed_dp("preceq", "miss")
    _seed_precision_stats(dp, "t", 0.9)
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name=None, target_value=0.1, comparator="eq"
    )
    assert verdict == "fail"


def test_precision_eq_uses_subtraction_not_addition() -> None:
    # observed 0.4, target 0.4: abs(0.4 - 0.4) = 0 < 0.001 -> pass.
    # The `+` mutant computes abs(0.4 + 0.4) = 0.8 >= 0.001 -> fail.
    dp = _seed_dp("preceq", "sub")
    _seed_precision_stats(dp, "t", 0.4)
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name=None, target_value=0.4, comparator="eq"
    )
    assert verdict == "pass"


def test_precision_eq_not_abs_of_none() -> None:
    # abs(None) raises; the original computes abs(observed - target).
    # A clean verdict here proves the subtraction expression is intact.
    dp = _seed_dp("preceq", "noneabs")
    _seed_precision_stats(dp, "t", 0.2)
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name=None, target_value=0.2, comparator="eq"
    )
    assert verdict == "pass"


def test_precision_eq_threshold_strict_less_not_leq() -> None:
    # abs diff exactly equals the 0.001 literal: stored null_ratio 0.001,
    # target 0.0 -> abs(0.001 - 0.0) == 0.001.  `< 0.001` is False -> fail;
    # the `<= 0.001` mutant flips to pass.
    dp = _seed_dp("preceq", "thresh")
    _seed_precision_stats(dp, "t", 0.001)
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name=None, target_value=0.0, comparator="eq"
    )
    assert verdict == "fail"


def test_precision_eq_threshold_is_thousandth_not_unit() -> None:
    # abs diff 0.5 is >= 0.001 -> fail, but < 1.001 would pass.  Kills the
    # `< 0.001` -> `< 1.001` threshold-constant mutant.
    dp = _seed_dp("preceq", "unit")
    _seed_precision_stats(dp, "t", 0.5)
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name=None, target_value=0.0, comparator="eq"
    )
    assert verdict == "fail"


# ===========================================================================
# measure_timeliness — guard + detail-dict literals
# ===========================================================================


def test_timeliness_one_missing_col_requires_policy() -> None:
    # event present, processing missing -> "bitemporal policy required".
    # Kills `not event or not processing` -> `... and ...`: the `and`
    # mutant would fall through to the wired-detail branch instead.
    verdict, detail = runtime_slo.measure_timeliness(
        _factory(),
        data_product_id=1,
        event_time_col="evt",
        processing_time_col=None,
        target_value=5.0,
    )
    assert verdict == "unmeasured"
    assert detail == {"reason": "bitemporal policy required"}


def test_timeliness_policy_required_dict_exact() -> None:
    # Kills key/value case mutants on the bitemporal-required detail dict.
    _verdict, detail = runtime_slo.measure_timeliness(
        _factory(),
        data_product_id=1,
        event_time_col=None,
        processing_time_col=None,
        target_value=5.0,
    )
    assert detail == {"reason": "bitemporal policy required"}
    assert list(detail.keys()) == ["reason"]
    assert detail["reason"] == "bitemporal policy required"


def test_timeliness_wired_detail_dict_exact_keys_and_values() -> None:
    # Both columns present -> the wired-detail branch.  Kills every key
    # case mutant ("reason"/"processing_time_col"/"target_value"/
    # "comparator") and the reason-string case mutants.
    verdict, detail = runtime_slo.measure_timeliness(
        _factory(),
        data_product_id=1,
        event_time_col="evt",
        processing_time_col="proc",
        target_value=7.5,
        comparator="gte",
    )
    assert verdict == "unmeasured"
    assert detail == {
        "reason": "engine-side measurement not wired in this revision",
        "event_time_col": "evt",
        "processing_time_col": "proc",
        "target_value": 7.5,
        "comparator": "gte",
    }
    assert set(detail.keys()) == {
        "reason",
        "event_time_col",
        "processing_time_col",
        "target_value",
        "comparator",
    }


# ===========================================================================
# measure_runtime_kind — branch literals per kind
# ===========================================================================


def test_dispatch_timeliness_branch_literal() -> None:
    # kind="timeliness" must route to measure_timeliness (unmeasured with a
    # bitemporal "reason").  Kills the branch-literal case mutants that
    # would mis-route to measure_performance ("no perf samples").
    dp = _seed_dp("disp", "tl")
    verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="timeliness",
        data_product_id=dp,
        target_value=5.0,
        comparator="lte",
        spec={"event_time_col": "evt", "processing_time_col": "proc"},
    )
    assert verdict == "unmeasured"
    assert detail["reason"] == "engine-side measurement not wired in this revision"


def test_dispatch_precision_accuracy_branch_literal() -> None:
    # kind="precision_accuracy" routes to the precision measurer (observed
    # null ratio), not the performance fallback.  Kills the branch literal.
    dp = _seed_dp("disp", "pa")
    _seed_precision_stats(dp, "t", 0.02)
    verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="precision_accuracy",
        data_product_id=dp,
        target_value=0.05,
        comparator="lte",
    )
    assert verdict == "pass"
    assert detail["observed"] == pytest.approx(0.02)


def test_dispatch_availability_branch_literal() -> None:
    # kind="availability" routes to the availability measurer (observed
    # percent), not the performance fallback.  Kills the branch literal.
    dp = _seed_dp("disp", "av")
    _seed_probes(dp, ok=3, fail=1)
    verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="availability",
        data_product_id=dp,
        target_value=70.0,
        comparator="gte",
    )
    assert verdict == "pass"
    assert detail["observed_percent"] == pytest.approx(75.0)


# ===========================================================================
# measure_runtime_kind — timeliness keyword wiring from spec
# ===========================================================================


def test_dispatch_timeliness_passes_event_time_col_from_spec() -> None:
    # spec["event_time_col"] must reach measure_timeliness.  Kills
    # event_time_col=None / spec.get(<wrong-key>) mutants: dropping the
    # event column flips the verdict-detail to "bitemporal policy required".
    dp = _seed_dp("disp", "tlevt")
    _verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="timeliness",
        data_product_id=dp,
        target_value=5.0,
        comparator="lte",
        spec={"event_time_col": "evt", "processing_time_col": "proc"},
    )
    assert detail["event_time_col"] == "evt"
    assert detail["reason"] == "engine-side measurement not wired in this revision"


def test_dispatch_timeliness_passes_processing_time_col_from_spec() -> None:
    # spec["processing_time_col"] must reach the measurer.  Kills
    # processing_time_col=None / wrong-key mutants.
    dp = _seed_dp("disp", "tlproc")
    _verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="timeliness",
        data_product_id=dp,
        target_value=5.0,
        comparator="lte",
        spec={"event_time_col": "evt", "processing_time_col": "proc"},
    )
    assert detail["processing_time_col"] == "proc"
    assert detail["reason"] == "engine-side measurement not wired in this revision"


def test_dispatch_timeliness_passes_target_and_comparator() -> None:
    # target_value/comparator must flow through verbatim.  Kills
    # target_value=None, comparator=None, and the dropped-comparator
    # mutant (with a non-default comparator the drop would surface "lte").
    dp = _seed_dp("disp", "tltc")
    _verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="timeliness",
        data_product_id=dp,
        target_value=9.0,
        comparator="gte",
        spec={"event_time_col": "evt", "processing_time_col": "proc"},
    )
    assert detail["target_value"] == 9.0
    assert detail["comparator"] == "gte"


# ===========================================================================
# measure_runtime_kind — precision_accuracy keyword wiring from spec
# ===========================================================================


def test_dispatch_precision_table_name_from_spec_scopes_lookup() -> None:
    # spec["table_name"] must scope the snapshot lookup.  Only a snapshot
    # for a *different* table exists; with the correct table filter the
    # measurer finds nothing -> "unmeasured".  Kills table_name=None /
    # wrong-key mutants (which would drop the filter and find the row).
    dp = _seed_dp("disp", "patbl")
    _seed_precision_stats(dp, "other_table", 0.02)
    verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="precision_accuracy",
        data_product_id=dp,
        target_value=0.05,
        comparator="lte",
        spec={"table_name": "wanted_table"},
    )
    assert verdict == "unmeasured"
    assert detail == {"reason": "no statistics snapshot"}


def test_dispatch_precision_data_product_id_scopes_lookup() -> None:
    # data_product_id must scope the lookup.  Stats live under dp; the
    # data_product_id=None mutant queries for a NULL product -> no row ->
    # "unmeasured" instead of the real pass.
    dp = _seed_dp("disp", "padpid")
    _seed_precision_stats(dp, "t", 0.02)
    verdict, _ = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="precision_accuracy",
        data_product_id=dp,
        target_value=0.05,
        comparator="lte",
    )
    assert verdict == "pass"


def test_dispatch_precision_passes_target_and_comparator() -> None:
    # target_value/comparator must flow through.  Kills target_value=None,
    # comparator=None, and the dropped-comparator mutant: with comparator
    # "gte" and observed 0.9 vs target 0.5 -> pass; the "lte" fallback
    # (or eq) would flip to fail.
    dp = _seed_dp("disp", "patc")
    _seed_precision_stats(dp, "t", 0.9)
    verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="precision_accuracy",
        data_product_id=dp,
        target_value=0.5,
        comparator="gte",
    )
    assert verdict == "pass"
    assert detail["target"] == pytest.approx(0.5)
    assert detail["comparator"] == "gte"


# ===========================================================================
# measure_runtime_kind — availability keyword wiring from spec
# ===========================================================================


def test_dispatch_availability_data_product_id_scopes_lookup() -> None:
    # data_product_id=None mutant would query a NULL product -> no probes
    # -> "unmeasured" instead of the real verdict.
    dp = _seed_dp("disp", "avdpid")
    _seed_probes(dp, ok=3, fail=1)
    verdict, _ = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="availability",
        data_product_id=dp,
        target_value=70.0,
        comparator="gte",
    )
    assert verdict == "pass"


def test_dispatch_availability_passes_target_and_comparator() -> None:
    # target_value/comparator must flow through.  observed 75 vs target 90
    # under gte -> fail; the comparator=None (eq) or target=None mutant
    # would not produce this clean fail.
    dp = _seed_dp("disp", "avtc")
    _seed_probes(dp, ok=3, fail=1)  # 75.0
    verdict, _ = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="availability",
        data_product_id=dp,
        target_value=90.0,
        comparator="gte",
    )
    assert verdict == "fail"


def test_dispatch_availability_window_days_from_spec() -> None:
    # spec["window_days"]=30 must reach the measurer: a 14-day-old probe
    # is then in-window and counted.  Kills the mutants that fall back to
    # 7 / 8 (which would exclude the old probe and change total_count and
    # the reflected window_days).
    dp = _seed_dp("disp", "avwin")
    now = datetime.datetime.now(datetime.UTC)
    _seed_probes(dp, ok=1, fail=0, when=now)
    _seed_probes(dp, ok=1, fail=0, when=now - datetime.timedelta(days=14))
    _verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="availability",
        data_product_id=dp,
        target_value=50.0,
        comparator="gte",
        spec={"window_days": 30},
    )
    assert detail["window_days"] == 30
    assert detail["total_count"] == 2


def test_dispatch_availability_window_days_defaults_to_seven() -> None:
    # With no spec window_days the default is 7 (NOT 8).  Kills the
    # `spec.get("window_days", 8)` default-constant mutant via the
    # reflected window_days.
    dp = _seed_dp("disp", "avwin7")
    _seed_probes(dp, ok=1, fail=0)
    _verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="availability",
        data_product_id=dp,
        target_value=50.0,
        comparator="gte",
    )
    assert detail["window_days"] == 7


# ===========================================================================
# measure_runtime_kind — performance keyword wiring from spec
# ===========================================================================


def test_dispatch_performance_sample_window_from_spec_limits_rows() -> None:
    # spec["sample_window"]=1 must reach the measurer: only the single most
    # recent ok sample is considered.  Kills the mutants that ignore the
    # spec value (fall back to 100 / drop the kwarg / use a wrong key),
    # which would include all samples and change sample_count + p95.
    dp = _seed_dp("disp", "perfwin")
    # Oldest -> newest.  With window 1 only the last (10ms) counts.
    _seed_perf(dp, [9000.0, 9000.0, 10.0])
    verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="performance",
        data_product_id=dp,
        target_value=1000.0,
        comparator="lte",
        spec={"sample_window": 1},
    )
    assert detail["sample_count"] == 1
    assert detail["observed_p95_ms"] == pytest.approx(10.0)
    assert verdict == "pass"


def test_dispatch_performance_passes_comparator() -> None:
    # comparator must flow through.  p95 ~10ms vs target 1000 under gte ->
    # fail; the dropped-comparator "lte" fallback would flip to pass.
    dp = _seed_dp("disp", "perfcmp")
    _seed_perf(dp, [10.0, 10.0, 10.0])
    verdict, _ = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="performance",
        data_product_id=dp,
        target_value=1000.0,
        comparator="gte",
    )
    assert verdict == "fail"


def test_dispatch_performance_sample_window_default_caps_at_hundred() -> None:
    # With no spec the window default is 100.  Seed 101 ok samples where
    # the single oldest is a huge outlier: with the 100-cap that oldest is
    # excluded (p95 small), but the `sample_window=None` mutant removes the
    # limit, pulls all 101, and the outlier inflates p95.
    dp = _seed_dp("disp", "perfcap")
    durations = [500000.0] + [10.0] * 100  # index 0 is the oldest sample
    _seed_perf(dp, durations)
    _verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="performance",
        data_product_id=dp,
        target_value=1000.0,
        comparator="lte",
    )
    assert detail["sample_count"] == 100
    assert detail["observed_p95_ms"] == pytest.approx(10.0)
