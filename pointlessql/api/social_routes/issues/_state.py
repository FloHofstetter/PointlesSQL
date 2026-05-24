"""Close + reopen + the shared ``_transition_state`` body."""

from __future__ import annotations

import datetime
import json
import logging
from typing import Any, cast

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.api.social_routes._issue_helpers import (
    can_edit_issue,
    hydrate_emails,
    hydrate_parent,
    serialise_issue,
)
from pointlessql.exceptions import (
    BadRequestError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from pointlessql.models.social._issue import (
    ISSUE_CLOSED_REASONS,
    Issue,
)
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_ISSUE_STATE_CHANGED,
    emit_governance_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["social"])


async def _transition_state(
    issue_id: int,
    request: Request,
    *,
    new_state: str,
    closed_reason: str | None = None,
) -> dict[str, Any]:
    """Shared close / reopen / not-planned transition with audit + event."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        issue = session.execute(
            select(Issue).where(Issue.id == issue_id, Issue.workspace_id == workspace_id)
        ).scalar_one_or_none()
        if issue is None:
            raise ResourceNotFoundError.not_found(what=f"issue id={issue_id}")
        if not can_edit_issue(user, issue):
            raise PermissionDeniedError("Only the issue opener or an admin may transition state.")
        prior_state = issue.state
        issue.state = new_state
        if new_state == "open":
            issue.closed_at = None
            issue.closed_reason = None
        else:
            issue.closed_at = datetime.datetime.now(datetime.UTC)
            issue.closed_reason = closed_reason
        session.commit()
        parent_kind, parent_ref = hydrate_parent(session, issue.parent_social_target_id)
        emails = hydrate_emails(
            session,
            [issue.opened_by_user_id]
            + ([issue.assignee_user_id] if issue.assignee_user_id else []),
        )
        result = serialise_issue(
            issue,
            parent_kind=parent_kind,
            parent_ref=parent_ref,
            assignee_email=emails.get(issue.assignee_user_id or 0),
            opener_email=emails.get(issue.opened_by_user_id),
        )

    mirror_social_to_audit(
        factory,
        user_id=int(user["id"]),
        user_email=str(user["email"]),
        action="audit.issue.state_changed",
        entity_kind="issue",
        entity_ref=str(issue_id),
        suffix="state_changed",
        detail={
            "issue_id": issue_id,
            "from_state": prior_state,
            "to_state": new_state,
            "closed_reason": closed_reason,
        },
        workspace_id=workspace_id,
    )
    await emit_governance_event(
        EVENT_TYPE_ISSUE_STATE_CHANGED,
        {
            "issue_id": issue_id,
            "workspace_id": workspace_id,
            "from_state": prior_state,
            "to_state": new_state,
            "closed_reason": closed_reason,
        },
        session_factory=factory,
        workspace_id=workspace_id,
    )
    # feed surfacing for state transitions.  ``verb`` is
    # bound outside the try block so the exception handler's log line
    # has a stable name even if the fanout-module import explodes.
    verb = (
        "closed"
        if new_state.startswith("closed")
        else ("resolved" if new_state == "resolved" else "reopened")
    )
    try:
        from pointlessql.services.notifications.fanout import fanout_event

        fanout_event(
            factory,
            event_type=f"pointlessql.issue.{verb}",
            entity_kind="issue",
            entity_ref=str(issue_id),
            workspace_id=workspace_id,
            actor_user_id=int(user["id"]),
            source_url=f"/issues/{issue_id}",
            summary_md=f"Issue #{issue_id} {verb}",
        )
    except Exception:  # noqa: BLE001 — fanout best-effort
        # bare-broad-ok: issue-state-change fanout is best-effort
        logger.exception("issue_state_change_fanout_failed issue_id=%s verb=%s", issue_id, verb)
    return result


@router.post("/api/issues/{issue_id}/close")
async def close_issue(issue_id: int, request: Request) -> dict[str, Any]:
    """Close an open issue.

    Body (optional):
        ``{"closed_reason": "fixed" | "wont_fix" | "duplicate"
        | "superseded", "not_planned": bool}``.  When
        ``not_planned`` is true the state lands as
        ``closed_not_planned``; otherwise ``closed``.
    """
    payload: dict[str, Any] = {}
    try:
        raw = await request.json()
        if isinstance(raw, dict):
            payload = cast(dict[str, Any], raw)
    except ValueError, json.JSONDecodeError:
        payload = {}
    closed_reason_raw = payload.get("closed_reason")
    if closed_reason_raw is not None and closed_reason_raw not in ISSUE_CLOSED_REASONS:
        raise BadRequestError(f"closed_reason must be one of {ISSUE_CLOSED_REASONS}")
    closed_reason: str | None = str(closed_reason_raw) if closed_reason_raw is not None else None
    not_planned = bool(payload.get("not_planned"))
    new_state = "closed_not_planned" if not_planned else "closed"
    return await _transition_state(
        issue_id,
        request,
        new_state=new_state,
        closed_reason=closed_reason,
    )


@router.post("/api/issues/{issue_id}/reopen")
async def reopen_issue(issue_id: int, request: Request) -> dict[str, Any]:
    """Reopen a closed issue.  Clears ``closed_at`` + ``closed_reason``."""
    return await _transition_state(issue_id, request, new_state="open")
