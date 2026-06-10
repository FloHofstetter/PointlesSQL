"""``/api/data-products/{catalog}/{schema}/endorsements`` — typed badges.

Three endpoints:

* ``GET`` — list every endorsement (active + historical),
  newest first.
* ``POST`` — apply one type.  Body: ``{endorsement_type,
  note_md?}``.  Accepts ``?as_agent=<slug>`` so an
  endorsement can be applied *by an agent on behalf of* its
  principal.  Gate: steward + install-admin (auditor also
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

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api._social_serializers import agent_payload as _agent_payload
from pointlessql.api.data_products_routes._shared import (
    load_one,
    resolve_agent_for_principal,
)
from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError, BadRequestError, ResourceNotFoundError
from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_endorsement import (
    ENDORSEMENT_TYPES,
    DataProductEndorsement,
)
from pointlessql.services.social import resolve_citations
from pointlessql.services.social._target_resolver import resolve_dp_target
from pointlessql.services.social.audit_mirror import mirror_social_to_audit

router = APIRouter(tags=["data-products"])


_AUDITOR_TYPES: frozenset[str] = frozenset({"verified-by-steward"})


def _check_gate(
    user: Any,
    row: Any,
    endorsement_type: str,
) -> None:
    """Raise unless the caller can apply / remove *endorsement_type*."""
    is_steward = row.steward_user_id is not None and row.steward_user_id == user["id"]
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
    note_md_resolved: str,
    agent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render one endorsement row as JSON.

    The ``agent`` payload mirrors the comment-serialiser shape
    : present when ``applied_by_agent_id`` is set,
    ``None`` otherwise.

    ``note_md_resolved`` carries the cite-token render projection
    — same string as ``note_md`` with ``#dp:`` /
    ``#topic:`` / ``#user:`` / ``#agent:`` tokens replaced by
    markdown anchors.  Frontend reads this via
    ``pqlRenderCitations``.
    """
    return {
        "id": endorsement.id,
        "data_product_id": endorsement.data_product_id,
        "endorsement_type": endorsement.endorsement_type,
        "applied_by": {
            "user_id": endorsement.applied_by_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "agent": agent,
        "applied_at": endorsement.applied_at.isoformat(),
        "removed_at": (endorsement.removed_at.isoformat() if endorsement.removed_at else None),
        "note_md": endorsement.note_md or "",
        "note_md_resolved": note_md_resolved,
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
            users = session.execute(select(User).where(User.id.in_(author_ids))).scalars().all()
            author_map = {u.id: (u.email, u.display_name) for u in users}
        agent_ids = {r.applied_by_agent_id for r in rows if r.applied_by_agent_id is not None}
        agent_map: dict[int, Agent] = {}
        if agent_ids:
            agents = session.execute(select(Agent).where(Agent.id.in_(agent_ids))).scalars().all()
            agent_map = {a.id: a for a in agents}
    payload = [
        _serialise(
            r,
            author_email=author_map.get(r.applied_by_user_id, (None, None))[0],
            author_display_name=author_map.get(r.applied_by_user_id, (None, None))[1],
            note_md_resolved=resolve_citations(
                r.note_md or "",
                factory,
                workspace_id,
            ),
            agent=_agent_payload(
                agent_map.get(r.applied_by_agent_id) if r.applied_by_agent_id is not None else None
            ),
        )
        for r in rows
    ]
    return {"data_product_id": row.id, "endorsements": payload}


@router.post("/api/data-products/{catalog}/{schema}/endorsements")
async def apply_endorsement(
    catalog: str,
    schema: str,
    request: Request,
    as_agent: str | None = None,
) -> dict[str, Any]:
    """Apply an endorsement of the given type.

    Body: ``{"endorsement_type": str, "note_md": str?}``.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.
        as_agent: Optional agent slug — when set,
            the endorsement is applied *by the agent on behalf of*
            the caller (who must be the agent's
            ``principal_user_id``, or admin).  ``applied_by_user_id``
            still records the principal so the audit chain stays
            intact.

    Returns:
        Serialised endorsement row.  If an active row of the same
        type already exists, returns it unchanged (no second row).
        When ``?as_agent=`` is supplied the caller must be the
        agent's ``principal_user_id`` or admin; otherwise the
        helper raises :class:`AuthorizationError` (rendered as a
        403 by middleware).  An unknown ``?as_agent=`` slug
        propagates :class:`ResourceNotFoundError` (404) from
        :func:`resolve_agent_for_principal`.

    Raises:
        BadRequestError: 400 when ``endorsement_type`` is missing
            or outside the typed allow-list.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _c, _e, _d = load_one(factory, workspace_id, catalog, schema)

    body = await request.json()
    endorsement_type = body.get("endorsement_type") or ""
    if endorsement_type not in ENDORSEMENT_TYPES:
        raise BadRequestError(f"endorsement_type must be one of {sorted(ENDORSEMENT_TYPES)!r}")
    _check_gate(user, row, endorsement_type)
    note_md = (body.get("note_md") or "").strip()

    applied_by_agent_id: int | None = None
    if as_agent is not None:
        applied_by_agent_id = resolve_agent_for_principal(
            factory, workspace_id=workspace_id, slug=as_agent, user=user
        )

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
            existing_agent = (
                session.get(Agent, existing.applied_by_agent_id)
                if existing.applied_by_agent_id is not None
                else None
            )
            return _serialise(
                existing,
                author_email=author.email if author else None,
                author_display_name=author.display_name if author else None,
                note_md_resolved=resolve_citations(
                    existing.note_md or "",
                    factory,
                    workspace_id,
                ),
                agent=_agent_payload(existing_agent),
            )

        target = resolve_dp_target(
            session,
            workspace_id=workspace_id,
            catalog_name=catalog,
            schema_name=schema,
        )
        new_row = DataProductEndorsement(
            workspace_id=workspace_id,
            data_product_id=row.id,
            social_target_id=target.id,
            endorsement_type=endorsement_type,
            applied_by_user_id=user["id"],
            applied_by_agent_id=applied_by_agent_id,
            applied_at=now,
            note_md=note_md,
        )
        session.add(new_row)
        session.commit()
        session.refresh(new_row)
        author = session.get(User, new_row.applied_by_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None
        new_agent = (
            session.get(Agent, new_row.applied_by_agent_id)
            if new_row.applied_by_agent_id is not None
            else None
        )
        new_agent_payload = _agent_payload(new_agent)

    audit_detail: dict[str, Any] = {
        "endorsement_type": endorsement_type,
        "endorsement_id": new_row.id,
    }
    if applied_by_agent_id is not None:
        audit_detail["agent_id"] = applied_by_agent_id
        audit_detail["principal_user_id"] = user["id"]
    mirror_social_to_audit(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="endorsement.applied",
        entity_kind="dp",
        entity_ref=f"{catalog}.{schema}",
        detail=audit_detail,
        workspace_id=workspace_id,
    )
    return _serialise(
        new_row,
        author_email=author_email,
        author_display_name=author_display,
        note_md_resolved=resolve_citations(
            new_row.note_md or "",
            factory,
            workspace_id,
        ),
        agent=new_agent_payload,
    )


@router.delete("/api/data-products/{catalog}/{schema}/endorsements/{endorsement_id}")
async def remove_endorsement(
    catalog: str,
    schema: str,
    endorsement_id: int,
    request: Request,
) -> dict[str, Any]:
    """Soft-delete an endorsement.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        endorsement_id: PK of the endorsement row.
        request: Incoming FastAPI request.

    Returns:
        ``{"id": int, "removed_at": str}``.  Idempotent on
        already-removed rows (returns the existing
        ``removed_at`` unchanged).

    Raises:
        ResourceNotFoundError.not_found: 404 when the endorsement
            is missing or scoped to a different product.
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
            raise ResourceNotFoundError.not_found(what=f"endorsement id={endorsement_id}")
        _check_gate(user, row, endorsement.endorsement_type)
        if endorsement.removed_at is None:
            endorsement.removed_at = datetime.datetime.now(datetime.UTC)
            session.add(endorsement)
            session.commit()
            session.refresh(endorsement)

    mirror_social_to_audit(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action="endorsement.removed",
        entity_kind="dp",
        entity_ref=f"{catalog}.{schema}",
        detail={
            "endorsement_type": endorsement.endorsement_type,
            "endorsement_id": endorsement.id,
        },
        workspace_id=workspace_id,
    )
    return {
        "id": endorsement.id,
        "removed_at": (endorsement.removed_at.isoformat() if endorsement.removed_at else None),
    }
