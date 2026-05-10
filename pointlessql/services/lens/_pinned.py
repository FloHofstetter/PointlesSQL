"""Lens pinned-answer service helpers (Sprint 65.6).

Persists assistant-message snapshots so an analyst can re-find the
answer later via a stable URL.  Visibility mirrors :class:`SavedQuery`:
owner + admins always see; ``is_shared=True`` extends to every
workspace member.
"""

from __future__ import annotations

import datetime
import re
from typing import TYPE_CHECKING

from sqlalchemy import delete, select

from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import LensMessage, LensPinnedAnswer

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slugify(text: str) -> str:
    """Reduce *text* to a URL-safe lowercase slug, ≤ 64 chars."""
    cleaned = _SLUG_RE.sub("-", (text or "pin").lower()).strip("-")
    return cleaned[:64] or "pin"


def _next_unique_slug(
    factory: sessionmaker[Session], *, workspace_id: int, base: str
) -> str:
    """Return a workspace-unique slug, suffixing ``-2`` / ``-3`` on collision."""
    candidate = base
    suffix = 1
    with factory() as session:
        while True:
            existing = session.scalar(
                select(LensPinnedAnswer.id).where(
                    LensPinnedAnswer.workspace_id == workspace_id,
                    LensPinnedAnswer.slug == candidate,
                )
            )
            if existing is None:
                return candidate
            suffix += 1
            candidate = f"{base}-{suffix}"


def create_pin(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    owner_id: int,
    title: str,
    source_message_id: int | None,
    is_shared: bool = False,
) -> LensPinnedAnswer:
    """Pin one assistant message + return the detached row.

    Captures a snapshot of the assistant text + the most recent SQL
    tool-call's executed_sql + result_preview so the pin survives
    source-session deletion.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace the pin belongs to.
        owner_id: User creating the pin.
        title: Short human label.
        source_message_id: Assistant :class:`LensMessage` id (or
            ``None`` if the caller is pinning a synthetic answer).
        is_shared: When ``True`` every workspace member sees the pin.

    Returns:
        The detached :class:`LensPinnedAnswer` row.

    Raises:
        ResourceNotFoundError: When *source_message_id* is set but
            does not point at an assistant message in the workspace.
    """  # noqa: DOC502 — ResourceNotFoundError raised by _capture_snapshot
    base_slug = _slugify(title)
    slug = _next_unique_slug(factory, workspace_id=workspace_id, base=base_slug)

    snapshot, sql_text, preview = _capture_snapshot(
        factory,
        source_message_id=source_message_id,
    )

    now = datetime.datetime.now(datetime.UTC)
    row = LensPinnedAnswer(
        workspace_id=workspace_id,
        owner_id=owner_id,
        slug=slug,
        title=title[:200],
        source_message_id=source_message_id,
        content_snapshot=snapshot,
        sql_text=sql_text,
        result_preview=preview,
        is_shared=is_shared,
        created_at=now,
        updated_at=now,
    )
    with factory() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    return row


def _capture_snapshot(
    factory: sessionmaker[Session],
    *,
    source_message_id: int | None,
) -> tuple[str, str | None, object | None]:
    """Return (assistant_text, sql_text, result_preview) for the pin."""
    if source_message_id is None:
        return ("", None, None)
    with factory() as session:
        assistant = session.get(LensMessage, source_message_id)
        if assistant is None or assistant.role != "assistant":
            raise ResourceNotFoundError(
                f"lens_message: {source_message_id} not found or not assistant"
            )
        snapshot = assistant.content or ""
        # Find the most recent tool-row in the same session that ran
        # a query (carries executed_sql in tool_result).
        last_query = session.scalar(
            select(LensMessage)
            .where(
                LensMessage.session_id == assistant.session_id,
                LensMessage.role == "tool",
                LensMessage.tool_name == "query",
                LensMessage.created_at <= assistant.created_at,
            )
            .order_by(LensMessage.created_at.desc(), LensMessage.id.desc())
            .limit(1)
        )
        sql_text: str | None = None
        preview: object | None = None
        if last_query is not None:
            result = last_query.tool_result or {}
            if isinstance(result, dict):
                sql_text = result.get("executed_sql") or None
                preview = {
                    "columns": result.get("columns"),
                    "rows": (result.get("rows") or [])[:20],
                    "row_count": result.get("row_count"),
                }
        return (snapshot, sql_text, preview)


def get_pin_by_slug(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    slug: str,
    requester_id: int | None,
    requester_is_admin: bool,
) -> LensPinnedAnswer:
    """Return one pin by slug, applying visibility rules.

    Args:
        factory: SQLAlchemy session factory.
        workspace_id: Workspace filter.
        slug: Pin slug.
        requester_id: User id of the caller (``None`` for API-key
            requests; the visibility check then requires
            ``is_shared=True`` unless *requester_is_admin*).
        requester_is_admin: Admin pass-through.

    Returns:
        The detached :class:`LensPinnedAnswer` row.

    Raises:
        ResourceNotFoundError: When no row matches OR when visibility
            rules deny the read.
    """
    with factory() as session:
        row = session.scalar(
            select(LensPinnedAnswer).where(
                LensPinnedAnswer.workspace_id == workspace_id,
                LensPinnedAnswer.slug == slug,
            )
        )
        if row is None:
            raise ResourceNotFoundError(f"lens_pinned: {slug}")
        if not requester_is_admin and row.owner_id != (requester_id or -1):
            if not row.is_shared:
                raise ResourceNotFoundError(f"lens_pinned: {slug}")
        session.expunge(row)
        return row


def list_pins(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    requester_id: int | None,
    requester_is_admin: bool,
    limit: int = 50,
) -> list[LensPinnedAnswer]:
    """List visible pins, newest first."""
    with factory() as session:
        stmt = (
            select(LensPinnedAnswer)
            .where(LensPinnedAnswer.workspace_id == workspace_id)
            .order_by(LensPinnedAnswer.created_at.desc())
            .limit(limit)
        )
        if not requester_is_admin:
            from sqlalchemy import or_

            stmt = stmt.where(
                or_(
                    LensPinnedAnswer.owner_id == (requester_id or -1),
                    LensPinnedAnswer.is_shared.is_(True),
                )
            )
        rows = list(session.scalars(stmt).all())
        for row in rows:
            session.expunge(row)
        return rows


def delete_pin(
    factory: sessionmaker[Session],
    *,
    workspace_id: int,
    slug: str,
    requester_id: int | None,
    requester_is_admin: bool,
) -> bool:
    """Delete one pin; only the owner or an admin succeeds."""
    with factory() as session:
        stmt = delete(LensPinnedAnswer).where(
            LensPinnedAnswer.workspace_id == workspace_id,
            LensPinnedAnswer.slug == slug,
        )
        if not requester_is_admin:
            stmt = stmt.where(LensPinnedAnswer.owner_id == (requester_id or -1))
        result = session.execute(stmt)
        session.commit()
        return int(getattr(result, "rowcount", 0) or 0) > 0
