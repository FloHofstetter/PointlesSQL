"""Mesh-cost dashboard + cost-by-product + cost-by-consumer routes."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Body, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_admin,
    require_user,
)
from pointlessql.exceptions import AuthorizationError, BadRequestError
from pointlessql.services import cost as cost_service
from pointlessql.services.governance._policy import set_workspace_policy

router = APIRouter(tags=["admin-cost"])


def _parse_window(
    since: str | None, until: str | None
) -> tuple[datetime.datetime | None, datetime.datetime | None]:
    """Best-effort ISO-8601 parse; raises 400 on malformed input."""
    def parse(value: str | None) -> datetime.datetime | None:
        if not value:
            return None
        try:
            return datetime.datetime.fromisoformat(value)
        except (ValueError, TypeError) as exc:
            raise BadRequestError(f"invalid ISO-8601 timestamp: {value}") from exc

    return parse(since), parse(until)


@router.get("/api/mesh/health/full")
async def mesh_health_full(request: Request) -> dict[str, Any]:
    """Return the comprehensive mesh-health dashboard payload (any-user)."""
    require_user(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    return cost_service.mesh_health_full(factory, workspace_id=workspace_id)


@router.get("/api/cost/by-product")
async def cost_by_product(
    request: Request,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Per-product cost rollup over a window (steward/admin)."""
    require_user(request)
    user = get_user(request)
    if not user.get("is_admin"):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="auditor",
            securable_type="cost_dashboard",
            full_name="",
        )
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    since_parsed, until_parsed = _parse_window(since, until)
    return {
        "rows": cost_service.cost_by_product(
            factory,
            workspace_id=workspace_id,
            since=since_parsed,
            until=until_parsed,
        )
    }


@router.get("/api/cost/by-consumer")
async def cost_by_consumer(
    request: Request,
    since: str | None = None,
    until: str | None = None,
) -> dict[str, Any]:
    """Per-consumer cost rollup over a window (admin only)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    since_parsed, until_parsed = _parse_window(since, until)
    return {
        "rows": cost_service.cost_by_consumer(
            factory,
            workspace_id=workspace_id,
            since=since_parsed,
            until=until_parsed,
        )
    }


@router.put("/api/admin/governance/quota")
async def set_workspace_quota(
    request: Request,
    body: dict[str, Any] = Body(default_factory=dict[str, Any]),
) -> dict[str, Any]:
    """Set the workspace-default quota fields (admin)."""
    require_admin(request)
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    keys = ("max_cost_per_day", "max_queries_per_hour", "quota_enforcement")
    fields = {k: body[k] for k in keys if k in body}
    set_workspace_policy(
        factory,
        workspace_id=workspace_id,
        fields=fields,
        updated_by_user_id=int(user.get("id", 0) or 0) or None,
    )
    await audit(
        request,
        "governance.workspace_quota_set",
        f"workspace:{workspace_id}",
        {"fields": list(fields.keys())},
    )
    return {"updated_fields": list(fields.keys())}
