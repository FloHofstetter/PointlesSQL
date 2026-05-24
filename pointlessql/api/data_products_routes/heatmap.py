"""Contributor heatmap.

12-month-window GitHub-style calendar of social activity on a DP.
Reads from the existing AuditLog rows whose ``target`` matches
``dp:<catalog>.<schema>`` (the prefix every DP-scoped audit emits).
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.models import AuditLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["data-products", "heatmap"])


@router.get("/api/data-products/{catalog}/{schema}/heatmap")
async def api_dp_heatmap(
    request: Request, catalog: str, schema: str
) -> dict[str, Any]:
    """Return per-day action counts for the last 365 days.

    Args:
        request: Incoming FastAPI request.
        catalog: UC catalog.
        schema: UC schema.

    Returns:
        ``{"total": int, "cells": [{"day": "YYYY-MM-DD", "count": int}, ...]}``
        with a row for every day in the window (zero-fill).
    """
    require_user(request)
    workspace_id = current_workspace_id(request)
    target = f"dp:{catalog}.{schema}"
    today = datetime.datetime.now(datetime.UTC).date()
    cutoff = today - datetime.timedelta(days=364)
    cutoff_dt = datetime.datetime.combine(
        cutoff, datetime.time.min, tzinfo=datetime.UTC
    )

    factory = request.app.state.session_factory
    counts_by_day: dict[str, int] = {}
    with factory() as session:
        # SQLite + PG both expose date() / DATE().  Keep it simple
        # by aggregating in Python — the worst case is ~10⁴ rows.
        rows = list(
            session.scalars(
                select(AuditLog).where(
                    AuditLog.workspace_id == workspace_id,
                    AuditLog.target == target,
                    AuditLog.created_at >= cutoff_dt,
                )
            ).all()
        )
        for r in rows:
            if r.created_at is None:
                continue
            day_key = r.created_at.date().isoformat()
            counts_by_day[day_key] = counts_by_day.get(day_key, 0) + 1
    cells: list[dict[str, Any]] = []
    for offset in range(365):
        day = cutoff + datetime.timedelta(days=offset)
        key = day.isoformat()
        cells.append({"day": key, "count": counts_by_day.get(key, 0)})

    return {"total": sum(c["count"] for c in cells), "cells": cells}
