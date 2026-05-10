"""Run-supervision list views — HTML page + JSON sibling.

A newest-first overview of agent runs with drill-down links into
``/runs/{id}``.  Auth is enforced by app-wide middleware; the
template layers the filter bar and admin-only Approve / Deny column
on top.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse

from pointlessql.api.runs_routes._loaders import load_runs
from pointlessql.api.runs_routes._shared import templates

router = APIRouter()

_RUNS_PAGE_SIZE = 200


def _next_offset(offset: int, page: int, total: int) -> int | None:
    """Return the offset for the next page or ``None`` if exhausted."""
    upcoming = offset + page
    if upcoming >= total:
        return None
    return upcoming


@router.get("/runs", response_class=HTMLResponse)
async def runs_list_page(
    request: Request,
    offset: int = Query(default=0, ge=0),
) -> HTMLResponse:
    """Render the supervision list of agent runs.

    Args:
        request: Incoming FastAPI request.
        offset: Zero-based offset for the page.  HTMX requests with
            ``HX-Request: true`` short-circuit to a fragment template
            (rows + OOB-swap pager) so the Load-More button can
            stream further pages without re-rendering the shell.

    Returns:
        ``pages/runs_list.html`` for full requests, or
        ``pages/_partials/runs_list_append.html`` for HTMX.
    """
    runs, total = load_runs(request, offset=offset, limit=_RUNS_PAGE_SIZE)
    next_offset = _next_offset(offset, _RUNS_PAGE_SIZE, total)
    remaining = max(total - (offset + len(runs)), 0)
    ctx: dict[str, Any] = {
        "runs": runs,
        "total": total,
        "offset": offset,
        "row_limit": _RUNS_PAGE_SIZE,
        "next_offset": next_offset,
        "remaining": remaining,
        "active_page": "runs",
        "active_catalog": None,
        "active_schema": None,
        "active_table": None,
    }
    # Distinguish a Load-More HTMX request (rows + OOB pager) from
    # a hx-boost page nav (wants the full shell so #main-content can
    # be swapped).  Boost sets ``HX-Boosted: true`` in addition to
    # ``HX-Request``; the Load-More button does not.
    is_load_more = (
        request.headers.get("HX-Request") == "true"
        and request.headers.get("HX-Boosted") != "true"
    )
    template = (
        "pages/_partials/runs_list_append.html"
        if is_load_more
        else "pages/runs_list.html"
    )
    return templates(request).TemplateResponse(request, template, ctx)


@router.get("/api/runs")
async def runs_list_api(
    request: Request,
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """JSON sibling of ``GET /runs`` for machine consumers."""
    runs, total = load_runs(request, offset=offset, limit=_RUNS_PAGE_SIZE)
    next_offset = _next_offset(offset, _RUNS_PAGE_SIZE, total)
    return {"runs": runs, "total": total, "next_offset": next_offset}
