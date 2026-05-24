"""Cell-level lineage read-side.

A "lineage badge" is the small `<table-name>` chip the editor will
render in the cell header when a cell has previously written to one
or more Delta tables.  The write history already lives in
:class:`pointlessql.models.AgentRunOperation` rows whose
``op_name`` is in the WRITE set (``write_table``, ``merge``,
``autoload``, ``update``, ``delete``, etc.); they get an
``agent_run_id`` linkable back to a :class:`NotebookCellRun` row.

This module is the read helper that joins the two so the editor
can fetch ``{file_path, content_hash} → [badge, …]`` without
hand-rolling SQL at the route layer.  The route surface is in
:mod:`pointlessql.api.notebooks_routes.cell_lineage`.

Only cell-runs that already have a non-null ``agent_run_id`` are
matched — pure-Python notebook cells without an agent-run context
silently return an empty list.  That matches the Phase 98.C
contract: badges surface what the audit trail already captured.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.models.agent._audit import AgentRunOperation
from pointlessql.models.notebook import NotebookCellRun

#: ``op_name`` values that count as a "write" for badge purposes.
#: Read-only ops like ``sql`` / ``aggregate`` / ``sql_explain`` are
#: intentionally excluded — they show up in the run-history popover,
#: not in the cell-header lineage chip.
WRITE_OP_NAMES: frozenset[str] = frozenset(
    (
        "write_table",
        "merge",
        "autoload",
        "update",
        "delete",
        "drop_table",
        "create_schema",
        "drop_schema",
        "alter_table",
        "branch_create",
        "branch_promote",
        "branch_discard",
        "dbt_model",
        "train_model",
    )
)


def list_cell_lineage_badges(
    session: Session,
    *,
    file_path: str,
    content_hash: str,
) -> list[dict[str, Any]]:
    """Return write-op badges for one cell.

    Args:
        session: A SQLAlchemy session.
        file_path: Notebook path relative to ``notebooks_dir``.
        content_hash: ``sha256(source)[:16]`` of the cell source —
            the same identity column :class:`NotebookCellRun` keys on.

    Returns:
        List of badge dicts ordered most-recent-first:
        ``{"op_name": str, "target_table": str | None,
          "rows_affected": int | None,
          "delta_version_after": int | None,
          "started_at": iso8601-str}``.

    Duplicate ``(op_name, target_table)`` pairs are collapsed to the
    most recent occurrence so the header chip strip stays compact —
    the run-history popover keeps the full N-runs detail.
    """
    stmt = (
        select(
            NotebookCellRun.agent_run_id,
            NotebookCellRun.started_at,
        )
        .where(
            NotebookCellRun.file_path == file_path,
            NotebookCellRun.content_hash == content_hash,
            NotebookCellRun.agent_run_id.is_not(None),
        )
        .order_by(NotebookCellRun.started_at.desc())
    )
    cell_runs = session.execute(stmt).all()
    if not cell_runs:
        return []

    run_ids = [row.agent_run_id for row in cell_runs if row.agent_run_id]
    if not run_ids:
        return []

    op_stmt = (
        select(AgentRunOperation)
        .where(
            AgentRunOperation.agent_run_id.in_(run_ids),
            AgentRunOperation.op_name.in_(WRITE_OP_NAMES),
        )
        .order_by(AgentRunOperation.started_at.desc())
    )
    ops = session.execute(op_stmt).scalars().all()

    seen: set[tuple[str, str | None]] = set()
    out: list[dict[str, Any]] = []
    for op in ops:
        key = (op.op_name, op.target_table)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "op_name": op.op_name,
                "target_table": op.target_table,
                "rows_affected": op.rows_affected,
                "delta_version_after": op.delta_version_after,
                "started_at": op.started_at.isoformat(),
            }
        )
    return out


def list_cell_lineage_badges_bulk(
    session: Session,
    *,
    file_path: str,
) -> dict[str, list[dict[str, Any]]]:
    """Return ``{content_hash: [badge, ...]}`` for every cell in one notebook.

    The per-cell route exists for deep-link / detail use; the editor's
    cell-header chip strip needs N badges in a single call so the
    bulk variant avoids the N+1.

    Args:
        session: A SQLAlchemy session.
        file_path: Notebook path relative to ``notebooks_dir``.

    Returns:
        ``{content_hash: [badge, ...]}`` keyed by the cell-source
        identity column shared with :class:`NotebookCellRun`.  Cells
        with no write history are omitted; callers default to an
        empty list per row.  Same per-badge shape and dedup rules as
        :func:`list_cell_lineage_badges`.
    """
    stmt = (
        select(
            NotebookCellRun.content_hash,
            NotebookCellRun.agent_run_id,
            NotebookCellRun.started_at,
        )
        .where(
            NotebookCellRun.file_path == file_path,
            NotebookCellRun.agent_run_id.is_not(None),
        )
        .order_by(NotebookCellRun.started_at.desc())
    )
    rows = session.execute(stmt).all()
    if not rows:
        return {}

    runs_by_content: dict[str, list[str]] = {}
    for content_hash, agent_run_id, _ in rows:
        if not agent_run_id:
            continue
        runs_by_content.setdefault(content_hash, []).append(agent_run_id)

    if not runs_by_content:
        return {}

    all_run_ids = [rid for ids in runs_by_content.values() for rid in ids]
    op_stmt = (
        select(AgentRunOperation)
        .where(
            AgentRunOperation.agent_run_id.in_(all_run_ids),
            AgentRunOperation.op_name.in_(WRITE_OP_NAMES),
        )
        .order_by(AgentRunOperation.started_at.desc())
    )
    ops_by_run: dict[str, list[AgentRunOperation]] = {}
    for op in session.execute(op_stmt).scalars().all():
        ops_by_run.setdefault(op.agent_run_id, []).append(op)

    out: dict[str, list[dict[str, Any]]] = {}
    for content_hash, run_ids in runs_by_content.items():
        seen: set[tuple[str, str | None]] = set()
        badges: list[dict[str, Any]] = []
        for rid in run_ids:
            for op in ops_by_run.get(rid, ()):
                key = (op.op_name, op.target_table)
                if key in seen:
                    continue
                seen.add(key)
                badges.append(
                    {
                        "op_name": op.op_name,
                        "target_table": op.target_table,
                        "rows_affected": op.rows_affected,
                        "delta_version_after": op.delta_version_after,
                        "started_at": op.started_at.isoformat(),
                    }
                )
        if badges:
            out[content_hash] = badges
    return out


__all__ = [
    "WRITE_OP_NAMES",
    "list_cell_lineage_badges",
    "list_cell_lineage_badges_bulk",
]
