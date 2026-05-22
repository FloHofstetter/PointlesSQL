"""Lineage axis — row-edge aggregates, rejects, unattributed writes."""

from __future__ import annotations

from typing import Any

from fastapi import Request
from sqlalchemy import func, select

from pointlessql.models import AgentRunOperation


def load_lineage_summary_for_run(
    request: Request,
    run_id: str,
    *,
    op_id: int | None = None,
) -> dict[str, Any]:
    """Aggregate ``lineage_row_edges`` per operation.

    Joins ``lineage_row_edges`` against ``agent_run_operations`` so
    the run-detail Lineage tab can render one row per op with
    source/target FQNs, op name, and edge count.  Operations with no
    recorded edges are excluded (the empty-state alert covers that).

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.
        op_id:  cross-axis filter — when set, restrict
            the aggregate to a single op.

    Returns:
        Dict shaped ``{"total_edges": int, "rows": [{
        "ordinal": int, "op_name": str, "source_table": str,
        "target_table": str, "edge_count": int,
        "sample_target_row_id": str | None}, ...]}`` ready to
        feed the run-detail Lineage tab.  ``sample_target_row_id``
        is an arbitrary representative row id for the (op, target)
        group — used by the Lineage sub-pills to deep-link a
        "Trace target row" click into the Row-trace pane.
    """
    from pointlessql.models import LineageRowEdge

    factory = request.app.state.session_factory
    rows: list[dict[str, Any]] = []
    total = 0
    with factory() as session:
        stmt = (
            select(
                AgentRunOperation.id,
                AgentRunOperation.ordinal,
                AgentRunOperation.op_name,
                AgentRunOperation.target_table,
                LineageRowEdge.source_table,
                func.count(LineageRowEdge.id).label("edge_count"),
                func.min(LineageRowEdge.target_row_id).label("sample_target_row_id"),
            )
            .join(LineageRowEdge, LineageRowEdge.op_id == AgentRunOperation.id)
            .where(AgentRunOperation.agent_run_id == run_id)
            .group_by(
                AgentRunOperation.id,
                AgentRunOperation.ordinal,
                AgentRunOperation.op_name,
                AgentRunOperation.target_table,
                LineageRowEdge.source_table,
            )
            .order_by(AgentRunOperation.ordinal)
        )
        if op_id is not None:
            stmt = stmt.where(AgentRunOperation.id == op_id)
        for row in session.execute(stmt).all():
            edge_count = int(row[5])
            total += edge_count
            rows.append(
                {
                    "ordinal": int(row[1]),
                    "op_name": row[2],
                    "target_table": row[3],
                    "source_table": row[4],
                    "edge_count": edge_count,
                    "sample_target_row_id": row[6],
                }
            )
    return {"total_edges": total, "rows": rows}


def load_rejects_for_run(
    request: Request,
    run_id: str,
    *,
    op_id: int | None = None,
) -> list[dict[str, Any]]:
    """Return ``lineage_row_rejects`` for the run-detail tab.

    Args:
        request: Incoming FastAPI request.
        run_id: Owning ``AgentRun.id``.
        op_id:  cross-axis filter — when set, restrict
            to rejects produced by this single op.  ``None`` keeps
            the full run-scoped list.

    Returns:
        List of dicts shaped ``{"op_id", "source_table",
        "source_row_id", "reason", "detail", "created_at"}`` in
        insertion order.  Empty list when no rejects were recorded
        (default — ``track_rejects=True`` not set on any merge call
        in the run).
    """
    from pointlessql.models import LineageRowReject

    factory = request.app.state.session_factory
    rows: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(LineageRowReject)
            .where(LineageRowReject.run_id == run_id)
            .order_by(LineageRowReject.id)
        )
        if op_id is not None:
            stmt = stmt.where(LineageRowReject.op_id == op_id)
        for r in session.scalars(stmt):
            rows.append(
                {
                    "op_id": r.op_id,
                    "source_table": r.source_table,
                    "source_row_id": r.source_row_id,
                    "reason": r.reason,
                    "detail": r.detail,
                    "created_at": r.created_at,
                }
            )
    return rows


def load_unattributed_for_run(
    request: Request,
    *,
    tables_touched: list[str],
) -> list[dict[str, Any]]:
    """Return ``unattributed_writes`` rows on tables this run touched.

    Filters to rows with ``acknowledged_at IS NULL`` so the
    run-detail surface highlights only the queue admins still need
    to triage.  Empty list when ``tables_touched`` is empty (no
    join surface) or no unacknowledged writes exist.

    Args:
        request: Incoming FastAPI request.
        tables_touched: Three-part UC names from the run's
            ``tables_touched`` JSON.

    Returns:
        List of dicts shaped like the admin page's entries.
    """
    if not tables_touched:
        return []
    from pointlessql.models import UnattributedWrite

    factory = request.app.state.session_factory
    out: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(UnattributedWrite)
            .where(
                UnattributedWrite.table_fqn.in_(tables_touched),
                UnattributedWrite.acknowledged_at.is_(None),
            )
            .order_by(UnattributedWrite.detected_at.desc())
            .limit(50)
        )
        for row in session.scalars(stmt).all():
            out.append(
                {
                    "id": row.id,
                    "table_fqn": row.table_fqn,
                    "delta_version": row.delta_version,
                    "commit_timestamp": (
                        row.commit_timestamp.isoformat() if row.commit_timestamp else None
                    ),
                    "detected_at": row.detected_at.isoformat(),
                }
            )
    return out
