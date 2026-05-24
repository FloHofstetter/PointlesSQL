"""Tag GET + PATCH on any securable. PATCH needs MODIFY."""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import effective_principal, get_uc_client, get_user
from pointlessql.services.authorization import MODIFY, check_privilege

logger = logging.getLogger(__name__)

router = APIRouter(tags=["governance"])


@router.get("/api/tags/{securable_type}/{full_name:path}")
async def api_get_tags(
    request: Request,
    securable_type: str,
    full_name: str,
) -> list[dict[str, object]]:
    """Return tags for a securable."""
    client = get_uc_client(request)
    return await client.get_tags(securable_type, full_name)


@router.patch("/api/tags/{securable_type}/{full_name:path}")
async def api_update_tags(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]]:
    """Update tags for a securable. Body: {"changes": [...]}."""
    client = get_uc_client(request)
    user = get_user(request)
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
        user.get("is_admin", False),
        securable_type,
        full_name,
        MODIFY,
    )
    result = await client.update_tags(securable_type, full_name, body.get("changes", []))
    await audit(
        request,
        "update_tags",
        f"{securable_type}:{full_name}",
        json.dumps(body.get("changes", [])),
    )
    return result
