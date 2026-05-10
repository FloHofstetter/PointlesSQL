"""Cascade detection across the lineage row + column axes.

When the operator is about to rollback table X, the rollback-preview
endpoint surfaces a warning naming downstream tables that were
derived from X via row lineage (``lineage_row_edges``) or column
lineage (``lineage_column_map``).  v1 ships **preview-only**: the
warning is informational, never auto-cascades.  Auto-cascade
(rolling back downstream tables in the same click) lands as a
hypothetical  if a real demand surfaces.

The helper lives next to :mod:`pointlessql.services.lineage_edges`
and reuses the same best-effort posture: a DB error returns ``[]``
rather than raising into the rollback path.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from sqlalchemy import case, func, select

from pointlessql.models import LineageColumnMap, LineageRowEdge

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownstreamSpec:
    """One table that drank from the source.

    Attributes:
        target_table: Fully-qualified UC name of the downstream
            table.
        via: Which lineage axis carried the edge — ``"row"`` for
            ``lineage_row_edges``, ``"column"`` for
            ``lineage_column_map``, or ``"both"`` when the
            relationship surfaces on both axes (the common case
            for primitive-driven derivations).
        edge_count: Number of edges across all matching axes.
            Approximates "how much" of the downstream came from
            the source.
        most_recent_run_id: The ``run_id`` of the latest edge that
            carried this relationship, or ``None`` when the table
            has no edges (shouldn't happen but defensive).
    """

    target_table: str
    via: Literal["row", "column", "both"]
    edge_count: int
    most_recent_run_id: str | None


def find_downstream_tables(
    session_factory: Callable[[], Session],
    *,
    source_table: str,
) -> list[DownstreamSpec]:
    """Return tables that derived data from *source_table*.

    Walks ``lineage_row_edges`` (row-level provenance) and
    ``lineage_column_map`` (column-level provenance) for any row
    whose ``source_table`` matches.  Distinct downstream
    ``target_table`` names are aggregated into a single
    :class:`DownstreamSpec` with combined edge counts and the most
    recent ``run_id`` across both axes.

    The query is best-effort: any unexpected DB error is logged and
    swallowed, returning an empty list so the rollback-preview
    endpoint can render "no known downstream tables" instead of a
    500.

    Args:
        session_factory: SQLAlchemy session factory (typically
            ``app.state.session_factory``).
        source_table: Fully-qualified UC name of the source the
            operator is about to rollback.  Edges where
            ``source_table`` equals this string are aggregated.

    Returns:
        A list of :class:`DownstreamSpec`, one per distinct
        downstream table.  The list is sorted by edge_count
        descending, so the loudest dependency surfaces first.
        Empty when no edges match or the query failed.
    """
    try:
        with session_factory() as session:
            row_rows = list(
                session.execute(
                    select(
                        LineageRowEdge.target_table,
                        func.count(LineageRowEdge.id).label("edge_count"),
                        func.max(LineageRowEdge.run_id).label("most_recent_run_id"),
                    )
                    .where(LineageRowEdge.source_table == source_table)
                    .group_by(LineageRowEdge.target_table)
                )
            )
            col_rows = list(
                session.execute(
                    select(
                        LineageColumnMap.target_table,
                        func.count(LineageColumnMap.id).label("edge_count"),
                        func.max(
                            case(
                                (LineageColumnMap.run_id.is_not(None), LineageColumnMap.run_id),
                                else_=None,
                            )
                        ).label("most_recent_run_id"),
                    )
                    .where(LineageColumnMap.source_table == source_table)
                    .group_by(LineageColumnMap.target_table)
                )
            )
    except Exception:  # noqa: BLE001 — best-effort cascade preview
        logger.exception("cascade: find_downstream_tables failed for %s", source_table)
        return []

    @dataclass
    class _Bucket:
        row_edges: int = 0
        col_edges: int = 0
        row_recent: str | None = None
        col_recent: str | None = None

    by_table: dict[str, _Bucket] = {}
    for target_table, edge_count, most_recent in row_rows:
        if not isinstance(target_table, str) or target_table == source_table:
            continue
        bucket = by_table.setdefault(target_table, _Bucket())
        bucket.row_edges = int(edge_count) if edge_count is not None else 0
        bucket.row_recent = most_recent if isinstance(most_recent, str) else None
    for target_table, edge_count, most_recent in col_rows:
        if not isinstance(target_table, str) or target_table == source_table:
            continue
        bucket = by_table.setdefault(target_table, _Bucket())
        bucket.col_edges = int(edge_count) if edge_count is not None else 0
        bucket.col_recent = most_recent if isinstance(most_recent, str) else None

    specs: list[DownstreamSpec] = []
    for target_table, bucket in by_table.items():
        edge_count = bucket.row_edges + bucket.col_edges
        if edge_count == 0:
            continue
        if bucket.row_edges and bucket.col_edges:
            via: Literal["row", "column", "both"] = "both"
        elif bucket.row_edges:
            via = "row"
        else:
            via = "column"
        recents = [r for r in (bucket.row_recent, bucket.col_recent) if r]
        most_recent_run = max(recents) if recents else None
        specs.append(
            DownstreamSpec(
                target_table=target_table,
                via=via,
                edge_count=edge_count,
                most_recent_run_id=most_recent_run,
            )
        )
    specs.sort(key=lambda s: (-s.edge_count, s.target_table))
    return specs
