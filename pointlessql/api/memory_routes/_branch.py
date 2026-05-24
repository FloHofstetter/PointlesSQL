"""``POST /api/memory/{agent_id}/branch`` — agent-memory branch action.

Thin HTTP wrapper around :func:`pql.memory.branch` / :func:`fork`.
The route picks the underlying function from the request body's
``intent`` field (``"create"`` → ``branch``, ``"fork"`` → ``fork``)
so the UI's two buttons share one endpoint.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, Field

from pointlessql.api.dependencies import require_user
from pointlessql.exceptions import (
    BadRequestError,
    CatalogNotFoundError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.pql import memory
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.types import RunId

router = APIRouter()


class BranchRequest(BaseModel):
    """Request body for ``POST /api/memory/{agent_id}/branch``."""

    from_run_id: str = Field(
        ...,
        description="Source agent-run UUID to branch from.",
    )
    branch_name: str | None = Field(
        default=None,
        description="Optional branch suffix; auto-derived when null.",
    )
    pin_to_version: bool = Field(
        default=True,
        description="Stamp the source run's first-write delta version into branch metadata.",
    )
    intent: Literal["create", "fork"] = Field(
        default="create",
        description="``create`` calls pql.memory.branch; ``fork`` calls pql.memory.fork.",
    )


@router.post("/{agent_id}/branch")
async def branch_endpoint(
    agent_id: str,
    body: BranchRequest,
    request: Request,
) -> dict[str, Any]:
    """Create a Delta branch off the run's schema state.

    Args:
        agent_id: Free-form runtime identifier.
        body: Request payload.
        request: Incoming FastAPI request.

    Returns:
        ``{"branch_schema_fqn": ..., "parent_schema_fqn": ...,
        "pinned_delta_version": ..., "intent": ...}``.

    Raises:
        HTTPException: 400 on validation failures, 422 on
            soyuz-side schema conflicts, 503 when soyuz-catalog
            is unreachable.
    """
    require_user(request)
    settings = request.app.state.settings
    client = make_soyuz_client(settings)
    factory = request.app.state.session_factory
    unreachable = "soyuz-catalog unreachable"

    func = memory.branch if body.intent == "create" else memory.fork
    try:
        result = func(
            client=client,
            session_factory=factory,
            agent_id=agent_id,
            from_run_id=RunId(body.from_run_id),
            branch_name=body.branch_name,
            pin_to_version=body.pin_to_version,
            unreachable_msg=unreachable,
        )
    except ValidationError as exc:
        # surfaces caller-supplied validation issues.
        raise BadRequestError(str(exc)) from exc
    except CatalogNotFoundError:
        # CatalogNotFoundError carries 404 + catalog_not_found code.
        raise
    except CatalogUnavailableError:
        # CatalogUnavailableError carries 502 + catalog_unavailable code.
        raise
    return result
