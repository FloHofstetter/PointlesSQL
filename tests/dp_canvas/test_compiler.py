"""Compiler tests for the dp_canvas package."""

from __future__ import annotations

import pytest

from pointlessql.services.dp_canvas import (
    CanvasDoc,
    compile_canvas,
    render_sql,
)
from tests.dp_canvas._helpers import edge, linear_doc, node


def test_empty_doc_errors() -> None:
    _, errors = compile_canvas(CanvasDoc(nodes=[], edges=[]))
    assert errors and errors[0].kind == "empty_doc"


def test_missing_output_port_errors() -> None:
    doc = CanvasDoc(
        nodes=[node("inp", "InputPort", {"table_fqn": "c.s.t"})],
        edges=[],
    )
    _, errors = compile_canvas(doc)
    assert any(e.kind == "output_port_count" for e in errors)


def test_multiple_output_ports_compile() -> None:
    """Two OutputPorts fan out from one source into two sinks sharing a CTE base."""
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "c.s.t"}),
            node(
                "o1",
                "OutputPort",
                {"port_name": "a", "materialized_table": "c.s.x", "mode": "overwrite"},
            ),
            node(
                "o2",
                "OutputPort",
                {"port_name": "b", "materialized_table": "c.s.y", "mode": "overwrite"},
            ),
        ],
        edges=[edge("e1", "inp", "out", "o1", "in"), edge("e2", "inp", "out", "o2", "in")],
    )
    fragment, errors = compile_canvas(doc)
    assert errors == []
    assert fragment is not None
    assert len(fragment.sinks) == 2
    assert {s.target_fqn for s in fragment.sinks} == {"c.s.x", "c.s.y"}
    assert {s.port_name for s in fragment.sinks} == {"a", "b"}
    # Both sinks share the same CTE chain; only the final SELECT differs.
    assert fragment.referenced_tables == ["c.s.t"]


def test_duplicate_sink_target_errors() -> None:
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "c.s.t"}),
            node("o1", "OutputPort", {"port_name": "a", "materialized_table": "c.s.x"}),
            node("o2", "OutputPort", {"port_name": "b", "materialized_table": "c.s.x"}),
        ],
        edges=[edge("e1", "inp", "out", "o1", "in"), edge("e2", "inp", "out", "o2", "in")],
    )
    _, errors = compile_canvas(doc)
    assert any(e.kind == "duplicate_sink" for e in errors)


def test_duplicate_sink_port_name_errors() -> None:
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "c.s.t"}),
            node("o1", "OutputPort", {"port_name": "dup", "materialized_table": "c.s.x"}),
            node("o2", "OutputPort", {"port_name": "dup", "materialized_table": "c.s.y"}),
        ],
        edges=[edge("e1", "inp", "out", "o1", "in"), edge("e2", "inp", "out", "o2", "in")],
    )
    _, errors = compile_canvas(doc)
    assert any(e.kind == "duplicate_sink" for e in errors)


def test_input_pin_wired_twice_errors() -> None:
    """Two edges landing on one input pin is a footgun, not a silent overwrite."""
    doc = CanvasDoc(
        nodes=[
            node("a", "InputPort", {"table_fqn": "c.s.a"}),
            node("b", "InputPort", {"table_fqn": "c.s.b"}),
            node("flt", "Filter", {"predicate": "1=1"}),
            node("out", "OutputPort", {"port_name": "p", "materialized_table": "c.s.t"}),
        ],
        edges=[
            edge("e1", "a", "out", "flt", "in"),
            edge("e2", "b", "out", "flt", "in"),
            edge("e_out", "flt", "out", "out", "in"),
        ],
    )
    _, errors = compile_canvas(doc)
    assert any(e.kind == "duplicate_pin" for e in errors)


def test_fanout_one_source_two_chains() -> None:
    """One source feeds two distinct downstream chains, each to its own sink."""
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "main.s.src"}),
            node("f1", "Filter", {"predicate": "amount > 0"}),
            node("f2", "Filter", {"predicate": "amount < 0"}),
            node("o1", "OutputPort", {"port_name": "pos", "materialized_table": "main.s.pos"}),
            node("o2", "OutputPort", {"port_name": "neg", "materialized_table": "main.s.neg"}),
        ],
        edges=[
            edge("e1", "inp", "out", "f1", "in"),
            edge("e2", "inp", "out", "f2", "in"),
            edge("e3", "f1", "out", "o1", "in"),
            edge("e4", "f2", "out", "o2", "in"),
        ],
    )
    fragment, errors = compile_canvas(doc)
    assert errors == []
    assert fragment is not None
    assert len(fragment.sinks) == 2
    assert fragment.referenced_tables == ["main.s.src"]


def test_simple_chain_compiles() -> None:
    doc = linear_doc("main.sales.src", "main.sales.tgt", predicate="amount > 0")
    fragment, errors = compile_canvas(doc)
    assert errors == []
    assert fragment is not None
    assert fragment.referenced_tables == ["main.sales.src"]
    assert len(fragment.sinks) == 1
    assert fragment.sinks[0].final_cte == "n2_outputport"
    rendered = render_sql(fragment, fragment.sinks[0])
    assert "WITH" in rendered
    assert "n0_inputport" in rendered
    assert "n1_filter" in rendered


def test_cycle_detected() -> None:
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
            edge("e_out", "b", "out", "out", "in"),
        ],
    )
    _, errors = compile_canvas(doc)
    assert any(e.kind == "cycle" for e in errors)


def test_unknown_block_type_errors() -> None:
    doc = CanvasDoc(
        nodes=[
            node("inp", "Mystery"),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "c.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[edge("e1", "inp", "out", "out", "in")],
    )
    _, errors = compile_canvas(doc)
    assert any(e.kind == "unknown_block" for e in errors)


def test_diamond_dag_compiles() -> None:
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
    fragment, errors = compile_canvas(doc)
    assert errors == []
    assert fragment is not None
    assert sorted(fragment.referenced_tables) == ["main.s.a", "main.s.b"]


def test_sql_block_placeholder_substitution() -> None:
    doc = CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": "main.s.src"}),
            node("sql", "SQL", {"query": "SELECT * FROM {{in}} WHERE id > 0"}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.tgt", "mode": "overwrite"},
            ),
        ],
        edges=[
            edge("e1", "inp", "out", "sql", "in"),
            edge("e2", "sql", "out", "out", "in"),
        ],
    )
    fragment, errors = compile_canvas(doc)
    assert errors == []
    assert fragment is not None
    sql_cte_body = dict(fragment.ctes)["n1_sql"]
    assert "n0_inputport" in sql_cte_body


def test_duplicate_node_id_flagged() -> None:
    doc = CanvasDoc(
        nodes=[
            node("a", "InputPort", {"table_fqn": "main.s.x"}),
            node("a", "InputPort", {"table_fqn": "main.s.y"}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[edge("e", "a", "out", "out", "in")],
    )
    _, errors = compile_canvas(doc)
    assert any(e.kind == "duplicate_node_id" for e in errors)


def test_edge_target_missing_flagged() -> None:
    doc = CanvasDoc(
        nodes=[
            node("a", "InputPort", {"table_fqn": "main.s.x"}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.s.t", "mode": "overwrite"},
            ),
        ],
        edges=[edge("e", "ghost", "out", "out", "in")],
    )
    _, errors = compile_canvas(doc)
    assert any(e.kind == "edge_target_missing" for e in errors)


def test_render_sql_with_no_ctes_handles_gracefully() -> None:
    from pointlessql.services.dp_canvas._types import PinSchema, SinkSpec, SQLFragment

    sink = SinkSpec(
        output_node_id="out",
        port_name="p",
        target_fqn="c.s.t",
        mode="overwrite",
        final_cte="cte_x",
        output_schema=PinSchema(kind="table", columns=[]),
    )
    frag = SQLFragment(ctes=[], sinks=[sink], referenced_tables=[])
    assert render_sql(frag, sink) == "SELECT * FROM cte_x"


@pytest.mark.parametrize(
    "predicate", ["amount > 0", "amount IS NOT NULL", "country IN ('DE','FR')"]
)
def test_filter_predicates_propagate_into_sql(predicate: str) -> None:
    doc = linear_doc("main.sales.src", "main.sales.tgt", predicate=predicate)
    fragment, errors = compile_canvas(doc)
    assert errors == []
    assert fragment is not None
    filter_cte = dict(fragment.ctes)["n1_filter"]
    assert predicate in filter_cte
