"""Behaviour tests pinning the data-product-as-code planner's emitted Ops.

These assert the *exact* ``Op`` dicts the planner produces for product
add/update, policy add/update, SLO add/update/remove, and the
removal-path ``before`` dicts for input/output ports and SLOs.  They are
written to kill mutations that rename a dict key, swap an action / kind
string, null a kwarg, drop a list argument, or flip the unit-fallback
condition.
"""

from __future__ import annotations

import json

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
# planner — product "add" Op carries the exact product dict and strings
# ---------------------------------------------------------------------------


def test_plan_product_addition_op_full_shape() -> None:
    """The product add Op must use action='add', a catalog.schema target,
    before=None, and an after dict whose keys are exactly the product
    field names (kills key-rename + action/target/after-null mutants).
    """
    spec = parse_spec(
        {
            "name": "Prod Name",
            "catalog": "dpac",
            "schema": "prod_add",
            "domain": "sales",
            "lifecycle": "active",
            "owner_email": "owner@x.io",
            "description": "the description",
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    op = next(o for o in plan.additions if o.kind == "product")
    assert op.action == "add"
    assert op.target == "dpac.prod_add"
    assert op.before is None
    assert op.after == {
        "name": "Prod Name",
        "catalog": "dpac",
        "schema": "prod_add",
        "domain": "sales",
        "lifecycle": "active",
        "owner_email": "owner@x.io",
        "description": "the description",
    }


# ---------------------------------------------------------------------------
# planner — product "update" Op fires only when the description changes,
# and carries the exact kind/action/target/before/after shape
# ---------------------------------------------------------------------------


def test_plan_product_update_op_full_shape() -> None:
    """Changing the description yields a product update Op with the exact
    kind/action/target strings and before/after dicts (kills the
    kind/action/target/before/after null + string + key-rename mutants).
    """
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "prod_upd",
            "description": "old desc",
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "prod_upd",
            "description": "new desc",
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    op = next(o for o in plan.modifications if o.kind == "product")
    assert op.kind == "product"
    assert op.action == "update"
    assert op.target == "dpac.prod_upd"
    assert op.before == {"catalog": "dpac", "schema": "prod_upd"}
    assert op.after["description"] == "new desc"
    assert op.after["name"] == "P"


def test_plan_product_unchanged_description_emits_no_update() -> None:
    """Re-planning a spec whose non-empty description matches the stored
    row produces no product modification.  Kills the
    ``(row.description or "")`` -> ``(row.description and "")`` mutant,
    which would coerce a stored description to "" and spuriously report a
    change.
    """
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "prod_same",
            "description": "stable",
        }
    )
    _apply(spec)
    plan = plan_spec(_factory(), spec=spec)
    assert [o for o in plan.modifications if o.kind == "product"] == []


# ---------------------------------------------------------------------------
# planner — policies "add" Op (product absent) carries the exact
# action/target (kills action/target null + string mutants)
# ---------------------------------------------------------------------------


def test_plan_policies_addition_op_shape() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "pol_add",
            "policies": {"retention_days": 30},
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    op = next(o for o in plan.additions if o.kind == "policies")
    assert op.action == "add"
    assert op.target == "dpac.pol_add"
    assert op.before is None
    assert op.after["retention_days"] == 30


# ---------------------------------------------------------------------------
# planner — policies "update" Op target + the delta's after value
# ---------------------------------------------------------------------------


def test_plan_policies_update_target_and_after_value() -> None:
    """The policies update Op targets catalog.schema and its after dict
    carries the *desired* value for each changed field.  Kills both the
    ``target=None`` mutant and the ``desired.get(None)`` mutant (which
    would null every after value).
    """
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "pol_upd",
            "policies": {"retention_days": 30},
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "pol_upd",
            "policies": {"retention_days": 90},
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    op = next(o for o in plan.modifications if o.kind == "policies")
    assert op.target == "dpac.pol_upd"
    assert op.before == {"retention_days": 30}
    assert op.after == {"retention_days": 90}


# ---------------------------------------------------------------------------
# planner — SLO "update" Op full shape (kind/action/target/before/after)
# ---------------------------------------------------------------------------


def test_plan_slo_modification_op_full_shape() -> None:
    """A changed SLO target_value yields a single update Op whose
    kind/action strings and before/after dicts are exact.  Kills the
    Op-null, kwarg-null, kwarg-drop, and string-mutation survivors on the
    SLO modification branch.
    """
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_mod",
            "slos": [
                {
                    "kind": "freshness",
                    "comparator": "lte",
                    "target_value": 1.0,
                    "table": "events",
                }
            ],
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_mod",
            "slos": [
                {
                    "kind": "freshness",
                    "comparator": "lte",
                    "target_value": 5.0,
                    "table": "events",
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    slo_mods = [o for o in plan.modifications if o.kind == "slo"]
    assert len(slo_mods) == 1
    op = slo_mods[0]
    assert op.kind == "slo"
    assert op.action == "update"
    assert op.target == "freshness"
    # The applier resolves freshness' kind-default unit ("minutes"); the
    # spec omits unit, so the planner inherits the stored one on both sides.
    assert op.before == {
        "kind": "freshness",
        "comparator": "lte",
        "target_value": 1.0,
        "table": "events",
        "unit": "minutes",
    }
    assert op.after == {
        "kind": "freshness",
        "comparator": "lte",
        "target_value": 5.0,
        "table": "events",
        "unit": "minutes",
    }


# ---------------------------------------------------------------------------
# planner — SLO unit fallback only fires when the spec omits the unit.
# When the spec *provides* a differing unit, the planner must keep the
# spec's unit (kills ``desired.get("unit")`` -> ``desired.get(None)`` /
# wrong-key mutants, which always evaluate the fallback and clobber the
# spec unit with the stored one).
# ---------------------------------------------------------------------------


def test_plan_slo_keeps_spec_unit_when_provided() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_unit2",
            "slos": [{"kind": "freshness", "comparator": "lte", "target_value": 1.0}],
        }
    )
    _apply(spec_v1)
    # The stored unit is the freshness kind-default ("minutes").  The new
    # spec explicitly provides a *different* unit; the fallback must NOT
    # fire, so the planner emits an update whose desired unit is the spec's.
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_unit2",
            "slos": [
                {
                    "kind": "freshness",
                    "comparator": "lte",
                    "target_value": 1.0,
                    "unit": "hours",
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    op = next(o for o in plan.modifications if o.kind == "slo")
    assert op.after["unit"] == "hours"
    assert op.before["unit"] == "minutes"


# ---------------------------------------------------------------------------
# planner — SLO removal Op carries before={"kind": <stored kind>}
# (kills before=None and the "kind" key-rename mutants)
# ---------------------------------------------------------------------------


def test_plan_slo_removal_before_dict() -> None:
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_rm",
            "slos": [
                {"kind": "freshness", "target_value": 1.0},
                {"kind": "completeness", "target_value": 0.9, "comparator": "gte"},
            ],
        }
    )
    _apply(spec_two)
    spec_one = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_rm",
            "slos": [{"kind": "freshness", "target_value": 1.0}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    op = next(o for o in plan.removals if o.kind == "slo")
    assert op.action == "remove"
    assert op.target == "completeness"
    assert op.before == {"kind": "completeness"}
    assert op.after is None


# ---------------------------------------------------------------------------
# planner — input-port removal Op carries the full prior-state before dict
# (kills the four key-rename mutants on the removal before dict)
# ---------------------------------------------------------------------------


def test_plan_input_port_removal_before_dict() -> None:
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_rm",
            "input_ports": [
                {"name": "keep", "kind": "external"},
                {
                    "name": "drop",
                    "kind": "upstream_product",
                    "source_ref": "other.cat",
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
            "input_ports": [{"name": "keep", "kind": "external"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    op = next(o for o in plan.removals if o.target == "drop")
    assert op.before == {
        "name": "drop",
        "kind": "upstream_product",
        "source_ref": "other.cat",
        "description": "going away",
    }
    assert op.after is None


# ---------------------------------------------------------------------------
# planner — output-port removal Op carries the full _output_port_dict, and
# decodes a stored identity_requirements JSON string (kills before=None on
# removal and ``json.loads(None)`` in _output_port_dict)
# ---------------------------------------------------------------------------


def _set_output_port_identity(schema: str, port_name: str, payload: dict) -> None:
    with _factory()() as session:
        row = (
            session.query(DataProductOutputPort)
            .filter(DataProductOutputPort.name == port_name)
            .one()
        )
        row.identity_requirements = json.dumps(payload)
        session.commit()


def test_plan_output_port_removal_before_dict_decodes_identity() -> None:
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "op_rm",
            "output_ports": [
                {"name": "keep", "kind": "sql"},
                {
                    "name": "drop",
                    "kind": "file",
                    "description": "bye",
                    "format": "csv",
                    "location": "/lake/drop",
                },
            ],
        }
    )
    _apply(spec_two)
    # The applier does not persist identity_requirements; seed it directly
    # on the stored row so the removal path must JSON-decode it.
    _set_output_port_identity("op_rm", "drop", {"scope": "pii"})
    spec_one = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "op_rm",
            "output_ports": [{"name": "keep", "kind": "sql"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    op = next(o for o in plan.removals if o.target == "drop")
    assert op.before == {
        "name": "drop",
        "kind": "file",
        "description": "bye",
        "format": "csv",
        "location": "/lake/drop",
        "identity_requirements": {"scope": "pii"},
    }
    assert op.after is None


# ---------------------------------------------------------------------------
# planner — the diff helpers receive the live modifications / removals
# lists.  A mutant that passes None for one of these crashes plan_spec
# when that branch has to append, so a successful plan with the expected
# op proves the right list was threaded through.
# ---------------------------------------------------------------------------


def test_plan_threads_modifications_list_to_slos() -> None:
    """An SLO update must land in plan.modifications.  Kills the mutant
    that passes None as _diff_slos' modifications list (it would crash on
    append).
    """
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_thread",
            "slos": [{"kind": "freshness", "comparator": "lte", "target_value": 1.0}],
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_thread",
            "slos": [{"kind": "freshness", "comparator": "lte", "target_value": 2.0}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    assert any(o.kind == "slo" and o.action == "update" for o in plan.modifications)


def test_plan_threads_removals_list_to_entities() -> None:
    """Dropping an entity must land in plan.removals.  Kills the mutant
    passing None as _diff_entities' removals list.
    """
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ent_thread",
            "entities": [
                {"name": "A", "source_table": "ta", "primary_key_columns": ["id"]},
                {"name": "B", "source_table": "tb", "primary_key_columns": ["id"]},
            ],
        }
    )
    _apply(spec_two)
    spec_one = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ent_thread",
            "entities": [{"name": "A", "source_table": "ta", "primary_key_columns": ["id"]}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    assert any(o.kind == "entity" and o.target == "B" for o in plan.removals)


def test_plan_threads_removals_list_to_contract_tests() -> None:
    """Dropping a contract test must land in plan.removals.  Kills the
    mutant passing None as _diff_contract_tests' removals list.
    """
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ct_thread",
            "contract_tests": [
                {
                    "name": "keep",
                    "assertion_kind": "null_rate",
                    "assertion_spec": {"column": "id"},
                },
                {
                    "name": "drop",
                    "assertion_kind": "null_rate",
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
            "schema": "ct_thread",
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
    assert any(o.kind == "contract_test" and o.target == "drop" for o in plan.removals)


def test_plan_threads_removals_list_to_fixtures() -> None:
    """Dropping a fixture must land in plan.removals.  Kills the mutant
    passing None as _diff_fixtures' removals list.
    """
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_thread",
            "fixtures": [
                {"table_name": "keep", "generator_spec": [{"column": "id"}]},
                {"table_name": "drop", "generator_spec": [{"column": "id"}]},
            ],
        }
    )
    _apply(spec_two)
    spec_one = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_thread",
            "fixtures": [{"table_name": "keep", "generator_spec": [{"column": "id"}]}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    assert any(o.kind == "fixture" and o.target == "drop" for o in plan.removals)
