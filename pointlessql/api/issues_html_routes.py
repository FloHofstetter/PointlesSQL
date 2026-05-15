"""HTML pages for the GitHub-Issues entity (Phase 77.7).

Two pages mirror the data-products surface:

* ``GET /issues`` — global cross-entity issues index with chip
  filters + a row layout that shows the parent kind/ref.
* ``GET /issues/{id}`` — single-issue detail with a sidebar for
  state / assignee / labels / milestone / parent link, plus a
  comments thread driven by the polymorphic discussion routes.

Both redirect anonymous visitors to ``/auth/login?next=...`` so
the deep-link survives the OIDC round-trip.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select

from pointlessql.api.dependencies import current_workspace_id, get_user
from pointlessql.models.social._issue import Issue
from pointlessql.models.social._social_target import SocialTarget

router = APIRouter(tags=["issues"])


@router.get("/issues", response_class=HTMLResponse, response_model=None)
async def issues_index_page(
    request: Request,
) -> HTMLResponse | RedirectResponse:
    """Render the global cross-entity issues index."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url="/auth/login?next=/issues", status_code=303
        )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/issues_index.html",
        {"active_page": "issues", "is_admin": user["is_admin"]},
    )


@router.get(
    "/issues/{issue_id}", response_class=HTMLResponse, response_model=None
)
async def issue_detail_page(
    issue_id: int, request: Request
) -> HTMLResponse | RedirectResponse:
    """Render a single issue's detail page."""
    user = get_user(request)
    if user["id"] == 0:
        return RedirectResponse(
            url=f"/auth/login?next=/issues/{issue_id}", status_code=303
        )
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
        parent_row = session.execute(
            select(
                SocialTarget.entity_kind, SocialTarget.entity_ref
            ).where(SocialTarget.id == issue.parent_social_target_id)
        ).first()
        parent_kind = str(parent_row[0]) if parent_row else None
        parent_ref = str(parent_row[1]) if parent_row else None
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/issue_detail.html",
        {
            "active_page": "issues",
            "is_admin": user["is_admin"],
            "issue_id": issue_id,
            "issue_title": issue.title,
            "parent_kind": parent_kind,
            "parent_ref": parent_ref,
        },
    )
