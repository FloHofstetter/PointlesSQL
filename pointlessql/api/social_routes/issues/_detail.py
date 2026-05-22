"""``GET /api/issues/{id}`` + ``PATCH /api/issues/{id}`` — detail + update."""

from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.api.social_routes._issue_helpers import (
    can_edit_issue,
    hydrate_emails,
    hydrate_parent,
    serialise_issue,
    validate_labels,
)
from pointlessql.api.social_routes.issues._open import MAX_TITLE
from pointlessql.models.social._issue import Issue
from pointlessql.services.social.audit_mirror import mirror_social_to_audit

router = APIRouter(tags=["social"])


@router.get("/api/issues/{issue_id}")
async def get_issue(issue_id: int, request: Request) -> dict[str, Any]:
    """Return one issue + its parent kind/ref."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        issue = session.execute(
            select(Issue).where(
                Issue.id == issue_id, Issue.workspace_id == workspace_id
            )
        ).scalar_one_or_none()
        if issue is None:
            # bare-http-ok: API contract / request validation.
            raise HTTPException(status_code=404, detail="issue not found")
        parent_kind, parent_ref = hydrate_parent(
            session, issue.parent_social_target_id
        )
        emails = hydrate_emails(
            session,
            [issue.opened_by_user_id]
            + (
                [issue.assignee_user_id]
                if issue.assignee_user_id
                else []
            ),
        )
        return serialise_issue(
            issue,
            parent_kind=parent_kind,
            parent_ref=parent_ref,
            assignee_email=emails.get(issue.assignee_user_id or 0),
            opener_email=emails.get(issue.opened_by_user_id),
        )


@router.patch("/api/issues/{issue_id}")
async def patch_issue(
    issue_id: int, request: Request
) -> dict[str, Any]:
    """Update opener-editable fields on an issue."""
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        # bare-http-ok: API contract / request validation.
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object"
        )
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    factory = request.app.state.session_factory
    with factory() as session:
        issue = session.execute(
            select(Issue).where(
                Issue.id == issue_id, Issue.workspace_id == workspace_id
            )
        ).scalar_one_or_none()
        if issue is None:
            # bare-http-ok: API contract / request validation.
            raise HTTPException(status_code=404, detail="issue not found")
        if not can_edit_issue(user, issue):
            raise HTTPException(
                status_code=403, detail="only opener or admin may edit"
            )
        if "title" in payload:
            new_title_raw = payload["title"]
            if not isinstance(new_title_raw, str) or not new_title_raw.strip():
                # bare-http-ok: API contract / request validation.
                raise HTTPException(
                    status_code=400,
                    detail="title must be a non-empty string",
                )
            if len(new_title_raw) > MAX_TITLE:
                # bare-http-ok: API contract / request validation.
                raise HTTPException(
                    status_code=400, detail="title too long"
                )
            issue.title = new_title_raw.strip()
        if "body_md" in payload:
            new_body_raw = payload["body_md"]
            if not isinstance(new_body_raw, str):
                # bare-http-ok: API contract / request validation.
                raise HTTPException(
                    status_code=400, detail="body_md must be a string"
                )
            issue.body_md = new_body_raw
        if "assignee_user_id" in payload:
            new_assignee_raw = payload["assignee_user_id"]
            if new_assignee_raw is not None and not isinstance(
                new_assignee_raw, int
            ):
                # bare-http-ok: API contract / request validation.
                raise HTTPException(
                    status_code=400,
                    detail="assignee_user_id must be int or null",
                )
            issue.assignee_user_id = new_assignee_raw
        if "milestone_id" in payload:
            new_milestone_raw = payload["milestone_id"]
            if new_milestone_raw is not None and not isinstance(
                new_milestone_raw, int
            ):
                # bare-http-ok: API contract / request validation.
                raise HTTPException(
                    status_code=400,
                    detail="milestone_id must be int or null",
                )
            issue.milestone_id = new_milestone_raw
        if "labels" in payload:
            issue.labels_json = validate_labels(payload["labels"])
        session.commit()
        parent_kind, parent_ref = hydrate_parent(
            session, issue.parent_social_target_id
        )
        emails = hydrate_emails(
            session,
            [issue.opened_by_user_id]
            + (
                [issue.assignee_user_id]
                if issue.assignee_user_id
                else []
            ),
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
        action="audit.issue.patched",
        entity_kind="issue",
        entity_ref=str(issue_id),
        suffix="patched",
        detail={
            "issue_id": issue_id,
            "fields": sorted(str(k) for k in payload),
        },
        workspace_id=workspace_id,
    )
    return result
