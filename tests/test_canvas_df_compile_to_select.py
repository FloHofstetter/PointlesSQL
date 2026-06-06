"""Tests for the sink-free ``compile_to_select`` primitive.

``compile_to_select`` compiles the slice of a canvas ending at a chosen
terminal node into a ``WITH … SELECT * FROM <terminal_cte>`` string — no
OutputPort sink required — so the DataFrame Studio (and any other sink-free
consumer) can compile + preview + emit without coupling ``canvas_df`` back
to the data-product sink blocks.

Importing ``dp_canvas`` registers the source blocks (InputPort, FileInput,
…) into the shared ``BLOCK_REGISTRY`` so the slices below resolve.
"""

from __future__ import annotations

import pointlessql.services.dp_canvas as _dp_canvas  # noqa: F401  (registers source blocks)
from pointlessql.services.canvas_df import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    ColumnSpec,
    PinSchema,
    compile_to_select,
)


def _orders_seed(node_id: str) -> dict[str, PinSchema]:
    return {
        node_id: PinSchema(
            kind="table",
            columns=[
                ColumnSpec(name="id", duckdb_type="BIGINT", nullable=False),
                ColumnSpec(name="amount", duckdb_type="DECIMAL(10,2)", nullable=True),
            ],
        )
    }


def _filter_doc() -> CanvasDoc:
    return CanvasDoc(
        nodes=[
            CanvasNode(id="src", block_type="InputPort", config={"table_fqn": "main.s.orders"}),
            CanvasNode(id="flt", block_type="Filter", config={"predicate": "amount > 0"}),
        ],
        edges=[
            CanvasEdge(
                id="e1",
                source_node_id="src",
                source_pin="out",
                target_node_id="flt",
                target_pin="in",
            )
        ],
    )


def test_compile_to_select_basic() -> None:
    doc = _filter_doc()
    res, errors = compile_to_select(
        doc, terminal_node_id="flt", upstream_schemas=_orders_seed("src")
    )
    assert errors == []
    assert res is not None
    assert res.sql.startswith("WITH ")
    assert res.sql.strip().endswith("SELECT * FROM n1_filter")
    assert res.referenced_tables == ["main.s.orders"]
    assert [c.name for c in res.output_schema.columns] == ["id", "amount"]
    assert res.terminal_node_id == "flt"


def test_compile_to_select_terminates_at_chosen_node() -> None:
    """A node downstream of the terminal is excluded from the slice."""
    doc = _filter_doc()
    doc.nodes.append(CanvasNode(id="lim", block_type="Limit", config={"n": 5}))
    doc.edges.append(
        CanvasEdge(
            id="e2",
            source_node_id="flt",
            source_pin="out",
            target_node_id="lim",
            target_pin="in",
        )
    )
    # Terminal = flt → the Limit node must not appear in the SQL.
    res, errors = compile_to_select(
        doc, terminal_node_id="flt", upstream_schemas=_orders_seed("src")
    )
    assert errors == []
    assert res is not None
    assert "n2_limit" not in res.sql
    assert "LIMIT" not in res.sql  # no implicit limit on emit


def test_compile_to_select_no_sink_needed() -> None:
    """A doc with zero OutputPort/FileOutput still compiles (the point)."""
    doc = _filter_doc()
    res, errors = compile_to_select(
        doc, terminal_node_id="flt", upstream_schemas=_orders_seed("src")
    )
    assert errors == [] and res is not None


def test_compile_to_select_unknown_terminal() -> None:
    doc = _filter_doc()
    res, errors = compile_to_select(doc, terminal_node_id="nope")
    assert res is None
    assert any("not found" in e.message for e in errors)


def test_compile_to_select_propagates_block_errors() -> None:
    """A bad config in the slice surfaces as a compile error, not a crash."""
    doc = CanvasDoc(
        nodes=[
            CanvasNode(id="src", block_type="InputPort", config={"table_fqn": "main.s.orders"}),
            CanvasNode(id="flt", block_type="Filter", config={"predicate": ""}),
        ],
        edges=[
            CanvasEdge(
                id="e1",
                source_node_id="src",
                source_pin="out",
                target_node_id="flt",
                target_pin="in",
            )
        ],
    )
    res, errors = compile_to_select(
        doc, terminal_node_id="flt", upstream_schemas=_orders_seed("src")
    )
    assert res is None
    assert errors
