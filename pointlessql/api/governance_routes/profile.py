"""Table-stats endpoints: profile, get stats, delete stats."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import Response

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import (
    require_admin,
)
from pointlessql.api.governance_routes._helpers import (
    enforce_table_profile_access,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["governance"])


@router.post("/api/tables/{full_name:path}/profile")
async def api_profile_table(
    request: Request,
    full_name: str,
) -> dict[str, Any]:
    """Compute + cache per-column statistics for the Delta table.

    The caller must hold SELECT on the table or be an administrator.
    Results are cached by ``(full_name, delta_log_version)`` so a
    second call at the same Delta version is a single index seek.

    Args:
        request: Incoming request.
        full_name: UC three-part dotted name (path-encoded).

    Returns:
        Dict with ``full_name``, ``delta_log_version``, and a
        ``columns`` list of serialised stats rows.

    Raises:
        CatalogNotFoundError: On missing table or missing storage.
        AuthorizationError: When the caller lacks SELECT.
    """  # noqa: DOC502,DOC503 — raised via helpers
    from pointlessql.services import table_stats as ts_service

    table_info = await enforce_table_profile_access(request, full_name)
    storage_location = str(table_info.get("storage_location") or "")
    raw_columns = cast(list[dict[str, Any]], table_info.get("columns") or [])
    columns = [
        {"name": str(c.get("name") or ""), "type": str(c.get("type_text") or "")}
        for c in raw_columns
        if c.get("name")
    ]
    factory = getattr(request.app.state, "session_factory", None)

    # Short-circuit: if the current version is already cached we
    # still surface it but do not recompute.
    current_version = await asyncio.to_thread(
        ts_service.read_delta_log_version,
        storage_location,
    )
    if factory is not None:
        cached = await asyncio.to_thread(
            ts_service.read_cached,
            factory,
            full_name=full_name,
            delta_log_version=current_version,
        )
        if cached is not None:
            await audit(
                request,
                "table.profile_cache_hit",
                f"table:{full_name}",
                {"delta_log_version": current_version},
            )
            return {
                "full_name": full_name,
                "delta_log_version": current_version,
                "cached": True,
                "columns": cached,
            }

    stats = await asyncio.to_thread(
        ts_service.compute_stats,
        full_name,
        storage_location,
        columns,
    )
    if factory is not None:
        await asyncio.to_thread(
            ts_service.write_cached,
            factory,
            full_name=full_name,
            delta_log_version=current_version,
            stats=stats,
        )
    await audit(
        request,
        "table.profiled",
        f"table:{full_name}",
        {
            "delta_log_version": current_version,
            "column_count": len(stats),
        },
    )
    serialised = [
        {
            "column_name": col_name,
            "delta_log_version": current_version,
            "computed_at": datetime.now(UTC).isoformat(),
            "stats": stats_dict,
        }
        for col_name, stats_dict in stats.items()
    ]
    return {
        "full_name": full_name,
        "delta_log_version": current_version,
        "cached": False,
        "columns": serialised,
    }


@router.get("/api/tables/{full_name:path}/stats")
async def api_get_table_stats(
    request: Request,
    full_name: str,
    version: int | None = None,
) -> dict[str, Any]:
    """Return cached stats for a UC table, optionally pinned to a version.

    Args:
        request: Incoming request.
        full_name: UC three-part dotted name.
        version: Optional Delta log version; defaults to the latest
            cached version for this table.

    Returns:
        Dict with ``full_name``, ``delta_log_version``, and
        ``columns`` (empty list if nothing is cached yet).

    Raises:
        CatalogNotFoundError: On missing table or missing storage.
        AuthorizationError: When the caller lacks SELECT.
    """  # noqa: DOC502,DOC503 — raised via helpers
    from pointlessql.services import table_stats as ts_service

    await enforce_table_profile_access(request, full_name)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return {"full_name": full_name, "delta_log_version": None, "columns": []}
    cached = await asyncio.to_thread(
        ts_service.read_cached,
        factory,
        full_name=full_name,
        delta_log_version=version,
    )
    if cached is None:
        return {"full_name": full_name, "delta_log_version": version, "columns": []}
    latest_version = max(row["delta_log_version"] for row in cached)
    return {
        "full_name": full_name,
        "delta_log_version": version if version is not None else latest_version,
        "columns": cached,
    }


@router.delete(
    "/api/tables/{full_name:path}/stats",
    status_code=204,
)
async def api_delete_table_stats(
    request: Request,
    full_name: str,
) -> Response:
    """Evict every cached statistics row for *full_name* (admin only).

    Args:
        request: Incoming request.
        full_name: UC three-part name.

    Returns:
        Empty 204.
    """
    from pointlessql.services import table_stats as ts_service

    require_admin(request)
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return Response(status_code=204)
    removed = await asyncio.to_thread(
        ts_service.delete_cached,
        factory,
        full_name,
    )
    await audit(
        request,
        "table.stats_cleared",
        f"table:{full_name}",
        {"rows_removed": removed},
    )
    return Response(status_code=204)
