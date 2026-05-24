"""``POST /api/memory/{agent_id}/replay`` — agent-memory replay action.

Thin HTTP wrapper around :func:`pql.memory.replay`.  Returns the
:class:`ReplayResult` shape as JSON plus an ``HX-Redirect`` header
pointing at the new replay run's detail page so the UI can refresh
directly.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from pointlessql.api.dependencies import require_user
from pointlessql.exceptions import (
    BadRequestError,
    CatalogUnavailableError,
    ValidationError,
)
from pointlessql.pql import memory
from pointlessql.pql.engine import make_engine
from pointlessql.services.agent_runs.memory._replay import ReplayUnsafeOpError
from pointlessql.services.agent_runs.memory._replay_policy import ReplayPolicy
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.types import RunId

router = APIRouter()


class ReplayRequest(BaseModel):
    """Request body for ``POST /api/memory/{agent_id}/replay``."""

    branch_schema_fqn: str = Field(
        ...,
        description="Two-part catalog.branch_schema the replay writes against.",
    )
    source_run_id: str = Field(
        ...,
        description="Agent-run UUID whose operations are replayed.",
    )
    policy: str = Field(
        default="skip_unsafe",
        description="One of 'strict', 'skip_unsafe', 'lenient'.",
    )


@router.post("/{agent_id}/replay")
async def replay_endpoint(
    agent_id: str,
    body: ReplayRequest,
    request: Request,
) -> JSONResponse:
    """Replay a source run's operations onto the named branch.

    Args:
        agent_id: Free-form runtime identifier.
        body: Request payload.
        request: Incoming FastAPI request.

    Returns:
        :class:`JSONResponse` with the replay result fields plus
        an ``HX-Redirect`` header pointing at
        ``/runs/{replay_run_id}`` so HTMX clients land on the new
        run's detail page in one round-trip.

    Raises:
        HTTPException: 400 on validation / unknown policy, 422
            when STRICT policy hits an unsafe op, 503 when soyuz
            is unreachable.
    """
    require_user(request)
    try:
        policy_enum = ReplayPolicy(body.policy)
    except ValueError as exc:
        raise BadRequestError(
            f"unknown policy {body.policy!r}; "
            f"must be one of {[p.value for p in ReplayPolicy]}"
        ) from exc

    settings = request.app.state.settings
    client = make_soyuz_client(settings)
    factory = request.app.state.session_factory
    engine = make_engine(getattr(settings.delta, "engine", "pandas"))

    try:
        result = memory.replay(
            client=client,
            engine=engine,
            session_factory=factory,
            branch_schema_fqn=body.branch_schema_fqn,
            source_run_id=RunId(body.source_run_id),
            agent_id=agent_id,
            policy=policy_enum,
            unreachable_msg="soyuz-catalog unreachable",
        )
    except ReplayUnsafeOpError as exc:
        raise ValidationError(str(exc)) from exc
    except ValidationError:
        # ValidationError already carries status 422 + validation_error code;
        # let the global exception handler render it.
        raise
    except CatalogUnavailableError:
        # CatalogUnavailableError already carries status 502; central
        # handler renders it as problem+json.
        raise

    payload: dict[str, Any] = {
        "replay_run_id": str(result.replay_run_id),
        "ops_replayed": result.ops_replayed,
        "ops_skipped": [
            {
                "op_id": s.op_id,
                "op_name": s.op_name.value,
                "reason": s.reason,
            }
            for s in result.ops_skipped
        ],
        "started_at": result.started_at.isoformat(),
        "finished_at": result.finished_at.isoformat(),
    }
    response = JSONResponse(payload)
    response.headers["HX-Redirect"] = f"/runs/{result.replay_run_id}"
    return response
