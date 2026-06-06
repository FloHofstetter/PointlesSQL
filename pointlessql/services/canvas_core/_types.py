"""Consumer-agnostic graph envelope for every canvas surface.

These types are the *contract* between a Drawflow-style editor frontend
and any backend that wants to persist, validate, diff, or order a node
graph — data products, the scheduler's task chains, the notebook
DataFrame builder.  The envelope is deliberately tiny: a node carries an
opaque ``config`` dict plus a ``block_type`` registry key, so a new node
kind never bumps ``schema_version`` and never forces this module to know
anything domain-specific (SQL, Delta, task execution, …).

Domain-specific shapes — pin schemas, SQL fragments, sink specs — live
in the layers above (``canvas_df`` for dataframe pipelines, the
per-consumer service packages) and never leak down here.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CanvasNode(BaseModel):
    """One block on the canvas.

    Attributes:
        id: Stable identifier the editor mints (a UUID v4 string for most
            consumers) so edges and downstream results can reference the
            node across re-saves.
        block_type: Registry key the consuming layer resolves through its
            own node-kind registry.
        config: Block-specific configuration.  Each consumer parses this
            dict through its own schema — invalid configs become
            structured errors at compile/validate time, not pydantic
            ``ValidationError`` here, so the editor can keep the document
            open with the error surfaced in-place.
        position: Optional ``{"x": float, "y": float}`` for the editor
            layout.  Ignored by every backend pipeline.
    """

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=64)
    block_type: str = Field(min_length=1, max_length=64)
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] | None = None


class CanvasEdge(BaseModel):
    """A wire between an upstream output-pin and a downstream input-pin."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=64)
    source_node_id: str = Field(min_length=1, max_length=64)
    source_pin: str = Field(min_length=1, max_length=64)
    target_node_id: str = Field(min_length=1, max_length=64)
    target_pin: str = Field(min_length=1, max_length=64)


class CanvasDoc(BaseModel):
    """The serialised canvas document each consumer persists.

    Top-level envelope is deliberately tiny — every interesting decision
    lives inside the per-node ``config`` dicts so adding a new block type
    never bumps ``schema_version``.
    """

    model_config = ConfigDict(extra="ignore")

    nodes: list[CanvasNode] = Field(default_factory=list)
    edges: list[CanvasEdge] = Field(default_factory=list)
    schema_version: Literal[1] = 1
    metadata: dict[str, Any] = Field(default_factory=dict)


class CompileError(BaseModel):
    """A single problem a validator or compiler surfaced.

    Errors are accumulated and returned as a list rather than raised so
    the editor can render every problem at once instead of one-at-a-time
    round-trips.  ``node_id`` and ``pin`` are populated when the error has
    a graph location; ``message`` is the human-readable summary the UI
    shows next to the offending pin.

    The ``kind`` literal spans both the consumer-agnostic structural
    errors (``empty_doc`` / ``cycle`` / ``duplicate_node_id`` /
    ``edge_target_missing`` / ``unknown_block``) and the dataframe-layer
    compile errors (``bad_config`` / ``type_mismatch`` / ``duplicate_pin``
    / ``output_port_count`` / ``duplicate_sink`` / ``missing_input``).  A
    consumer simply never emits the kinds it has no notion of.

    Optional diagnostic fields (``expected_type`` / ``actual_type`` /
    ``column`` / ``suggestion``) carry just-enough structure for the
    editor to render hover-tooltips with concrete next-steps.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal[
        "empty_doc",
        "cycle",
        "missing_input",
        "unknown_block",
        "bad_config",
        "output_port_count",
        "duplicate_sink",
        "type_mismatch",
        "duplicate_pin",
        "duplicate_node_id",
        "edge_target_missing",
    ]
    node_id: str | None = None
    pin: str | None = None
    message: str
    expected_type: str | None = None
    actual_type: str | None = None
    column: str | None = None
    suggestion: str | None = None


__all__ = [
    "CanvasDoc",
    "CanvasEdge",
    "CanvasNode",
    "CompileError",
]
