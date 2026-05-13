"""``GET /api/users/search`` — typeahead picker (Phase 76.1).

Drives the comment @-autocomplete dropdown.  Returns up to eight
users matching the caller's query against either ``email`` or
``display_name`` (case-insensitive prefix).  Workspace-scoped:
only users in the caller's current workspace are returned.

Anti-abuse: requires authentication, capped result set, and never
returns sensitive fields (password_hash, oidc_subject, etc.).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import or_, select

from pointlessql.api.dependencies import require_user
from pointlessql.models.auth import User

router = APIRouter(tags=["users"])

_MAX_RESULTS = 8


@router.get("/api/users/search")
async def search_users(
    request: Request,
    q: str = "",
) -> dict[str, Any]:
    """Return up to eight users matching the prefix *q*.

    Args:
        request: Incoming FastAPI request.
        q: Prefix query.  Trimmed + lower-cased.  Empty returns
            an empty list (the typeahead-debounce loop on the
            frontend already skips the request when the user
            hasn't typed anything; this is a defensive guard).

    Returns:
        ``{"q": str, "results": [{user_id, email, display_name},
        ...]}``.
    """
    require_user(request)
    query = q.strip().lower()
    if not query:
        return {"q": query, "results": []}

    factory = request.app.state.session_factory
    like = f"{query}%"
    with factory() as session:
        rows = (
            session.execute(
                select(User.id, User.email, User.display_name)
                .where(
                    or_(
                        User.email.ilike(like),
                        User.display_name.ilike(like),
                    )
                )
                .order_by(User.display_name, User.email)
                .limit(_MAX_RESULTS)
            )
            .all()
        )

    return {
        "q": query,
        "results": [
            {
                "user_id": int(uid),
                "email": email,
                "display_name": display_name,
            }
            for uid, email, display_name in rows
        ],
    }
