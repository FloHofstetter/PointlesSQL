"""Per-row lineage trace routes (Sprint 15.4).

Sprint 15.3 fills ``lineage_row_edges`` from every PQL merge / write
that carried ``_lineage_row_id``.  This module exposes:

* ``GET /api/lineage/row-trace?table=&row_id=`` — JSON walkback to
  the bronze root, with the originating ``_source_file`` stamped on
  the deepest step when the bronze table can be opened.
* ``GET /tables/{full_name}/rows/{row_id}/trace`` — HTML page that
  renders the same walkback as a Bootstrap list-group for human
  reviewers.

Both endpoints require the same SELECT privilege on the *input*
table that the table-detail page does — the trace doesn't reveal
data values, but it does reveal the existence of a row in a
specific bronze file.

Operation-level details (`op_name`, principal) are joined off the
referenced ``agent_run_operations`` row so each step in the trace
also names the run + primitive that produced it.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select

from pointlessql.api.dependencies import (
    effective_principal,
    get_uc_client,
    get_user,
)
from pointlessql.exceptions import CatalogNotFoundError, CatalogUnavailableError
from pointlessql.models import AgentRunOperation
from pointlessql.services.authorization import SELECT, check_privilege
from pointlessql.services.lineage_edges import (
    ColumnPredecessorRef,
    ColumnTraceStep,
    LineageStep,
    PredecessorRef,
    lookup_bronze_source_file,
    walk_back,
    walk_back_columns,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["lineage"])

_MAX_HOPS = 20


def _templates(request: Request) -> Jinja2Templates:
    """Pull the shared Jinja environment off the FastAPI app state."""
    return request.app.state.templates


def _get_session_factory() -> Any:
    """Return the global SQLAlchemy session factory.

    Wrapped in a helper so the route bodies stay readable and so
    tests can patch the lookup without monkey-patching the dotted
    path inside two separate handlers.
    """
    from pointlessql.db import get_session_factory

    return get_session_factory()


async def _enforce_select(request: Request, full_name: str) -> None:
    """Reject the request when the caller lacks SELECT on *full_name*.

    Args:
        request: Incoming FastAPI request.
        full_name: Three-part UC name to authorise against.
    """  # noqa: DOC502 — propagates AuthorizationError from check_privilege
    client = get_uc_client(request)
    user = get_user(request)
    principal = effective_principal(request) or user.get("email", "")
    await check_privilege(
        client,
        principal,
        user.get("is_admin", False),
        "table",
        full_name,
        SELECT,
    )


def _predecessor_to_dict(
    pred: PredecessorRef, op_meta: dict[int, dict[str, Any]]
) -> dict[str, Any]:
    """Project a :class:`PredecessorRef` into the JSON payload shape.

    Args:
        pred: One predecessor edge feeding a step.
        op_meta: Joined op metadata; see :func:`_step_to_dict`.

    Returns:
        Dict with ``table`` / ``row_id`` / ``op_id`` / ``op_name`` /
        ``run_id`` keys.  ``op_name`` is ``None`` when the join row
        is missing (deleted run, FK orphan).
    """
    meta = op_meta.get(pred.op_id)
    return {
        "table": pred.table,
        "row_id": pred.row_id,
        "op_id": pred.op_id,
        "op_name": meta.get("op_name") if meta else None,
        "run_id": pred.run_id,
    }


def _step_to_dict(step: LineageStep, op_meta: dict[int, dict[str, Any]]) -> dict[str, Any]:
    """Project a :class:`LineageStep` into the JSON payload shape.

    Args:
        step: One walkback step.
        op_meta: ``{op_id: {"op_name": str, "agent_run_id": str |
            None}}`` joined off ``agent_run_operations`` for every
            distinct ``op_id`` referenced by the steps **or** by
            their predecessors.

    Returns:
        Dict with ``depth`` / ``table`` / ``row_id`` / ``op_id`` /
        ``op_name`` / ``run_id`` / ``source_file`` /
        ``predecessors`` keys.  ``predecessors`` is the full list of
        edges feeding this row — length > 1 indicates fan-in
        (aggregate op or repeated re-runs).
    """
    meta = op_meta.get(step.op_id) if step.op_id is not None else None
    return {
        "depth": step.depth,
        "table": step.table,
        "row_id": step.row_id,
        "op_id": step.op_id,
        "op_name": meta.get("op_name") if meta else None,
        "run_id": step.run_id,
        "source_file": step.source_file,
        "predecessors": [_predecessor_to_dict(p, op_meta) for p in step.predecessors],
    }


async def _enrich_with_source_file(request: Request, steps: list[LineageStep]) -> list[LineageStep]:
    """Stamp ``source_file`` onto the deepest step from the bronze table.

    Looks the storage location up via the soyuz UC client, then
    probes the Delta table with DuckDB.  Anything that goes wrong
    (table missing, column dropped, library import failure) leaves
    the step unchanged — the trace is still useful without the
    file label.

    Args:
        request: Incoming FastAPI request (for the UC client).
        steps: Walkback steps as returned by
            :func:`pointlessql.services.lineage_edges.walk_back`.

    Returns:
        A new list with the deepest step replaced by an enriched
        copy when the lookup succeeded; otherwise the original
        list, identity-preserving.
    """
    if not steps:
        return steps
    deepest = steps[-1]
    if deepest.source_file is not None:
        return steps

    parts = deepest.table.split(".")
    if len(parts) != 3:
        return steps

    client = get_uc_client(request)
    try:
        info = await client.get_table(parts[0], parts[1], parts[2])
    except CatalogNotFoundError, CatalogUnavailableError:
        return steps
    except Exception:  # noqa: BLE001 — best-effort enrichment
        logger.debug("row-trace: failed to resolve storage_location for %s", deepest.table)
        return steps

    storage_location = info.get("storage_location") if info else None
    if not isinstance(storage_location, str) or not storage_location:
        return steps

    source_file = lookup_bronze_source_file(
        table=deepest.table,
        row_id=deepest.row_id,
        storage_location=storage_location,
    )
    if source_file is None:
        return steps

    enriched = LineageStep(
        depth=deepest.depth,
        table=deepest.table,
        row_id=deepest.row_id,
        op_id=deepest.op_id,
        run_id=deepest.run_id,
        source_file=source_file,
        predecessors=deepest.predecessors,
    )
    return [*steps[:-1], enriched]


def _collect_op_ids(steps: list[LineageStep]) -> set[int]:
    """Collect every ``op_id`` referenced by *steps* or their predecessors.

    Args:
        steps: Walkback result from
            :func:`pointlessql.services.lineage_edges.walk_back`.

    Returns:
        Set of op IDs to look up in ``agent_run_operations`` so the
        JSON / HTML response can label every edge with its op_name.
    """
    ids: set[int] = set()
    for step in steps:
        if step.op_id is not None:
            ids.add(step.op_id)
        for pred in step.predecessors:
            ids.add(pred.op_id)
    return ids


def _load_op_metadata(op_ids: set[int]) -> dict[int, dict[str, Any]]:
    """Fetch ``op_name`` / ``principal`` for every referenced op.

    Args:
        op_ids: Operation IDs collected from the walkback steps.

    Returns:
        ``{op_id: {"op_name": str, "principal": str | None}}``.
        Missing ops (deleted runs, FK orphans) are absent from the
        result; the caller renders a "—" in their place.
    """
    if not op_ids:
        return {}
    factory = _get_session_factory()
    with factory() as session:
        stmt = select(
            AgentRunOperation.id,
            AgentRunOperation.op_name,
            AgentRunOperation.agent_run_id,
        ).where(AgentRunOperation.id.in_(op_ids))
        result: dict[int, dict[str, Any]] = {}
        for row in session.execute(stmt).all():
            result[int(row[0])] = {"op_name": row[1], "agent_run_id": row[2]}
        return result


@router.get("/api/lineage/row-trace")
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
        but has no incoming edge — Sprint-15.4 callers render this
        as "lineage break".

    Raises:
        HTTPException: 400 when ``row_id`` is empty.
    """
    if not row_id:
        raise HTTPException(status_code=400, detail="row_id is required")
    await _enforce_select(request, table)

    factory = _get_session_factory()
    steps = walk_back(factory, table=table, row_id=row_id, max_hops=_MAX_HOPS)
    steps = await _enrich_with_source_file(request, steps)

    op_meta = _load_op_metadata(_collect_op_ids(steps))
    return {
        "table": table,
        "row_id": row_id,
        "steps": [_step_to_dict(s, op_meta) for s in steps],
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
    full_name = f"{catalog_name}.{schema_name}.{table_name}"
    await _enforce_select(request, full_name)

    factory = _get_session_factory()
    steps = walk_back(factory, table=full_name, row_id=row_id, max_hops=_MAX_HOPS)
    steps = await _enrich_with_source_file(request, steps)
    op_meta = _load_op_metadata(_collect_op_ids(steps))

    return _templates(request).TemplateResponse(
        request,
        "pages/row_trace.html",
        {
            "catalog_name": catalog_name,
            "schema_name": schema_name,
            "table_name": table_name,
            "full_name": full_name,
            "row_id": row_id,
            "steps": [_step_to_dict(s, op_meta) for s in steps],
            "active_catalog": catalog_name,
            "active_schema": schema_name,
            "active_table": table_name,
        },
    )


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
    meta = op_meta.get(pred.op_id)
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
            ids.add(pred.op_id)
    return ids


@router.get("/api/lineage/column-trace")
async def api_column_trace(
    request: Request,
    table: str = Query(..., description="Three-part UC name"),
    column: str = Query(..., description="Column name to trace"),
) -> dict[str, Any]:
    """Return the column-lineage walkback for one column as JSON.

    Sprint 15.6.4 — sibling to :func:`api_row_trace`.  Each step
    lists every predecessor edge that fed the current
    ``(table, column)`` pair, classified by ``transform_kind``.

    Args:
        request: FastAPI request.
        table: Three-part UC name of the column's table.
        column: Column name to trace.

    Returns:
        ``{"table", "column", "steps": [...]}``.

    Raises:
        HTTPException: 400 when ``column`` is empty.
    """
    if not column:
        raise HTTPException(status_code=400, detail="column is required")
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
    full_name = f"{catalog_name}.{schema_name}.{table_name}"
    await _enforce_select(request, full_name)

    factory = _get_session_factory()
    steps = walk_back_columns(factory, table=full_name, column=column_name, max_hops=_MAX_HOPS)
    op_meta = _load_op_metadata(_collect_column_op_ids(steps))

    return _templates(request).TemplateResponse(
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
