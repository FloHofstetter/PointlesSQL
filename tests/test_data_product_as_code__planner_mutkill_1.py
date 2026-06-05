"""Behaviour tests pinning the planner diff functions for contract tests,
entities, fixtures, and input ports.

Each test asserts the *exact* Op the planner emits on the add / update /
remove paths: the ``kind`` / ``action`` constant, the ``target`` it
identifies the op by, and the precise ``before`` dict (key names + the
field each value is read from).  They also pin the membership-set
bookkeeping that decides whether a row counts as a removal, so a spec
name registered as ``None`` (which would falsely flag an unchanged row
for removal) is caught.
"""

from __future__ import annotations

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    DataProduct,
    DataProductContractTest,
    DataProductContractTestResult,
    DataProductEntity,
    DataProductFixture,
    DataProductInputPort,
    DataProductOutputPort,
    DataProductPolicy,
    DataProductSLO,
)
from pointlessql.services.data_product_as_code import (
    apply_plan,
    parse_spec,
    plan_spec,
)


def _factory():
    return app.state.session_factory


def _wipe() -> None:
    with _factory()() as session:
        session.query(DataProductContractTestResult).delete()
        session.query(DataProductContractTest).delete()
        session.query(DataProductFixture).delete()
        session.query(DataProductPolicy).delete()
        session.query(DataProductEntity).delete()
        session.query(DataProductSLO).delete()
        session.query(DataProductOutputPort).delete()
        session.query(DataProductInputPort).delete()
        session.query(DataProduct).delete()
        session.commit()


@pytest.fixture(autouse=True)
def _clean_state():
    _wipe()
    yield
    _wipe()


def _apply(spec) -> None:
    apply_plan(_factory(), spec=spec, plan=plan_spec(_factory(), spec=spec))


# ---------------------------------------------------------------------------
# contract tests — add path
# ---------------------------------------------------------------------------


def test_plan_contract_test_addition_op_shape() -> None:
    """The add op identifies the test by its name, with before=None."""
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ct_add",
            "contract_tests": [
                {
                    "name": "null_rate_id",
                    "assertion_kind": "null_rate",
                    "assertion_spec": {"column": "id"},
                    "severity": "error",
                    "enabled": False,
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    op = next(o for o in plan.additions if o.kind == "contract_test")
    assert op.kind == "contract_test"
    assert op.action == "add"
    assert op.target == "null_rate_id"
    assert op.before is None
    assert op.after == {
        "name": "null_rate_id",
        "assertion_kind": "null_rate",
        "assertion_spec": {"column": "id"},
        "severity": "error",
        "enabled": False,
    }


# ---------------------------------------------------------------------------
# contract tests — update path (action + target constants)
# ---------------------------------------------------------------------------


def test_plan_contract_test_update_op_action_and_target() -> None:
    """The update op uses action='update' and targets the test name."""
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ct_upd",
            "contract_tests": [
                {
                    "name": "ct",
                    "assertion_kind": "null_rate",
                    "assertion_spec": {"column": "id"},
                    "severity": "warn",
                    "enabled": True,
                }
            ],
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ct_upd",
            "contract_tests": [
                {
                    "name": "ct",
                    "assertion_kind": "null_rate",
                    "assertion_spec": {"column": "id"},
                    "severity": "error",
                    "enabled": True,
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    ct_mods = [o for o in plan.modifications if o.kind == "contract_test"]
    assert len(ct_mods) == 1
    op = ct_mods[0]
    assert op.action == "update"
    assert op.target == "ct"


# ---------------------------------------------------------------------------
# contract tests — spec-name bookkeeping: an unchanged test is NOT a removal
# ---------------------------------------------------------------------------


def test_plan_contract_test_unchanged_is_not_removed() -> None:
    """Re-planning an identical spec emits no contract-test removal.

    If the spec name were registered as None in the membership set, the
    surviving DB row would falsely qualify as a removal.
    """
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ct_keep",
            "contract_tests": [
                {
                    "name": "ct",
                    "assertion_kind": "null_rate",
                    "assertion_spec": {"column": "id"},
                }
            ],
        }
    )
    _apply(spec)
    plan = plan_spec(_factory(), spec=spec)
    assert [o for o in plan.removals if o.kind == "contract_test"] == []


# ---------------------------------------------------------------------------
# contract tests — remove path: condition flip, Op identity, before dict
# ---------------------------------------------------------------------------


def test_plan_contract_test_removal_op_shape() -> None:
    """A dropped test yields exactly one remove Op with the full before dict."""
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ct_rm",
            "contract_tests": [
                {
                    "name": "keep",
                    "assertion_kind": "null_rate",
                    "assertion_spec": {"column": "id"},
                },
                {
                    "name": "drop",
                    "assertion_kind": "column_present",
                    "assertion_spec": {"column": "x"},
                },
            ],
        }
    )
    _apply(spec_two)
    spec_one = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ct_rm",
            "contract_tests": [
                {
                    "name": "keep",
                    "assertion_kind": "null_rate",
                    "assertion_spec": {"column": "id"},
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    ct_removals = [o for o in plan.removals if o.kind == "contract_test"]
    assert len(ct_removals) == 1
    op = ct_removals[0]
    assert op is not None
    assert op.kind == "contract_test"
    assert op.action == "remove"
    assert op.target == "drop"
    assert op.before == {"name": "drop"}
    assert op.after is None


# ---------------------------------------------------------------------------
# entities — add path
# ---------------------------------------------------------------------------


def test_plan_entity_addition_op_shape() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ent_add",
            "entities": [
                {
                    "name": "Customer",
                    "source_table": "cust",
                    "primary_key_columns": ["id"],
                    "description": "d",
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    op = next(o for o in plan.additions if o.kind == "entity")
    assert op.kind == "entity"
    assert op.action == "add"
    assert op.target == "Customer"
    assert op.before is None
    assert op.after == {
        "name": "Customer",
        "source_table": "cust",
        "primary_key_columns": ["id"],
        "description": "d",
    }


# ---------------------------------------------------------------------------
# entities — update path
# ---------------------------------------------------------------------------


def test_plan_entity_update_op_action_and_target() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ent_upd",
            "entities": [
                {
                    "name": "E",
                    "source_table": "t1",
                    "primary_key_columns": ["a"],
                }
            ],
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ent_upd",
            "entities": [
                {
                    "name": "E",
                    "source_table": "t2",
                    "primary_key_columns": ["a"],
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    ent_mods = [o for o in plan.modifications if o.kind == "entity"]
    assert len(ent_mods) == 1
    op = ent_mods[0]
    assert op.action == "update"
    assert op.target == "E"


# ---------------------------------------------------------------------------
# entities — remove path: condition flip, Op identity, before dict
# ---------------------------------------------------------------------------


def test_plan_entity_removal_op_shape() -> None:
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ent_rm",
            "entities": [
                {"name": "keep", "source_table": "t", "primary_key_columns": ["a"]},
                {"name": "drop", "source_table": "t2", "primary_key_columns": ["b"]},
            ],
        }
    )
    _apply(spec_two)
    spec_one = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ent_rm",
            "entities": [{"name": "keep", "source_table": "t", "primary_key_columns": ["a"]}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    ent_removals = [o for o in plan.removals if o.kind == "entity"]
    assert len(ent_removals) == 1
    op = ent_removals[0]
    assert op is not None
    assert op.kind == "entity"
    assert op.action == "remove"
    assert op.target == "drop"
    assert op.before == {"name": "drop"}
    assert op.after is None


# ---------------------------------------------------------------------------
# fixtures — add path
# ---------------------------------------------------------------------------


def test_plan_fixture_addition_op_shape() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_add",
            "fixtures": [
                {
                    "table_name": "seed",
                    "generator_spec": [{"column": "id"}],
                    "row_count": 4,
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    op = next(o for o in plan.additions if o.kind == "fixture")
    assert op.kind == "fixture"
    assert op.action == "add"
    assert op.target == "seed"
    assert op.before is None
    assert op.after == {
        "table_name": "seed",
        "generator_spec": [{"column": "id"}],
        "row_count": 4,
    }


# ---------------------------------------------------------------------------
# fixtures — spec-table bookkeeping: unchanged fixture is NOT a removal
# ---------------------------------------------------------------------------


def test_plan_fixture_unchanged_is_not_removed() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_keep",
            "fixtures": [
                {
                    "table_name": "t",
                    "generator_spec": [{"column": "id"}],
                    "row_count": 3,
                }
            ],
        }
    )
    _apply(spec)
    plan = plan_spec(_factory(), spec=spec)
    assert [o for o in plan.removals if o.kind == "fixture"] == []


# ---------------------------------------------------------------------------
# fixtures — update path
# ---------------------------------------------------------------------------


def test_plan_fixture_update_op_action_and_target() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_upd",
            "fixtures": [
                {
                    "table_name": "t",
                    "generator_spec": [{"column": "id"}],
                    "row_count": 3,
                }
            ],
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_upd",
            "fixtures": [
                {
                    "table_name": "t",
                    "generator_spec": [{"column": "id"}],
                    "row_count": 9,
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    fx_mods = [o for o in plan.modifications if o.kind == "fixture"]
    assert len(fx_mods) == 1
    op = fx_mods[0]
    assert op.action == "update"
    assert op.target == "t"


# ---------------------------------------------------------------------------
# fixtures — remove path: condition flip, Op identity, before dict
# ---------------------------------------------------------------------------


def test_plan_fixture_removal_op_shape() -> None:
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_rm",
            "fixtures": [
                {
                    "table_name": "keep",
                    "generator_spec": [{"column": "id"}],
                    "row_count": 1,
                },
                {
                    "table_name": "drop",
                    "generator_spec": [{"column": "x"}],
                    "row_count": 2,
                },
            ],
        }
    )
    _apply(spec_two)
    spec_one = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_rm",
            "fixtures": [
                {
                    "table_name": "keep",
                    "generator_spec": [{"column": "id"}],
                    "row_count": 1,
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    fx_removals = [o for o in plan.removals if o.kind == "fixture"]
    assert len(fx_removals) == 1
    op = fx_removals[0]
    assert op is not None
    assert op.kind == "fixture"
    assert op.action == "remove"
    assert op.target == "drop"
    assert op.before == {"table_name": "drop"}
    assert op.after is None


# ---------------------------------------------------------------------------
# input ports — add path
# ---------------------------------------------------------------------------


def test_plan_input_port_addition_op_shape() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_add",
            "input_ports": [
                {
                    "name": "upstream",
                    "kind": "external",
                    "source_ref": "ref",
                    "description": "d",
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    op = next(o for o in plan.additions if o.kind == "input_port")
    assert op.kind == "input_port"
    assert op.action == "add"
    assert op.target == "upstream"
    assert op.before is None
    assert op.after == {
        "name": "upstream",
        "kind": "external",
        "source_ref": "ref",
        "description": "d",
    }


# ---------------------------------------------------------------------------
# input ports — update path (action + target constants)
# ---------------------------------------------------------------------------


def test_plan_input_port_update_op_action_and_target() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_upd",
            "input_ports": [
                {
                    "name": "src",
                    "kind": "external",
                    "source_ref": "ref-1",
                    "description": "old",
                }
            ],
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_upd",
            "input_ports": [
                {
                    "name": "src",
                    "kind": "external",
                    "source_ref": "ref-2",
                    "description": "new",
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    ip_mods = [o for o in plan.modifications if o.kind == "input_port"]
    assert len(ip_mods) == 1
    op = ip_mods[0]
    assert op.action == "update"
    assert op.target == "src"


# ---------------------------------------------------------------------------
# input ports — remove path: full before dict with exact key names
# ---------------------------------------------------------------------------


def test_plan_input_port_removal_before_dict() -> None:
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_rm",
            "input_ports": [
                {"name": "keep", "kind": "external", "source_ref": "r0"},
                {
                    "name": "drop",
                    "kind": "upstream_product",
                    "source_ref": "ref-x",
                    "description": "going away",
                },
            ],
        }
    )
    _apply(spec_two)
    spec_one = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_rm",
            "input_ports": [{"name": "keep", "kind": "external", "source_ref": "r0"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    ip_removals = [o for o in plan.removals if o.kind == "input_port"]
    assert len(ip_removals) == 1
    op = ip_removals[0]
    assert op.target == "drop"
    assert op.before == {
        "name": "drop",
        "kind": "upstream_product",
        "source_ref": "ref-x",
        "description": "going away",
    }
    assert op.after is None
