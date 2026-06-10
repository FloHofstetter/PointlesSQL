"""Pydantic types for the dataframe canvas layer.

The graph envelope (:class:`CanvasDoc` / :class:`CanvasNode` /
:class:`CanvasEdge`) and the shared :class:`CompileError` live in the
consumer-agnostic :mod:`pointlessql.services.canvas_core` kernel; they are
re-exported here so a dataframe consumer can pull every type it needs from
one module.

What this module *owns* is the dataframe-flavoured half of the contract —
pin schemas plus the SQL compiler's fragment/sink shapes.  A pin is a
rowset with a column list; a sink names a materialisation target the
compiler resolved from a terminal block.  These are pure data shapes: they
describe a SQL pipeline without knowing how (or whether) it is persisted,
which is what lets both the data-product and notebook consumers reuse them.
"""

from __future__ import annotations

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
        model_config: Pydantic model config — instances are frozen so
            a column spec can be hashed and shared across compile
            passes without defensive copies.
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


__all__ = [
    "CanvasDoc",
    "CanvasEdge",
    "CanvasNode",
    "ColumnSpec",
    "CompileError",
    "PinSchema",
    "SQLFragment",
    "SinkSpec",
]
