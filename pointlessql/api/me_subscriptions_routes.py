"""Per-user CloudEvent webhook subscriptions (Phase 72.6).

Surfaces ``/me/subscriptions`` HTML + four JSON endpoints
(``GET / POST / PUT / DELETE``).  HMAC secret is generated
server-side at create time and returned to the caller exactly
once.  Subscriptions deliver via the existing audit-sink HMAC
signer (Phase 20).
"""

from __future__ import annotations

import datetime
import secrets
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import BadRequestError, ResourceNotFoundError
from pointlessql.models.notifications import UserWebhookSubscription

router = APIRouter(tags=["me"])


def _serialise(
    sub: UserWebhookSubscription, *, include_secret: bool = False
) -> dict[str, Any]:
    """Render one subscription as JSON.

    The HMAC secret is only echoed when ``include_secret=True``;
    that's reserved for the create response so the caller can
    record it once.
    """
    payload: dict[str, Any] = {
        "id": sub.id,
        "webhook_url": sub.webhook_url,
        "event_type_filter": sub.event_type_filter,
        "dp_ref_filter": sub.dp_ref_filter,
        "is_active": bool(sub.is_active),
        "created_at": sub.created_at.isoformat(),
        "last_delivered_at": (
            sub.last_delivered_at.isoformat()
            if sub.last_delivered_at
            else None
        ),
        "last_error": sub.last_error,
    }
    if include_secret:
        payload["hmac_secret"] = sub.hmac_secret
    return payload


@router.get(
    "/me/subscriptions", response_class=HTMLResponse, response_model=None
)
async def me_subscriptions_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the self-service subscriptions page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/me/subscriptions", status_code=303
        )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/me_subscriptions.html",
        {"active_page": "me_subscriptions"},
    )


@router.get("/api/me/subscriptions")
async def list_subscriptions(request: Request) -> dict[str, Any]:
    """Return the caller's active + inactive subscriptions."""
    require_user(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(UserWebhookSubscription)
                .where(UserWebhookSubscription.user_id == user["id"])
                .order_by(UserWebhookSubscription.created_at.desc())
            )
            .scalars()
            .all()
        )
    return {"subscriptions": [_serialise(r) for r in rows]}


@router.post("/api/me/subscriptions")
async def create_subscription(request: Request) -> dict[str, Any]:
    """Create a new webhook subscription.

    Body: ``{"webhook_url": str, "event_type_filter": str,
    "dp_ref_filter": str?}``.  Returns the serialised row with the
    generated ``hmac_secret`` field — recorded once.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    body = await request.json()
    webhook_url = (body.get("webhook_url") or "").strip()
    event_type_filter = (body.get("event_type_filter") or "").strip()
    dp_ref_filter = body.get("dp_ref_filter") or None
    if not webhook_url:
        raise BadRequestError("webhook_url is required")
    if not event_type_filter:
        raise BadRequestError("event_type_filter is required")

    hmac_secret = secrets.token_urlsafe(64)
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = UserWebhookSubscription(
            workspace_id=workspace_id,
            user_id=user["id"],
            webhook_url=webhook_url,
            hmac_secret=hmac_secret,
            event_type_filter=event_type_filter,
            dp_ref_filter=dp_ref_filter,
            is_active=1,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
    return _serialise(row, include_secret=True)


@router.put("/api/me/subscriptions/{sub_id}")
async def update_subscription(
    sub_id: int, request: Request
) -> dict[str, Any]:
    """Toggle ``is_active`` or update filter/URL."""
    require_user(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    body = await request.json()
    with factory() as session:
        row = session.get(UserWebhookSubscription, sub_id)
        if row is None or row.user_id != user["id"]:
            raise ResourceNotFoundError("subscription not found.")
        if "is_active" in body:
            row.is_active = 1 if bool(body["is_active"]) else 0
        if "webhook_url" in body:
            row.webhook_url = (body["webhook_url"] or "").strip() or row.webhook_url
        if "event_type_filter" in body:
            new_filter = (body["event_type_filter"] or "").strip()
            if new_filter:
                row.event_type_filter = new_filter
        if "dp_ref_filter" in body:
            row.dp_ref_filter = body["dp_ref_filter"] or None
        session.add(row)
        session.commit()
        session.refresh(row)
    return _serialise(row)


@router.delete("/api/me/subscriptions/{sub_id}")
async def delete_subscription(
    sub_id: int, request: Request
) -> dict[str, Any]:
    """Hard-delete a subscription."""
    require_user(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(UserWebhookSubscription, sub_id)
        if row is None or row.user_id != user["id"]:
            return {"deleted": False}
        session.delete(row)
        session.commit()
    return {"deleted": True}
