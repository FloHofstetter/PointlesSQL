"""Mutation-killing tests for the interval-of-change SLO measurer.

Pins the observable arithmetic and branch behaviour of
``pointlessql.services.slo._interval_of_change``: the percentile
interpolation, the window-guard boundary, the SQL filter / ordering
that selects which write events feed the metric, the most-recent
timestamp surfaced as ``last_write_at``, and the verdict comparator /
exact-string logic.

The DB-backed tests drive the in-memory SQLite engine wired by the
autouse ``_auth_db`` conftest fixture through
``app.state.session_factory`` — the same pattern as
``tests/test_slo_mutkill.py``.
"""

from __future__ import annotations

import datetime
import uuid

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.services.slo._interval_of_change import (
    IntervalOfChangeMeasurement,
    _percentile_sorted,
    measure_interval_of_change,
    verdict_from_measurement,
)


def _factory():
    return app.state.session_factory


def _seed_dp(catalog: str, schema: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
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
            contract_json="{}",
            last_loaded_at=now,
            created_at=now,
        )
        session.add(row)
        session.commit()
        return row.id


def _seed_op() -> int:
    """Create one AgentRun + AgentRunOperation, return op_id."""
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


def _seed_events(
    dp_id: int,
    op_id: int,
    pairs: list[tuple[datetime.datetime, str]],
) -> None:
    """Insert one contract event per ``(created_at, outcome)`` pair, in order."""
    with _factory()() as session:
        for ts, outcome in pairs:
            session.add(
                DataProductContractEvent(
                    agent_run_operation_id=op_id,
                    data_product_id=dp_id,
                    outcome=outcome,
                    details_json="{}",
                    created_at=ts,
                )
            )
        session.commit()


def _measurement(median: float, p95: float = 0.0, n: int = 3) -> IntervalOfChangeMeasurement:
    return IntervalOfChangeMeasurement(
        median_minutes=median,
        p95_minutes=p95 or median,
        sample_size=n,
        last_write_at="2026-05-30T12:00:00+00:00",
    )


# ===========================================================================
# _percentile_sorted — interpolation arithmetic + boundaries
# ===========================================================================


def test_percentile_empty_returns_zero_not_one() -> None:
    # Kills `return 0.0` -> `return 1.0` on the empty-input guard.
    assert _percentile_sorted([], 0.5) == 0.0


def test_percentile_single_value_returns_it_unchanged() -> None:
    # Kills `len(values) == 1` -> `== 2`: with the mutant a one-element
    # list falls through to interpolation (still 7.0 here), but a TWO-element
    # list takes the early return and yields values[0] instead of interpolating.
    assert _percentile_sorted([7.0], 0.5) == 7.0
    # With two elements the `== 2` mutant short-circuits to values[0] = 0.0;
    # the original interpolates to 5.0.
    assert _percentile_sorted([0.0, 10.0], 0.5) == 5.0


def test_percentile_two_element_interpolation() -> None:
    # rank = 1*0.5 = 0.5 -> lo=0, hi=1, frac=0.5 -> 0*0.5 + 10*0.5 = 5.0.
    # Kills `hi = min(lo+1, ...)` -> `min(lo+2, ...)` (would clamp hi back to
    # lo=0 and return 0*0.5 + 0*0.5 = 0.0) and the `1 - frac` sign / op flips.
    assert _percentile_sorted([0.0, 10.0], 0.5) == 5.0


def test_percentile_hi_index_one_above_lo() -> None:
    # [0, 4, 10] q=0.5 -> rank 1.0 -> lo=1, hi=2, frac=0.0 -> values[1] = 4.0.
    # The `lo+2` mutant would set hi=min(3,2)=2 — same hi here — so use a frac>0
    # case to expose the wrong neighbour instead.
    # [0, 4, 10] q=0.25 -> rank 0.5 -> lo=0, hi=1, frac=0.5 -> 0*0.5 + 4*0.5 = 2.0.
    # `lo+2` mutant: hi=min(2,2)=2 -> 0*0.5 + 10*0.5 = 5.0 (wrong).
    assert _percentile_sorted([0.0, 4.0, 10.0], 0.25) == pytest.approx(2.0)


def test_percentile_full_quantile_uses_last_value() -> None:
    # q=1.0 -> rank = (n-1) -> lo = n-1, frac 0 -> returns the last value.
    # Kills `min(lo+1, len-1)` -> `min(lo+1, len+1)`: the mutant would pick
    # hi = len -> IndexError on the multi-element list.
    assert _percentile_sorted([1.0, 2.0, 3.0], 1.0) == 3.0


def test_percentile_lo_weight_is_multiplied_by_complement() -> None:
    # [4, 12] q=0.25 -> rank 0.25 -> lo=0, hi=1, frac=0.25.
    # original: 4*(1-0.25) + 12*0.25 = 3.0 + 3.0 = 6.0.
    # `* (1 - frac)` -> `/ (1 - frac)` mutant: 4/0.75 + 3 = 8.333... (wrong).
    # `(1 - frac)` -> `(1 + frac)` mutant: 4*1.25 + 3 = 8.0 (wrong).
    assert _percentile_sorted([4.0, 12.0], 0.25) == pytest.approx(6.0)


# ===========================================================================
# measure_interval_of_change — window guard, SQL filters, ordering, timestamps
# ===========================================================================


def test_window_two_is_allowed_not_rejected() -> None:
    # Kills `window < 2` -> `window <= 2` and `window < 3`: a window of
    # exactly 2 must be accepted (it is the minimum), not raise ValueError.
    dp = _seed_dp("ioc", "win2")
    op = _seed_op()
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    _seed_events(
        dp,
        op,
        [(base, "compliant"), (base + datetime.timedelta(minutes=10), "compliant")],
    )
    m = measure_interval_of_change(_factory(), data_product_id=dp, window=2)
    assert m is not None
    assert m.sample_size == 1
    assert m.median_minutes == pytest.approx(10.0)


def test_window_below_two_raises() -> None:
    with pytest.raises(ValueError):
        measure_interval_of_change(_factory(), data_product_id=1, window=1)


def test_only_write_outcomes_counted() -> None:
    # Kills removal of the `outcome.in_(WRITE_OUTCOMES)` filter: a "violated"
    # event sits between two writes; if it were counted the intervals (and so
    # the median) would change.  With it filtered out, two writes 60 min apart
    # give a single 60-minute interval.
    dp = _seed_dp("ioc", "outcome")
    op = _seed_op()
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    _seed_events(
        dp,
        op,
        [
            (base, "compliant"),
            (base + datetime.timedelta(minutes=30), "violated"),
            (base + datetime.timedelta(minutes=60), "compliant"),
        ],
    )
    m = measure_interval_of_change(_factory(), data_product_id=dp)
    assert m is not None
    assert m.sample_size == 1  # only the two writes -> one interval
    assert m.median_minutes == pytest.approx(60.0)


def test_scoped_to_data_product() -> None:
    # Kills removal of the `data_product_id == data_product_id` where-clause:
    # writes against a different product must not feed this product's metric.
    dp = _seed_dp("ioc", "scoped")
    other = _seed_dp("ioc", "other")
    op = _seed_op()
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    # this product: two writes 60 min apart
    _seed_events(
        dp,
        op,
        [(base, "compliant"), (base + datetime.timedelta(minutes=60), "compliant")],
    )
    # other product: many tightly-spaced writes that would skew the median down
    _seed_events(
        other,
        op,
        [(base + datetime.timedelta(minutes=i), "compliant") for i in range(0, 10)],
    )
    m = measure_interval_of_change(_factory(), data_product_id=dp)
    assert m is not None
    assert m.sample_size == 1
    assert m.median_minutes == pytest.approx(60.0)


def test_last_write_at_is_most_recent_timestamp() -> None:
    # Kills `last_write_at=timestamps[-1].isoformat()` -> `None`, `[+1]`, `[-2]`.
    # With three distinct timestamps the last index differs from index 1 and -2.
    dp = _seed_dp("ioc", "lastwrite")
    op = _seed_op()
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    ts = [
        base,
        base + datetime.timedelta(minutes=10),
        base + datetime.timedelta(minutes=45),
    ]
    _seed_events(dp, op, [(t, "compliant") for t in ts])
    m = measure_interval_of_change(_factory(), data_product_id=dp)
    assert m is not None
    # SQLite hands datetimes back naive; compare against the same shape the
    # code produces (the most-recent timestamp, ts[-1], not ts[1] or ts[-2]).
    assert m.last_write_at == ts[-1].replace(tzinfo=None).isoformat()
    assert m.last_write_at != ts[1].replace(tzinfo=None).isoformat()
    assert m.last_write_at != ts[-2].replace(tzinfo=None).isoformat()


def test_orders_by_created_at_desc_to_keep_most_recent_window() -> None:
    # Kills `.order_by(created_at.desc())` -> `.order_by(None)`.  With a window
    # smaller than the number of rows, the descending order makes the query keep
    # the MOST RECENT events; dropping the ORDER BY keeps insertion-order rows
    # (the oldest), changing which timestamp is the most recent write.
    dp = _seed_dp("ioc", "order")
    op = _seed_op()
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    # Insert oldest-first so rowid order == chronological order.
    ts = [base + datetime.timedelta(hours=h) for h in range(4)]
    _seed_events(dp, op, [(t, "compliant") for t in ts])
    m = measure_interval_of_change(_factory(), data_product_id=dp, window=2)
    assert m is not None
    # window=2 with desc() keeps the two newest events -> last_write_at = ts[-1].
    # The order_by(None) mutant keeps the two oldest -> ts[1], which differs.
    assert m.last_write_at == ts[-1].replace(tzinfo=None).isoformat()
    assert m.last_write_at != ts[1].replace(tzinfo=None).isoformat()


def test_returns_none_below_two_writes() -> None:
    dp = _seed_dp("ioc", "single")
    op = _seed_op()
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    _seed_events(dp, op, [(base, "compliant")])
    assert measure_interval_of_change(_factory(), data_product_id=dp) is None


# ===========================================================================
# verdict_from_measurement — comparator branches + exact strings
# ===========================================================================


def test_verdict_lte_boundary_equal_is_pass() -> None:
    # Kills `observed <= target` -> `observed < target`.
    verdict, _ = verdict_from_measurement(_measurement(60.0), target_value=60.0, comparator="lte")
    assert verdict == "pass"


def test_verdict_lte_over_target_is_fail() -> None:
    verdict, _ = verdict_from_measurement(_measurement(61.0), target_value=60.0, comparator="lte")
    assert verdict == "fail"


def test_verdict_gte_branch_selected_only_for_gte() -> None:
    # Kills `elif comparator == "gte"` -> `!= "gte"`, `"XXgteXX"`, `"GTE"`.
    # gte logic on observed 40 vs target 60: 40 >= 60 is False -> "fail".
    # If the branch were skipped (string mutants) it would fall to the eq
    # branch: abs(40-60) < 0.001 is False -> still "fail" — not distinguishing.
    # So choose observed where gte and eq disagree: observed 60, target 60 ->
    # gte: 60 >= 60 -> "pass"; eq: abs(0) < 0.001 -> "pass" — also same.
    # Use observed 80, target 60: gte -> "pass"; eq -> abs(20) -> "fail".
    verdict, _ = verdict_from_measurement(_measurement(80.0), target_value=60.0, comparator="gte")
    assert verdict == "pass"


def test_verdict_ne_gte_mutant_distinguished_by_eq_path() -> None:
    # Kills `elif comparator == "gte"` -> `elif comparator != "gte"`:
    # with comparator "eq" the original takes the else (eq) branch, but the
    # `!= "gte"` mutant takes the gte branch.  observed 80 vs target 60:
    # eq -> "fail" (abs 20 >= 0.001); gte -> "pass".  Original must be "fail".
    verdict, _ = verdict_from_measurement(_measurement(80.0), target_value=60.0, comparator="eq")
    assert verdict == "fail"


def test_verdict_gte_under_target_is_fail_exact_string() -> None:
    # Kills the gte branch `else "fail"` -> `"XXfailXX"` / `"FAIL"`.
    verdict, _ = verdict_from_measurement(_measurement(40.0), target_value=60.0, comparator="gte")
    assert verdict == "fail"


def test_verdict_eq_match_is_pass_exact_string() -> None:
    # Kills the eq branch verdict mutants: `verdict = None`, `"XXpassXX"`,
    # `"PASS"`, and `abs(None)` (which would raise).
    verdict, _ = verdict_from_measurement(_measurement(60.0), target_value=60.0, comparator="eq")
    assert verdict == "pass"


def test_verdict_eq_mismatch_is_fail_exact_string() -> None:
    # Kills the eq branch `else "fail"` -> `"XXfailXX"` / `"FAIL"`.
    verdict, _ = verdict_from_measurement(_measurement(70.0), target_value=60.0, comparator="eq")
    assert verdict == "fail"


def test_verdict_eq_subtraction_not_addition() -> None:
    # Kills `abs(observed - target)` -> `abs(observed + target)`.
    # observed 0.0005, target 0.0005: `-` -> 0.0 < 0.001 -> "pass";
    # `+` -> 0.001, and 0.001 < 0.001 is False -> "fail".
    verdict, _ = verdict_from_measurement(
        _measurement(0.0005), target_value=0.0005, comparator="eq"
    )
    assert verdict == "pass"


def test_verdict_eq_tolerance_is_strict_less_than() -> None:
    # Kills `< 0.001` -> `<= 0.001`: a diff of exactly the literal 0.001 must
    # be "fail" under strict `<`.  abs(0.001 - 0.0) is bit-for-bit the 0.001
    # literal, so `< 0.001` is False (fail) while `<= 0.001` would be "pass".
    verdict, _ = verdict_from_measurement(_measurement(0.001), target_value=0.0, comparator="eq")
    assert verdict == "fail"


def test_verdict_eq_tolerance_constant_is_thousandth() -> None:
    # Kills `< 0.001` -> `< 1.001`: a diff of 0.5 is outside the real
    # tolerance -> "fail" (the 1.001 mutant would call it "pass").
    verdict, _ = verdict_from_measurement(_measurement(60.5), target_value=60.0, comparator="eq")
    assert verdict == "fail"


def test_verdict_none_measurement_is_unmeasured() -> None:
    verdict, detail = verdict_from_measurement(None, target_value=60.0, comparator="lte")
    assert verdict == "unmeasured"
    assert detail == {"reason": "fewer than 2 write events"}
