"""Admin surface for the external-write (unattributed Delta) scanner.

Owns the four routes that drive 's detection-only flow:

* ``GET /admin/external-writes`` (HTML) — list view with table-FQN
  substring filter and an "unacknowledged only" toggle.
* ``GET /api/admin/external-writes`` — JSON variant of the same.
* ``POST /api/admin/external-writes/scan`` — on-demand scan trigger
  (the periodic background loop in ``main.py`` is opt-in via
  ``POINTLESSQL_EXTERNAL_WRITES_SCAN_INTERVAL_SECONDS``).
* ``POST /api/admin/external-writes/{id}/acknowledge`` — mark one
  unattributed-write row as reviewed.

All four are admin-gated.  See
``project_full_autonomous_audit_critical_path.md`` for why this
sits at "detection only" and not "hard-block".
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import get_templates, get_user, require_admin
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.services import external_write_scanner
from pointlessql.services._executor import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin", "external-writes"])


@router.get("/admin/external-writes", response_class=HTMLResponse)
async def admin_external_writes_index(
    request: Request,
    table_fqn_like: str | None = None,
    only_unacknowledged: bool = True,
) -> HTMLResponse:
    """Render the unattributed-writes admin page.

    Args:
        request: Incoming FastAPI request.
        table_fqn_like: Optional substring filter on ``table_fqn``.
        only_unacknowledged: Toggle for the unacknowledged-only
            view (default ``True`` — that's the queue admins
            actually need to work on).

    Returns:
        The rendered HTML page.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    cleaned_like = (
        table_fqn_like.strip()
        if isinstance(table_fqn_like, str) and table_fqn_like.strip()
        else None
    )
    entries = await run_sync(
        external_write_scanner.list_unattributed,
        factory,
        only_unacknowledged=only_unacknowledged,
        table_fqn_like=cleaned_like,
        limit=500,
    )
    unacknowledged_total = await run_sync(external_write_scanner.count_unacknowledged, factory)
    return get_templates(request).TemplateResponse(
        request,
        "pages/admin_external_writes.html",
        {
            "entries": entries,
            "table_fqn_like": cleaned_like or "",
            "only_unacknowledged": only_unacknowledged,
            "unacknowledged_total": unacknowledged_total,
            "active_page": "admin",
            "active_catalog": None,
            "active_schema": None,
            "active_table": None,
        },
    )


@router.get("/api/admin/external-writes")
async def api_list_external_writes(
    request: Request,
    table_fqn_like: str | None = None,
    only_unacknowledged: bool = False,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return ``unattributed_writes`` rows as JSON.

    Args:
        request: Incoming FastAPI request.
        table_fqn_like: Optional substring filter.
        only_unacknowledged: Filter to rows whose ``acknowledged_at``
            is ``NULL``.
        limit: Hard row cap.

    Returns:
        List of dicts — see
        :func:`pointlessql.services.external_write_scanner.list_unattributed`.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    cleaned_like = (
        table_fqn_like.strip()
        if isinstance(table_fqn_like, str) and table_fqn_like.strip()
        else None
    )
    effective_limit = max(1, min(int(limit), 1000))
    return await run_sync(
        external_write_scanner.list_unattributed,
        factory,
        only_unacknowledged=only_unacknowledged,
        table_fqn_like=cleaned_like,
        limit=effective_limit,
    )


@router.post("/api/admin/external-writes/scan")
async def api_trigger_scan(request: Request) -> dict[str, int]:
    """Trigger an on-demand scan of every UC table.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``{"inserted": N}`` where N is the number of new
        ``unattributed_writes`` rows persisted.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    uc = request.app.state.uc_client
    settings = request.app.state.settings
    inserted = await external_write_scanner.scan_all(
        factory, uc, history_limit=settings.external_writes.history_limit
    )
    await audit(
        request,
        "external_writes.scanned",
        "external_writes:on_demand",
        {"inserted": inserted},
    )
    return {"inserted": inserted}


@router.post("/api/admin/external-writes/{write_id}/acknowledge")
async def api_acknowledge_external_write(
    request: Request,
    write_id: int,
) -> dict[str, Any]:
    """Mark one ``unattributed_writes`` row as reviewed.

    Args:
        request: Incoming FastAPI request.
        write_id: Primary key of the row to acknowledge.

    Returns:
        ``{"id": N, "acknowledged_by": "..."}`` on success.

    Raises:
        CatalogNotFoundError: If no row with that id exists.
    """  # noqa: DOC502 — raised below
    require_admin(request)
    factory = request.app.state.session_factory
    user = get_user(request)
    acknowledged_by = user.get("email", "admin")
    ok = await run_sync(
        external_write_scanner.acknowledge,
        factory,
        write_id,
        acknowledged_by=acknowledged_by,
    )
    if not ok:
        raise CatalogNotFoundError(f"unattributed_writes row {write_id} not found")
    await audit(
        request,
        "external_writes.acknowledged",
        f"unattributed_writes:{write_id}",
        {"acknowledged_by": acknowledged_by},
    )
    return {"id": write_id, "acknowledged_by": acknowledged_by}
