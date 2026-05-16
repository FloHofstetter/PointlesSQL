"""Read-only lineage endpoint. SELECT on the target table."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import effective_principal, get_uc_client, get_user
from pointlessql.services.authorization import SELECT, check_privilege

logger = logging.getLogger(__name__)

router = APIRouter(tags=["governance"])


@router.get("/api/lineage/{full_name:path}")
async def api_lineage(request: Request, full_name: str, depth: int = 3) -> dict[str, object]:
    """Return combined upstream/downstream lineage for a table."""
    client = get_uc_client(request)
    user = get_user(request)
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )
    return await client.get_lineage(full_name, depth)
