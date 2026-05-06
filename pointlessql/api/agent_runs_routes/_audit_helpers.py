"""Shared helpers for the per-run audit-axis endpoints.

The five ``/api/agent-runs/{run_id}/audit/*`` routes all need to:

1. Confirm the requested run id exists (so a stale id surfaces as a
   clean ``CatalogNotFoundError`` instead of an empty rows list); and
2. Persist a ``query_history`` row marking that the audit endpoint
   was hit, so the cockpit/Hermes audit traffic stays visible inside
   the same audit lake it queries.

Both helpers are best-effort about errors: the audit-of-audit
breadcrumb is suppressed on any failure, since the agent reviewing
yesterday's anomalies needs the data more than it needs a
self-tracking row.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.api.dependencies import get_user
from pointlessql.exceptions import CatalogNotFoundError
from pointlessql.models.agent_runs import AgentRun
from pointlessql.services.query_history import record_query

logger = logging.getLogger(__name__)


def record_audit_self(
    request: Request,
    *,
    endpoint: str,
    params: dict[str, Any],
    started_at: datetime,
) -> None:
    """Persist a ``query_history`` row for one ``/api/agent-runs/.../audit/*`` call.

    Audit-of-audit logging — every per-run audit-axis read leaves a
    ``read_kind='audit_api'`` breadcrumb so the cockpit/Hermes
    traffic stays visible in the same audit lake it queries.
    Best-effort: a swallowed insert never fails the actual audit
    response.

    Args:
        request: FastAPI request, carrying the authenticated user.
        endpoint: Stable string identifier for the route, e.g.
            ``"/api/agent-runs/{run_id}/audit/lineage"``.
        params: Query-string params honoured (so a "weirdly empty
            result" can be re-traced via the params the cockpit
            caller actually sent).
        started_at: Wall-clock instant the route began handling.
    """
    user = get_user(request)
    finished_at = datetime.now(UTC)
    factory = request.app.state.session_factory
    sql_text = f"-- audit_api: {endpoint} {json.dumps(params, sort_keys=True, default=str)}"
    try:
        record_query(
            factory,
            user_id=int(user.get("id") or 0),
            user_email=str(user.get("email") or "anonymous"),
            sql_text=sql_text,
            started_at=started_at,
            finished_at=finished_at,
            status="succeeded",
            row_count=None,
            duration_ms=int((finished_at - started_at).total_seconds() * 1000),
            referenced_tables=[],
            agent_run_id=None,
            read_kind="audit_api",
        )
    except Exception as exc:  # noqa: BLE001 — audit-of-audit must never break the audit response
        logger.warning("audit_api: failed to self-track %s: %s", endpoint, exc)


def ensure_run_visible(factory: Any, run_id: str, *, workspace_id: int | None = None) -> AgentRun:
    """Return the ``AgentRun`` row for *run_id* or raise 404.

    Shared 404-guard for the per-run audit-axis endpoints so a
    Hermes audit-reviewer that cites a stale ``run_id`` gets a
    clean ``CatalogNotFoundError`` rather than a hollow ``rows: []``.

    When *workspace_id* is supplied, runs from a *different*
    workspace also surface as 404 — cross-workspace audit-axis
    access is indistinguishable from "no such run" by design (a leak
    through the error code would tell the caller that a run with
    that UUID exists somewhere they can't see).

    Args:
        factory: Sessionmaker callable from ``app.state``.
        run_id: UUID of the run to load.
        workspace_id: Caller's resolved workspace.  ``None`` skips
            the workspace check, which is appropriate for the
            super-admin cross-workspace lens.

    Returns:
        Detached :class:`AgentRun` row.

    Raises:
        CatalogNotFoundError: No run with that id, or the run lives
            in a different workspace than *workspace_id*.
    """
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        if workspace_id is not None and int(row.workspace_id) != int(workspace_id):
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        session.expunge(row)
    return row
