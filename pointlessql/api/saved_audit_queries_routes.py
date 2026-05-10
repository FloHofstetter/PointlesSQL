"""Saved-audit-query CRUD + run + export endpoints.

Admin-only.  See
:mod:`pointlessql.services.saved_audit_queries` for the
allow-list, starter-row contract, and execution semantics.
"""

from __future__ import annotations

import csv
import io
import json
import logging
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.templating import Jinja2Templates

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.services import saved_audit_queries as svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["audit"])


def _templates(request: Request) -> Jinja2Templates:
    return request.app.state.templates


@router.get("/api/saved-audit-queries")
async def api_list_saved_audit_queries(request: Request) -> dict[str, Any]:
    """Return every saved audit query (starters first).

    Args:
        request: FastAPI request.

    Returns:
        ``{"saved_audit_queries": [...]}``.
    """
    require_admin(request)
    return {"saved_audit_queries": svc.list_all(request.app.state.session_factory)}


@router.post("/api/saved-audit-queries")
async def api_create_saved_audit_query(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create one new saved audit query.

    Args:
        request: FastAPI request.
        body: ``{"title", "description"?, "sql_text",
            "alert_threshold_count"?}``.

    Returns:
        Serialised row.

    Raises:
        ValidationError: title/SQL empty or SQL outside the
            allow-list.
    """
    require_admin(request)
    user = get_user(request)
    title = str(body.get("title") or "")
    sql_text = str(body.get("sql_text") or "")
    description = body.get("description")
    description = str(description) if description is not None else None
    alert_threshold = body.get("alert_threshold_count")
    if alert_threshold is not None:
        try:
            alert_threshold = int(alert_threshold)
        except (TypeError, ValueError) as exc:
            raise ValidationError("alert_threshold_count must be an integer") from exc
    row = svc.create(
        request.app.state.session_factory,
        owner_id=int(user.get("id") or 0),
        title=title,
        description=description,
        sql_text=sql_text,
        alert_threshold_count=alert_threshold,
    )
    await audit(
        request,
        "saved_audit_query.created",
        f"saved_audit_query:{row['slug']}",
        {"title": row["title"]},
    )
    return row


@router.get("/api/saved-audit-queries/{slug}")
async def api_get_saved_audit_query(request: Request, slug: str) -> dict[str, Any]:
    """Return one saved audit query by slug.

    Args:
        request: FastAPI request.
        slug: URL-visible identifier.

    Returns:
        Serialised row.

    Raises:
        ResourceNotFoundError: 404 when slug does not exist.
    """
    require_admin(request)
    row = svc.get_by_slug(request.app.state.session_factory, slug)
    if row is None:
        raise ResourceNotFoundError(f"saved_audit_query: {slug}")
    return row


@router.patch("/api/saved-audit-queries/{slug}")
async def api_update_saved_audit_query(
    request: Request,
    slug: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Patch an existing saved audit query.  Refuses on starters.

    Args:
        request: FastAPI request.
        slug: Target slug.
        body: Mutable subset of
            ``{"title", "description", "sql_text",
            "alert_threshold_count"}``.

    Returns:
        Serialised row.

    Raises:
        ResourceNotFoundError: 404 when slug missing or row is a
            starter.
        ValidationError: Provided SQL outside the allow-list, or
            ``alert_threshold_count`` not coercible to an integer.
    """
    require_admin(request)
    threshold_arg: int | None | str = "__unchanged__"
    if "alert_threshold_count" in body:
        raw = body.get("alert_threshold_count")
        if raw is None:
            threshold_arg = None
        else:
            try:
                threshold_arg = int(raw)
            except (TypeError, ValueError) as exc:
                raise ValidationError("alert_threshold_count must be an integer or null") from exc
    row = svc.update(
        request.app.state.session_factory,
        slug,
        title=body.get("title"),
        description=body.get("description"),
        sql_text=body.get("sql_text"),
        alert_threshold_count=threshold_arg,
    )
    if row is None:
        raise ResourceNotFoundError(f"saved_audit_query: {slug}")
    await audit(
        request,
        "saved_audit_query.updated",
        f"saved_audit_query:{slug}",
        {"keys": sorted(body.keys())},
    )
    return row


@router.delete("/api/saved-audit-queries/{slug}")
async def api_delete_saved_audit_query(request: Request, slug: str) -> dict[str, Any]:
    """Delete a non-starter saved audit query by slug.

    Args:
        request: FastAPI request.
        slug: Target slug.

    Returns:
        ``{"deleted": True}``.

    Raises:
        ResourceNotFoundError: 404 when slug missing or row is a
            starter.
    """
    require_admin(request)
    deleted = svc.delete(request.app.state.session_factory, slug)
    if not deleted:
        raise ResourceNotFoundError(f"saved_audit_query: {slug}")
    await audit(
        request,
        "saved_audit_query.deleted",
        f"saved_audit_query:{slug}",
        None,
    )
    return {"deleted": True}


@router.post("/api/saved-audit-queries/{slug}/run")
async def api_run_saved_audit_query(
    request: Request,
    slug: str,
    row_cap: int = Query(default=1000, ge=1, le=10_000),
) -> dict[str, Any]:
    """Execute the saved query and return the result set as JSON.

    Args:
        request: FastAPI request.
        slug: Target slug.
        row_cap: Hard row cap (1–10 000).  Export endpoints can
            request the higher caps.

    Returns:
        ``{"slug", "columns", "rows", "row_count", "truncated",
        "referenced_tables"}``.

    Raises:
        ResourceNotFoundError: 404 when slug missing.
    """
    require_admin(request)
    result = svc.execute(request.app.state.session_factory, slug, row_cap=row_cap)
    if result is None:
        raise ResourceNotFoundError(f"saved_audit_query: {slug}")
    return result


@router.get("/api/saved-audit-queries/{slug}/export.csv")
async def api_export_saved_audit_query_csv(
    request: Request,
    slug: str,
) -> StreamingResponse:
    """Stream the query result as CSV.

    Args:
        request: FastAPI request.
        slug: Target slug.

    Returns:
        ``text/csv`` streaming response with the BOM-less UTF-8
        body and a ``Content-Disposition`` header carrying the
        slug as filename.

    Raises:
        ResourceNotFoundError: 404 when slug missing.
    """
    require_admin(request)
    result = svc.execute(request.app.state.session_factory, slug, row_cap=10_000)
    if result is None:
        raise ResourceNotFoundError(f"saved_audit_query: {slug}")

    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(result["columns"])
    for row in result["rows"]:
        writer.writerow([row.get(col) for col in result["columns"]])

    await audit(
        request,
        "saved_audit_query.exported",
        f"saved_audit_query:{slug}",
        {"format": "csv", "row_count": result["row_count"]},
    )
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}.csv"',
        },
    )


@router.get("/api/saved-audit-queries/{slug}/export.json")
async def api_export_saved_audit_query_json(
    request: Request,
    slug: str,
) -> StreamingResponse:
    """Stream the query result as a JSON array.

    Args:
        request: FastAPI request.
        slug: Target slug.

    Returns:
        ``application/json`` streaming response.

    Raises:
        ResourceNotFoundError: 404 when slug missing.
    """
    require_admin(request)
    result = svc.execute(request.app.state.session_factory, slug, row_cap=10_000)
    if result is None:
        raise ResourceNotFoundError(f"saved_audit_query: {slug}")

    payload = json.dumps(
        {
            "slug": slug,
            "columns": result["columns"],
            "rows": result["rows"],
            "row_count": result["row_count"],
            "truncated": result["truncated"],
        },
        default=str,
    )
    await audit(
        request,
        "saved_audit_query.exported",
        f"saved_audit_query:{slug}",
        {"format": "json", "row_count": result["row_count"]},
    )
    return StreamingResponse(
        iter([payload]),
        media_type="application/json",
        headers={
            "Content-Disposition": f'attachment; filename="{slug}.json"',
        },
    )


_AUDIT_QUERIES_PAGE_SIZE = 50


@router.get("/audit/queries", response_class=HTMLResponse)
async def html_audit_queries(
    request: Request,
    offset: int = Query(default=0, ge=0),
) -> HTMLResponse:
    """Render the audit-cockpit query workbench.

    Args:
        request: FastAPI request.
        offset: Zero-based offset for the saved-queries pager.

    Returns:
        Rendered ``pages/audit_queries.html`` with one page of saved
        queries plus the global ``total`` so the pager can decide
        whether to render Next/Prev buttons.
    """
    require_admin(request)
    rows, total = svc.list_paginated(
        request.app.state.session_factory,
        offset=offset,
        limit=_AUDIT_QUERIES_PAGE_SIZE,
    )
    return _templates(request).TemplateResponse(
        request,
        "pages/audit_queries.html",
        {
            "saved_audit_queries": rows,
            "saved_audit_queries_total": total,
            "saved_audit_queries_offset": offset,
            "saved_audit_queries_limit": _AUDIT_QUERIES_PAGE_SIZE,
            "active_page": "audit",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/audit/queries/{slug}", response_class=HTMLResponse)
async def html_audit_query_detail(request: Request, slug: str) -> HTMLResponse:
    """Render one saved query as a dedicated read-page.

    Cards on ``/audit/queries`` link here so the user can read the
    full markdown briefing without the cockpit's split-pane editor.
    The detail page exposes the same Run / CSV / JSON / Open-in-
    editor actions but with the description front and centre.

    Args:
        request: FastAPI request.
        slug: URL-visible identifier of the saved query.

    Returns:
        Rendered ``pages/saved_audit_query_detail.html``.

    Raises:
        ResourceNotFoundError: When *slug* does not match any saved
            query.
    """
    require_admin(request)
    row = svc.get_by_slug(request.app.state.session_factory, slug)
    if row is None:
        raise ResourceNotFoundError(f"Saved audit query not found: {slug}")
    return _templates(request).TemplateResponse(
        request,
        "pages/saved_audit_query_detail.html",
        {
            "query": row,
            "active_page": "audit",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )
