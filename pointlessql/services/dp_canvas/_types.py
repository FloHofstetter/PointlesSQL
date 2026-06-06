"""Pydantic types for the visual data-product canvas.

The graph envelope (:class:`CanvasDoc` / :class:`CanvasNode` /
:class:`CanvasEdge`) and the shared :class:`CompileError` now live in the
consumer-agnostic :mod:`pointlessql.services.canvas_core` kernel; they are
re-exported here so every existing ``from pointlessql.services.dp_canvas
import …`` (and ``from …dp_canvas._types import …``) keeps resolving
unchanged.

What stays here is the *dataframe-flavoured* half of the contract — pin
schemas, the SQL compiler's fragment/sink shapes, and the executor's
per-sink results.  These are scoped to the data-product pipeline: a pin
is a rowset with a column list, a sink materialises a Delta table.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from pointlessql.services.canvas_core._types import (
    CanvasDoc,
    CanvasEdge,
    CanvasNode,
    CompileError,
)


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


class SinkSpec(BaseModel):
    """One materialisation target the compiler resolved from a sink block.

    A canvas may carry several sink blocks — each publishes a distinct
    target from the *same* shared CTE chain.  ``final_cte`` names this
    sink's terminal CTE; the executor renders ``WITH <shared ctes> SELECT
    * FROM <final_cte>`` per sink.  ``port_name`` / ``mode`` / ``merge_on``
    are lifted from the block's ``config`` at compile time so the executor
    never has to re-walk the document per sink.

    Most sinks are ``OutputPort`` blocks that write a Delta table
    (``sink_kind="delta"``, the default).  A ``FileOutput`` block produces
    a ``sink_kind="file"`` spec instead: it writes ``file_path`` in
    ``file_format`` and bypasses Unity Catalog entirely, so it carries no
    real ``target_fqn`` (the path is mirrored there for dedup/display).
    """

    model_config = ConfigDict(frozen=True)

    output_node_id: str = Field(min_length=1, max_length=64)
    port_name: str = Field(min_length=1, max_length=255)
    target_fqn: str = Field(min_length=1, max_length=512)
    mode: str = Field(min_length=1, max_length=32)
    merge_on: list[str] = Field(default_factory=list)
    final_cte: str = Field(min_length=1, max_length=128)
    output_schema: PinSchema
    sink_kind: Literal["delta", "file"] = "delta"
    file_path: str | None = Field(default=None, max_length=1024)
    file_format: str | None = None


class SQLFragment(BaseModel):
    """The compiler's output: an ordered CTE chain plus one or more sinks.

    ``ctes`` are emitted in execution order — every sink shares this same
    chain, rendered as ``WITH a AS (…), b AS (…) SELECT * FROM
    <sink.final_cte>``.  ``sinks`` holds one :class:`SinkSpec` per
    ``OutputPort`` block (at least one).  ``referenced_tables`` is the
    union of every base-table FQN that needs to be registered as a DuckDB
    view before the SQL runs.
    """

    model_config = ConfigDict(frozen=True)

    ctes: list[tuple[str, str]] = Field(default_factory=list)
    sinks: list[SinkSpec] = Field(min_length=1)
    referenced_tables: list[str] = Field(default_factory=list)


class SinkResult(BaseModel):
    """The per-sink outcome of one :func:`execute_canvas` run.

    Attributes:
        port_name: ``OutputPort.config.port_name`` this result belongs to.
        target_fqn: Three-part UC name this sink materialised to.
        rows_written: Rows written into the target Delta table; ``0`` when
            the sink failed before any write.
        output_port_id: PK of the ``data_product_output_ports`` row
            registered for the materialised table.  ``None`` when an
            existing port with the same name was reused or the sink failed.
        status: ``"ok"`` when the write + registration succeeded,
            ``"failed"`` when this sink raised mid-run (other sinks still
            run — materialisation is best-effort per sink).
        error: Human-readable failure summary when ``status == "failed"``.
    """

    model_config = ConfigDict(frozen=True)

    port_name: str
    target_fqn: str
    rows_written: int = 0
    output_port_id: int | None = None
    status: Literal["ok", "failed"]
    error: str | None = None


class MultiExecuteResult(BaseModel):
    """The return envelope of :func:`execute_canvas`.

    A canvas may publish several output ports; ``sinks`` carries one
    :class:`SinkResult` per ``OutputPort`` block, in document order.
    Config / compile errors short-circuit before any write (the call
    raises); a *runtime* write failure on one sink leaves the others
    untouched and surfaces as that sink's ``status == "failed"``.

    Attributes:
        sinks: Per-sink outcomes for this run (at least one).
        graph_version: ``version`` the executor stamped on the single
            ``data_product_canvas_graph`` row minted for this run — all
            sinks share it.
        compile_errors: Always empty on a successful run; reserved for
            callers that want to inspect dry-run output in future waves.
    """

    model_config = ConfigDict(frozen=True)

    sinks: list[SinkResult] = Field(default_factory=list)
    graph_version: int
    compile_errors: Sequence[CompileError] = Field(default_factory=list)


__all__ = [
    "CanvasDoc",
    "CanvasEdge",
    "CanvasNode",
    "ColumnSpec",
    "CompileError",
    "MultiExecuteResult",
    "PinSchema",
    "SQLFragment",
    "SinkResult",
    "SinkSpec",
]
