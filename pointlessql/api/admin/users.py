"""Admin user-session management routes."""

from __future__ import annotations

from fastapi import APIRouter, Request

from pointlessql.api._audit_helpers import audit
from pointlessql.api.dependencies import require_admin
from pointlessql.exceptions import ResourceNotFoundError
from pointlessql.services import auth as auth_service

router = APIRouter(tags=["admin-users"])


@router.post("/api/admin/users/{user_id}/revoke-sessions")
async def api_admin_revoke_sessions(request: Request, user_id: int) -> dict[str, object]:
    """Force-log-out a user by invalidating all their outstanding JWTs.

    Bumps the target user's ``session_version`` so every token minted
    before now stops authenticating — the admin-side counterpart to the
    self-revocation a user's own logout performs.

    Args:
        request: Incoming FastAPI request.
        user_id: The user whose sessions to revoke.

    Returns:
        ``{"user_id": int, "revoked": True}``.

    Raises:
        ResourceNotFoundError: When no user has the given id.
    """
    require_admin(request)
    factory = request.app.state.session_factory
    if not auth_service.revoke_user_sessions(factory, user_id):
        raise ResourceNotFoundError(f"user {user_id} not found")
    await audit(request, "user.sessions_revoked", f"user:{user_id}", {"user_id": user_id})
    return {"user_id": user_id, "revoked": True}
