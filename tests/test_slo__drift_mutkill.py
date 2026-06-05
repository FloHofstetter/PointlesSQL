"""Behaviour tests targeting surviving mutants in ``slo._drift``.

Closes mutation gaps that the broad ``tests/test_slo_mutkill.py`` suite
leaves open: the ``_null_ratios`` ``and``/``or`` guard, the
``compute_drift`` SQL ``where``-clause scoping + ``limit`` window, the
exact-string metric keys, the ``< 2`` measured boundary, the null-ratio
loop's ``continue`` control flow + observed-value wiring, and the
``max_drift_sigma`` missing-``metrics``-key default.

Fixtures mirror ``tests/test_slo_mutkill.py``: the in-memory SQLite
engine wired by the autouse ``_auth_db`` conftest fixture through
``app.state.session_factory``.
"""

from __future__ import annotations

import datetime
import json

import pytest

from pointlessql.api.main import app
from pointlessql.models import DataProduct, DataProductStatistics
from pointlessql.services.slo._drift import (
    _null_ratios,
    compute_drift,
    max_drift_sigma,
)


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


def _seed_series(dp_id: int, table: str, counts: list[int]) -> None:
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    # counts[0] is the OLDEST; the latest (most-recent created_at) is last.
    for i, c in enumerate(counts):
        _add_stats(dp_id, table, row_count=c, when=base + datetime.timedelta(minutes=i))


# ===========================================================================
# _null_ratios — the column guard is a conjunction, not a disjunction
# ===========================================================================


def test_null_ratios_skips_non_int_null_count() -> None:
    # Kills `isinstance(col, dict) and isinstance(..., int)` -> `... or ...`:
    # with `or`, a dict column whose null_count is NOT an int still enters the
    # body and divides a non-numeric value, raising instead of returning {}.
    shape = json.dumps({"columns": {"a": {"null_count": "not-an-int"}}})
    assert _null_ratios(shape, 100) == {}


def test_null_ratios_includes_int_null_count() -> None:
    # The original conjunction admits genuine int null_counts.
    shape = json.dumps({"columns": {"a": {"null_count": 5}}})
    assert _null_ratios(shape, 100) == {"a": 0.05}


# ===========================================================================
# compute_drift — where-clause scoping (product + table)
# ===========================================================================


def test_drift_scoped_to_table_name() -> None:
    # Kills removal of the `table_name == table_name` where-clause: a sibling
    # table's diverging snapshots must not pollute table "t"'s baseline.
    dp = _seed_dp("driftscope", "table")
    _seed_series(dp, "t", [100, 100, 100, 100])  # frozen -> no drift
    # A noisy sibling table on the same product: if its rows leaked in, the
    # baseline mean/std and baseline_n would change.
    _seed_series(dp, "other", [1, 9999, 1, 9999])
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    assert drift["baseline_n"] == 3
    rc = next(m for m in drift["metrics"] if m["metric"] == "row_count")
    assert rc["mean"] == pytest.approx(100.0)
    assert rc["std"] == pytest.approx(0.0)


def test_drift_scoped_to_product_id() -> None:
    # Kills removal of the `data_product_id == data_product_id` where-clause:
    # another product's snapshots must not be read for this product.
    dp = _seed_dp("driftscope", "prod")
    other = _seed_dp("driftscope", "prodother")
    _seed_series(dp, "t", [50, 50, 50])  # baseline [50, 50], latest 50
    _seed_series(other, "t", [1, 2, 3, 4, 5])  # would inflate baseline_n / mean
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    assert drift["baseline_n"] == 2
    rc = next(m for m in drift["metrics"] if m["metric"] == "row_count")
    assert rc["mean"] == pytest.approx(50.0)


# ===========================================================================
# compute_drift — limit window (baseline_depth + 1)
# ===========================================================================


def test_drift_limit_is_baseline_depth_plus_one() -> None:
    # With baseline_depth=2 the query limit is 3, so of 5 snapshots only the
    # 3 most-recent are read -> baseline_n == 2.  Kills:
    #   .limit(baseline_depth + 1) -> baseline_depth - 1  (limit 1 -> unmeasured)
    #   .limit(baseline_depth + 1) -> baseline_depth + 2  (limit 4 -> baseline_n 3)
    #   .limit(baseline_depth + 1) -> .limit(None)        (no limit -> baseline_n 4)
    dp = _seed_dp("driftwin", "limit")
    _seed_series(dp, "t", [10, 20, 30, 40, 50])
    drift = compute_drift(
        _factory(), data_product_id=dp, table_name="t", sigma=2.0, baseline_depth=2
    )
    assert drift["measured"] is True
    assert drift["baseline_n"] == 2
    rc = next(m for m in drift["metrics"] if m["metric"] == "row_count")
    # Latest is 50; the two priors read are 40 and 30 -> mean 35.
    assert rc["observed"] == 50.0
    assert rc["mean"] == pytest.approx(35.0)


# ===========================================================================
# compute_drift — the measured boundary is `< 2` (exactly two -> measured)
# ===========================================================================


def test_drift_exactly_two_snapshots_is_measured() -> None:
    # Kills `len(snapshots) < 2` -> `<= 2` and -> `< 3`: with exactly two
    # snapshots (one baseline) the result must be measured, not the empty
    # unmeasured stub.
    dp = _seed_dp("driftbound", "two")
    _seed_series(dp, "t", [200, 100])  # baseline [200], latest 100
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    assert drift["measured"] is True
    assert drift["baseline_n"] == 1
    rc = next(m for m in drift["metrics"] if m["metric"] == "row_count")
    assert rc["observed"] == 100.0
    assert rc["mean"] == pytest.approx(200.0)


# ===========================================================================
# compute_drift — exact metric dict keys (std / z)
# ===========================================================================


def test_drift_metric_keys_are_exact() -> None:
    # Kills key mutations: "std" -> "XXstdXX"/"STD" and "z" -> "XXzXX"/"Z".
    dp = _seed_dp("driftkeys", "exact")
    _seed_series(dp, "t", [10, 20, 30, 28])
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    rc = next(m for m in drift["metrics"] if m["metric"] == "row_count")
    assert set(rc.keys()) == {"metric", "observed", "mean", "std", "z", "drifted"}
    assert "z" in rc
    assert "std" in rc


# ===========================================================================
# compute_drift — null-ratio loop: continue (not break) + observed wiring
# ===========================================================================


def test_drift_null_ratio_loop_continues_past_unmatched_column() -> None:
    # Column "a" appears only in the latest snapshot (no baseline series), so
    # its loop iteration hits the `if not series: continue`.  Kills
    # `continue` -> `break`: with break, the later column "b" (which DOES have
    # a baseline and drifts) would never produce its metric.
    dp = _seed_dp("driftloop", "continue")
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    # Three baseline snapshots: only column "b" present, all zero nulls.
    for i in range(3):
        shape = {"columns": {"b": {"null_count": 0}}}
        _add_stats(dp, "t", row_count=100, shape=shape, when=base + datetime.timedelta(minutes=i))
    # Latest: column "a" (unmatched, ordered first) then "b" (matched, drifts).
    latest_shape = {"columns": {"a": {"null_count": 10}, "b": {"null_count": 90}}}
    _add_stats(
        dp, "t", row_count=100, shape=latest_shape, when=base + datetime.timedelta(minutes=3)
    )
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    kinds = {m["metric"] for m in drift["metrics"]}
    assert "null_ratio:a" not in kinds  # no baseline -> skipped
    assert "null_ratio:b" in kinds  # reached only if the loop continued


def test_drift_null_ratio_observed_is_latest_value() -> None:
    # Kills `_z_score(observed, series)` -> `_z_score(None, series)`: the
    # null-ratio metric's z is computed from the real observed ratio, so a
    # divergent latest produces a finite z that flags drift.  With observed
    # forced to None the z computation would crash / not match.
    dp = _seed_dp("driftloop", "observed")
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    for i in range(3):
        shape = {"columns": {"a": {"null_count": 0}}}
        _add_stats(dp, "t", row_count=100, shape=shape, when=base + datetime.timedelta(minutes=i))
    latest_shape = {"columns": {"a": {"null_count": 80}}}
    _add_stats(
        dp, "t", row_count=100, shape=latest_shape, when=base + datetime.timedelta(minutes=3)
    )
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    nr = next(m for m in drift["metrics"] if m["metric"] == "null_ratio:a")
    assert nr["observed"] == pytest.approx(0.8)  # 80 / 100
    assert nr["mean"] == pytest.approx(0.0)
    assert nr["z"] == float("inf") or nr["z"] is None  # zero-variance baseline diverges
    assert nr["drifted"] is True


# ===========================================================================
# max_drift_sigma — default for a missing "metrics" key
# ===========================================================================


def test_max_drift_sigma_missing_metrics_key_returns_zero() -> None:
    # Kills `drift.get("metrics", [])` -> `.get("metrics", None)` /
    # `.get("metrics")`: with no "metrics" key the original iterates an empty
    # list and returns 0.0; the mutant would iterate None and raise TypeError.
    assert max_drift_sigma({}) == 0.0


# ===========================================================================
# compute_drift — the NULL-RATIO metric block specifically
#
# The earlier null-ratio coverage used a *zero-variance* baseline, which makes
# the z-score ``inf``.  Under ``inf`` several mutations on the null-ratio block
# are indistinguishable from the original (``inf > sigma`` == ``inf >= sigma``;
# ``_z_score(None, frozen)`` still returns ``inf``).  These tests use a
# *non-zero-variance* null-ratio baseline so the second metric builder's
# comparator, observed-argument wiring, and dict keys become observable.
# ===========================================================================


def _seed_null_series(
    dp_id: int, table: str, column: str, null_counts: list[int], row_count: int = 100
) -> None:
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    # null_counts[0] is the OLDEST; the latest (most-recent created_at) is last.
    for i, nc in enumerate(null_counts):
        shape = {"columns": {column: {"null_count": nc}}}
        _add_stats(
            dp_id,
            table,
            row_count=row_count,
            shape=shape,
            when=base + datetime.timedelta(minutes=i),
        )


def test_drift_null_ratio_threshold_is_strict_greater_not_geq() -> None:
    # The null-ratio metric's `drifted = z > sigma` must be STRICT.  Kills the
    # second-block `z > sigma` -> `z >= sigma` mutant, which the row_count
    # boundary test does not reach.
    #
    # Baseline null_counts [0, 0, 50, 50] at row_count 100 -> ratios
    # [0, 0, 0.5, 0.5]: mean 0.25, std 0.25.  Latest null_count 75 -> ratio
    # 0.75 -> z = |0.75 - 0.25| / 0.25 = 2.0 exactly == sigma.
    dp = _seed_dp("driftnull", "thresh")
    _seed_null_series(dp, "t", "a", [0, 0, 50, 50, 75])
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    nr = next(m for m in drift["metrics"] if m["metric"] == "null_ratio:a")
    assert nr["z"] == pytest.approx(2.0)
    assert nr["z"] == 2.0  # exact, so the comparator boundary is reachable
    assert nr["drifted"] is False  # z > sigma is False at equality; >= would be True
    assert drift["drifted"] is False


def test_drift_null_ratio_observed_is_wired_through_with_variable_baseline() -> None:
    # Kills the null-ratio `_z_score(observed, series)` -> `_z_score(None, series)`
    # mutant.  A NON-zero-variance baseline makes `_z_score(None, ...)` raise a
    # TypeError (None - float), so the mutant blows up inside compute_drift while
    # the original computes a finite z from the real observed ratio.
    #
    # Also pins the null-ratio metric's exact key set, killing the second-block
    # "std" -> "XXstdXX"/"STD" key mutations (the row_count key test does not
    # touch this dict).
    dp = _seed_dp("driftnull", "observed")
    # Baseline ratios [0.0, 0.1, 0.2] (non-zero variance); latest ratio 0.8.
    _seed_null_series(dp, "t", "a", [0, 10, 20, 80])
    drift = compute_drift(_factory(), data_product_id=dp, table_name="t", sigma=2.0)
    nr = next(m for m in drift["metrics"] if m["metric"] == "null_ratio:a")
    assert set(nr.keys()) == {"metric", "observed", "mean", "std", "z", "drifted"}
    assert nr["observed"] == pytest.approx(0.8)  # 80 / 100, not None
    assert nr["mean"] == pytest.approx(0.1)
    assert nr["std"] == pytest.approx(0.0816496580927726, rel=1e-9)
    assert nr["z"] == pytest.approx(8.573214099741124, rel=1e-9)
    assert nr["drifted"] is True
