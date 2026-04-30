"""Per-row lineage edge helpers (Sprint 15.3 + 15.4).

Sprint 15.3 fills the table from ``pql.merge`` and ``pql.write_table``;
Sprint 15.4 walks it backwards for the row-trace UI.  All inserts are
**best-effort** — a DB hiccup must never roll back a Delta write that
already committed.  Failures are returned to the caller as an
``Exception`` so the operation row can carry the
``[lineage_edges_partial]`` marker for the audit trail.
"""

from __future__ import annotations

import datetime
import hashlib
import logging
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import insert, select
from sqlalchemy.exc import SQLAlchemyError

from pointlessql.models import (
    LineageColumnMap,
    LineageRowEdge,
    LineageRowReject,
    LineageValueChange,
)

MAX_COLUMN_EDGES_PER_OP = 1000

MAX_VALUE_CHANGES_PER_OP = 100_000


class ColumnEdgeCapExceeded(Exception):
    """Raised when an op tries to record more than ``MAX_COLUMN_EDGES_PER_OP`` edges.

    Returned (not raised) by :func:`record_column_edges` so the caller
    can stamp a ``[lineage_column_partial]`` marker on the audit row.
    Mirrors the best-effort contract of :func:`record_edges` —
    column lineage failure must never roll back a Delta write.
    """


class ValueChangeCapExceeded(Exception):
    """Raised when an op tries to record more than ``MAX_VALUE_CHANGES_PER_OP`` rows.

    Returned (not raised) by :func:`record_value_changes` so the caller
    can stamp a ``[lineage_value_partial]`` marker on the audit row.
    Same best-effort contract as :class:`ColumnEdgeCapExceeded` —
    value-lineage failure must never roll back a Delta merge.
    """

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PredecessorRef:
    """One source-side edge feeding a :class:`LineageStep`.

    Sprint 15.5.2 — surfaces aggregate fan-in (and the occasional
    re-run history) on the row-trace UI.  Multiple predecessors per
    step mean either:

    * the row was produced by an aggregate operation that grouped
      several source rows into this output, or
    * the same merge ran more than once and stamped overlapping
      edges (audit history; deterministic re-runs reuse the target
      row id).

    Attributes:
        table: Fully-qualified UC name of the source row.
        row_id: ``_lineage_row_id`` value on the source row.
        op_id: ``agent_run_operations.id`` that produced this edge.
        run_id: PointlesSQL run UUID associated with the edge, or
            ``None`` when the join row is missing.
    """

    table: str
    row_id: str
    op_id: int
    run_id: str | None


@dataclass(frozen=True)
class LineageStep:
    """One node in a row-trace walkback."""

    depth: int
    table: str
    row_id: str
    op_id: int | None
    run_id: str | None
    source_file: str | None = None
    predecessors: tuple[PredecessorRef, ...] = ()


@dataclass(frozen=True)
class ColumnEdgeSpec:
    """One source-column → target-column mapping.

    Sprint 15.6.1 — bulk-insert input for :func:`record_column_edges`
    and the in-memory shape PQL primitives stash on the recorder
    until the post-commit hook persists them.

    ``source_table`` and ``source_column`` are nullable to support
    ``transform_kind == "unknown_origin"`` (audit columns, undeclared
    derived columns, ``sql_unknown`` projections).

    Attributes:
        source_table: Fully-qualified UC name of the source table,
            or ``None`` for ``unknown_origin`` edges.
        source_column: Source column name, or ``None`` for
            ``unknown_origin`` edges.
        target_table: Fully-qualified UC name of the target table.
        target_column: Target column name.
        transform_kind: One of
            :data:`pointlessql.models.lineage.TRANSFORM_KINDS`.
        transform_detail: Optional free-form context (aggregation
            function name for ``aggregate``, rendered subexpression
            for ``sql_function``, ``"audit"`` for audit columns,
            ``"synth_target_row_id"`` for the synthesised row-id
            edge).
    """

    source_table: str | None
    source_column: str | None
    target_table: str
    target_column: str
    transform_kind: str
    transform_detail: str | None = None


@dataclass(frozen=True)
class ColumnPredecessorRef:
    """One source-side column edge feeding a :class:`ColumnTraceStep`.

    Mirrors :class:`PredecessorRef` for the column-trace walkback.

    Attributes:
        table: Fully-qualified UC name of the source table, or
            ``None`` for ``unknown_origin`` edges.
        column: Source column name, or ``None`` for
            ``unknown_origin`` edges.
        op_id: ``agent_run_operations.id`` that produced this edge.
        run_id: PointlesSQL run UUID, or ``None`` when the join row
            is missing.
        transform_kind: How the source feeds the target.
        transform_detail: Optional context (see
            :class:`ColumnEdgeSpec`).
    """

    table: str | None
    column: str | None
    op_id: int
    run_id: str | None
    transform_kind: str
    transform_detail: str | None


@dataclass(frozen=True)
class ColumnTraceStep:
    """One node in a column-trace walkback."""

    depth: int
    table: str
    column: str
    op_id: int | None
    run_id: str | None
    predecessors: tuple[ColumnPredecessorRef, ...] = ()


@dataclass(frozen=True)
class ValueChangeSpec:
    """One per-cell preimage/postimage pair for ``lineage_value_changes``.

    Sprint 15.7.1 — bulk-insert input for :func:`record_value_changes`
    and the in-memory shape :func:`extract_value_changes` produces
    after pairing CDF events on ``_lineage_row_id``.

    ``old_value`` / ``new_value`` are stringified renders (Python's
    default ``str()``) of the underlying cell value; ``None`` means
    the cell was actually NULL.  No truncation happens here — the
    DB column is ``Text`` (unbounded).

    Attributes:
        target_table: Fully-qualified UC name of the table that holds
            the changed row.
        target_row_id: ``_lineage_row_id`` of the changed target row.
        target_column: Column name whose value changed.
        old_value: Stringified preimage value, or ``None`` for NULL.
        new_value: Stringified postimage value, or ``None`` for NULL.
    """

    target_table: str
    target_row_id: str
    target_column: str
    old_value: str | None
    new_value: str | None


def synth_target_row_id(source_row_id: str, target_table: str) -> str:
    """Mint a deterministic ``_lineage_row_id`` for a merged target row.

    Args:
        source_row_id: Source row's ``_lineage_row_id``.
        target_table: Fully-qualified UC name of the target.

    Returns:
        64-character lowercase hex digest stable across re-runs of
        the same merge.  Collisions across different
        ``(source_row_id, target_table)`` pairs are
        cryptographically negligible.
    """
    return hashlib.sha256(f"{source_row_id}:{target_table}".encode()).hexdigest()


def synth_aggregate_target_row_id(target_table: str, group_values: Sequence[Any]) -> str:
    """Mint a deterministic ``_lineage_row_id`` for an aggregate output row.

    The aggregate variant cannot reuse :func:`synth_target_row_id`
    because aggregations have N source IDs per target — using any
    single source would make the target ID depend on group ordering.
    Hashing the *group-by values* instead keeps the target ID stable
    across re-runs (same group keys → same target ID) while still
    being unique per group.  Source IDs go into the edges payload.

    Args:
        target_table: Fully-qualified UC name of the target.
        group_values: Values of the group-by columns for this output
            row, in the order the caller declared them.  Each value
            is stringified via ``str()`` for the digest input.

    Returns:
        64-character lowercase hex digest stable across re-runs of
        the same aggregation against the same target.
    """
    payload = target_table + ":" + "|".join(str(v) for v in group_values)
    return hashlib.sha256(payload.encode()).hexdigest()


def record_edges(
    session_factory: sessionmaker[Session],
    *,
    run_id: str,
    op_id: int,
    source_table: str,
    target_table: str,
    source_row_ids: Sequence[str],
    target_row_ids: Sequence[str],
    source_model_uri: str | None = None,
) -> Exception | None:
    """Bulk-insert one edge row per ``(source_row_id, target_row_id)`` pair.

    Args:
        session_factory: SQLAlchemy session factory.
        run_id: PointlesSQL ``agent_run_id`` driving the merge.
        op_id: ``agent_run_operations.id`` of the merge that created
            the edges.
        source_table: Fully-qualified UC name the rows were read from.
        target_table: Fully-qualified UC name the rows landed in.
        source_row_ids: Source-side ``_lineage_row_id`` values, one
            per row.  Must align element-wise with
            ``target_row_ids``.
        target_row_ids: Target-side IDs synthesised by
            :func:`synth_target_row_id`.
        source_model_uri: Sprint 21.7 — when set, every edge row
            carries the originating model URI so the model-detail
            DAG can paint the downstream "Predictions" half.

    Returns:
        ``None`` on a successful commit (or when both ID lists are
        empty / the lengths don't line up — both treated as no-ops).
        The underlying ``Exception`` when the insert failed so the
        caller can stamp ``[lineage_edges_partial]`` on the audit row.
    """
    n = min(len(source_row_ids), len(target_row_ids))
    if n == 0 or len(source_row_ids) != len(target_row_ids):
        return None

    now = datetime.datetime.now(datetime.UTC)
    rows = [
        {
            "run_id": run_id,
            "op_id": op_id,
            "source_table": source_table,
            "source_row_id": source_row_ids[i],
            "target_table": target_table,
            "target_row_id": target_row_ids[i],
            "source_model_uri": source_model_uri,
            "created_at": now,
        }
        for i in range(n)
    ]

    try:
        with session_factory() as session:
            session.execute(insert(LineageRowEdge), rows)
            session.commit()
        return None
    except SQLAlchemyError as exc:
        logger.info(
            "lineage_row_edges insert failed for run=%s op=%s n=%s: %s",
            run_id,
            op_id,
            n,
            exc,
        )
        return exc


def record_rejects(
    session_factory: sessionmaker[Session],
    *,
    run_id: str,
    op_id: int,
    source_table: str,
    rejects: Sequence[tuple[str, str, str | None]],
) -> Exception | None:
    """Bulk-insert rejected-row markers into ``lineage_row_rejects``.

    Sprint 15.5.3 — populated by ``pql.merge(track_rejects=True)``
    when a pre-merge set-diff identifies source rows that won't land.

    Args:
        session_factory: SQLAlchemy session factory.
        run_id: PointlesSQL ``agent_run_id``.
        op_id: ``agent_run_operations.id`` of the merge call.
        source_table: Fully-qualified UC name the rejects came from.
        rejects: ``[(source_row_id, reason, detail), ...]`` —
            ``reason`` must be one of
            :data:`pointlessql.models.lineage.REJECT_REASONS`;
            ``detail`` is optional free-form context.  Empty input is
            a no-op.

    Returns:
        ``None`` on success or empty input.  The underlying
        ``Exception`` when the insert failed so the caller can stamp
        a marker on the audit row.
    """
    if not rejects:
        return None

    now = datetime.datetime.now(datetime.UTC)
    rows = [
        {
            "run_id": run_id,
            "op_id": op_id,
            "source_table": source_table,
            "source_row_id": source_row_id,
            "reason": reason,
            "detail": detail,
            "created_at": now,
        }
        for source_row_id, reason, detail in rejects
    ]

    try:
        with session_factory() as session:
            session.execute(insert(LineageRowReject), rows)
            session.commit()
        return None
    except SQLAlchemyError as exc:
        logger.info(
            "lineage_row_rejects insert failed for run=%s op=%s n=%s: %s",
            run_id,
            op_id,
            len(rows),
            exc,
        )
        return exc


def fetch_target_row_predecessors(
    session_factory: sessionmaker[Session],
    *,
    target_table: str,
    target_row_id: str,
) -> list[LineageRowEdge]:
    """Return every edge that lands on ``target_row_id`` in ``target_table``.

    Args:
        session_factory: SQLAlchemy session factory.
        target_table: Fully-qualified UC name to filter on.
        target_row_id: ``_lineage_row_id`` value of the row to trace.

    Returns:
        All matching edges, ordered by ``created_at`` ascending so
        the oldest merge appears first.  Multiple edges per row are
        possible when the merge ran more than once.
    """
    with session_factory() as session:
        stmt = (
            select(LineageRowEdge)
            .where(
                LineageRowEdge.target_table == target_table,
                LineageRowEdge.target_row_id == target_row_id,
            )
            .order_by(LineageRowEdge.created_at.asc())
        )
        return list(session.scalars(stmt))


def fetch_source_row_descendants(
    session_factory: sessionmaker[Session],
    *,
    source_table: str,
    source_row_id: str,
) -> list[LineageRowEdge]:
    """Return every edge that this source row ever fed.

    Args:
        session_factory: SQLAlchemy session factory.
        source_table: Fully-qualified UC name to filter on.
        source_row_id: ``_lineage_row_id`` value of the row to trace
            forward.

    Returns:
        All edges with this source, ordered ``created_at`` ascending.
    """
    with session_factory() as session:
        stmt = (
            select(LineageRowEdge)
            .where(
                LineageRowEdge.source_table == source_table,
                LineageRowEdge.source_row_id == source_row_id,
            )
            .order_by(LineageRowEdge.created_at.asc())
        )
        return list(session.scalars(stmt))


def count_edges_for_op(
    session_factory: sessionmaker[Session], op_ids: Iterable[int]
) -> dict[int, int]:
    """Return ``{op_id: edge_count}`` for the given ops.

    Args:
        session_factory: SQLAlchemy session factory.
        op_ids: Operation IDs to count edges for.  Empty input
            yields an empty dict.

    Returns:
        Mapping with one entry per op-id that produced at least one
        edge; ops with no edges are absent.
    """
    op_id_list = [int(o) for o in op_ids]
    if not op_id_list:
        return {}
    from sqlalchemy import func

    with session_factory() as session:
        stmt = (
            select(LineageRowEdge.op_id, func.count(LineageRowEdge.id))
            .where(LineageRowEdge.op_id.in_(op_id_list))
            .group_by(LineageRowEdge.op_id)
        )
        result: dict[int, int] = {}
        for op_id, count in session.execute(stmt).all():
            result[int(op_id)] = int(count)
        return result


def walk_back(
    session_factory: sessionmaker[Session],
    *,
    table: str,
    row_id: str,
    max_hops: int = 20,
) -> list[LineageStep]:
    """Walk the lineage graph backward from one row to its bronze root.

    Each step records **every** predecessor edge that feeds the
    current ``(table, row_id)`` pair via :class:`PredecessorRef`
    entries on :attr:`LineageStep.predecessors`, so the row-trace UI
    can surface aggregate fan-in (one target produced by N source
    rows in a single ``pql.aggregate`` op) and re-run history (the
    same merge ran twice and stamped overlapping edges).  The
    chain-recursion still picks the **oldest** predecessor at each
    step so the walk remains deterministic.

    The walk stops when no predecessor exists (we're at the bronze
    root or at a table that lost its lineage column) or when
    ``max_hops`` is reached (defensive guard against accidental
    cycles, which the deterministic ID synthesis should make
    impossible).

    Args:
        session_factory: SQLAlchemy session factory.
        table: Fully-qualified UC name of the row to trace.
        row_id: ``_lineage_row_id`` of the row to trace.
        max_hops: Maximum walk depth.  Defaults to 20.

    Returns:
        A list of :class:`LineageStep`, depth-0 being the input row
        itself and the last step being the deepest reachable
        ancestor.  Each step's :attr:`predecessors` lists the edges
        that fed it (length ≥ 1 when an incoming edge exists; length
        > 1 means fan-in).  An empty list is **never** returned —
        depth-0 is always present, possibly with empty
        ``predecessors`` when no edge lands on the input row.
    """
    steps: list[LineageStep] = []
    seen: set[tuple[str, str]] = set()

    current_table = table
    current_row = row_id
    depth = 0

    seen.add((current_table, current_row))
    pending_step = LineageStep(
        depth=depth,
        table=current_table,
        row_id=current_row,
        op_id=None,
        run_id=None,
    )

    while True:
        predecessors = fetch_target_row_predecessors(
            session_factory, target_table=current_table, target_row_id=current_row
        )
        pred_refs = tuple(
            PredecessorRef(
                table=edge.source_table,
                row_id=edge.source_row_id,
                op_id=edge.op_id,
                run_id=edge.run_id,
            )
            for edge in predecessors
        )
        steps.append(
            LineageStep(
                depth=pending_step.depth,
                table=pending_step.table,
                row_id=pending_step.row_id,
                op_id=pending_step.op_id,
                run_id=pending_step.run_id,
                source_file=pending_step.source_file,
                predecessors=pred_refs,
            )
        )

        if not predecessors or depth >= max_hops:
            break

        edge = predecessors[0]
        next_key = (edge.source_table, edge.source_row_id)
        if next_key in seen:
            break

        depth += 1
        seen.add(next_key)
        current_table = edge.source_table
        current_row = edge.source_row_id
        pending_step = LineageStep(
            depth=depth,
            table=current_table,
            row_id=current_row,
            op_id=edge.op_id,
            run_id=edge.run_id,
        )

    return steps


def record_column_edges(
    session_factory: sessionmaker[Session],
    *,
    run_id: str,
    op_id: int,
    edges: Sequence[ColumnEdgeSpec],
) -> Exception | None:
    """Bulk-insert one row per :class:`ColumnEdgeSpec` into ``lineage_column_map``.

    Sprint 15.6.1 — column-level analog of :func:`record_edges`.
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
    rows = [
        {
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

    Sprint 15.6.1 — column-level analog of :func:`walk_back`.  Each
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


def record_value_changes(
    session_factory: sessionmaker[Session],
    *,
    run_id: str,
    op_id: int,
    changes: Sequence[ValueChangeSpec],
    pii_mode: str = "store_clear",
    pii_hash_secret: str | None = None,
) -> Exception | None:
    """Bulk-insert one row per :class:`ValueChangeSpec` into ``lineage_value_changes``.

    Sprint 15.7.1 — value-level analog of :func:`record_column_edges`.
    Same best-effort contract: the function returns the exception
    rather than raising, so a Delta merge that already committed never
    rolls back.  The audit row gets a ``[lineage_value_partial]``
    marker stamped by the caller.

    The 100k-row cap (:data:`MAX_VALUE_CHANGES_PER_OP`) gates
    pathological full-table upserts where most rows changed across
    most columns.  When breached the function inserts no rows and
    returns a :class:`ValueChangeCapExceeded` sentinel.

    Sprint 20.1 adds the PII redaction hook: when ``pii_mode`` is
    ``hash_only`` or ``redact_with_audit_log``, every column whose
    name matches
    :data:`pointlessql.services.pii_redactor.PII_NAME_PATTERN` gets
    its ``old_value`` / ``new_value`` rewritten before insert.
    ``hash_only`` keeps equality joinable across runs; the
    ``redact_with_audit_log`` mode also appends a single
    ``audit_log`` row noting the redaction count.

    Args:
        session_factory: SQLAlchemy session factory.
        run_id: PointlesSQL ``agent_run_id`` driving the merge.
        op_id: ``agent_run_operations.id`` of the merge.
        changes: Value-change specs to persist.  Empty input is a
            no-op.
        pii_mode: One of ``store_clear`` (default — no rewrite),
            ``hash_only``, ``redact_with_audit_log``.  Resolves
            from :attr:`pointlessql.settings.AuditSettings.pii_mode`
            in production callers.
        pii_hash_secret: Pre-shared secret for ``hash_only`` mode.
            ``None`` triggers a lazy auto-generation via
            :func:`pointlessql.services.pii_redactor.get_or_create_pii_hash_secret`.

    Returns:
        ``None`` on success or empty input.
        :class:`ValueChangeCapExceeded` when the cap was breached
        (zero rows written).  The underlying ``Exception`` when the
        bulk insert failed.
    """
    if not changes:
        return None

    if len(changes) > MAX_VALUE_CHANGES_PER_OP:
        msg = (
            f"value-change count {len(changes)} exceeds per-op cap "
            f"{MAX_VALUE_CHANGES_PER_OP}; skipping insert"
        )
        logger.info(
            "lineage_value_changes cap exceeded for run=%s op=%s: %s",
            run_id,
            op_id,
            msg,
        )
        return ValueChangeCapExceeded(msg)

    redacted_count = 0
    if pii_mode != "store_clear":
        from pointlessql.services.pii_redactor import (
            get_or_create_pii_hash_secret,
            hash_value,
            is_pii_by_name,
            redact_value,
        )

        secret: str | None = pii_hash_secret
        if pii_mode == "hash_only" and not secret:
            try:
                secret = get_or_create_pii_hash_secret(session_factory)
            except Exception as exc:  # noqa: BLE001 — fall back to redact
                logger.warning(
                    "pii_redactor: secret generation failed (run=%s op=%s): %s; "
                    "falling back to redact_with_audit_log mode for this op",
                    run_id,
                    op_id,
                    exc,
                )
                pii_mode = "redact_with_audit_log"

        new_changes: list[ValueChangeSpec] = []
        from dataclasses import replace as _dc_replace

        for change in changes:
            if not is_pii_by_name(change.target_column):
                new_changes.append(change)
                continue
            if pii_mode == "hash_only":
                new_changes.append(
                    _dc_replace(
                        change,
                        old_value=hash_value(change.old_value, secret=secret or ""),
                        new_value=hash_value(change.new_value, secret=secret or ""),
                    )
                )
            else:  # redact_with_audit_log
                new_changes.append(
                    _dc_replace(
                        change,
                        old_value=redact_value(change.old_value),
                        new_value=redact_value(change.new_value),
                    )
                )
            redacted_count += 1
        changes = new_changes

    now = datetime.datetime.now(datetime.UTC)
    rows = [
        {
            "run_id": run_id,
            "op_id": op_id,
            "target_table": change.target_table,
            "target_row_id": change.target_row_id,
            "target_column": change.target_column,
            "old_value": change.old_value,
            "new_value": change.new_value,
            "created_at": now,
        }
        for change in changes
    ]

    try:
        with session_factory() as session:
            session.execute(insert(LineageValueChange), rows)
            session.commit()
    except SQLAlchemyError as exc:
        logger.info(
            "lineage_value_changes insert failed for run=%s op=%s n=%s: %s",
            run_id,
            op_id,
            len(rows),
            exc,
        )
        return exc

    if pii_mode == "redact_with_audit_log" and redacted_count > 0:
        from pointlessql.services.audit import log_action

        try:
            log_action(
                session_factory,
                0,
                "system:pii_redactor",
                "pii_redact",
                f"agent_run_operations:{op_id}",
                {"redacted_count": redacted_count, "mode": pii_mode},
                actor_role="system",
            )
        except Exception:  # noqa: BLE001 — audit-log failure must not break write
            logger.exception(
                "pii_redactor: audit_log append failed for run=%s op=%s",
                run_id,
                op_id,
            )

    return None


def count_value_changes_for_op(
    session_factory: sessionmaker[Session], op_ids: Iterable[int]
) -> dict[int, int]:
    """Return ``{op_id: value_change_count}`` for the given ops.

    Used by the run-detail Operations tab to surface a "value changes:
    N" counter alongside the existing row-edge / column-edge counters.

    Args:
        session_factory: SQLAlchemy session factory.
        op_ids: Operation IDs to count value changes for.

    Returns:
        Mapping with one entry per op-id that produced at least one
        value change.
    """
    op_id_list = [int(o) for o in op_ids]
    if not op_id_list:
        return {}
    from sqlalchemy import func

    with session_factory() as session:
        stmt = (
            select(LineageValueChange.op_id, func.count(LineageValueChange.id))
            .where(LineageValueChange.op_id.in_(op_id_list))
            .group_by(LineageValueChange.op_id)
        )
        result: dict[int, int] = {}
        for op_id, count in session.execute(stmt).all():
            result[int(op_id)] = int(count)
        return result


def fetch_value_changes_for_row(
    session_factory: sessionmaker[Session],
    *,
    target_table: str,
    target_row_id: str,
    column: str | None = None,
) -> list[LineageValueChange]:
    """Return every value-change row for ``(target_table, target_row_id)``.

    Args:
        session_factory: SQLAlchemy session factory.
        target_table: Fully-qualified UC name of the target table.
        target_row_id: ``_lineage_row_id`` of the target row.
        column: When given, narrow to one column.

    Returns:
        All matching changes, ordered by ``created_at`` ascending so
        the oldest update appears first.  A single re-run that
        touched N columns of one row produces N rows with the same
        ``op_id``.
    """
    with session_factory() as session:
        stmt = select(LineageValueChange).where(
            LineageValueChange.target_table == target_table,
            LineageValueChange.target_row_id == target_row_id,
        )
        if column is not None:
            stmt = stmt.where(LineageValueChange.target_column == column)
        stmt = stmt.order_by(LineageValueChange.created_at.asc())
        return list(session.scalars(stmt))


def lookup_bronze_source_file(*, table: str, row_id: str, storage_location: str) -> str | None:
    """Read ``_source_file`` for one bronze row, by ``_lineage_row_id``.

    Used by the row-trace UI to put a "this came from ``orders.csv``"
    label on the deepest walkback step.  Best-effort — returns
    ``None`` when the table can't be opened, the column is missing,
    or no row matches.

    Args:
        table: Fully-qualified UC name (purely informational here —
            ``storage_location`` is what we actually open).
        row_id: ``_lineage_row_id`` to look up.
        storage_location: Delta-table URI from soyuz-catalog.

    Returns:
        The ``_source_file`` cell value, or ``None`` when not found.
    """
    try:
        import deltalake
        import duckdb
    except ImportError:
        return None

    try:
        dt = deltalake.DeltaTable(storage_location)
        dataset = dt.to_pyarrow_dataset()
    except Exception:  # noqa: BLE001 — best-effort lookup
        return None

    conn: Any = duckdb.connect()
    try:
        conn.register("_lineage_table", dataset)
        cursor = conn.execute(
            "SELECT _source_file FROM _lineage_table WHERE _lineage_row_id = ? LIMIT 1",
            [row_id],
        )
        row = cursor.fetchone()
        if row is None:
            return None
        value = row[0]
        return str(value) if value is not None else None
    except Exception:  # noqa: BLE001 — column may be missing on older bronze tables
        logger.debug("lookup_bronze_source_file failed for %s row_id=%s", table, row_id)
        return None
    finally:
        conn.close()
