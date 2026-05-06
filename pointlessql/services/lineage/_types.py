"""Shared types, exceptions, constants, and helpers for the lineage subpackage.

Holds the public dataclasses (``PredecessorRef``, ``LineageStep``,
``ColumnEdgeSpec``, ``ColumnPredecessorRef``, ``ColumnTraceStep``,
``ValueChangeSpec``), the per-op caps (``MAX_COLUMN_EDGES_PER_OP``,
``MAX_VALUE_CHANGES_PER_OP``) + matching exceptions, plus the
deterministic-id helpers (``synth_target_row_id``,
``synth_aggregate_target_row_id``) and the workspace-id resolver.
"""

from __future__ import annotations

import hashlib
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.models import AgentRunOperation

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


logger = logging.getLogger("pointlessql.services.lineage")


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


@dataclass(frozen=True)
class PredecessorRef:
    """One source-side edge feeding a :class:`LineageStep`.

    surfaces aggregate fan-in (and the occasional
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

    bulk-insert input for :func:`record_column_edges`
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

    bulk-insert input for :func:`record_value_changes`
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


def workspace_id_for_op(session_factory: sessionmaker[Session], op_id: int | None) -> int:
    """Return the workspace_id of the parent agent_run_operation, or 1.

    Every lineage row inherits its workspace from the op that
    created it.  Best-effort: a missing op_id (or DB hiccup) falls
    back to the seeded default workspace so a row can still be
    written rather than dropped.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: ``agent_run_operations.id`` of the parent op.  ``None``
            (or unknown id) returns 1.

    Returns:
        The parent op's ``workspace_id``, or ``1`` on miss.
    """
    if op_id is None:
        return 1
    try:
        with session_factory() as session:
            value = session.scalar(
                select(AgentRunOperation.workspace_id).where(AgentRunOperation.id == op_id)
            )
            return int(value) if value is not None else 1
    except Exception:  # noqa: BLE001 — fallback path
        return 1


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
