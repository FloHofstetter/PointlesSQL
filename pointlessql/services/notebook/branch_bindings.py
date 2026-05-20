"""Per-notebook Delta-branch binding (Phase 102).

A notebook can declare that its ``pql.write_table`` / ``pql.merge``
calls target a named Delta-branch instead of the canonical ``main``
state.  The kernel-side primitive reads the binding via the env
bridge (``POINTLESSQL_BRANCH``) so a single ``.py`` runs identically
against ``main`` and a branch — only the resolved storage layer
changes.

Promotion is a separate step gated by a human review.  Mark the
binding ``promoted_at`` once the reviewer approves; the actual
"merge branch into main" Delta-side operation happens in the
existing :mod:`pointlessql.services.agent_runs.memory._branch`
service.

This module is the binding-history + lifecycle helper.  One notebook
can carry many historical bindings (one per experiment); only one
without a ``superseded_at`` is the "current" binding for execution.
Promotion sets ``promoted_at``; discard sets ``discarded_at``; both
also set ``superseded_at`` so the next ``bind_branch`` call mints a
fresh current row.
"""

from __future__ import annotations

import datetime
import re
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import Notebook, NotebookBranchBinding

_BRANCH_NAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,126}$")


def _normalise_branch_name(raw: str) -> str:
    """Reject branch names outside ``[A-Za-z0-9][A-Za-z0-9._-]*``."""
    name = (raw or "").strip()
    if not _BRANCH_NAME_PATTERN.fullmatch(name):
        raise ValidationError(
            "branch_name must match [A-Za-z0-9][A-Za-z0-9._-]* and be 1-127 chars"
        )
    return name


def _current(
    session: Session, *, notebook_id: str
) -> NotebookBranchBinding | None:
    """Return the active (non-superseded) binding row or ``None``."""
    return session.execute(
        select(NotebookBranchBinding)
        .where(
            NotebookBranchBinding.notebook_id == notebook_id,
            NotebookBranchBinding.superseded_at.is_(None),
        )
        .order_by(NotebookBranchBinding.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def bind_branch(
    session: Session,
    *,
    notebook_id: str,
    branch_name: str,
    base_revision_uuid: str | None = None,
    created_by_user_id: int | None = None,
) -> NotebookBranchBinding:
    """Set the current branch binding for a notebook.

    Supersedes the prior active binding (if any) so only one is
    ever "current" at a time.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        branch_name: Delta-branch name.
        base_revision_uuid: Optional Phase-97 revision the branch
            forks from.
        created_by_user_id: Audit pointer.

    Returns:
        The new :class:`NotebookBranchBinding` row.

    Raises:
        ValidationError: On bad input or unknown notebook.
    """
    name = _normalise_branch_name(branch_name)
    if session.get(Notebook, notebook_id) is None:
        raise ValidationError(f"notebook {notebook_id!r} not found")
    now = datetime.datetime.now(datetime.UTC)
    prior = _current(session, notebook_id=notebook_id)
    if prior is not None:
        prior.superseded_at = now
    row = NotebookBranchBinding(
        notebook_id=notebook_id,
        branch_name=name,
        base_revision_uuid=base_revision_uuid,
        created_by_user_id=created_by_user_id,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row


def get_current_binding(
    session: Session, *, notebook_id: str
) -> dict[str, Any] | None:
    """Return the active binding envelope for a notebook.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.

    Returns:
        Dict ``{branch_name, base_revision_uuid, created_at, …}`` or
        ``None`` when the notebook runs against ``main``.
    """
    row = _current(session, notebook_id=notebook_id)
    return binding_to_envelope(row) if row is not None else None


def promote_binding(
    session: Session,
    *,
    notebook_id: str,
    promoted_by_user_id: int | None = None,
) -> NotebookBranchBinding:
    """Mark the current binding as promoted.

    The actual Delta-side merge into ``main`` happens in
    :mod:`pointlessql.services.agent_runs.memory._branch`; this
    method only records the lifecycle transition on the binding.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        promoted_by_user_id: Audit pointer to the reviewer.

    Returns:
        The updated row.

    Raises:
        ValidationError: When no current binding exists.
    """
    row = _current(session, notebook_id=notebook_id)
    if row is None:
        raise ValidationError(
            f"notebook {notebook_id!r} has no active branch binding to promote"
        )
    now = datetime.datetime.now(datetime.UTC)
    row.promoted_at = now
    row.promoted_by_user_id = promoted_by_user_id
    row.superseded_at = now
    session.flush()
    return row


def discard_binding(
    session: Session, *, notebook_id: str
) -> NotebookBranchBinding | None:
    """Roll back the current binding without promoting.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.

    Returns:
        The discarded row or ``None`` when none existed.
    """
    row = _current(session, notebook_id=notebook_id)
    if row is None:
        return None
    now = datetime.datetime.now(datetime.UTC)
    row.discarded_at = now
    row.superseded_at = now
    session.flush()
    return row


def list_bindings(
    session: Session, *, notebook_id: str, limit: int = 50
) -> list[dict[str, Any]]:
    """Return historical bindings for a notebook, newest first.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` UUID.
        limit: Newest-N cap.

    Returns:
        List of binding dicts ordered ``created_at desc``.
    """
    rows = session.execute(
        select(NotebookBranchBinding)
        .where(NotebookBranchBinding.notebook_id == notebook_id)
        .order_by(NotebookBranchBinding.created_at.desc())
        .limit(limit)
    ).scalars().all()
    return [binding_to_envelope(r) for r in rows]


def binding_to_envelope(row: NotebookBranchBinding) -> dict[str, Any]:
    """Serialise a row for REST output."""
    return {
        "id": row.id,
        "notebook_id": row.notebook_id,
        "branch_name": row.branch_name,
        "base_revision_uuid": row.base_revision_uuid,
        "created_by_user_id": row.created_by_user_id,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "promoted_at": row.promoted_at.isoformat() if row.promoted_at else None,
        "promoted_by_user_id": row.promoted_by_user_id,
        "discarded_at": row.discarded_at.isoformat()
        if row.discarded_at
        else None,
        "superseded_at": row.superseded_at.isoformat()
        if row.superseded_at
        else None,
        "is_current": row.superseded_at is None,
    }


__all__ = [
    "bind_branch",
    "discard_binding",
    "get_current_binding",
    "list_bindings",
    "promote_binding",
]
