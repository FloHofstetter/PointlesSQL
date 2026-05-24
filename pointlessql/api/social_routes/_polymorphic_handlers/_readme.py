"""Entity README get / put handlers.

Each axis lives in its own sub-module now while the
public handler names re-export from the package facade.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import desc, func, select

from pointlessql.api.dependencies import (
    get_user,
    require_user,
)
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    readme_supported,
    resolve_target_id,
    serialise_readme,
)
from pointlessql.exceptions import (
    AuthorizationError,
    BadRequestError,
    ResourceNotFoundError,
)
from pointlessql.models.auth import User
from pointlessql.models.social._entity_readme import EntityReadme

# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------


async def get_polymorphic_readme(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Return the latest README for the polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        Serialised latest README row.

    Raises:
        ResourceNotFoundError: When the entity has no README yet,
            or when the registry says READMEs aren't supported for
            this kind.
    """
    require_user(request)
    readme_supported(kind)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        latest = session.execute(
            select(EntityReadme)
            .where(
                EntityReadme.workspace_id == workspace_id,
                EntityReadme.social_target_id == target_id,
            )
            .order_by(desc(EntityReadme.version_int))
            .limit(1)
        ).scalar_one_or_none()
        if latest is None:
            raise ResourceNotFoundError(f"No README yet for {kind}:{ref}.")
        author = session.get(User, latest.updated_by_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None
    return serialise_readme(
        latest,
        author_email=author_email,
        author_display_name=author_display,
    )


async def put_polymorphic_readme(kind: str, ref: str, request: Request) -> dict[str, Any]:
    """Save a new README version for the polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        Serialised README version row (existing one when body
        matches the latest version's content, otherwise the new
        row at ``version_int = max+1``).

    Raises:
        AuthorizationError: When the caller is not an install-admin.
            Non-DP entities have no per-entity steward concept,
            so only install-admins can edit READMEs in this
            iteration.
        BadRequestError: When ``body_md`` isn't a string.
        ResourceNotFoundError: When the registry says READMEs
            aren't supported for this kind.
    """
    require_user(request)
    user = get_user(request)
    if not bool(user.get("is_admin")):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="readme-edit",
            securable_type=kind,
            full_name=ref,
        )
    readme_supported(kind)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    body = await request.json()
    body_md = body.get("body_md", "")
    if not isinstance(body_md, str):
        raise BadRequestError("body_md must be a string")

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        latest = session.execute(
            select(EntityReadme)
            .where(
                EntityReadme.workspace_id == workspace_id,
                EntityReadme.social_target_id == target_id,
            )
            .order_by(desc(EntityReadme.version_int))
            .limit(1)
        ).scalar_one_or_none()
        if latest is not None and latest.body_md == body_md:
            author = session.get(User, latest.updated_by_user_id)
            return serialise_readme(
                latest,
                author_email=author.email if author else None,
                author_display_name=(author.display_name if author else None),
            )
        next_version = (
            session.execute(
                select(func.coalesce(func.max(EntityReadme.version_int), 0)).where(
                    EntityReadme.workspace_id == workspace_id,
                    EntityReadme.social_target_id == target_id,
                )
            ).scalar_one()
            + 1
        )
        new_row = EntityReadme(
            workspace_id=workspace_id,
            social_target_id=target_id,
            version_int=int(next_version),
            body_md=body_md,
            updated_by_user_id=user["id"],
            updated_at=now,
        )
        session.add(new_row)
        session.commit()
        session.refresh(new_row)
        author = session.get(User, new_row.updated_by_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None

    return serialise_readme(
        new_row,
        author_email=author_email,
        author_display_name=author_display,
    )
