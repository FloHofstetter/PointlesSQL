"""``POST /api/social/{parent_kind}/{parent_ref}/issues`` — create an issue."""

from __future__ import annotations

import datetime
import logging
import uuid
from typing import Any, cast

from fastapi import APIRouter, Request

from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.api.social_routes._issue_helpers import (
    ensure_parent_supports_issues,
    hydrate_emails,
    hydrate_parent,
    normalise_parent_ref,
    resolve_parent_target_id,
    serialise_issue,
    validate_labels,
)
from pointlessql.exceptions import BadRequestError
from pointlessql.models.social._issue import Issue
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_ISSUE_OPENED,
    emit_governance_event,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["social"])

MAX_TITLE = 255


@router.post("/api/social/{parent_kind}/{parent_ref:path}/issues")
async def open_issue(
    parent_kind: str, parent_ref: str, request: Request
) -> dict[str, Any]:
    """Open a new issue against a parent entity.

    Request body shape:
        ``{"title": str, "body_md"?: str, "labels"?: list[str],
        "assignee_user_id"?: int, "milestone_id"?: int}``

    Args:
        parent_kind: Parent entity kind from the URL path.
        parent_ref: Parent entity reference from the URL path.
        request: Active FastAPI request — used to resolve the
            caller, workspace scope and JSON body.

    Returns:
        The new issue as a JSON dict.

    Raises:
        BadRequestError: On bad body / parent ref / labels.
        ResourceNotFoundError: When the parent kind opts out of
            issues or the DP parent is missing.
    """
    require_user(request)
    user = get_user(request)
    ensure_parent_supports_issues(parent_kind)
    canonical_parent_ref = normalise_parent_ref(parent_kind, parent_ref)

    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        raise BadRequestError("request body must be a JSON object")
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    title_raw = payload.get("title")
    if not isinstance(title_raw, str) or not title_raw.strip():
        raise BadRequestError("title is required and non-empty")
    title: str = title_raw
    if len(title) > MAX_TITLE:
        raise BadRequestError(f"title too long (max {MAX_TITLE} chars)")
    body_md_raw = payload.get("body_md", "") or ""
    if not isinstance(body_md_raw, str):
        raise BadRequestError("body_md must be a string")
    body_md: str = body_md_raw
    labels_json = validate_labels(payload.get("labels"))
    assignee_raw = payload.get("assignee_user_id")
    if assignee_raw is not None and not isinstance(assignee_raw, int):
        raise BadRequestError("assignee_user_id must be an int or null")
    assignee_user_id: int | None = assignee_raw
    milestone_raw = payload.get("milestone_id")
    if milestone_raw is not None and not isinstance(milestone_raw, int):
        raise BadRequestError("milestone_id must be an int or null")
    milestone_id: int | None = milestone_raw

    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        parent_target_id = resolve_parent_target_id(
            session, workspace_id, parent_kind, canonical_parent_ref
        )

        # Step 1: insert the issue's own social_target with a
        # placeholder ref (we don't yet know the issue.id).  The
        # placeholder is a UUID hex so the workspace+kind+ref unique
        # never collides across concurrent opens.
        placeholder = f"_pending_{uuid.uuid4().hex}"
        anchor = SocialTarget(
            workspace_id=workspace_id,
            entity_kind="issue",
            entity_ref=placeholder,
            data_product_id=None,
        )
        session.add(anchor)
        session.flush()

        # Step 2: insert the issue with the anchor in hand.
        now = datetime.datetime.now(datetime.UTC)
        issue = Issue(
            workspace_id=workspace_id,
            social_target_id=int(anchor.id),
            parent_social_target_id=parent_target_id,
            title=title.strip(),
            body_md=body_md,
            state="open",
            assignee_user_id=assignee_user_id,
            opened_by_user_id=int(user["id"]),
            opened_at=now,
            milestone_id=milestone_id,
            labels_json=labels_json,
        )
        session.add(issue)
        session.flush()

        # Step 3: rewrite the anchor's entity_ref to the real id.
        anchor.entity_ref = str(issue.id)
        session.commit()

        # Hydration for the response.
        parent_kind_hyd, parent_ref_hyd = hydrate_parent(
            session, parent_target_id
        )
        emails = hydrate_emails(
            session,
            [int(user["id"])]
            + ([assignee_user_id] if assignee_user_id else []),
        )
        result = serialise_issue(
            issue,
            parent_kind=parent_kind_hyd,
            parent_ref=parent_ref_hyd,
            assignee_email=emails.get(int(assignee_user_id))
            if assignee_user_id
            else None,
            opener_email=emails.get(int(user["id"])),
        )

    # Audit + governance + fanout — issue is now durable.
    mirror_social_to_audit(
        factory,
        user_id=int(user["id"]),
        user_email=str(user["email"]),
        action="audit.issue.opened",
        entity_kind="issue",
        entity_ref=str(result["id"]),
        suffix="opened",
        detail={
            "issue_id": result["id"],
            "parent_kind": parent_kind_hyd,
            "parent_ref": parent_ref_hyd,
            "title": title.strip(),
        },
        workspace_id=workspace_id,
    )
    await emit_governance_event(
        EVENT_TYPE_ISSUE_OPENED,
        {
            "issue_id": result["id"],
            "workspace_id": workspace_id,
            "parent_kind": parent_kind_hyd,
            "parent_ref": parent_ref_hyd,
            "opened_by": int(user["id"]),
            "title": title.strip(),
        },
        session_factory=factory,
        workspace_id=workspace_id,
    )
    # Phase 81.K.6 — surface issue lifecycle in the feed.  The
    # fanout dispatcher's follower-resolver walks the polymorphic
    # social_follows on this issue and its parent entity; an empty
    # follower set is a no-op so this is safe regardless of state.
    try:
        from pointlessql.services.notifications.fanout import fanout_event

        fanout_event(
            factory,
            event_type="pointlessql.issue.opened",
            entity_kind="issue",
            entity_ref=str(result["id"]),
            workspace_id=workspace_id,
            actor_user_id=int(user["id"]),
            source_url=f"/issues/{result['id']}",
            summary_md=f"Issue \"{title.strip()[:120]}\" opened",
        )
    except Exception:  # noqa: BLE001 — fanout best-effort
        # bare-broad-ok: issue-opened fanout is best-effort
        logger.exception("issue_opened_fanout_failed issue_id=%s", result.get("id"))
    return result
