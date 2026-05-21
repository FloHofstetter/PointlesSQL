"""Mute / snooze / unmute endpoints for the feed.

Mutes are stored in ``feed_mutes`` keyed by
``(user_id, entity_kind, entity_ref)`` with an optional
``muted_until`` snooze deadline.  Author-mutes are stored as
``entity_kind='user', entity_ref=<user_id>`` so the feed handler's
single membership-set check covers both threads and authors.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request
from pydantic import BaseModel
from sqlalchemy import select

from pointlessql.api.dependencies import get_user, require_user
from pointlessql.exceptions import ValidationError
from pointlessql.models.social._feed_mute import FeedMute

router = APIRouter(tags=["feed"])

# Phase 81.K.4 — snooze durations expressed as relative seconds.
# Keys are the labels the UI surfaces; values are the wall-clock
# offset added to ``now()`` when the user picks one.
_SNOOZE_DURATIONS: dict[str, datetime.timedelta] = {
    "1h": datetime.timedelta(hours=1),
    "8h": datetime.timedelta(hours=8),
    "1d": datetime.timedelta(days=1),
}


class _MuteBody(BaseModel):
    """Request body for ``POST /api/feed/mute``."""

    entity_kind: str
    entity_ref: str


class _MuteAuthorBody(BaseModel):
    """Request body for ``POST /api/feed/mute-author``."""

    user_id: int


class _SnoozeBody(BaseModel):
    """Request body for ``POST /api/feed/snooze``."""

    entity_kind: str
    entity_ref: str
    duration: str


def _upsert_mute(
    session: Any,
    user_id: int,
    entity_kind: str,
    entity_ref: str,
    muted_until: datetime.datetime | None,
) -> None:
    """Insert or update a single mute row.

    The unique index ``uq_feed_mutes_per_target`` guarantees one row
    per ``(user_id, entity_kind, entity_ref)`` — re-muting updates
    the ``muted_until`` instead of duplicating.

    Args:
        session: SQLAlchemy session.
        user_id: Caller's user-id.
        entity_kind: Discriminator.
        entity_ref: Entity reference.
        muted_until: Optional snooze deadline.
    """
    existing = session.execute(
        select(FeedMute).where(
            FeedMute.user_id == user_id,
            FeedMute.entity_kind == entity_kind,
            FeedMute.entity_ref == entity_ref,
        )
    ).scalar_one_or_none()
    if existing is None:
        session.add(
            FeedMute(
                user_id=user_id,
                entity_kind=entity_kind,
                entity_ref=entity_ref,
                muted_until=muted_until,
            )
        )
    else:
        existing.muted_until = muted_until
    session.commit()


@router.post("/api/feed/mute")
async def mute_thread(request: Request, body: _MuteBody) -> dict[str, Any]:
    """Mute a thread (entity) for the caller's feed indefinitely.

    Args:
        request: Incoming FastAPI request.
        body: ``{entity_kind, entity_ref}`` JSON payload.

    Returns:
        ``{"ok": true}`` on success.
    """
    require_user(request)
    caller = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        _upsert_mute(
            session,
            caller["id"],
            body.entity_kind,
            body.entity_ref,
            muted_until=None,
        )
    return {"ok": True}


@router.post("/api/feed/mute-author")
async def mute_author(
    request: Request, body: _MuteAuthorBody
) -> dict[str, Any]:
    """Mute every feed item authored by *user_id* for the caller.

    Stored as a ``feed_mutes`` row with ``entity_kind='user'`` so the
    feed handler's single mute-set membership check covers both
    threads and authors.

    Args:
        request: Incoming FastAPI request.
        body: ``{user_id}`` JSON payload.

    Returns:
        ``{"ok": true}`` on success.
    """
    require_user(request)
    caller = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        _upsert_mute(
            session,
            caller["id"],
            "user",
            str(body.user_id),
            muted_until=None,
        )
    return {"ok": True}


@router.post("/api/feed/snooze")
async def snooze_thread(
    request: Request, body: _SnoozeBody
) -> dict[str, Any]:
    """Snooze a thread for one of the canonical durations.

    Args:
        request: Incoming FastAPI request.
        body: ``{entity_kind, entity_ref, duration}`` JSON payload.
            ``duration`` must be one of ``1h`` / ``8h`` / ``1d``.

    Returns:
        ``{"ok": true, "muted_until": iso8601}`` with the deadline.

    Raises:
        ValidationError: When ``duration`` is unknown.
    """
    require_user(request)
    caller = get_user(request)
    delta = _SNOOZE_DURATIONS.get(body.duration)
    if delta is None:
        raise ValidationError(
            f"unknown duration {body.duration!r}; "
            f"expected one of {sorted(_SNOOZE_DURATIONS)}",
        )
    muted_until = datetime.datetime.now(datetime.UTC) + delta
    factory = request.app.state.session_factory
    with factory() as session:
        _upsert_mute(
            session,
            caller["id"],
            body.entity_kind,
            body.entity_ref,
            muted_until=muted_until,
        )
    return {"ok": True, "muted_until": muted_until.isoformat()}


@router.post("/api/feed/unmute")
async def unmute(request: Request, body: _MuteBody) -> dict[str, Any]:
    """Remove a mute / snooze entry for the caller.

    Args:
        request: Incoming FastAPI request.
        body: ``{entity_kind, entity_ref}`` JSON payload.

    Returns:
        ``{"ok": true, "removed": bool}`` — ``removed`` is ``False``
        when no matching row existed (idempotent unmute).
    """
    require_user(request)
    caller = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        existing = session.execute(
            select(FeedMute).where(
                FeedMute.user_id == caller["id"],
                FeedMute.entity_kind == body.entity_kind,
                FeedMute.entity_ref == body.entity_ref,
            )
        ).scalar_one_or_none()
        if existing is None:
            return {"ok": True, "removed": False}
        session.delete(existing)
        session.commit()
    return {"ok": True, "removed": True}
