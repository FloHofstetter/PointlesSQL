"""``POST /api/data-products/{catalog}/{schema}/comments`` — create one comment."""

from __future__ import annotations

import datetime
import json
from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api._social_serializers import agent_payload
from pointlessql.api.data_products_routes._shared import (
    load_one,
    resolve_agent_for_principal,
)
from pointlessql.api.data_products_routes.comments._constants import (
    ALLOWED_CATEGORIES,
    ALLOWED_EMOJI,
    DISCUSSION_MENTION_AMBIGUOUS,
    DISCUSSION_POSTED,
    MAX_THREAD_DEPTH,
)
from pointlessql.api.data_products_routes.comments._helpers import (
    body_preview,
    chain_depth,
    serialise_comment,
)
from pointlessql.api.data_products_routes.comments._mentions import (
    extract_displayname_mentions,
    extract_mention_emails,
    resolve_displayname_mentions,
    resolve_mentions,
)
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import BadRequestError
from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.services.notifications.fanout import fanout_event
from pointlessql.services.social import resolve_citations
from pointlessql.services.social._target_resolver import resolve_dp_target
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_COMMENTED,
    emit_governance_event,
)

router = APIRouter(tags=["data-products"])


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
        raise BadRequestError("body_md is required")
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
        raise BadRequestError(f"category must be one of {ALLOWED_CATEGORIES}")

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
                raise BadRequestError(
                    "parent_comment_id refers to an unknown comment"
                )
            if chain_depth(session, parent_comment_id) >= MAX_THREAD_DEPTH:
                raise BadRequestError(f"thread depth exceeds {MAX_THREAD_DEPTH}")
            # Replies inherit category from the top-level ancestor.
            effective_category = parent.category
        else:
            effective_category = requested_category or "general"

        emails = extract_mention_emails(body_md)
        mentioned_ids = resolve_mentions(session, emails)
        displayname_tokens = extract_displayname_mentions(body_md)
        resolved_dn, ambiguous_displaynames = resolve_displayname_mentions(
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
            action=DISCUSSION_MENTION_AMBIGUOUS,
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
        action=DISCUSSION_POSTED,
        entity_kind="dp",
        entity_ref=f"{catalog}.{schema}",
        suffix=f"tab-discussion-comment-{comment_id}",
        detail={
            "data_product_id": comment_dp_id,
            "comment_id": comment_id,
            "parent_comment_id": parent_comment_id,
            "body_preview": body_preview(body_md),
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

    return serialise_comment(
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
