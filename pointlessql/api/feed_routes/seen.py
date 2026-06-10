"""Feed seen-cursor endpoint.

The ambient feed stream is infinite, so rather than mark every row read
the reader carries a single high-water timestamp.  ``POST /api/feed/seen``
advances that cursor (default: now) so the stream can collapse to
"you're all caught up" without losing any history below the line.  The
cursor only ever moves forward — a stale client can never rewind it.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.models.notifications import FeedReadMarker

router = APIRouter(tags=["feed"])


class _SeenBody(BaseModel):
    """Request body for ``POST /api/feed/seen``.

    Attributes:
        at: Optional ISO-8601 timestamp the caller has seen up to.
            Omitted / unparseable falls back to now; a value in the
            future is clamped to now so the cursor can't outrun reality.
    """

    at: str | None = None


def _as_utc(dt: datetime.datetime) -> datetime.datetime:
    """Coerce a possibly-naive datetime to timezone-aware UTC.

    SQLite drops the offset on a ``DateTime(timezone=True)`` column, so a
    value read back from the cursor row is naive.  Normalising before any
    comparison or ``isoformat`` keeps the forward-only check from raising
    on naive-vs-aware and guarantees the response carries an offset.

    Args:
        dt: A datetime that may or may not carry tzinfo.

    Returns:
        The same instant as a UTC-aware datetime.
    """
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=datetime.UTC)


def _resolve_at(raw: str | None) -> datetime.datetime:
    """Resolve the requested cursor instant, clamped to ``[-inf, now]``.

    Args:
        raw: Optional ISO-8601 string from the request body.

    Returns:
        A timezone-aware UTC datetime: the parsed value when valid and
        not in the future, otherwise now.
    """
    now = datetime.datetime.now(datetime.UTC)
    if not raw:
        return now
    try:
        parsed = datetime.datetime.fromisoformat(raw)
    except ValueError, TypeError:
        return now
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=datetime.UTC)
    return min(parsed, now)


@router.post("/api/feed/seen")
async def mark_feed_seen(request: Request, body: _SeenBody | None = None) -> dict[str, Any]:
    """Advance the caller's feed seen-cursor (forward only).

    Upserts the caller's ``feed_read_markers`` row.  A new cursor is
    created at the requested instant; an existing cursor only moves
    forward, so an out-of-order request from a stale tab never rewinds
    "caught up" back to "unseen".

    Args:
        request: Incoming FastAPI request.
        body: Optional ``{at}`` payload; ``at`` defaults to now.

    Returns:
        ``{"ok": True, "seen_at": iso8601}`` with the resulting cursor.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    at = _resolve_at(body.at if body else None)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(FeedReadMarker).where(
                FeedReadMarker.user_id == caller["id"],
                FeedReadMarker.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if row is None:
            row = FeedReadMarker(
                user_id=caller["id"],
                workspace_id=workspace_id,
                seen_at=at,
            )
            session.add(row)
        elif at > _as_utc(row.seen_at):
            row.seen_at = at
        session.commit()
        resolved = _as_utc(row.seen_at)
    return {"ok": True, "seen_at": resolved.isoformat()}
