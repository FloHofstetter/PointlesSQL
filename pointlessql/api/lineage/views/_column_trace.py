# pyright: reportPrivateUsage=false
"""Column-trace endpoints: JSON ``/api/lineage/column-trace`` + HTML page."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.dependencies import get_templates
from pointlessql.api.error_responses import STANDARD_ERROR_RESPONSES
from pointlessql.api.lineage.views._helpers import (
    _MAX_HOPS,
    _enforce_select,
    _get_session_factory,
    _load_op_metadata,
)
from pointlessql.exceptions import ValidationError
from pointlessql.services.lineage_edges import (
    ColumnPredecessorRef,
    ColumnTraceStep,
    walk_back_columns,
)
from pointlessql.types import TableFqn

router = APIRouter(tags=["lineage"])


def _column_predecessor_to_dict(
    pred: ColumnPredecessorRef, op_meta: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """Project a :class:`ColumnPredecessorRef` into the JSON payload shape.

    Args:
        pred: One predecessor edge feeding a column-trace step.
        op_meta: Op metadata joined off ``agent_run_operations``.

    Returns:
        Dict with ``table`` / ``column`` / ``op_id`` / ``op_name`` /
        ``run_id`` / ``transform_kind`` / ``transform_detail`` keys.
    """
    meta = op_meta.get(pred.op_id) if pred.op_id is not None else None
    return {
        "table": pred.table,
        "column": pred.column,
        "op_id": pred.op_id,
        "op_name": meta.get("op_name") if meta else None,
        "run_id": pred.run_id,
        "transform_kind": pred.transform_kind,
        "transform_detail": pred.transform_detail,
    }


def _column_step_to_dict(
    step: ColumnTraceStep, op_meta: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """Project a :class:`ColumnTraceStep` into the JSON payload shape.

    Args:
        step: One column-trace walkback step.
        op_meta: Op metadata joined off ``agent_run_operations``.

    Returns:
        Dict with ``depth`` / ``table`` / ``column`` / ``op_id`` /
        ``op_name`` / ``run_id`` / ``predecessors`` keys.
        ``predecessors`` length > 1 indicates fan-in (multiple
        source columns feeding one target column in a single op).
    """
    meta = op_meta.get(step.op_id) if step.op_id is not None else None
    return {
        "depth": step.depth,
        "table": step.table,
        "column": step.column,
        "op_id": step.op_id,
        "op_name": meta.get("op_name") if meta else None,
        "run_id": step.run_id,
        "predecessors": [_column_predecessor_to_dict(p, op_meta) for p in step.predecessors],
    }


def _collect_column_op_ids(steps: list[ColumnTraceStep]) -> set[int]:
    """Collect every ``op_id`` referenced by *steps* or their predecessors.

    Args:
        steps: Walkback result.

    Returns:
        Set of op IDs to look up in ``agent_run_operations``.
    """
    ids: set[int] = set()
    for step in steps:
        if step.op_id is not None:
            ids.add(step.op_id)
        for pred in step.predecessors:
            if pred.op_id is not None:
                ids.add(pred.op_id)
    return ids


@router.get("/api/lineage/column-trace", responses=STANDARD_ERROR_RESPONSES)
async def api_column_trace(
    request: Request,
    table: str = Query(..., description="Three-part UC name"),
    column: str = Query(..., description="Column name to trace"),
) -> dict[str, Any]:
    """Return the column-lineage walkback for one column as JSON.

    sibling to :func:`api_row_trace`.  Each step
    lists every predecessor edge that fed the current
    ``(table, column)`` pair, classified by ``transform_kind``.

    Args:
        request: FastAPI request.
        table: Three-part UC name of the column's table.
        column: Column name to trace.

    Returns:
        ``{"table", "column", "steps": [...]}``.

    Raises:
        ValidationError: 400 when ``column`` is empty.
    """
    if not column:
        raise ValidationError("column is required")
    await _enforce_select(request, table)

    factory = _get_session_factory()
    steps = walk_back_columns(factory, table=table, column=column, max_hops=_MAX_HOPS)
    op_meta = _load_op_metadata(_collect_column_op_ids(steps))
    return {
        "table": table,
        "column": column,
        "steps": [_column_step_to_dict(s, op_meta) for s in steps],
    }


@router.get(
    "/catalogs/{catalog_name}/schemas/{schema_name}/tables/{table_name}"
    "/columns/{column_name}/trace",
    response_class=HTMLResponse,
)
async def html_column_trace(
    request: Request,
    catalog_name: str,
    schema_name: str,
    table_name: str,
    column_name: str,
) -> HTMLResponse:
    """Render the column-trace UI page.

    Args:
        request: FastAPI request.
        catalog_name: Catalog containing the column's table.
        schema_name: Schema containing the column's table.
        table_name: Table containing the column.
        column_name: Column name to trace.

    Returns:
        Rendered ``pages/column_trace.html`` with the steps,
        catalog/schema/table parts (for breadcrumb), and the
        column name.
    """
    full_name = TableFqn.from_parts(catalog_name, schema_name, table_name)
    await _enforce_select(request, full_name)

    factory = _get_session_factory()
    steps = walk_back_columns(factory, table=full_name, column=column_name, max_hops=_MAX_HOPS)
    op_meta = _load_op_metadata(_collect_column_op_ids(steps))

    return get_templates(request).TemplateResponse(
        request,
        "pages/column_trace.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "table_name": table_name,
            "full_name": full_name,
            "column_name": column_name,
            "steps": [_column_step_to_dict(s, op_meta) for s in steps],
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": table_name,
        },
    )
