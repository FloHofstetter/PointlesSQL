"""Pinned-fact promotion of notebook revisions.

A *fact* is a long-lived bookmark on a :class:`NotebookRevision` that
adds a human-readable shape (``title`` + ``description_md``) on top of
the deterministic content hash already on the revision row.  The
service has three responsibilities:

* Pin / unpin / list / get :class:`NotebookRevisionFact` rows.
* Mint or reuse the polymorphic :class:`SocialTarget` anchor for
  ``kind='notebook_revision'`` (whole-revision facts) or
  ``kind='notebook_cell_output'`` (per-cell-output facts), so the
  fact participates in the social surface (followers,
  comments) and the feed fanout.
* Fan a ``"notebook_revision_pinned"`` event out to the notebook's
  followers via :func:`pointlessql.services.notifications.fanout.fanout_event`
  so the activity feed surfaces the pin.

Audit recording of agent-driven pins is a thin wrapper that the
``pql.facts`` PQL facade adds on top of :func:`pin_revision_fact`;
the service itself stays storage-focused so the unit tests can
exercise it without spinning up a full PQL.
"""

from __future__ import annotations

import datetime
import logging
import uuid as _uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from pointlessql.exceptions import ValidationError
from pointlessql.models.notebook import (
    Notebook,
    NotebookRevision,
    NotebookRevisionFact,
)
from pointlessql.services.social._target_resolver import get_or_create_target

logger = logging.getLogger(__name__)


def _entity_kind_for(cell_content_hash: str | None) -> str:
    """Pick the right social-target kind for the fact shape."""
    return "notebook_cell_output" if cell_content_hash else "notebook_revision"


def pin_revision_fact(
    session: Session,
    *,
    workspace_id: int,
    revision_uuid: str,
    title: str,
    description_md: str | None = None,
    cell_content_hash: str | None = None,
    result_snapshot_json: str | None = None,
    pinned_by_user_id: int | None = None,
    pinned_by_agent_id: str | None = None,
) -> NotebookRevisionFact:
    """Promote a revision (or one of its cell outputs) into a fact.

    Idempotent on ``(workspace_id, revision_id, cell_content_hash)``
    while the fact is active (the partial UNIQUE filtered on
    ``unpinned_at IS NULL``).  A re-pin after an unpin mints a fresh
    row so the soft-delete tombstone is preserved for audit.

    Args:
        session: A SQLAlchemy session.  The caller owns the
            transaction; this function flushes but does not commit.
        workspace_id: Tenant scope.  Hard isolation: a fact pinned in
            workspace A is invisible to workspace B even when the
            underlying revision is shared via federation.
        revision_uuid: 36-char :class:`NotebookRevision` UUID.
        title: Human-readable label (≤ 200 chars).
        description_md: Optional Markdown rendered on the library
            detail page.
        cell_content_hash: When set, pins one specific cell's output
            inside the revision.  ``None`` pins the whole revision.
        result_snapshot_json: Optional frozen JSON snapshot of the
            cell's last-known output frame for cell-output facts.
        pinned_by_user_id: Required iff *pinned_by_agent_id* is unset.
        pinned_by_agent_id: Required iff *pinned_by_user_id* is unset.

    Returns:
        The persisted (or pre-existing active) :class:`NotebookRevisionFact`.

    Raises:
        ValidationError: On bad input shape, unknown revision, missing
            attribution, or title length violation.
    """
    if not title:
        raise ValidationError("title must be a non-empty string")
    if len(title) > 200:
        raise ValidationError("title must be at most 200 characters")
    if pinned_by_user_id is None and not pinned_by_agent_id:
        raise ValidationError("pin requires either pinned_by_user_id or pinned_by_agent_id")
    revision = session.execute(
        select(NotebookRevision).where(NotebookRevision.revision_uuid == revision_uuid)
    ).scalar_one_or_none()
    if revision is None:
        raise ValidationError(f"revision {revision_uuid!r} not found")
    notebook = session.get(Notebook, revision.notebook_id)
    if notebook is None or int(notebook.workspace_id) != int(workspace_id):
        raise ValidationError(f"revision {revision_uuid!r} is not in workspace {workspace_id}")
    # Idempotent active-row lookup.  We re-query rather than relying on
    # the partial UNIQUE to raise so the caller gets a clean return
    # value instead of an IntegrityError to translate.
    existing = session.execute(
        select(NotebookRevisionFact).where(
            NotebookRevisionFact.workspace_id == workspace_id,
            NotebookRevisionFact.revision_id == revision.id,
            NotebookRevisionFact.cell_content_hash == cell_content_hash,
            NotebookRevisionFact.unpinned_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return existing

    kind = _entity_kind_for(cell_content_hash)
    if cell_content_hash:
        entity_ref = f"{revision_uuid}:{cell_content_hash}"
    else:
        entity_ref = revision_uuid
    # The social target uses the revision UUID (+ optional content hash)
    # as the ref so a follower-of-revision subscription survives later
    # title edits on the fact itself.  We mint a UUID for the fact row
    # only after we know the anchor is in place.
    target = get_or_create_target(
        session,
        workspace_id=workspace_id,
        kind=kind,
        ref=entity_ref,
    )
    row = NotebookRevisionFact(
        fact_uuid=str(_uuid.uuid4()),
        workspace_id=workspace_id,
        social_target_id=target.id,
        revision_id=revision.id,
        cell_content_hash=cell_content_hash,
        title=title,
        description_md=description_md,
        result_snapshot_json=result_snapshot_json,
        pinned_by_user_id=pinned_by_user_id,
        pinned_by_agent_id=pinned_by_agent_id,
    )
    session.add(row)
    session.flush()
    return row


def unpin_fact(session: Session, *, fact_uuid: str) -> NotebookRevisionFact:
    """Soft-delete a fact by stamping ``unpinned_at``.

    Args:
        session: A SQLAlchemy session.
        fact_uuid: 36-char fact UUID.

    Returns:
        The updated :class:`NotebookRevisionFact` row.

    Raises:
        ValidationError: When the UUID is unknown or the row is
            already unpinned.
    """
    row = session.execute(
        select(NotebookRevisionFact).where(NotebookRevisionFact.fact_uuid == fact_uuid)
    ).scalar_one_or_none()
    if row is None:
        raise ValidationError(f"fact {fact_uuid!r} not found")
    if row.unpinned_at is not None:
        raise ValidationError(f"fact {fact_uuid!r} is already unpinned")
    row.unpinned_at = datetime.datetime.now(datetime.UTC)
    session.flush()
    return row


def get_fact(session: Session, *, fact_uuid: str) -> NotebookRevisionFact | None:
    """Return one fact by UUID regardless of pinned/unpinned state."""
    return session.execute(
        select(NotebookRevisionFact).where(NotebookRevisionFact.fact_uuid == fact_uuid)
    ).scalar_one_or_none()


def list_facts(
    session: Session,
    *,
    workspace_id: int,
    notebook_id: str | None = None,
    include_unpinned: bool = False,
    limit: int = 50,
    offset: int = 0,
) -> list[NotebookRevisionFact]:
    """List facts for a workspace, newest-pinned first.

    Args:
        session: A SQLAlchemy session.
        workspace_id: Tenant scope.
        notebook_id: When set, restrict to facts whose revision belongs
            to the given notebook UUID.
        include_unpinned: When ``True``, include soft-deleted rows in
            the result (audit-grade browse).  Default ``False``.
        limit: Newest-N cap (1–500).
        offset: Zero-indexed row offset for paginated reads.
            Defaults to 0 (no skip).  Not capped — only ``limit`` is.

    Returns:
        List of :class:`NotebookRevisionFact` rows in
        ``pinned_at desc`` order.
    """
    stmt = (
        select(NotebookRevisionFact)
        .where(NotebookRevisionFact.workspace_id == workspace_id)
        .order_by(desc(NotebookRevisionFact.pinned_at))
        .offset(max(0, int(offset)))
        .limit(max(1, min(500, int(limit))))
    )
    if not include_unpinned:
        stmt = stmt.where(NotebookRevisionFact.unpinned_at.is_(None))
    if notebook_id is not None:
        stmt = stmt.join(
            NotebookRevision,
            NotebookRevision.id == NotebookRevisionFact.revision_id,
        ).where(NotebookRevision.notebook_id == notebook_id)
    return list(session.execute(stmt).scalars().all())


def list_facts_for_cells(
    session: Session,
    *,
    workspace_id: int,
    notebook_id: str,
    cell_content_hashes: list[str],
) -> dict[str, list[NotebookRevisionFact]]:
    """Bulk lookup of active cell-output facts keyed by content hash.

    Used by the editor's cell-header pin chip to render one badge per
    cell in a single query.  Inactive (unpinned) rows are excluded.

    Args:
        session: A SQLAlchemy session.
        workspace_id: Tenant scope.
        notebook_id: 36-char notebook UUID.
        cell_content_hashes: One or more cell ``content_hash`` strings.

    Returns:
        ``{content_hash: [fact_row, ...]}`` — empty dict when none
        are pinned.
    """
    if not cell_content_hashes:
        return {}
    rows = (
        session.execute(
            select(NotebookRevisionFact)
            .join(
                NotebookRevision,
                NotebookRevision.id == NotebookRevisionFact.revision_id,
            )
            .where(
                NotebookRevisionFact.workspace_id == workspace_id,
                NotebookRevisionFact.cell_content_hash.in_(cell_content_hashes),
                NotebookRevision.notebook_id == notebook_id,
                NotebookRevisionFact.unpinned_at.is_(None),
            )
        )
        .scalars()
        .all()
    )
    grouped: dict[str, list[NotebookRevisionFact]] = {}
    for row in rows:
        key = row.cell_content_hash or ""
        grouped.setdefault(key, []).append(row)
    return grouped


def row_to_envelope(row: NotebookRevisionFact) -> dict[str, Any]:
    """Serialise one fact row for REST output.

    The envelope intentionally omits the result snapshot so the list
    endpoint stays light; the detail endpoint expands it via a separate
    call into :func:`get_fact_detail`.
    """
    return {
        "fact_uuid": row.fact_uuid,
        "workspace_id": row.workspace_id,
        "social_target_id": row.social_target_id,
        "revision_id": row.revision_id,
        "cell_content_hash": row.cell_content_hash,
        "title": row.title,
        "description_md": row.description_md,
        "pinned_by_user_id": row.pinned_by_user_id,
        "pinned_by_agent_id": row.pinned_by_agent_id,
        "pinned_at": row.pinned_at.isoformat() if row.pinned_at else None,
        "unpinned_at": (row.unpinned_at.isoformat() if row.unpinned_at else None),
        "active": row.unpinned_at is None,
    }


def get_fact_detail(session: Session, *, fact_uuid: str) -> dict[str, Any] | None:
    """Return one fact's row + the linked revision UUID + snapshot.

    The revision UUID is resolved via a single extra get so the
    front-end can hyperlink without the route layer having to chase
    the FK manually.
    """
    row = get_fact(session, fact_uuid=fact_uuid)
    if row is None:
        return None
    envelope = row_to_envelope(row)
    revision = session.get(NotebookRevision, row.revision_id)
    envelope["revision_uuid"] = revision.revision_uuid if revision is not None else None
    envelope["notebook_id"] = revision.notebook_id if revision is not None else None
    envelope["result_snapshot_json"] = row.result_snapshot_json
    return envelope


__all__ = [
    "get_fact",
    "get_fact_detail",
    "list_facts",
    "list_facts_for_cells",
    "pin_revision_fact",
    "row_to_envelope",
    "unpin_fact",
]
