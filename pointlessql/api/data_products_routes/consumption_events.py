"""Consumption-audit feed for the Overview panel (D2).

Backed by the rows :func:`pointlessql.services.governance.emit_consumption_audit`
writes to ``audit_log``.  The panel shows the last ``limit``
``consumption.undeclared`` and ``consumption.blocked`` entries against
the product, plus an ack-button that writes a complementary
``consumption.acknowledged`` row.

This is read-only by design — the ack action is the only mutation, and
it is gated to steward / admin so a regular user can not silence a
finding for everyone.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError
from pointlessql.models import AuditLog
from pointlessql.services.audit import log_action
from pointlessql.services.governance import (
    CONSUMPTION_BLOCKED_ACTION,
    CONSUMPTION_UNDECLARED_ACTION,
)

CONSUMPTION_ACK_ACTION = "consumption.acknowledged"

router = APIRouter(tags=["data-products"])


@router.get("/api/data-products/{catalog}/{schema}/consumption-acknowledgements")
async def list_consumption_events(
    catalog: str,
    schema: str,
    request: Request,
    limit: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """Return the last *limit* consumption-related audit rows on this product."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    target = f"data_product:{dp_row.id}"
    with factory() as session:
        rows = list(
            session.scalars(
                select(AuditLog)
                .where(
                    AuditLog.target == target,
                    AuditLog.action.in_(
                        (CONSUMPTION_UNDECLARED_ACTION, CONSUMPTION_BLOCKED_ACTION)
                    ),
                )
                .order_by(AuditLog.id.desc())
                .limit(limit)
            ).all()
        )
    items: list[dict[str, Any]] = []
    for row in rows:
        detail: dict[str, Any] = {}
        if row.detail:
            try:
                detail = json.loads(row.detail)
            except (TypeError, ValueError):
                detail = {"raw": row.detail}
        items.append(
            {
                "id": int(row.id),
                "action": row.action,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "source": detail.get("source"),
                "mode": detail.get("mode"),
                "reason": detail.get("reason"),
                "actor_email": row.user_email,
            }
        )
    return {"items": items}


@router.post(
    "/api/data-products/{catalog}/{schema}/consumption-acknowledgements/{event_id}"
)
async def acknowledge_consumption_event(
    catalog: str,
    schema: str,
    event_id: int,
    request: Request,
) -> dict[str, Any]:
    """Acknowledge one ``consumption.undeclared`` audit row.

    Steward / admin only.  Writes a complementary
    ``consumption.acknowledged`` row referencing *event_id*.
    """
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    dp_row, _, _, _ = load_one(factory, workspace_id, catalog, schema)
    user = get_user(request)
    is_admin = bool(user.get("is_admin"))
    is_steward = dp_row.steward_user_id is not None and dp_row.steward_user_id == user["id"]
    if not (is_admin or is_steward):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="steward",
            securable_type="data_product",
            full_name=f"{catalog}.{schema}",
        )
    log_action(
        factory,
        int(user.get("id", 0) or 0),
        user.get("email", "") or "",
        CONSUMPTION_ACK_ACTION,
        f"data_product:{dp_row.id}",
        detail={"acknowledged_event_id": int(event_id)},
        actor_role="admin" if is_admin else "user",
        workspace_id=workspace_id,
    )
    return {
        "acknowledged": True,
        "event_id": int(event_id),
        "acknowledged_at": datetime.datetime.now(datetime.UTC).isoformat(),
    }
