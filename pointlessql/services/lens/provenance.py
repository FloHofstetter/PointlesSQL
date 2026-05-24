"""Lens unified provenance trace — row + column + value lineage in one shape.

The signature feature of the Lens read-only Q&A surface.
Wraps the three Phase-15.x lineage backbones into a single
analyst-friendly response so an LLM can answer "where does this number
come from" without orchestrating three separate tool calls.

Three modes resolved by which scope params are populated:

* **Table-scope** (``table_fqn`` only) — upstream-table summary.
* **Column-scope** (``+ column``) — column lineage trail with
  transformations.
* **Row-scope** (``+ row_id``) — full row walkback with optional
  value-change trail when ``column`` is also set.

Workspace isolation is enforced by the route layer; this module does
not consult ``request.state`` so it stays unit-testable.  Cross-
workspace reads are blocked at the API boundary, not here.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Literal

from pydantic import BaseModel, Field

from pointlessql.services.lineage import (
    fetch_value_changes_for_row,
    walk_back,
    walk_back_columns,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

DEFAULT_MAX_HOPS = 5
MAX_ALLOWED_HOPS = 10
MAX_VALUE_CHANGE_ROWS = 50


ProvenanceMode = Literal["table", "column", "row", "row_value"]


class ProvenanceQuery(BaseModel):
    """Input shape for :func:`provenance`.

    Pydantic-validated so the same model surface works as an LLM tool
    schema, browser query parameter set, and Python call signature.

    Attributes:
        table_fqn: Fully-qualified UC table name (``catalog.schema.table``).
        row_id: Optional ``_lineage_row_id`` of the row to trace.  When
            unset, a table-scope trace is returned.
        column: Optional column name.  Combine with ``row_id`` to get
            value changes; combine alone to get column-trace.
        max_hops: Walkback depth limit; capped at
            :data:`MAX_ALLOWED_HOPS`.
    """

    table_fqn: str = Field(min_length=3, description="Three-part UC name")
    row_id: str | None = Field(default=None, description="_lineage_row_id value")
    column: str | None = Field(default=None, description="Column name")
    max_hops: int = Field(default=DEFAULT_MAX_HOPS, ge=1, le=MAX_ALLOWED_HOPS)


class ProvenanceSource(BaseModel):
    """One distinct upstream table referenced by the trace."""

    table_fqn: str
    columns: list[str] = Field(default_factory=list)


class Transformation(BaseModel):
    """One column-level transformation on the trace path."""

    target_table: str
    target_column: str
    source_table: str | None
    source_column: str | None
    transform_kind: str
    transform_detail: str | None = None
    op_id: int | None = None
    run_id: str | None = None


class RowStep(BaseModel):
    """One node on a row-trace walkback."""

    depth: int
    table: str
    row_id: str
    op_id: int | None
    run_id: str | None
    source_file: str | None = None
    predecessor_count: int = 0


class ValueChange(BaseModel):
    """One per-cell value change on the trace path."""

    target_table: str
    target_row_id: str
    target_column: str
    old_value: str | None
    new_value: str | None
    op_id: int | None
    created_at: str


class ProvenanceTrace(BaseModel):
    """Output shape of :func:`provenance`.

    Attributes:
        mode: Which scope was traced (resolved from input params).
        summary: Human + agent readable one-paragraph summary of the
            trace.  Suitable for the LLM to quote verbatim.
        sources: Distinct upstream tables (with the columns referenced
            on each).  Empty when no lineage is recorded.
        transformations: Column-level transformations on the path.
            Populated for column / row-value modes.
        row_steps: Row-level walkback steps.  Populated for row /
            row_value modes.
        value_changes: Per-cell value changes.  Populated for
            row_value mode.
        notes: Cautionary notes (e.g. "lineage truncated at hop limit",
            "no upstream lineage recorded for this table").
    """

    mode: ProvenanceMode
    summary: str
    sources: list[ProvenanceSource] = Field(default_factory=list)
    transformations: list[Transformation] = Field(default_factory=list)
    row_steps: list[RowStep] = Field(default_factory=list)
    value_changes: list[ValueChange] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def _resolve_mode(query: ProvenanceQuery) -> ProvenanceMode:
    """Pick the trace mode from which optional params are populated."""
    if query.row_id and query.column:
        return "row_value"
    if query.row_id:
        return "row"
    if query.column:
        return "column"
    return "table"


def _summarize_column(query: ProvenanceQuery, transformations: list[Transformation]) -> str:
    """Build a one-line column-scope summary."""
    if not transformations:
        return f"No column lineage recorded for {query.table_fqn}.{query.column}."
    n = len(transformations)
    return (
        f"{query.table_fqn}.{query.column} traces back through "
        f"{n} column-level transformation{'s' if n != 1 else ''}."
    )


def _summarize_row(query: ProvenanceQuery, row_steps: list[RowStep]) -> str:
    """Build a one-line row-scope summary."""
    if not row_steps:
        return f"No row lineage recorded for {query.table_fqn} row {query.row_id}."
    n = len(row_steps)
    return (
        f"Row {query.row_id} in {query.table_fqn} traces back through "
        f"{n} hop{'s' if n != 1 else ''}."
    )


def _summarize_row_value(
    query: ProvenanceQuery,
    row_steps: list[RowStep],
    value_changes: list[ValueChange],
) -> str:
    """Build a row+value summary combining hop count and change count."""
    base = _summarize_row(query, row_steps)
    if not value_changes:
        return f"{base} No per-cell value changes recorded for column {query.column}."
    n = len(value_changes)
    return f"{base} {n} value change{'s' if n != 1 else ''} recorded for column {query.column}."


def _collect_sources_from_columns(
    transformations: list[Transformation],
) -> list[ProvenanceSource]:
    """Group column transformations into a per-source-table summary."""
    by_table: dict[str, set[str]] = {}
    for t in transformations:
        if t.source_table is None:
            continue
        cols = by_table.setdefault(t.source_table, set())
        if t.source_column is not None:
            cols.add(t.source_column)
    return sorted(
        (
            ProvenanceSource(table_fqn=table, columns=sorted(cols))
            for table, cols in by_table.items()
        ),
        key=lambda s: s.table_fqn,
    )


def _collect_sources_from_row_steps(
    row_steps: list[RowStep],
) -> list[ProvenanceSource]:
    """Distinct tables visited on the row walkback (excluding depth 0)."""
    seen: dict[str, ProvenanceSource] = {}
    for step in row_steps:
        if step.depth == 0:
            continue
        if step.table not in seen:
            seen[step.table] = ProvenanceSource(table_fqn=step.table, columns=[])
    return sorted(seen.values(), key=lambda s: s.table_fqn)


def _trace_columns(factory: sessionmaker[Session], query: ProvenanceQuery) -> list[Transformation]:
    """Walk column lineage and flatten to the wire shape."""
    if not query.column:
        return []
    steps = walk_back_columns(
        factory,
        table=query.table_fqn,
        column=query.column,
        max_hops=query.max_hops,
    )
    out: list[Transformation] = []
    for step in steps:
        for pred in step.predecessors:
            out.append(
                Transformation(
                    target_table=step.table,
                    target_column=step.column,
                    source_table=pred.table,
                    source_column=pred.column,
                    transform_kind=pred.transform_kind,
                    transform_detail=pred.transform_detail,
                    op_id=pred.op_id,
                    run_id=pred.run_id,
                )
            )
    return out


def _trace_rows(
    factory: sessionmaker[Session], query: ProvenanceQuery
) -> tuple[list[RowStep], bool]:
    """Walk row lineage; returns (steps, hit_hop_limit)."""
    if not query.row_id:
        return [], False
    steps = walk_back(
        factory,
        table=query.table_fqn,
        row_id=query.row_id,
        max_hops=query.max_hops,
    )
    out = [
        RowStep(
            depth=s.depth,
            table=s.table,
            row_id=s.row_id,
            op_id=s.op_id,
            run_id=s.run_id,
            source_file=s.source_file,
            predecessor_count=len(s.predecessors),
        )
        for s in steps
    ]
    hit_limit = bool(out) and out[-1].depth >= query.max_hops and out[-1].predecessor_count > 0
    return out, hit_limit


def _trace_value_changes(
    factory: sessionmaker[Session], query: ProvenanceQuery
) -> tuple[list[ValueChange], bool]:
    """Fetch value changes for the row+column; returns (changes, truncated)."""
    if not (query.row_id and query.column):
        return [], False
    rows = fetch_value_changes_for_row(
        factory,
        target_table=query.table_fqn,
        target_row_id=query.row_id,
        column=query.column,
    )
    truncated = len(rows) > MAX_VALUE_CHANGE_ROWS
    capped = rows[:MAX_VALUE_CHANGE_ROWS]
    out = [
        ValueChange(
            target_table=r.target_table,
            target_row_id=r.target_row_id,
            target_column=r.target_column,
            old_value=r.old_value,
            new_value=r.new_value,
            op_id=r.op_id,
            created_at=r.created_at.isoformat() if r.created_at else "",
        )
        for r in capped
    ]
    return out, truncated


def provenance(factory: sessionmaker[Session], query: ProvenanceQuery) -> ProvenanceTrace:
    """Walk the unified lineage trace for *query*.

    See module docstring for the three modes and which lineage tables
    each mode walks.

    Args:
        factory: SQLAlchemy session factory.
        query: Validated :class:`ProvenanceQuery`.

    Returns:
        A :class:`ProvenanceTrace` whose ``mode`` reflects which scope
        was actually walked.  Empty traces (no recorded lineage) return
        a populated ``notes`` entry rather than raising.
    """
    mode = _resolve_mode(query)
    notes: list[str] = []

    if mode == "table":
        # Table-scope today returns no walkback (no row to anchor); we
        # surface an explicit note so the LLM understands the scope and
        # can suggest providing a row_id for deeper trace.
        return ProvenanceTrace(
            mode="table",
            summary=(
                f"Table-scope provenance for {query.table_fqn}: no anchor row "
                f"provided.  Pass a row_id or column for a deeper trace."
            ),
            notes=[
                "Table-scope mode returns metadata only; pass row_id or column for a real walkback."
            ],
        )

    if mode == "column":
        transformations = _trace_columns(factory, query)
        sources = _collect_sources_from_columns(transformations)
        if not transformations:
            notes.append(f"No column lineage recorded for {query.table_fqn}.{query.column}.")
        return ProvenanceTrace(
            mode="column",
            summary=_summarize_column(query, transformations),
            sources=sources,
            transformations=transformations,
            notes=notes,
        )

    if mode == "row":
        row_steps, hit_limit = _trace_rows(factory, query)
        sources = _collect_sources_from_row_steps(row_steps)
        if hit_limit:
            notes.append(
                f"Row walkback truncated at hop limit ({query.max_hops}); "
                f"raise max_hops up to {MAX_ALLOWED_HOPS} for deeper traces."
            )
        if not row_steps or (len(row_steps) == 1 and row_steps[0].predecessor_count == 0):
            notes.append(
                f"No upstream row lineage recorded for {query.table_fqn} row {query.row_id}."
            )
        return ProvenanceTrace(
            mode="row",
            summary=_summarize_row(query, row_steps),
            sources=sources,
            row_steps=row_steps,
            notes=notes,
        )

    # row_value
    transformations = _trace_columns(factory, query)
    row_steps, hit_limit = _trace_rows(factory, query)
    value_changes, truncated = _trace_value_changes(factory, query)
    sources = _collect_sources_from_columns(transformations) or _collect_sources_from_row_steps(
        row_steps
    )
    if hit_limit:
        notes.append(f"Row walkback truncated at hop limit ({query.max_hops}).")
    if truncated:
        notes.append(f"Value-change list truncated to {MAX_VALUE_CHANGE_ROWS} most recent rows.")
    if not value_changes:
        notes.append(
            f"No value changes recorded for {query.table_fqn}.{query.column} "
            f"row {query.row_id} (track_value_changes likely off on the "
            f"writing op)."
        )
    return ProvenanceTrace(
        mode="row_value",
        summary=_summarize_row_value(query, row_steps, value_changes),
        sources=sources,
        transformations=transformations,
        row_steps=row_steps,
        value_changes=value_changes,
        notes=notes,
    )
