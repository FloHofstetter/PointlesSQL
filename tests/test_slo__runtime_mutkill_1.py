"""Mutation-killing tests for ``pointlessql.services.slo._runtime``.

Pins the observable outputs of the four runtime SLO measurers and the
percentile interpolation helper: verdict comparators, the exact verdict
literals, the detail/reason dict keys and values, the snapshot/probe
query scoping + ordering + limiting, and the ``abs`` eq-tolerance
arithmetic.  Each test asserts a value that is true on the real code and
false under the corresponding mutant.

The fixtures mirror ``tests/test_slo_mutkill.py``: they drive the
in-memory SQLite engine wired by the autouse ``_auth_db`` conftest
fixture through ``app.state.session_factory``.
"""

from __future__ import annotations

import datetime
import json

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
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
    dp_id: int,
    durations: list[int],
    *,
    status: str = "ok",
    when: datetime.datetime | None = None,
) -> None:
    moment = when or datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        for d in durations:
            session.add(
                DataProductQueryPerfSample(
                    data_product_id=dp_id,
                    table_name="t",
                    started_at=moment,
                    duration_ms=d,
                    status=status,
                )
            )
        session.commit()


def _seed_precision(
    dp_id: int,
    table: str,
    null_ratio_max: float | None,
    *,
    when: datetime.datetime | None = None,
    shape: dict | None = None,
) -> None:
    created = when or datetime.datetime.now(datetime.UTC)
    if shape is None:
        shape = {} if null_ratio_max is None else {"null_ratio_max": null_ratio_max}
    with _factory()() as session:
        session.add(
            DataProductStatistics(
                data_product_id=dp_id,
                table_name=table,
                row_count=100,
                shape_json=json.dumps(shape),
                created_at=created,
            )
        )
        session.commit()


# ===========================================================================
# _percentile_sorted — the hi-index cap mutations
# ===========================================================================


def test_percentile_hi_index_is_lo_plus_one() -> None:
    # values [0, 10, 20, 30] at q=0.5 -> rank = 3*0.5 = 1.5 -> lo=1, hi=2,
    # frac 0.5 -> values[1]*0.5 + values[2]*0.5 = 10*0.5 + 20*0.5 = 15.0.
    # The `lo + 2` mutant would use values[3]=30 -> 10*0.5+30*0.5 = 20.0.
    assert runtime_slo._percentile_sorted([0.0, 10.0, 20.0, 30.0], 0.5) == pytest.approx(15.0)


def test_percentile_hi_index_cap_is_len_minus_one() -> None:
    # At the very top of the distribution the interpolation index is capped
    # at the last element.  q=1.0 on [0, 100] -> rank=1.0 -> lo=1, hi capped
    # at len-1 = 1, frac 0.0 -> values[1] = 100.0.  The `len + 1` cap mutant
    # would let hi exceed the list and raise IndexError instead.
    assert runtime_slo._percentile_sorted([0.0, 100.0], 1.0) == pytest.approx(100.0)


# ===========================================================================
# measure_availability — comparator literals, branch verdicts, eq tolerance
# ===========================================================================


def test_availability_lte_comparator_literal_and_boundary() -> None:
    # Routes through the `comparator == "lte"` branch; observed 75.0 with an
    # lte target of 75.0 must pass.  Kills the "lte" literal mutations (which
    # would skip this branch) and the `<=` -> `<` flip and `None`-verdict.
    dp = _seed_dp("avail", "lte_b")
    _seed_probes(dp, ok=3, fail=1)  # 75.0
    verdict, _ = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=75.0, comparator="lte"
    )
    assert verdict == "pass"


def test_availability_lte_over_target_fail_literal() -> None:
    # observed 75.0, lte target 50.0 -> fail.  Pins the lte-branch "fail"
    # literal and confirms the verdict is a non-None string.
    dp = _seed_dp("avail", "lte_f")
    _seed_probes(dp, ok=3, fail=1)  # 75.0
    verdict, _ = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=50.0, comparator="lte"
    )
    assert verdict == "fail"


def test_availability_eq_branch_pass_fail_and_tolerance() -> None:
    # observed 75.0.  eq target 75.0 -> within 0.001 -> pass; target 76.0 ->
    # |75-76| = 1.0 which is NOT < 0.001 -> fail.  Kills the eq-branch
    # `None`-verdict, the pass/fail literal mutations, the `observed -
    # target` -> `observed + target` flip, the `abs(None)` mutant, and the
    # `< 0.001` -> `< 1.001` tolerance widening (which would flip 76.0 to a
    # pass).
    dp = _seed_dp("avail", "eq")
    _seed_probes(dp, ok=3, fail=1)  # 75.0
    v_pass, _ = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=75.0, comparator="eq"
    )
    v_fail, _ = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=76.0, comparator="eq"
    )
    assert v_pass == "pass"
    assert v_fail == "fail"


def test_availability_eq_plus_flip_would_misverdict() -> None:
    # observed 50.0, eq target 50.0.  Original: |50-50| = 0 < 0.001 -> pass.
    # The `observed + target` mutant gives |100| -> fail.  This pins the
    # subtraction direction in the eq tolerance.
    dp = _seed_dp("avail", "eqplus")
    _seed_probes(dp, ok=1, fail=1)  # 50.0
    verdict, _ = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=50.0, comparator="eq"
    )
    assert verdict == "pass"


# ===========================================================================
# measure_availability — probed_at >= cutoff boundary
# ===========================================================================


def test_availability_probe_at_cutoff_boundary_is_included() -> None:
    # A probe whose timestamp sits effectively at the window edge must be
    # counted by the inclusive `probed_at >= cutoff` filter.  We seed a
    # single fresh probe; the `>=` -> `>` mutant only drops a probe sitting
    # exactly on the cutoff, so this guards the inclusive-window contract by
    # confirming the recent probe is present.
    dp = _seed_dp("avail", "cutoff")
    _seed_probes(dp, ok=2, fail=0, when=datetime.datetime.now(datetime.UTC))
    verdict, detail = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=50.0, window_days=7
    )
    assert detail["total_count"] == 2
    assert verdict == "pass"


# ===========================================================================
# measure_performance — scoping, reason dict, comparators, eq tolerance,
# ordering + limiting
# ===========================================================================


def test_performance_scoped_to_product() -> None:
    # A perf sample on another product must not be counted.  Kills the
    # removal of the `data_product_id == data_product_id` where-clause: with
    # the clause gone the other product's slow sample would inflate p95.
    dp = _seed_dp("perf", "scoped")
    other = _seed_dp("perf", "other")
    _seed_perf(dp, [10])
    _seed_perf(other, [9000, 9000, 9000])
    _verdict_, detail = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=100.0
    )
    assert detail["sample_count"] == 1
    assert detail["observed_p95_ms"] == pytest.approx(10.0)


def test_performance_no_samples_reason_dict_exact() -> None:
    # No perf samples -> ("unmeasured", {"reason": "no perf samples"}).
    # Kills the "reason" key and "no perf samples" value mutations.
    dp = _seed_dp("perf", "empty")
    verdict, detail = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=100.0
    )
    assert verdict == "unmeasured"
    assert detail == {"reason": "no perf samples"}


def test_performance_lte_boundary_equal_is_pass() -> None:
    # p95 of a single 100ms sample is 100.0; lte target 100.0 -> pass.
    # Kills the lte `<=` -> `<` flip.
    dp = _seed_dp("perf", "lte_b")
    _seed_perf(dp, [100])
    verdict, _ = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=100.0, comparator="lte"
    )
    assert verdict == "pass"


def test_performance_gte_branch_literal_and_boundary() -> None:
    # comparator "gte": p95 100.0, target 100.0 -> pass; target 200.0 ->
    # fail.  Kills the `elif comparator == "gte"` -> `!= "gte"` flip, the
    # "gte" literal mutations, the gte-branch `None`-verdict, the `>=` ->
    # `>` flip, and the gte pass/fail literal mutations.
    dp = _seed_dp("perf", "gte")
    _seed_perf(dp, [100])
    v_pass, _ = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=100.0, comparator="gte"
    )
    v_fail, _ = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=200.0, comparator="gte"
    )
    assert v_pass == "pass"
    assert v_fail == "fail"


def test_performance_eq_branch_tolerance_and_arithmetic() -> None:
    # comparator "eq": p95 100.0.  target 100.0 -> within 0.001 -> pass;
    # target 101.0 -> |100-101| = 1.0 not < 0.001 -> fail.  Kills the
    # eq-branch `None`-verdict, pass/fail literals, `abs(None)`, the
    # `p95 + target` flip, and the `< 0.001` -> `< 1.001` widening.
    dp = _seed_dp("perf", "eq")
    _seed_perf(dp, [100])
    v_pass, _ = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=100.0, comparator="eq"
    )
    v_fail, _ = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=101.0, comparator="eq"
    )
    assert v_pass == "pass"
    assert v_fail == "fail"


def test_performance_limit_truncates_to_sample_window() -> None:
    # With more samples than the window, only `sample_window` most-recent
    # rows are read.  Kills `.limit(sample_window)` -> `.limit(None)`:
    # dropping the limit would read all 4 rows (changing sample_count and
    # p95).  The most-recent two are both 10ms; the older two are 9000ms.
    dp = _seed_dp("perf", "limit")
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    _seed_perf(dp, [9000, 9000], when=base)
    _seed_perf(dp, [10, 10], when=base + datetime.timedelta(minutes=5))
    _verdict_, detail = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=100.0, sample_window=2
    )
    assert detail["sample_count"] == 2
    assert detail["observed_p95_ms"] == pytest.approx(10.0)


def test_performance_orders_by_started_at_desc() -> None:
    # The window keeps the most-recent samples (started_at desc).  Kills
    # `.order_by(...desc())` -> `.order_by(None)`: with no ordering the
    # limit would keep an arbitrary (insertion-order) set including the old
    # slow samples instead of the recent fast ones.
    dp = _seed_dp("perf", "order")
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    # Insert the SLOW samples first (oldest), then FAST samples (newest).
    _seed_perf(dp, [9000, 9000], when=base)
    _seed_perf(dp, [10, 10], when=base + datetime.timedelta(minutes=5))
    verdict, detail = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=100.0, sample_window=2
    )
    # Recent two are 10ms -> p95 10.0 -> pass under target 100.
    assert detail["observed_p95_ms"] == pytest.approx(10.0)
    assert verdict == "pass"


# ===========================================================================
# measure_precision_accuracy — table filter, ordering, reason dict,
# comparators, eq tolerance, except-handler payload
# ===========================================================================


def test_precision_table_filter_selects_matching_table() -> None:
    # Two snapshots: table "t" (newer, ratio 0.9) and table "u" (older,
    # ratio 0.02).  Asking for table "u" must read u's snapshot (0.02).
    # Kills `table_name == table_name` -> `!= table_name` (which would
    # select the OTHER table -> 0.9) and the `stmt.where(None)` mutant
    # (which yields no row -> "unmeasured").
    dp = _seed_dp("prec", "tablefilter")
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    _seed_precision(dp, "u", 0.02, when=base)
    _seed_precision(dp, "t", 0.9, when=base + datetime.timedelta(minutes=5))
    verdict, detail = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name="u", target_value=0.05
    )
    assert detail["observed"] == pytest.approx(0.02)
    assert verdict == "pass"


def test_precision_stmt_none_mutant_would_raise_not_return() -> None:
    # The table filter must keep the query executable.  With a snapshot
    # present and a table name set, the measurer returns a normal verdict
    # tuple.  The `stmt = None` mutant makes session.scalar(None) raise.
    dp = _seed_dp("prec", "stmtnone")
    _seed_precision(dp, "t", 0.02)
    verdict, detail = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name="t", target_value=0.05
    )
    assert verdict == "pass"
    assert detail["observed"] == pytest.approx(0.02)


def test_precision_orders_by_created_at_desc() -> None:
    # Two snapshots for the same table: older ratio 0.02, newer ratio 0.9.
    # The latest (0.9) must win, failing an lte target of 0.05.  Kills
    # `.order_by(created_at.desc())` -> `.order_by(None)` (which returns the
    # oldest insertion-order row -> 0.02 -> pass).
    dp = _seed_dp("prec", "order")
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    _seed_precision(dp, "t", 0.02, when=base)
    _seed_precision(dp, "t", 0.9, when=base + datetime.timedelta(minutes=5))
    verdict, detail = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name="t", target_value=0.05
    )
    assert detail["observed"] == pytest.approx(0.9)
    assert verdict == "fail"


def test_precision_no_snapshot_reason_dict_exact() -> None:
    # No snapshot -> ("unmeasured", {"reason": "no statistics snapshot"}).
    # Kills the "reason" key and "no statistics snapshot" value mutations.
    dp = _seed_dp("prec", "nosnap")
    verdict, detail = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name=None, target_value=0.05
    )
    assert verdict == "unmeasured"
    assert detail == {"reason": "no statistics snapshot"}


def test_precision_invalid_json_falls_back_to_empty_payload() -> None:
    # A snapshot whose shape_json is non-JSON text triggers the except
    # branch; payload must become {} so null_ratio defaults to 0.0 -> pass.
    # Kills `payload = {}` -> `payload = None` in the handler (None.get
    # would raise AttributeError instead of returning a verdict).
    dp = _seed_dp("prec", "badjson")
    with _factory()() as session:
        session.add(
            DataProductStatistics(
                data_product_id=dp,
                table_name="t",
                row_count=100,
                shape_json="not valid json",
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    verdict, detail = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name="t", target_value=0.05
    )
    assert detail["observed"] == 0.0
    assert verdict == "pass"


def test_precision_lte_boundary_equal_is_pass() -> None:
    # null_ratio 0.05, lte target 0.05 -> pass.  Kills the lte `<=` -> `<`.
    dp = _seed_dp("prec", "lte_b")
    _seed_precision(dp, "t", 0.05)
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name="t", target_value=0.05, comparator="lte"
    )
    assert verdict == "pass"


def test_precision_gte_branch_literal_and_boundary() -> None:
    # comparator "gte": ratio 0.05, target 0.05 -> pass; target 0.5 -> fail.
    # Kills the `elif comparator == "gte"` -> `!= "gte"` flip, the "gte"
    # literal mutations, the gte-branch `None`-verdict, the `>=` -> `>`
    # flip, and the gte pass/fail literal mutations.
    dp_a = _seed_dp("prec", "gte_pass")
    dp_b = _seed_dp("prec", "gte_fail")
    _seed_precision(dp_a, "t", 0.05)
    _seed_precision(dp_b, "t", 0.05)
    v_pass, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp_a, table_name="t", target_value=0.05, comparator="gte"
    )
    v_fail, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp_b, table_name="t", target_value=0.5, comparator="gte"
    )
    assert v_pass == "pass"
    assert v_fail == "fail"


def test_precision_eq_branch_none_verdict_mutant() -> None:
    # comparator "eq": ratio 0.05, target 0.05 -> within 0.001 -> pass.
    # Kills the eq-branch `verdict = None` mutant and the "pass" literal.
    dp = _seed_dp("prec", "eq")
    _seed_precision(dp, "t", 0.05)
    verdict, _ = runtime_slo.measure_precision_accuracy(
        _factory(), data_product_id=dp, table_name="t", target_value=0.05, comparator="eq"
    )
    assert verdict == "pass"


# ===========================================================================
# measure_availability — "lte" body literal must route to the lte branch, not
# fall through to the eq tolerance
# ===========================================================================


def test_availability_lte_literal_routes_to_lte_branch_not_eq() -> None:
    # observed 50.0 (1 ok / 1 fail), lte target 75.0 -> the lte branch gives
    # 50 <= 75 -> "pass".  The `"lte"` -> `"XXlteXX"` / `"LTE"` body-literal
    # mutants skip the lte branch; with comparator "lte" the gte branch is
    # also skipped, so control falls to the eq tolerance: |50 - 75| = 25 is
    # not < 0.001 -> "fail".  A below-target observation makes the lte verdict
    # diverge from the eq fall-through verdict, which a boundary/over-target
    # case cannot.
    dp = _seed_dp("avail", "lte_lit")
    _seed_probes(dp, ok=1, fail=1)  # 50.0
    verdict, _ = runtime_slo.measure_availability(
        _factory(), data_product_id=dp, target_value=75.0, comparator="lte"
    )
    assert verdict == "pass"


# ===========================================================================
# measure_performance — "gte" branch test/literal must route to the gte
# branch, not fall through to the eq tolerance
# ===========================================================================


def test_performance_gte_literal_routes_to_gte_branch_not_eq() -> None:
    # p95 100.0, comparator "gte", target 50.0 -> the gte branch gives
    # 100 >= 50 -> "pass".  The `== "gte"` -> `!= "gte"` flip and the
    # `"gte"` -> `"XXgteXX"` / `"GTE"` literal mutants all skip the gte
    # branch when comparator is "gte", dropping control to the eq tolerance:
    # |100 - 50| = 50 is not < 0.001 -> "fail".  An over-target observation
    # makes the gte verdict diverge from the eq fall-through, which the
    # round-1 boundary/under-target cases could not.
    dp = _seed_dp("perf", "gte_lit")
    _seed_perf(dp, [100])
    verdict, _ = runtime_slo.measure_performance(
        _factory(), data_product_id=dp, target_value=50.0, comparator="gte"
    )
    assert verdict == "pass"


# ===========================================================================
# measure_runtime_kind — error message + comparator pass-through
# ===========================================================================


def test_dispatch_unknown_kind_message_names_the_kind() -> None:
    # The dispatcher raises ValueError with a message that quotes the bad
    # kind.  Kills `raise ValueError(...)` -> `raise ValueError(None)`, which
    # still raises ValueError (so a bare `pytest.raises(ValueError)` cannot
    # see it) but carries the string "None" instead of the descriptive text.
    dp = _seed_dp("disp", "msg")
    with pytest.raises(ValueError) as excinfo:
        runtime_slo.measure_runtime_kind(
            _factory(),
            kind="totally_unknown",
            data_product_id=dp,
            target_value=0.0,
            comparator="lte",
        )
    message = str(excinfo.value)
    assert "unknown runtime kind" in message
    assert "totally_unknown" in message


def test_dispatch_availability_passes_comparator_through() -> None:
    # Dispatch availability with comparator "lte" and an observation below
    # target: the lte branch gives 50 <= 75 -> "pass".  Kills the dropped
    # `comparator=comparator` kwarg in the availability dispatch arm, which
    # would let measure_availability fall back to its default comparator
    # "gte" -> 50 >= 75 -> "fail".
    dp = _seed_dp("disp", "avail_cmp")
    _seed_probes(dp, ok=1, fail=1)  # 50.0
    verdict, detail = runtime_slo.measure_runtime_kind(
        _factory(),
        kind="availability",
        data_product_id=dp,
        target_value=75.0,
        comparator="lte",
    )
    assert verdict == "pass"
    assert detail["observed_percent"] == pytest.approx(50.0)
