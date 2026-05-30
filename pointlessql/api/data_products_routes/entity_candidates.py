"""Entity-link candidate review-queue routes."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from pointlessql.api.dependencies import get_user, require_user
from pointlessql.exceptions import AuthorizationError
from pointlessql.services import entities as entities_service

router = APIRouter(tags=["data-products"])


def _require_steward_or_admin(request: Request) -> None:
    """Soft gate — anyone signed-in may view; only steward/admin acts."""
    require_user(request)
    user = get_user(request)
    if user.get("is_admin"):
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="steward",
        securable_type="entity_link_candidate",
        full_name="",
    )


@router.get("/api/entity-link-candidates")
async def list_entity_link_candidates(
    request: Request,
    status: str = "pending",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    """Return entity-link candidates filtered by *status* (any-user)."""
    require_user(request)
    factory = request.app.state.session_factory
    if status == "pending":
        return {
            "candidates": entities_service.list_pending_candidates(
                factory, limit=limit, offset=offset
            )
        }
    return {
        "candidates": entities_service.list_candidates_by_decision(
            factory, decision=status, limit=limit, offset=offset
        )
    }


@router.post("/api/entity-link-candidates/{candidate_id}/accept")
async def accept_entity_link_candidate(
    candidate_id: int, request: Request
) -> dict[str, Any]:
    """Promote a candidate to an entity_link (steward/admin)."""
    _require_steward_or_admin(request)
    factory = request.app.state.session_factory
    user = get_user(request)
    try:
        return entities_service.accept_candidate(
            factory,
            candidate_id=candidate_id,
            reviewed_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except LookupError as exc:
        # bare-http-ok: 404 for unknown candidate.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # bare-http-ok: 409 — already decided.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/entity-link-candidates/{candidate_id}/reject")
async def reject_entity_link_candidate(
    candidate_id: int, request: Request
) -> dict[str, Any]:
    """Mark a candidate as rejected (steward/admin)."""
    _require_steward_or_admin(request)
    factory = request.app.state.session_factory
    user = get_user(request)
    try:
        return entities_service.reject_candidate(
            factory,
            candidate_id=candidate_id,
            reviewed_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except LookupError as exc:
        # bare-http-ok: 404 for unknown candidate.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # bare-http-ok: 409 — already decided.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/entity-link-candidates/{candidate_id}/defer")
async def defer_entity_link_candidate(
    candidate_id: int, request: Request
) -> dict[str, Any]:
    """Mark a candidate as deferred (steward/admin)."""
    _require_steward_or_admin(request)
    factory = request.app.state.session_factory
    user = get_user(request)
    try:
        return entities_service.defer_candidate(
            factory,
            candidate_id=candidate_id,
            reviewed_by_user_id=int(user.get("id", 0) or 0) or None,
        )
    except LookupError as exc:
        # bare-http-ok: 404 for unknown candidate.
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        # bare-http-ok: 409 — already decided.
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/api/admin/entity-discovery/run-now")
async def run_entity_discovery_now(request: Request) -> dict[str, Any]:
    """Trigger an entity-discovery pass synchronously (admin)."""
    from pointlessql.api.dependencies import current_workspace_id, require_admin

    require_admin(request)
    factory = request.app.state.session_factory
    inserted = entities_service.discover_candidates(
        factory,
        workspace_id=current_workspace_id(request),
    )
    return {"inserted": inserted}
