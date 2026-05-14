"""``/api/data-products/{catalog}/{schema}/follow`` — follow / subscribe (Phase 71.3).

Four endpoints:

* ``POST /follow`` — idempotent INSERT … ON CONFLICT DO NOTHING.
* ``DELETE /follow`` — idempotent DELETE.
* ``GET /followers/count`` — public count, ungated beyond the
  logged-in-user gate.
* ``GET /followers`` — full list, restricted to steward + admin
  for privacy.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import AuthorizationError
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_follows import DataProductFollow
from pointlessql.services.social._target_resolver import resolve_dp_target
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_FOLLOWED,
    emit_governance_event,
)

router = APIRouter(tags=["data-products"])


@router.post("/api/data-products/{catalog}/{schema}/follow")
async def follow_data_product(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Idempotent follow.

    Returns ``{"followed": True, "already": bool}`` — ``already``
    is true on the second consecutive POST.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        existing = session.get(
            DataProductFollow,
            {
                "workspace_id": workspace_id,
                "data_product_id": row.id,
                "user_id": user["id"],
            },
        )
        if existing is not None:
            return {"followed": True, "already": True}
        target = resolve_dp_target(
            session,
            workspace_id=workspace_id,
            catalog_name=catalog,
            schema_name=schema,
        )
        session.add(
            DataProductFollow(
                workspace_id=workspace_id,
                data_product_id=row.id,
                social_target_id=target.id,
                user_id=user["id"],
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()

    # Phase 71.4: governance event only — no inbox fan-out for a
    # follow (the actor is the only person who cares; their own
    # rows would self-suppress anyway).
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_FOLLOWED,
        {
            "data_product_id": row.id,
            "data_product_ref": f"{catalog}.{schema}",
            "follower_user_id": user["id"],
            "follower_email": user.get("email", ""),
        },
        settings=request.app.state.settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )
    return {"followed": True, "already": False}


@router.delete("/api/data-products/{catalog}/{schema}/follow")
async def unfollow_data_product(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Idempotent unfollow.

    Returns ``{"followed": False, "removed": bool}`` — ``removed``
    is true on the call that actually dropped a row.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        existing = session.get(
            DataProductFollow,
            {
                "workspace_id": workspace_id,
                "data_product_id": row.id,
                "user_id": user["id"],
            },
        )
        if existing is None:
            return {"followed": False, "removed": False}
        session.delete(existing)
        session.commit()
    return {"followed": False, "removed": True}


@router.get("/api/data-products/{catalog}/{schema}/followers/count")
async def get_followers_count(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return the follower count + whether the caller is following.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"count": int, "following": bool}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        count = session.execute(
            select(func.count(DataProductFollow.user_id)).where(
                DataProductFollow.workspace_id == workspace_id,
                DataProductFollow.data_product_id == row.id,
            )
        ).scalar_one()
        following = (
            session.get(
                DataProductFollow,
                {
                    "workspace_id": workspace_id,
                    "data_product_id": row.id,
                    "user_id": user["id"],
                },
            )
            is not None
        )
    return {"count": int(count), "following": following}


@router.get("/api/data-products/{catalog}/{schema}/followers")
async def list_followers(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return the full list of followers — restricted to steward + admin.

    Privacy gate: the count is public (above) but the names are
    not.  Workspace-admin proxy is install-admin (``is_admin``)
    per the Phase-71 plan.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "followers": [...]}`` with one
        entry per follower (user_id + email + display_name +
        ``created_at`` of the follow link).

    Raises:
        AuthorizationError: When the caller is neither steward nor
            install-admin.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    is_steward = (
        row.steward_user_id is not None and row.steward_user_id == user["id"]
    )
    is_admin = bool(user.get("is_admin"))
    if not (is_steward or is_admin):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="followers-list",
            securable_type="data_product",
            full_name=f"{catalog}.{schema}",
        )

    with factory() as session:
        rows = session.execute(
            select(DataProductFollow, User)
            .join(User, User.id == DataProductFollow.user_id)
            .where(
                DataProductFollow.workspace_id == workspace_id,
                DataProductFollow.data_product_id == row.id,
            )
            .order_by(DataProductFollow.created_at.desc())
        ).all()

    followers = [
        {
            "user_id": user_row.id,
            "email": user_row.email,
            "display_name": user_row.display_name,
            "created_at": follow.created_at.isoformat(),
        }
        for follow, user_row in rows
    ]
    return {"data_product_id": row.id, "followers": followers}
