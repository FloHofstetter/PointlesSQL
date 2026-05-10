"""Lineage tools — ``provenance`` and ``lineage_neighbors``.

``provenance`` wraps the Sprint 65.1 unified trace service so the LLM
can answer "where does this number come from" with one tool call.

``lineage_neighbors`` gives a one-hop neighbor view (upstream + downstream
tables of the input table) without a full walkback — useful when the
analyst is sketching the data flow rather than chasing a specific row.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from pydantic import BaseModel, Field
from sqlalchemy import select

from pointlessql.models import LineageRowEdge
from pointlessql.services.lens.provenance import (
    ProvenanceQuery,
    ProvenanceTrace,
    provenance,
)
from pointlessql.services.lens.tools._base import SessionContext, ToolDef

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# provenance
# ---------------------------------------------------------------------------


class ProvenanceToolArgs(BaseModel):
    """Input for ``provenance`` (mirrors :class:`ProvenanceQuery`)."""

    table_fqn: str = Field(
        min_length=3, description="Three-part UC name catalog.schema.table"
    )
    row_id: str | None = Field(
        default=None,
        description="Optional _lineage_row_id of the row to trace",
    )
    column: str | None = Field(
        default=None, description="Optional column name to narrow the trace"
    )
    max_hops: int = Field(default=5, ge=1, le=10)


async def _execute_provenance(
    ctx: SessionContext, args: ProvenanceToolArgs
) -> ProvenanceTrace:
    """Return the unified row+column+value provenance trace."""
    query = ProvenanceQuery(
        table_fqn=args.table_fqn,
        row_id=args.row_id,
        column=args.column,
        max_hops=args.max_hops,
    )
    return provenance(ctx.factory, query)


PROVENANCE_TOOL = ToolDef(
    name="provenance",
    description=(
        "Trace where a value, row, column, or table came from.  Folds "
        "row-lineage, column-lineage, and per-cell value changes into "
        "one response.  Pass table_fqn alone for table-scope; add "
        "column for column-trace; add row_id for row walkback; add "
        "both row_id and column for the value-change trail.  "
        "Workspace-isolated."
    ),
    input_model=ProvenanceToolArgs,
    output_model=ProvenanceTrace,
    executor=_execute_provenance,
)


# ---------------------------------------------------------------------------
# lineage_neighbors
# ---------------------------------------------------------------------------


class LineageNeighborsArgs(BaseModel):
    """Input for ``lineage_neighbors``."""

    table_fqn: str = Field(min_length=3, description="UC FQN to neighbor-walk")
    limit: int = Field(default=20, ge=1, le=100)


class LineageNeighborsResult(BaseModel):
    """Output: distinct one-hop upstream + downstream tables."""

    table_fqn: str
    upstream: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)


async def _execute_lineage_neighbors(
    ctx: SessionContext, args: LineageNeighborsArgs
) -> LineageNeighborsResult:
    """Return distinct one-hop upstream + downstream tables."""
    upstream = sorted(
        _distinct_neighbors(
            ctx.factory,
            target_table=args.table_fqn,
            limit=args.limit,
        )
    )
    downstream = sorted(
        _distinct_neighbors(
            ctx.factory,
            source_table=args.table_fqn,
            limit=args.limit,
        )
    )
    return LineageNeighborsResult(
        table_fqn=args.table_fqn,
        upstream=upstream,
        downstream=downstream,
    )


LINEAGE_NEIGHBORS_TOOL = ToolDef(
    name="lineage_neighbors",
    description=(
        "List the one-hop upstream and downstream tables of a UC "
        "table.  Use this for a quick data-flow sketch; use "
        "'provenance' for a deep walkback trace."
    ),
    input_model=LineageNeighborsArgs,
    output_model=LineageNeighborsResult,
    executor=_execute_lineage_neighbors,
)


def _distinct_neighbors(
    factory: sessionmaker[Session],
    *,
    source_table: str | None = None,
    target_table: str | None = None,
    limit: int,
) -> set[str]:
    """Return the distinct neighbor table names for the given side."""
    if source_table is None and target_table is None:
        return set()
    with factory() as session:
        if source_table is not None:
            stmt = (
                select(LineageRowEdge.target_table)
                .where(LineageRowEdge.source_table == source_table)
                .distinct()
                .limit(limit)
            )
        else:
            stmt = (
                select(LineageRowEdge.source_table)
                .where(LineageRowEdge.target_table == target_table)
                .distinct()
                .limit(limit)
            )
        return {str(row) for (row,) in session.execute(stmt).all() if row}
