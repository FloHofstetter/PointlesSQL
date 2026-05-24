"""Pinned-answer routes for the Lens read-only Q&A surface."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_analyst,
)
from pointlessql.services.lens._pinned import (
    create_pin,
    delete_pin,
    get_pin_by_slug,
    list_pins,
)

router = APIRouter()


class CreatePinBody(BaseModel):
    """Input for ``POST /api/lens/pinned``."""

    title: str = Field(min_length=1, max_length=200)
    source_message_id: int | None = None
    is_shared: bool = False


class PinRow(BaseModel):
    """One pinned-answer row in API responses."""

    slug: str
    title: str
    source_message_id: int | None
    is_shared: bool
    created_at: str


class PinDetail(PinRow):
    """Full pinned-answer payload incl. snapshot + preview."""

    content_snapshot: str
    sql_text: str | None
    result_preview: Any | None


class PinList(BaseModel):
    """``GET /api/lens/pinned`` response shape."""

    pins: list[PinRow]


@router.post(
    "/pinned",
    response_model=PinRow,
    status_code=201,
    dependencies=[Depends(require_analyst)],
)
def create_pin_endpoint(
    request: Request,
    body: CreatePinBody,
) -> PinRow:
    """Pin one assistant message + return the new pin row.

    Args:
        request: FastAPI request.
        body: Validated pin-create payload.

    Returns:
        The created :class:`PinRow`.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    row = create_pin(
        factory,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
        title=body.title,
        source_message_id=body.source_message_id,
        is_shared=body.is_shared,
    )
    return PinRow(
        slug=str(row.slug),
        title=str(row.title),
        source_message_id=row.source_message_id,
        is_shared=bool(row.is_shared),
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


@router.get(
    "/pinned",
    response_model=PinList,
    dependencies=[Depends(require_analyst)],
)
def list_pins_endpoint(request: Request) -> PinList:
    """List visible pinned answers in the active workspace.

    Args:
        request: FastAPI request.

    Returns:
        :class:`PinList` ordered newest first.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    rows = list_pins(
        factory,
        workspace_id=workspace_id,
        requester_id=int(user.get("id") or 0),
        requester_is_admin=bool(user.get("is_admin")),
    )
    return PinList(
        pins=[
            PinRow(
                slug=str(r.slug),
                title=str(r.title),
                source_message_id=r.source_message_id,
                is_shared=bool(r.is_shared),
                created_at=r.created_at.isoformat() if r.created_at else "",
            )
            for r in rows
        ]
    )


@router.get(
    "/pinned/{slug}",
    response_model=PinDetail,
    dependencies=[Depends(require_analyst)],
)
def get_pin_endpoint(request: Request, slug: str) -> PinDetail:
    """Return one pin's full payload.

    Args:
        request: FastAPI request.
        slug: Pin slug.

    Returns:
        :class:`PinDetail` with snapshot + preview.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    row = get_pin_by_slug(
        factory,
        workspace_id=workspace_id,
        slug=slug,
        requester_id=int(user.get("id") or 0),
        requester_is_admin=bool(user.get("is_admin")),
    )
    return PinDetail(
        slug=str(row.slug),
        title=str(row.title),
        source_message_id=row.source_message_id,
        is_shared=bool(row.is_shared),
        created_at=row.created_at.isoformat() if row.created_at else "",
        content_snapshot=str(row.content_snapshot or ""),
        sql_text=row.sql_text,
        result_preview=row.result_preview,
    )


@router.delete(
    "/pinned/{slug}",
    status_code=204,
    dependencies=[Depends(require_analyst)],
)
def delete_pin_endpoint(request: Request, slug: str) -> None:
    """Delete a pinned answer.

    Args:
        request: FastAPI request.
        slug: Pin slug.

    Raises:
        ResourceNotFoundError: When no pin matches.
    """
    from pointlessql.exceptions import ResourceNotFoundError

    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    deleted = delete_pin(
        factory,
        workspace_id=workspace_id,
        slug=slug,
        requester_id=int(user.get("id") or 0),
        requester_is_admin=bool(user.get("is_admin")),
    )
    if not deleted:
        raise ResourceNotFoundError(f"lens_pinned: {slug}")


@router.get(
    "/pinned/{slug}/view",
    response_class=HTMLResponse,
    dependencies=[Depends(require_analyst)],
)
def view_pin_page(request: Request, slug: str) -> HTMLResponse:
    """Render the pinned-answer standalone page.

    Args:
        request: FastAPI request.
        slug: Pin slug.

    Returns:
        Server-rendered HTML view.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    row = get_pin_by_slug(
        factory,
        workspace_id=workspace_id,
        slug=slug,
        requester_id=int(user.get("id") or 0),
        requester_is_admin=bool(user.get("is_admin")),
    )
    templates = request.app.state.templates
    return templates.TemplateResponse(
        request,
        "pages/lens_pinned_view.html",
        {
            "active_page": "lens",
            "pin": row,
        },
    )
