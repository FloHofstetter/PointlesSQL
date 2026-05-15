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
from pointlessql.models.catalog._data_product_readme import DataProductReadme
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.services.notifications.fanout import fanout_event
from pointlessql.services.social import (
    get_or_create_target,
    resolve_citations,
)
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.social.entity_registry import get as registry_get
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

_NOT_WIRED_FOR_KIND_FOLLOW = (
    "follow / unfollow on non-DP kinds is deferred to Phase 77.8 "
    "(needs a polymorphic followers table)."
)


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
    row: DataProductReadme,
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

    Args:
        request: Active FastAPI request — used for workspace scope.
        kind: Non-DP entity kind discriminator.
        ref: Opaque entity reference within *kind*.

    Returns:
        Tuple of ``(workspace_id, social_target_id)``.  The anchor
        row is created on demand if it does not yet exist.
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    with factory() as session:
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
    """Return the follower count for the polymorphic entity.

    Non-DP follow writes return 501 (the underlying composite-PK
    constraint blocks them; Phase 77.8 introduces a polymorphic
    follow table).  Count read still works — there are simply
    zero rows.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"count": 0, "following": false}`` until 77.8.
    """
    require_user(request)
    # Ensure the target row exists so the count query is consistent
    # with the apply/remove side once 77.8 lands.
    _resolve_target_id(request, kind, ref)
    # Phase 77.1.5: no polymorphic follower rows exist yet — the
    # composite-PK constraint on ``data_product_follows`` requires
    # a real DP id, so non-DP follows can't be written.  Return a
    # bit-stable zero for now so the UI doesn't need a kind switch.
    return {"count": 0, "following": False}


async def list_polymorphic_followers(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Return the (currently empty) follower list for non-DP kinds.

    Args:
        kind: Entity kind discriminator.
        ref: Opaque entity reference within *kind*.
        request: Incoming FastAPI request.

    Returns:
        ``{"entity_kind", "entity_ref", "followers": []}`` — Phase
        77.8 will fill the list once the polymorphic follow table
        lands.
    """
    require_user(request)
    _resolve_target_id(request, kind, ref)
    return {
        "entity_kind": kind,
        "entity_ref": ref,
        "followers": [],
    }


async def follow_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Reject non-DP follow attempts with 501 until Phase 77.8."""
    require_user(request)
    del kind, ref
    # bare-http-ok: deferred per locked decision.
    raise HTTPException(status_code=501, detail=_NOT_WIRED_FOR_KIND_FOLLOW)


async def unfollow_polymorphic_entity(
    kind: str, ref: str, request: Request
) -> dict[str, Any]:
    """Reject non-DP unfollow attempts with 501 until Phase 77.8."""
    require_user(request)
    del kind, ref
    # bare-http-ok: deferred per locked decision.
    raise HTTPException(status_code=501, detail=_NOT_WIRED_FOR_KIND_FOLLOW)


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
            select(DataProductReadme)
            .where(
                DataProductReadme.workspace_id == workspace_id,
                DataProductReadme.social_target_id == target_id,
            )
            .order_by(desc(DataProductReadme.version_int))
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
            select(DataProductReadme)
            .where(
                DataProductReadme.workspace_id == workspace_id,
                DataProductReadme.social_target_id == target_id,
            )
            .order_by(desc(DataProductReadme.version_int))
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
                        func.max(DataProductReadme.version_int), 0
                    )
                ).where(
                    DataProductReadme.workspace_id == workspace_id,
                    DataProductReadme.social_target_id == target_id,
                )
            ).scalar_one()
            + 1
        )
        new_row = DataProductReadme(
            workspace_id=workspace_id,
            data_product_id=None,
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
    """
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
    """
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
    "delete_polymorphic_comment",
    "delete_polymorphic_review",
    "follow_polymorphic_entity",
    "get_polymorphic_followers_count",
    "get_polymorphic_readme",
    "list_polymorphic_comments",
    "list_polymorphic_endorsements",
    "list_polymorphic_followers",
    "list_polymorphic_reviews",
    "post_polymorphic_comment",
    "put_polymorphic_readme",
    "remove_polymorphic_endorsement",
    "unfollow_polymorphic_entity",
    "upsert_polymorphic_review",
]
