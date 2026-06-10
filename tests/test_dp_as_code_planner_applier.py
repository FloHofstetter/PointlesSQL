"""Planner + applier round-trip (Phase 143)."""

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


def _wipe():
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


def test_plan_against_empty_db_adds_everything() -> None:
    spec = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "plan_add",
            "output_ports": [{"name": "sql", "kind": "sql"}],
            "input_ports": [{"name": "iot", "kind": "operational_system"}],
            "slos": [{"kind": "freshness", "target_value": 60.0}],
            "entities": [
                {
                    "name": "Customer",
                    "source_table": "customer_master",
                    "primary_key_columns": ["id"],
                }
            ],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    assert plan.product_present is False
    kinds = {op.kind for op in plan.additions}
    assert "product" in kinds
    assert "output_port" in kinds
    assert "input_port" in kinds
    assert "slo" in kinds
    assert "entity" in kinds
    assert plan.modifications == []
    assert plan.removals == []


def test_apply_creates_product_and_subentities() -> None:
    spec = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "apply_add",
            "output_ports": [{"name": "sql", "kind": "sql"}],
            "slos": [{"kind": "freshness", "target_value": 60.0, "comparator": "lte"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    outcome = apply_plan(_factory(), spec=spec, plan=plan)
    assert outcome.dry_run is False
    assert outcome.applied >= 3
    assert outcome.errors == []
    with _factory()() as session:
        product = session.query(DataProduct).one()
        assert product.catalog_name == "dpac"
        assert product.schema_name == "apply_add"
        ports = session.query(DataProductOutputPort).all()
        assert len(ports) == 1


def test_dry_run_makes_no_writes() -> None:
    spec = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "dry_run",
            "output_ports": [{"name": "sql", "kind": "sql"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec)
    outcome = apply_plan(_factory(), spec=spec, plan=plan, dry_run=True)
    assert outcome.dry_run is True
    assert outcome.applied == 0
    with _factory()() as session:
        assert session.query(DataProduct).count() == 0


def test_apply_is_idempotent_on_repeat() -> None:
    spec = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "idempotent",
            "output_ports": [{"name": "sql", "kind": "sql"}],
            "input_ports": [{"name": "iot", "kind": "operational_system"}],
            "slos": [{"kind": "freshness", "target_value": 30.0, "comparator": "lte"}],
        }
    )
    plan_one = plan_spec(_factory(), spec=spec)
    apply_plan(_factory(), spec=spec, plan=plan_one)
    plan_two = plan_spec(_factory(), spec=spec)
    assert plan_two.is_noop() is True


def test_remove_op_emitted_when_db_has_extra_port() -> None:
    spec_with_port = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "removal",
            "output_ports": [
                {"name": "sql", "kind": "sql"},
                {"name": "events", "kind": "event"},
            ],
        }
    )
    apply_plan(
        _factory(),
        spec=spec_with_port,
        plan=plan_spec(_factory(), spec=spec_with_port),
    )
    spec_one_port = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "removal",
            "output_ports": [{"name": "sql", "kind": "sql"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_one_port)
    assert any(op.target == "events" for op in plan.removals)
    apply_plan(_factory(), spec=spec_one_port, plan=plan)
    with _factory()() as session:
        ports = session.query(DataProductOutputPort).all()
        assert {p.name for p in ports} == {"sql"}


def test_modification_op_emitted_when_field_diverges() -> None:
    spec_v1 = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "mod",
            "output_ports": [{"name": "sql", "kind": "sql"}],
        }
    )
    apply_plan(_factory(), spec=spec_v1, plan=plan_spec(_factory(), spec=spec_v1))
    spec_v2 = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "mod",
            "output_ports": [{"name": "sql", "kind": "sql", "description": "new note"}],
        }
    )
    plan = plan_spec(_factory(), spec=spec_v2)
    assert any(op.target == "sql" for op in plan.modifications)


def test_export_round_trip_yields_noop_plan() -> None:
    spec = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "round_trip",
            "output_ports": [{"name": "sql", "kind": "sql"}],
            "slos": [{"kind": "completeness", "target_value": 0.95, "comparator": "gte"}],
            "entities": [
                {
                    "name": "Customer",
                    "source_table": "customer_master",
                    "primary_key_columns": ["id"],
                }
            ],
        }
    )
    apply_plan(_factory(), spec=spec, plan=plan_spec(_factory(), spec=spec))
    exported = export_data_product(_factory(), catalog="dpac", schema="round_trip")
    plan = plan_spec(_factory(), spec=exported)
    assert plan.is_noop() is True


def test_export_unknown_product_raises_lookup_error() -> None:
    with pytest.raises(LookupError):
        export_data_product(_factory(), catalog="nope", schema="nope")


def test_apply_policies_field_writes_product_policy() -> None:
    spec = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "policies",
            "policies": {"retention_days": 30, "encryption_class": "at_rest"},
        }
    )
    apply_plan(_factory(), spec=spec, plan=plan_spec(_factory(), spec=spec))
    with _factory()() as session:
        rows = session.query(DataProductPolicy).all()
        assert len(rows) == 1
        assert rows[0].retention_days == 30
        assert rows[0].encryption_class == "at_rest"


def test_export_emits_policies_when_present() -> None:
    spec = parse_spec(
        {
            "name": "Customers",
            "catalog": "dpac",
            "schema": "export_policy",
            "policies": {"retention_days": 90},
        }
    )
    apply_plan(_factory(), spec=spec, plan=plan_spec(_factory(), spec=spec))
    exported = export_data_product(_factory(), catalog="dpac", schema="export_policy")
    assert exported.policies is not None
    assert exported.policies.retention_days == 90
