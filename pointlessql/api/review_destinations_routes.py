"""Admin CRUD for the ``review_destinations`` table — Sprint 19.2.1.

Four JSON endpoints, all gated by :func:`require_admin`.  HMAC
secrets are returned at create time only; subsequent reads expose
``has_hmac_secret`` rather than the cleartext value.

This module mirrors the shape of
:mod:`pointlessql.api.admin_api_keys_routes` so future admins
recognise the affordances at a glance: list / create-with-secret-
display / patch / delete.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import require_admin
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models.agent_reviews import REVIEW_SEVERITIES, ReviewDestination

router = APIRouter(tags=["admin-review-destinations"])

_MAX_NAME = 64
_MAX_URL = 2000
_MAX_SECRET = 256


def _serialize(row: ReviewDestination) -> dict[str, Any]:
    """Project a :class:`ReviewDestination` ORM row to a JSON-safe dict.

    Args:
        row: ORM row.

    Returns:
        ``{id, name, webhook_url, has_hmac_secret, is_active,
        min_severity, created_at}``.  ``hmac_secret`` itself is
        never returned post-create.
    """
    return {
        "id": row.id,
        "name": row.name,
        "webhook_url": row.webhook_url,
        "has_hmac_secret": bool(row.hmac_secret),
        "is_active": bool(row.is_active),
        "min_severity": row.min_severity,
        "created_at": row.created_at.astimezone(datetime.UTC).isoformat(),
    }


def _validate_name(value: Any) -> str:
    """Return *value* as a non-empty trimmed string ≤ 64 chars."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("name must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > _MAX_NAME:
        raise ValidationError(f"name must be ≤ {_MAX_NAME} chars")
    return cleaned


def _validate_url(value: Any) -> str:
    """Return *value* as a non-empty https/http URL ≤ 2000 chars."""
    if not isinstance(value, str) or not value.strip():
        raise ValidationError("webhook_url must be a non-empty string")
    cleaned = value.strip()
    if len(cleaned) > _MAX_URL:
        raise ValidationError(f"webhook_url must be ≤ {_MAX_URL} chars")
    if not (cleaned.startswith("https://") or cleaned.startswith("http://")):
        raise ValidationError("webhook_url must start with http:// or https://")
    return cleaned


def _validate_min_severity(value: Any) -> str:
    """Return *value* as one of the three allowed severity strings."""
    if not isinstance(value, str) or value.strip() not in REVIEW_SEVERITIES:
        raise ValidationError(f"min_severity must be one of {sorted(REVIEW_SEVERITIES)}")
    return value.strip()


@router.get("/api/admin/review-destinations")
async def api_admin_list_review_destinations(request: Request) -> dict[str, Any]:
    """List every review destination, active and inactive."""
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        rows = list(
            session.scalars(select(ReviewDestination).order_by(ReviewDestination.id.asc())).all()
        )
        for row in rows:
            session.expunge(row)
    return {"destinations": [_serialize(row) for row in rows]}


@router.post("/api/admin/review-destinations")
async def api_admin_create_review_destination(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a new webhook destination.

    The HMAC secret (if any) is stored verbatim and never re-read.
    The full row including ``hmac_secret`` plaintext is returned
    exactly once so the admin can copy it into the receiving system.

    Args:
        request: Incoming FastAPI request.
        body: ``{name, webhook_url, hmac_secret?, min_severity?,
            is_active?}``.

    Returns:
        Serialised destination + ``hmac_secret`` (plaintext, once).

    Raises:
        ValidationError: On bound or shape violations, or when a
            destination with the requested name already exists.
    """
    require_admin(request)
    name = _validate_name(body.get("name"))
    webhook_url = _validate_url(body.get("webhook_url"))
    raw_secret = body.get("hmac_secret")
    hmac_secret: str | None = None
    if raw_secret is not None:
        if not isinstance(raw_secret, str):
            raise ValidationError("hmac_secret must be a string when set")
        if len(raw_secret) > _MAX_SECRET:
            raise ValidationError(f"hmac_secret must be ≤ {_MAX_SECRET} chars")
        hmac_secret = raw_secret or None
    min_severity = _validate_min_severity(body.get("min_severity", "warn"))
    is_active = bool(body.get("is_active", True))

    factory = request.app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.scalar(select(ReviewDestination).where(ReviewDestination.name == name))
        if existing is not None:
            raise ValidationError(f"review_destination with name {name!r} already exists")
        row = ReviewDestination(
            name=name,
            webhook_url=webhook_url,
            hmac_secret=hmac_secret,
            is_active=is_active,
            min_severity=min_severity,
            created_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(
        request,
        "review_destination.created",
        f"review_destination:{row.name}",
        {"min_severity": min_severity, "is_active": is_active},
    )
    payload = _serialize(row)
    payload["hmac_secret"] = hmac_secret
    return payload


@router.patch("/api/admin/review-destinations/{dest_id}")
async def api_admin_update_review_destination(
    request: Request,
    dest_id: int,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Update a destination in place (sparse PATCH)."""
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(ReviewDestination, dest_id)
        if row is None:
            raise CatalogNotFoundError(f"review_destination id={dest_id} not found")
        if "webhook_url" in body:
            row.webhook_url = _validate_url(body["webhook_url"])
        if "min_severity" in body:
            row.min_severity = _validate_min_severity(body["min_severity"])
        if "is_active" in body:
            row.is_active = bool(body["is_active"])
        if "hmac_secret" in body:
            raw = body["hmac_secret"]
            if raw is None or raw == "":
                row.hmac_secret = None
            else:
                if not isinstance(raw, str) or len(raw) > _MAX_SECRET:
                    raise ValidationError(f"hmac_secret must be a string ≤ {_MAX_SECRET} chars")
                row.hmac_secret = raw
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(
        request,
        "review_destination.updated",
        f"review_destination:{row.name}",
        {k: v for k, v in body.items() if k != "hmac_secret"},
    )
    return _serialize(row)


@router.delete("/api/admin/review-destinations/{dest_id}")
async def api_admin_delete_review_destination(request: Request, dest_id: int) -> dict[str, Any]:
    """Hard-delete a destination row.

    Hard-delete is fine because the dispatcher already records the
    destination's ``url_hash`` + ``name`` onto each
    :class:`AgentReview.delivered_to_json` log entry, so historical
    fan-out attribution survives the row going away.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.get(ReviewDestination, dest_id)
        if row is None:
            raise CatalogNotFoundError(f"review_destination id={dest_id} not found")
        name = row.name
        session.delete(row)
        session.commit()
    await audit(
        request,
        "review_destination.deleted",
        f"review_destination:{name}",
    )
    return {"deleted": dest_id, "name": name}
