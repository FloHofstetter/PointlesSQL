"""Lens session CRUD routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_analyst,
)
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.models import LENS_PROVIDERS
from pointlessql.services.lens import (
    create_session,
    delete_session,
    get_session,
    list_sessions,
)

router = APIRouter()


class CreateSessionBody(BaseModel):
    """Input for ``POST /api/lens/sessions``."""

    title: str = Field(min_length=1, max_length=200)
    llm_provider: str = Field(default="anthropic")
    llm_model: str | None = Field(default=None)


class SessionRow(BaseModel):
    """One Lens session row in API responses."""

    id: int
    title: str
    llm_provider: str
    llm_model: str
    total_cost_estimate: float
    created_at: str
    last_message_at: str | None


class SessionList(BaseModel):
    """``GET /api/lens/sessions`` response shape."""

    sessions: list[SessionRow]


@router.post(
    "/sessions",
    response_model=SessionRow,
    status_code=201,
    dependencies=[Depends(require_analyst)],
)
def create_session_endpoint(
    request: Request,
    body: CreateSessionBody,
) -> SessionRow:
    """Create a new chat session in the active workspace.

    Args:
        request: FastAPI request (for app.state + workspace_id).
        body: Validated session-create payload.

    Returns:
        The created :class:`SessionRow`.

    Raises:
        ValidationError: When the body's ``llm_provider`` is not in
            :data:`LENS_PROVIDERS`.
    """
    if body.llm_provider not in LENS_PROVIDERS:
        from pointlessql.exceptions import ValidationError

        raise ValidationError(
            f"llm_provider must be one of {sorted(LENS_PROVIDERS)}; got {body.llm_provider!r}"
        )
    factory = request.app.state.session_factory
    settings = request.app.state.settings
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    default_model = (
        settings.lens.openai_model_default
        if body.llm_provider == "openai"
        else settings.lens.anthropic_model_default
    )
    row = create_session(
        factory,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
        title=body.title,
        llm_provider=body.llm_provider,
        llm_model=body.llm_model or default_model,
    )
    return _serialise_session(row)


@router.get(
    "/sessions",
    response_model=SessionList,
    dependencies=[Depends(require_analyst)],
)
def list_sessions_endpoint(
    request: Request,
    limit: int = 50,
) -> SessionList:
    """List the analyst's recent sessions, newest activity first.

    Args:
        request: FastAPI request.
        limit: Page size cap (defaults to 50).

    Returns:
        :class:`SessionList`.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    rows = list_sessions(
        factory,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
        limit=limit,
    )
    return SessionList(sessions=[_serialise_session(r) for r in rows])


@router.delete(
    "/sessions/{session_id}",
    status_code=204,
    dependencies=[Depends(require_analyst)],
)
def delete_session_endpoint(
    request: Request,
    session_id: int,
) -> None:
    """Delete a session (cascades through messages).

    Args:
        request: FastAPI request.
        session_id: Lens session primary key.

    Raises:
        ResourceNotFoundError: When no row matches the workspace +
            owner scope.
    """
    factory = request.app.state.session_factory
    workspace_id = current_workspace_id(request)
    user = get_user(request)
    # Verify the session exists for this workspace + owner before
    # deleting; raises ResourceNotFoundError when not.
    get_session(
        factory,
        session_id=session_id,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
    )
    deleted = delete_session(
        factory,
        session_id=session_id,
        workspace_id=workspace_id,
        owner_id=int(user.get("id") or 0),
    )
    if not deleted:
        raise ResourceNotFoundError(f"lens_session: {session_id}")


def _serialise_session(row: object) -> SessionRow:
    """Render a detached :class:`LensSession` to the wire shape."""
    created_at_val = getattr(row, "created_at", None)
    last_message_at_val = getattr(row, "last_message_at", None)
    return SessionRow(
        id=int(getattr(row, "id", 0)),
        title=str(getattr(row, "title", "")),
        llm_provider=str(getattr(row, "llm_provider", "")),
        llm_model=str(getattr(row, "llm_model", "")),
        total_cost_estimate=float(getattr(row, "total_cost_estimate", 0.0) or 0.0),
        created_at=created_at_val.isoformat() if created_at_val else "",
        last_message_at=(last_message_at_val.isoformat() if last_message_at_val else None),
    )
