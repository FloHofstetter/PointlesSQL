"""operator diagnostics for the cross-worker co-edit bus.

Exposes ``GET /api/admin/coedit-bus/status`` returning a JSON snapshot
of the bound :class:`CoeditBus` (listener health, cleanup task health,
inflight outbox rows).  Helps an operator confirm that a fresh
multi-worker deployment is actually exchanging frames over PG.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import require_admin

router = APIRouter(tags=["admin", "coedit-bus"])


@router.get("/api/admin/coedit-bus/status")
async def api_admin_coedit_bus_status(request: Request) -> dict[str, Any]:
    """Return a JSON snapshot of the bus subsystem.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"enabled": bool, ...}`` where ``enabled`` is ``False`` on
        single-worker / SQLite installs.  When ``True``, the payload
        also carries ``own_pid``, ``ttl_seconds``,
        ``cleanup_interval_seconds``, ``listener_alive``,
        ``listener_ready``, ``cleanup_alive``, and
        ``inflight_outbox_rows``.
    """
    require_admin(request)
    bus = getattr(request.app.state, "coedit_bus", None)
    if bus is None:
        return {"enabled": False}
    snapshot = bus.status_snapshot()
    snapshot["enabled"] = True
    return snapshot
