"""Permission + effective-permission GET / PATCH endpoints.

PATCH needs MANAGE_GRANTS on the target.  GET surfaces both the raw
grant rows and the effective resolution.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import effective_principal, get_uc_client, get_user
from pointlessql.services.authorization import MANAGE_GRANTS, check_privilege

logger = logging.getLogger(__name__)

router = APIRouter(tags=["governance"])


@router.get("/api/permissions/{securable_type}/{full_name:path}")
async def api_get_permissions(
    request: Request,
    securable_type: str,
    full_name: str,
) -> list[dict[str, object]]:
    """Return privilege assignments for a securable."""
    client = get_uc_client(request)
    return await client.get_permissions(securable_type, full_name)


@router.patch("/api/permissions/{securable_type}/{full_name:path}")
async def api_update_permissions(
    request: Request,
    securable_type: str,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> list[dict[str, object]]:
    """Update permissions for a securable. Body: {"changes": [...]}."""
    client = get_uc_client(request)
    user = get_user(request)
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
        user.get("is_admin", False),
        securable_type,
        full_name,
        MANAGE_GRANTS,
    )
    result = await client.update_permissions(securable_type, full_name, body.get("changes", []))
    await audit(
        request,
        "update_permissions",
        f"{securable_type}:{full_name}",
        json.dumps(body.get("changes", [])),
    )
    return result


@router.get("/api/effective-permissions/{securable_type}/{full_name:path}")
async def api_get_effective_permissions(
    request: Request,
    securable_type: str,
    full_name: str,
) -> list[dict[str, object]]:
    """Return effective (inherited) permissions for a securable."""
    client = get_uc_client(request)
    return await client.get_effective_permissions(securable_type, full_name)
