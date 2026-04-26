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

from pointlessql.models import LineageRowEdge

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
