"""Column-level lineage capture + walkback.

Owns the ``LineageColumnMap`` write path plus ``walk_back_columns``
and the column-edge counter used by the run-detail Operations tab.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterable, Sequence
from typing import TYPE_CHECKING

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError

from pointlessql.models import LineageColumnMap
from pointlessql.services.lineage._types import (
    MAX_COLUMN_EDGES_PER_OP,
    ColumnEdgeCapExceeded,
    ColumnEdgeSpec,
    ColumnPredecessorRef,
    ColumnTraceStep,
    logger,
    workspace_id_for_op,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def record_column_edges(
    session_factory: sessionmaker[Session],
    *,
    run_id: str,
    op_id: int,
    edges: Sequence[ColumnEdgeSpec],
) -> Exception | None:
    """Bulk-insert one row per :class:`ColumnEdgeSpec` into ``lineage_column_map``.

    column-level analog of :func:`record_edges`.
    Same best-effort contract: a DB hiccup or cap breach is returned
    to the caller, never raised, so the Delta write upstream never
    rolls back.  The audit row gets a ``[lineage_column_partial]``
    marker stamped by the caller.

    A 1000-edge cap (:data:`MAX_COLUMN_EDGES_PER_OP`) gates pathological
    ``pql.sql`` queries.  When breached the function inserts no rows
    and returns a :class:`ColumnEdgeCapExceeded` sentinel.

    Args:
        session_factory: SQLAlchemy session factory.
        run_id: PointlesSQL ``agent_run_id`` driving the op.
        op_id: ``agent_run_operations.id`` of the producing op.
        edges: Column-edge specs to persist.  Empty input is a no-op.

    Returns:
        ``None`` on success or empty input.
        :class:`ColumnEdgeCapExceeded` when the cap was breached
        (zero rows written).  The underlying ``Exception`` when the
        bulk insert failed.
    """
    if not edges:
        return None

    if len(edges) > MAX_COLUMN_EDGES_PER_OP:
        msg = (
            f"column-edge count {len(edges)} exceeds per-op cap "
            f"{MAX_COLUMN_EDGES_PER_OP}; skipping insert"
        )
        logger.info("lineage_column_map cap exceeded for run=%s op=%s: %s", run_id, op_id, msg)
        return ColumnEdgeCapExceeded(msg)

    now = datetime.datetime.now(datetime.UTC)
    workspace_id = workspace_id_for_op(session_factory, op_id)
    rows = [
        {
            "workspace_id": workspace_id,
            "run_id": run_id,
            "op_id": op_id,
            "source_table": edge.source_table,
            "source_column": edge.source_column,
            "target_table": edge.target_table,
            "target_column": edge.target_column,
            "transform_kind": edge.transform_kind,
            "transform_detail": edge.transform_detail,
            "created_at": now,
        }
        for edge in edges
    ]

    try:
        with session_factory() as session:
            session.execute(insert(LineageColumnMap), rows)
            session.commit()
        return None
    except SQLAlchemyError as exc:
        logger.info(
            "lineage_column_map insert failed for run=%s op=%s n=%s: %s",
            run_id,
            op_id,
            len(rows),
            exc,
        )
        return exc


def fetch_target_column_predecessors(
    session_factory: sessionmaker[Session],
    *,
    target_table: str,
    target_column: str,
) -> list[LineageColumnMap]:
    """Return every column edge that lands on ``(target_table, target_column)``.

    Args:
        session_factory: SQLAlchemy session factory.
        target_table: Fully-qualified UC name of the target table.
        target_column: Target column name.

    Returns:
        All matching edges, ordered by ``created_at`` ascending so
        the oldest op appears first.  An aggregate-style fan-in
        (one target column produced by N source columns in a single
        op) shows up as N edges with the same ``op_id``.
    """
    with session_factory() as session:
        stmt = (
            select(LineageColumnMap)
            .where(
                LineageColumnMap.target_table == target_table,
                LineageColumnMap.target_column == target_column,
            )
            .order_by(LineageColumnMap.created_at.asc())
        )
        return list(session.scalars(stmt))


def count_column_edges_for_op(
    session_factory: sessionmaker[Session], op_ids: Iterable[int]
) -> dict[int, int]:
    """Return ``{op_id: column_edge_count}`` for the given ops.

    Used by the run-detail Operations tab to surface a "column edges:
    N" counter alongside the existing row-edge counter.

    Args:
        session_factory: SQLAlchemy session factory.
        op_ids: Operation IDs to count edges for.

    Returns:
        Mapping with one entry per op-id that produced at least one
        column edge.
    """
    op_id_list = [int(o) for o in op_ids]
    if not op_id_list:
        return {}
    from sqlalchemy import func

    with session_factory() as session:
        stmt = (
            select(LineageColumnMap.op_id, func.count(LineageColumnMap.id))
            .where(LineageColumnMap.op_id.in_(op_id_list))
            .group_by(LineageColumnMap.op_id)
        )
        result: dict[int, int] = {}
        for op_id, count in session.execute(stmt).all():
            result[int(op_id)] = int(count)
        return result


def walk_back_columns(
    session_factory: sessionmaker[Session],
    *,
    table: str,
    column: str,
    max_hops: int = 20,
) -> list[ColumnTraceStep]:
    """Walk the column-lineage graph backward from one column to its sources.

    column-level analog of :func:`walk_back`.  Each
    step records every predecessor edge that feeds the current
    ``(table, column)`` pair via :class:`ColumnPredecessorRef` entries.
    The chain-recursion picks the **first unique** source column at
    each step so the walk remains deterministic; remaining
    predecessors surface as click-through leaves.

    The walk stops when no predecessor exists, when an
    ``unknown_origin`` edge breaks the chain (no source column to
    follow), or when ``max_hops`` is reached.

    Args:
        session_factory: SQLAlchemy session factory.
        table: Fully-qualified UC name of the column to trace.
        column: Column name to trace.
        max_hops: Maximum walk depth.  Defaults to 20.

    Returns:
        A list of :class:`ColumnTraceStep`, depth-0 being the input
        column itself.  Depth-0 always appears, possibly with empty
        ``predecessors`` when no edge lands on the input column.
    """
    steps: list[ColumnTraceStep] = []
    seen: set[tuple[str, str]] = set()

    current_table = table
    current_column = column
    depth = 0

    seen.add((current_table, current_column))
    pending_step = ColumnTraceStep(
        depth=depth,
        table=current_table,
        column=current_column,
        op_id=None,
        run_id=None,
    )

    while True:
        predecessors = fetch_target_column_predecessors(
            session_factory,
            target_table=current_table,
            target_column=current_column,
        )
        pred_refs = tuple(
            ColumnPredecessorRef(
                table=edge.source_table,
                column=edge.source_column,
                op_id=edge.op_id,
                run_id=edge.run_id,
                transform_kind=edge.transform_kind,
                transform_detail=edge.transform_detail,
            )
            for edge in predecessors
        )
        steps.append(
            ColumnTraceStep(
                depth=pending_step.depth,
                table=pending_step.table,
                column=pending_step.column,
                op_id=pending_step.op_id,
                run_id=pending_step.run_id,
                predecessors=pred_refs,
            )
        )

        if not predecessors or depth >= max_hops:
            break

        next_table: str | None = None
        next_column: str | None = None
        next_op_id: int | None = None
        next_run_id: str | None = None
        for edge in predecessors:
            if edge.source_table is None or edge.source_column is None:
                continue
            key = (edge.source_table, edge.source_column)
            if key in seen:
                continue
            next_table = edge.source_table
            next_column = edge.source_column
            next_op_id = edge.op_id
            next_run_id = edge.run_id
            break

        if next_table is None or next_column is None:
            break

        depth += 1
        seen.add((next_table, next_column))
        current_table = next_table
        current_column = next_column
        pending_step = ColumnTraceStep(
            depth=depth,
            table=current_table,
            column=current_column,
            op_id=next_op_id,
            run_id=next_run_id,
        )

    return steps
