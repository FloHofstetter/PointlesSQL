"""``/api/data-products/{catalog}/{schema}/endorsements`` — typed badges (Phase 72.4).

Three endpoints:

* ``GET`` — list every endorsement (active + historical),
  newest first.
* ``POST`` — apply one type.  Body: ``{endorsement_type,
  note_md?}``.  Gate: steward + install-admin (auditor also
  passes for ``verified-by-steward`` only).  Re-applying the
  same type when there is already an active row is a no-op
  that returns the existing row.
* ``DELETE /{id}`` — soft-delete (sets ``removed_at``).  Same
  gate as POST.  Idempotent on an already-removed row.

Every successful POST and DELETE drops an ``audit_log`` row so
the audit-search FTS picks the action up alongside everything
else (matches the Phase-72.5 mirror pattern).
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_endorsement import (
    ENDORSEMENT_TYPES,
    DataProductEndorsement,
)
from pointlessql.services import audit as audit_service

router = APIRouter(tags=["data-products"])


_AUDITOR_TYPES: frozenset[str] = frozenset({"verified-by-steward"})


def _check_gate(
    user: Any,
    row: Any,
    endorsement_type: str,
) -> None:
    """Raise unless the caller can apply / remove *endorsement_type*."""
    is_steward = (
        row.steward_user_id is not None and row.steward_user_id == user["id"]
    )
    is_admin = bool(user.get("is_admin"))
    is_auditor = bool(user.get("is_auditor"))
    if is_steward or is_admin:
        return
    if is_auditor and endorsement_type in _AUDITOR_TYPES:
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege=f"endorse:{endorsement_type}",
        securable_type="data_product",
        full_name=f"{row.catalog_name}.{row.schema_name}",
    )


def _serialise(
    endorsement: DataProductEndorsement,
    *,
    author_email: str | None,
    author_display_name: str | None,
) -> dict[str, Any]:
    """Render one endorsement row as JSON."""
    return {
        "id": endorsement.id,
        "data_product_id": endorsement.data_product_id,
        "endorsement_type": endorsement.endorsement_type,
        "applied_by": {
            "user_id": endorsement.applied_by_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "applied_at": endorsement.applied_at.isoformat(),
        "removed_at": (
            endorsement.removed_at.isoformat() if endorsement.removed_at else None
        ),
        "note_md": endorsement.note_md or "",
    }


@router.get("/api/data-products/{catalog}/{schema}/endorsements")
async def list_endorsements(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return every endorsement for the product (active + removed)."""
    require_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductEndorsement)
                .where(
                    DataProductEndorsement.workspace_id == workspace_id,
                    DataProductEndorsement.data_product_id == row.id,
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
                session.execute(select(User).where(User.id.in_(author_ids)))
                .scalars()
                .all()
            )
            author_map = {u.id: (u.email, u.display_name) for u in users}
    payload = [
        _serialise(
            r,
            author_email=author_map.get(r.applied_by_user_id, (None, None))[0],
            author_display_name=author_map.get(r.applied_by_user_id, (None, None))[1],
        )
        for r in rows
    ]
    return {"data_product_id": row.id, "endorsements": payload}


@router.post("/api/data-products/{catalog}/{schema}/endorsements")
async def apply_endorsement(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Apply an endorsement of the given type.

    Body: ``{"endorsement_type": str, "note_md": str?}``.

    Returns:
        Serialised endorsement row.  If an active row of the same
        type already exists, returns it unchanged (no second row).
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    body = await request.json()
    endorsement_type = body.get("endorsement_type") or ""
    if endorsement_type not in ENDORSEMENT_TYPES:
        # bare-http-ok: typed enum boundary.
        raise HTTPException(
            status_code=400,
            detail=(
                f"endorsement_type must be one of "
                f"{sorted(ENDORSEMENT_TYPES)!r}"
            ),
        )
    _check_gate(user, row, endorsement_type)
    note_md = (body.get("note_md") or "").strip()

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.execute(
            select(DataProductEndorsement).where(
                DataProductEndorsement.workspace_id == workspace_id,
                DataProductEndorsement.data_product_id == row.id,
                DataProductEndorsement.endorsement_type == endorsement_type,
                DataProductEndorsement.removed_at.is_(None),
            )
        ).scalar_one_or_none()
        if existing is not None:
            author = session.get(User, existing.applied_by_user_id)
            return _serialise(
                existing,
                author_email=author.email if author else None,
                author_display_name=author.display_name if author else None,
            )

        new_row = DataProductEndorsement(
            workspace_id=workspace_id,
            data_product_id=row.id,
            endorsement_type=endorsement_type,
            applied_by_user_id=user["id"],
            applied_at=now,
            note_md=note_md,
        )
        session.add(new_row)
        session.commit()
        session.refresh(new_row)
        author = session.get(User, new_row.applied_by_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None

    audit_service.log_action(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="endorsement.applied",
        target=f"data_product:{catalog}.{schema}",
        detail={
            "endorsement_type": endorsement_type,
            "endorsement_id": new_row.id,
        },
        workspace_id=workspace_id,
    )
    return _serialise(
        new_row,
        author_email=author_email,
        author_display_name=author_display,
    )


@router.delete(
    "/api/data-products/{catalog}/{schema}/endorsements/{endorsement_id}"
)
async def remove_endorsement(
    catalog: str,
    schema: str,
    endorsement_id: int,
    request: Request,
) -> dict[str, Any]:
    """Soft-delete an endorsement.

    Returns:
        ``{"id": int, "removed_at": str}``.  Idempotent on
        already-removed rows (returns the existing
        ``removed_at`` unchanged).
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        endorsement = session.get(DataProductEndorsement, endorsement_id)
        if (
            endorsement is None
            or endorsement.workspace_id != workspace_id
            or endorsement.data_product_id != row.id
        ):
            # bare-http-ok: cross-product / cross-workspace ids 404.
            raise HTTPException(status_code=404, detail="endorsement not found")
        _check_gate(user, row, endorsement.endorsement_type)
        if endorsement.removed_at is None:
            endorsement.removed_at = datetime.datetime.now(datetime.UTC)
            session.add(endorsement)
            session.commit()
            session.refresh(endorsement)

    audit_service.log_action(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="endorsement.removed",
        target=f"data_product:{catalog}.{schema}",
        detail={
            "endorsement_type": endorsement.endorsement_type,
            "endorsement_id": endorsement.id,
        },
        workspace_id=workspace_id,
    )
    return {
        "id": endorsement.id,
        "removed_at": (
            endorsement.removed_at.isoformat() if endorsement.removed_at else None
        ),
    }
