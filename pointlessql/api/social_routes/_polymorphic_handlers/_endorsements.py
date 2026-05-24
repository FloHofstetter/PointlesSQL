"""Endorsement list / apply / remove handlers.

Extracted from the 2231-LOC ``_polymorphic_handlers.py`` monolith
in Phase 89.1 — each axis lives in its own sub-module now while the
public handler names re-export from the package facade.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.api.dependencies import (
    get_user,
    require_user,
)
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    endorsements_supported,
    resolve_target_id,
    serialise_endorsement,
)
from pointlessql.exceptions import (
    AuthorizationError,
    BadRequestError,
    ResourceNotFoundError,
)
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_endorsement import (
    ENDORSEMENT_TYPES,
    DataProductEndorsement,
)
from pointlessql.services.social import (
    resolve_citations,
)
from pointlessql.services.social.audit_mirror import mirror_social_to_audit

# ---------------------------------------------------------------------------
# Endorsements
# ---------------------------------------------------------------------------


async def list_polymorphic_endorsements(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return every endorsement for the polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "endorsements": [...]}``.
    """
    require_user(request)
    endorsements_supported(kind)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductEndorsement)
                .where(
                    DataProductEndorsement.workspace_id == workspace_id,
                    DataProductEndorsement.social_target_id == target_id,
                )
                .order_by(DataProductEndorsement.applied_at.desc())
            )
            .scalars()
            .all()
        )
        author_ids = {r.applied_by_user_id for r in rows}
        author_map: dict[int, tuple[str, str]] = {}
        if author_ids:
            users = (
                session.execute(
                    select(User).where(User.id.in_(author_ids))
                )
                .scalars()
                .all()
            )
            author_map = {u.id: (u.email, u.display_name) for u in users}
    payload = [
        serialise_endorsement(
            r,
            author_email=author_map.get(
                r.applied_by_user_id, (None, None)
            )[0],
            author_display_name=author_map.get(
                r.applied_by_user_id, (None, None)
            )[1],
            note_md_resolved=resolve_citations(
                r.note_md or "", factory, workspace_id
            ),
        )
        for r in rows
    ]
    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "social_target_id": target_id,
        "endorsements": payload,
    }


async def apply_polymorphic_endorsement(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Apply an endorsement of the given type to the polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        Serialised endorsement row.  Idempotent: re-applying the
        same type from the same caller returns the existing active
        row unchanged (matches the DP-path contract).

    Raises:
        BadRequestError: When ``endorsement_type`` is missing or
            outside the typed allow-list.
    """
    require_user(request)
    user = get_user(request)
    endorsements_supported(kind)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    body = await request.json()
    endorsement_type = body.get("endorsement_type") or ""
    if endorsement_type not in ENDORSEMENT_TYPES:
        raise BadRequestError(
            f"endorsement_type must be one of {sorted(ENDORSEMENT_TYPES)!r}"
        )
    note_md = (body.get("note_md") or "").strip()
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.execute(
            select(DataProductEndorsement).where(
                DataProductEndorsement.workspace_id == workspace_id,
                DataProductEndorsement.social_target_id == target_id,
                DataProductEndorsement.endorsement_type == endorsement_type,
                DataProductEndorsement.applied_by_user_id == user["id"],
                DataProductEndorsement.removed_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is not None:
            author = session.get(User, existing.applied_by_user_id)
            return serialise_endorsement(
                existing,
                author_email=author.email if author else None,
                author_display_name=(
                    author.display_name if author else None
                ),
                note_md_resolved=resolve_citations(
                    existing.note_md or "", factory, workspace_id
                ),
            )
        new_row = DataProductEndorsement(
            workspace_id=workspace_id,
            data_product_id=None,
            social_target_id=target_id,
            endorsement_type=endorsement_type,
            applied_by_user_id=user["id"],
            applied_by_agent_id=None,
            applied_at=now,
            note_md=note_md,
        )
        session.add(new_row)
        session.commit()
        session.refresh(new_row)
        author = session.get(User, new_row.applied_by_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None
        new_row_id = int(new_row.id)

    mirror_social_to_audit(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="endorsement.applied",
        entity_kind=kind,
        entity_ref=ref,
        detail={
            "endorsement_type": endorsement_type,
            "endorsement_id": new_row_id,
        },
        workspace_id=workspace_id,
    )
    return serialise_endorsement(
        new_row,
        author_email=author_email,
        author_display_name=author_display,
        note_md_resolved=resolve_citations(
            new_row.note_md or "", factory, workspace_id
        ),
    )


async def remove_polymorphic_endorsement(
    kind: str, ref: str, endorsement_id: int, request: Request
) -> dict[str, Any]:
    """Soft-delete an endorsement on the polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        endorsement_id: PK of the endorsement row to remove.
        request: Incoming FastAPI request.

    Returns:
        ``{"id": int, "removed_at": str | None}``.

    Raises:
        ResourceNotFoundError: When the endorsement is missing or
            scoped to a different entity.
        AuthorizationError: When the caller is neither the original
            applier nor an install-admin.
    """
    require_user(request)
    user = get_user(request)
    endorsements_supported(kind)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        endorsement = session.get(DataProductEndorsement, endorsement_id)
        if (
            endorsement is None
            or endorsement.workspace_id != workspace_id
            or endorsement.social_target_id != target_id
        ):
            raise ResourceNotFoundError.not_found(
                what=f"endorsement id={endorsement_id}"
            )
        is_applier = endorsement.applied_by_user_id == user["id"]
        is_admin = bool(user.get("is_admin"))
        if not (is_applier or is_admin):
            raise AuthorizationError(
                principal=user.get("email", ""),
                privilege=f"unendorse:{endorsement.endorsement_type}",
                securable_type=kind,
                full_name=ref,
            )
        if endorsement.removed_at is None:
            endorsement.removed_at = datetime.datetime.now(datetime.UTC)
            session.add(endorsement)
            session.commit()
            session.refresh(endorsement)
        endorsement_type = endorsement.endorsement_type
        endorsement_id_final = int(endorsement.id)
        removed_at_iso = (
            endorsement.removed_at.isoformat()
            if endorsement.removed_at
            else None
        )

    mirror_social_to_audit(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="endorsement.removed",
        entity_kind=kind,
        entity_ref=ref,
        detail={
            "endorsement_type": endorsement_type,
            "endorsement_id": endorsement_id_final,
        },
        workspace_id=workspace_id,
    )
    return {"id": endorsement_id_final, "removed_at": removed_at_iso}


