"""Per-cell authorship attribution.

This module is the upsert-on-save service that maintains the
``notebook_cell_authorship`` row 1:1 with
:class:`NotebookCellIdentity`.  Callers come from two places:

* The save-path reconciler (after the cell-UUID is minted /
  re-confirmed) — passes the saver's email + their last agent_run
  context if any.
* The Phase-96 AI-assistant acceptance path — passes the agent's
  ``agent_run_id`` so the cell shows up attributed to the chat-driven
  authoring run.

The semantics are:

* First save of a cell mints the row with both ``first_*`` and
  ``last_modifier_*`` set to the same caller.
* Subsequent saves leave ``first_*`` alone and only bump
  ``last_modifier_*`` + ``last_modified_at``.

The reviewer-per-cell flow piggybacks on the existing polymorphic
comment system (``DataProductComment`` posted against the
``notebook_cell`` social anchor with ``author_agent_id`` set).  This
module exposes :func:`mark_reviewer_visit` as a hook the reviewer
agent's tool can call to bump the cell's ``last_reviewed_*`` columns
once the schema grows them in a follow-up sprint.  Backend-only
ship today; the cell-header chip and the reviewer-inline UI land
in a follow-up to avoid the nested-x-data trap.
"""

from __future__ import annotations

import datetime
from typing import Any, Literal

from sqlalchemy import select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import NotebookCellAuthorship, NotebookCellIdentity

AuthorKind = Literal["user", "agent"]


def upsert_cell_authorship(
    session: Session,
    *,
    cell_uuid: str,
    kind: AuthorKind,
    email: str | None = None,
    agent_id: int | None = None,
    agent_run_id: str | None = None,
    when: datetime.datetime | None = None,
) -> NotebookCellAuthorship:
    """Idempotent upsert of one ``notebook_cell_authorship`` row.

    Args:
        session: A SQLAlchemy session.
        cell_uuid: ``NotebookCellIdentity.id`` (stable per cell).
        kind: ``"user"`` or ``"agent"`` — the caller's author kind.
        email: User email; required when ``kind == "user"``.
        agent_id: ``agents.id`` FK; required when ``kind == "agent"``.
        agent_run_id: Run context (``agent_runs.id``) the cell was
            minted under.  Only set for the first save of an
            agent-authored cell; updates leave it alone.
        when: Wall-clock the save event landed.  Defaults to
            ``datetime.now(UTC)``.

    Returns:
        The (new or updated) row.

    Raises:
        ValidationError: When ``kind`` does not match the populated
            identity argument (e.g. ``kind == "user"`` with no email).
    """
    if kind == "user":
        if not email:
            raise ValidationError(
                "upsert_cell_authorship: kind='user' requires email"
            )
    elif kind == "agent":
        # inline editor
        # chat has no registered ``Agent`` DB row, so ``agent_id`` is
        # often unavailable.  The ``agent_run_id`` alone is enough
        # provenance — the cell-header chip falls back to a generic
        # "AI assistant" label when ``agent_id`` is null.
        if agent_id is None and not agent_run_id:
            raise ValidationError(
                "upsert_cell_authorship: kind='agent' requires "
                "agent_id or agent_run_id"
            )
    else:
        raise ValidationError(f"unknown author kind: {kind!r}")

    identity = session.get(NotebookCellIdentity, cell_uuid)
    if identity is None:
        raise ValidationError(f"cell {cell_uuid!r} not found")

    now = when or datetime.datetime.now(datetime.UTC)
    row = session.execute(
        select(NotebookCellAuthorship).where(
            NotebookCellAuthorship.cell_uuid == cell_uuid
        )
    ).scalar_one_or_none()
    if row is None:
        row = NotebookCellAuthorship(
            cell_uuid=cell_uuid,
            first_author_kind=kind,
            first_author_email=email,
            first_author_agent_id=agent_id,
            first_author_agent_run_id=agent_run_id,
            last_modifier_kind=kind,
            last_modifier_email=email,
            last_modifier_agent_id=agent_id,
            created_at=now,
            last_modified_at=now,
        )
        session.add(row)
    else:
        row.last_modifier_kind = kind
        row.last_modifier_email = email
        row.last_modifier_agent_id = agent_id
        row.last_modified_at = now
    session.flush()
    return row


def get_attribution(
    session: Session, *, cell_uuid: str
) -> dict[str, Any] | None:
    """Return the attribution envelope for one cell.

    Args:
        session: A SQLAlchemy session.
        cell_uuid: ``NotebookCellIdentity.id``.

    Returns:
        Dict ``{cell_uuid, first_author: {…}, last_modifier: {…},
        created_at, last_modified_at}`` or ``None`` when no row
        exists.
    """
    row = session.execute(
        select(NotebookCellAuthorship).where(
            NotebookCellAuthorship.cell_uuid == cell_uuid
        )
    ).scalar_one_or_none()
    if row is None:
        return None
    return {
        "cell_uuid": row.cell_uuid,
        "first_author": {
            "kind": row.first_author_kind,
            "email": row.first_author_email,
            "agent_id": row.first_author_agent_id,
            "agent_run_id": row.first_author_agent_run_id,
        },
        "last_modifier": {
            "kind": row.last_modifier_kind,
            "email": row.last_modifier_email,
            "agent_id": row.last_modifier_agent_id,
        },
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "last_modified_at": (
            row.last_modified_at.isoformat() if row.last_modified_at else None
        ),
    }


def list_for_notebook(
    session: Session, *, notebook_id: str
) -> dict[str, dict[str, Any]]:
    """Return ``{cell_uuid: envelope}`` for every cell in one notebook.

    Lets the editor render the per-cell author chip without firing
    one HTTP round-trip per cell — a 50-cell notebook would otherwise
    burn 50 requests on every page load.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``notebooks.id``.

    Returns:
        Mapping ``{cell_uuid -> envelope}``.  Cells that exist in the
        notebook but have no authorship row yet (rare — only happens
        between cell mint and first save commit) are simply absent.
    """
    rows = session.execute(
        select(NotebookCellAuthorship)
        .join(
            NotebookCellIdentity,
            NotebookCellIdentity.id == NotebookCellAuthorship.cell_uuid,
        )
        .where(NotebookCellIdentity.notebook_id == notebook_id)
    ).scalars().all()
    out: dict[str, dict[str, Any]] = {}
    for row in rows:
        out[row.cell_uuid] = {
            "cell_uuid": row.cell_uuid,
            "first_author": {
                "kind": row.first_author_kind,
                "email": row.first_author_email,
                "agent_id": row.first_author_agent_id,
                "agent_run_id": row.first_author_agent_run_id,
            },
            "last_modifier": {
                "kind": row.last_modifier_kind,
                "email": row.last_modifier_email,
                "agent_id": row.last_modifier_agent_id,
            },
            "created_at": (
                row.created_at.isoformat() if row.created_at else None
            ),
            "last_modified_at": (
                row.last_modified_at.isoformat()
                if row.last_modified_at
                else None
            ),
        }
    return out


def list_authored_by_agent(
    session: Session,
    *,
    agent_id: int,
    limit: int = 100,
    offset: int = 0,
) -> list[dict[str, Any]]:
    """Return cells minted by one agent.

    Args:
        session: A SQLAlchemy session.
        agent_id: ``agents.id``.
        limit: Newest-N cap (default 100).
        offset: Zero-indexed row offset for paginated reads.
            Defaults to 0 (no skip).

    Returns:
        List of ``{cell_uuid, created_at}`` dicts in newest-first
        order — the agent-profile page surfaces this as "cells
        authored by this agent".
    """
    rows = session.execute(
        select(NotebookCellAuthorship)
        .where(NotebookCellAuthorship.first_author_agent_id == agent_id)
        .order_by(NotebookCellAuthorship.created_at.desc())
        .offset(max(0, int(offset)))
        .limit(limit)
    ).scalars().all()
    return [
        {
            "cell_uuid": r.cell_uuid,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "agent_run_id": r.first_author_agent_run_id,
        }
        for r in rows
    ]


__all__ = [
    "AuthorKind",
    "get_attribution",
    "list_authored_by_agent",
    "list_for_notebook",
    "upsert_cell_authorship",
]
