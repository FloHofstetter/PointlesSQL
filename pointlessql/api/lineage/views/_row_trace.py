# pyright: reportPrivateUsage=false
"""Row-trace endpoints: JSON ``/api/lineage/row-trace`` + HTML page."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import current_workspace_id, get_templates
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.api.lineage.views._helpers import (
    _MAX_HOPS,
    _apply_pii_masking,
    _attach_cdf_events,
    _attach_value_changes,
    _collect_op_ids,
    _enforce_select,
    _enrich_with_source_file,
    _get_session_factory,
    _load_op_metadata,
    _step_to_dict,
)
from pointlessql.exceptions import ValidationError
from pointlessql.services.lineage_edges import walk_back
from pointlessql.types import TableFqn

router = APIRouter(tags=["lineage"])


@router.get("/api/lineage/row-trace", responses=STANDARD_ERROR_RESPONSES)
async def api_row_trace(
    request: Request,
    table: str = Query(..., description="Three-part UC name"),
    row_id: str = Query(..., description="_lineage_row_id of the row to trace"),
) -> dict[str, Any]:
    """Return the lineage walkback for one row as JSON.

    Args:
        request: FastAPI request (carries the UC client).
        table: Three-part UC name of the row's table.
        row_id: ``_lineage_row_id`` value to trace.

    Returns:
        ``{"table": str, "row_id": str, "steps": [...]}`` where
        ``steps`` is the deterministic walkback (depth-0 is the
        input row itself; subsequent depths are predecessors).
        Empty ``steps`` list when the row exists at the input table
        but has no incoming edge —  callers render this
        as "lineage break".

    Raises:
        ValidationError: 400 when ``row_id`` is empty.
    """
    if not row_id:
        raise ValidationError("row_id is required")
    await _enforce_select(request, table)

    factory = _get_session_factory()
    steps = walk_back(factory, table=table, row_id=row_id, max_hops=_MAX_HOPS)
    steps = await _enrich_with_source_file(request, steps)

    op_meta = _load_op_metadata(_collect_op_ids(steps))
    step_dicts = [_step_to_dict(s, op_meta) for s in steps]
    step_dicts = _attach_value_changes(factory, step_dicts)
    step_dicts = _attach_cdf_events(factory, step_dicts, workspace_id=current_workspace_id(request))
    step_dicts = await _apply_pii_masking(request, step_dicts)
    return {
        "table": table,
        "row_id": row_id,
        "steps": step_dicts,
    }


@router.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}/rows/{row_id}/trace",
    response_class=HTMLResponse,
)
async def html_row_trace(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
    row_id: str,
) -> HTMLResponse:
    """Render the row-trace UI page.

    Args:
        request: FastAPI request.
        catalog_name: Catalog containing the row.
        schema_name: Schema containing the row.
        table_name: Table containing the row.
        row_id: ``_lineage_row_id`` value to trace.

    Returns:
        Rendered ``pages/row_trace.html`` with the steps,
        catalog/schema/table parts (for breadcrumb), and the
        original row id.
    """
    full_name = TableFqn.from_parts(catalog_name, schema_name, table_name)
    await _enforce_select(request, full_name)

    factory = _get_session_factory()
    steps = walk_back(factory, table=full_name, row_id=row_id, max_hops=_MAX_HOPS)
    steps = await _enrich_with_source_file(request, steps)
    op_meta = _load_op_metadata(_collect_op_ids(steps))
    step_dicts = [_step_to_dict(s, op_meta) for s in steps]
    step_dicts = _attach_value_changes(factory, step_dicts)
    step_dicts = _attach_cdf_events(factory, step_dicts, workspace_id=current_workspace_id(request))
    step_dicts = await _apply_pii_masking(request, step_dicts)

    return get_templates(request).TemplateResponse(
        request,
        "pages/row_trace.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "table_name": table_name,
            "full_name": full_name,
            "row_id": row_id,
            "steps": step_dicts,
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": table_name,
        },
    )
