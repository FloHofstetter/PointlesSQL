"""Excel add-in bridge — manifest, OData discovery, and metric feeds.

A thin external-client adapter so the Microsoft Excel add-in can pull
governed metric views into a worksheet without a per-user ODBC driver.
Reads route through the same grant-enforced metric-query path as the
in-app surface; this module only adds the Office.js manifest, an OData
service document, and the OData-v4 envelope Excel consumes.
"""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Query, Request
from fastapi.responses import Response

from pointlessql.api.dependencies import get_uc_client, get_user
from pointlessql.exceptions import ValidationError
from pointlessql.pql._metrics import compile_metric_query
from pointlessql.services import excel_bridge
from pointlessql.services._executor import run_sync
from pointlessql.services.notebook._sql_cell import resolve_select_context

router = APIRouter(tags=["excel-bridge"])

_MAX_ROWS = 50_000


def _run_metric_sql(sql: str, approved: dict[str, str], policies: dict[str, Any] | None) -> Any:
    """Execute a compiled metric SELECT in the sync PQL bridge."""
    from pointlessql.pql import PQL

    return PQL.sql(sql, approved_tables=approved, max_rows=_MAX_ROWS, table_policies=policies)


def _spec_names(spec: dict[str, Any], key: str) -> list[str]:
    """Pull the named members (dimensions / measures) from a metric spec."""
    names: list[str] = []
    for item in cast("list[Any]", spec.get(key) or []):
        if isinstance(item, dict):
            name = cast("dict[str, Any]", item).get("name")
            if name:
                names.append(str(name))
        elif isinstance(item, str):
            names.append(item)
    return names


@router.get("/api/excel/manifest.xml", response_class=Response)
async def excel_manifest(request: Request) -> Response:
    """Return the Office.js add-in manifest pointing Excel at this server.

    Args:
        request: Incoming FastAPI request (for the base URL).

    Returns:
        An ``application/xml`` Office Add-in manifest.
    """
    base_url = str(request.base_url).rstrip("/")
    return Response(
        content=excel_bridge.office_manifest(base_url=base_url), media_type="application/xml"
    )


@router.get("/api/excel/odata")
async def excel_odata_service(
    request: Request,
    catalog: str | None = Query(default=None),
    schema: str | None = Query(default=None),
) -> dict[str, Any]:
    """Return the OData service document of pullable metric views.

    Args:
        request: Incoming FastAPI request.
        catalog: Catalog to list metric views from; ``None`` returns an
            empty (but valid) service document.
        schema: Schema within the catalog.

    Returns:
        The service document from
        :func:`excel_bridge.odata_service_document`.
    """
    base_url = str(request.base_url).rstrip("/") + "/api/excel/odata"
    entity_sets: list[str] = []
    if catalog and catalog.strip() and schema and schema.strip():
        uc = get_uc_client(request)
        views = await uc.list_metric_views(catalog.strip(), schema.strip())
        entity_sets = [str(view.get("full_name") or view.get("name") or "") for view in views]
    return excel_bridge.odata_service_document(base_url, [name for name in entity_sets if name])


@router.get("/api/excel/odata/metric/{full_name}")
async def excel_metric_feed(
    request: Request,
    full_name: str,
    dimensions: str | None = Query(default=None, description="Comma-separated dimension names"),
    measures: str | None = Query(default=None, description="Comma-separated measure names"),
) -> dict[str, Any]:
    """Deliver a governed metric view as an OData feed Excel can read.

    The metric query compiles + runs through the same grant-enforced path
    as the in-app metric surface; the result is wrapped in an OData-v4
    envelope.  Omitting ``dimensions`` / ``measures`` pulls every member
    the view declares.

    Args:
        request: Incoming FastAPI request.
        full_name: ``catalog.schema.name`` of the metric view.
        dimensions: Comma-separated dimension names; defaults to all.
        measures: Comma-separated measure names; defaults to all.

    Returns:
        The OData feed from :func:`excel_bridge.to_odata_feed`.

    Raises:
        ValidationError: If the requested members do not compile into a
            valid metric query.
    """
    uc = get_uc_client(request)
    view = await uc.get_metric_view(full_name)
    spec = cast("dict[str, Any]", view.get("spec") or {})
    source = str(view.get("source_table_full_name") or "")
    dims = _split(dimensions) if dimensions is not None else _spec_names(spec, "dimensions")
    meas = _split(measures) if measures is not None else _spec_names(spec, "measures")
    try:
        sql = compile_metric_query(source_table=source, spec=spec, dimensions=dims, measures=meas)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    user = get_user(request)
    approved, policies = await resolve_select_context(
        sql,
        uc_client=request.app.state.uc_client,
        actor_email=user["email"],
        is_admin=bool(user["is_admin"]),
    )
    result = await run_sync(_run_metric_sql, sql, approved, policies)
    return excel_bridge.to_odata_feed(full_name, result.columns, result.rows)


def _split(value: str) -> list[str]:
    """Split a comma-separated query value into trimmed non-empty names."""
    return [part.strip() for part in value.split(",") if part.strip()]
