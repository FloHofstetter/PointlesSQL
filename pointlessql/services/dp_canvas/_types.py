"""Pydantic envelopes for the visual data-product canvas.

These types are the *contract* between the editor frontend, the
compiler, the schema-flow validator, and the executor.  Document
shape is intentionally minimal: nodes carry an opaque ``config``
dict that each block's ``BlockSpec`` unpacks via its own per-block
schema — that keeps the envelope stable even as block types accrete.

Pin types are scoped to v1 — only ``TableRef`` (schemaful rowsets).
Later waves can add ``ScalarValue`` / ``ModelRef`` / ``VectorIndex``
without rewriting the envelope.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ColumnSpec(BaseModel):
    """One column in a pin's table schema.

    Attributes:
        name: Lowercase column identifier as it appears in the DuckDB
            view bound to the upstream Delta table.
        duckdb_type: DuckDB-flavoured type string (``"VARCHAR"``,
            ``"BIGINT"``, ``"DECIMAL(10,2)"``, …).  Not validated
            beyond non-emptiness — DuckDB will surface a clearer error
            at compile time than a bespoke parser would.
        nullable: Whether the underlying Delta column allows nulls.
    """

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1, max_length=255)
    duckdb_type: str = Field(min_length=1, max_length=128)
    nullable: bool = True


class PinSchema(BaseModel):
    """Shape of data crossing a pin.

    v1 supports a single ``kind`` (``"table"``) — every pin is a
    rowset with a column list.  When a block cannot infer its output
    schema (e.g. a raw ``SQL`` block whose downstream schema would
    require a live DuckDB ``DESCRIBE`` round-trip not yet wired) the
    column list is empty and ``unknown`` is set so downstream blocks
    can decide whether to surface a "schema unknown" badge or skip
    propagation.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal["table"] = "table"
    columns: list[ColumnSpec] = Field(default_factory=list)
    unknown: bool = False


class CanvasNode(BaseModel):
    """One block on the canvas.

    Attributes:
        id: Stable identifier the editor mints (UUID v4 string) so
            edges + executor results can reference the node across
            re-saves.
        block_type: Registry key in :data:`BLOCK_REGISTRY`.
        config: Block-specific configuration.  Each ``BlockSpec``
            parses this dict through its own Pydantic config schema —
            invalid configs become :class:`CompileError` rows at
            compile time, not pydantic ``ValidationError`` here, so
            the editor can keep the document open with the error
            surfaced in-place.
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
    """The serialised canvas document persisted in ``data_product_canvas_graph``.

    Top-level envelope is deliberately tiny — every interesting decision
    lives inside the per-node ``config`` dicts so adding a new block
    type never bumps ``schema_version``.
    """

    model_config = ConfigDict(extra="ignore")

    nodes: list[CanvasNode] = Field(default_factory=list)
    edges: list[CanvasEdge] = Field(default_factory=list)
    schema_version: Literal[1] = 1


class SQLFragment(BaseModel):
    """The compiler's output: an ordered CTE chain plus a final pick.

    ``ctes`` are emitted in execution order — the executor concatenates
    them as ``WITH a AS (…), b AS (…) SELECT * FROM <final_cte>``.
    ``referenced_tables`` is the union of every base-table FQN that
    needs to be registered as a DuckDB view before the SQL runs.
    """

    model_config = ConfigDict(frozen=True)

    ctes: list[tuple[str, str]] = Field(default_factory=list)
    final_cte: str = Field(min_length=1, max_length=128)
    referenced_tables: list[str] = Field(default_factory=list)
    output_schema: PinSchema


class CompileError(BaseModel):
    """A single problem the compiler or validator surfaced.

    Errors are accumulated and returned as a list rather than raised
    so the editor can render every problem at once instead of
    one-at-a-time round-trips.  ``node_id`` and ``pin`` are populated
    when the error has a graph location; ``message`` is the
    human-readable summary the UI shows next to the offending pin.

    Optional diagnostic fields (``expected_type`` / ``actual_type``
    / ``column`` / ``suggestion``) carry just-enough structure for
    the editor to render hover-tooltips with concrete next-steps —
    e.g. surface "Expected INT, got VARCHAR on column foo" and
    offer to wire in a Cast block automatically.
    """

    model_config = ConfigDict(frozen=True)

    kind: Literal[
        "empty_doc",
        "cycle",
        "missing_input",
        "unknown_block",
        "bad_config",
        "output_port_count",
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


class ExecuteResult(BaseModel):
    """The return envelope of :func:`execute_canvas`.

    Attributes:
        rows_written: Number of rows the materialise wrote into the
            target Delta table.
        target_fqn: Three-part UC name the canvas materialised to.
        output_port_id: PK of the ``data_product_output_ports`` row
            registered for the materialised table.  ``None`` when an
            existing port with the same name was reused.
        graph_version: ``version`` column the executor stamped on the
            ``data_product_canvas_graph`` row it minted for this run.
        compile_errors: Always empty on successful execute (errors
            short-circuit before any write); reserved for callers that
            want to inspect dry-run output in future waves.
    """

    model_config = ConfigDict(frozen=True)

    rows_written: int
    target_fqn: str
    output_port_id: int | None
    graph_version: int
    compile_errors: Sequence[CompileError] = Field(default_factory=list)
