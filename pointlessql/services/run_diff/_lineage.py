"""Lineage-shaped run diffs: rejects + value-change buckets + row counts + cell-level."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import func, select

from pointlessql.models import (
    AgentRunOperation,
    LineageRowReject,
    LineageValueChange,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def _reject_buckets(factory: sessionmaker[Session], run_id: str) -> dict[str, int]:
    """Return ``{reject_reason: count}`` for one run.

    Args:
        factory: SQLAlchemy session factory.
        run_id: ``AgentRun.id`` to bucket.

    Returns:
        Dict keyed by :class:`LineageRowReject.reason`.  Empty when
        the run has no rejects (``track_rejects=True`` not set on
        any merge).
    """
    with factory() as session:
        stmt = (
            select(LineageRowReject.reason, func.count(LineageRowReject.id))
            .where(LineageRowReject.run_id == run_id)
            .group_by(LineageRowReject.reason)
        )
        return {reason: int(count) for reason, count in session.execute(stmt).all()}


def _value_change_buckets(factory: sessionmaker[Session], run_id: str) -> dict[str, int]:
    """Return ``{target_table: count}`` of value changes for one run."""
    with factory() as session:
        stmt = (
            select(LineageValueChange.target_table, func.count(LineageValueChange.id))
            .where(LineageValueChange.run_id == run_id)
            .group_by(LineageValueChange.target_table)
        )
        return {table: int(count) for table, count in session.execute(stmt).all()}


def _row_count_per_table(factory: sessionmaker[Session], run_id: str) -> dict[str, int]:
    """Sum ``rows_affected`` per target table for one run."""
    with factory() as session:
        stmt = (
            select(
                AgentRunOperation.target_table,
                func.coalesce(func.sum(AgentRunOperation.rows_affected), 0),
            )
            .where(
                AgentRunOperation.agent_run_id == run_id,
                AgentRunOperation.target_table.is_not(None),
            )
            .group_by(AgentRunOperation.target_table)
        )
        return {
            table: int(total) for table, total in session.execute(stmt).all() if table is not None
        }


def _shift_dict(a: dict[str, int], b: dict[str, int]) -> dict[str, Any]:
    """Render ``{a: …, b: …, delta: …}`` over a union of keys.

    Args:
        a: Counts keyed by some bucket on the left side.
        b: Counts keyed by the same bucket on the right side.

    Returns:
        ``{"a": a_dict, "b": b_dict, "delta": {key: b - a}}``;
        keys missing on one side count as 0 there.  Sorted
        deterministically so the JSON response is reproducible.
    """
    keys = sorted(set(a.keys()) | set(b.keys()))
    delta = {k: int(b.get(k, 0)) - int(a.get(k, 0)) for k in keys}
    return {
        "a": {k: int(a.get(k, 0)) for k in keys},
        "b": {k: int(b.get(k, 0)) for k in keys},
        "delta": delta,
    }


def build_lineage_diff(
    factory: sessionmaker[Session],
    *,
    run_a_id: str,
    run_b_id: str,
) -> dict[str, Any]:
    """Compose the  lineage-shaped delta between two runs.

    The diff focuses on what *forensics* needs:

    * ``reject_pattern_shift`` — bucketed reject reasons on each
      side, plus a ``delta`` per reason (``b - a``) so a shift
      from "0 schema_mismatch" to "47 schema_mismatch" jumps out.
    * ``value_change_volume_per_table`` — per-target counts on
      each side; same delta structure.
    * ``row_count_delta_per_table`` — sum of ``rows_affected``
      per target.

    No soyuz roundtrip — every input is local.  Schema-drift
    (column-list compare) is intentionally deferred; it would
    require fan-out through ``UnityCatalogClient.get_table`` for
    every distinct table touched, which the current routes don't
    cache yet.

    Args:
        factory: SQLAlchemy session factory.
        run_a_id: Left side run UUID.
        run_b_id: Right side run UUID.

    Returns:
        ``{"reject_pattern_shift": {reasons, delta},
        "value_change_volume_per_table": {tables, delta},
        "row_count_delta_per_table": {tables, delta}}``.
    """
    rejects_a = _reject_buckets(factory, run_a_id)
    rejects_b = _reject_buckets(factory, run_b_id)
    vc_a = _value_change_buckets(factory, run_a_id)
    vc_b = _value_change_buckets(factory, run_b_id)
    rows_a = _row_count_per_table(factory, run_a_id)
    rows_b = _row_count_per_table(factory, run_b_id)
    return {
        "reject_pattern_shift": _shift_dict(rejects_a, rejects_b),
        "value_change_volume_per_table": _shift_dict(vc_a, vc_b),
        "row_count_delta_per_table": _shift_dict(rows_a, rows_b),
    }


_VALUE_CHANGES_DEFAULT_TOP_K = 50


def _load_value_changes(
    session: Session, run_id: str
) -> dict[tuple[str, int, str, str], LineageValueChange]:
    """Index :class:`LineageValueChange` rows by (table, op_id, row_id, column).

    The composite key uniquely identifies a single cell within a
    run.  When a run wrote the same cell more than once across
    multiple ops the *last* one wins — runs almost never do that
    in practice, and the cockpit's diff view doesn't try to
    visualise op-level cell history yet.
    """
    stmt = select(LineageValueChange).where(LineageValueChange.run_id == run_id)
    out: dict[tuple[str, int, str, str], LineageValueChange] = {}
    for row in session.scalars(stmt).all():
        key = (row.target_table, row.op_id, row.target_row_id, row.target_column)
        out[key] = row
    return out


def build_value_changes_diff(
    factory: sessionmaker[Session],
    *,
    run_a_id: str,
    run_b_id: str,
    top_k: int = _VALUE_CHANGES_DEFAULT_TOP_K,
    reveal: bool = False,
) -> dict[str, Any]:
    """Cell-level diff of :class:`LineageValueChange` rows across two runs.

    Extends :func:`build_lineage_diff` (volumes only) with the
    actual diverging cells.  For every (target_table,
    op_id, row_id, column) cell present in *both* runs, compares
    ``new_value``: equal pairs drop, divergent pairs surface as a
    single row in ``divergent_cells`` of the corresponding table
    bucket.  Cells unique to one run also surface as
    ``a_only`` / ``b_only`` lists per table.

    Cell values are masked to ``"***"`` unless ``reveal=True``;
    the route layer only flips that when the caller is admin so
    auditor-scope Hermes flows never leak cleartext.

    Output is capped at ``top_k`` rows per (table, op_id, axis)
    triple.  When the cap fires the bucket carries
    ``truncated=True`` so the UI can link to the existing
    ``/audit/value-changes`` page for full detail.

    Args:
        factory: SQLAlchemy session factory.
        run_a_id: Left side run UUID.
        run_b_id: Right side run UUID.
        top_k: Per-bucket row cap (default 50).
        reveal: When ``True``, store cleartext values; otherwise
            mask all ``a_value`` / ``b_value`` cells.

    Returns:
        ``{"top_k": int, "tables": [{"target_table", "op_id",
        "divergent_cells": [...], "a_only": [...], "b_only": [...],
        "truncated": bool}, ...]}``.
    """
    with factory() as session:
        cells_a = _load_value_changes(session, run_a_id)
        cells_b = _load_value_changes(session, run_b_id)

    keys = set(cells_a.keys()) | set(cells_b.keys())
    by_bucket: dict[tuple[str, int], dict[str, list[dict[str, Any]]]] = {}

    def _mask(value: str | None) -> str | None:
        if value is None:
            return None
        return value if reveal else "***"

    for key in sorted(keys):
        target_table, op_id, row_id, column = key
        bucket = by_bucket.setdefault(
            (target_table, op_id),
            {"divergent_cells": [], "a_only": [], "b_only": []},
        )
        cell_a = cells_a.get(key)
        cell_b = cells_b.get(key)
        if cell_a is not None and cell_b is not None:
            if cell_a.new_value == cell_b.new_value:
                continue
            bucket["divergent_cells"].append(
                {
                    "row_id": row_id,
                    "column": column,
                    "a_old_value": _mask(cell_a.old_value),
                    "a_new_value": _mask(cell_a.new_value),
                    "b_old_value": _mask(cell_b.old_value),
                    "b_new_value": _mask(cell_b.new_value),
                }
            )
        elif cell_a is not None:
            bucket["a_only"].append(
                {
                    "row_id": row_id,
                    "column": column,
                    "old_value": _mask(cell_a.old_value),
                    "new_value": _mask(cell_a.new_value),
                }
            )
        else:
            assert cell_b is not None  # noqa: S101 — exhausted the OR above
            bucket["b_only"].append(
                {
                    "row_id": row_id,
                    "column": column,
                    "old_value": _mask(cell_b.old_value),
                    "new_value": _mask(cell_b.new_value),
                }
            )

    tables: list[dict[str, Any]] = []
    for (target_table, op_id), data in sorted(by_bucket.items()):
        truncated = False
        for axis in ("divergent_cells", "a_only", "b_only"):
            rows = data[axis]
            if len(rows) > top_k:
                truncated = True
                data[axis] = rows[:top_k]
        tables.append(
            {
                "target_table": target_table,
                "op_id": op_id,
                "divergent_cells": data["divergent_cells"],
                "a_only": data["a_only"],
                "b_only": data["b_only"],
                "truncated": truncated,
            }
        )

    return {"top_k": top_k, "masked": not reveal, "tables": tables}
