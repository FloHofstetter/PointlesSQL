"""Data classification console: tag-policy rules + PII scans.

One admin surface combining the two halves of attribute-based
governance: the rule set (tag → mask / row filter, enforced at the
SELECT choke points) and the scanner that produces the ``pii`` column
tags those rules typically match.  JSON routes are admin-only; the
HTML console lives at ``/admin/classification``.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    get_templates,
    get_uc_client,
    get_user,
    require_admin,
)
from pointlessql.exceptions import ValidationError
from pointlessql.services import pii_classification, tag_policies

router = APIRouter(tags=["classification"])


def _serialize_rule(rule: Any) -> dict[str, Any]:
    """Render one rule row for JSON responses."""
    return {
        "id": rule.id,
        "tag_key": rule.tag_key,
        "tag_value": rule.tag_value,
        "scope_type": rule.scope_type,
        "scope_value": rule.scope_value,
        "effect": rule.effect,
        "expr": rule.expr,
        "priority": rule.priority,
        "is_active": rule.is_active,
        "description": rule.description,
        "created_at": rule.created_at.isoformat() if rule.created_at else None,
    }


@router.get("/api/admin/tag-policies")
async def api_list_tag_policies(request: Request) -> list[dict[str, Any]]:
    """List every tag-policy rule (admin only)."""
    require_admin(request)
    factory = request.app.state.session_factory
    return [_serialize_rule(r) for r in tag_policies.list_rules(factory)]


@router.post("/api/admin/tag-policies")
async def api_create_tag_policy(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Create a rule (admin only).

    Body: ``{tag_key, tag_value?, scope_type?, scope_value?, effect,
    expr, priority?, description?}``.
    """
    require_admin(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    rule = tag_policies.create_rule(
        factory,
        tag_key=str(body.get("tag_key") or ""),
        tag_value=(str(body["tag_value"]) if body.get("tag_value") else None),
        effect=str(body.get("effect") or ""),
        expr=str(body.get("expr") or ""),
        priority=int(body.get("priority") or 100),
        description=(str(body["description"]) if body.get("description") else None),
        scope_type=str(body.get("scope_type") or "global"),
        scope_value=(str(body["scope_value"]) if body.get("scope_value") else None),
        created_by_user_id=user["id"],
    )
    await audit(request, "tag_policy.created", f"tag_policy:{rule.id}", _serialize_rule(rule))
    return _serialize_rule(rule)


@router.patch("/api/admin/tag-policies/{rule_id}")
async def api_update_tag_policy(
    request: Request, rule_id: int, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Toggle / reprioritise / annotate a rule (admin only)."""
    require_admin(request)
    factory = request.app.state.session_factory
    rule = tag_policies.update_rule(
        factory,
        rule_id,
        is_active=(bool(body["is_active"]) if "is_active" in body else None),
        priority=(int(body["priority"]) if "priority" in body else None),
        description=(str(body["description"]) if "description" in body else None),
    )
    await audit(request, "tag_policy.updated", f"tag_policy:{rule_id}", body)
    return _serialize_rule(rule)


@router.delete("/api/admin/tag-policies/{rule_id}")
async def api_delete_tag_policy(request: Request, rule_id: int) -> dict[str, Any]:
    """Delete a rule (admin only).

    Args:
        request: The incoming request (admin gate).
        rule_id: Target rule id.

    Returns:
        ``{"deleted": true}`` on success.

    Raises:
        ValidationError: When the rule does not exist.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    if not tag_policies.delete_rule(factory, rule_id):
        raise ValidationError(f"tag policy rule {rule_id} not found")
    await audit(request, "tag_policy.deleted", f"tag_policy:{rule_id}")
    return {"deleted": True}


@router.get("/api/admin/tag-policies/preview")
async def api_preview_scan_policy(
    request: Request,
    table: str = Query(..., description="catalog.schema.table to preview"),
    principal: str | None = Query(default=None, description="external principal to preview as"),
) -> dict[str, Any]:
    """Preview the cross-engine scan policy for a table + principal (admin).

    Shows which columns an external Iceberg client running as
    *principal* would see masked, and which row-filter predicate the
    pre-filtered scan plan would carry — the observability view over the
    same tag-policy evaluation the SELECT choke points apply.

    Args:
        request: The incoming request (admin gate + UC client).
        table: Three-part ``catalog.schema.table`` to preview.
        principal: External principal to evaluate as; defaults to the
            requesting admin's email when omitted.

    Returns:
        The preview payload from
        :func:`tag_policies.preview_scan_policy`.
    """
    require_admin(request)
    uc_client = get_uc_client(request)
    user = get_user(request)
    target_principal = (principal or "").strip() or str(user.get("email", ""))
    return await tag_policies.preview_scan_policy(
        uc_client,
        full_name=table.strip(),
        principal=target_principal,
        factory=request.app.state.session_factory,
    )


@router.post("/api/admin/classification/scan")
async def api_classification_scan(
    request: Request, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Run a PII scan now, as the calling admin (admin only).

    Args:
        request: The incoming request (admin gate + principal client).
        body: ``{"table": "cat.sch.tbl"}`` or
            ``{"catalog": ..., "schema": ...}``.

    Returns:
        ``{"findings": [...]}`` with one entry per classified column.

    Raises:
        ValidationError: When the body carries no usable scope.
    """
    require_admin(request)
    uc_client = get_uc_client(request)
    try:
        findings = await pii_classification.scan_scope(
            uc_client,
            table=(str(body["table"]) if body.get("table") else None),
            catalog=(str(body["catalog"]) if body.get("catalog") else None),
            schema=(str(body["schema"]) if body.get("schema") else None),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    await audit(
        request,
        "classification.scan",
        f"scan:{body.get('table') or body.get('catalog')}",
        {"findings": len(findings)},
    )
    return {"findings": [dataclasses.asdict(f) for f in findings]}


@router.get("/admin/classification", response_class=HTMLResponse)
async def admin_classification_page(request: Request) -> Any:
    """Render the classification console (rules + scan)."""
    require_admin(request)
    factory = request.app.state.session_factory
    rules = [_serialize_rule(r) for r in tag_policies.list_rules(factory)]
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_classification.html",
        {
            "active_page": "admin",
            "rules": rules,
        },
    )
