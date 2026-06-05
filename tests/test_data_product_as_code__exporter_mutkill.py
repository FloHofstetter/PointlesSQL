"""Behaviour tests targeting surviving mutants in the data-product-as-code
exporter (``export_data_product`` + ``_extract_name``).

Each test asserts an *exact* observable output of
``export_data_product`` — the per-port / per-SLO / per-entity field
values, the ordering of each listing, the pipeline round-trip, the
``policies is None`` short-circuit, and the contract-name fallback.
They kill mutants that null a field, drop a kwarg, remove a SQL
``order_by`` / ``where`` filter, flip a comparison, or short-circuit a
branch.
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
    export_data_product,
    parse_spec,
    plan_spec,
)
from pointlessql.services.dp_canvas import CanvasDoc, CanvasNode, save_graph


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


def _product_id(catalog: str, schema: str) -> int:
    with _factory()() as session:
        row = (
            session.query(DataProduct)
            .filter(DataProduct.catalog_name == catalog)
            .filter(DataProduct.schema_name == schema)
            .one()
        )
        return int(row.id)


# ---------------------------------------------------------------------------
# _extract_name — the ``isinstance(decoded, dict) and decoded.get("name")``
# guard short-circuits to the default when the contract JSON is not a
# name-bearing dict.
# ---------------------------------------------------------------------------


def test_export_falls_back_to_default_name_when_contract_has_no_name() -> None:
    """A contract dict without a ``name`` key falls back to catalog.schema.

    Kills the ``and`` -> ``or`` flip in ``_extract_name``: with ``or`` a
    name-less dict would take the truthy ``isinstance`` branch and raise
    a ``KeyError`` reading ``decoded["name"]`` instead of returning the
    default.  Also kills the ``default=None`` call-site mutant, which
    would make ``name`` ``None`` and fail ``DataProductSpec`` validation.
    """
    _apply(
        parse_spec(
            {
                "name": "Original",
                "catalog": "dpac",
                "schema": "no_name",
                "output_ports": [{"name": "sql", "kind": "sql"}],
            }
        )
    )
    # Overwrite the stored contract JSON with a dict that has no name.
    with _factory()() as session:
        row = session.query(DataProduct).filter(DataProduct.schema_name == "no_name").one()
        row.contract_json = json.dumps({"version": "1.0.0"})
        session.commit()
    exported = export_data_product(_factory(), catalog="dpac", schema="no_name")
    assert exported.name == "dpac.no_name"


def test_export_recovers_name_from_contract_dict() -> None:
    """A name-bearing contract dict yields that exact name (not the default)."""
    _apply(
        parse_spec(
            {
                "name": "The Real Name",
                "catalog": "dpac",
                "schema": "has_name",
                "output_ports": [{"name": "sql", "kind": "sql"}],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="has_name")
    assert exported.name == "The Real Name"


# ---------------------------------------------------------------------------
# export — missing product raises LookupError with the catalog.schema in
# the message.
# ---------------------------------------------------------------------------


def test_export_missing_product_raises_lookup_error_with_identity() -> None:
    """Kills the ``LookupError(None)`` message-drop mutant.

    The message must name the catalog.schema that was not found.
    """
    with pytest.raises(LookupError) as excinfo:
        export_data_product(_factory(), catalog="dpac", schema="nope")
    assert "dpac.nope" in str(excinfo.value)


# ---------------------------------------------------------------------------
# export — output port carries every field verbatim, including
# identity_requirements decoded from its JSON string.
# ---------------------------------------------------------------------------


def test_export_output_port_carries_all_scalar_fields() -> None:
    """description / format / location must survive the export read-back.

    Kills the ``description=None`` / ``format=None`` / ``location=None``
    null-and-drop mutants on ``OutputPortSpec``.
    """
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "op_export",
                "output_ports": [
                    {
                        "name": "sql_port",
                        "kind": "file",
                        "description": "described",
                        "format": "parquet",
                        "location": "/lake/sql_port",
                    }
                ],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="op_export")
    assert len(exported.output_ports) == 1
    port = exported.output_ports[0]
    assert port.name == "sql_port"
    assert port.kind == "file"
    assert port.description == "described"
    assert port.format == "parquet"
    assert port.location == "/lake/sql_port"


def test_export_output_port_decodes_identity_requirements() -> None:
    """A JSON-encoded identity_requirements string round-trips to a dict.

    Kills the ``identity_requirements=None`` drop and the
    ``json.loads(None)`` mutant (the latter raises ``TypeError``).
    """
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "op_idreq",
                "output_ports": [{"name": "sql", "kind": "sql"}],
            }
        )
    )
    # The applier does not persist identity_requirements; set it directly
    # so the exporter's decode branch is exercised.
    with _factory()() as session:
        row = session.query(DataProductOutputPort).one()
        row.identity_requirements = json.dumps({"scope": "pii", "level": 2})
        session.commit()
    exported = export_data_product(_factory(), catalog="dpac", schema="op_idreq")
    port = exported.output_ports[0]
    assert port.identity_requirements == {"scope": "pii", "level": 2}


def test_export_output_ports_ordered_by_name() -> None:
    """Output ports come back sorted by name.

    Kills the ``order_by(None)`` mutant: insertion order here is the
    reverse of name order, so a dropped sort surfaces.
    """
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "op_order",
                "output_ports": [
                    {"name": "zeta", "kind": "sql"},
                    {"name": "alpha", "kind": "sql"},
                    {"name": "mike", "kind": "sql"},
                ],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="op_order")
    assert [p.name for p in exported.output_ports] == ["alpha", "mike", "zeta"]


# ---------------------------------------------------------------------------
# export — input port fields + ordering + product-scoped filter.
# ---------------------------------------------------------------------------


def test_export_input_port_carries_all_fields() -> None:
    """name / kind / source_ref / description must round-trip.

    Kills the input-port null-and-drop mutants; nulling the required
    ``name`` / ``kind`` would raise a validation error, and nulling
    ``source_ref`` / ``description`` is caught by the value assertion.
    """
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "ip_export",
                "input_ports": [
                    {
                        "name": "upstream",
                        "kind": "upstream_product",
                        "source_ref": "other.catalog.tbl",
                        "description": "feeds us",
                    }
                ],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="ip_export")
    assert len(exported.input_ports) == 1
    port = exported.input_ports[0]
    assert port.name == "upstream"
    assert port.kind == "upstream_product"
    assert port.source_ref == "other.catalog.tbl"
    assert port.description == "feeds us"


def test_export_input_ports_ordered_by_name() -> None:
    """Input ports come back sorted by name (kills ``order_by(None)``)."""
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "ip_order",
                "input_ports": [
                    {"name": "yankee", "kind": "external"},
                    {"name": "bravo", "kind": "external"},
                    {"name": "kilo", "kind": "external"},
                ],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="ip_order")
    assert [p.name for p in exported.input_ports] == ["bravo", "kilo", "yankee"]


def test_export_input_ports_scoped_to_requested_product() -> None:
    """Only the requested product's input ports are exported.

    Kills the ``select(None)`` / ``where(None)`` / ``where(... != ...)``
    mutants on the input-port query: a broken filter would bleed another
    product's ports in (or return the wrong product's ports entirely).
    """
    _apply(
        parse_spec(
            {
                "name": "A",
                "catalog": "dpac",
                "schema": "ip_scope_a",
                "input_ports": [{"name": "a_only", "kind": "external"}],
            }
        )
    )
    _apply(
        parse_spec(
            {
                "name": "B",
                "catalog": "dpac",
                "schema": "ip_scope_b",
                "input_ports": [{"name": "b_only", "kind": "external"}],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="ip_scope_a")
    assert [p.name for p in exported.input_ports] == ["a_only"]


# ---------------------------------------------------------------------------
# export — SLO fields (table, unit) + ordering.
# ---------------------------------------------------------------------------


def test_export_slo_carries_table_and_unit() -> None:
    """SLO ``table`` and ``unit`` must round-trip.

    Kills the ``table=None`` / ``unit=None`` null-and-drop mutants.  The
    applier does not persist ``unit``, so it is set directly on the row.
    """
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "slo_export",
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
    )
    with _factory()() as session:
        row = session.query(DataProductSLO).one()
        row.unit = "minutes"
        session.commit()
    exported = export_data_product(_factory(), catalog="dpac", schema="slo_export")
    assert len(exported.slos) == 1
    slo = exported.slos[0]
    assert slo.table == "events"
    assert slo.unit == "minutes"


def test_export_slos_ordered_by_kind() -> None:
    """SLOs come back sorted by slo_kind (kills ``order_by(None)``)."""
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "slo_order",
                "slos": [
                    {"kind": "volume", "target_value": 1.0},
                    {"kind": "completeness", "target_value": 0.9, "comparator": "gte"},
                    {"kind": "freshness", "target_value": 2.0},
                ],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="slo_order")
    assert [s.kind for s in exported.slos] == [
        "completeness",
        "freshness",
        "volume",
    ]


# ---------------------------------------------------------------------------
# export — entity ordering.
# ---------------------------------------------------------------------------


def test_export_entities_ordered_by_name() -> None:
    """Entities come back sorted by entity_name (kills ``order_by(None)``)."""
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "ent_order",
                "entities": [
                    {
                        "name": "Zoo",
                        "source_table": "t_zoo",
                        "primary_key_columns": ["id"],
                    },
                    {
                        "name": "Apple",
                        "source_table": "t_apple",
                        "primary_key_columns": ["id"],
                    },
                    {
                        "name": "Mango",
                        "source_table": "t_mango",
                        "primary_key_columns": ["id"],
                    },
                ],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="ent_order")
    assert [e.name for e in exported.entities] == ["Apple", "Mango", "Zoo"]


# ---------------------------------------------------------------------------
# export — contract test enabled flag + ordering.
# ---------------------------------------------------------------------------


def test_export_contract_test_preserves_enabled_true() -> None:
    """An enabled contract test exports ``enabled=True``.

    Kills the ``bool(None)`` mutant, which would force every exported
    contract test to ``enabled=False``.
    """
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "ct_enabled",
                "contract_tests": [
                    {
                        "name": "ct_on",
                        "assertion_kind": "null_rate",
                        "assertion_spec": {"column": "id"},
                        "severity": "warn",
                        "enabled": True,
                    }
                ],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="ct_enabled")
    assert len(exported.contract_tests) == 1
    assert exported.contract_tests[0].enabled is True


def test_export_contract_tests_ordered_by_name() -> None:
    """Contract tests come back sorted by name (kills ``order_by(None)``)."""
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "ct_order",
                "contract_tests": [
                    {
                        "name": "yvonne",
                        "assertion_kind": "null_rate",
                        "assertion_spec": {"column": "id"},
                    },
                    {
                        "name": "boris",
                        "assertion_kind": "null_rate",
                        "assertion_spec": {"column": "id"},
                    },
                    {
                        "name": "karl",
                        "assertion_kind": "null_rate",
                        "assertion_spec": {"column": "id"},
                    },
                ],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="ct_order")
    assert [t.name for t in exported.contract_tests] == ["boris", "karl", "yvonne"]


# ---------------------------------------------------------------------------
# export — fixture ordering.
# ---------------------------------------------------------------------------


def test_export_fixtures_ordered_by_table_name() -> None:
    """Fixtures come back sorted by table_name (kills ``order_by(None)``)."""
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "fx_order",
                "fixtures": [
                    {"table_name": "zulu", "generator_spec": [], "row_count": 1},
                    {"table_name": "alpha", "generator_spec": [], "row_count": 1},
                    {"table_name": "november", "generator_spec": [], "row_count": 1},
                ],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="fx_order")
    assert [f.table_name for f in exported.fixtures] == [
        "alpha",
        "november",
        "zulu",
    ]


# ---------------------------------------------------------------------------
# export — policies short-circuit: no policy row means policies is None.
# ---------------------------------------------------------------------------


def test_export_without_policy_yields_none_policies() -> None:
    """A product with no policy override exports ``policies is None``.

    Kills the ``is not None`` -> ``is None`` flip on the
    ``any(...)`` guard: with the flip, an all-``None`` policy payload
    (no policy row) would build a non-``None`` all-``None`` ``PolicySpec``.
    """
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "no_policy",
                "output_ports": [{"name": "sql", "kind": "sql"}],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="no_policy")
    assert exported.policies is None


def test_export_with_policy_yields_populated_policies() -> None:
    """A product with a policy override exports the populated PolicySpec."""
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "with_policy",
                "policies": {"retention_days": 30},
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="with_policy")
    assert exported.policies is not None
    assert exported.policies.retention_days == 30


# ---------------------------------------------------------------------------
# export — input_ports are wired into the returned spec (not dropped).
# ---------------------------------------------------------------------------


def test_export_spec_includes_input_ports_field() -> None:
    """The returned spec must carry the built ``input_ports`` list.

    Kills the mutant that drops ``input_ports=input_ports`` from the
    ``DataProductSpec`` constructor (which would default it to ``[]``).
    """
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "ip_wired",
                "input_ports": [{"name": "src", "kind": "external"}],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="ip_wired")
    assert [p.name for p in exported.input_ports] == ["src"]


# ---------------------------------------------------------------------------
# export — canvas pipeline round-trip.
# ---------------------------------------------------------------------------


def test_export_includes_saved_canvas_pipeline() -> None:
    """A saved canvas graph is loaded into the exported ``pipeline``.

    Kills the cluster of pipeline mutants: ``latest = None``,
    ``data_product_id=None`` (no rows), ``pipeline = None``,
    ``from_canvas_doc(None|latest[1])`` (both raise), and
    ``pipeline=None`` in the constructor.  All of them either drop the
    pipeline or raise instead of returning the saved node.
    """
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "pipe",
                "output_ports": [{"name": "sql", "kind": "sql"}],
            }
        )
    )
    pid = _product_id("dpac", "pipe")
    doc = CanvasDoc(
        nodes=[CanvasNode(id="n1", block_type="source", config={"k": "v"})],
        edges=[],
    )
    save_graph(_factory(), data_product_id=pid, doc=doc, author_user_id=None)
    exported = export_data_product(_factory(), catalog="dpac", schema="pipe")
    assert exported.pipeline is not None
    assert [n.id for n in exported.pipeline.nodes] == ["n1"]
    assert exported.pipeline.nodes[0].type == "source"


def test_export_without_pipeline_leaves_pipeline_none() -> None:
    """No saved graph means ``pipeline is None`` in the exported spec."""
    _apply(
        parse_spec(
            {
                "name": "P",
                "catalog": "dpac",
                "schema": "no_pipe",
                "output_ports": [{"name": "sql", "kind": "sql"}],
            }
        )
    )
    exported = export_data_product(_factory(), catalog="dpac", schema="no_pipe")
    assert exported.pipeline is None
