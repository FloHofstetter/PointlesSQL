"""Widget query execution — the data path behind every chart.

Two entry points with one shared core:

* the authenticated path runs as the *viewer* — SELECT enforcement
  applies to whoever is looking at the dashboard;
* the public-token path runs as the *owner* (embedded-credentials
  model) — publishing is the owner's explicit decision to let
  anonymous viewers execute exactly these queries with their
  privileges.

Both substitute dashboard parameters server-side with type-checked
literal escaping before any SQL leaves the process.
"""

from __future__ import annotations

import json
from typing import Any, cast

from fastapi import APIRouter, Body, Request

from pointlessql.api.bi_dashboards_routes._shared import ensure_dashboard
from pointlessql.api.dependencies import get_user
from pointlessql.exceptions import ResourceNotFoundError, ValidationError
from pointlessql.models.auth import User
from pointlessql.models.bi_dashboards import BiDashboard
from pointlessql.services import bi_dashboards as bi_service
from pointlessql.services._executor import run_sync
from pointlessql.services.notebook._sql_cell import resolve_select_context

router = APIRouter()

_ROW_CAPS: dict[str, int] = {"counter": 10, "table": 1_000, "chart": 10_000}
"""Per-kind row caps — a counter never needs more than a handful."""


def _run_widget_sql(
    sql: str,
    approved: dict[str, str],
    max_rows: int,
    policies: dict[str, Any] | None = None,
) -> Any:
    """Execute *sql* in the sync PQL bridge (dispatched via run_sync)."""
    from pointlessql.pql import PQL

    return PQL.sql(sql, approved_tables=approved, max_rows=max_rows, table_policies=policies)


async def _execute_widget(
    request: Request,
    dashboard: BiDashboard,
    widget_id: int,
    *,
    values: dict[str, Any],
    actor_email: str,
    is_admin: bool,
) -> dict[str, Any]:
    """Run one widget's query and frame the JSON payload.

    Args:
        request: Incoming FastAPI request (for app state).
        dashboard: The widget's dashboard.
        widget_id: Widget primary key.
        values: Caller-supplied parameter values.
        actor_email: Principal for SELECT enforcement.
        is_admin: Whether that principal short-circuits privilege
            checks.

    Returns:
        ``{"columns", "rows", "row_count", "truncated",
        "duration_ms"}``.

    Raises:
        ResourceNotFoundError: When the widget is not on this
            dashboard.
        ValidationError: When the widget has no SQL bound or a
            parameter fails validation.
    """
    factory = request.app.state.session_factory
    widget = bi_service.get_widget(factory, dashboard_id=dashboard.id, widget_id=widget_id)
    if widget is None:
        raise ResourceNotFoundError(f"Widget {widget_id} not found on '{dashboard.slug}'.")
    sql = bi_service.resolve_widget_sql(factory, widget=widget)
    if sql is None:
        raise ValidationError("widget has no SQL bound")
    specs = json.loads(dashboard.params or "[]")
    try:
        sql = bi_service.substitute_params(sql, specs=specs, values=values)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    approved, policies = await resolve_select_context(
        sql,
        uc_client=request.app.state.uc_client,
        actor_email=actor_email,
        is_admin=is_admin,
    )
    max_rows = _ROW_CAPS.get(widget.kind, 1_000)
    result = await run_sync(_run_widget_sql, sql, approved, max_rows, policies)
    return {
        "columns": result.columns,
        "rows": result.rows,
        "row_count": result.row_count,
        "truncated": result.truncated,
        "duration_ms": result.duration_ms,
    }


def _coerce_values(body: dict[str, Any]) -> dict[str, Any]:
    """Pull the parameter-value map out of the request body."""
    values = body.get("params")
    return cast("dict[str, Any]", values) if isinstance(values, dict) else {}


@router.post("/api/bi/dashboards/{slug}/widgets/{widget_id}/data")
async def api_widget_data(
    request: Request,
    slug: str,
    widget_id: int,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Run a widget query as the authenticated viewer.

    Args:
        request: Incoming FastAPI request.
        slug: Dashboard slug.
        widget_id: Widget primary key.
        body: ``{"params"?: {<name>: <value>}}``.

    Returns:
        The framed result payload.
    """
    dashboard = ensure_dashboard(request, slug)
    user = get_user(request)
    return await _execute_widget(
        request,
        dashboard,
        widget_id,
        values=_coerce_values(body),
        actor_email=user["email"],
        is_admin=bool(user["is_admin"]),
    )


@router.post("/api/bi/public/{token}/widgets/{widget_id}/data")
async def api_public_widget_data(
    request: Request,
    token: str,
    widget_id: int,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Run a widget query on a published dashboard (token = credential).

    Executes as the dashboard owner — the embedded-credentials model
    every published BI dashboard implies.  Unknown / revoked tokens
    answer 404.

    Args:
        request: Incoming FastAPI request.
        token: Public-share token from the URL.
        widget_id: Widget primary key.
        body: ``{"params"?: {<name>: <value>}}``.

    Returns:
        The framed result payload.

    Raises:
        ResourceNotFoundError: For unknown tokens or when the owner
            account no longer exists.
    """
    factory = request.app.state.session_factory
    dashboard = bi_service.get_dashboard_by_token(factory, token=token)
    if dashboard is None:
        raise ResourceNotFoundError("Published dashboard not found.")
    with factory() as session:
        owner = session.get(User, dashboard.owner_id)
        if owner is None:
            raise ResourceNotFoundError("Published dashboard owner no longer exists.")
        owner_email = owner.email
        owner_is_admin = bool(owner.is_admin)
    return await _execute_widget(
        request,
        dashboard,
        widget_id,
        values=_coerce_values(body),
        actor_email=owner_email,
        is_admin=owner_is_admin,
    )
