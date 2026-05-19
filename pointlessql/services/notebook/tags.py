"""Notebook-level tag CRUD (Phase 98.B).

Notebook tags categorise a whole notebook in the workspace tree
(``etl`` / ``draft`` / ``prod`` / etc.).  This module is the thin
service layer the REST routes call; the model lives in
:class:`pointlessql.models.notebook.NotebookTag`.

Tags are normalised (lowercased, stripped, length-bounded) before
insertion so the workspace tree can filter on a stable shape.  The
unique constraint on ``(notebook_id, tag)`` makes ``add_tag``
idempotent — a re-add silently returns the existing row.
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import Notebook, NotebookTag

_TAG_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,62}[a-z0-9]?$")
_MAX_TAGS_PER_NOTEBOOK = 16

#: Curated tag vocabulary surfaced in the notebook header tag picker.
#: Free-text tags are still allowed (validated by :func:`_normalize`);
#: the curated list is just the default dropdown.
CURATED_NOTEBOOK_TAGS: tuple[str, ...] = (
    "etl",
    "draft",
    "prod",
    "wip",
    "verified",
    "broken",
    "ml",
    "report",
    "scratch",
)


def _normalize(raw: str) -> str:
    """Lowercase, strip, and validate one tag string.

    Args:
        raw: Tag string from the request body.

    Returns:
        The normalised tag (lowercased, stripped).

    Raises:
        ValidationError: When the result is empty, too long, or
            contains characters outside ``[a-z0-9_-]``.
    """
    tag = raw.strip().lower()
    if not tag:
        raise ValidationError("tag must not be empty")
    if not _TAG_PATTERN.fullmatch(tag):
        raise ValidationError(
            "tag must match [a-z0-9][a-z0-9_-]*[a-z0-9]? and be 1-64 chars"
        )
    return tag


def list_tags(session: Session, notebook_id: str) -> list[dict[str, Any]]:
    """Return every tag attached to one notebook.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` (UUID) the tags belong to.

    Returns:
        List of ``{"tag": str, "created_at": str}`` dicts in
        insertion order.
    """
    rows = session.execute(
        select(NotebookTag)
        .where(NotebookTag.notebook_id == notebook_id)
        .order_by(NotebookTag.created_at.asc(), NotebookTag.id.asc())
    ).scalars().all()
    return [
        {"tag": row.tag, "created_at": row.created_at.isoformat()}
        for row in rows
    ]


def add_tag(session: Session, *, notebook_id: str, raw_tag: str) -> str:
    """Attach a tag to a notebook; idempotent.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` (UUID).
        raw_tag: Tag string; normalised before insert.

    Returns:
        The normalised tag string actually written.

    Raises:
        ValidationError: When the tag fails validation, the notebook
            does not exist, or the per-notebook tag cap is exceeded.
    """
    tag = _normalize(raw_tag)
    notebook = session.get(Notebook, notebook_id)
    if notebook is None:
        raise ValidationError(f"notebook {notebook_id!r} not found")
    existing = session.execute(
        select(NotebookTag).where(
            NotebookTag.notebook_id == notebook_id,
            NotebookTag.tag == tag,
        )
    ).scalar_one_or_none()
    if existing is not None:
        return tag
    count = session.execute(
        select(NotebookTag).where(NotebookTag.notebook_id == notebook_id)
    ).scalars().all()
    if len(count) >= _MAX_TAGS_PER_NOTEBOOK:
        raise ValidationError(
            f"notebook tag cap reached ({_MAX_TAGS_PER_NOTEBOOK})"
        )
    session.add(NotebookTag(notebook_id=notebook_id, tag=tag))
    session.flush()
    return tag


def remove_tag(session: Session, *, notebook_id: str, raw_tag: str) -> bool:
    """Detach a tag from a notebook.

    Args:
        session: A SQLAlchemy session.
        notebook_id: ``Notebook.id`` (UUID).
        raw_tag: Tag string; normalised before lookup.

    Returns:
        ``True`` when a row was deleted, ``False`` when the tag was
        not attached to the notebook in the first place.
    """
    tag = _normalize(raw_tag)
    existing = session.execute(
        select(NotebookTag).where(
            NotebookTag.notebook_id == notebook_id,
            NotebookTag.tag == tag,
        )
    ).scalar_one_or_none()
    if existing is None:
        return False
    session.execute(
        delete(NotebookTag).where(
            NotebookTag.notebook_id == notebook_id,
            NotebookTag.tag == tag,
        )
    )
    return True


def list_notebooks_for_tag(
    session: Session, *, workspace_id: int, tag: str
) -> list[str]:
    """Return notebook UUIDs in ``workspace_id`` tagged ``tag``.

    Args:
        session: A SQLAlchemy session.
        workspace_id: Scope the lookup to one tenant.
        tag: Tag to filter on; normalised before lookup.

    Returns:
        List of ``Notebook.id`` UUIDs in attach order.
    """
    normalised = _normalize(tag)
    stmt = (
        select(NotebookTag.notebook_id)
        .join(Notebook, Notebook.id == NotebookTag.notebook_id)
        .where(
            Notebook.workspace_id == workspace_id,
            NotebookTag.tag == normalised,
        )
        .order_by(NotebookTag.created_at.asc())
    )
    return [row for row in session.execute(stmt).scalars().all()]


__all__ = [
    "CURATED_NOTEBOOK_TAGS",
    "add_tag",
    "list_notebooks_for_tag",
    "list_tags",
    "remove_tag",
]
