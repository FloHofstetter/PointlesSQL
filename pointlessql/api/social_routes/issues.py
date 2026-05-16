"""Polymorphic Issues router (Phase 77.7).

GitHub-Issues entity wired into the polymorphic social layer:
each issue is a row in ``issues`` PLUS its own ``social_targets``
anchor row (``kind='issue', entity_ref=str(issue.id)``).  An issue
is opened against a parent entity (table / model / branch / dp);
the parent link goes through the parent's own ``social_target_id``
so deleting the parent cascades into the issue.

Endpoint surface:

* ``POST /api/social/{parent_kind}/{parent_ref}/issues`` — create
* ``GET /api/social/{parent_kind}/{parent_ref}/issues`` — list (parent-scoped)
* ``GET /api/issues`` — global cross-entity index with filters
* ``GET /api/issues/{id}`` — single issue + parent metadata
* ``PATCH /api/issues/{id}`` — title / body / assignee / labels / milestone
* ``POST /api/issues/{id}/close`` + ``.../reopen`` — state transitions
* ``GET/POST/PATCH/DELETE /api/workspaces/{ws}/labels``
* ``GET/POST/PATCH/DELETE /api/workspaces/{ws}/milestones``

Issue → parent linkage uses two ``social_target`` FKs:
``social_target_id`` (self) and ``parent_social_target_id``.  The
self-target carries kind='issue' so the issue is comment-able,
follow-able, star-able and endorsement-able transparently through
the existing polymorphic routes.

Audit + governance:

* ``EVENT_TYPE_ISSUE_OPENED`` on create
* ``EVENT_TYPE_ISSUE_STATE_CHANGED`` on every close / reopen /
  mark-not-planned
* ``audit_log.target`` uses the generic ``issue:{id}#...`` prefix
  (locked decision #9).
"""

from __future__ import annotations

import datetime
import json
import uuid
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Query, Request
from sqlalchemy import and_, desc, select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.api.social_routes._issue_helpers import (
    can_edit_issue,
    ensure_parent_supports_issues,
    hydrate_emails,
    hydrate_parent,
    normalise_parent_ref,
    resolve_parent_target_id,
    serialise_issue,
    validate_labels,
)
from pointlessql.models.social._issue import (
    ISSUE_CLOSED_REASONS,
    Issue,
)
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_ISSUE_OPENED,
    EVENT_TYPE_ISSUE_STATE_CHANGED,
    emit_governance_event,
)

router = APIRouter(tags=["social"])

_MAX_TITLE = 255

# ---------------------------------------------------------------------------
# POST — create an issue against a parent
# ---------------------------------------------------------------------------



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
        HTTPException: 400 on bad body / parent ref / labels;
            404 when the parent kind opts out of issues or the DP
            parent is missing.
    """
    require_user(request)
    user = get_user(request)
    ensure_parent_supports_issues(parent_kind)
    canonical_parent_ref = normalise_parent_ref(parent_kind, parent_ref)

    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        # bare-http-ok: API contract / request validation.
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object"
        )
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    title_raw = payload.get("title")
    if not isinstance(title_raw, str) or not title_raw.strip():
        # bare-http-ok: API contract / request validation.
        raise HTTPException(
            status_code=400, detail="title is required and non-empty"
        )
    title: str = title_raw
    if len(title) > _MAX_TITLE:
        # bare-http-ok: API contract / request validation.
        raise HTTPException(
            status_code=400,
            detail=f"title too long (max {_MAX_TITLE} chars)",
        )
    body_md_raw = payload.get("body_md", "") or ""
    if not isinstance(body_md_raw, str):
        # bare-http-ok: API contract / request validation.
        raise HTTPException(
            status_code=400, detail="body_md must be a string"
        )
    body_md: str = body_md_raw
    labels_json = validate_labels(payload.get("labels"))
    assignee_raw = payload.get("assignee_user_id")
    if assignee_raw is not None and not isinstance(assignee_raw, int):
        # bare-http-ok: API contract / request validation.
        raise HTTPException(
            status_code=400, detail="assignee_user_id must be an int or null"
        )
    assignee_user_id: int | None = assignee_raw
    milestone_raw = payload.get("milestone_id")
    if milestone_raw is not None and not isinstance(milestone_raw, int):
        # bare-http-ok: API contract / request validation.
        raise HTTPException(
            status_code=400, detail="milestone_id must be an int or null"
        )
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
        pass
    return result


# ---------------------------------------------------------------------------
# GET — list issues against a parent
# ---------------------------------------------------------------------------


@router.get("/api/social/{parent_kind}/{parent_ref:path}/issues")
async def list_issues_for_parent(
    parent_kind: str,
    parent_ref: str,
    request: Request,
    state: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """List every issue opened against ``parent_kind/parent_ref``."""
    require_user(request)
    ensure_parent_supports_issues(parent_kind)
    canonical_parent_ref = normalise_parent_ref(parent_kind, parent_ref)

    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        parent_target_id = resolve_parent_target_id(
            session, workspace_id, parent_kind, canonical_parent_ref
        )
        conditions = [
            Issue.workspace_id == workspace_id,
            Issue.parent_social_target_id == parent_target_id,
        ]
        if state is not None:
            conditions.append(Issue.state == state)
        rows = (
            session.execute(
                select(Issue)
                .where(and_(*conditions))
                .order_by(desc(Issue.opened_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        user_ids = list(
            {r.opened_by_user_id for r in rows}
            | {r.assignee_user_id for r in rows if r.assignee_user_id}
        )
        emails = hydrate_emails(session, user_ids)
        return {
            "parent_kind": parent_kind,
            "parent_ref": canonical_parent_ref,
            "count": len(rows),
            "issues": [
                serialise_issue(
                    r,
                    parent_kind=parent_kind,
                    parent_ref=canonical_parent_ref,
                    assignee_email=emails.get(r.assignee_user_id or 0),
                    opener_email=emails.get(r.opened_by_user_id),
                )
                for r in rows
            ],
        }


# ---------------------------------------------------------------------------
# GET — global cross-entity issues index
# ---------------------------------------------------------------------------


@router.get("/api/issues")
async def list_issues_global(
    request: Request,
    state: str | None = Query(default=None),
    assignee_user_id: int | None = Query(default=None),
    opened_by_user_id: int | None = Query(default=None),
    milestone_id: int | None = Query(default=None),
    parent_kind: str | None = Query(default=None),
    label: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Cross-entity issues listing for the global ``/issues`` page."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        conditions = [Issue.workspace_id == workspace_id]
        if state is not None:
            conditions.append(Issue.state == state)
        if assignee_user_id is not None:
            conditions.append(Issue.assignee_user_id == assignee_user_id)
        if opened_by_user_id is not None:
            conditions.append(Issue.opened_by_user_id == opened_by_user_id)
        if milestone_id is not None:
            conditions.append(Issue.milestone_id == milestone_id)
        if parent_kind is not None:
            conditions.append(
                Issue.parent_social_target_id.in_(
                    select(SocialTarget.id).where(
                        SocialTarget.workspace_id == workspace_id,
                        SocialTarget.entity_kind == parent_kind,
                    )
                )
            )
        rows = (
            session.execute(
                select(Issue)
                .where(and_(*conditions))
                .order_by(desc(Issue.opened_at))
                .limit(limit)
            )
            .scalars()
            .all()
        )
        # Apply label filter client-side (labels are JSON arrays;
        # SQL-indexed label filtering is a 77.9 FTS deliverable).
        if label is not None:
            rows = [
                r for r in rows if label in json.loads(r.labels_json or "[]")
            ]
        user_ids = list(
            {r.opened_by_user_id for r in rows}
            | {r.assignee_user_id for r in rows if r.assignee_user_id}
        )
        emails = hydrate_emails(session, user_ids)
        parent_ids = [r.parent_social_target_id for r in rows]
        parent_lookup: dict[int, tuple[str | None, str | None]] = {}
        if parent_ids:
            for tid, kind_, ref_ in session.execute(
                select(
                    SocialTarget.id,
                    SocialTarget.entity_kind,
                    SocialTarget.entity_ref,
                ).where(SocialTarget.id.in_(parent_ids))
            ).all():
                parent_lookup[int(tid)] = (str(kind_), str(ref_))
        return {
            "count": len(rows),
            "issues": [
                serialise_issue(
                    r,
                    parent_kind=parent_lookup.get(
                        r.parent_social_target_id, (None, None)
                    )[0],
                    parent_ref=parent_lookup.get(
                        r.parent_social_target_id, (None, None)
                    )[1],
                    assignee_email=emails.get(r.assignee_user_id or 0),
                    opener_email=emails.get(r.opened_by_user_id),
                )
                for r in rows
            ],
        }


# ---------------------------------------------------------------------------
# GET — one issue + parent metadata
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# PATCH — update title / body / assignee / labels / milestone
# ---------------------------------------------------------------------------


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
            if len(new_title_raw) > _MAX_TITLE:
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


# ---------------------------------------------------------------------------
# POST close / reopen
# ---------------------------------------------------------------------------


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
            select(Issue).where(
                Issue.id == issue_id, Issue.workspace_id == workspace_id
            )
        ).scalar_one_or_none()
        if issue is None:
            # bare-http-ok: API contract / request validation.
            raise HTTPException(status_code=404, detail="issue not found")
        if not can_edit_issue(user, issue):
            raise HTTPException(
                status_code=403,
                detail="only opener or admin may transition state",
            )
        prior_state = issue.state
        issue.state = new_state
        if new_state == "open":
            issue.closed_at = None
            issue.closed_reason = None
        else:
            issue.closed_at = datetime.datetime.now(datetime.UTC)
            issue.closed_reason = closed_reason
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
    # Phase 81.K.6 — feed surfacing for state transitions.
    try:
        from pointlessql.services.notifications.fanout import fanout_event

        verb = (
            "closed" if new_state.startswith("closed")
            else ("resolved" if new_state == "resolved" else "reopened")
        )
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
        pass
    return result


@router.post("/api/issues/{issue_id}/close")
async def close_issue(
    issue_id: int, request: Request
) -> dict[str, Any]:
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
    except (ValueError, json.JSONDecodeError):
        payload = {}
    closed_reason_raw = payload.get("closed_reason")
    if (
        closed_reason_raw is not None
        and closed_reason_raw not in ISSUE_CLOSED_REASONS
    ):
        # bare-http-ok: API contract / request validation.
        raise HTTPException(
            status_code=400,
            detail=f"closed_reason must be one of {ISSUE_CLOSED_REASONS}",
        )
    closed_reason: str | None = (
        str(closed_reason_raw) if closed_reason_raw is not None else None
    )
    not_planned = bool(payload.get("not_planned"))
    new_state = "closed_not_planned" if not_planned else "closed"
    return await _transition_state(
        issue_id,
        request,
        new_state=new_state,
        closed_reason=closed_reason,
    )


@router.post("/api/issues/{issue_id}/reopen")
async def reopen_issue(
    issue_id: int, request: Request
) -> dict[str, Any]:
    """Reopen a closed issue.  Clears ``closed_at`` + ``closed_reason``."""
    return await _transition_state(issue_id, request, new_state="open")



__all__: list[str] = ["router"]
