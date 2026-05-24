"""Labels + Milestones CRUD for the Phase-77.7 Issues entity.

Split out from :mod:`pointlessql.api.social_routes.issues` so the
issue-route surface stays under the file-size budget.  Both
catalogues are workspace-scoped; admin-vs-member gating is the
same simple ``workspace_id == current_workspace_id`` check used
elsewhere.

The routes:

* ``GET/POST/DELETE /api/workspaces/{ws}/labels``
* ``GET/POST/DELETE /api/workspaces/{ws}/milestones``
"""

from __future__ import annotations

import datetime
from typing import Any, cast

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import (
    BadRequestError,
    ConflictError,
    PermissionDeniedError,
    ResourceNotFoundError,
)
from pointlessql.models.social._issue_label import IssueLabel
from pointlessql.models.social._issue_milestone import IssueMilestone

router = APIRouter(tags=["social"])


# ---------------------------------------------------------------------------
# Helpers
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


# ---------------------------------------------------------------------------
# Labels CRUD
# ---------------------------------------------------------------------------


@router.get("/api/workspaces/{workspace_id}/labels")
async def list_labels(
    workspace_id: int, request: Request
) -> dict[str, Any]:
    """List every label registered for a workspace."""
    require_user(request)
    if workspace_id != current_workspace_id(request):
        raise PermissionDeniedError("Cross-workspace label read forbidden.")
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
        raise PermissionDeniedError("Cross-workspace label write forbidden.")
    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        raise BadRequestError("request body must be a JSON object")
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    slug_raw = payload.get("slug")
    if not isinstance(slug_raw, str) or not slug_raw:
        raise BadRequestError("slug must be a non-empty string")
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
            raise ConflictError(f"label slug {slug!r} already exists")
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
        raise PermissionDeniedError("Cross-workspace label write forbidden.")
    factory = request.app.state.session_factory
    with factory() as session:
        label = session.execute(
            select(IssueLabel).where(
                IssueLabel.id == label_id,
                IssueLabel.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if label is None:
            raise ResourceNotFoundError.not_found(what=f"label id={label_id}")
        session.delete(label)
        session.commit()
    return {"deleted": True, "id": label_id}


# ---------------------------------------------------------------------------
# Milestones CRUD
# ---------------------------------------------------------------------------


@router.get("/api/workspaces/{workspace_id}/milestones")
async def list_milestones(
    workspace_id: int, request: Request
) -> dict[str, Any]:
    """List every milestone for a workspace."""
    require_user(request)
    if workspace_id != current_workspace_id(request):
        raise PermissionDeniedError("Cross-workspace milestone read forbidden.")
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
        raise PermissionDeniedError("Cross-workspace milestone write forbidden.")
    payload_raw = await request.json()
    if not isinstance(payload_raw, dict):
        raise BadRequestError("request body must be a JSON object")
    payload: dict[str, Any] = cast(dict[str, Any], payload_raw)
    title_raw = payload.get("title")
    if not isinstance(title_raw, str) or not title_raw.strip():
        raise BadRequestError("title is required")
    title: str = title_raw
    description_raw = payload.get("description_md")
    description_md: str | None = (
        description_raw if isinstance(description_raw, str) else None
    )
    due_at_raw = payload.get("due_at")
    due_at: datetime.datetime | None = None
    if due_at_raw is not None:
        if not isinstance(due_at_raw, str):
            raise BadRequestError("due_at must be an ISO 8601 string")
        try:
            due_at = datetime.datetime.fromisoformat(due_at_raw)
        except (TypeError, ValueError) as exc:
            raise BadRequestError(f"due_at not ISO 8601: {exc}") from exc
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
        raise PermissionDeniedError("Cross-workspace milestone write forbidden.")
    factory = request.app.state.session_factory
    with factory() as session:
        m = session.execute(
            select(IssueMilestone).where(
                IssueMilestone.id == milestone_id,
                IssueMilestone.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if m is None:
            raise ResourceNotFoundError.not_found(
                what=f"milestone id={milestone_id}"
            )
        session.delete(m)
        session.commit()
    return {"deleted": True, "id": milestone_id}


__all__: list[str] = ["router"]
