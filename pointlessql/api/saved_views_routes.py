"""Saved-View REST + HTML routes.

A SavedView is a parameterised, SELECT-only SQL artefact authored
by a tech user and consumed read-only by non-tech users.  Listing
+ run paths are workspace-public; mutation is owner-or-admin.

The run endpoint deliberately bypasses the heavier
``/api/sql/execute`` dispatcher — saved views do not need cancel
tokens, EXPLAIN, or query-history rows.  They go straight to a
short-lived DuckDB connection with positional parameter bindings.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

from fastapi import APIRouter, Body, Query, Request
from fastapi.responses import HTMLResponse, Response

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    current_workspace_id,
    effective_principal,
    get_templates,
    get_user,
    require_user,
)
from pointlessql.api.sql._dispatcher import DispatchContext
from pointlessql.exceptions import (
    CatalogNotFoundError,
    SQLExecutionError,
    ValidationError,
)
from pointlessql.services import saved_views as saved_views_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["views"])


@router.get("/api/views")
async def api_list_views(
    request: Request,
    dp_id: int | None = Query(default=None),
    target_fqn: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
) -> dict[str, Any]:
    """List saved views visible to the caller's workspace.

    Args:
        request: Incoming FastAPI request.
        dp_id: Optional DP scope filter.
        target_fqn: Optional table FQN scope filter.
        include_inactive: Include archived rows when ``True``.

    Returns:
        ``{"views": [...]}``.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    rows = await asyncio.to_thread(
        saved_views_service.list_visible,
        factory,
        workspace_id=workspace_id,
        dp_id=dp_id,
        target_fqn=target_fqn,
        include_inactive=include_inactive,
    )
    return {"views": rows}


@router.post("/api/views")
async def api_create_view(request: Request, body: dict[str, Any] = Body(...)) -> dict[str, Any]:
    """Create a new saved view.

    Propagates :class:`ValidationError` from
    :func:`saved_views_service.create_saved_view` when the SQL is
    not a SELECT or the parameters / placeholders mismatch.

    Args:
        request: Incoming FastAPI request.
        body: ``{title, description, sql, parameters?, dp_id?,
            target_fqn?}``.

    Returns:
        The serialised row.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    payload = body or {}
    row = await asyncio.to_thread(
        saved_views_service.create_saved_view,
        request.app.state.session_factory,
        workspace_id=workspace_id,
        owner_id=int(user["id"]),
        title=str(payload.get("title") or ""),
        description=payload.get("description")
        if isinstance(payload.get("description"), str)
        else None,
        sql_text=str(payload.get("sql_text") or payload.get("sql") or ""),
        parameters=payload.get("parameters"),
        dp_id=payload.get("dp_id") if isinstance(payload.get("dp_id"), int) else None,
        target_fqn=payload.get("target_fqn")
        if isinstance(payload.get("target_fqn"), str)
        else None,
    )
    await audit(request, "view.created", f"saved_view:{row['slug']}", {"title": row["title"]})
    return row


@router.get("/api/views/{slug}")
async def api_get_view(request: Request, slug: str) -> dict[str, Any]:
    """Return a single view by slug.

    Args:
        request: Incoming request.
        slug: The view slug.

    Returns:
        The serialised row.

    Raises:
        CatalogNotFoundError: When the slug is unknown or in
            another workspace.
    """  # noqa: DOC502
    require_user(request)
    workspace_id = current_workspace_id(request)
    row = await asyncio.to_thread(
        saved_views_service.get_by_slug,
        request.app.state.session_factory,
        slug,
        workspace_id=workspace_id,
    )
    if row is None:
        raise CatalogNotFoundError(f"Saved view {slug!r} not found.")
    return row


@router.patch("/api/views/{slug}")
async def api_update_view(
    request: Request, slug: str, body: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    """Partial-update a saved view.

    Args:
        request: Incoming request.
        slug: The view slug.
        body: Partial payload — any of ``title`` / ``description``
            / ``sql`` / ``parameters`` / ``dp_id`` / ``target_fqn``
            / ``is_active``.

    Returns:
        The updated row.

    Raises:
        CatalogNotFoundError: When the slug is unknown or the
            caller is not authorised to mutate.
    """  # noqa: DOC502
    require_user(request)
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    payload = body or {}
    row = await asyncio.to_thread(
        saved_views_service.update_by_slug,
        request.app.state.session_factory,
        slug,
        workspace_id=workspace_id,
        user_id=int(user["id"]),
        is_admin=bool(user.get("is_admin", False)),
        title=payload.get("title") if isinstance(payload.get("title"), str) else None,
        description=payload.get("description")
        if isinstance(payload.get("description"), str)
        else None,
        sql_text=payload.get("sql_text")
        if isinstance(payload.get("sql_text"), str)
        else (payload.get("sql") if isinstance(payload.get("sql"), str) else None),
        parameters=payload.get("parameters")
        if isinstance(payload.get("parameters"), list)
        else None,
        dp_id=payload.get("dp_id") if isinstance(payload.get("dp_id"), int) else None,
        target_fqn=payload.get("target_fqn")
        if isinstance(payload.get("target_fqn"), str)
        else None,
        is_active=bool(payload.get("is_active")) if "is_active" in payload else None,
    )
    if row is None:
        raise CatalogNotFoundError(f"Saved view {slug!r} not found.")
    await audit(request, "view.updated", f"saved_view:{slug}", {"title": row["title"]})
    return row


@router.delete("/api/views/{slug}", status_code=204)
async def api_delete_view(request: Request, slug: str) -> Response:
    """Hard-delete a saved view.

    Args:
        request: Incoming request.
        slug: View slug.

    Returns:
        Empty 204 on success.

    Raises:
        CatalogNotFoundError: When unknown or not authorised.
    """  # noqa: DOC502
    require_user(request)
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    ok = await asyncio.to_thread(
        saved_views_service.delete_by_slug,
        request.app.state.session_factory,
        slug,
        workspace_id=workspace_id,
        user_id=int(user["id"]),
        is_admin=bool(user.get("is_admin", False)),
    )
    if not ok:
        raise CatalogNotFoundError(f"Saved view {slug!r} not found.")
    await audit(request, "view.deleted", f"saved_view:{slug}", None)
    return Response(status_code=204)


@router.post("/api/views/{slug}/run")
async def api_run_view(
    request: Request, slug: str, body: dict[str, Any] = Body(default=None)
) -> dict[str, Any]:
    """Execute a saved view with the supplied parameter values.

    Propagates :class:`SQLExecutionError` from the worker thread
    when DuckDB rejects the rewritten SQL.

    Args:
        request: Incoming request.
        slug: View slug.
        body: ``{"parameters": {name: value, ...}}`` (may be empty).

    Returns:
        ``{"columns": [...], "rows": [...], "row_count": N,
        "truncated": bool, "duration_ms": int}``.

    Raises:
        CatalogNotFoundError: When the slug is unknown or the view
            is archived.
        ValidationError: When the parameters payload is not an
            object (parameter-value coercion failures propagate the
            same exception from the service layer).
    """
    import duckdb

    from pointlessql.pql import prepare_sql
    from pointlessql.pql.engine import register_delta_view

    require_user(request)
    workspace_id = current_workspace_id(request)
    settings = request.app.state.settings
    factory = request.app.state.session_factory
    row = await asyncio.to_thread(
        saved_views_service.get_row,
        factory,
        slug,
        workspace_id=workspace_id,
    )
    if row is None:
        raise CatalogNotFoundError(f"Saved view {slug!r} not found.")
    if not row.is_active:
        raise CatalogNotFoundError(f"Saved view {slug!r} is archived.")
    import json as _json
    from typing import cast as _cast

    parameters = _cast(list[dict[str, Any]], _json.loads(row.parameters_json or "[]"))
    payload = body or {}
    values = payload.get("parameters") or payload.get("values") or {}
    if not isinstance(values, dict):
        raise ValidationError("parameters must be an object.")
    rewritten, binds = saved_views_service.render_sql_with_params(row.sql_text, parameters, values)
    saved_views_service.validate_sql_is_select(rewritten)
    from pointlessql.pql import parse_and_classify

    ast, stype = parse_and_classify(rewritten)
    prepared = prepare_sql(rewritten)
    user = get_user(request)
    actor = effective_principal(request) or user.get("email", "")
    ctx = DispatchContext(
        request=request,
        settings=settings,
        sql=rewritten,
        ast=ast,
        stype=stype,
        actor_email=actor,
        is_admin=bool(user.get("is_admin", False)),
        conn=None,
        max_rows=settings.sql.max_rows,
    )
    # Reuse the SELECT enforcement helper for parity with the editor.
    # Imported from the privilege sub-module instead of a private name
    # on the dispatcher facade so pyright doesn't trip on cross-module
    # private access — the helper is package-internal either way.
    from pointlessql.api.sql._dispatcher._privilege import enforce_select_per_table

    approved = await enforce_select_per_table(ctx, prepared.refs)
    max_rows = max(1, int(settings.sql.max_rows))

    def _run() -> dict[str, Any]:
        from typing import cast as _cast2

        conn = duckdb.connect()
        try:
            for ref in prepared.refs:
                register_delta_view(conn, ref, approved[ref])
            start = time.perf_counter()
            try:
                arrow_raw = conn.execute(prepared.rewritten_sql, binds).to_arrow_table()
            except duckdb.Error as exc:
                raise SQLExecutionError(str(exc)) from exc
            arrow_table = _cast2(Any, arrow_raw)
            duration_ms = int((time.perf_counter() - start) * 1000)
            num_rows: int = int(arrow_table.num_rows)
            truncated = num_rows > max_rows
            if truncated:
                arrow_table = arrow_table.slice(0, max_rows)
                num_rows = max_rows
            column_names = list(arrow_table.column_names)
            return {
                "columns": [
                    {
                        "name": name,
                        "type": str(arrow_table.schema.field(name).type),
                    }
                    for name in column_names
                ],
                "rows": [[r.get(c) for c in column_names] for r in arrow_table.to_pylist()],
                "row_count": num_rows,
                "truncated": truncated,
                "duration_ms": duration_ms,
            }
        finally:
            conn.close()

    result = await asyncio.to_thread(_run)
    # JSON-serialise rows where DuckDB returned native datetime / Decimal.
    serialised_rows: list[list[Any]] = []
    for row_values in result["rows"]:
        serialised_rows.append([_json_safe(v) for v in row_values])
    result["rows"] = serialised_rows
    await audit(
        request,
        "view.executed",
        f"saved_view:{slug}",
        {
            "row_count": result["row_count"],
            "duration_ms": result["duration_ms"],
        },
    )
    return result


def _json_safe(value: Any) -> Any:
    """Coerce DuckDB row values to JSON-serialisable primitives.

    Args:
        value: The raw cell value.

    Returns:
        A primitive (``str`` / ``int`` / ``float`` / ``bool`` /
        ``None``) suitable for ``json.dumps``.
    """
    import datetime as _dt
    import decimal

    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, (_dt.datetime, _dt.date, _dt.time)):
        return value.isoformat()
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (bytes, bytearray)):
        return value.decode("utf-8", errors="replace")
    return str(value)


# -- HTML pages ------------------------------------------------------------


@router.get("/views", response_class=HTMLResponse)
async def page_views_list(request: Request) -> HTMLResponse:
    """List page: every saved view visible to the workspace.

    Args:
        request: Incoming request.

    Returns:
        Rendered HTML.
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    rows = await asyncio.to_thread(
        saved_views_service.list_visible,
        request.app.state.session_factory,
        workspace_id=workspace_id,
    )
    return get_templates(request).TemplateResponse(
        request,
        "pages/saved_views_list.html",
        {
            "views": rows,
            "active_page": "views",
        },
    )


@router.get("/views/new", response_class=HTMLResponse)
async def page_view_new(request: Request) -> HTMLResponse:
    """Editor page for creating a new saved view.

    Args:
        request: Incoming request.

    Returns:
        Rendered HTML.
    """
    require_user(request)
    return get_templates(request).TemplateResponse(
        request,
        "pages/saved_view_new.html",
        {"active_page": "views"},
    )


@router.get("/views/{slug}", response_class=HTMLResponse)
async def page_view_detail(request: Request, slug: str) -> HTMLResponse:
    """Detail / run page for an individual saved view.

    Args:
        request: Incoming request.
        slug: View slug.

    Returns:
        Rendered HTML.

    Raises:
        CatalogNotFoundError: When the slug is unknown in this
            workspace.
    """  # noqa: DOC502
    require_user(request)
    workspace_id = current_workspace_id(request)
    row = await asyncio.to_thread(
        saved_views_service.get_by_slug,
        request.app.state.session_factory,
        slug,
        workspace_id=workspace_id,
    )
    if row is None:
        raise CatalogNotFoundError(f"Saved view {slug!r} not found.")
    return get_templates(request).TemplateResponse(
        request,
        "pages/saved_view_detail.html",
        {
            "view": row,
            "active_page": "views",
            "embed": False,
        },
    )


@router.get("/views/{slug}/embed", response_class=HTMLResponse)
async def page_view_embed(request: Request, slug: str) -> HTMLResponse:
    """Minimal-chrome embed page for ``<iframe src="…">``.

    Args:
        request: Incoming request.
        slug: View slug.

    Returns:
        Rendered HTML without the global navbar / sidebar.

    Raises:
        CatalogNotFoundError: When the slug is unknown in this
            workspace.
    """  # noqa: DOC502
    require_user(request)
    workspace_id = current_workspace_id(request)
    row = await asyncio.to_thread(
        saved_views_service.get_by_slug,
        request.app.state.session_factory,
        slug,
        workspace_id=workspace_id,
    )
    if row is None:
        raise CatalogNotFoundError(f"Saved view {slug!r} not found.")
    return get_templates(request).TemplateResponse(
        request,
        "pages/saved_view_embed.html",
        {
            "view": row,
            "active_page": "views",
            "embed": True,
        },
    )
