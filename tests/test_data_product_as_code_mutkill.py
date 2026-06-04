"""Behaviour tests targeting surviving mutants in the data-product-as-code
planner + applier.

These assert *exact* observable outputs: the field values an apply
persists (read back through ``export_data_product`` and the CRUD
listings) and the precise ``Op.before`` / ``Op.after`` dicts a plan
emits.  They are written to kill mutations that drop a field, rename a
dict key, swap an action string, or flip a comparison.
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
    export_data_product,
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
# applier — output port "add" persists every field verbatim
# ---------------------------------------------------------------------------


def test_apply_output_port_persists_all_fields() -> None:
    """The add path must carry name/kind/description/format/location.

    Kills mutants that null any of these kwargs or rename the dict
    key the value is read from.
    """
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "op_fields",
            "output_ports": [
                {
                    "name": "sql_port",
                    "kind": "sql",
                    "description": "the desc",
                    "format": "parquet",
                    "location": "/lake/sql_port",
                }
            ],
        }
    )
    _apply(spec)
    with _factory()() as session:
        row = session.query(DataProductOutputPort).one()
        assert row.name == "sql_port"
        assert row.kind == "sql"
        assert row.description == "the desc"
        assert row.format == "parquet"
        assert row.location == "/lake/sql_port"


def test_apply_output_port_update_keeps_new_field_values() -> None:
    """An update re-creates the port with the new description/format.

    Kills the update-branch field-drop mutants (delete + re-create
    path must use op.after, not stale values).
    """
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "op_update",
            "output_ports": [{"name": "sql", "kind": "sql"}],
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "op_update",
            "output_ports": [
                {
                    "name": "sql",
                    "kind": "file",
                    "description": "now described",
                    "format": "csv",
                    "location": "/lake/sql",
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    assert [op.target for op in plan.modifications] == ["sql"]
    apply_plan(_factory(), spec=spec_v2, plan=plan)
    with _factory()() as session:
        rows = session.query(DataProductOutputPort).all()
        assert len(rows) == 1
        row = rows[0]
        assert row.kind == "file"
        assert row.description == "now described"
        assert row.format == "csv"
        assert row.location == "/lake/sql"


# ---------------------------------------------------------------------------
# applier — input port "add" persists kind + source_ref + description
# ---------------------------------------------------------------------------


def test_apply_input_port_persists_all_fields() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_fields",
            "input_ports": [
                {
                    "name": "upstream",
                    "kind": "upstream_product",
                    "source_ref": "other.catalog",
                    "description": "feeds us",
                }
            ],
        }
    )
    _apply(spec)
    with _factory()() as session:
        row = session.query(DataProductInputPort).one()
        assert row.name == "upstream"
        assert row.kind == "upstream_product"
        assert row.source_ref == "other.catalog"
        assert row.description == "feeds us"


# ---------------------------------------------------------------------------
# applier — slo "add" persists target_value + table + comparator
# ---------------------------------------------------------------------------


def test_apply_slo_persists_target_table_and_comparator() -> None:
    """Kills the ``table_name=None`` and comparator/target-drop mutants."""
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_fields",
            "slos": [
                {
                    "kind": "freshness",
                    "comparator": "gte",
                    "target_value": 42.0,
                    "table": "events",
                }
            ],
        }
    )
    _apply(spec)
    with _factory()() as session:
        row = session.query(DataProductSLO).one()
        assert row.slo_kind == "freshness"
        assert row.comparator == "gte"
        assert row.target_value == 42.0
        assert row.table_name == "events"


# ---------------------------------------------------------------------------
# applier — entity "add" persists source_table + primary_key_columns
# ---------------------------------------------------------------------------


def test_apply_entity_persists_source_table_and_pk() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ent_fields",
            "entities": [
                {
                    "name": "Customer",
                    "source_table": "cust_master",
                    "primary_key_columns": ["id", "region"],
                    "description": "the customer entity",
                }
            ],
        }
    )
    _apply(spec)
    with _factory()() as session:
        row = session.query(DataProductEntity).one()
        assert row.entity_name == "Customer"
        assert row.source_table == "cust_master"
    # Read back through the exporter to confirm the PK list survives the
    # JSON round-trip in declared order.
    exported = export_data_product(_factory(), catalog="dpac", schema="ent_fields")
    assert len(exported.entities) == 1
    ent = exported.entities[0]
    assert ent.name == "Customer"
    assert ent.source_table == "cust_master"
    assert ent.primary_key_columns == ["id", "region"]
    assert ent.description == "the customer entity"


# ---------------------------------------------------------------------------
# applier — contract test + fixture "add" persist their payloads
# ---------------------------------------------------------------------------


def test_apply_contract_test_persists_payload() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ct_fields",
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
    _apply(spec)
    exported = export_data_product(_factory(), catalog="dpac", schema="ct_fields")
    assert len(exported.contract_tests) == 1
    test = exported.contract_tests[0]
    assert test.name == "null_rate_id"
    assert test.assertion_kind == "null_rate"
    assert test.assertion_spec == {"column": "id"}
    assert test.severity == "error"
    assert test.enabled is False


def test_apply_fixture_persists_row_count_and_generator() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_fields",
            "fixtures": [
                {
                    "table_name": "seed_tbl",
                    "generator_spec": [{"column": "id", "type": "int"}],
                    "row_count": 7,
                }
            ],
        }
    )
    _apply(spec)
    with _factory()() as session:
        row = session.query(DataProductFixture).one()
        assert row.table_name == "seed_tbl"
        assert int(row.row_count) == 7
    exported = export_data_product(_factory(), catalog="dpac", schema="fx_fields")
    fx = exported.fixtures[0]
    assert fx.generator_spec == [{"column": "id", "type": "int"}]
    assert fx.row_count == 7


# ---------------------------------------------------------------------------
# applier — policies "add" maps every field; linked_policy_module_ids
# is special-cased
# ---------------------------------------------------------------------------


def test_apply_policies_writes_each_field_value() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "pol_fields",
            "policies": {
                "retention_days": 30,
                "encryption_class": "at_rest",
                "residency_region": "eu",
                "consent_required": True,
                "linked_policy_module_ids": [3, 9],
            },
        }
    )
    _apply(spec)
    with _factory()() as session:
        row = session.query(DataProductPolicy).one()
        assert row.retention_days == 30
        assert row.encryption_class == "at_rest"
        assert row.residency_region == "eu"
        assert row.consent_required is True
        # linked_policy_module_ids is JSON-encoded by the applier before
        # the write; the persisted column is the encoded list.
        assert row.linked_policy_module_ids == "[3, 9]"


def test_export_round_trips_linked_policy_module_ids() -> None:
    """A product with linked policy modules exports without raising.

    Regression: ``linked_policy_module_ids`` is persisted as a JSON
    string, and the exporter feeds the policy payload straight into
    ``PolicySpec`` (typed ``list[int] | None``).  The raw string used to
    trip a pydantic ``ValidationError``, so any product with linked policy
    modules was un-exportable and its plan diff was permanently dirty.
    ``get_product_policy`` now decodes the field back to a list.
    """
    spec = parse_spec(
        {
            "name": "Linked",
            "catalog": "dpac",
            "schema": "linked_pol",
            "policies": {"linked_policy_module_ids": [3, 9]},
        }
    )
    _apply(spec)
    exported = export_data_product(_factory(), catalog="dpac", schema="linked_pol")
    assert exported.policies is not None
    assert exported.policies.linked_policy_module_ids == [3, 9]


# ---------------------------------------------------------------------------
# applier — ensure_product writes the contract name / description so the
# exporter recovers the product name from contract_json
# ---------------------------------------------------------------------------


def test_apply_product_name_recovered_via_contract_json() -> None:
    """The product name lives only in contract_json; export reads it back.

    Kills mutants that rename the ``name`` key in the contract dict or
    drop the description.
    """
    spec = parse_spec(
        {
            "name": "Pretty Name",
            "catalog": "dpac",
            "schema": "prod_name",
            "description": "a product description",
            "output_ports": [{"name": "sql", "kind": "sql"}],
        }
    )
    _apply(spec)
    exported = export_data_product(_factory(), catalog="dpac", schema="prod_name")
    assert exported.name == "Pretty Name"
    assert exported.description == "a product description"


def test_apply_uses_workspace_id_in_lookup() -> None:
    """A product seeded under workspace 1 is found and updated, not duplicated.

    Kills the ensure_product workspace_id/catalog/schema filter mutants:
    a broken filter would insert a second row instead of updating.
    """
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ws_lookup",
            "description": "v1",
        }
    )
    _apply(spec)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ws_lookup",
            "description": "v2",
        }
    )
    _apply(spec_v2)
    with _factory()() as session:
        rows = session.query(DataProduct).all()
        assert len(rows) == 1
        assert rows[0].description == "v2"


# ---------------------------------------------------------------------------
# planner — exact addition Op.after dicts (kills model_dump-drop, action
# string swaps, target swaps)
# ---------------------------------------------------------------------------


def test_plan_output_port_addition_op_shape() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "plan_op",
            "output_ports": [{"name": "sql", "kind": "sql", "description": "d", "format": "f"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    op = next(o for o in plan.additions if o.kind == "output_port")
    assert op.action == "add"
    assert op.target == "sql"
    assert op.before is None
    assert op.after == {
        "name": "sql",
        "kind": "sql",
        "description": "d",
        "format": "f",
        "location": None,
        "identity_requirements": None,
    }


def test_plan_slo_addition_op_shape() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "plan_slo",
            "slos": [{"kind": "freshness", "comparator": "lte", "target_value": 5.0}],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    op = next(o for o in plan.additions if o.kind == "slo")
    assert op.action == "add"
    assert op.target == "freshness"
    assert op.after["kind"] == "freshness"
    assert op.after["comparator"] == "lte"
    assert op.after["target_value"] == 5.0


# ---------------------------------------------------------------------------
# planner — modification Op carries the exact prior-state ``before`` dict
# (kills the _*_dict key-rename + field-source mutants and the != guard)
# ---------------------------------------------------------------------------


def test_plan_output_port_modification_before_dict() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "mod_before",
            "output_ports": [{"name": "sql", "kind": "sql", "description": "old"}],
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "mod_before",
            "output_ports": [{"name": "sql", "kind": "sql", "description": "new"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    op = next(o for o in plan.modifications if o.kind == "output_port")
    assert op.action == "update"
    assert op.before == {
        "name": "sql",
        "kind": "sql",
        "description": "old",
        "format": None,
        "location": None,
        "identity_requirements": None,
    }
    assert op.after["description"] == "new"


def test_plan_input_port_modification_before_dict() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_mod",
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
            "schema": "ip_mod",
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
    op = next(o for o in plan.modifications if o.kind == "input_port")
    assert op.before == {
        "name": "src",
        "kind": "external",
        "source_ref": "ref-1",
        "description": "old",
    }
    assert op.after["source_ref"] == "ref-2"


def test_plan_entity_modification_before_dict() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ent_mod",
            "entities": [
                {
                    "name": "E",
                    "source_table": "t1",
                    "primary_key_columns": ["a"],
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
            "schema": "ent_mod",
            "entities": [
                {
                    "name": "E",
                    "source_table": "t2",
                    "primary_key_columns": ["a", "b"],
                    "description": "new",
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    op = next(o for o in plan.modifications if o.kind == "entity")
    assert op.before == {
        "name": "E",
        "source_table": "t1",
        "primary_key_columns": ["a"],
        "description": "old",
    }
    assert op.after["source_table"] == "t2"
    assert op.after["primary_key_columns"] == ["a", "b"]


def test_plan_contract_test_modification_before_dict() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ct_mod",
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
            "schema": "ct_mod",
            "contract_tests": [
                {
                    "name": "ct",
                    "assertion_kind": "null_rate",
                    "assertion_spec": {"column": "id"},
                    "severity": "error",
                    "enabled": False,
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    op = next(o for o in plan.modifications if o.kind == "contract_test")
    assert op.before == {
        "name": "ct",
        "assertion_kind": "null_rate",
        "assertion_spec": {"column": "id"},
        "severity": "warn",
        "enabled": True,
    }
    assert op.after["severity"] == "error"
    assert op.after["enabled"] is False


def test_plan_fixture_modification_before_dict() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "fx_mod",
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
            "schema": "fx_mod",
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
    op = next(o for o in plan.modifications if o.kind == "fixture")
    assert op.before == {
        "table_name": "t",
        "generator_spec": [{"column": "id"}],
        "row_count": 3,
    }
    assert op.after["row_count"] == 9


# ---------------------------------------------------------------------------
# planner — SLO unit-fallback: when the spec omits unit, the planner
# inherits the stored unit so the round-trip is a no-op (kills the
# ``desired.get("unit")`` key mutants and the fallback assignment)
# ---------------------------------------------------------------------------


def test_plan_slo_unit_fallback_yields_noop() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_unit",
            "slos": [{"kind": "freshness", "comparator": "lte", "target_value": 1.0}],
        }
    )
    _apply(spec)
    # Second plan against the same spec (unit omitted) must inherit the
    # persisted unit and emit no modification.
    plan = plan_spec(_factory(), spec=spec)
    slo_mods = [o for o in plan.modifications if o.kind == "slo"]
    assert slo_mods == []


# ---------------------------------------------------------------------------
# planner — diff_policies emits an update only for changed fields, and the
# before/after dicts cover exactly the changed keys
# ---------------------------------------------------------------------------


def test_plan_policies_modification_only_changed_fields() -> None:
    spec_v1 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "pol_mod",
            "policies": {"retention_days": 30, "encryption_class": "at_rest"},
        }
    )
    _apply(spec_v1)
    spec_v2 = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "pol_mod",
            "policies": {"retention_days": 90, "encryption_class": "at_rest"},
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    op = next(o for o in plan.modifications if o.kind == "policies")
    assert op.action == "update"
    # Only retention_days changed.
    assert op.before == {"retention_days": 30}
    assert op.after == {"retention_days": 90}


def test_plan_policies_noop_when_unchanged() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "pol_noop",
            "policies": {"retention_days": 30},
        }
    )
    _apply(spec)
    plan = plan_spec(_factory(), spec=spec)
    assert [o for o in plan.modifications if o.kind == "policies"] == []


# ---------------------------------------------------------------------------
# planner — product_id resolves to 0 (not a real id) when the product is
# absent, so live-row queries short-circuit to empty.  A leaked id would
# bleed another product's rows into the plan.
# ---------------------------------------------------------------------------


def test_plan_absent_product_does_not_borrow_other_rows() -> None:
    """Kills the ``else 0`` -> ``else 1`` product_id default mutant.

    Seed a real product (id will be 1) with an output port, then plan a
    *different* product that does not exist.  If the absent-product
    branch used id=1 it would diff against the seeded product's ports
    and emit spurious removals.
    """
    seeded = parse_spec(
        {
            "name": "Seeded",
            "catalog": "dpac",
            "schema": "seeded",
            "output_ports": [{"name": "real_port", "kind": "sql"}],
        }
    )
    _apply(seeded)
    absent = parse_spec(
        {
            "name": "Absent",
            "catalog": "dpac",
            "schema": "absent",
            "output_ports": [{"name": "wanted", "kind": "sql"}],
        }
    )
    plan = plan_spec(_factory(), spec=absent)
    assert plan.product_present is False
    # No removals at all — the absent product has no live rows to remove.
    assert plan.removals == []
    # Exactly one output-port addition, for the wanted port only.
    op_targets = {o.target for o in plan.additions if o.kind == "output_port"}
    assert op_targets == {"wanted"}


# ---------------------------------------------------------------------------
# applier — dry run never writes; apply count is exact
# ---------------------------------------------------------------------------


def test_dry_run_reports_total_without_writing() -> None:
    spec = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "dry",
            "output_ports": [{"name": "sql", "kind": "sql"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    outcome = apply_plan(_factory(), spec=spec, plan=plan, dry_run=True)
    assert outcome.dry_run is True
    assert outcome.total == plan.op_count()
    assert outcome.applied == 0
    with _factory()() as session:
        assert session.query(DataProduct).count() == 0


# ---------------------------------------------------------------------------
# applier — removal ops actually delete the live row
# ---------------------------------------------------------------------------


def test_apply_removes_dropped_input_port() -> None:
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_remove",
            "input_ports": [
                {"name": "a", "kind": "external"},
                {"name": "b", "kind": "external"},
            ],
        }
    )
    _apply(spec_two)
    spec_one = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "ip_remove",
            "input_ports": [{"name": "a", "kind": "external"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    assert any(o.target == "b" for o in plan.removals)
    apply_plan(_factory(), spec=spec_one, plan=plan)
    with _factory()() as session:
        names = {r.name for r in session.query(DataProductInputPort).all()}
        assert names == {"a"}


def test_apply_removes_dropped_slo() -> None:
    spec_two = parse_spec(
        {
            "name": "P",
            "catalog": "dpac",
            "schema": "slo_remove",
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
            "schema": "slo_remove",
            "slos": [{"kind": "freshness", "target_value": 1.0}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one)
    assert any(o.target == "completeness" for o in plan.removals if o.kind == "slo")
    apply_plan(_factory(), spec=spec_one, plan=plan)
    with _factory()() as session:
        kinds = {r.slo_kind for r in session.query(DataProductSLO).all()}
        assert kinds == {"freshness"}
