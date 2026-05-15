"""Kind-agnostic social-write handlers (Phase 77.1.5).

The Phase-76 DP routes do an awful lot of work — mention
resolution, threading, soft-delete gating, audit-mirroring,
governance fan-out — that is intrinsically *not* DP-specific.
The DP handlers couple it to ``(catalog, schema)`` only because
the social tables historically pointed at ``data_products.id``.

After Phase 77.0.G the social tables are anchored on
``social_target_id`` (nullable ``data_product_id`` back-pointer
for DP rows only).  Phase 77.1.5 lifts the per-axis write
paths out into this module so any registered entity kind
(currently ``table`` + ``branch``) can use them.  The DP routes
stay unchanged — duplication lives until Phase 77.11 unifies.

Locked decisions reflected here:

* **Audit prefix** is built via the entity registry, so the
  generic ``{kind}:{ref}#...`` form lands automatically for
  table + branch kinds (locked decision #9 keeps the legacy
  ``data_product:`` prefix only for ``kind='dp'``, but those
  rows go through the DP handlers, not this module).
* **Follow** for non-DP kinds returns 501 — the composite-PK
  constraint on ``data_product_follows`` requires a real DP id
  and the polymorphic follow table is a Phase 77.8 deliverable.
* **Reactions** for non-DP kinds aren't wired here either —
  the existing add/remove handlers do a DP lookup; polymorphic
  reactions land in Phase 77.8 alongside follows.
* **Endorsement gate**: any authenticated user may apply or
  remove their own endorsement on table / branch kinds (peer-
  review model).  Admins may remove anyone's row.  The
  branch-promote gate at HTTP boundary is what enforces
  "needs ≥1 peer endorsement" — the apply endpoint stays open.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any

from fastapi import HTTPException, Request
from sqlalchemy import desc, func, select

from pointlessql.api.dependencies import (
    current_workspace_id,
    get_user,
    require_user,
)
from pointlessql.exceptions import AuthorizationError
from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_endorsement import (
    ENDORSEMENT_TYPES,
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.social._entity_readme import EntityReadme
from pointlessql.models.social._social_follow import SocialFollow
from pointlessql.models.social._social_reaction import SocialReaction
from pointlessql.models.social._social_star import SocialStar
from pointlessql.services.notifications.fanout import fanout_event
from pointlessql.services.social import (
    get_or_create_target,
    resolve_citations,
)
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.social.entity_registry import (
    get as registry_get,
)
from pointlessql.services.social.entity_registry import (
    url_for as registry_url_for,
)
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_COMMENTED,
    EVENT_TYPE_DATA_PRODUCT_REVIEWED,
    emit_governance_event,
)

# ---------------------------------------------------------------------------
# Per-axis constants reused from the DP handlers
# ---------------------------------------------------------------------------

_BODY_PREVIEW_LEN = 140
_MAX_THREAD_DEPTH = 5

_DISCUSSION_POSTED = "audit.discussion.posted"
_DISCUSSION_DELETED = "audit.discussion.deleted"
_MENTION_RE = re.compile(r"@([\w.+-]+@[\w-]+\.[\w.-]+)")
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)

ALLOWED_CATEGORIES: tuple[str, ...] = (
    "general",
    "question",
    "announcement",
    "idea",
)
ALLOWED_EMOJI: tuple[str, ...] = ("👍", "❤️", "🎉", "😄", "😕", "👀")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _body_preview(body_md: str) -> str:
    """Truncate a comment body for the audit-log detail JSON."""
    snippet = body_md.strip().replace("\n", " ")
    if len(snippet) > _BODY_PREVIEW_LEN:
        return snippet[: _BODY_PREVIEW_LEN - 1] + "…"
    return snippet


def _extract_mention_emails(body_md: str) -> list[str]:
    """Return ``@email`` mentions in *body_md* with fenced code stripped."""
    stripped = _FENCED_CODE_RE.sub("", body_md)
    return _MENTION_RE.findall(stripped)


def _resolve_mention_ids(session: Any, emails: list[str]) -> list[int]:
    """Map @-mention emails to persisted user ids (case-insensitive)."""
    if not emails:
        return []
    lowered = list({e.lower() for e in emails})
    rows = session.execute(
        select(User.id).where(User.email.in_(lowered))
    ).all()
    return [int(uid) for (uid,) in rows]


def _chain_depth(session: Any, parent_id: int) -> int:
    """Return the depth of the existing reply chain ending at *parent_id*."""
    depth = 1
    current_id: int | None = parent_id
    while current_id is not None and depth <= _MAX_THREAD_DEPTH + 1:
        parent = session.get(DataProductComment, current_id)
        if parent is None or parent.parent_comment_id is None:
            return depth
        current_id = parent.parent_comment_id
        depth += 1
    return depth


def _collect_reactions(
    session: Any, comment_ids: list[int], caller_user_id: int
) -> dict[int, list[dict[str, Any]]]:
    """Return per-comment reaction aggregates keyed by comment id."""
    if not comment_ids:
        return {}
    rows = session.execute(
        select(
            DataProductCommentReaction.comment_id,
            DataProductCommentReaction.emoji,
            DataProductCommentReaction.user_id,
        ).where(DataProductCommentReaction.comment_id.in_(comment_ids))
    ).all()
    counts: dict[int, dict[str, int]] = {}
    mine: dict[int, set[str]] = {}
    for cid, emoji, uid in rows:
        counts.setdefault(cid, {e: 0 for e in ALLOWED_EMOJI})
        if emoji in counts[cid]:
            counts[cid][emoji] += 1
        if uid == caller_user_id:
            mine.setdefault(cid, set()).add(emoji)
    result: dict[int, list[dict[str, Any]]] = {}
    for cid in comment_ids:
        per = counts.get(cid, {e: 0 for e in ALLOWED_EMOJI})
        mine_set = mine.get(cid, set())
        result[cid] = [
            {
                "emoji": e,
                "count": per[e],
                "has_current_user_reacted": e in mine_set,
            }
            for e in ALLOWED_EMOJI
        ]
    return result


def _serialise_comment(
    row: DataProductComment,
    *,
    author_email: str | None,
    author_display_name: str | None,
    body_md_resolved: str,
    reactions: list[dict[str, Any]] | None = None,
    agent: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Render one comment row as a JSON-friendly dict."""
    return {
        "id": row.id,
        "social_target_id": row.social_target_id,
        "parent_comment_id": row.parent_comment_id,
        "author": {
            "user_id": row.author_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "agent": agent,
        "body_md": "" if row.deleted_at else row.body_md,
        "body_md_resolved": body_md_resolved,
        "mentioned_user_ids": json.loads(row.mentioned_user_ids_json or "[]"),
        "category": row.category,
        "is_accepted_answer": bool(row.is_accepted_answer),
        "reactions": reactions if reactions is not None else [],
        "created_at": row.created_at.isoformat(),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


def _serialise_endorsement(
    row: DataProductEndorsement,
    *,
    author_email: str | None,
    author_display_name: str | None,
    note_md_resolved: str,
) -> dict[str, Any]:
    """Render one endorsement row as JSON (no agent payload here)."""
    return {
        "id": row.id,
        "social_target_id": row.social_target_id,
        "endorsement_type": row.endorsement_type,
        "applied_by": {
            "user_id": row.applied_by_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "applied_at": row.applied_at.isoformat(),
        "removed_at": (
            row.removed_at.isoformat() if row.removed_at else None
        ),
        "note_md": row.note_md or "",
        "note_md_resolved": note_md_resolved,
    }


def _serialise_readme(
    row: EntityReadme,
    *,
    author_email: str | None,
    author_display_name: str | None,
) -> dict[str, Any]:
    """Render one README version as JSON."""
    return {
        "id": row.id,
        "social_target_id": row.social_target_id,
        "version_int": row.version_int,
        "body_md": row.body_md,
        "updated_by": {
            "user_id": row.updated_by_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "updated_at": row.updated_at.isoformat(),
    }


def _resolve_target_id(
    request: Request, kind: str, ref: str
) -> tuple[int, int]:
    """Resolve ``(workspace_id, social_target_id)`` for the kind+ref.

    For ``kind='dp'`` routes through :func:`resolve_dp_target` so the
    ``data_product_id`` back-pointer gets populated correctly; the
    plain :func:`get_or_create_target` requires the caller to know
    that id upfront, which the polymorphic Star / Follow paths
    don't until they resolve the DP themselves.

    Args:
        request: Active FastAPI request — used for workspace scope.
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.

    Returns:
        Tuple of ``(workspace_id, social_target_id)``.  The anchor
        row is created on demand if it does not yet exist.

    Raises:
        HTTPException: 404 when ``kind='dp'`` and no DataProduct
            exists at the requested ``catalog.schema``.
    """
    from pointlessql.services.social._target_resolver import resolve_dp_target

    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
        if kind == "dp":
            parts = ref.split(".", 1)
            if len(parts) != 2 or not all(parts):
                # bare-http-ok: ref shape is the API contract.
                raise HTTPException(
                    status_code=400,
                    detail="kind='dp' ref must be 'catalog.schema'",
                )
            try:
                target = resolve_dp_target(
                    session,
                    workspace_id=workspace_id,
                    catalog_name=parts[0],
                    schema_name=parts[1],
                )
            except LookupError as exc:
                # bare-http-ok: DP not found in this workspace.
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        else:
            target = get_or_create_target(
                session,
                workspace_id=workspace_id,
                kind=kind,
                ref=ref,
            )
        session.commit()
        return workspace_id, int(target.id)


def _readme_supported(kind: str) -> None:
    """Raise 404 when *kind* has ``supports_readme=False``.

    Branches return ``supports_readme=False`` in the registry —
    the README endpoints would silently succeed otherwise because
    the underlying table has no kind gate.  We surface a clean
    404 so the client knows there's no READMEs for this entity.
    """
    spec = registry_get(kind)
    if not spec.supports_readme:
        # bare-http-ok: READMEs are entity-kind opt-in.
        raise HTTPException(
            status_code=404,
            detail=f"kind={kind!r} does not support READMEs",
        )


def _endorsements_supported(kind: str) -> None:
    """Raise 404 when *kind* has ``supports_endorsements=False``."""
    spec = registry_get(kind)
    if not spec.supports_endorsements:
        # bare-http-ok: endorsements are entity-kind opt-in.
        raise HTTPException(
            status_code=404,
            detail=f"kind={kind!r} does not support endorsements",
        )


def _reviews_supported(kind: str) -> None:
    """Raise 501 when *kind* has ``supports_reviews=False``."""
    spec = registry_get(kind)
    if not spec.supports_reviews:
        # bare-http-ok: reviews are entity-kind opt-in.
        raise HTTPException(
            status_code=501,
            detail=(
                f"kind={kind!r} does not support reviews "
                "(supports_reviews=False in the entity registry)"
            ),
        )


def _serialise_review(
    row: DataProductReview,
    *,
    author_email: str | None,
    author_display_name: str | None,
    body_md_resolved: str,
) -> dict[str, Any]:
    """Render one polymorphic review row as JSON.

    Mirrors the DP-route serialiser shape minus the ``agent``
    payload — agent-on-behalf-of authoring is a DP-only affordance
    today and lifting it polymorphic-wide is a Phase 77.11 ask.
    The ``data_product_id`` field stays in the payload for backward
    JSON-shape compat; it is ``None`` for non-DP kinds.
    """
    return {
        "id": row.id,
        "data_product_id": row.data_product_id,
        "social_target_id": row.social_target_id,
        "author": {
            "user_id": row.author_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "agent": None,
        "stars": row.stars,
        "body_md": row.body_md,
        "body_md_resolved": body_md_resolved,
        "dp_version_at_review": row.dp_version_at_review,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


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
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
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
        agent_map: dict[int, dict[str, Any]] = {}
        if agent_ids:
            agents = (
                session.execute(select(Agent).where(Agent.id.in_(agent_ids)))
                .scalars()
                .all()
            )
            agent_map = {
                a.id: {
                    "slug": a.slug,
                    "display_name": a.display_name,
                    "avatar_kind": a.avatar_kind,
                    "is_verified": bool(a.is_verified),
                    "principal_user_id": a.principal_user_id,
                }
                for a in agents
            }
        reactions_by_comment = _collect_reactions(
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
        agent_payload = (
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
            _serialise_comment(
                c,
                author_email=author_email,
                author_display_name=author_display,
                body_md_resolved=body_md_resolved,
                agent=agent_payload,
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
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Create a comment on the polymorphic entity.

    Body: ``{"body_md": str, "parent_comment_id": int | None,
    "category": str | None}``.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        Serialised comment row.

    Raises:
        HTTPException: 400 on empty body, missing parent,
            unknown category, or over-deep nesting.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    body = await request.json()
    body_md = (body.get("body_md") or "").strip()
    if not body_md:
        # bare-http-ok: request body is required.
        raise HTTPException(status_code=400, detail="body_md is required")
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
        # bare-http-ok: category must be one of the canonical four.
        raise HTTPException(
            status_code=400,
            detail=f"category must be one of {ALLOWED_CATEGORIES}",
        )

    with factory() as session:
        if parent_comment_id is not None:
            parent = session.get(DataProductComment, parent_comment_id)
            if (
                parent is None
                or parent.workspace_id != workspace_id
                or parent.social_target_id != target_id
            ):
                # bare-http-ok: parent must exist on the same entity.
                raise HTTPException(
                    status_code=400,
                    detail="parent_comment_id refers to an unknown comment",
                )
            if _chain_depth(session, parent_comment_id) >= _MAX_THREAD_DEPTH:
                # bare-http-ok: enforce thread-depth ceiling.
                raise HTTPException(
                    status_code=400,
                    detail=f"thread depth exceeds {_MAX_THREAD_DEPTH}",
                )
            effective_category = parent.category
        else:
            effective_category = requested_category or "general"

        mention_ids = _resolve_mention_ids(
            session, _extract_mention_emails(body_md)
        )
        now = datetime.datetime.now(datetime.UTC)
        comment = DataProductComment(
            workspace_id=workspace_id,
            data_product_id=None,
            social_target_id=target_id,
            parent_comment_id=parent_comment_id,
            author_user_id=user["id"],
            author_agent_id=None,
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

    mirror_social_to_audit(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action=_DISCUSSION_POSTED,
        entity_kind=kind,
        entity_ref=ref,
        suffix=f"tab-discussion-comment-{comment_id}",
        detail={
            "comment_id": comment_id,
            "parent_comment_id": parent_comment_id,
            "body_preview": _body_preview(body_md),
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

    return _serialise_comment(
        comment,
        author_email=author_email,
        author_display_name=author_display,
        body_md_resolved=resolve_citations(body_md, factory, workspace_id),
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
        HTTPException: 404 when the comment is missing or scoped
            to a different entity.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        comment = session.get(DataProductComment, comment_id)
        if (
            comment is None
            or comment.workspace_id != workspace_id
            or comment.social_target_id != target_id
        ):
            # bare-http-ok: cross-entity ids 404.
            raise HTTPException(
                status_code=404, detail="comment not found"
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
            action=_DISCUSSION_DELETED,
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
    _endorsements_supported(kind)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
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
        _serialise_endorsement(
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
        HTTPException: 400 when ``endorsement_type`` is missing or
            outside the typed allow-list.
    """
    require_user(request)
    user = get_user(request)
    _endorsements_supported(kind)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

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
            return _serialise_endorsement(
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
    return _serialise_endorsement(
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
        HTTPException: 404 when the endorsement is missing or
            scoped to a different entity.
        AuthorizationError: When the caller is neither the original
            applier nor an install-admin.
    """
    require_user(request)
    user = get_user(request)
    _endorsements_supported(kind)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        endorsement = session.get(DataProductEndorsement, endorsement_id)
        if (
            endorsement is None
            or endorsement.workspace_id != workspace_id
            or endorsement.social_target_id != target_id
        ):
            # bare-http-ok: cross-entity ids 404.
            raise HTTPException(
                status_code=404, detail="endorsement not found"
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


# ---------------------------------------------------------------------------
# Followers
# ---------------------------------------------------------------------------


async def get_polymorphic_followers_count(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return the follower count + caller-following flag (Phase 77.8).

    Counts rows on the polymorphic ``social_follows`` table for
    ``social_target_id == target_id``.  The ``following`` flag
    reports whether the caller has an outstanding follow row.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"count": int, "following": bool}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        count = session.execute(
            select(func.count(SocialFollow.user_id)).where(
                SocialFollow.workspace_id == workspace_id,
                SocialFollow.social_target_id == target_id,
            )
        ).scalar_one()
        mine = session.get(
            SocialFollow,
            {
                "workspace_id": workspace_id,
                "social_target_id": target_id,
                "user_id": user["id"],
            },
        )
    return {"count": int(count), "following": mine is not None}


async def list_polymorphic_followers(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return the follower roster for the polymorphic entity (Phase 77.8).

    The list is gated to the caller themselves + workspace admins —
    privacy mirrors the DP follower list.  Non-admin callers see an
    empty ``followers`` array but accurate ``count``.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "followers": [...]}`` where
        each follower entry carries ``user_id``, ``email``,
        ``display_name`` and the ``created_at`` of the follow row.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        is_admin = bool(user.get("is_admin"))
        if not is_admin:
            return {
                "entity_kind": kind,
                "entity_ref": ref,
                "followers": [],
            }
        rows = session.execute(
            select(SocialFollow, User)
            .join(User, User.id == SocialFollow.user_id)
            .where(
                SocialFollow.workspace_id == workspace_id,
                SocialFollow.social_target_id == target_id,
            )
            .order_by(SocialFollow.created_at.desc())
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
    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "followers": followers,
    }


async def follow_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Idempotently follow a polymorphic entity (Phase 77.8).

    Writes one row to ``social_follows``.  Repeat POSTs no-op via
    the composite-PK ``(workspace_id, social_target_id, user_id)``.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"followed": True, "already": bool}`` — ``already`` is
        true on the second consecutive POST.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        existing = session.get(
            SocialFollow,
            {
                "workspace_id": workspace_id,
                "social_target_id": target_id,
                "user_id": user["id"],
            },
        )
        if existing is not None:
            return {"followed": True, "already": True}
        session.add(
            SocialFollow(
                workspace_id=workspace_id,
                social_target_id=target_id,
                user_id=user["id"],
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    return {"followed": True, "already": False}


async def unfollow_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Idempotently unfollow a polymorphic entity (Phase 77.8).

    Drops the matching ``social_follows`` row if present.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"followed": False, "removed": bool}`` — ``removed`` is
        true on the call that actually dropped a row.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        existing = session.get(
            SocialFollow,
            {
                "workspace_id": workspace_id,
                "social_target_id": target_id,
                "user_id": user["id"],
            },
        )
        if existing is None:
            return {"followed": False, "removed": False}
        session.delete(existing)
        session.commit()
    return {"followed": False, "removed": True}


# ---------------------------------------------------------------------------
# Entity-level reactions (Phase 77.8.C UNIQUE + 77.8.D handlers)
# ---------------------------------------------------------------------------


def _validate_emoji_field(emoji: str | None) -> str:
    """Normalise + validate a reaction emoji against the GitHub-6 set."""
    if not emoji or emoji not in ALLOWED_EMOJI:
        # bare-http-ok: emoji is a fixed allow-list.
        raise HTTPException(
            status_code=400,
            detail=f"emoji must be one of {ALLOWED_EMOJI}",
        )
    return emoji


async def list_polymorphic_reactions(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return aggregated entity-level reactions for a polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "reactions": [...]}`` where
        each row is ``{"emoji", "count", "has_current_user_reacted"}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    del workspace_id
    factory = request.app.state.session_factory

    with factory() as session:
        rows = session.execute(
            select(
                SocialReaction.emoji,
                SocialReaction.user_id,
            ).where(SocialReaction.social_target_id == target_id)
        ).all()

    counts: dict[str, int] = {e: 0 for e in ALLOWED_EMOJI}
    mine: set[str] = set()
    for emoji_row, uid in rows:
        if emoji_row in counts:
            counts[emoji_row] += 1
        if uid == user["id"]:
            mine.add(emoji_row)

    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "reactions": [
            {
                "emoji": e,
                "count": counts[e],
                "has_current_user_reacted": e in mine,
            }
            for e in ALLOWED_EMOJI
        ],
    }


async def apply_polymorphic_reaction(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Add an emoji reaction on a polymorphic entity (Phase 77.8.D).

    Idempotency is enforced by the
    ``uq_dp_reactions_polymorphic`` UNIQUE constraint that 77.8.C
    added (legacy DP-id PK is unable to dedupe rows with NULL
    ``data_product_id``).  Re-applying the same emoji no-ops.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "emoji", "added": bool}``.
    """
    from sqlalchemy.exc import IntegrityError

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    payload = await request.json()
    emoji = _validate_emoji_field(payload.get("emoji"))

    added = False
    with factory() as session:
        try:
            session.add(
                SocialReaction(
                    workspace_id=workspace_id,
                    social_target_id=target_id,
                    user_id=user["id"],
                    emoji=emoji,
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
            session.commit()
            added = True
        except IntegrityError:
            session.rollback()
            added = False

    if added:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.reaction.dp_added",
            entity_kind=kind,
            entity_ref=ref,
            detail={"emoji": emoji},
            workspace_id=workspace_id,
        )

    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "emoji": emoji,
        "added": added,
    }


async def remove_polymorphic_reaction(
    kind: str, ref: str, emoji: str, request: Request
) -> dict[str, Any]:
    """Remove the caller's emoji reaction on a polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        emoji: The emoji to remove (must be in the allow-list).
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "emoji", "removed": bool}``.
    """
    from sqlalchemy import delete as _delete

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory
    emoji = _validate_emoji_field(emoji)

    removed = False
    with factory() as session:
        result = session.execute(
            _delete(SocialReaction).where(
                SocialReaction.social_target_id == target_id,
                SocialReaction.user_id == user["id"],
                SocialReaction.emoji == emoji,
            )
        )
        session.commit()
        removed = bool(result.rowcount)

    if removed:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.reaction.dp_removed",
            entity_kind=kind,
            entity_ref=ref,
            detail={"emoji": emoji},
            workspace_id=workspace_id,
        )
    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "emoji": emoji,
        "removed": removed,
    }


# ---------------------------------------------------------------------------
# Comment reactions (Phase 78 polish — polymorphism unlock)
# ---------------------------------------------------------------------------


def _load_comment_on_target(
    session: Any, comment_id: int, *, workspace_id: int, target_id: int
) -> DataProductComment:
    """Return the live comment row that belongs to the social target.

    The comment must live in the same workspace and reference the
    same ``social_target_id`` as the kind/ref the caller addressed.
    Soft-deleted comments are treated as missing.
    """
    comment = session.get(DataProductComment, comment_id)
    if (
        comment is None
        or comment.workspace_id != workspace_id
        or comment.social_target_id != target_id
        or comment.deleted_at is not None
    ):
        # bare-http-ok: target comment must exist + be live on this entity.
        raise HTTPException(status_code=404, detail="comment not found")
    return comment


async def apply_polymorphic_comment_reaction(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Add an emoji reaction to a comment on any entity kind.

    Idempotent: re-applying the same triple is a no-op.  The
    comment author is pinged via :func:`fanout_event` regardless
    of kind (mirrors the DP-only path landed in Phase 76.1).

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        comment_id: PK of the comment being reacted to.
        request: Incoming FastAPI request.

    Returns:
        ``{"comment_id", "emoji", "added": bool}``.
    """
    from sqlalchemy.exc import IntegrityError

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    payload = await request.json()
    emoji = _validate_emoji_field(payload.get("emoji"))

    added = False
    comment_author_id: int | None = None
    dp_back_pointer: int | None = None
    with factory() as session:
        comment = _load_comment_on_target(
            session, comment_id, workspace_id=workspace_id, target_id=target_id
        )
        comment_author_id = int(comment.author_user_id)
        dp_back_pointer = (
            int(comment.data_product_id)
            if kind == "dp" and comment.data_product_id is not None
            else None
        )
        try:
            session.add(
                DataProductCommentReaction(
                    comment_id=comment_id,
                    social_target_id=target_id,
                    user_id=user["id"],
                    emoji=emoji,
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
            session.commit()
            added = True
        except IntegrityError:
            session.rollback()
            added = False

    if added:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.reaction.comment_added",
            entity_kind=kind,
            entity_ref=ref,
            suffix=f"tab-discussion-comment-{comment_id}",
            detail={"comment_id": comment_id, "emoji": emoji},
            workspace_id=workspace_id,
        )
        if comment_author_id != user["id"]:
            source_url = (
                f"{registry_url_for(kind, ref)}"
                f"#tab-discussion-comment-{comment_id}"
            )
            summary = (
                f"@{user.get('email') or 'someone'} reacted "
                f"{emoji} to your comment on {ref}"
            )
            fanout_event(
                factory,
                event_type="pointlessql.data_product.comment_reacted",
                entity_kind=kind,
                entity_ref=ref,
                workspace_id=workspace_id,
                actor_user_id=user["id"],
                source_url=source_url,
                summary_md=summary,
                data_product_id=dp_back_pointer,
                extra_recipients=[comment_author_id],
            )

    return {"comment_id": comment_id, "emoji": emoji, "added": added}


async def remove_polymorphic_comment_reaction(
    kind: str, ref: str, comment_id: int, emoji: str, request: Request
) -> dict[str, Any]:
    """Remove the caller's emoji reaction on a comment.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        comment_id: PK of the comment.
        emoji: The emoji to remove.
        request: Incoming FastAPI request.

    Returns:
        ``{"comment_id", "emoji", "removed": bool}``.
    """
    from sqlalchemy import delete as _delete

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory
    emoji = _validate_emoji_field(emoji)

    removed = False
    with factory() as session:
        _load_comment_on_target(
            session, comment_id, workspace_id=workspace_id, target_id=target_id
        )
        result = session.execute(
            _delete(DataProductCommentReaction).where(
                DataProductCommentReaction.comment_id == comment_id,
                DataProductCommentReaction.user_id == user["id"],
                DataProductCommentReaction.emoji == emoji,
            )
        )
        session.commit()
        removed = bool(result.rowcount)

    if removed:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.reaction.comment_removed",
            entity_kind=kind,
            entity_ref=ref,
            suffix=f"tab-discussion-comment-{comment_id}",
            detail={"comment_id": comment_id, "emoji": emoji},
            workspace_id=workspace_id,
        )
    return {"comment_id": comment_id, "emoji": emoji, "removed": removed}


async def list_polymorphic_comment_reactions(
    kind: str, ref: str, comment_id: int, request: Request
) -> dict[str, Any]:
    """Return aggregated reaction counts for a comment on any kind.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        comment_id: PK of the comment.
        request: Incoming FastAPI request.

    Returns:
        ``{"comment_id", "reactions": [{emoji, count,
        has_current_user_reacted}, ...]}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        _load_comment_on_target(
            session, comment_id, workspace_id=workspace_id, target_id=target_id
        )
        rows = session.execute(
            select(
                DataProductCommentReaction.emoji,
                DataProductCommentReaction.user_id,
            ).where(DataProductCommentReaction.comment_id == comment_id)
        ).all()

    counts: dict[str, int] = {e: 0 for e in ALLOWED_EMOJI}
    mine: set[str] = set()
    for emoji_row, uid in rows:
        if emoji_row in counts:
            counts[emoji_row] += 1
        if uid == user["id"]:
            mine.add(emoji_row)

    return {
        "comment_id": comment_id,
        "reactions": [
            {
                "emoji": e,
                "count": counts[e],
                "has_current_user_reacted": e in mine,
            }
            for e in ALLOWED_EMOJI
        ],
    }


# ---------------------------------------------------------------------------
# Stars (Phase 77.8)
# ---------------------------------------------------------------------------


async def get_polymorphic_star(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return the star count for the entity + whether caller starred it.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"starred": bool, "count": int}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        count = session.execute(
            select(func.count(SocialStar.user_id)).where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.social_target_id == target_id,
            )
        ).scalar_one()
        mine = session.get(
            SocialStar,
            {
                "workspace_id": workspace_id,
                "user_id": user["id"],
                "social_target_id": target_id,
            },
        )
    return {"starred": mine is not None, "count": int(count)}


async def star_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Idempotently star a polymorphic entity (Phase 77.8).

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"starred": True, "count": int}`` — the updated count
        reflects the post-write state.
    """
    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        existing = session.get(
            SocialStar,
            {
                "workspace_id": workspace_id,
                "user_id": user["id"],
                "social_target_id": target_id,
            },
        )
        first_star = existing is None
        if first_star:
            session.add(
                SocialStar(
                    workspace_id=workspace_id,
                    user_id=user["id"],
                    social_target_id=target_id,
                    created_at=datetime.datetime.now(datetime.UTC),
                )
            )
            session.commit()
        count = session.execute(
            select(func.count(SocialStar.user_id)).where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.social_target_id == target_id,
            )
        ).scalar_one()

    if first_star:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.star.added",
            entity_kind=kind,
            entity_ref=ref,
            detail={},
            workspace_id=workspace_id,
        )
    return {"starred": True, "count": int(count)}


async def unstar_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Idempotently unstar a polymorphic entity (Phase 77.8)."""
    from sqlalchemy import delete as _delete

    require_user(request)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        result = session.execute(
            _delete(SocialStar).where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.user_id == user["id"],
                SocialStar.social_target_id == target_id,
            )
        )
        session.commit()
        removed = bool(result.rowcount)
        count = session.execute(
            select(func.count(SocialStar.user_id)).where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.social_target_id == target_id,
            )
        ).scalar_one()

    if removed:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action="audit.star.removed",
            entity_kind=kind,
            entity_ref=ref,
            detail={},
            workspace_id=workspace_id,
        )
    return {"starred": False, "count": int(count)}


async def list_user_stars(
    user_id: int, request: Request, kind: str | None = None, limit: int = 50
) -> dict[str, Any]:
    """Return the starred-entity list for a given user.

    Args:
        user_id: Target user whose stars to list.  Only the caller
            themselves or an admin may list anyone else's stars.
        request: Incoming FastAPI request.
        kind: Optional filter to a single entity kind.
        limit: Max number of rows to return.

    Returns:
        ``{"user_id", "count", "stars": [...]}``.

    Raises:
        AuthorizationError: When the caller is not the target user
            and not an admin.
    """
    from pointlessql.models.social._social_target import SocialTarget

    require_user(request)
    caller = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory

    if caller["id"] != user_id and not bool(caller.get("is_admin")):
        raise AuthorizationError(
            principal=caller.get("email", ""),
            privilege="stars-list",
            securable_type="user",
            full_name=str(user_id),
        )

    with factory() as session:
        stmt = (
            select(SocialStar, SocialTarget)
            .join(SocialTarget, SocialTarget.id == SocialStar.social_target_id)
            .where(
                SocialStar.workspace_id == workspace_id,
                SocialStar.user_id == user_id,
            )
            .order_by(desc(SocialStar.created_at))
            .limit(limit)
        )
        if kind is not None:
            stmt = stmt.where(SocialTarget.entity_kind == kind)
        rows = session.execute(stmt).all()
    stars = [
        {
            "entity_kind": target.entity_kind,
            "entity_ref": target.entity_ref,
            "starred_at": star.created_at.isoformat(),
        }
        for star, target in rows
    ]
    return {"user_id": user_id, "count": len(stars), "stars": stars}


# ---------------------------------------------------------------------------
# README
# ---------------------------------------------------------------------------


async def get_polymorphic_readme(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return the latest README for the polymorphic entity.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        Serialised latest README row.

    Raises:
        HTTPException: 404 when the entity has no README yet, or
            when the registry says READMEs aren't supported for
            this kind.
    """
    require_user(request)
    _readme_supported(kind)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
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
            # bare-http-ok: no README yet — clients branch on 404.
            raise HTTPException(status_code=404, detail="no readme")
        author = session.get(User, latest.updated_by_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None
    return _serialise_readme(
        latest,
        author_email=author_email,
        author_display_name=author_display,
    )


async def put_polymorphic_readme(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
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
        HTTPException: 400 when ``body_md`` isn't a string; 404
            when the registry says READMEs aren't supported.
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
    _readme_supported(kind)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    body = await request.json()
    body_md = body.get("body_md", "")
    if not isinstance(body_md, str):
        # bare-http-ok: payload contract — body must be string.
        raise HTTPException(
            status_code=400, detail="body_md must be a string"
        )

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
            return _serialise_readme(
                latest,
                author_email=author.email if author else None,
                author_display_name=(
                    author.display_name if author else None
                ),
            )
        next_version = (
            session.execute(
                select(
                    func.coalesce(
                        func.max(EntityReadme.version_int), 0
                    )
                ).where(
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

    return _serialise_readme(
        new_row,
        author_email=author_email,
        author_display_name=author_display,
    )


# ---------------------------------------------------------------------------
# Reviews (Phase 77.2.1 — polymorphic enable for kind='model')
# ---------------------------------------------------------------------------


async def list_polymorphic_reviews(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return every review on a polymorphic entity + summary.

    Args:
        kind: Entity kind (must have ``supports_reviews=True``).
        ref: Entity reference.
        request: Incoming FastAPI request.

    Returns:
        ``{"social_target_id": int, "summary": {avg_stars, count},
        "my_review": {...} | None, "reviews": [...]}``.

    Raises:
        HTTPException: 501 when *kind* has reviews disabled.
    """  # noqa: DOC502 — raised by _reviews_supported helper
    require_user(request)
    _reviews_supported(kind)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductReview)
                .where(
                    DataProductReview.workspace_id == workspace_id,
                    DataProductReview.social_target_id == target_id,
                )
                .order_by(DataProductReview.created_at.desc())
            )
            .scalars()
            .all()
        )
        author_ids = {r.author_user_id for r in rows}
        author_map: dict[int, tuple[str, str | None]] = {}
        if author_ids:
            users = (
                session.execute(select(User).where(User.id.in_(author_ids)))
                .scalars()
                .all()
            )
            author_map = {u.id: (u.email, u.display_name) for u in users}

        avg_stars, count = (
            session.execute(
                select(
                    func.avg(DataProductReview.stars),
                    func.count(DataProductReview.id),
                ).where(
                    DataProductReview.workspace_id == workspace_id,
                    DataProductReview.social_target_id == target_id,
                )
            )
        ).one()
        summary = {
            "avg_stars": float(avg_stars) if avg_stars is not None else None,
            "count": int(count),
        }

    payload: list[dict[str, Any]] = []
    my_review: dict[str, Any] | None = None
    for r in rows:
        author_email, author_display = author_map.get(
            r.author_user_id, (None, None)
        )
        body_resolved = resolve_citations(
            r.body_md, factory, workspace_id,
        )
        s = _serialise_review(
            r,
            author_email=author_email,
            author_display_name=author_display,
            body_md_resolved=body_resolved,
        )
        payload.append(s)
        if r.author_user_id == user["id"]:
            my_review = s

    return {
        "social_target_id": target_id,
        "summary": summary,
        "my_review": my_review,
        "reviews": payload,
    }


async def upsert_polymorphic_review(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Idempotent upsert of the caller's review on a polymorphic entity.

    Body: ``{"stars": int (1..5), "body_md": str?}``.

    Args:
        kind: Entity kind (must have ``supports_reviews=True``).
        ref: Entity reference.
        request: Incoming FastAPI request.

    Returns:
        Serialised review row.

    Raises:
        HTTPException: 400 on invalid stars or missing payload; 501
            when *kind* has reviews disabled.
    """
    require_user(request)
    _reviews_supported(kind)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    body = await request.json()
    raw_stars = body.get("stars")
    if raw_stars is None:
        # bare-http-ok: required field.
        raise HTTPException(status_code=400, detail="stars is required")
    try:
        stars = int(raw_stars)
    except (TypeError, ValueError):
        # bare-http-ok: stars must be int.
        raise HTTPException(
            status_code=400, detail="stars must be an int"
        ) from None
    if stars < 1 or stars > 5:
        # bare-http-ok: stars range — DB CHECK is the canonical gate.
        raise HTTPException(status_code=400, detail="stars must be in 1..5")
    body_md = (body.get("body_md") or "").strip()

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.execute(
            select(DataProductReview).where(
                DataProductReview.workspace_id == workspace_id,
                DataProductReview.social_target_id == target_id,
                DataProductReview.author_user_id == user["id"],
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.stars = stars
            existing.body_md = body_md
            existing.updated_at = now
            # Polymorphic kinds don't carry a per-row "DP version"
            # the way the DP path does — leave the column at its
            # existing value (it was set on first insert).
            session.add(existing)
            review = existing
        else:
            review = DataProductReview(
                workspace_id=workspace_id,
                data_product_id=None,
                social_target_id=target_id,
                author_user_id=user["id"],
                author_agent_id=None,
                stars=stars,
                body_md=body_md,
                # Non-DP kinds have no DP-style version string;
                # empty is the agreed sentinel until a future
                # entity_version migration generalises the column.
                dp_version_at_review="",
                created_at=now,
                updated_at=now,
            )
            session.add(review)
        session.commit()
        session.refresh(review)

        author = session.get(User, review.author_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None
        review_id = review.id
        review_stars = review.stars

    # Governance + fanout fire on every PUT (including upsert): a
    # star change is something followers want to know about.
    spec = registry_get(kind)
    source_url = f"{spec.url_for(ref)}#tab-reviews"
    summary = f"@{author_email or 'someone'} reviewed {ref} ({stars}/5)"
    fanout_event(
        factory,
        event_type=EVENT_TYPE_DATA_PRODUCT_REVIEWED,
        entity_kind=kind,
        entity_ref=ref,
        workspace_id=workspace_id,
        actor_user_id=user["id"],
        source_url=source_url,
        summary_md=summary,
        data_product_id=None,
    )
    governance_payload: dict[str, Any] = {
        "entity_kind": kind,
        "entity_ref": ref,
        "social_target_id": target_id,
        "review_id": review_id,
        "author_user_id": user["id"],
        "author_email": author_email,
        "stars": review_stars,
        "actor_kind": "user",
    }
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_REVIEWED,
        governance_payload,
        settings=request.app.state.settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )

    return _serialise_review(
        review,
        author_email=author_email,
        author_display_name=author_display,
        body_md_resolved=resolve_citations(
            review.body_md, factory, workspace_id,
        ),
    )


async def delete_polymorphic_review(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Remove the caller's review on a polymorphic entity.

    Self only — there is no per-entity moderator role for reviews.
    Idempotent on a missing row.

    Args:
        kind: Entity kind (must have ``supports_reviews=True``).
        ref: Entity reference.
        request: Incoming FastAPI request.

    Returns:
        ``{"deleted": bool}``.

    Raises:
        HTTPException: 501 when *kind* has reviews disabled.
    """  # noqa: DOC502 — raised by _reviews_supported helper
    require_user(request)
    _reviews_supported(kind)
    user = get_user(request)
    workspace_id, target_id = _resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    with factory() as session:
        existing = session.execute(
            select(DataProductReview).where(
                DataProductReview.workspace_id == workspace_id,
                DataProductReview.social_target_id == target_id,
                DataProductReview.author_user_id == user["id"],
            )
        ).scalar_one_or_none()
        if existing is None:
            return {"deleted": False}
        session.delete(existing)
        session.commit()
    return {"deleted": True}


__all__: list[str] = [
    "apply_polymorphic_endorsement",
    "apply_polymorphic_reaction",
    "delete_polymorphic_comment",
    "delete_polymorphic_review",
    "follow_polymorphic_entity",
    "get_polymorphic_followers_count",
    "get_polymorphic_readme",
    "get_polymorphic_star",
    "list_polymorphic_comments",
    "list_polymorphic_endorsements",
    "list_polymorphic_followers",
    "list_polymorphic_reactions",
    "list_polymorphic_reviews",
    "list_user_stars",
    "post_polymorphic_comment",
    "put_polymorphic_readme",
    "remove_polymorphic_endorsement",
    "remove_polymorphic_reaction",
    "star_polymorphic_entity",
    "unfollow_polymorphic_entity",
    "unstar_polymorphic_entity",
    "upsert_polymorphic_review",
]
