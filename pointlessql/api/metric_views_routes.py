"""Metric-view routes — semantic-layer definitions + governed queries.

JSON surface under ``/api/metric-views`` plus one HTML browser page.
Definitions live in soyuz-catalog (through the facade); querying
compiles the definition via
:func:`pointlessql.pql._metrics.compile_metric_query` and executes
through the same SELECT-enforcement + PQL.sql path as the SQL
editor, so a metric view can never read more than its caller could.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_templates, get_uc_client, get_user
from pointlessql.exceptions import ValidationError
from pointlessql.pql._metrics import compile_metric_query
from pointlessql.services._executor import run_sync
from pointlessql.services.notebook._sql_cell import resolve_select_context

router = APIRouter(tags=["metric-views"])

_MAX_ROWS = 10_000


@router.get("/api/metric-views")
async def api_list_metric_views(
    request: Request,
    catalog_name: str = Query(...),
    schema_name: str = Query(...),
) -> dict[str, Any]:
    """List a schema's metric views.

    Args:
        request: Incoming FastAPI request.
        catalog_name: Parent catalog.
        schema_name: Parent schema.

    Returns:
        ``{"metric_views": [...]}`` straight from the catalog.
    """
    uc = get_uc_client(request)
    views = await uc.list_metric_views(catalog_name, schema_name)
    return {"metric_views": views}


@router.post("/api/metric-views")
async def api_create_metric_view(
    request: Request,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Create a metric view.

    Args:
        request: Incoming FastAPI request.
        body: ``{"name", "catalog_name", "schema_name",
            "source_table_full_name", "spec", "comment"?}`` —
            validated structurally by soyuz.

    Returns:
        The created metric-view info dict.
    """
    uc = get_uc_client(request)
    created = await uc.create_metric_view(body)
    full_name = created.get("full_name") or body.get("name")
    await audit(
        request,
        "metric_view.created",
        f"metric_view:{full_name}",
        {"source": body.get("source_table_full_name")},
    )
    return created


@router.get("/api/metric-views/{full_name}")
async def api_get_metric_view(request: Request, full_name: str) -> dict[str, Any]:
    """Return one metric view by ``catalog.schema.name``."""
    uc = get_uc_client(request)
    return await uc.get_metric_view(full_name)


@router.patch("/api/metric-views/{full_name}")
async def api_update_metric_view(
    request: Request,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Patch a metric view (spec / comment / source / rename)."""
    uc = get_uc_client(request)
    updated = await uc.update_metric_view(full_name, body)
    await audit(
        request,
        "metric_view.updated",
        f"metric_view:{full_name}",
        {"fields": sorted(body)},
    )
    return updated


@router.delete("/api/metric-views/{full_name}")
async def api_delete_metric_view(request: Request, full_name: str) -> dict[str, Any]:
    """Delete a metric view."""
    uc = get_uc_client(request)
    await uc.delete_metric_view(full_name)
    await audit(request, "metric_view.deleted", f"metric_view:{full_name}", None)
    return {"deleted": True}


def _run_metric_sql(
    sql: str,
    approved: dict[str, str],
    max_rows: int,
    policies: dict[str, Any] | None = None,
) -> Any:
    """Execute the compiled SELECT in the sync PQL bridge."""
    from pointlessql.pql import PQL

    return PQL.sql(sql, approved_tables=approved, max_rows=max_rows, table_policies=policies)


@router.post("/api/metric-views/{full_name}/query")
async def api_query_metric_view(
    request: Request,
    full_name: str,
    body: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """Compile and run a governed query against a metric view.

    Args:
        request: Incoming FastAPI request.
        full_name: ``catalog.schema.name`` of the metric view.
        body: ``{"dimensions"?: [names], "measures": [names],
            "where"?: str, "order_by"?: str, "limit"?: int}``.

    Returns:
        ``{"sql", "columns", "rows", "row_count", "truncated",
        "duration_ms"}`` — the compiled SQL ships so the UI can show
        provenance.

    Raises:
        ValidationError: On unknown dimension/measure names or
            malformed fragments.
    """
    uc = get_uc_client(request)
    view = await uc.get_metric_view(full_name)
    spec = cast("dict[str, Any]", view.get("spec") or {})
    source = str(view.get("source_table_full_name") or "")
    dimensions_raw = cast("list[Any]", body.get("dimensions") or [])
    measures_raw = cast("list[Any]", body.get("measures") or [])
    try:
        sql = compile_metric_query(
            source_table=source,
            spec=spec,
            dimensions=[str(d) for d in dimensions_raw],
            measures=[str(m) for m in measures_raw],
            where=body.get("where"),
            order_by=body.get("order_by"),
            limit=body.get("limit"),
        )
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    user = get_user(request)
    approved, policies = await resolve_select_context(
        sql,
        uc_client=request.app.state.uc_client,
        actor_email=user["email"],
        is_admin=bool(user["is_admin"]),
    )
    result = await run_sync(_run_metric_sql, sql, approved, _MAX_ROWS, policies)
    return {
        "sql": sql,
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "duration_ms": result.duration_ms,
    }


@router.get("/metric-views", response_class=HTMLResponse)
async def metric_views_page(request: Request):
    """Render the metric-view browser (catalog/schema picker + editor)."""
    return get_templates(request).TemplateResponse(
        request,
        "pages/metric_views.html",
        {"active_page": "metric-views"},
    )
