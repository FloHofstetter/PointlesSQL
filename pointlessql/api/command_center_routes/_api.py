"""JSON siblings of the command center — summary refresh and compare."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request

from pointlessql.api.command_center_routes._shared import build_command_center, compare_runs

router = APIRouter()


@router.get("/api/command-center/summary")
async def command_center_summary(request: Request) -> dict[str, Any]:
    """Return the cockpit payload for live refresh without a full reload.

    Mirrors the context the HTML page is rendered from, so the in-page
    refresh button can repaint the board against the same shape.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"live", "candidate_groups", "counts"}``.
    """
    return build_command_center(request)


@router.get("/api/command-center/compare")
async def command_center_compare(
    request: Request,
    run_ids: str = Query(default="", description="Comma-separated run ids to compare."),
) -> dict[str, Any]:
    """Return a side-by-side comparison matrix for the selected runs.

    The comma-separated ``run_ids`` mirror the user's selection order;
    blank entries are dropped and unknown ids are skipped so a stale
    selection still yields a partial comparison.

    Args:
        request: Incoming FastAPI request.
        run_ids: Comma-separated run ids from the selection.

    Returns:
        ``{"runs": [...]}`` — one normalized column per resolvable run.
    """
    parsed = [part for part in run_ids.split(",") if part.strip()]
    return compare_runs(request, parsed)
