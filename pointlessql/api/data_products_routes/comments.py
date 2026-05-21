"""``/api/data-products/{catalog}/{schema}/comments`` — threaded discussion (Phase 71.1 + 76.1).

Four endpoints:

* ``GET`` — list every live comment for the product, threaded
  order (top-level → reply chain), excludes soft-deleted top-level
  rows but keeps a placeholder when a soft-deleted parent has live
  children.  Each row carries ``category`` + ``is_accepted_answer``
  + aggregated ``reactions`` (Phase 76.1).
* ``POST`` — create a comment.  Resolves ``@<email>`` *and*
  ``@<display_name>`` mentions against the ``users`` table and
  stores the resolved id list for the Phase-71.4 notification
  fan-out.  ``category`` defaults to ``general``; only top-level
  comments accept it (replies inherit).  Threading is capped at
  depth 5 (Phase 76.1 lifted from 2).
* ``DELETE`` — soft-delete by setting ``deleted_at``.  Author,
  data-product steward, or install-admin may execute.
* ``POST /{id}/accept-answer`` — mark a reply under a
  ``question``-category top-level thread as the accepted answer.
  Steward / install-admin / OP only.  Atomic per thread.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from pointlessql.api._social_serializers import agent_payload
from pointlessql.api.data_products_routes._shared import (
    load_one,
    resolve_agent_for_principal,
)
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import AuthorizationError
from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.services.notifications.fanout import fanout_event
from pointlessql.services.social import resolve_citations
from pointlessql.services.social._target_resolver import resolve_dp_target
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_ANSWER_ACCEPTED,
    EVENT_TYPE_DATA_PRODUCT_COMMENTED,
    emit_governance_event,
)

# Phase 72.5 — audit-bound discussions sidecar.  Each comment
# POST / DELETE drops an ``audit_log`` row alongside the
# DataProductComment write so the Phase-18.7 audit-search FTS
# index picks comments up.  The comments stay system-of-record;
# the audit row is a discoverability mirror.
_DISCUSSION_POSTED = "audit.discussion.posted"
_DISCUSSION_DELETED = "audit.discussion.deleted"
_DISCUSSION_ANSWER_ACCEPTED = "audit.discussion.answer_accepted"
_DISCUSSION_MENTION_AMBIGUOUS = "audit.discussion.mention_ambiguous"
_BODY_PREVIEW_LEN = 140

# Phase 76.1 — comment-category enum + reactions canonical set.
# Phase 101 Wave-D added ``review`` for cell-level review decisions
# (notebook_cell entity-kind); kept in lockstep with
# ``_polymorphic_handlers._shared.ALLOWED_CATEGORIES``.
ALLOWED_CATEGORIES: tuple[str, ...] = (
    "general",
    "question",
    "announcement",
    "idea",
    "review",
)
ALLOWED_EMOJI: tuple[str, ...] = ("👍", "❤️", "🎉", "😄", "😕", "👀")


def _body_preview(body_md: str) -> str:
    """Truncate a comment body for the audit-log detail JSON."""
    snippet = body_md.strip().replace("\n", " ")
    if len(snippet) > _BODY_PREVIEW_LEN:
        return snippet[: _BODY_PREVIEW_LEN - 1] + "…"
    return snippet

router = APIRouter(tags=["data-products"])


_MAX_THREAD_DEPTH = 5
_MENTION_RE = re.compile(r"@([\w.+-]+@[\w-]+\.[\w.-]+)")
# Display-name mention pattern — must start with a letter and not
# contain '@' (so it never matches the email path above).  Bounded
# length to prevent runaway regex matches on adversarial input.
_DISPLAYNAME_MENTION_RE = re.compile(r"@([A-Za-z][A-Za-z0-9._-]{2,30})\b")
_FENCED_CODE_RE = re.compile(r"```.*?```", re.DOTALL)


def _extract_mention_emails(body_md: str) -> list[str]:
    """Return ``@email`` mentions in *body_md* with fenced code stripped.

    Strips ``` … ``` fenced blocks before scanning so a documentation
    example doesn't spam a real user.  Inline ``code`` is *not*
    stripped — too aggressive for one regex; documented as a known
    limitation.
    """
    stripped = _FENCED_CODE_RE.sub("", body_md)
    return _MENTION_RE.findall(stripped)


def _extract_displayname_mentions(body_md: str) -> list[str]:
    """Return ``@display_name`` mentions, fenced-code-aware.

    The email-pattern matches first; we de-duplicate by stripping
    any token containing ``@`` post-scan so a single ``@alice@x.y``
    isn't double-counted.
    """
    stripped = _FENCED_CODE_RE.sub("", body_md)
    raw = _DISPLAYNAME_MENTION_RE.findall(stripped)
    return [t for t in raw if "@" not in t]


def _resolve_mentions(session: Any, emails: list[str]) -> list[int]:
    """Map @-mention emails to their persisted user ids (case-insensitive)."""
    if not emails:
        return []
    lowered = list({e.lower() for e in emails})
    users = (
        session.execute(
            select(User.id, User.email).where(User.email.in_(lowered))
        ).all()
    )
    return [int(uid) for uid, _email in users]


def _resolve_displayname_mentions(
    session: Any, tokens: list[str]
) -> tuple[list[int], list[str]]:
    """Map ``@display_name`` mentions to user ids with disambiguation.

    Two users sharing the same ``display_name`` are unresolvable —
    we skip both (callers can fall back to ``@email`` for
    precision) and surface the ambiguous token to the caller so
    an audit row can be written.

    Args:
        session: Open SQLAlchemy session.
        tokens: De-duplicated display-name fragments extracted from
            the comment body.

    Returns:
        ``(resolved_user_ids, ambiguous_tokens)``.  ``resolved`` is
        empty when no token matched exactly one user.
    """
    if not tokens:
        return [], []
    lowered = list({t.lower() for t in tokens})
    rows = (
        session.execute(
            select(User.id, User.display_name).where(
                func.lower(User.display_name).in_(lowered)
            )
        ).all()
    )
    by_name: dict[str, list[int]] = {}
    for uid, name in rows:
        by_name.setdefault(name.lower(), []).append(int(uid))
    resolved: list[int] = []
    ambiguous: list[str] = []
    for token in lowered:
        hits = by_name.get(token, [])
        if len(hits) == 1:
            resolved.append(hits[0])
        elif len(hits) > 1:
            ambiguous.append(token)
    return resolved, ambiguous


def _chain_depth(session: Any, parent_id: int) -> int:
    """Return the depth of the existing reply chain ending at *parent_id*.

    Depth 1 = top-level comment, depth 2 = a single reply, etc.
    Walks up via ``parent_comment_id`` with a hard ceiling so a
    pathological self-loop in the data can't blow up the request.
    """
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
    """Return per-comment reaction aggregates.

    Args:
        session: Open SQLAlchemy session.
        comment_ids: PKs to aggregate.
        caller_user_id: Used to set the per-emoji
            ``has_current_user_reacted`` flag.

    Returns:
        ``{comment_id: [{emoji, count, has_current_user_reacted}]}``.
        Comments with no reactions get an entry with zero counts on
        every emoji so the UI doesn't have to special-case missing
        keys.
    """
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
        "data_product_id": row.data_product_id,
        "parent_comment_id": row.parent_comment_id,
        "author": {
            "user_id": row.author_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        # Phase 76.5 — when the comment is authored by an agent
        # the ``agent`` payload carries the slug + display name;
        # ``author.user_id`` is None in that case.
        "agent": agent,
        "body_md": "" if row.deleted_at else row.body_md,
        # Phase 76.7 — cite-token render projection.  Carries the
        # same string as ``body_md`` with ``#dp:`` / ``#topic:`` /
        # ``#user:`` / ``#agent:`` tokens replaced by markdown
        # anchors.  The frontend reads this field via the
        # ``pqlRenderCitations`` helper.
        "body_md_resolved": body_md_resolved,
        "mentioned_user_ids": json.loads(row.mentioned_user_ids_json or "[]"),
        "category": row.category,
        "is_accepted_answer": bool(row.is_accepted_answer),
        "reactions": reactions if reactions is not None else [],
        "created_at": row.created_at.isoformat(),
        "deleted_at": row.deleted_at.isoformat() if row.deleted_at else None,
    }


@router.get("/api/data-products/{catalog}/{schema}/comments")
async def list_data_product_comments(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return every live comment for the product in threaded order.

    A soft-deleted top-level comment with no live children is
    omitted; a soft-deleted parent whose replies are still live
    is rendered as a placeholder so the reply chain stays
    coherent.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "comments": [...]}`` flattened
        in (parent_id, created_at) order.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductComment)
                .where(
                    DataProductComment.workspace_id == workspace_id,
                    DataProductComment.data_product_id == row.id,
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
                session.execute(select(User).where(User.id.in_(author_ids)))
                .scalars()
                .all()
            )
            author_map = {u.id: (u.email, u.display_name) for u in users}
        agent_ids = {
            c.author_agent_id for c in rows if c.author_agent_id is not None
        }
        agent_map: dict[int, dict[str, Any] | None] = {}
        if agent_ids:
            agents = (
                session.execute(select(Agent).where(Agent.id.in_(agent_ids)))
                .scalars()
                .all()
            )
            agent_map = {a.id: agent_payload(a) for a in agents}
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
            # Soft-deleted leaf — drop entirely.
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
            _serialise_comment(
                c,
                author_email=author_email,
                author_display_name=author_display,
                body_md_resolved=body_md_resolved,
                agent=comment_agent_payload,
                reactions=reactions_by_comment.get(c.id),
            )
        )

    return {"data_product_id": row.id, "comments": payload}


@router.post("/api/data-products/{catalog}/{schema}/comments")
async def post_data_product_comment(
    catalog: str,
    schema: str,
    request: Request,
    as_agent: str | None = None,
) -> dict[str, Any]:
    """Create a comment on the product.

    Body: ``{"body_md": str, "parent_comment_id": int | None,
    "category": str | None}``.

    Threading capped at depth 5 (Phase 76.1 lifted from 2).  The
    handler walks the parent's ``parent_comment_id`` chain and
    rejects a POST that would push depth past 5.  Replies inherit
    their parent's category — the caller's ``category`` is only
    honoured on top-level comments.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.
        as_agent: Optional agent slug — when set, the comment is
            posted *by* the agent on behalf of the caller (who
            must be the agent's ``principal_user_id``, or admin).
            The ``author_user_id`` column still records the
            principal so the audit chain stays intact (Phase 76.5).

    Returns:
        Serialised comment row.  When ``?as_agent=`` is supplied
        the caller must be the agent's ``principal_user_id`` or
        install-admin; otherwise the helper raises an
        :class:`pointlessql.exceptions.AuthorizationError` (the
        middleware turns it into a 403).

    Raises:
        HTTPException: 400 on empty body, missing parent, unknown
            category, or over-deep nesting; 404 on unknown
            ``?as_agent=`` slug.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    body = await request.json()
    body_md = (body.get("body_md") or "").strip()
    if not body_md:
        # bare-http-ok: request body is required + non-empty.
        raise HTTPException(status_code=400, detail="body_md is required")
    parent_comment_id_raw = body.get("parent_comment_id")
    parent_comment_id = (
        int(parent_comment_id_raw) if parent_comment_id_raw is not None else None
    )
    requested_category_raw = body.get("category")
    requested_category = (
        str(requested_category_raw).strip().lower()
        if requested_category_raw is not None
        else None
    )
    if requested_category is not None and requested_category not in ALLOWED_CATEGORIES:
        # bare-http-ok: category must be one of the canonical four.
        raise HTTPException(
            status_code=400,
            detail=f"category must be one of {ALLOWED_CATEGORIES}",
        )

    # Phase 76.5 — resolve the optional ``as_agent`` slug *before*
    # writing the comment so the authorship-discriminator is set
    # atomically.  Helper enforces the principal-or-admin gate;
    # see ``_shared.resolve_agent_for_principal``.
    author_agent_id: int | None = None
    if as_agent is not None:
        author_agent_id = resolve_agent_for_principal(
            factory, workspace_id=workspace_id, slug=as_agent, user=user
        )

    ambiguous_displaynames: list[str] = []
    with factory() as session:
        if parent_comment_id is not None:
            parent = session.get(DataProductComment, parent_comment_id)
            if (
                parent is None
                or parent.workspace_id != workspace_id
                or parent.data_product_id != row.id
            ):
                # bare-http-ok: parent must exist in the same product.
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
            # Replies inherit category from the top-level ancestor.
            effective_category = parent.category
        else:
            effective_category = requested_category or "general"

        emails = _extract_mention_emails(body_md)
        mentioned_ids = _resolve_mentions(session, emails)
        displayname_tokens = _extract_displayname_mentions(body_md)
        resolved_dn, ambiguous_displaynames = _resolve_displayname_mentions(
            session, displayname_tokens
        )
        # Combine + de-duplicate while preserving order.
        mentioned_ids = list(dict.fromkeys(mentioned_ids + resolved_dn))
        now = datetime.datetime.now(datetime.UTC)
        target = resolve_dp_target(
            session,
            workspace_id=workspace_id,
            catalog_name=catalog,
            schema_name=schema,
        )
        # Phase 76.5 — ``author_user_id`` always carries the
        # human accountable (caller if direct, principal_user
        # when speaking-as-agent).  ``author_agent_id`` is the
        # optional presentation-layer override.
        comment = DataProductComment(
            workspace_id=workspace_id,
            data_product_id=row.id,
            social_target_id=target.id,
            parent_comment_id=parent_comment_id,
            author_user_id=user["id"],
            author_agent_id=author_agent_id,
            body_md=body_md,
            mentioned_user_ids_json=json.dumps(mentioned_ids),
            category=effective_category,
            is_accepted_answer=False,
            created_at=now,
        )
        session.add(comment)
        session.commit()
        session.refresh(comment)

        author_row = session.get(User, comment.author_user_id)
        author_email = author_row.email if author_row else None
        author_display = author_row.display_name if author_row else None
        post_agent_payload: dict[str, Any] | None = None
        if comment.author_agent_id is not None:
            agent_row = session.get(Agent, comment.author_agent_id)
            post_agent_payload = agent_payload(agent_row)
        comment_id = comment.id
        comment_dp_id = comment.data_product_id

    for token in ambiguous_displaynames:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action=_DISCUSSION_MENTION_AMBIGUOUS,
            entity_kind="dp",
            entity_ref=f"{catalog}.{schema}",
            suffix=f"tab-discussion-comment-{comment_id}",
            detail={"comment_id": comment_id, "ambiguous_token": token},
            workspace_id=workspace_id,
        )

    # Phase 72.5: audit-log mirror so the Phase-18.7 FTS picks
    # comments up in `/audit/search`.  The DataProductComment
    # table stays system-of-record; this row is discoverability
    # only.  body_preview keeps the 140-char display affordance;
    # body_md ships the full body so the Phase-78 FTS unlock can
    # find comments by long-form content.
    mirror_social_to_audit(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action=_DISCUSSION_POSTED,
        entity_kind="dp",
        entity_ref=f"{catalog}.{schema}",
        suffix=f"tab-discussion-comment-{comment_id}",
        detail={
            "data_product_id": comment_dp_id,
            "comment_id": comment_id,
            "parent_comment_id": parent_comment_id,
            "body_preview": _body_preview(body_md),
            "body_md": body_md,
        },
        workspace_id=workspace_id,
    )

    # Phase 71.4: per-user inbox fan-out + governance CloudEvent.
    source_url = (
        f"/data-products/{catalog}/{schema}#tab-discussion-comment-{comment_id}"
    )
    summary = f"@{author_email or 'someone'} commented on {catalog}.{schema}"
    fanout_event(
        factory,
        event_type=EVENT_TYPE_DATA_PRODUCT_COMMENTED,
        entity_kind="dp",
        entity_ref=f"{catalog}.{schema}",
        workspace_id=workspace_id,
        actor_user_id=user["id"],
        source_url=source_url,
        summary_md=summary,
        data_product_id=comment_dp_id,
        extra_recipients=mentioned_ids,
    )
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_COMMENTED,
        {
            "data_product_id": comment_dp_id,
            "data_product_ref": f"{catalog}.{schema}",
            "comment_id": comment_id,
            "author_user_id": user["id"],
            "author_email": author_email,
            "mentioned_user_ids": mentioned_ids,
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
        agent=post_agent_payload,
        reactions=[
            {"emoji": e, "count": 0, "has_current_user_reacted": False}
            for e in ALLOWED_EMOJI
        ],
    )


@router.post(
    "/api/data-products/{catalog}/{schema}/comments/{comment_id}/accept-answer"
)
async def accept_answer(
    catalog: str,
    schema: str,
    comment_id: int,
    request: Request,
) -> dict[str, Any]:
    """Mark *comment_id* as the accepted answer on its question thread.

    Authorised callers: data-product steward, install-admin, and
    the author of the top-level question comment (the OP).  Only
    replies in a ``question``-category top-level thread are valid
    targets.  At most one reply per thread carries the
    ``is_accepted_answer`` flag — accepting C2 unmarks C1 if C1
    was previously marked.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        comment_id: PK of the reply to mark as the accepted answer.
        request: Incoming FastAPI request.

    Returns:
        ``{"id": int, "is_accepted_answer": True}``.

    Raises:
        AuthorizationError: When the caller is not steward, admin,
            or the question-thread OP.
        HTTPException: 404 if the comment is missing; 400 if the
            comment is not a reply in a ``question`` thread.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        comment = session.get(DataProductComment, comment_id)
        if (
            comment is None
            or comment.workspace_id != workspace_id
            or comment.data_product_id != row.id
            or comment.deleted_at is not None
        ):
            # bare-http-ok: target reply must exist + be live.
            raise HTTPException(status_code=404, detail="comment not found")

        if comment.parent_comment_id is None:
            # bare-http-ok: only replies (not the question itself)
            # can be marked.
            raise HTTPException(
                status_code=400,
                detail="accept-answer is only valid on a reply",
            )
        top_level = session.get(DataProductComment, comment.parent_comment_id)
        # Walk up to the actual top-level question (replies may be
        # depth 3-5 after the threading lift).
        while (
            top_level is not None and top_level.parent_comment_id is not None
        ):
            top_level = session.get(
                DataProductComment, top_level.parent_comment_id
            )
        if top_level is None or top_level.category != "question":
            # bare-http-ok: thread must be a question.
            raise HTTPException(
                status_code=400,
                detail="accept-answer requires a 'question' top-level thread",
            )

        is_steward = (
            row.steward_user_id is not None and row.steward_user_id == user["id"]
        )
        is_admin = bool(user.get("is_admin"))
        is_op = top_level.author_user_id == user["id"]
        if not (is_steward or is_admin or is_op):
            raise AuthorizationError(
                principal=user.get("email", ""),
                privilege="accept-answer",
                securable_type="data_product_comment",
                full_name=str(comment_id),
            )

        # Atomic flip: clear any prior accepted answer in this
        # thread, then mark this one.  Replies share the same root
        # via the walk-up above, so we filter by it.
        thread_ids: list[int] = [top_level.id]
        stack: list[int] = [top_level.id]
        while stack:
            current = stack.pop()
            children = (
                session.execute(
                    select(DataProductComment.id).where(
                        DataProductComment.parent_comment_id == current
                    )
                )
                .scalars()
                .all()
            )
            for cid in children:
                thread_ids.append(int(cid))
                stack.append(int(cid))
        for tid in thread_ids:
            existing = session.get(DataProductComment, tid)
            if existing is not None:
                existing.is_accepted_answer = tid == comment_id
        session.commit()

        op_user_id = int(top_level.author_user_id)
        answer_author_id = int(comment.author_user_id)

    mirror_social_to_audit(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action=_DISCUSSION_ANSWER_ACCEPTED,
        entity_kind="dp",
        entity_ref=f"{catalog}.{schema}",
        suffix=f"tab-discussion-comment-{comment_id}",
        detail={
            "data_product_id": row.id,
            "comment_id": comment_id,
            "question_comment_id": top_level.id if top_level else None,
        },
        workspace_id=workspace_id,
    )

    # Notify the answer author + the question OP (de-dup actor).
    source_url = (
        f"/data-products/{catalog}/{schema}#tab-discussion-comment-{comment_id}"
    )
    summary = (
        f"Answer accepted on {catalog}.{schema}"
    )
    recipients = {answer_author_id, op_user_id}
    recipients.discard(user["id"])
    fanout_event(
        factory,
        event_type=EVENT_TYPE_DATA_PRODUCT_ANSWER_ACCEPTED,
        entity_kind="dp",
        entity_ref=f"{catalog}.{schema}",
        workspace_id=workspace_id,
        actor_user_id=user["id"],
        source_url=source_url,
        summary_md=summary,
        data_product_id=row.id,
        extra_recipients=list(recipients),
    )
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_ANSWER_ACCEPTED,
        {
            "data_product_id": row.id,
            "data_product_ref": f"{catalog}.{schema}",
            "comment_id": comment_id,
            "question_comment_id": top_level.id if top_level else None,
            "answer_author_user_id": answer_author_id,
            "op_user_id": op_user_id,
            "actor_user_id": user["id"],
        },
        settings=request.app.state.settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )

    return {"id": comment_id, "is_accepted_answer": True}


@router.delete("/api/data-products/{catalog}/{schema}/comments/{comment_id}")
async def delete_data_product_comment(
    catalog: str,
    schema: str,
    comment_id: int,
    request: Request,
) -> dict[str, Any]:
    """Soft-delete a comment by setting ``deleted_at``.

    Author, data-product steward, or install-admin may delete.
    Idempotent on an already-deleted row.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        comment_id: PK of the comment to soft-delete.
        request: Incoming FastAPI request.

    Returns:
        ``{"id": int, "deleted_at": str}`` reflecting the new state.

    Raises:
        AuthorizationError: When the caller is neither author nor
            steward nor admin.
        HTTPException: 404 when the comment is missing or scoped to
            a different product.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        comment = session.get(DataProductComment, comment_id)
        if (
            comment is None
            or comment.workspace_id != workspace_id
            or comment.data_product_id != row.id
        ):
            # bare-http-ok: comment must exist in the addressed product.
            raise HTTPException(status_code=404, detail="comment not found")

        is_author = comment.author_user_id == user["id"]
        is_steward = (
            row.steward_user_id is not None and row.steward_user_id == user["id"]
        )
        is_admin = bool(user.get("is_admin"))
        if not (is_author or is_steward or is_admin):
            raise AuthorizationError(
                principal=user.get("email", ""),
                privilege="soft-delete",
                securable_type="data_product_comment",
                full_name=str(comment_id),
            )

        was_already_deleted = comment.deleted_at is not None
        if comment.deleted_at is None:
            comment.deleted_at = datetime.datetime.now(datetime.UTC)
            session.add(comment)
            session.commit()
            session.refresh(comment)

    # Phase 72.5: audit-log mirror — only fire on the *transition*
    # (was-live → soft-deleted), not on idempotent re-DELETEs that
    # find the row already gone.  This keeps the audit trail
    # accurate at one row per actual moderation action.
    if not was_already_deleted:
        mirror_social_to_audit(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action=_DISCUSSION_DELETED,
            entity_kind="dp",
            entity_ref=f"{catalog}.{schema}",
            suffix=f"tab-discussion-comment-{comment.id}",
            detail={
                "data_product_id": comment.data_product_id,
                "comment_id": comment.id,
            },
            workspace_id=workspace_id,
        )

    return {
        "id": comment.id,
        "deleted_at": (
            comment.deleted_at.isoformat() if comment.deleted_at else None
        ),
    }
