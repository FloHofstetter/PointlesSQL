"""DP-as-Code ↔ canvas-doc round-trip + diff service unit tests."""

from __future__ import annotations

from pointlessql.services.data_product_as_code._canvas_pipeline import (
    CanvasPipelineSpec,
    from_canvas_doc,
    to_canvas_doc,
)
from pointlessql.services.dp_canvas import CanvasDoc, CanvasEdge, CanvasNode
from pointlessql.services.dp_canvas._diff import diff_docs


def _doc_three_block() -> CanvasDoc:
    return CanvasDoc(
        nodes=[
            CanvasNode(
                id="inp",
                block_type="InputPort",
                config={"table_fqn": "main.bronze.events"},
                position={"x": 10, "y": 20},
            ),
            CanvasNode(
                id="flt",
                block_type="Filter",
                config={"predicate": "amt > 0"},
                position={"x": 200, "y": 20},
            ),
            CanvasNode(
                id="out",
                block_type="OutputPort",
                config={
                    "port_name": "primary",
                    "materialized_table": "main.silver.events_clean",
                    "mode": "overwrite",
                },
                position={"x": 400, "y": 20},
            ),
        ],
        edges=[
            CanvasEdge(
                id="e1",
                source_node_id="inp",
                source_pin="out",
                target_node_id="flt",
                target_pin="in",
            ),
            CanvasEdge(
                id="e2",
                source_node_id="flt",
                source_pin="out",
                target_node_id="out",
                target_pin="in",
            ),
        ],
    )


def test_roundtrip_idempotent() -> None:
    doc = _doc_three_block()
    spec = from_canvas_doc(doc)
    back = to_canvas_doc(spec)
    assert back == doc


def test_export_with_no_pipeline_serialises_cleanly() -> None:
    empty = CanvasDoc(nodes=[], edges=[])
    spec = from_canvas_doc(empty)
    assert spec.nodes == []
    assert spec.edges == []
    assert spec.version == 1


def test_pipeline_spec_rejects_extra_fields() -> None:
    import pytest as _pytest

    with _pytest.raises(Exception):
        CanvasPipelineSpec.model_validate(
            {"version": 1, "nodes": [], "edges": [], "bogus": 1}
        )


def test_diff_identical_doc_is_empty() -> None:
    doc = _doc_three_block()
    result = diff_docs(doc, doc)
    assert result.is_empty()


def test_diff_added_node_surfaces() -> None:
    before = _doc_three_block()
    after_nodes = list(before.nodes) + [
        CanvasNode(id="lim", block_type="Limit", config={"n": 100})
    ]
    after = CanvasDoc(nodes=after_nodes, edges=before.edges)
    result = diff_docs(before, after)
    assert [n.id for n in result.added_nodes] == ["lim"]
    assert not result.removed_nodes


def test_diff_modified_node_emits_before_after() -> None:
    before = _doc_three_block()
    new_nodes = [
        CanvasNode(
            id=n.id,
            block_type=n.block_type,
            config={"predicate": "amt > 100"} if n.id == "flt" else dict(n.config),
        )
        for n in before.nodes
    ]
    after = CanvasDoc(nodes=new_nodes, edges=before.edges)
    result = diff_docs(before, after)
    assert len(result.modified_nodes) == 1
    diff = result.modified_nodes[0]
    assert diff.before_config == {"predicate": "amt > 0"}
    assert diff.after_config == {"predicate": "amt > 100"}


def test_diff_ignores_position_only_change() -> None:
    before = _doc_three_block()
    new_nodes = [
        CanvasNode(
            id=n.id,
            block_type=n.block_type,
            config=dict(n.config),
            position={"x": (n.position or {}).get("x", 0) + 50, "y": 0} if n.position else None,
        )
        for n in before.nodes
    ]
    after = CanvasDoc(nodes=new_nodes, edges=before.edges)
    result = diff_docs(before, after)
    assert not result.modified_nodes
