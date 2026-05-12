"""Per-user notification inbox routes (Phase 71.4).

Surfaces five endpoints + one HTML page:

* ``GET /notifications`` — HTML shell that the Alpine component
  hydrates against the JSON endpoints below.
* ``GET /api/notifications`` — paginated list, optional
  ``?unread=true`` filter, optional ``?event_type=...`` filter.
* ``GET /api/notifications/unread-count`` — count for the bell badge.
* ``POST /api/notifications/{id}/read`` — mark single read; idempotent.
* ``POST /api/notifications/read-all`` — mark all caller's rows read.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, select

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification

router = APIRouter(tags=["notifications"])


def _serialise_notification(
    row: UserNotification,
    *,
    actor_email: str | None,
    actor_display_name: str | None,
    dp_ref: str | None,
) -> dict[str, Any]:
    """Render one inbox row as JSON."""
    return {
        "id": row.id,
        "event_type": row.event_type,
        "source_data_product_id": row.source_data_product_id,
        "source_data_product_ref": dp_ref,
        "source_url": row.source_url,
        "summary_md": row.summary_md,
        "actor": {
            "user_id": row.actor_user_id,
            "email": actor_email,
            "display_name": actor_display_name,
        },
        "read_at": row.read_at.isoformat() if row.read_at else None,
        "created_at": row.created_at.isoformat(),
    }


@router.get("/notifications", response_class=HTMLResponse, response_model=None)
async def notifications_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the HTML shell for the per-user inbox."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/notifications", status_code=303
        )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/notifications.html",
        {"active_page": "notifications"},
    )


@router.get("/api/notifications")
async def list_notifications(
    request: Request,
    unread: bool = Query(default=False),
    event_type: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """List the caller's notifications with optional unread + type filters."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory

    with factory() as session:
        stmt = (
            select(UserNotification)
            .where(
                UserNotification.workspace_id == workspace_id,
                UserNotification.recipient_user_id == user["id"],
            )
            .order_by(UserNotification.created_at.desc())
        )
        if unread:
            stmt = stmt.where(UserNotification.read_at.is_(None))
        if event_type:
            stmt = stmt.where(UserNotification.event_type == event_type)
        stmt = stmt.limit(limit).offset(offset)
        rows = session.execute(stmt).scalars().all()

        actor_ids = {r.actor_user_id for r in rows if r.actor_user_id is not None}
        actor_map: dict[int, tuple[str, str]] = {}
        if actor_ids:
            users = (
                session.execute(select(User).where(User.id.in_(actor_ids)))
                .scalars()
                .all()
            )
            actor_map = {u.id: (u.email, u.display_name) for u in users}

        dp_ids = {r.source_data_product_id for r in rows if r.source_data_product_id is not None}
        dp_ref_map: dict[int, str] = {}
        if dp_ids:
            dps = (
                session.execute(select(DataProduct).where(DataProduct.id.in_(dp_ids)))
                .scalars()
                .all()
            )
            dp_ref_map = {dp.id: f"{dp.catalog_name}.{dp.schema_name}" for dp in dps}

    payload = [
        _serialise_notification(
            r,
            actor_email=(actor_map.get(r.actor_user_id, (None, None))[0]
                         if r.actor_user_id is not None
                         else None),
            actor_display_name=(actor_map.get(r.actor_user_id, (None, None))[1]
                                if r.actor_user_id is not None
                                else None),
            dp_ref=dp_ref_map.get(r.source_data_product_id or -1),
        )
        for r in rows
    ]
    return {"notifications": payload, "offset": offset, "limit": limit}


@router.get("/api/notifications/unread-count")
async def unread_count(request: Request) -> dict[str, int]:
    """Return the unread-count for the bell badge."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        count = session.execute(
            select(func.count(UserNotification.id)).where(
                UserNotification.workspace_id == workspace_id,
                UserNotification.recipient_user_id == user["id"],
                UserNotification.read_at.is_(None),
            )
        ).scalar_one()
    return {"unread": int(count)}


@router.post("/api/notifications/{notification_id}/read")
async def mark_read(
    notification_id: int,
    request: Request,
) -> dict[str, Any]:
    """Mark one row read.  Idempotent on already-read rows."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(UserNotification, notification_id)
        if (
            row is None
            or row.workspace_id != workspace_id
            or row.recipient_user_id != user["id"]
        ):
            # bare-http-ok: cross-user / cross-workspace ids surface as 404
            # rather than 403 so the inbox doesn't leak existence info.
            raise HTTPException(status_code=404, detail="notification not found")
        if row.read_at is None:
            row.read_at = datetime.datetime.now(datetime.UTC)
            session.add(row)
            session.commit()
            session.refresh(row)
    return {
        "id": row.id,
        "read_at": row.read_at.isoformat() if row.read_at else None,
    }


@router.post("/api/notifications/read-all")
async def mark_all_read(request: Request) -> dict[str, Any]:
    """Mark every unread row for the caller as read."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        rows = (
            session.execute(
                select(UserNotification).where(
                    UserNotification.workspace_id == workspace_id,
                    UserNotification.recipient_user_id == user["id"],
                    UserNotification.read_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        for r in rows:
            r.read_at = now
            session.add(r)
        session.commit()
    return {"flipped": len(rows)}
