"""Mutation-killing tests for the contract-test runner.

These pin observable behaviour of ``run_contract_tests`` /
``_run_single_test``: the resolved target-table string, fixture
selection + fallback, the error reasons surfaced for the live and
synthetic failure paths, the per-status accumulators, the audit
workspace id, the persisted result row (status, compact observation
JSON, duration), and the returned ``RunOutcome`` summary.
"""

from __future__ import annotations

import datetime
import json
import time

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
    run_contract_tests,
)

# ---------------------------------------------------------------------------
# helpers / fixtures (mirrors tests/test_contract_tests_mutkill.py)
# ---------------------------------------------------------------------------


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


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


def _fixture(dp_id: int, table_name: str, rows: int) -> None:
    declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name=table_name,
        generator_spec_json=[{"column": "email", "kind": "email"}],
        row_count=rows,
    )


def _row_count_test(
    dp_id: int,
    name: str,
    *,
    table: str,
    lo: int = 1,
    hi: int = 100,
) -> None:
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name=name,
        assertion_kind="row_count_range",
        assertion_spec_json={"table": table, "min": lo, "max": hi},
    )


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


def _persisted_results() -> list[DataProductContractTestResult]:
    with _factory()() as session:
        return list(
            session.query(DataProductContractTestResult)
            .order_by(DataProductContractTestResult.id)
            .all()
        )


# ---------------------------------------------------------------------------
# target-table resolution: the persisted observation echoes "table"
# ---------------------------------------------------------------------------


def test_missing_table_key_resolves_to_empty_string() -> None:
    # No "table" key in the spec => the default must be "" (not None,
    # "None", or a mangled literal).  The runner echoes target_table
    # into the persisted observation under "table".
    dp_id = _seed_dp("ct", "no_table_key")
    _fixture(dp_id, "users", rows=4)
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="rc",
        assertion_kind="row_count_range",
        # spec carries no "table" key on purpose.
        assertion_spec_json={"min": 1, "max": 100},
    )
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")

    assert outcome.results[0]["status"] == "pass"
    rows = _persisted_results()
    assert len(rows) == 1
    decoded = json.loads(rows[0].observation_json)
    assert decoded["table"] == ""


def test_empty_spec_resolves_target_table_to_empty_string() -> None:
    # An empty spec string decodes to a falsy {} => the else-branch
    # default "" is used.  A mangled else default would surface here.
    dp_id = _seed_dp("ct", "empty_spec")
    _fixture(dp_id, "users", rows=4)
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="rc",
        assertion_kind="row_count_range",
        assertion_spec_json="",  # decodes to {} -> falsy
    )
    run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")

    rows = _persisted_results()
    assert len(rows) == 1
    decoded = json.loads(rows[0].observation_json)
    assert decoded["table"] == ""


# ---------------------------------------------------------------------------
# fixture selection: exact match vs first-fixture fallback
# ---------------------------------------------------------------------------


def test_synthetic_uses_fixture_matching_target_table() -> None:
    # Two fixtures with different row counts; the target points at the
    # SECOND one.  The runner must pick the exact-match fixture (9 rows),
    # not None / the first fixture (3 rows).
    dp_id = _seed_dp("ct", "fixture_match")
    _fixture(dp_id, "first_tbl", rows=3)
    _fixture(dp_id, "second_tbl", rows=9)
    _row_count_test(dp_id, "rc", table="second_tbl", lo=1, hi=100)

    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.results[0]["observation"]["observed"] == 9


def test_synthetic_unmatched_target_falls_back_to_first_fixture() -> None:
    # The target names a table with no fixture, but fixtures exist: the
    # runner falls back to the first fixture (3 rows) and evaluates it,
    # rather than erroring or crashing on a bad fallback expression.
    dp_id = _seed_dp("ct", "fixture_fallback")
    _fixture(dp_id, "first_tbl", rows=3)
    _fixture(dp_id, "second_tbl", rows=9)
    _row_count_test(dp_id, "rc", table="missing_tbl", lo=1, hi=100)

    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.results[0]["status"] == "pass"
    assert outcome.results[0]["observation"]["observed"] == 3


# ---------------------------------------------------------------------------
# error reasons surfaced by the failure paths
# ---------------------------------------------------------------------------


def test_synthetic_no_fixture_reason_text() -> None:
    dp_id = _seed_dp("ct", "no_fixture")
    _row_count_test(dp_id, "rc", table="users")
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.results[0]["status"] == "error"
    assert outcome.results[0]["observation"]["reason"] == "no fixture available for synthetic mode"


def test_fixture_generation_failure_reports_reason() -> None:
    # A fixture whose generator spec is invalid makes generate_arrow_table
    # raise ValueError; the runner must surface that as the error reason
    # rather than dropping it (None -> "no table to evaluate").
    dp_id = _seed_dp("ct", "bad_gen")
    declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[{"column": "x", "kind": "definitely_not_a_kind"}],
        row_count=5,
    )
    _row_count_test(dp_id, "rc", table="users")
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    reason = outcome.results[0]["observation"]["reason"]
    assert reason.startswith("fixture generation failed:")
    assert reason != "no table to evaluate"


def test_live_without_provider_reports_required_provider() -> None:
    # Live mode with no table_provider yields the exact "live mode
    # requires a table_provider" reason; a dropped/mangled literal would
    # change the persisted/returned reason.
    dp_id = _seed_dp("ct", "live_no_provider")
    _row_count_test(dp_id, "rc", table="events")
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="live")
    assert outcome.results[0]["status"] == "error"
    assert outcome.results[0]["observation"]["reason"] == "live mode requires a table_provider"


# ---------------------------------------------------------------------------
# per-status accumulators must add, not reset
# ---------------------------------------------------------------------------


def test_multiple_failures_accumulate_in_counter() -> None:
    # Two failing tests must produce failed == 2; a `failed = 1` reset
    # would cap the count at 1.
    dp_id = _seed_dp("ct", "two_fail")
    _fixture(dp_id, "users", rows=4)
    _row_count_test(dp_id, "fail_a", table="users", lo=1000, hi=2000)
    _row_count_test(dp_id, "fail_b", table="users", lo=1000, hi=2000)
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.failed == 2
    assert outcome.passed == 0
    assert outcome.errored == 0


def test_multiple_errors_accumulate_in_counter() -> None:
    # Two erroring tests (no fixture in synthetic mode) must produce
    # errored == 2; an `errored = 1` reset would cap at 1.
    dp_id = _seed_dp("ct", "two_error")
    _row_count_test(dp_id, "err_a", table="users")
    _row_count_test(dp_id, "err_b", table="users")
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.errored == 2
    assert outcome.passed == 0
    assert outcome.failed == 0


# ---------------------------------------------------------------------------
# product lookup failure
# ---------------------------------------------------------------------------


def test_missing_product_raises_lookup_error_with_message() -> None:
    # An unknown product id raises LookupError carrying the id; a None
    # message would no longer match the contracted text.
    with pytest.raises(LookupError, match=r"data product 999999 not found"):
        run_contract_tests(_factory(), data_product_id=999999, mode="synthetic")


# ---------------------------------------------------------------------------
# audit detail / workspace propagation
# ---------------------------------------------------------------------------


def test_audit_entry_uses_passed_workspace_id() -> None:
    # The workspace_id passed to run_contract_tests must reach the audit
    # row; dropping the kwarg (default 1) or passing None would not match.
    dp_id = _seed_dp("ct", "ws")
    _fixture(dp_id, "users", rows=4)
    _row_count_test(dp_id, "rc", table="users")
    run_contract_tests(
        _factory(),
        data_product_id=dp_id,
        mode="synthetic",
        workspace_id=7,
    )
    with _factory()() as session:
        entry = session.query(AuditLog).filter(AuditLog.action == "contract_test.run").one()
        assert entry.workspace_id == 7


# ---------------------------------------------------------------------------
# RunOutcome summary
# ---------------------------------------------------------------------------


def test_outcome_mode_echoes_requested_mode() -> None:
    dp_id = _seed_dp("ct", "mode_echo")
    _fixture(dp_id, "users", rows=4)
    _row_count_test(dp_id, "rc", table="users")
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.mode == "synthetic"


# ---------------------------------------------------------------------------
# persisted result row: duration + compact observation JSON
# ---------------------------------------------------------------------------


def test_persisted_duration_ms_is_recorded() -> None:
    # The persisted result row must carry a non-null duration_ms; passing
    # None (or dropping the kwarg) would leave the column NULL.
    dp_id = _seed_dp("ct", "dur_persist")
    _fixture(dp_id, "users", rows=4)
    _row_count_test(dp_id, "rc", table="users")
    run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    rows = _persisted_results()
    assert len(rows) == 1
    assert rows[0].duration_ms is not None
    assert isinstance(rows[0].duration_ms, int)


def test_returned_duration_ms_is_small_nonnegative_int() -> None:
    # duration_ms = int((monotonic() - start) * 1000): a fast run yields a
    # small non-negative int.  A `+ start` flip would explode the value;
    # a `None` assignment would not be an int.
    dp_id = _seed_dp("ct", "dur_return")
    _fixture(dp_id, "users", rows=4)
    _row_count_test(dp_id, "rc", table="users")
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    duration = outcome.results[0]["duration_ms"]
    assert isinstance(duration, int)
    assert 0 <= duration < 60_000


def test_persisted_observation_json_is_compact() -> None:
    # The observation is encoded with separators=(",", ":"); the compact
    # form has no ", " or ": " whitespace.  Dropping/None-ing separators
    # would re-introduce spaces.
    dp_id = _seed_dp("ct", "compact")
    _fixture(dp_id, "users", rows=4)
    _row_count_test(dp_id, "rc", table="users", lo=1, hi=100)
    run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    rows = _persisted_results()
    encoded = rows[0].observation_json
    assert encoded is not None
    assert ", " not in encoded
    assert ": " not in encoded
    # sanity: still valid, still carries the runner-injected keys.
    decoded = json.loads(encoded)
    assert decoded["mode"] == "synthetic"
    assert decoded["table"] == "users"


# ---------------------------------------------------------------------------
# duration scaling: elapsed seconds * 1000 (not / 1000)
# ---------------------------------------------------------------------------


def test_duration_ms_scales_seconds_up_by_a_thousand() -> None:
    # ``started_at`` is taken before the provider runs, so a provider
    # that blocks ~50 ms makes elapsed ~0.05 s.  With the correct
    # ``* 1000`` scaling duration_ms is ~50; a ``/ 1000`` mutant would
    # collapse it to int(0.05 / 1000) == 0.  Use a generous floor that
    # is impossible to hit by an unscaled-down value yet trivially
    # cleared by the real scaling, so the test stays non-flaky.
    dp_id = _seed_dp("ct", "dur_scale")
    _row_count_test(dp_id, "rc", table="events", lo=0, hi=10)

    sleep_s = 0.05

    def provider(catalog: str, schema: str, table_name: str) -> pa.Table:
        time.sleep(sleep_s)
        return pa.table({"id": pa.array([1, 2], type=pa.int64())})

    outcome = run_contract_tests(
        _factory(),
        data_product_id=dp_id,
        mode="live",
        table_provider=provider,
    )
    duration = outcome.results[0]["duration_ms"]
    # original: >= ~50; the ``/ 1000`` mutant yields 0.
    assert duration >= 10
    # the persisted row carries the same scaled value.
    rows = _persisted_results()
    assert rows[0].duration_ms >= 10


# ---------------------------------------------------------------------------
# observation JSON uses ``default=str`` for non-native values
# ---------------------------------------------------------------------------


def test_non_json_native_observation_serialised_via_default_str() -> None:
    # The referential assertion echoes raw column values into
    # ``sample_violations``.  A ``date32`` column yields ``datetime.date``
    # objects, which are not natively JSON-serialisable, so json.dumps
    # must rely on ``default=str``.  Dropping the callable (or setting it
    # to ``None``) makes json.dumps raise TypeError inside the runner,
    # which would propagate out of ``run_contract_tests``.
    dp_id = _seed_dp("ct", "default_str")
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="ref",
        assertion_kind="referential",
        assertion_spec_json={
            "table": "events",
            "column": "d",
            "allowed_values": ["1999-12-31"],
        },
    )

    def provider(catalog: str, schema: str, table_name: str) -> pa.Table:
        return pa.table({"d": pa.array([datetime.date(2020, 1, 1)], type=pa.date32())})

    # On the real code this returns cleanly; on the mutant json.dumps
    # raises TypeError before a result row is ever returned.
    outcome = run_contract_tests(
        _factory(),
        data_product_id=dp_id,
        mode="live",
        table_provider=provider,
    )
    assert outcome.failed == 1
    result = outcome.results[0]
    assert result["status"] == "fail"
    assert result["observation"]["violation_count"] == 1

    # the stringified date survived the encode/round-trip in the row.
    rows = _persisted_results()
    assert len(rows) == 1
    decoded = json.loads(rows[0].observation_json)
    assert decoded["sample_violations"] == ["2020-01-01"]
