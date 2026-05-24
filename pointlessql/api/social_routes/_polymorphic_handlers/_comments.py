"""Comment list / post / soft-delete handlers.

Each axis lives in its own sub-module now while the
public handler names re-export from the package facade.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from fastapi import Request
from sqlalchemy import select

from pointlessql.api._social_serializers import agent_payload
from pointlessql.api.data_products_routes._shared import (
    resolve_agent_for_principal,
)
from pointlessql.api.dependencies import (
    get_user,
    require_user,
)
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    ALLOWED_CATEGORIES,
    ALLOWED_EMOJI,
    DISCUSSION_DELETED,
    DISCUSSION_POSTED,
    MAX_THREAD_DEPTH,
    body_preview,
    chain_depth,
    collect_reactions,
    extract_mention_emails,
    resolve_mention_ids,
    resolve_target_id,
    serialise_comment,
)
from pointlessql.exceptions import (
    AuthorizationError,
    BadRequestError,
    ResourceNotFoundError,
)
from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.services.notifications.fanout import fanout_event
from pointlessql.services.social import (
    resolve_citations,
)
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.social.entity_registry import (
    get as registry_get,
)
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_COMMENTED,
    emit_governance_event,
)

# ---------------------------------------------------------------------------
# Comments
# ---------------------------------------------------------------------------


async def list_polymorphic_comments(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return every live comment on the polymorphic entity.

    Args:
        kind: Entity kind discriminator (e.g. ``'table'``,
            ``'branch'``).
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind": str, "entity_ref": str, "comments": [...]}``.
        Empty list when the entity has no live comments yet.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductComment)
                .where(
                    DataProductComment.workspace_id == workspace_id,
                    DataProductComment.social_target_id == target_id,
                )
                .order_by(
                    DataProductComment.parent_comment_id.nulls_first(),
                    DataProductComment.created_at,
                )
            )
            .scalars()
            .all()
        )
        author_ids = {c.author_user_id for c in rows}
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
        agent_ids = {
            c.author_agent_id
            for c in rows
            if c.author_agent_id is not None
        }
        agent_map: dict[int, dict[str, Any] | None] = {}
        if agent_ids:
            agents = (
                session.execute(select(Agent).where(Agent.id.in_(agent_ids)))
                .scalars()
                .all()
            )
            agent_map = {a.id: agent_payload(a) for a in agents}
        reactions_by_comment = collect_reactions(
            session, [c.id for c in rows], user["id"]
        )

    live_children_by_parent: dict[int, int] = {}
    for c in rows:
        if c.parent_comment_id is not None and c.deleted_at is None:
            live_children_by_parent[c.parent_comment_id] = (
                live_children_by_parent.get(c.parent_comment_id, 0) + 1
            )

    payload: list[dict[str, Any]] = []
    for c in rows:
        if c.deleted_at is not None and not live_children_by_parent.get(c.id):
            continue
        author_email, author_display = author_map.get(
            c.author_user_id, (None, None)
        )
        comment_agent_payload = (
            agent_map.get(c.author_agent_id)
            if c.author_agent_id is not None
            else None
        )
        body_md_resolved = (
            ""
            if c.deleted_at
            else resolve_citations(c.body_md, factory, workspace_id)
        )
        payload.append(
            serialise_comment(
                c,
                author_email=author_email,
                author_display_name=author_display,
                body_md_resolved=body_md_resolved,
                agent=comment_agent_payload,
                reactions=reactions_by_comment.get(c.id),
            )
        )

    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "social_target_id": target_id,
        "comments": payload,
    }


async def post_polymorphic_comment(
    kind: str,
    ref: str,
    request: Request,
    *,
    as_agent: str | None = None,
) -> dict[str, Any]:
    """Create a comment on the polymorphic entity.

    Body: ``{"body_md": str, "parent_comment_id": int | None,
    "category": str | None}``.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.
        as_agent: Optional agent slug — when set, the caller posts
            *on behalf of* that agent and ``author_agent_id`` lands
            on the row.  Phase 101 review-loop closure: ungated the
            DP-only flow so cell-level review decisions
            authored by ``hermes`` plugin (and other notebook
            entities) carry the same presentation-layer envelope.
            The principal-or-admin gate in
            :func:`resolve_agent_for_principal` still applies.

    Returns:
        Serialised comment row.

    Raises:
        BadRequestError: On empty body, missing parent, unknown
            category, or over-deep nesting.
        ResourceNotFoundError: When ``as_agent`` slug does not
            resolve.  Indirect: also raised inside
            :func:`resolve_agent_for_principal` for unauthorised
            ``as_agent`` callers (surfaces as 403 via the global
            handler).
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    author_agent_id: int | None = None
    if as_agent is not None:
        author_agent_id = resolve_agent_for_principal(
            factory, workspace_id=workspace_id, slug=as_agent, user=user
        )

    body = await request.json()
    body_md = (body.get("body_md") or "").strip()
    if not body_md:
        raise BadRequestError("body_md is required")
    parent_comment_id_raw = body.get("parent_comment_id")
    parent_comment_id = (
        int(parent_comment_id_raw)
        if parent_comment_id_raw is not None
        else None
    )
    requested_category_raw = body.get("category")
    requested_category = (
        str(requested_category_raw).strip().lower()
        if requested_category_raw is not None
        else None
    )
    if (
        requested_category is not None
        and requested_category not in ALLOWED_CATEGORIES
    ):
        raise BadRequestError(
            f"category must be one of {ALLOWED_CATEGORIES}"
        )

    with factory() as session:
        if parent_comment_id is not None:
            parent = session.get(DataProductComment, parent_comment_id)
            if (
                parent is None
                or parent.workspace_id != workspace_id
                or parent.social_target_id != target_id
            ):
                raise BadRequestError(
                    "parent_comment_id refers to an unknown comment"
                )
            if chain_depth(session, parent_comment_id) >= MAX_THREAD_DEPTH:
                raise BadRequestError(
                    f"thread depth exceeds {MAX_THREAD_DEPTH}"
                )
            effective_category = parent.category
        else:
            effective_category = requested_category or "general"

        mention_ids = resolve_mention_ids(
            session, extract_mention_emails(body_md)
        )
        now = datetime.datetime.now(datetime.UTC)
        comment = DataProductComment(
            workspace_id=workspace_id,
            data_product_id=None,
            social_target_id=target_id,
            parent_comment_id=parent_comment_id,
            author_user_id=user["id"],
            author_agent_id=author_agent_id,
            body_md=body_md,
            mentioned_user_ids_json=json.dumps(mention_ids),
            category=effective_category,
            is_accepted_answer=False,
            created_at=now,
        )
        session.add(comment)
        session.commit()
        session.refresh(comment)
        comment_id = int(comment.id)

        author_row = session.get(User, comment.author_user_id)
        author_email = author_row.email if author_row else None
        author_display = author_row.display_name if author_row else None
        agent_envelope: dict[str, Any] | None = None
        if author_agent_id is not None:
            agent_row = session.get(Agent, author_agent_id)
            if agent_row is not None:
                agent_envelope = agent_payload(agent_row)

    mirror_social_to_audit(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action=DISCUSSION_POSTED,
        entity_kind=kind,
        entity_ref=ref,
        suffix=f"tab-discussion-comment-{comment_id}",
        detail={
            "comment_id": comment_id,
            "parent_comment_id": parent_comment_id,
            "body_preview": body_preview(body_md),
            "body_md": body_md,
        },
        workspace_id=workspace_id,
    )

    spec = registry_get(kind)
    source_url = (
        f"{spec.url_for(ref)}#tab-discussion-comment-{comment_id}"
    )
    summary = f"@{author_email or 'someone'} commented on {kind}:{ref}"
    fanout_event(
        factory,
        event_type=EVENT_TYPE_DATA_PRODUCT_COMMENTED,
        entity_kind=kind,
        entity_ref=ref,
        workspace_id=workspace_id,
        actor_user_id=user["id"],
        source_url=source_url,
        summary_md=summary,
        data_product_id=None,
        extra_recipients=mention_ids,
    )
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_COMMENTED,
        {
            "entity_kind": kind,
            "entity_ref": ref,
            "comment_id": comment_id,
            "author_user_id": user["id"],
            "author_email": author_email,
            "mentioned_user_ids": mention_ids,
            "parent_comment_id": parent_comment_id,
        },
        settings=request.app.state.settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )

    return serialise_comment(
        comment,
        author_email=author_email,
        author_display_name=author_display,
        body_md_resolved=resolve_citations(body_md, factory, workspace_id),
        agent=agent_envelope,
        reactions=[
            {"emoji": e, "count": 0, "has_current_user_reacted": False}
            for e in ALLOWED_EMOJI
        ],
    )


async def delete_polymorphic_comment(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Soft-delete a comment by setting ``deleted_at``.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        comment_id: PK of the comment to soft-delete.
        request: Incoming FastAPI request.

    Returns:
        ``{"id": int, "deleted_at": str}``.

    Raises:
        AuthorizationError: When the caller is neither author nor
            install-admin.  Non-DP entities have no per-entity
            steward concept, so only the author and admin can
            delete.
        ResourceNotFoundError: When the comment is missing or
            scoped to a different entity.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        comment = session.get(DataProductComment, comment_id)
        if (
            comment is None
            or comment.workspace_id != workspace_id
            or comment.social_target_id != target_id
        ):
            raise ResourceNotFoundError.not_found(
                what=f"comment id={comment_id}"
            )

        is_author = comment.author_user_id == user["id"]
        is_admin = bool(user.get("is_admin"))
        if not (is_author or is_admin):
            raise AuthorizationError(
                principal=user.get("email", ""),
                privilege="soft-delete",
                securable_type=f"{kind}_comment",
                full_name=str(comment_id),
            )

        was_already_deleted = comment.deleted_at is not None
        if comment.deleted_at is None:
            comment.deleted_at = datetime.datetime.now(datetime.UTC)
            session.add(comment)
            session.commit()
            session.refresh(comment)

    if not was_already_deleted:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action=DISCUSSION_DELETED,
            entity_kind=kind,
            entity_ref=ref,
            suffix=f"tab-discussion-comment-{comment_id}",
            detail={"comment_id": comment_id},
            workspace_id=workspace_id,
        )

    return {
        "id": int(comment.id),
        "deleted_at": (
            comment.deleted_at.isoformat() if comment.deleted_at else None
        ),
    }


