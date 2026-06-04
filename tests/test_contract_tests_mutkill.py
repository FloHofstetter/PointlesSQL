"""Behaviour tests that pin observable contract-test outputs.

These tests assert exact return values, persisted DB rows, raised
error types, and audit-detail payloads for the contract-test
subsystem so that small mutations to status strings, dict keys,
default arguments, and branch conditions become observable failures.
"""

from __future__ import annotations

import datetime
import json

import pyarrow as pa
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    AuditLog,
    DataProduct,
    DataProductContractTest,
    DataProductContractTestResult,
    DataProductFixture,
)
from pointlessql.services.contract_tests import (
    declare_contract_test,
    declare_fixture,
    evaluate_assertion,
    generate_arrow_table,
    list_fixtures,
    run_contract_tests,
)

# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _table(**columns: list) -> pa.Table:
    return pa.table(columns)


def _seed_dp(catalog: str, schema: str) -> int:
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
            version="1.0.0",
            description="",
            sla_minutes=None,
            contract_yaml_hash="0" * 64,
            contract_json=json.dumps(contract),
            last_loaded_at=_now(),
            created_at=_now(),
        )
        session.add(row)
        session.commit()
        return int(row.id)


@pytest.fixture(autouse=True)
def _wipe_contract_tables():
    with _factory()() as session:
        session.query(DataProductContractTestResult).delete()
        session.query(DataProductContractTest).delete()
        session.query(DataProductFixture).delete()
        session.query(DataProduct).delete()
        session.query(AuditLog).delete()
        session.commit()
    yield


# ---------------------------------------------------------------------------
# _assert_null_rate
# ---------------------------------------------------------------------------


def test_null_rate_default_max_rate_is_zero() -> None:
    # With no ``max_rate`` in the spec the default must be 0.0, so any
    # null makes the assertion fail.  A default of 1.0 would pass.
    verdict = evaluate_assertion(
        assertion_kind="null_rate",
        spec_json={"column": "x"},
        table=_table(x=[1, None]),
    )
    assert verdict.status == "fail"
    assert verdict.observation["observed_rate"] == 0.5
    assert verdict.observation["max_rate"] == 0.0


def test_null_rate_missing_column_returns_error_status() -> None:
    verdict = evaluate_assertion(
        assertion_kind="null_rate",
        spec_json={"column": "nope", "max_rate": 0.0},
        table=_table(x=[1, 2]),
    )
    assert verdict.status == "error"
    assert verdict.observation == {"reason": "column 'nope' not in table"}


def test_null_rate_requires_column_message() -> None:
    with pytest.raises(ValueError, match="null_rate requires 'column'"):
        evaluate_assertion(
            assertion_kind="null_rate",
            spec_json={"max_rate": 0.1},
            table=_table(x=[1]),
        )


def test_null_rate_empty_table_passes_with_zero_rows() -> None:
    # Empty column short-circuits to pass with rows=0; a == 1 guard on
    # the row-count branch would mis-handle the single-row case below.
    verdict = evaluate_assertion(
        assertion_kind="null_rate",
        spec_json={"column": "x", "max_rate": 0.0},
        table=_table(x=pa.array([], type=pa.int64())),
    )
    assert verdict.status == "pass"
    assert verdict.observation == {
        "column": "x",
        "observed_rate": 0.0,
        "rows": 0,
    }


def test_null_rate_single_null_row_fails() -> None:
    # One null row out of one => rate 1.0 > 0.0 => fail.  If the empty
    # guard fired on a 1-row table this would wrongly report pass/0.
    verdict = evaluate_assertion(
        assertion_kind="null_rate",
        spec_json={"column": "x", "max_rate": 0.0},
        table=_table(x=pa.array([None], type=pa.int64())),
    )
    assert verdict.status == "fail"
    assert verdict.observation["observed_rate"] == 1.0
    assert verdict.observation["rows"] == 1


# ---------------------------------------------------------------------------
# _assert_freshness
# ---------------------------------------------------------------------------


def test_freshness_reads_max_lag_minutes_key() -> None:
    # A timestamp ~30 min old fails against a 10-min lag budget but
    # passes against the 60-min default.  If the asserter ignored the
    # ``max_lag_minutes`` key it would use 60 and wrongly pass.
    stale = (_now() - datetime.timedelta(minutes=30)).isoformat()
    verdict = evaluate_assertion(
        assertion_kind="freshness",
        spec_json={"timestamp_column": "ts", "max_lag_minutes": 10},
        table=_table(ts=[stale]),
    )
    assert verdict.status == "fail"
    assert verdict.observation["max_lag_minutes"] == 10.0


def test_freshness_missing_column_returns_error() -> None:
    verdict = evaluate_assertion(
        assertion_kind="freshness",
        spec_json={"timestamp_column": "nope"},
        table=_table(ts=[_now().isoformat()]),
    )
    assert verdict.status == "error"
    assert verdict.observation == {"reason": "column 'nope' not in table"}


def test_freshness_all_null_timestamps_fails() -> None:
    verdict = evaluate_assertion(
        assertion_kind="freshness",
        spec_json={"timestamp_column": "ts"},
        table=_table(ts=pa.array([None, None], type=pa.string())),
    )
    assert verdict.status == "fail"
    assert verdict.observation == {"reason": "no non-null timestamps"}


def test_freshness_unparseable_timestamps_error() -> None:
    verdict = evaluate_assertion(
        assertion_kind="freshness",
        spec_json={"timestamp_column": "ts"},
        table=_table(ts=["not-a-date", "also-bad"]),
    )
    assert verdict.status == "error"
    assert verdict.observation == {"reason": "no parseable ISO-8601 timestamps"}


def test_freshness_requires_timestamp_column_message() -> None:
    with pytest.raises(ValueError, match="freshness requires 'timestamp_column'"):
        evaluate_assertion(
            assertion_kind="freshness",
            spec_json={},
            table=_table(ts=["x"]),
        )


def test_freshness_lag_minutes_uses_sixty_second_divisor() -> None:
    # 120 minutes old; lag_minutes must be ~120 (seconds / 60).  A
    # /61 divisor would report ~118, a /59 would report ~122.
    latest = _now() - datetime.timedelta(minutes=120)
    verdict = evaluate_assertion(
        assertion_kind="freshness",
        spec_json={"timestamp_column": "ts", "max_lag_minutes": 10_000},
        table=_table(ts=[latest.isoformat()]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["lag_minutes"] == pytest.approx(120.0, abs=0.5)


# ---------------------------------------------------------------------------
# _assert_value_distribution
# ---------------------------------------------------------------------------


def test_value_distribution_missing_column_error_observation() -> None:
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "missing"},
        table=_table(tier=["a", "b"]),
    )
    assert verdict.status == "error"
    assert verdict.observation == {"reason": "column 'missing' not in table"}


def test_value_distribution_counts_distinct_values() -> None:
    verdict = evaluate_assertion(
        assertion_kind="value_distribution",
        spec_json={"column": "tier", "min_distinct": 1, "max_distinct": 2},
        table=_table(tier=["a", "b", "a", "c"]),
    )
    # 3 distinct > max_distinct 2 => fail; pins the count itself.
    assert verdict.status == "fail"
    assert verdict.observation["distinct_count"] == 3


# ---------------------------------------------------------------------------
# _assert_referential
# ---------------------------------------------------------------------------


def test_referential_requires_column_and_allowed_list_message() -> None:
    with pytest.raises(ValueError, match="referential requires 'column' and 'allowed_values' list"):
        evaluate_assertion(
            assertion_kind="referential",
            spec_json={"column": "tier"},
            table=_table(tier=["a"]),
        )


def test_referential_missing_column_error_observation() -> None:
    verdict = evaluate_assertion(
        assertion_kind="referential",
        spec_json={"column": "missing", "allowed_values": ["a"]},
        table=_table(tier=["a"]),
    )
    assert verdict.status == "error"
    assert verdict.observation == {"reason": "column 'missing' not in table"}


def test_referential_violation_count_and_sample() -> None:
    verdict = evaluate_assertion(
        assertion_kind="referential",
        spec_json={"column": "tier", "allowed_values": ["a"]},
        table=_table(tier=["a", "b", "c", "d", "e", "f"]),
    )
    assert verdict.status == "fail"
    assert verdict.observation["violation_count"] == 5
    # sample is capped at 5 entries.
    assert verdict.observation["sample_violations"] == ["b", "c", "d", "e", "f"]


# ---------------------------------------------------------------------------
# _assert_row_count_range
# ---------------------------------------------------------------------------


def test_row_count_range_default_min_is_zero() -> None:
    # No ``min`` in spec must default to 0 (not None, which would raise
    # on int(None)).  A 0-row table then passes the [0, max] range.
    verdict = evaluate_assertion(
        assertion_kind="row_count_range",
        spec_json={"max": 100},
        table=_table(x=pa.array([], type=pa.int64())),
    )
    assert verdict.status == "pass"
    assert verdict.observation == {"observed": 0, "min": 0, "max": 100}


def test_row_count_range_default_max_is_large() -> None:
    # No ``max`` must default to a huge ceiling so a normal table passes.
    verdict = evaluate_assertion(
        assertion_kind="row_count_range",
        spec_json={"min": 1},
        table=_table(x=[1, 2, 3]),
    )
    assert verdict.status == "pass"
    assert verdict.observation["max"] == 10**12


# ---------------------------------------------------------------------------
# _generate_value (via generate_arrow_table)
# ---------------------------------------------------------------------------


def test_name_kind_emits_non_empty_strings() -> None:
    # The ``name`` branch must match; a mangled literal would fall
    # through to "unknown generator kind: name".
    table = generate_arrow_table([{"column": "who", "kind": "name"}], row_count=5, seed=1)
    values = table["who"].to_pylist()
    assert len(values) == 5
    assert all(isinstance(v, str) and v for v in values)


def test_uuid_kind_emits_uuids() -> None:
    table = generate_arrow_table([{"column": "uid", "kind": "uuid"}], row_count=3, seed=1)
    values = table["uid"].to_pylist()
    assert all(isinstance(v, str) and len(v) == 36 for v in values)


def test_int_kind_default_max_is_one_hundred() -> None:
    # No ``max`` => default 100 (int).  ``int(None)`` would crash.
    table = generate_arrow_table([{"column": "n", "kind": "int", "min": 0}], row_count=50, seed=7)
    values = table["n"].to_pylist()
    assert all(0 <= v <= 100 for v in values)


def test_float_kind_default_min_is_zero() -> None:
    # No ``min`` => default 0.0, max forced to 0.5 => all values <= 0.5.
    # A default min of 1.0 would swap the range to [0.5, 1.0].
    table = generate_arrow_table(
        [{"column": "f", "kind": "float", "max": 0.5}], row_count=200, seed=3
    )
    values = table["f"].to_pylist()
    assert all(0.0 <= v <= 0.5 for v in values)
    assert min(values) < 0.4  # genuinely spans the low end


def test_float_kind_reads_max_key() -> None:
    # max=0.1 must be honoured; ignoring the key would default to 1.0.
    table = generate_arrow_table(
        [{"column": "f", "kind": "float", "min": 0.0, "max": 0.1}],
        row_count=200,
        seed=4,
    )
    values = table["f"].to_pylist()
    assert all(v <= 0.1 for v in values)


def test_iso8601_ts_default_since_days_works() -> None:
    # No ``since_days`` => default 30; ``int(None)`` would crash.
    table = generate_arrow_table([{"column": "t", "kind": "iso8601_ts"}], row_count=10, seed=9)
    parsed = [datetime.datetime.fromisoformat(v) for v in table["t"].to_pylist()]
    now = _now()
    assert all((now - p).days <= 31 for p in parsed)


def test_choice_kind_reads_choices_key() -> None:
    # The generator must read the ``choices`` key; a renamed lookup
    # would default to [] and raise "non-empty".
    table = generate_arrow_table(
        [{"column": "c", "kind": "choice", "choices": ["x", "y"]}],
        row_count=20,
        seed=2,
    )
    assert set(table["c"].to_pylist()).issubset({"x", "y"})


def test_bool_kind_p_true_one_is_all_true() -> None:
    # p_true=1.0 => every value True.  A renamed key would default to
    # 0.5 and produce a mix.
    table = generate_arrow_table(
        [{"column": "b", "kind": "bool", "p_true": 1.0}], row_count=50, seed=5
    )
    assert all(v is True for v in table["b"].to_pylist())


def test_bool_kind_p_true_zero_is_all_false() -> None:
    table = generate_arrow_table(
        [{"column": "b", "kind": "bool", "p_true": 0.0}], row_count=50, seed=5
    )
    assert all(v is False for v in table["b"].to_pylist())


# ---------------------------------------------------------------------------
# _run_single_test (observable via run_contract_tests + persisted rows)
# ---------------------------------------------------------------------------


def _declare_basic_fixture(dp_id: int, table_name: str = "users", rows: int = 8) -> None:
    declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name=table_name,
        generator_spec_json=[{"column": "email", "kind": "email"}],
        row_count=rows,
    )


def test_result_dict_keys_and_persisted_observation() -> None:
    dp_id = _seed_dp("ct", "keys")
    _declare_basic_fixture(dp_id, rows=8)
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="rowcount",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "users", "min": 1, "max": 100},
    )
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")

    assert outcome.passed == 1
    result = outcome.results[0]
    # exact key set + values returned to the caller.
    assert set(result) == {
        "contract_test_id",
        "name",
        "assertion_kind",
        "status",
        "observation",
        "duration_ms",
    }
    assert result["name"] == "rowcount"
    assert result["assertion_kind"] == "row_count_range"
    assert result["status"] == "pass"
    assert result["observation"]["observed"] == 8

    # the persisted ledger row keeps the encoded observation JSON.
    with _factory()() as session:
        rows = session.query(DataProductContractTestResult).all()
        assert len(rows) == 1
        persisted = rows[0]
        assert persisted.status == "pass"
        assert persisted.observation_json is not None
        decoded = json.loads(persisted.observation_json)
        assert decoded["mode"] == "synthetic"
        assert decoded["table"] == "users"
        assert decoded["observed"] == 8


def test_invalid_assertion_spec_yields_error_not_crash() -> None:
    # value_distribution with empty column raises ValueError inside the
    # evaluator; the runner must catch it and persist an error verdict
    # rather than leaving ``verdict`` unset and crashing.
    dp_id = _seed_dp("ct", "badspec")
    _declare_basic_fixture(dp_id, rows=5)
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="badcol",
        assertion_kind="value_distribution",
        assertion_spec_json={"table": "users"},  # no 'column'
    )
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.errored == 1
    assert outcome.passed == 0
    result = outcome.results[0]
    assert result["status"] == "error"
    assert "assertion spec invalid" in result["observation"]["reason"]


def test_live_provider_returns_none_reports_not_found() -> None:
    # When the provider returns None (no exception), the runner must set
    # the "live table not found" reason.  Flipping the branch condition
    # would leave the generic "no table to evaluate" reason instead.
    dp_id = _seed_dp("ct", "live_none")
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="rc",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "events", "min": 1, "max": 10},
    )

    def provider(catalog: str, schema: str, table_name: str):
        return None

    outcome = run_contract_tests(
        _factory(),
        data_product_id=dp_id,
        mode="live",
        table_provider=provider,
    )
    assert outcome.errored == 1
    assert outcome.results[0]["status"] == "error"
    assert outcome.results[0]["observation"]["reason"] == "live table not found"


def test_live_provider_raising_reports_load_failure() -> None:
    dp_id = _seed_dp("ct", "live_raise")
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="rc",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "events", "min": 1, "max": 10},
    )

    def provider(catalog: str, schema: str, table_name: str):
        raise RuntimeError("boom")

    outcome = run_contract_tests(
        _factory(),
        data_product_id=dp_id,
        mode="live",
        table_provider=provider,
    )
    assert outcome.errored == 1
    reason = outcome.results[0]["observation"]["reason"]
    assert "live table load failed" in reason
    assert "boom" in reason


def test_synthetic_without_fixture_reports_no_fixture() -> None:
    dp_id = _seed_dp("ct", "nofixture")
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="rc",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "users", "min": 1, "max": 10},
    )
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.errored == 1
    assert outcome.results[0]["observation"]["reason"] == "no fixture available for synthetic mode"


# ---------------------------------------------------------------------------
# run_contract_tests audit detail
# ---------------------------------------------------------------------------


def test_run_writes_audit_detail_with_counts() -> None:
    dp_id = _seed_dp("ct", "audit")
    _declare_basic_fixture(dp_id, rows=8)
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="pass_one",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "users", "min": 1, "max": 100},
    )
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="fail_one",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "users", "min": 1000, "max": 2000},
    )
    run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")

    with _factory()() as session:
        entries = session.query(AuditLog).filter(AuditLog.action == "contract_test.run").all()
        assert len(entries) == 1
        entry = entries[0]
        assert entry.actor_role == "system"
        assert entry.target == f"data_product:{dp_id}"
        detail = json.loads(entry.detail)
        assert detail == {
            "mode": "synthetic",
            "total": 2,
            "passed": 1,
            "failed": 1,
            "errored": 0,
        }


# ---------------------------------------------------------------------------
# declare_fixture
# ---------------------------------------------------------------------------


def test_declare_fixture_default_row_count_is_one_hundred() -> None:
    dp_id = _seed_dp("ct", "fxdefault")
    result = declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[{"column": "email", "kind": "email"}],
    )
    assert result["row_count"] == 100


def test_declare_fixture_serialised_shape() -> None:
    dp_id = _seed_dp("ct", "fxshape")
    result = declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[{"column": "email", "kind": "email"}],
        row_count=42,
    )
    assert set(result) == {
        "id",
        "data_product_id",
        "table_name",
        "generator_spec_json",
        "row_count",
        "created_at",
    }
    assert result["data_product_id"] == dp_id
    assert result["table_name"] == "users"
    assert result["row_count"] == 42
    assert json.loads(result["generator_spec_json"]) == [{"column": "email", "kind": "email"}]


def test_declare_fixture_is_idempotent_update() -> None:
    # A second declare with the same (product, table_name) must UPDATE
    # the existing row, not insert a duplicate.  Skipping the lookup
    # (or filtering on the wrong product) would create a second row.
    dp_id = _seed_dp("ct", "fxidem")
    first = declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[{"column": "a", "kind": "int"}],
        row_count=10,
    )
    second = declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[{"column": "b", "kind": "int"}],
        row_count=20,
    )
    assert second["id"] == first["id"]
    assert second["row_count"] == 20
    assert json.loads(second["generator_spec_json"]) == [{"column": "b", "kind": "int"}]

    fixtures = list_fixtures(_factory(), data_product_id=dp_id)
    assert len(fixtures) == 1
    assert fixtures[0]["row_count"] == 20


def test_declare_fixture_requires_table_name() -> None:
    dp_id = _seed_dp("ct", "fxnoname")
    with pytest.raises(ValueError, match="table_name is required"):
        declare_fixture(
            _factory(),
            data_product_id=dp_id,
            table_name="   ",
            generator_spec_json=[{"column": "a", "kind": "int"}],
        )
