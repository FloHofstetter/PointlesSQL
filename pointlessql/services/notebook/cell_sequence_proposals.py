"""Multi-cell AI-assistant proposals.

Extends single-cell propose / fix / explain flow to a
full cell-sequence proposal.  One row carries the entire suggested
sequence (``imports → DataFrame → plot → markdown``) so insertion
is atomic — the user picks "Insert all" or "Discard" without ever
landing in a half-applied state.

The LLM that generates the sequence lives in the hermes plugin
(``pql_propose_cell_sequence`` tool); the backend just stores +
serves the draft.  Provenance per-cell still goes through the
:class:`NotebookCellProvenance` table — accepting a
sequence fans out one provenance row per inserted cell once the
save-path reconciler mints UUIDs.
"""

from __future__ import annotations

import datetime
import json
import uuid as _uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models import EditorChatSession
from pointlessql.models.notebook import NotebookCellSequenceProposal

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_DISCARDED = "discarded"
STATUS_EXPIRED = "expired"
TERMINAL_STATUSES: frozenset[str] = frozenset({STATUS_ACCEPTED, STATUS_DISCARDED, STATUS_EXPIRED})


def propose_sequence(
    session: Session,
    *,
    chat_session_id: int,
    prompt: str,
    cells: list[dict[str, Any]],
    rationale: str | None = None,
) -> NotebookCellSequenceProposal:
    """Insert a new pending sequence proposal.

    Args:
        session: A SQLAlchemy session.
        chat_session_id: FK to :class:`EditorChatSession`.
        prompt: Verbatim user prompt.
        cells: Ordered list of cell dicts ``{position, cell_type,
            source, result_var?, tags?}``.  Must be non-empty;
            ``position`` is monotonic but not validated for
            duplicates beyond that.
        rationale: Optional model-side narrative.

    Returns:
        The persisted :class:`NotebookCellSequenceProposal` row.

    Raises:
        ValidationError: On bad input shape or unknown chat session.
    """
    if not cells:
        raise ValidationError("cells must be a non-empty list")
    if session.get(EditorChatSession, chat_session_id) is None:
        raise ValidationError(f"chat session {chat_session_id!r} not found")
    normalised: list[dict[str, Any]] = []
    for idx, cell in enumerate(cells):
        if not isinstance(cell, dict):
            raise ValidationError(f"cells[{idx}] must be an object")
        cell_type = cell.get("cell_type") or "code"
        if cell_type not in ("code", "markdown", "sql"):
            raise ValidationError(f"cells[{idx}].cell_type must be code|markdown|sql")
        source = cell.get("source")
        if not isinstance(source, str):
            raise ValidationError(f"cells[{idx}].source must be a string")
        normalised.append(
            {
                "position": int(cell.get("position", idx)),
                "cell_type": cell_type,
                "source": source,
                "result_var": cell.get("result_var"),
                "tags": list(cell.get("tags") or []),
            }
        )
    normalised.sort(key=lambda c: c["position"])
    row = NotebookCellSequenceProposal(
        proposal_id=str(_uuid.uuid4()),
        chat_session_id=chat_session_id,
        prompt=prompt,
        cells_json=json.dumps(normalised, sort_keys=True),
        rationale=rationale,
        status=STATUS_PENDING,
    )
    session.add(row)
    session.flush()
    return row


def get_sequence(session: Session, *, proposal_id: str) -> dict[str, Any] | None:
    """Return one sequence proposal envelope (or ``None``)."""
    row = session.execute(
        select(NotebookCellSequenceProposal).where(
            NotebookCellSequenceProposal.proposal_id == proposal_id
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return _row_to_envelope(row)


def accept_sequence(
    session: Session,
    *,
    proposal_id: str,
    accepted_by_user_id: int | None = None,
) -> NotebookCellSequenceProposal:
    """Flip the row to ``accepted``.

    Args:
        session: A SQLAlchemy session.
        proposal_id: 36-char proposal UUID.
        accepted_by_user_id: Audit pointer.

    Returns:
        The updated row.

    Raises:
        ValidationError: When unknown or already terminal.
    """
    row = _get_or_raise(session, proposal_id=proposal_id)
    if row.status in TERMINAL_STATUSES:
        raise ValidationError(f"sequence proposal {proposal_id!r} is already {row.status}")
    row.status = STATUS_ACCEPTED
    row.accepted_at = datetime.datetime.now(datetime.UTC)
    row.accepted_by_user_id = accepted_by_user_id
    session.flush()
    return row


def discard_sequence(session: Session, *, proposal_id: str) -> NotebookCellSequenceProposal:
    """Flip the row to ``discarded``.

    Args:
        session: A SQLAlchemy session.
        proposal_id: 36-char proposal UUID.

    Returns:
        The updated row.

    Raises:
        ValidationError: When unknown or already terminal.
    """
    row = _get_or_raise(session, proposal_id=proposal_id)
    if row.status in TERMINAL_STATUSES:
        raise ValidationError(f"sequence proposal {proposal_id!r} is already {row.status}")
    row.status = STATUS_DISCARDED
    row.discarded_at = datetime.datetime.now(datetime.UTC)
    session.flush()
    return row


def list_pending_for_session(
    session: Session, *, chat_session_id: int, limit: int = 20
) -> list[dict[str, Any]]:
    """Return pending sequence proposals for one chat session."""
    rows = (
        session.execute(
            select(NotebookCellSequenceProposal)
            .where(
                NotebookCellSequenceProposal.chat_session_id == chat_session_id,
                NotebookCellSequenceProposal.status == STATUS_PENDING,
            )
            .order_by(NotebookCellSequenceProposal.created_at.desc())
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return [_row_to_envelope(r) for r in rows]


def _get_or_raise(session: Session, *, proposal_id: str) -> NotebookCellSequenceProposal:
    row = session.execute(
        select(NotebookCellSequenceProposal).where(
            NotebookCellSequenceProposal.proposal_id == proposal_id
        )
    ).scalar_one_or_none()
    if row is None:
        raise ValidationError(f"sequence proposal {proposal_id!r} not found")
    return row


def _row_to_envelope(
    row: NotebookCellSequenceProposal,
) -> dict[str, Any]:
    """Serialise a row for REST output."""
    return {
        "proposal_id": row.proposal_id,
        "chat_session_id": row.chat_session_id,
        "prompt": row.prompt,
        "rationale": row.rationale,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "accepted_at": row.accepted_at.isoformat() if row.accepted_at else None,
        "accepted_by_user_id": row.accepted_by_user_id,
        "discarded_at": row.discarded_at.isoformat() if row.discarded_at else None,
        "cells": json.loads(row.cells_json),
    }


__all__ = [
    "STATUS_ACCEPTED",
    "STATUS_DISCARDED",
    "STATUS_EXPIRED",
    "STATUS_PENDING",
    "TERMINAL_STATUSES",
    "accept_sequence",
    "discard_sequence",
    "get_sequence",
    "list_pending_for_session",
    "propose_sequence",
]
