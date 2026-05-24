"""GET endpoints — parent-scoped listing + global cross-entity index."""

from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, desc, select

from pointlessql.api.dependencies import (
    PaginationParams,
    current_workspace_id,
    pagination,
    require_user,
)
from pointlessql.api.social_routes._issue_helpers import (
    ensure_parent_supports_issues,
    hydrate_emails,
    normalise_parent_ref,
    resolve_parent_target_id,
    serialise_issue,
)
from pointlessql.models.social._issue import Issue
from pointlessql.models.social._social_target import SocialTarget

router = APIRouter(tags=["social"])


@router.get("/api/social/{parent_kind}/{parent_ref:path}/issues")
async def list_issues_for_parent(
    parent_kind: str,
    parent_ref: str,
    request: Request,
    state: str | None = Query(default=None),
    paging: PaginationParams = Depends(pagination),
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
                .limit(paging.limit)
                .offset(paging.offset)
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


@router.get("/api/issues")
async def list_issues_global(
    request: Request,
    state: str | None = Query(default=None),
    assignee_user_id: int | None = Query(default=None),
    opened_by_user_id: int | None = Query(default=None),
    milestone_id: int | None = Query(default=None),
    parent_kind: str | None = Query(default=None),
    label: str | None = Query(default=None),
    paging: PaginationParams = Depends(pagination),
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
                .limit(paging.limit)
                .offset(paging.offset)
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
