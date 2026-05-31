"""Schema-flow propagation tests for the dp_canvas validator."""

from __future__ import annotations

from pointlessql.services.dp_canvas import (
    CanvasDoc,
    ColumnSpec,
    PinSchema,
    validate_schema_flow,
)
from tests.dp_canvas._helpers import edge, linear_doc, node


def _table_schema(*cols: tuple[str, str]) -> PinSchema:
    return PinSchema(
        kind="table",
        columns=[ColumnSpec(name=n, duckdb_type=t, nullable=True) for n, t in cols],
    )


def test_valid_chain_propagates_input_schema() -> None:
    doc = linear_doc("main.s.src", "main.s.tgt")
    seeds = {"inp": _table_schema(("id", "BIGINT"), ("amount", "DOUBLE"))}
    per_pin, errors = validate_schema_flow(doc, seed_schemas=seeds)
    assert errors == []
    out_pin = per_pin[("out", "in")]
    assert [c.name for c in out_pin.columns] == ["id", "amount"]


def test_filter_predicate_does_not_change_schema() -> None:
    doc = linear_doc("main.s.src", "main.s.tgt", predicate="amount > 0")
    seeds = {"inp": _table_schema(("amount", "DOUBLE"))}
    per_pin, errors = validate_schema_flow(doc, seed_schemas=seeds)
    assert errors == []
    assert per_pin[("flt", "out")].columns == seeds["inp"].columns


def test_project_missing_column_surfaces_type_mismatch() -> None:
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "main.s.src"}),
            node("prj", "Project", {"columns": ["ghost"]}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[
            edge("e1", "inp", "out", "prj", "in"),
            edge("e2", "prj", "out", "out", "in"),
        ],
    )
    seeds = {"inp": _table_schema(("real_col", "BIGINT"))}
    _per_pin, errors = validate_schema_flow(doc, seed_schemas=seeds)
    assert any(e.kind == "type_mismatch" for e in errors)


def test_join_key_missing_in_both_sides_errors() -> None:
    doc = CanvasDoc(
        nodes=[
            node("a", "InputPort", {"table_fqn": "main.s.a"}),
            node("b", "InputPort", {"table_fqn": "main.s.b"}),
            node("j", "Join", {"keys": ["id"], "how": "inner"}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[
            edge("e1", "a", "out", "j", "left"),
            edge("e2", "b", "out", "j", "right"),
            edge("e3", "j", "out", "out", "in"),
        ],
    )
    seeds = {
        "a": _table_schema(("not_id", "BIGINT")),
        "b": _table_schema(("also_not_id", "VARCHAR")),
    }
    _per_pin, errors = validate_schema_flow(doc, seed_schemas=seeds)
    assert sum(1 for e in errors if e.kind == "type_mismatch") == 2


def test_group_by_adds_aggregate_columns_to_output() -> None:
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "main.s.src"}),
            node(
                "g",
                "GroupBy",
                {
                    "keys": ["country"],
                    "aggregations": [{"column": "amount", "fn": "sum", "alias": "total"}],
                },
            ),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[
            edge("e1", "inp", "out", "g", "in"),
            edge("e2", "g", "out", "out", "in"),
        ],
    )
    seeds = {"inp": _table_schema(("country", "VARCHAR"), ("amount", "DOUBLE"))}
    per_pin, errors = validate_schema_flow(doc, seed_schemas=seeds)
    assert errors == []
    out_schema = per_pin[("g", "out")]
    names = [c.name for c in out_schema.columns]
    assert "country" in names
    assert "total" in names


def test_sql_block_infers_select_star_from_upstream() -> None:
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "main.s.src"}),
            node("s", "SQL", {"query": "SELECT * FROM {{in}}"}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[
            edge("e1", "inp", "out", "s", "in"),
            edge("e2", "s", "out", "out", "in"),
        ],
    )
    seeds = {"inp": _table_schema(("id", "BIGINT"), ("amt", "DOUBLE"))}
    per_pin, errors = validate_schema_flow(doc, seed_schemas=seeds)
    assert errors == []
    schema = per_pin[("s", "out")]
    assert schema.unknown is False
    assert sorted(col.name for col in schema.columns) == ["amt", "id"]


def test_sql_block_infers_join_with_two_upstreams() -> None:
    # Self-join via {{in}} placeholder — DESCRIBE resolves to projected columns.
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "main.s.src"}),
            node(
                "s",
                "SQL",
                {
                    "query": (
                        "SELECT a.id AS id, a.amt + b.amt AS combined "
                        "FROM {{in}} a JOIN {{in}} b USING (id)"
                    ),
                },
            ),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[
            edge("e1", "inp", "out", "s", "in"),
            edge("e2", "s", "out", "out", "in"),
        ],
    )
    seeds = {"inp": _table_schema(("id", "BIGINT"), ("amt", "DOUBLE"))}
    per_pin, errors = validate_schema_flow(doc, seed_schemas=seeds)
    assert errors == []
    schema = per_pin[("s", "out")]
    assert {col.name for col in schema.columns} == {"id", "combined"}


def test_sql_block_invalid_query_surfaces_bad_config() -> None:
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "main.s.src"}),
            node("s", "SQL", {"query": "this is not valid sql"}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[
            edge("e1", "inp", "out", "s", "in"),
            edge("e2", "s", "out", "out", "in"),
        ],
    )
    seeds = {"inp": _table_schema(("id", "BIGINT"))}
    _, errors = validate_schema_flow(doc, seed_schemas=seeds)
    bad = [e for e in errors if e.kind == "bad_config" and e.node_id == "s"]
    assert bad, f"expected a bad_config error on node 's', got {errors}"


def test_sql_block_yields_unknown_when_no_upstream_and_uses_placeholder() -> None:
    doc = CanvasDoc(
        nodes=[
            node("s", "SQL", {"query": "SELECT * FROM {{in}}"}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[edge("e2", "s", "out", "out", "in")],
    )
    per_pin, _ = validate_schema_flow(doc)
    assert per_pin[("s", "out")].unknown is True


def test_cycle_detected_in_schema_flow() -> None:
    doc = CanvasDoc(
        nodes=[
            node("a", "Filter", {"predicate": "1=1"}),
            node("b", "Filter", {"predicate": "2=2"}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "c.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[
            edge("e1", "a", "out", "b", "in"),
            edge("e2", "b", "out", "a", "in"),
            edge("e3", "b", "out", "out", "in"),
        ],
    )
    _, errors = validate_schema_flow(doc)
    assert any(e.kind == "cycle" for e in errors)
