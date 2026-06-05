"""Behaviour tests targeting surviving mutants in ``slo._evaluate``.

Pins the observable outputs of the SLO evaluator helpers and roll-up:
the completeness-percentage arithmetic, the per-kind measurement
(``_observe_measurable``) including table scoping and the
statistical-shape drift branch, and the ``evaluate_product`` result
shape / implicit-freshness branch / pass-rate maths.  Each assertion
is true on the real code and false on the corresponding mutant.

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
    DataProductInputPort,
    DataProductStatistics,
)
from pointlessql.services import slo as slo_service
from pointlessql.services.slo._evaluate import (
    _completeness_pct,
    _observe_measurable,
    evaluate_product,
)


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


def _read_stats(dp_id: int) -> list[dict]:
    from pointlessql.services.data_product_stats import read_latest_statistics

    return read_latest_statistics(_factory(), data_product_id=dp_id)


def _seed_drift_series(dp_id: int, table: str, counts: list[int]) -> None:
    base = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    for i, c in enumerate(counts):
        _add_stats(dp_id, table, row_count=c, when=base + datetime.timedelta(minutes=i))


# ===========================================================================
# _completeness_pct — saturation + structure + default mutants
# ===========================================================================


def test_completeness_full_returns_100() -> None:
    # All-non-null -> 100.0, not the clamped 1.0 (`max(0.0, ...)` -> `max(1.0, ...)`
    # is invisible here, but the returned 100.0 is the contract).
    entry = {
        "row_count": 10,
        "shape": {"columns": {"a": {"null_count": 0}, "b": {"null_count": 0}}},
    }
    assert _completeness_pct(entry) == 100.0


def test_completeness_partial_fraction_75() -> None:
    # 10 rows x 2 cols = 20 cells, 5 null -> 75.0.
    entry = {
        "row_count": 10,
        "shape": {"columns": {"a": {"null_count": 5}, "b": {"null_count": 0}}},
    }
    assert _completeness_pct(entry) == 75.0


def test_completeness_low_value_not_clamped_up_to_one() -> None:
    # A completeness percentage strictly between 0 and 1 must be returned
    # as-is.  Kills `max(0.0, ...)` -> `max(1.0, ...)`: 20 cells, 199 nulls
    # is impossible, so build a near-empty case: 200 cells, 199 nulls ->
    # (1 - 199/200) * 100 = 0.5, which the `max(1.0, ...)` mutant clamps up.
    entry = {
        "row_count": 100,
        "shape": {"columns": {"a": {"null_count": 199}, "b": {"null_count": 0}}},
    }
    assert _completeness_pct(entry) == pytest.approx(0.5)


def test_completeness_none_when_rows_present_but_no_columns() -> None:
    # Kills `not row_count or not columns` -> `... and ...`: rows present
    # but zero columns means total_cells would be 0; the `or` short-circuits
    # to None, the `and` mutant would fall through and divide by zero.
    assert _completeness_pct({"row_count": 10, "shape": {"columns": {}}}) is None


def test_completeness_none_when_zero_rows() -> None:
    assert _completeness_pct({"row_count": 0, "shape": {"columns": {"a": {}}}}) is None


def test_completeness_total_cells_one_is_not_special_cased() -> None:
    # 1 row x 1 col = 1 cell.  Kills `total_cells == 0` -> `total_cells == 1`:
    # the mutant would early-return None for this single-cell snapshot, but
    # the real code computes a real percentage.
    entry = {"row_count": 1, "shape": {"columns": {"a": {"null_count": 0}}}}
    assert _completeness_pct(entry) == 100.0


def test_completeness_missing_null_count_defaults_to_zero() -> None:
    # A column dict without a "null_count" key contributes 0 nulls.  Kills
    # `c.get("null_count", 0)` -> default `1` (would report 50% here) and
    # -> default `None` (would raise inside sum()).  2 cols, one with an
    # explicit 0 and one missing the key entirely; 2 cells, 0 nulls -> 100.
    entry = {
        "row_count": 1,
        "shape": {"columns": {"a": {"null_count": 0}, "b": {}}},
    }
    assert _completeness_pct(entry) == 100.0


# ===========================================================================
# _observe_measurable — scoping, min/max selection, statistical_shape branch
# ===========================================================================


def test_observe_volume_scopes_to_named_table() -> None:
    # Two tables: "big" has 100 rows, "small" has 5.  Volume scoped to
    # "big" must observe 100, NOT the cross-table minimum 5.  Kills
    # `_stats_for(stats, table_name)` -> `_stats_for(stats, None)`, which
    # would ignore scoping and pick min over all tables (5.0).
    dp = _seed_dp("obs", "scope")
    _add_stats(dp, "big", row_count=100)
    _add_stats(dp, "small", row_count=5)
    stats = _read_stats(dp)
    observed = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        table_name="big",
        stats=stats,
        has_inputs=False,
        sigma=2.0,
    )
    assert observed == 100.0


def test_observe_volume_takes_minimum_across_scoped_rows() -> None:
    # Product-wide volume (table_name=None) takes the minimum row_count.
    dp = _seed_dp("obs", "volmin")
    _add_stats(dp, "a", row_count=80)
    _add_stats(dp, "b", row_count=30)
    stats = _read_stats(dp)
    observed = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        table_name=None,
        stats=stats,
        has_inputs=False,
        sigma=2.0,
    )
    assert observed == 30.0


def test_observe_completeness_takes_minimum_pct() -> None:
    dp = _seed_dp("obs", "completemin")
    _add_stats(dp, "a", row_count=10, shape={"columns": {"c": {"null_count": 0}}})
    _add_stats(dp, "b", row_count=10, shape={"columns": {"c": {"null_count": 5}}})
    stats = _read_stats(dp)
    observed = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="completeness",
        table_name=None,
        stats=stats,
        has_inputs=False,
        sigma=2.0,
    )
    # b is 50% complete, a is 100% -> min 50.
    assert observed == pytest.approx(50.0)


def test_observe_lineage_true_false_branches() -> None:
    dp = _seed_dp("obs", "lineage")
    with_inputs = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="lineage",
        table_name=None,
        stats=[],
        has_inputs=True,
        sigma=2.0,
    )
    without = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="lineage",
        table_name=None,
        stats=[],
        has_inputs=False,
        sigma=2.0,
    )
    assert with_inputs == 100.0
    assert without == 0.0


def test_observe_statistical_shape_none_when_no_drift_baseline() -> None:
    # A single snapshot can't establish a drift baseline -> compute_drift
    # reports measured=False -> _observe_measurable must return None, NOT a
    # numeric worst.  Kills `measured = False` -> `measured = True` (which
    # would return worst=0.0) and `worst = 0.0` -> `worst = None`.
    dp = _seed_dp("obs", "shape_none")
    _add_stats(dp, "t", row_count=100)
    stats = _read_stats(dp)
    observed = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="statistical_shape",
        table_name="t",
        stats=stats,
        has_inputs=False,
        sigma=2.0,
    )
    assert observed is None


def test_observe_statistical_shape_stable_series_is_zero_not_clamped() -> None:
    # A perfectly stable row-count series drifts by sigma 0.0 on the latest
    # snapshot.  The observed worst must be 0.0 — kills `worst = 0.0` ->
    # `worst = 1.0` (which would inflate the stable observation to 1.0).
    dp = _seed_dp("obs", "shape_stable")
    _seed_drift_series(dp, "t", [100, 100, 100, 100])
    stats = _read_stats(dp)
    observed = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="statistical_shape",
        table_name="t",
        stats=stats,
        has_inputs=False,
        sigma=2.0,
    )
    assert observed == 0.0


def test_observe_statistical_shape_reports_drift_sigma() -> None:
    # A clear shift on the latest snapshot yields a large finite worst sigma.
    # The baseline has small non-zero variance so the z-score on the latest
    # value stays finite (a zero-variance baseline would yield inf -> None).
    dp = _seed_dp("obs", "shape_drift")
    _seed_drift_series(dp, "t", [100, 102, 98, 101, 99, 200])
    stats = _read_stats(dp)
    observed = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="statistical_shape",
        table_name="t",
        stats=stats,
        has_inputs=False,
        sigma=2.0,
    )
    assert observed is not None
    assert observed > 2.0


def test_observe_unknown_kind_returns_none() -> None:
    dp = _seed_dp("obs", "unknown")
    observed = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="not_a_kind",
        table_name=None,
        stats=[],
        has_inputs=True,
        sigma=2.0,
    )
    assert observed is None


# ===========================================================================
# evaluate_product — result-dict keys, implicit freshness, pass-rate maths
# ===========================================================================


def test_evaluate_implicit_freshness_result_keys_and_values() -> None:
    # The implicit-freshness result carries the exact literal keys/values:
    # comparator "lte", unit "minutes", source "implicit_freshness".  Kills
    # the XX/uppercase string mutants on those literals and the dict keys.
    dp = _seed_dp("eval", "implicit", sla_minutes=60)
    now = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    _add_stats(dp, "t", row_count=10, when=now)
    result = evaluate_product(_factory(), data_product_id=dp, now=now)
    fresh = next(r for r in result["results"] if r.get("source") == "implicit_freshness")
    assert fresh["comparator"] == "lte"
    assert fresh["unit"] == "minutes"
    assert fresh["slo_kind"] == "freshness"
    assert fresh["table"] is None
    assert fresh["target"] == 60.0
    assert fresh["measurable"] is True
    assert "observed" in fresh


def test_evaluate_implicit_freshness_uses_real_sigma_default() -> None:
    # The implicit-freshness lag is computed from stats freshness, and the
    # statistical-shape sigma default flows through evaluate_product.  Seed
    # a fresh snapshot at `now` -> lag 0 -> pass against a 60-minute SLA.
    dp = _seed_dp("eval", "freshlag", sla_minutes=60)
    now = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    _add_stats(dp, "t", row_count=10, when=now)
    result = evaluate_product(_factory(), data_product_id=dp, now=now)
    fresh = next(r for r in result["results"] if r.get("source") == "implicit_freshness")
    assert fresh["observed"] == 0.0
    assert fresh["verdict"] == "pass"


def test_evaluate_implicit_freshness_stale_fails() -> None:
    dp = _seed_dp("eval", "stale", sla_minutes=60)
    now = datetime.datetime(2026, 5, 30, 12, 0, tzinfo=datetime.UTC)
    old = now - datetime.timedelta(minutes=120)
    _add_stats(dp, "t", row_count=10, when=old)
    result = evaluate_product(_factory(), data_product_id=dp, now=now)
    fresh = next(r for r in result["results"] if r.get("source") == "implicit_freshness")
    assert fresh["observed"] == 120.0
    assert fresh["verdict"] == "fail"


def test_evaluate_implicit_freshness_suppressed_by_declared() -> None:
    # When an explicit freshness SLO is declared, the implicit one is NOT
    # appended.  Kills `not has_declared_freshness` condition flips.
    dp = _seed_dp("eval", "fresh_override", sla_minutes=60)
    _add_stats(dp, "t", row_count=10)
    slo_service.declare_slo(
        _factory(), data_product_id=dp, slo_kind="freshness", target_value=120.0
    )
    result = evaluate_product(_factory(), data_product_id=dp)
    sources = [r["source"] for r in result["results"] if r["slo_kind"] == "freshness"]
    assert sources == ["declared"]


def test_evaluate_no_implicit_freshness_without_sla() -> None:
    dp = _seed_dp("eval", "no_sla")
    _add_stats(dp, "t", row_count=10)
    result = evaluate_product(_factory(), data_product_id=dp)
    sources = [r.get("source") for r in result["results"]]
    assert "implicit_freshness" not in sources


def test_evaluate_result_dict_exact_keys() -> None:
    dp = _seed_dp("eval", "keys")
    _add_stats(dp, "t", row_count=100)
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        target_value=50.0,
        table_name="t",
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
    # One pass + one fail + one unmeasured -> scored = 2, pass_rate = 0.5.
    # Kills `scored = passed + failed` arithmetic flips and the division.
    dp = _seed_dp("eval", "rate")
    _add_stats(dp, "t", row_count=100, shape={"columns": {"a": {"null_count": 0}}})
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        target_value=50.0,
        table_name="t",
    )
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="completeness",
        target_value=999.0,
        table_name="t",
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


def test_evaluate_disabled_slo_skipped_without_breaking_loop() -> None:
    # A disabled SLO ordered before an enabled one ("completeness" <
    # "volume").  Kills `continue` -> `break`, which would drop the later
    # enabled volume SLO entirely.
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
    assert "completeness" not in kinds
    assert "volume" in kinds


def test_evaluate_has_inputs_flag_drives_lineage_verdict() -> None:
    # The product-level input-port probe feeds has_inputs through to the
    # lineage measurer.  Kills the `.limit(...)` / `is not None` probe
    # mutations indirectly: no inputs -> observe 0 -> fail.
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
# _observe_measurable statistical_shape — multi-table scoping branch
# ===========================================================================


def test_observe_shape_scoped_table_ignores_other_tables_drift() -> None:
    # Scope the statistical_shape observation to a single stable table "t"
    # while a SECOND table "other" in the same product is heavily drifting.
    # The scoped branch (`[table_name] if table_name is not None ...`) must
    # measure only "t" -> worst 0.0.  Kills the `table_name is not None`
    # -> `table_name is None` flip, which would fall through to the
    # all-tables comprehension and pick up "other"'s large sigma.
    dp = _seed_dp("obs", "shape_scope")
    _seed_drift_series(dp, "t", [100, 100, 100, 100])
    _seed_drift_series(dp, "other", [100, 102, 98, 101, 99, 200])
    stats = _read_stats(dp)
    observed = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="statistical_shape",
        table_name="t",
        stats=stats,
        has_inputs=False,
        sigma=2.0,
    )
    assert observed == 0.0


def test_observe_shape_product_wide_uses_stats_table_names() -> None:
    # Product-wide statistical_shape (table_name=None) derives the table
    # set from the stats entries' "table_name" field, then computes drift
    # per table from history.  A clearly drifting table -> a large finite
    # worst sigma.  Kills, at once:
    #   * `e["table_name"]` -> `e["XXtable_nameXX"]` / `e["TABLE_NAME"]`
    #     (KeyError when building the table list -> the call would raise),
    #   * `e.get("table_name")` -> `e.get(None)` / `e.get("XXtable_nameXX")`
    #     / `e.get("TABLE_NAME")` (filter always false -> empty table set ->
    #     nothing measured -> None instead of the real sigma).
    dp = _seed_dp("obs", "shape_pw")
    _seed_drift_series(dp, "t", [100, 102, 98, 101, 99, 200])
    stats = _read_stats(dp)
    observed = _observe_measurable(
        _factory(),
        data_product_id=dp,
        slo_kind="statistical_shape",
        table_name=None,
        stats=stats,
        has_inputs=False,
        sigma=2.0,
    )
    assert observed is not None
    assert observed > 2.0


# ===========================================================================
# evaluate_product — declared-SLO table scoping flows to the measurer
# ===========================================================================


def test_evaluate_declared_volume_scopes_to_its_table() -> None:
    # A declared volume SLO scoped to table "big" must observe ONLY "big"'s
    # row count (100), not the cross-table minimum (5 from "small").  Kills
    # `table_name=slo.table_name` -> `table_name=None` at the
    # _observe_measurable call site: the None mutant would observe min(5,100)
    # = 5 across all tables, flipping the gte-50 verdict from pass to fail.
    dp = _seed_dp("eval", "scoped_vol")
    _add_stats(dp, "big", row_count=100)
    _add_stats(dp, "small", row_count=5)
    slo_service.declare_slo(
        _factory(),
        data_product_id=dp,
        slo_kind="volume",
        target_value=50.0,
        table_name="big",
        comparator="gte",
    )
    result = evaluate_product(_factory(), data_product_id=dp)
    vol = next(r for r in result["results"] if r["slo_kind"] == "volume")
    assert vol["table"] == "big"
    assert vol["observed"] == 100.0
    assert vol["verdict"] == "pass"
