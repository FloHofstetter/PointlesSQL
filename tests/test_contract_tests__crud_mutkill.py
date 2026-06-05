"""Behaviour tests pinning the contract-test CRUD layer.

These tests assert the exact serialised dict keys, persisted
``created_by_user_id`` audit pointers, the ``row_count`` clamp
boundaries, the enabled-only listing filter, and the exact
validation-error messages so that small mutations to dict keys,
boolean wrapping, call-site keyword arguments, clamp constants, and
branch conditions in :mod:`pointlessql.services.contract_tests._crud`
become observable failures.
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
    DataProductContractTest,
    DataProductContractTestResult,
    DataProductFixture,
    User,
)
from pointlessql.services.contract_tests import (
    declare_contract_test,
    declare_fixture,
    list_contract_tests,
    list_fixtures,
)

# ---------------------------------------------------------------------------
# helpers / fixtures
# ---------------------------------------------------------------------------


def _factory():
    return app.state.session_factory


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.UTC)


def _a_user_id() -> int:
    """A seeded, FK-valid ``users.id`` to attach as the author pointer."""
    with _factory()() as session:
        uid = session.scalar(select(User.id).order_by(User.id))
    assert uid is not None
    return int(uid)


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
# _serialise_test — exact dict-key contract
# ---------------------------------------------------------------------------


def test_declare_contract_test_serialised_key_set() -> None:
    # Pins every key the serialiser emits.  Renaming any key (e.g.
    # ``data_product_id`` -> ``DATA_PRODUCT_ID`` / ``assertion_spec_json``
    # -> ``XXassertion_spec_jsonXX`` / ``enabled`` / ``created_at``) drops
    # the expected key and adds a bogus one.
    dp_id = _seed_dp("ct", "keys")
    result = declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="t1",
        assertion_kind="row_count_range",
        assertion_spec_json={"min": 1, "max": 10},
    )
    assert set(result) == {
        "id",
        "data_product_id",
        "name",
        "assertion_kind",
        "assertion_spec_json",
        "severity",
        "enabled",
        "created_at",
    }
    assert result["data_product_id"] == dp_id
    assert result["assertion_kind"] == "row_count_range"


def test_declare_contract_test_enabled_reflects_value_not_constant() -> None:
    # ``"enabled": bool(row.enabled)`` must reflect the stored flag.
    # ``bool(None)`` would collapse every test to ``False``.
    dp_id = _seed_dp("ct", "enbl")
    enabled_row = declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="on",
        assertion_kind="row_count_range",
        assertion_spec_json={"min": 1},
        enabled=True,
    )
    disabled_row = declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="off",
        assertion_kind="row_count_range",
        assertion_spec_json={"min": 1},
        enabled=False,
    )
    assert enabled_row["enabled"] is True
    assert disabled_row["enabled"] is False


# ---------------------------------------------------------------------------
# declare_contract_test — validation + author pointer
# ---------------------------------------------------------------------------


def test_declare_contract_test_blank_name_message() -> None:
    # Exact message — a mangled literal still raises ValueError but with
    # a different text, so assert on the full string, not a substring.
    dp_id = _seed_dp("ct", "noname")
    with pytest.raises(ValueError) as excinfo:
        declare_contract_test(
            _factory(),
            data_product_id=dp_id,
            name="   ",
            assertion_kind="row_count_range",
            assertion_spec_json={"min": 1},
        )
    assert str(excinfo.value) == "name is required"


def test_declare_contract_test_persists_created_by_user_id() -> None:
    # The author pointer must be threaded through to the insert.  A
    # call-site ``created_by_user_id=None`` (or a dropped kwarg) would
    # persist NULL instead of the supplied id.
    dp_id = _seed_dp("ct", "author")
    uid = _a_user_id()
    result = declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="t1",
        assertion_kind="row_count_range",
        assertion_spec_json={"min": 1},
        created_by_user_id=uid,
    )
    with _factory()() as session:
        row = session.get(DataProductContractTest, result["id"])
        assert row is not None
        assert row.created_by_user_id == uid


# ---------------------------------------------------------------------------
# declare_fixture — clamp boundaries + validation + author pointer
# ---------------------------------------------------------------------------


def test_declare_fixture_row_count_lower_clamp_keeps_one() -> None:
    # ``max(1, min(int(row_count), 100_000))`` floors at 1.  A floor of
    # 2 would bump a requested single row up to 2.
    dp_id = _seed_dp("ct", "lowclamp")
    result = declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[{"column": "a", "kind": "int"}],
        row_count=1,
    )
    assert result["row_count"] == 1


def test_declare_fixture_row_count_upper_clamp_is_one_hundred_thousand() -> None:
    # The ceiling is 100_000.  A ceiling of 100_001 would let an
    # over-large request through as 100_001 instead of clamping.
    dp_id = _seed_dp("ct", "highclamp")
    result = declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[{"column": "a", "kind": "int"}],
        row_count=100_001,
    )
    assert result["row_count"] == 100_000


def test_declare_fixture_blank_table_name_message() -> None:
    dp_id = _seed_dp("ct", "fxnoname")
    with pytest.raises(ValueError) as excinfo:
        declare_fixture(
            _factory(),
            data_product_id=dp_id,
            table_name="   ",
            generator_spec_json=[{"column": "a", "kind": "int"}],
        )
    assert str(excinfo.value) == "table_name is required"


def test_declare_fixture_persists_created_by_user_id() -> None:
    dp_id = _seed_dp("ct", "fxauthor")
    uid = _a_user_id()
    result = declare_fixture(
        _factory(),
        data_product_id=dp_id,
        table_name="users",
        generator_spec_json=[{"column": "a", "kind": "int"}],
        created_by_user_id=uid,
    )
    with _factory()() as session:
        row = session.get(DataProductFixture, result["id"])
        assert row is not None
        assert row.created_by_user_id == uid


# ---------------------------------------------------------------------------
# list_contract_tests — enabled-only filter
# ---------------------------------------------------------------------------


def test_list_contract_tests_excludes_disabled_when_requested() -> None:
    # ``include_disabled=False`` must filter to enabled rows only.
    # Inverting the ``not include_disabled`` guard, nulling the
    # statement, swapping ``is_(True)`` -> ``is_(False)`` / ``is_(None)``,
    # or replacing the filter with ``where(None)`` all change which rows
    # come back; asserting the returned set is exactly the enabled test
    # distinguishes every one of them.
    dp_id = _seed_dp("ct", "filter")
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="keep",
        assertion_kind="row_count_range",
        assertion_spec_json={"min": 1},
        enabled=True,
    )
    declare_contract_test(
        _factory(),
        data_product_id=dp_id,
        name="drop",
        assertion_kind="row_count_range",
        assertion_spec_json={"min": 1},
        enabled=False,
    )

    visible = list_contract_tests(_factory(), data_product_id=dp_id, include_disabled=False)
    assert [t["name"] for t in visible] == ["keep"]

    everything = list_contract_tests(_factory(), data_product_id=dp_id, include_disabled=True)
    assert {t["name"] for t in everything} == {"keep", "drop"}


# ---------------------------------------------------------------------------
# list_contract_tests / list_fixtures — explicit id ordering
# ---------------------------------------------------------------------------


def test_list_contract_tests_ordered_by_insertion_id_not_name() -> None:
    # The listing must come back in id (insertion) order via the explicit
    # ``order_by(DataProductContractTest.id)``.  Dropping that clause
    # (``order_by(None)``) lets the planner walk the unique
    # ``(data_product_id, name)`` index instead and yields name order, so
    # declaring names whose alphabetical order differs from their
    # insertion order makes the missing sort observable.
    dp_id = _seed_dp("ct", "order")
    for name in ("zeta", "alpha", "mid"):
        declare_contract_test(
            _factory(),
            data_product_id=dp_id,
            name=name,
            assertion_kind="row_count_range",
            assertion_spec_json={"min": 1},
        )
    names = [t["name"] for t in list_contract_tests(_factory(), data_product_id=dp_id)]
    assert names == ["zeta", "alpha", "mid"]


def test_list_fixtures_ordered_by_insertion_id_not_table_name() -> None:
    # Same contract for fixtures: the explicit ``order_by(
    # DataProductFixture.id)`` keeps insertion order.  ``order_by(None)``
    # would surface them in table-name order through the unique index.
    dp_id = _seed_dp("ct", "fxorder")
    for table_name in ("zeta", "alpha", "mid"):
        declare_fixture(
            _factory(),
            data_product_id=dp_id,
            table_name=table_name,
            generator_spec_json=[{"column": "a", "kind": "int"}],
        )
    names = [f["table_name"] for f in list_fixtures(_factory(), data_product_id=dp_id)]
    assert names == ["zeta", "alpha", "mid"]
