"""Destinations sub-resource: ``POST/DELETE /api/alerts/{slug}/destinations``.

Owner / admin gate; missing-vs-forbidden collapses to 404 same as the
parent CRUD.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Body, Request
from fastapi.responses import Response

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user
from pointlessql.services._executor import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(tags=["alerts"])


@router.post("/api/alerts/{slug}/destinations")
async def api_add_alert_destination(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Add a webhook or feed destination to an alert.

    Args:
        request: Incoming request.
        slug: Target alert slug.
        body: Body with ``kind`` (``webhook`` / ``feed``), plus
            ``webhook_url`` / ``hmac_secret`` when relevant.

    Returns:
        The new destination dict.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below; ValidationError bubbles from service
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = get_user(request)
    payload = body or {}
    dest = await run_sync(
        alerts_service.add_destination,
        factory,
        slug,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
        kind=str(payload.get("kind", "webhook")),
        webhook_url=payload.get("webhook_url")
        if isinstance(payload.get("webhook_url"), str)
        else None,
        hmac_secret=payload.get("hmac_secret")
        if isinstance(payload.get("hmac_secret"), str)
        else None,
    )
    if dest is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await audit(
        request,
        "alert.destination_added",
        f"alert:{slug}",
        {"kind": dest["kind"], "has_hmac": dest["has_hmac"]},
    )
    return dest


@router.delete(
    "/api/alerts/{slug}/destinations/{destination_id}",
    status_code=204,
)
async def api_delete_alert_destination(
    request: Request,
    slug: str,
    destination_id: int,
) -> Response:
    """Remove a destination from an alert.

    Args:
        request: Incoming request.
        slug: Target alert slug.
        destination_id: Row id of the destination.

    Returns:
        Empty 204 response on success.

    Raises:
        CatalogNotFoundError: On missing or forbidden slug.
    """  # noqa: DOC502 — raised below
    from pointlessql.exceptions import CatalogNotFoundError
    from pointlessql.services import alerts as alerts_service

    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    user = get_user(request)
    ok = await run_sync(
        alerts_service.delete_destination,
        factory,
        slug,
        destination_id,
        user_id=user["id"],
        is_admin=bool(user.get("is_admin", False)),
    )
    if not ok:
        raise CatalogNotFoundError(f"Alert {slug!r} not found.")
    await audit(
        request,
        "alert.destination_removed",
        f"alert:{slug}/destination:{destination_id}",
        None,
    )
    return Response(status_code=204)
