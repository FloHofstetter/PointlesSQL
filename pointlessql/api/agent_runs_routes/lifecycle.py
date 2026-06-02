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
from pointlessql.exceptions import CatalogNotFoundError, ValidationError
from pointlessql.models.agent._runs import AgentRun
from pointlessql.services.notifications.fanout import (
    fanout_event,
    resolve_user_id_by_email,
    resolve_workspace_admin_ids,
)
from pointlessql.types import RunStatus

router = APIRouter()


def _fanout_run_decision(
    request: Request,
    *,
    run_id: str,
    principal: str | None,
    workspace_id: int,
    actor_user_id: int,
    event_type: str,
    summary_md: str,
) -> None:
    """Fan a terminal approve / deny decision into the feed.

    Best-effort informational lane: the decision is a permanent fact,
    so it rides the immutable ``user_notifications`` pipe (with
    read-state + live SSE).  Recipients are the run's principal (so
    the author learns the verdict) plus the workspace admins; the
    acting approver is excluded by ``fanout_event``.

    Args:
        request: Incoming FastAPI request (for the session factory).
        run_id: The run that was decided.
        principal: The run's principal email, if any.
        workspace_id: The run's workspace.
        actor_user_id: The deciding admin's user id (excluded from
            the recipient set).
        event_type: ``pointlessql.agent_run.approved`` / ``.denied``.
        summary_md: One-line inbox summary.
    """
    factory = request.app.state.session_factory
    with factory() as session:
        recipients = resolve_workspace_admin_ids(session)
        principal_id = resolve_user_id_by_email(session, principal)
    if principal_id is not None:
        recipients.append(principal_id)
    fanout_event(
        factory,
        event_type=event_type,
        entity_kind="run",
        entity_ref=run_id,
        workspace_id=workspace_id,
        actor_user_id=actor_user_id,
        source_url=f"/runs/{run_id}",
        summary_md=summary_md,
        extra_recipients=recipients,
    )


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
        principal = row.principal
        workspace_id = int(row.workspace_id)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    await audit(request, "approve_agent_run", f"agent_run:{run_id}")
    _fanout_run_decision(
        request,
        run_id=run_id,
        principal=principal,
        workspace_id=workspace_id,
        actor_user_id=int(user["id"]),
        event_type="pointlessql.agent_run.approved",
        summary_md=f"Run {run_id[:8]} approved by {user['email']}",
    )
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
    user = get_user(request)
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
        principal = row.principal
        workspace_id = int(row.workspace_id)
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
    _fanout_run_decision(
        request,
        run_id=run_id,
        principal=principal,
        workspace_id=workspace_id,
        actor_user_id=int(user["id"]),
        event_type="pointlessql.agent_run.denied",
        summary_md=f"Run {run_id[:8]} denied{': ' + reason if reason else ''}",
    )
    return serialize_agent_run(row)
