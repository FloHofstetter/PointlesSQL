"""Branches Control-Room routes.

Surfaces the  Delta-branching primitives behind a
browser-driven UI plus a JSON API a Hermes plugin or external
reviewer can call.

Routes:

* ``GET /branches`` (HTML, admin-only) — list every branch
  schema across every catalog with status / strategy / parent
  metadata.
* ``GET /branches/{branch_fqn}`` (HTML, admin-only) — detail page
  with tag-by-tag drill-down + Audit-trail tab + Danger-zone
  buttons.
* ``GET /api/branches`` (JSON, supervisor+) — flat machine
  list, backing the HTML page and any external consumer.
* ``GET /api/branches/{branch_fqn}`` (JSON, supervisor+) —
  detail JSON.
* ``GET /api/branches/{branch_fqn}/preview-promote`` (JSON,
  supervisor+) — dry-run conflict report; no side effects.
* ``POST /api/branches/{branch_fqn}/promote`` (JSON, admin) —
  triggers :func:`pql.branch_promote`.
* ``POST /api/branches/{branch_fqn}/discard`` (JSON, admin) —
  triggers :func:`pql.branch_discard`.

Branch enumeration is intentionally simple in v1: walk catalogs →
schemas, ask soyuz for tags on each, keep the ones that return
non-``None`` from :func:`branch_tags.read_branch_tags_sync`.  That
is O(N²) in catalogs × schemas per page load and totally fine up
to a few hundred schemas; if it ever becomes a hot path, mirror
the active branches into PointlesSQL's own DB and read from there.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import desc, select

from pointlessql.api.dependencies import (
    get_user,
    require_admin,
    require_supervisor,
)
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models import BranchAuditLog
from pointlessql.pql._branch import (
    discard_branch_schema,
    preview_promote_conflicts,
    promote_branch_schema,
)
from pointlessql.pql._branch_errors import (
    BranchError,
    BranchPromotionConflictError,
)
from pointlessql.services import branch_tags
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.settings import Settings

logger = logging.getLogger(__name__)

router = APIRouter(tags=["branches"])


def _branch_tags_to_dict(tags: branch_tags.BranchTags) -> dict[str, Any]:
    """Project a :class:`BranchTags` into a JSON-safe dict."""
    return {
        "parent_schema": tags.parent_schema,
        "parent_version_at_create": tags.parent_version_at_create,
        "created_at": tags.created_at,
        "created_by_run_id": tags.created_by_run_id,
        "strategy": tags.strategy,
        "status": tags.status,
        "promoted_at": tags.promoted_at,
        "discarded_at": tags.discarded_at,
        "is_pre_promote_backup": tags.is_pre_promote_backup,
    }


def _enumerate_branches(client: Any) -> list[dict[str, Any]]:
    """Walk catalogs → schemas and collect branch-tagged ones.

    Returns a flat list of ``{branch_schema_fqn, tags}`` dicts.
    Errors on individual schemas are logged and skipped — one
    corrupt schema's tag set must not prevent the rest of the page
    from loading.

    Args:
        client: soyuz client.

    Returns:
        List of branch entries.
    """
    from pointlessql.services.unitycatalog._api import (
        _list_catalogs as list_catalogs_api,
    )
    from pointlessql.services.unitycatalog._api import (
        _list_schemas as list_schemas_api,
    )

    branches: list[dict[str, Any]] = []
    catalogs_response = list_catalogs_api.sync(client=client)
    catalog_rows: list[Any] = []
    if catalogs_response is not None:
        catalogs_attr = getattr(catalogs_response, "catalogs", None)
        if isinstance(catalogs_attr, list):
            catalog_rows = catalogs_attr

    for catalog in catalog_rows:
        catalog_name = getattr(catalog, "name", None)
        if not isinstance(catalog_name, str):
            continue
        try:
            schemas_response = list_schemas_api.sync(client=client, catalog_name=catalog_name)
        except Exception:  # noqa: BLE001 — keep enumeration resilient
            logger.warning(
                "_enumerate_branches: list_schemas failed for catalog=%s",
                catalog_name,
                exc_info=True,
            )
            continue
        if schemas_response is None:
            continue
        schema_rows = getattr(schemas_response, "schemas", None)
        if not isinstance(schema_rows, list):
            continue
        for schema in schema_rows:
            schema_name = getattr(schema, "name", None)
            if not isinstance(schema_name, str):
                continue
            schema_fqn = f"{catalog_name}.{schema_name}"
            try:
                tags = branch_tags.read_branch_tags_sync(client, schema_fqn)
            except Exception:  # noqa: BLE001 — corrupt tag set must not poison the list
                logger.warning(
                    "_enumerate_branches: read_branch_tags failed for %s",
                    schema_fqn,
                    exc_info=True,
                )
                continue
            if tags is None:
                continue
            branches.append(
                {
                    "branch_schema_fqn": schema_fqn,
                    "tags": _branch_tags_to_dict(tags),
                }
            )
    return branches


def _branch_audit_rows(
    request: Request, branch_schema_fqn: str, *, limit: int = 50
) -> list[dict[str, Any]]:
    """Return the latest audit-log rows for *branch_schema_fqn*."""
    factory = request.app.state.session_factory
    with factory() as session:
        rows = list(
            session.scalars(
                select(BranchAuditLog)
                .where(BranchAuditLog.branch_schema_fqn == branch_schema_fqn)
                .order_by(desc(BranchAuditLog.created_at))
                .limit(limit)
            )
        )
        for row in rows:
            session.expunge(row)
    return [
        {
            "id": r.id,
            "branch_schema_fqn": r.branch_schema_fqn,
            "parent_schema_fqn": r.parent_schema_fqn,
            "action": r.action,
            "run_id": r.run_id,
            "payload": json.loads(r.payload_json) if r.payload_json else None,
            "created_at": r.created_at.astimezone(datetime.UTC).isoformat(),
        }
        for r in rows
    ]


def _make_settings_client(request: Request) -> tuple[Any, Settings]:
    """Build a per-request soyuz client + resolved Settings tuple."""
    settings: Settings = request.app.state.settings
    client = make_soyuz_client(settings)
    return client, settings


@router.get("/api/branches")
async def api_list_branches(request: Request) -> dict[str, Any]:
    """JSON list of every branch across every catalog."""
    require_supervisor(request)
    client, _ = _make_settings_client(request)
    branches = _enumerate_branches(client)
    return {"branches": branches}


@router.get("/api/branches/{branch_fqn}")
async def api_get_branch(request: Request, branch_fqn: str) -> dict[str, Any]:
    """JSON detail for one branch (tags + audit-log tail)."""
    require_supervisor(request)
    client, _ = _make_settings_client(request)
    tags = branch_tags.read_branch_tags_sync(client, branch_fqn)
    if tags is None:
        raise CatalogNotFoundError(f"branch {branch_fqn!r} not found")
    return {
        "branch_schema_fqn": branch_fqn,
        "tags": _branch_tags_to_dict(tags),
        "audit_log": _branch_audit_rows(request, branch_fqn),
    }


@router.get("/api/branches/{branch_fqn}/preview-promote")
async def api_preview_promote(request: Request, branch_fqn: str) -> dict[str, Any]:
    """Dry-run conflict-detection for a planned promotion."""
    require_supervisor(request)
    client, _ = _make_settings_client(request)
    return preview_promote_conflicts(client=client, branch_schema_fqn=branch_fqn)


@router.post("/api/branches/{branch_fqn}/promote")
async def api_promote_branch(request: Request, branch_fqn: str) -> dict[str, Any]:
    """Promote a branch to be the new parent (admin-only)."""
    require_admin(request)
    client, settings = _make_settings_client(request)
    try:
        result = promote_branch_schema(
            client=client,
            branch_schema_fqn=branch_fqn,
            settings=settings,
        )
    except BranchPromotionConflictError as exc:
        return {
            "ok": False,
            "error": "promotion_conflict",
            "table": exc.table_name,
            "expected_version": exc.expected_version,
            "actual_version": exc.actual_version,
        }
    except BranchError as exc:
        return {"ok": False, "error": exc.__class__.__name__, "message": str(exc)}
    return {"ok": True, **result}


@router.post("/api/branches/{branch_fqn}/discard")
async def api_discard_branch(request: Request, branch_fqn: str) -> dict[str, Any]:
    """Discard a branch (admin-only)."""
    require_admin(request)
    client, settings = _make_settings_client(request)
    try:
        discard_branch_schema(
            client=client,
            branch_schema_fqn=branch_fqn,
            settings=settings,
        )
    except BranchError as exc:
        return {"ok": False, "error": exc.__class__.__name__, "message": str(exc)}
    return {"ok": True}


@router.get("/branches", response_class=HTMLResponse)
async def html_branches_list(request: Request) -> HTMLResponse:
    """Render the branches list page (admin-only)."""
    require_admin(request)
    user = get_user(request)
    client, _ = _make_settings_client(request)
    branches = _enumerate_branches(client)
    return request.app.state.templates.TemplateResponse(
        request,
        "pages/branches.html",
        {
            "branches": branches,
            "is_admin": user.get("is_admin", False),
            "active_page": "branches",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/branches/{branch_fqn}", response_class=HTMLResponse)
async def html_branch_detail(request: Request, branch_fqn: str) -> HTMLResponse:
    """Render the branch-detail page (admin-only)."""
    require_admin(request)
    user = get_user(request)
    client, _ = _make_settings_client(request)
    tags = branch_tags.read_branch_tags_sync(client, branch_fqn)
    if tags is None:
        raise CatalogNotFoundError(f"branch {branch_fqn!r} not found")
    audit_log = _branch_audit_rows(request, branch_fqn)
    return request.app.state.templates.TemplateResponse(
        request,
        "pages/branch_detail.html",
        {
            "branch_schema_fqn": branch_fqn,
            "tags": _branch_tags_to_dict(tags),
            "audit_log": audit_log,
            "is_admin": user.get("is_admin", False),
            "active_page": "branches",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
