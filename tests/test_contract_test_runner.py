"""Contract-test runner orchestration (Phase 142)."""

from __future__ import annotations

import datetime
import json

import pyarrow as pa
import pytest

from pointlessql.api.main import app
from pointlessql.models import (
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


@pytest.fixture(autouse=True)
def _wipe_contract_tables():
    with _factory()() as session:
        session.query(DataProductContractTestResult).delete()
        session.query(DataProductContractTest).delete()
        session.query(DataProductFixture).delete()
        session.query(DataProduct).delete()
        session.commit()
    yield


def test_synthetic_run_emits_result_per_test() -> None:
    dp_id = _seed_dp("ct", "synth")
    declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[
            {"column": "email", "kind": "email"},
            {"column": "age", "kind": "int", "min": 18, "max": 80},
        ],
        row_count=50,
    )
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="row_count_50",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "users", "min": 25, "max": 100},
    )
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="email_present",
        assertion_kind="column_present",
        assertion_spec_json={"table": "users", "columns": ["email"]},
    )

    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")

    assert outcome.total == 2
    assert outcome.passed == 2
    assert outcome.failed == 0
    assert outcome.errored == 0
    with _factory()() as session:
        results = session.query(DataProductContractTestResult).all()
        assert len(results) == 2
        for row in results:
            assert row.status == "pass"


def test_synthetic_run_fails_when_assertion_violates() -> None:
    dp_id = _seed_dp("ct", "fails")
    declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[{"column": "email", "kind": "email"}],
        row_count=10,
    )
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="needs_lots",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "users", "min": 1000, "max": 10000},
    )
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.failed == 1
    assert outcome.passed == 0


def test_live_mode_requires_table_provider() -> None:
    dp_id = _seed_dp("ct", "live_no_provider")
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="any",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "users", "min": 0, "max": 10},
    )
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="live")
    assert outcome.errored == 1
    assert outcome.passed == 0


def test_live_mode_with_table_provider_evaluates() -> None:
    dp_id = _seed_dp("ct", "live_with_provider")
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="rows_present",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "events", "min": 1, "max": 10},
    )

    def provider(catalog: str, schema: str, table_name: str) -> pa.Table | None:
        assert (catalog, schema, table_name) == ("ct", "live_with_provider", "events")
        return pa.table({"id": [1, 2, 3]})

    outcome = run_contract_tests(
        _factory(),
        data_product_id=dp_id,
        mode="live",
        table_provider=provider,
    )
    assert outcome.passed == 1


def test_unknown_mode_raises() -> None:
    dp_id = _seed_dp("ct", "bad_mode")
    with pytest.raises(ValueError, match="unknown run mode"):
        run_contract_tests(_factory(), data_product_id=dp_id, mode="nope")


def test_disabled_tests_are_skipped() -> None:
    dp_id = _seed_dp("ct", "disabled")
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="alpha",
        assertion_kind="row_count_range",
        assertion_spec_json={"table": "x", "min": 0, "max": 0},
        enabled=False,
    )
    outcome = run_contract_tests(_factory(), data_product_id=dp_id, mode="synthetic")
    assert outcome.total == 0
