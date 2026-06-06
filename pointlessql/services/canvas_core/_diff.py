"""Pure structural diff between two canvas documents.

Surfaces the four edit classes a canvas reviewer cares about:
nodes added, removed, or modified (config changed), and edges added
or removed.  Position-only changes are ignored — they're cosmetic
relayout and rendering them as "changed" would drown out meaningful
config edits.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pointlessql.services.canvas_core._types import CanvasDoc, CanvasEdge, CanvasNode


class CanvasNodeDiff(BaseModel):
    """One node-level entry in the diff."""

    model_config = ConfigDict(frozen=True)

    id: str
    block_type: str
    before_config: dict[str, Any] | None = None
    after_config: dict[str, Any] | None = None


class CanvasEdgeDiff(BaseModel):
    """One edge-level entry in the diff."""

    model_config = ConfigDict(frozen=True)

    id: str
    source_node_id: str
    source_pin: str
    target_node_id: str
    target_pin: str


class CanvasDiff(BaseModel):
    """The bundled diff returned by :func:`diff_docs`."""

    model_config = ConfigDict(frozen=True)

    added_nodes: list[CanvasNodeDiff] = Field(default_factory=lambda: [])
    removed_nodes: list[CanvasNodeDiff] = Field(default_factory=lambda: [])
    modified_nodes: list[CanvasNodeDiff] = Field(default_factory=lambda: [])
    added_edges: list[CanvasEdgeDiff] = Field(default_factory=lambda: [])
    removed_edges: list[CanvasEdgeDiff] = Field(default_factory=lambda: [])
    modified_edges: list[CanvasEdgeDiff] = Field(default_factory=lambda: [])

    def is_empty(self) -> bool:
        return not (
            self.added_nodes
            or self.removed_nodes
            or self.modified_nodes
            or self.added_edges
            or self.removed_edges
            or self.modified_edges
        )


def _edge_key(edge: CanvasEdge) -> tuple[str, str, str, str]:
    return (
        edge.source_node_id,
        edge.source_pin,
        edge.target_node_id,
        edge.target_pin,
    )


def _node_diff_from(node: CanvasNode, *, before: bool) -> CanvasNodeDiff:
    cfg = dict(node.config)
    if before:
        return CanvasNodeDiff(id=node.id, block_type=node.block_type, before_config=cfg)
    return CanvasNodeDiff(id=node.id, block_type=node.block_type, after_config=cfg)


def _edge_diff_from(edge: CanvasEdge) -> CanvasEdgeDiff:
    return CanvasEdgeDiff(
        id=edge.id,
        source_node_id=edge.source_node_id,
        source_pin=edge.source_pin,
        target_node_id=edge.target_node_id,
        target_pin=edge.target_pin,
    )


def diff_docs(before: CanvasDoc, after: CanvasDoc) -> CanvasDiff:
    """Compare *before* and *after*; return the structural delta."""
    before_nodes = {n.id: n for n in before.nodes}
    after_nodes = {n.id: n for n in after.nodes}
    added_nodes = [
        _node_diff_from(n, before=False)
        for nid, n in after_nodes.items()
        if nid not in before_nodes
    ]
    removed_nodes = [
        _node_diff_from(n, before=True) for nid, n in before_nodes.items() if nid not in after_nodes
    ]
    modified_nodes = []
    for nid, b_node in before_nodes.items():
        a_node = after_nodes.get(nid)
        if a_node is None:
            continue
        if b_node.block_type != a_node.block_type or b_node.config != a_node.config:
            modified_nodes.append(
                CanvasNodeDiff(
                    id=nid,
                    block_type=a_node.block_type,
                    before_config=dict(b_node.config),
                    after_config=dict(a_node.config),
                )
            )

    before_edge_keys = {_edge_key(e): e for e in before.edges}
    after_edge_keys = {_edge_key(e): e for e in after.edges}
    added_edges = [
        _edge_diff_from(e) for k, e in after_edge_keys.items() if k not in before_edge_keys
    ]
    removed_edges = [
        _edge_diff_from(e) for k, e in before_edge_keys.items() if k not in after_edge_keys
    ]

    modified_node_ids = {n.id for n in modified_nodes}
    modified_edges = [
        _edge_diff_from(e)
        for k, e in after_edge_keys.items()
        if k in before_edge_keys
        and (e.source_node_id in modified_node_ids or e.target_node_id in modified_node_ids)
    ]

    return CanvasDiff(
        added_nodes=added_nodes,
        removed_nodes=removed_nodes,
        modified_nodes=modified_nodes,
        added_edges=added_edges,
        removed_edges=removed_edges,
        modified_edges=modified_edges,
    )


__all__ = ["CanvasDiff", "CanvasEdgeDiff", "CanvasNodeDiff", "diff_docs"]
