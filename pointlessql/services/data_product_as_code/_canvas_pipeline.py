"""Canvas pipeline ↔ DataProductSpec round-trip.

Adds a *structured* ``pipeline:`` sub-tree to the YAML DP spec so a
visual canvas can be git-tracked, code-reviewed, and applied like any
other Data-Product-as-Code object.  The intentionally chosen shape
mirrors :class:`CanvasDoc` 1-to-1 so the converter functions are
pure mechanical translations and stay readable in PR diffs.

Why structured (vs. embedded JSON string): YAML pretty-prints lists
and dicts naturally, so the diff against a renamed block shows up
as a one-line key change instead of an opaque JSON-blob delta.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from pointlessql.services.dp_canvas import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
)


class _CanvasPipelinePosition(BaseModel):
    model_config = ConfigDict(extra="ignore")

    x: float = 0.0
    y: float = 0.0


class CanvasPipelineNode(BaseModel):
    """One block in the YAML pipeline sub-tree."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    type: str = Field(min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=lambda: {})
    position: _CanvasPipelinePosition | None = None


class CanvasPipelineEdge(BaseModel):
    """One wire in the YAML pipeline sub-tree.

    Field names mirror the canvas envelope (``source``/``target`` plus
    explicit pin names) so a YAML reviewer can recognise the wire
    topology without consulting the canvas docs.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=64)
    source_pin: str = Field(min_length=1, max_length=64, default="out")
    target: str = Field(min_length=1, max_length=64)
    target_pin: str = Field(min_length=1, max_length=64, default="in")


class CanvasPipelineSpec(BaseModel):
    """Top-level ``pipeline:`` block on a DataProductSpec."""

    model_config = ConfigDict(extra="forbid")

    version: Literal[1] = 1
    nodes: list[CanvasPipelineNode] = Field(default_factory=lambda: [])
    edges: list[CanvasPipelineEdge] = Field(default_factory=lambda: [])


def from_canvas_doc(doc: CanvasDoc) -> CanvasPipelineSpec:
    """Mechanical translation :class:`CanvasDoc` → :class:`CanvasPipelineSpec`."""
    nodes = [
        CanvasPipelineNode(
            id=n.id,
            type=n.block_type,
            config=dict(n.config),
            position=(
                _CanvasPipelinePosition(x=n.position["x"], y=n.position["y"])
                if n.position
                else None
            ),
        )
        for n in doc.nodes
    ]
    edges = [
        CanvasPipelineEdge(
            id=e.id,
            source=e.source_node_id,
            source_pin=e.source_pin,
            target=e.target_node_id,
            target_pin=e.target_pin,
        )
        for e in doc.edges
    ]
    return CanvasPipelineSpec(version=1, nodes=nodes, edges=edges)


def to_canvas_doc(spec: CanvasPipelineSpec) -> CanvasDoc:
    """Reverse of :func:`from_canvas_doc`."""
    nodes = [
        CanvasNode(
            id=n.id,
            block_type=n.type,
            config=dict(n.config),
            position=(
                {"x": n.position.x, "y": n.position.y} if n.position else None
            ),
        )
        for n in spec.nodes
    ]
    edges = [
        CanvasEdge(
            id=e.id,
            source_node_id=e.source,
            source_pin=e.source_pin,
            target_node_id=e.target,
            target_pin=e.target_pin,
        )
        for e in spec.edges
    ]
    return CanvasDoc(nodes=nodes, edges=edges)


__all__ = [
    "CanvasPipelineEdge",
    "CanvasPipelineNode",
    "CanvasPipelineSpec",
    "from_canvas_doc",
    "to_canvas_doc",
]
