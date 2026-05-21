"""Notification read-state endpoints.

The feed's "Mark all read" button and the per-item toggle both
post here.  Visibility model: callers can only flip rows addressed
to themselves; 404 hides existence of foreign rows.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select, update

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models.notifications import UserNotification

router = APIRouter(tags=["feed"])


@router.post("/api/notifications/mark-all-read")
async def mark_all_read(request: Request) -> dict[str, Any]:
    """Mark every unread notification for the caller as read.

    Phase 81.K.4 — the feed's top-level "Mark all read" button posts
    here; the per-item endpoint covers the granular case.  Returns
    the count touched so the UI can confirm.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"ok": true, "count": N}`` where N is the number of rows
        flipped from unread to read.
    """
    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        result = session.execute(
            update(UserNotification)
            .where(
                UserNotification.recipient_user_id == caller["id"],
                UserNotification.workspace_id == workspace_id,
                UserNotification.read_at.is_(None),
            )
            .values(read_at=now)
        )
        session.commit()
        # rowcount is dialect-dependent; cast to int defensively.
        count = int(result.rowcount or 0)
    return {"ok": True, "count": count}


@router.post("/api/notifications/{notification_id}/read")
async def toggle_notification_read(
    request: Request, notification_id: int
) -> dict[str, Any]:
    """Toggle the ``read_at`` flag on a single notification.

    Phase 81.K.4 — the item-action menu's "Mark as read / unread"
    entry posts here.  We only allow the caller to flip rows
    addressed to themselves.

    Args:
        request: Incoming FastAPI request.
        notification_id: Primary key of the notification.

    Returns:
        ``{"ok": true, "read": bool}`` with the new state.

    Raises:
        ResourceNotFoundError: When the row doesn't belong to the
            caller.
    """
    require_user(request)
    caller = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(UserNotification).where(
                UserNotification.id == notification_id,
                UserNotification.recipient_user_id == caller["id"],
            )
        ).scalar_one_or_none()
        if row is None:
            raise ResourceNotFoundError("notification not found")
        now = datetime.datetime.now(datetime.UTC)
        if row.read_at is None:
            row.read_at = now
            new_state = True
        else:
            row.read_at = None
            new_state = False
        session.commit()
    return {"ok": True, "read": new_state}
