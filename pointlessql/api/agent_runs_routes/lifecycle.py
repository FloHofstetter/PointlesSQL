"""Admin-only approval / denial transitions for runs in ``needs_approval``.

Approve transitions ``needs_approval`` → ``approved`` and stamps the
admin email + UTC timestamp.  Deny is a terminal transition straight
to ``denied`` with ``finished_at`` set; the optional ``reason`` body
field is recommended for audit readability.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, Body, Request
from sqlalchemy import select

from pointlessql.api._audit_helpers import audit
from pointlessql.api.agent_runs_routes._anomaly_persist import persist_run_anomaly
from pointlessql.api.agent_runs_routes._serializers import serialize_agent_run
from pointlessql.api.dependencies import get_user, require_admin
from pointlessql.enums import RunStatus
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models.agent_runs import AgentRun

router = APIRouter()


@router.post("/api/agent-runs/{run_id}/approve")
async def api_approve_agent_run(
    request: Request,
    run_id: str,
) -> dict[str, Any]:
    """Admin-only approval for a run pending ``needs_approval``.

    Transitions the row to ``approved`` and records the approving
    admin + timestamp.  The HTML supervision UI surfaces this as an
    Approve button on the run-detail page.

    Args:
        request: Incoming FastAPI request.
        run_id: The UUID string of the run to approve.

    Returns:
        The serialized row after the transition.

    Raises:
        CatalogNotFoundError: No run with that id.
        ValidationError: Run is not in ``needs_approval``.
    """
    require_admin(request)
    user = get_user(request)
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        if row.status != RunStatus.NEEDS_APPROVAL:
            raise ValidationError(f"agent run {run_id!r} is {row.status!r}, cannot approve")
        row.status = RunStatus.APPROVED
        row.approved_by = user["email"]
        row.approved_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(request, "approve_agent_run", f"agent_run:{run_id}")
    return serialize_agent_run(row)


@router.post("/api/agent-runs/{run_id}/deny")
async def api_deny_agent_run(
    request: Request,
    run_id: str,
    body: dict[str, Any] = Body(default={}),
) -> dict[str, Any]:
    """Admin-only denial for a run pending ``needs_approval``.

    Terminal transition: the row moves straight to ``denied`` with
    ``finished_at`` set.  A ``reason`` body field is optional but
    recommended for audit readability.

    Args:
        request: Incoming FastAPI request.
        run_id: The UUID string of the run to deny.
        body: Optional JSON with ``reason`` text.

    Returns:
        The serialized, terminal row.

    Raises:
        CatalogNotFoundError: No run with that id.
        ValidationError: Run is not in ``needs_approval``.
    """
    require_admin(request)
    reason_raw = body.get("reason")
    reason = str(reason_raw).strip() if isinstance(reason_raw, str) and reason_raw.strip() else None
    factory = request.app.state.session_factory
    with factory() as session:
        row = session.scalar(select(AgentRun).where(AgentRun.id == run_id))
        if row is None:
            raise CatalogNotFoundError(f"agent run {run_id!r} not found")
        if row.status != RunStatus.NEEDS_APPROVAL:
            raise ValidationError(f"agent run {run_id!r} is {row.status!r}, cannot deny")
        row.status = RunStatus.DENIED
        row.denied_reason = reason
        row.finished_at = datetime.now(UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    persist_run_anomaly(request, run_id)
    await audit(
        request,
        "deny_agent_run",
        f"agent_run:{run_id}",
        {"reason": reason},
    )
    return serialize_agent_run(row)
