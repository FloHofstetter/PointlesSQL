# pyright: reportPrivateUsage=false
"""``build_column_lineage_diff`` — edge-level column-lineage delta."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from sqlalchemy import select

from pointlessql.models import LineageColumnMap

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


_ColumnEdgeKey = tuple[int, str, str, str, str]


def _column_edge_key(row: LineageColumnMap) -> _ColumnEdgeKey:
    """Composite identity used to align two runs' column-lineage rows.

    The 5-tuple ``(op_id, source_table, source_column, target_table,
    target_column)`` is what makes one column-lineage edge
    distinguishable from another.  Including ``op_id`` rather than
    just the column-pair prevents two distinct ops touching the
    same columns from collapsing into one alignment slot.
    """
    # Run-scoped diffs only ever see rows from local agent runs, so
    # ``op_id`` is always non-NULL in this code path.  The
    # nullability on the column allows external-producer rows that
    # are explicitly filtered out before this helper runs; coerce
    # ``None`` to 0 defensively in case a future caller drifts.
    return (
        int(row.op_id) if row.op_id is not None else 0,
        row.source_table or "",
        row.source_column or "",
        row.target_table,
        row.target_column,
    )


def build_column_lineage_diff(
    factory: sessionmaker[Session],
    *,
    run_a_id: str,
    run_b_id: str,
) -> dict[str, Any]:
    """Edge-level diff of :class:`LineageColumnMap` rows across two runs.

    Identity tuple is ``(op_id, source_table, source_column,
    target_table, target_column)``.  Edges with the same identity
    but a different ``transform_kind`` or ``transform_detail`` are
    surfaced under ``edges_changed``.

    Args:
        factory: SQLAlchemy session factory.
        run_a_id: Left side run UUID.
        run_b_id: Right side run UUID.

    Returns:
        ``{"edges_only_in_a": [...], "edges_only_in_b": [...],
        "edges_changed": [{"a", "b", "kind_changed", "detail_changed"},
        ...]}``.  Each edge dict carries the five identity fields
        plus ``transform_kind`` / ``transform_detail``.
    """
    with factory() as session:
        rows_a = list(
            session.scalars(
                select(LineageColumnMap).where(LineageColumnMap.run_id == run_a_id)
            ).all()
        )
        rows_b = list(
            session.scalars(
                select(LineageColumnMap).where(LineageColumnMap.run_id == run_b_id)
            ).all()
        )

    by_key_a: dict[_ColumnEdgeKey, LineageColumnMap] = {_column_edge_key(r): r for r in rows_a}
    by_key_b: dict[_ColumnEdgeKey, LineageColumnMap] = {_column_edge_key(r): r for r in rows_b}
    keys_a = set(by_key_a.keys())
    keys_b = set(by_key_b.keys())

    def _serialize(row: LineageColumnMap) -> dict[str, Any]:
        return {
            "op_id": row.op_id,
            "source_table": row.source_table,
            "source_column": row.source_column,
            "target_table": row.target_table,
            "target_column": row.target_column,
            "transform_kind": row.transform_kind,
            "transform_detail": row.transform_detail,
        }

    edges_only_in_a = [_serialize(by_key_a[k]) for k in sorted(keys_a - keys_b)]
    edges_only_in_b = [_serialize(by_key_b[k]) for k in sorted(keys_b - keys_a)]
    edges_changed: list[dict[str, Any]] = []
    for key in sorted(keys_a & keys_b):
        a = by_key_a[key]
        b = by_key_b[key]
        kind_changed = a.transform_kind != b.transform_kind
        detail_changed = a.transform_detail != b.transform_detail
        if not kind_changed and not detail_changed:
            continue
        edges_changed.append(
            {
                "a": _serialize(a),
                "b": _serialize(b),
                "kind_changed": kind_changed,
                "detail_changed": detail_changed,
            }
        )

    return {
        "edges_only_in_a": edges_only_in_a,
        "edges_only_in_b": edges_only_in_b,
        "edges_changed": edges_changed,
    }
