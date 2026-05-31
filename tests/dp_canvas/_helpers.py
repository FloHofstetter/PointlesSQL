"""Shared builders for dp_canvas tests."""

from __future__ import annotations

from typing import Any

from pointlessql.services.dp_canvas import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
)


def node(
    id: str,
    block_type: str,
    config: dict[str, Any] | None = None,
) -> CanvasNode:
    return CanvasNode(id=id, block_type=block_type, config=config or {})


def edge(
    id: str,
    src: str,
    src_pin: str,
    tgt: str,
    tgt_pin: str,
) -> CanvasEdge:
    return CanvasEdge(
        id=id,
        source_node_id=src,
        source_pin=src_pin,
        target_node_id=tgt,
        target_pin=tgt_pin,
    )


def linear_doc(
    input_fqn: str,
    target_fqn: str,
    *,
    predicate: str | None = None,
    port_name: str = "primary",
    mode: str = "overwrite",
) -> CanvasDoc:
    """Build a minimal Input → (Filter?) → Output document."""
    nodes = [node("inp", "InputPort", {"table_fqn": input_fqn})]
    edges = []
    last = "inp"
    last_pin = "out"
    if predicate is not None:
        nodes.append(node("flt", "Filter", {"predicate": predicate}))
        edges.append(edge("e1", last, last_pin, "flt", "in"))
        last, last_pin = "flt", "out"
    nodes.append(
        node(
            "out",
            "OutputPort",
            {
                "port_name": port_name,
                "materialized_table": target_fqn,
                "mode": mode,
            },
        )
    )
    edges.append(edge("e_out", last, last_pin, "out", "in"))
    return CanvasDoc(nodes=nodes, edges=edges)
