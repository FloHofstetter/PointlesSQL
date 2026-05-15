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
from pointlessql.api.social_routes._kind_dispatch import (
    parse_dp_ref,
    parse_ref,
)
from pointlessql.models.auth import User
from pointlessql.models.social._issue import (
    ISSUE_CLOSED_REASONS,
    Issue,
)
from pointlessql.models.social._issue_label import IssueLabel
from pointlessql.models.social._issue_milestone import IssueMilestone
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.social._target_resolver import (
    get_or_create_target,
    resolve_dp_target,
)
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.social.entity_registry import get as registry_get
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_ISSUE_OPENED,
    EVENT_TYPE_ISSUE_STATE_CHANGED,
    emit_governance_event,
)

router = APIRouter(tags=["social"])

_MAX_TITLE = 255
_MAX_LABELS = 20


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ensure_parent_supports_issues(kind: str) -> None:
    """Raise 404 when the parent kind has ``supports_issues=False``."""
    spec = registry_get(kind)
    if not spec.supports_issues:
        # bare-http-ok: issues are entity-kind opt-in.
        raise HTTPException(
            status_code=404,
            detail=f"kind={kind!r} does not support issues",
        )


def _resolve_parent_target_id(
    session: Any,
    workspace_id: int,
    kind: str,
    ref: str,
) -> int:
    """Return the parent's ``social_targets.id`` for an issue create.

    Args:
        session: Active SQLAlchemy session.
        workspace_id: Tenant scope for both the parent + the issue.
        kind: Parent entity kind discriminator.
        ref: Parent entity reference.

    Returns:
        The parent's ``social_targets.id``.  Created on demand for
        non-DP kinds; looked up via ``resolve_dp_target`` for
        ``kind='dp'`` so the back-pointer is populated.

    Raises:
        HTTPException: 404 when ``kind='dp'`` and the DP row is
            missing in the workspace.
    """
    if kind == "dp":
        try:
            target = resolve_dp_target(
                session,
                workspace_id=workspace_id,
                catalog_name=ref.split(".", 1)[0],
                schema_name=ref.split(".", 1)[1],
            )
        except LookupError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
    else:
        target = get_or_create_target(
            session,
            workspace_id=workspace_id,
            kind=kind,
            ref=ref,
        )
    return int(target.id)


def _normalise_parent_ref(kind: str, ref: str) -> str:
    """Validate the parent ``(kind, ref)`` pair and return the canonical ref."""
    if kind == "dp":
        catalog, schema = parse_dp_ref(kind, ref)
        return f"{catalog}.{schema}"
    return parse_ref(kind, ref)


def _validate_labels(raw: Any) -> str:
    """Coerce a labels-input value into a JSON string of slugs.

    Args:
        raw: Either a Python list of strings, or a JSON-encoded
            string already.  Anything else triggers a 400.

    Returns:
        Canonical JSON-encoded list of label slugs.

    Raises:
        HTTPException: 400 on malformed input or > :data:`_MAX_LABELS`.
    """
    if raw is None:
        return "[]"
    parsed: Any
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise HTTPException(
                status_code=400, detail=f"labels not JSON: {exc}"
            ) from exc
    else:
        parsed = raw
    if not isinstance(parsed, list):
        raise HTTPException(
            status_code=400, detail="labels must be a JSON array of strings"
        )
    parsed_list = cast(list[Any], parsed)
    if len(parsed_list) > _MAX_LABELS:
        raise HTTPException(
            status_code=400,
            detail=f"too many labels (max {_MAX_LABELS})",
        )
    cleaned: list[str] = []
    for item in parsed_list:
        if not isinstance(item, str) or not item:
            raise HTTPException(
                status_code=400,
                detail="every label must be a non-empty string slug",
            )
        cleaned.append(item)
    return json.dumps(cleaned)


def _serialise_issue(
    issue: Issue,
    *,
    parent_kind: str | None = None,
    parent_ref: str | None = None,
    assignee_email: str | None = None,
    opener_email: str | None = None,
) -> dict[str, Any]:
    """Render one issue row as a JSON-friendly dict."""
    return {
        "id": issue.id,
        "social_target_id": issue.social_target_id,
        "parent_social_target_id": issue.parent_social_target_id,
        "parent_kind": parent_kind,
        "parent_ref": parent_ref,
        "title": issue.title,
        "body_md": issue.body_md,
        "state": issue.state,
        "assignee": {
            "user_id": issue.assignee_user_id,
            "email": assignee_email,
        }
        if issue.assignee_user_id is not None
        else None,
        "opened_by": {
            "user_id": issue.opened_by_user_id,
            "email": opener_email,
        },
        "opened_at": issue.opened_at.isoformat(),
        "closed_at": issue.closed_at.isoformat()
        if issue.closed_at
        else None,
        "closed_reason": issue.closed_reason,
        "milestone_id": issue.milestone_id,
        "labels": json.loads(issue.labels_json or "[]"),
    }


def _hydrate_parent(
    session: Any, parent_social_target_id: int
) -> tuple[str | None, str | None]:
    """Look up ``(parent_kind, parent_ref)`` for a parent social_target id."""
    row = session.execute(
        select(
            SocialTarget.entity_kind, SocialTarget.entity_ref
        ).where(SocialTarget.id == parent_social_target_id)
    ).first()
    if row is None:
        return None, None
    return str(row[0]), str(row[1])


def _hydrate_emails(
    session: Any, user_ids: list[int]
) -> dict[int, str]:
    """Bulk-resolve user ids to email strings."""
    if not user_ids:
        return {}
    rows = session.execute(
        select(User.id, User.email).where(User.id.in_(user_ids))
    ).all()
    return {int(uid): str(email) for uid, email in rows}


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
    _ensure_parent_supports_issues(parent_kind)
    canonical_parent_ref = _normalise_parent_ref(parent_kind, parent_ref)

    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object"
        )
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    title_raw = payload.get("title")
    if not isinstance(title_raw, str) or not title_raw.strip():
        raise HTTPException(
            status_code=400, detail="title is required and non-empty"
        )
    title: str = title_raw
    if len(title) > _MAX_TITLE:
        raise HTTPException(
            status_code=400,
            detail=f"title too long (max {_MAX_TITLE} chars)",
        )
    body_md_raw = payload.get("body_md", "") or ""
    if not isinstance(body_md_raw, str):
        raise HTTPException(
            status_code=400, detail="body_md must be a string"
        )
    body_md: str = body_md_raw
    labels_json = _validate_labels(payload.get("labels"))
    assignee_raw = payload.get("assignee_user_id")
    if assignee_raw is not None and not isinstance(assignee_raw, int):
        raise HTTPException(
            status_code=400, detail="assignee_user_id must be an int or null"
        )
    assignee_user_id: int | None = assignee_raw
    milestone_raw = payload.get("milestone_id")
    if milestone_raw is not None and not isinstance(milestone_raw, int):
        raise HTTPException(
            status_code=400, detail="milestone_id must be an int or null"
        )
    milestone_id: int | None = milestone_raw

    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        parent_target_id = _resolve_parent_target_id(
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
        parent_kind_hyd, parent_ref_hyd = _hydrate_parent(
            session, parent_target_id
        )
        emails = _hydrate_emails(
            session,
            [int(user["id"])]
            + ([assignee_user_id] if assignee_user_id else []),
        )
        result = _serialise_issue(
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
    _ensure_parent_supports_issues(parent_kind)
    canonical_parent_ref = _normalise_parent_ref(parent_kind, parent_ref)

    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        parent_target_id = _resolve_parent_target_id(
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
        emails = _hydrate_emails(session, user_ids)
        return {
            "parent_kind": parent_kind,
            "parent_ref": canonical_parent_ref,
            "count": len(rows),
            "issues": [
                _serialise_issue(
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
        emails = _hydrate_emails(session, user_ids)
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
                _serialise_issue(
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
            raise HTTPException(status_code=404, detail="issue not found")
        parent_kind, parent_ref = _hydrate_parent(
            session, issue.parent_social_target_id
        )
        emails = _hydrate_emails(
            session,
            [issue.opened_by_user_id]
            + (
                [issue.assignee_user_id]
                if issue.assignee_user_id
                else []
            ),
        )
        return _serialise_issue(
            issue,
            parent_kind=parent_kind,
            parent_ref=parent_ref,
            assignee_email=emails.get(issue.assignee_user_id or 0),
            opener_email=emails.get(issue.opened_by_user_id),
        )


# ---------------------------------------------------------------------------
# PATCH — update title / body / assignee / labels / milestone
# ---------------------------------------------------------------------------


def _can_edit_issue(user: Any, issue: Issue) -> bool:
    """Return whether *user* may PATCH *issue*.

    Opener + admin only.  Mirrors GitHub's perms.
    """
    if user.get("is_admin"):
        return True
    return int(user.get("id") or 0) == int(issue.opened_by_user_id)


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
            raise HTTPException(status_code=404, detail="issue not found")
        if not _can_edit_issue(user, issue):
            raise HTTPException(
                status_code=403, detail="only opener or admin may edit"
            )
        if "title" in payload:
            new_title_raw = payload["title"]
            if not isinstance(new_title_raw, str) or not new_title_raw.strip():
                raise HTTPException(
                    status_code=400,
                    detail="title must be a non-empty string",
                )
            if len(new_title_raw) > _MAX_TITLE:
                raise HTTPException(
                    status_code=400, detail="title too long"
                )
            issue.title = new_title_raw.strip()
        if "body_md" in payload:
            new_body_raw = payload["body_md"]
            if not isinstance(new_body_raw, str):
                raise HTTPException(
                    status_code=400, detail="body_md must be a string"
                )
            issue.body_md = new_body_raw
        if "assignee_user_id" in payload:
            new_assignee_raw = payload["assignee_user_id"]
            if new_assignee_raw is not None and not isinstance(
                new_assignee_raw, int
            ):
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
                raise HTTPException(
                    status_code=400,
                    detail="milestone_id must be int or null",
                )
            issue.milestone_id = new_milestone_raw
        if "labels" in payload:
            issue.labels_json = _validate_labels(payload["labels"])
        session.commit()
        parent_kind, parent_ref = _hydrate_parent(
            session, issue.parent_social_target_id
        )
        emails = _hydrate_emails(
            session,
            [issue.opened_by_user_id]
            + (
                [issue.assignee_user_id]
                if issue.assignee_user_id
                else []
            ),
        )
        result = _serialise_issue(
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
            raise HTTPException(status_code=404, detail="issue not found")
        if not _can_edit_issue(user, issue):
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
        parent_kind, parent_ref = _hydrate_parent(
            session, issue.parent_social_target_id
        )
        emails = _hydrate_emails(
            session,
            [issue.opened_by_user_id]
            + (
                [issue.assignee_user_id]
                if issue.assignee_user_id
                else []
            ),
        )
        result = _serialise_issue(
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


# ---------------------------------------------------------------------------
# Labels CRUD
# ---------------------------------------------------------------------------


def _serialise_label(label: IssueLabel) -> dict[str, Any]:
    """Render an :class:`IssueLabel` row as a JSON-friendly dict."""
    return {
        "id": label.id,
        "slug": label.slug,
        "label_text": label.label_text,
        "color_hex": label.color_hex,
        "created_at": label.created_at.isoformat(),
    }


@router.get("/api/workspaces/{workspace_id}/labels")
async def list_labels(
    workspace_id: int, request: Request
) -> dict[str, Any]:
    """List every label registered for a workspace."""
    require_user(request)
    if workspace_id != current_workspace_id(request):
        raise HTTPException(
            status_code=403, detail="cross-workspace label read forbidden"
        )
    factory = request.app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(IssueLabel)
                .where(IssueLabel.workspace_id == workspace_id)
                .order_by(IssueLabel.slug)
            )
            .scalars()
            .all()
        )
        return {"labels": [_serialise_label(r) for r in rows]}


@router.post("/api/workspaces/{workspace_id}/labels")
async def create_label(
    workspace_id: int, request: Request
) -> dict[str, Any]:
    """Register a new label."""
    require_user(request)
    if workspace_id != current_workspace_id(request):
        raise HTTPException(
            status_code=403, detail="cross-workspace label write forbidden"
        )
    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object"
        )
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    slug_raw = payload.get("slug")
    if not isinstance(slug_raw, str) or not slug_raw:
        raise HTTPException(
            status_code=400, detail="slug must be a non-empty string"
        )
    slug: str = slug_raw
    label_text_raw = payload.get("label_text") or slug
    label_text: str = str(label_text_raw)
    color_hex: str = str(payload.get("color_hex", "#cccccc"))
    factory = request.app.state.session_factory
    with factory() as session:
        existing = session.execute(
            select(IssueLabel).where(
                IssueLabel.workspace_id == workspace_id,
                IssueLabel.slug == slug,
            )
        ).scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=409, detail=f"label slug {slug!r} already exists"
            )
        label = IssueLabel(
            workspace_id=workspace_id,
            slug=slug,
            label_text=label_text,
            color_hex=color_hex,
        )
        session.add(label)
        session.commit()
        session.refresh(label)
        return _serialise_label(label)


@router.delete("/api/workspaces/{workspace_id}/labels/{label_id}")
async def delete_label(
    workspace_id: int, label_id: int, request: Request
) -> dict[str, Any]:
    """Drop a label.  Existing issue label-arrays are NOT updated."""
    require_user(request)
    if workspace_id != current_workspace_id(request):
        raise HTTPException(
            status_code=403, detail="cross-workspace label write forbidden"
        )
    factory = request.app.state.session_factory
    with factory() as session:
        label = session.execute(
            select(IssueLabel).where(
                IssueLabel.id == label_id,
                IssueLabel.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if label is None:
            raise HTTPException(status_code=404, detail="label not found")
        session.delete(label)
        session.commit()
    return {"deleted": True, "id": label_id}


# ---------------------------------------------------------------------------
# Milestones CRUD
# ---------------------------------------------------------------------------


def _serialise_milestone(m: IssueMilestone) -> dict[str, Any]:
    """Render an :class:`IssueMilestone` row as a JSON-friendly dict."""
    return {
        "id": m.id,
        "title": m.title,
        "description_md": m.description_md,
        "due_at": m.due_at.isoformat() if m.due_at else None,
        "closed_at": m.closed_at.isoformat() if m.closed_at else None,
        "created_at": m.created_at.isoformat(),
    }


@router.get("/api/workspaces/{workspace_id}/milestones")
async def list_milestones(
    workspace_id: int, request: Request
) -> dict[str, Any]:
    """List every milestone for a workspace."""
    require_user(request)
    if workspace_id != current_workspace_id(request):
        raise HTTPException(
            status_code=403,
            detail="cross-workspace milestone read forbidden",
        )
    factory = request.app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(IssueMilestone)
                .where(IssueMilestone.workspace_id == workspace_id)
                .order_by(IssueMilestone.due_at.is_(None), IssueMilestone.due_at)
            )
            .scalars()
            .all()
        )
        return {"milestones": [_serialise_milestone(r) for r in rows]}


@router.post("/api/workspaces/{workspace_id}/milestones")
async def create_milestone(
    workspace_id: int, request: Request
) -> dict[str, Any]:
    """Create a milestone."""
    require_user(request)
    if workspace_id != current_workspace_id(request):
        raise HTTPException(
            status_code=403,
            detail="cross-workspace milestone write forbidden",
        )
    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        raise HTTPException(
            status_code=400, detail="request body must be a JSON object"
        )
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    title_raw = payload.get("title")
    if not isinstance(title_raw, str) or not title_raw.strip():
        raise HTTPException(
            status_code=400, detail="title is required"
        )
    title: str = title_raw
    description_raw = payload.get("description_md")
    description_md: str | None = (
        description_raw if isinstance(description_raw, str) else None
    )
    due_at_raw = payload.get("due_at")
    due_at: datetime.datetime | None = None
    if due_at_raw is not None:
        if not isinstance(due_at_raw, str):
            raise HTTPException(
                status_code=400, detail="due_at must be an ISO 8601 string"
            )
        try:
            due_at = datetime.datetime.fromisoformat(due_at_raw)
        except (TypeError, ValueError) as exc:
            raise HTTPException(
                status_code=400, detail=f"due_at not ISO 8601: {exc}"
            ) from exc
    factory = request.app.state.session_factory
    with factory() as session:
        m = IssueMilestone(
            workspace_id=workspace_id,
            title=title.strip(),
            description_md=description_md,
            due_at=due_at,
        )
        session.add(m)
        session.commit()
        session.refresh(m)
        return _serialise_milestone(m)


@router.delete("/api/workspaces/{workspace_id}/milestones/{milestone_id}")
async def delete_milestone(
    workspace_id: int, milestone_id: int, request: Request
) -> dict[str, Any]:
    """Drop a milestone.  Issues stay; their ``milestone_id`` may dangle."""
    require_user(request)
    if workspace_id != current_workspace_id(request):
        raise HTTPException(
            status_code=403,
            detail="cross-workspace milestone write forbidden",
        )
    factory = request.app.state.session_factory
    with factory() as session:
        m = session.execute(
            select(IssueMilestone).where(
                IssueMilestone.id == milestone_id,
                IssueMilestone.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if m is None:
            raise HTTPException(
                status_code=404, detail="milestone not found"
            )
        session.delete(m)
        session.commit()
    return {"deleted": True, "id": milestone_id}


__all__: list[str] = ["router"]
