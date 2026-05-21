"""Notebook replay / scenario-mode (Phase 103).

Each replay row re-executes a Phase-97 :class:`NotebookRevision` and
parks the fresh outputs alongside the original.  The actual
kernel-driven re-execution loop is out of scope for this module —
the scaffolding here is the metadata + diff surface that drives the
side-by-side comparison page.

Design notes:

* Replays are immutable once finished — the row is the diff anchor.
  Rerun = a brand-new replay row.
* ``outputs_json`` lands when the worker reports completion.  The
  ``record_finished`` call also computes a small diff digest
  (``stable`` / ``changed`` / ``missing`` / ``new`` cell counts) so
  the list page can render without re-loading the heavy JSON.
* The full per-cell diff is computed lazily by
  :func:`compute_replay_diff` so cell sources / outputs stream into
  Monaco only when the user opens the comparison.
"""

from __future__ import annotations

import datetime
import json
import uuid as _uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import (
    Notebook,
    NotebookReplay,
    NotebookRevision,
)

REPLAY_STATUS_PENDING = "pending"
REPLAY_STATUS_RUNNING = "running"
REPLAY_STATUS_OK = "ok"
REPLAY_STATUS_ERROR = "error"
REPLAY_STATUS_CANCELLED = "cancelled"

VALID_TERMINAL_STATUSES: tuple[str, ...] = (
    REPLAY_STATUS_OK,
    REPLAY_STATUS_ERROR,
    REPLAY_STATUS_CANCELLED,
)


def start_replay(
    session: Session,
    *,
    notebook_id: str,
    base_revision_uuid: str,
    branch_name: str | None = None,
    triggered_by_user_id: int | None = None,
) -> NotebookReplay:
    """Insert a fresh replay row in ``pending`` status.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        base_revision_uuid: Phase-97 revision UUID the replay forks
            from.  Must already exist and belong to ``notebook_id``.
        branch_name: Optional Phase-102 branch the replay's writes
            target.
        triggered_by_user_id: Audit pointer.

    Returns:
        The newly inserted :class:`NotebookReplay` row.

    Raises:
        ValidationError: When the notebook or revision is unknown.
    """
    if session.get(Notebook, notebook_id) is None:
        raise ValidationError(f"notebook {notebook_id!r} not found")
    rev = session.execute(
        select(NotebookRevision).where(
            NotebookRevision.revision_uuid == base_revision_uuid,
            NotebookRevision.notebook_id == notebook_id,
        )
    ).scalar_one_or_none()
    if rev is None:
        raise ValidationError(
            f"revision {base_revision_uuid!r} not found under notebook"
        )
    row = NotebookReplay(
        replay_uuid=str(_uuid.uuid4()),
        notebook_id=notebook_id,
        base_revision_uuid=base_revision_uuid,
        branch_name=branch_name,
        status=REPLAY_STATUS_PENDING,
        outputs_json="[]",
        triggered_by_user_id=triggered_by_user_id,
    )
    session.add(row)
    session.flush()
    return row


def mark_running(
    session: Session, *, replay_uuid: str
) -> NotebookReplay:
    """Transition the replay row to ``running``.

    Args:
        session: A SQLAlchemy session.
        replay_uuid: 36-char replay UUID.

    Returns:
        The updated row.  The lookup helper raises
        :class:`ValidationError` (propagated) when the UUID is unknown.
    """
    row = _get_replay(session, replay_uuid=replay_uuid)
    row.status = REPLAY_STATUS_RUNNING
    session.flush()
    return row


def record_finished(
    session: Session,
    *,
    replay_uuid: str,
    status: str,
    outputs: list[dict[str, Any]] | None = None,
) -> NotebookReplay:
    """Mark a replay row as finished + persist outputs + diff summary.

    Args:
        session: A SQLAlchemy session.
        replay_uuid: 36-char replay UUID.
        status: One of :data:`VALID_TERMINAL_STATUSES`.
        outputs: Output rows from the re-execution.  ``None`` /
            empty for cancelled or error replays.

    Returns:
        The updated row.

    Raises:
        ValidationError: When the UUID is unknown or ``status`` is
            outside the terminal set.
    """
    if status not in VALID_TERMINAL_STATUSES:
        raise ValidationError(
            f"status must be one of {VALID_TERMINAL_STATUSES}; got {status!r}"
        )
    row = _get_replay(session, replay_uuid=replay_uuid)
    outputs = outputs or []
    row.status = status
    row.finished_at = datetime.datetime.now(datetime.UTC)
    row.outputs_json = json.dumps(outputs, sort_keys=True)
    row.diff_summary_json = json.dumps(
        _diff_summary(session, base_revision_uuid=row.base_revision_uuid, new_outputs=outputs),
        sort_keys=True,
    )
    session.flush()
    return row


def get_replay(
    session: Session, *, replay_uuid: str
) -> dict[str, Any] | None:
    """Return the replay envelope (or ``None`` if unknown)."""
    row = session.execute(
        select(NotebookReplay).where(NotebookReplay.replay_uuid == replay_uuid)
    ).scalar_one_or_none()
    if row is None:
        return None
    return _row_to_envelope(row, include_outputs=True)


def list_replays(
    session: Session, *, notebook_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Return replays for a notebook, newest first."""
    rows = session.execute(
        select(NotebookReplay)
        .where(NotebookReplay.notebook_id == notebook_id)
        .order_by(NotebookReplay.started_at.desc())
        .limit(limit)
    ).scalars().all()
    return [_row_to_envelope(r, include_outputs=False) for r in rows]


def compute_replay_diff(
    session: Session, *, replay_uuid: str
) -> dict[str, Any]:
    """Return the cell-by-cell side-by-side diff envelope.

    Args:
        session: A SQLAlchemy session.
        replay_uuid: 36-char UUID.

    Returns:
        Dict ``{base_revision_uuid, replay_uuid, cells: [
        {content_hash, source, original_outputs, replayed_outputs,
        verdict}, …]}`` where ``verdict`` is ``stable`` /
        ``changed`` / ``missing`` / ``new``.

    Raises:
        ValidationError: When the replay or its base revision is
            unknown.
    """
    row = _get_replay(session, replay_uuid=replay_uuid)
    base = session.execute(
        select(NotebookRevision).where(
            NotebookRevision.revision_uuid == row.base_revision_uuid
        )
    ).scalar_one_or_none()
    if base is None:
        raise ValidationError(
            f"base revision {row.base_revision_uuid!r} missing"
        )
    base_cells = json.loads(base.cells_json)
    base_outputs = json.loads(base.outputs_json)
    replay_outputs = json.loads(row.outputs_json)

    base_by_cell = _group_outputs_by_cell(base_outputs)
    replay_by_cell = _group_outputs_by_cell(replay_outputs)
    cells: list[dict[str, Any]] = []
    for cell in base_cells:
        h = cell.get("content_hash") or ""
        original = base_by_cell.get(h, [])
        replayed = replay_by_cell.get(h, [])
        if not replayed:
            verdict = "missing"
        elif not original:
            verdict = "new"
        elif original == replayed:
            verdict = "stable"
        else:
            verdict = "changed"
        cells.append(
            {
                "content_hash": h,
                "cell_type": cell.get("cell_type"),
                "source": cell.get("source"),
                "original_outputs": original,
                "replayed_outputs": replayed,
                "verdict": verdict,
            }
        )
    return {
        "replay_uuid": row.replay_uuid,
        "base_revision_uuid": row.base_revision_uuid,
        "status": row.status,
        "cells": cells,
    }


def _get_replay(
    session: Session, *, replay_uuid: str
) -> NotebookReplay:
    """Resolve a replay row or raise ValidationError."""
    row = session.execute(
        select(NotebookReplay).where(NotebookReplay.replay_uuid == replay_uuid)
    ).scalar_one_or_none()
    if row is None:
        raise ValidationError(f"replay {replay_uuid!r} not found")
    return row


def _group_outputs_by_cell(
    outputs: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group output rows by ``content_hash``."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in outputs:
        h = row.get("content_hash") or ""
        grouped.setdefault(h, []).append(row)
    for k in grouped:
        grouped[k].sort(key=lambda r: r.get("output_index") or 0)
    return grouped


def _diff_summary(
    session: Session,
    *,
    base_revision_uuid: str,
    new_outputs: list[dict[str, Any]],
) -> dict[str, int]:
    """Compute the {stable,changed,missing,new} digest."""
    base = session.execute(
        select(NotebookRevision).where(
            NotebookRevision.revision_uuid == base_revision_uuid
        )
    ).scalar_one_or_none()
    if base is None:
        return {"stable": 0, "changed": 0, "missing": 0, "new": 0}
    base_cells = json.loads(base.cells_json)
    base_outputs = json.loads(base.outputs_json)
    base_by_cell = _group_outputs_by_cell(base_outputs)
    new_by_cell = _group_outputs_by_cell(new_outputs)
    counts = {"stable": 0, "changed": 0, "missing": 0, "new": 0}
    for cell in base_cells:
        h = cell.get("content_hash") or ""
        original = base_by_cell.get(h, [])
        replayed = new_by_cell.get(h, [])
        if not replayed:
            counts["missing"] += 1
        elif not original:
            counts["new"] += 1
        elif original == replayed:
            counts["stable"] += 1
        else:
            counts["changed"] += 1
    return counts


def _row_to_envelope(
    row: NotebookReplay, *, include_outputs: bool
) -> dict[str, Any]:
    """Serialise one replay row for REST output."""
    envelope: dict[str, Any] = {
        "replay_uuid": row.replay_uuid,
        "notebook_id": row.notebook_id,
        "base_revision_uuid": row.base_revision_uuid,
        "branch_name": row.branch_name,
        "status": row.status,
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "diff_summary": (
            json.loads(row.diff_summary_json) if row.diff_summary_json else None
        ),
        "triggered_by_user_id": row.triggered_by_user_id,
    }
    if include_outputs:
        envelope["outputs"] = json.loads(row.outputs_json)
    return envelope


__all__ = [
    "REPLAY_STATUS_CANCELLED",
    "REPLAY_STATUS_ERROR",
    "REPLAY_STATUS_OK",
    "REPLAY_STATUS_PENDING",
    "REPLAY_STATUS_RUNNING",
    "VALID_TERMINAL_STATUSES",
    "compute_replay_diff",
    "get_replay",
    "list_replays",
    "mark_running",
    "record_finished",
    "start_replay",
]
