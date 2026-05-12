"""``/api/data-products/{catalog}/{schema}/comments`` — threaded discussion (Phase 71.1).

Three endpoints:

* ``GET`` — list every live comment for the product, threaded
  order (top-level → reply chain), excludes soft-deleted top-level
  rows but keeps a placeholder when a soft-deleted parent has live
  children.
* ``POST`` — create a comment.  Resolves ``@<email>`` mentions
  against the ``users`` table and stores the resolved id list for
  the Phase-71.4 notification fan-out.
* ``DELETE`` — soft-delete by setting ``deleted_at``.  Author,
  data-product steward, or install-admin may execute.
"""

from __future__ import annotations

import datetime
import json
import re
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import AuthorizationError
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.services import audit as audit_service
from pointlessql.services.notifications import fanout_dataproduct_event
from pointlessql.services.workspace.governance import (
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
_BODY_PREVIEW_LEN = 140


def _body_preview(body_md: str) -> str:
    """Truncate a comment body for the audit-log detail JSON."""
    snippet = body_md.strip().replace("\n", " ")
    if len(snippet) > _BODY_PREVIEW_LEN:
        return snippet[: _BODY_PREVIEW_LEN - 1] + "…"
    return snippet

router = APIRouter(tags=["data-products"])


_MAX_THREAD_DEPTH = 2
_MENTION_RE = re.compile(r"@([\w.+-]+@[\w-]+\.[\w.-]+)")
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


def _serialise_comment(
    row: DataProductComment,
    *,
    author_email: str | None,
    author_display_name: str | None,
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
        "body_md": "" if row.deleted_at else row.body_md,
        "mentioned_user_ids": json.loads(row.mentioned_user_ids_json or "[]"),
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
        author_email, author_display = author_map.get(c.author_user_id, (None, None))
        payload.append(
            _serialise_comment(
                c,
                author_email=author_email,
                author_display_name=author_display,
            )
        )

    return {"data_product_id": row.id, "comments": payload}


@router.post("/api/data-products/{catalog}/{schema}/comments")
async def post_data_product_comment(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Create a comment on the product.

    Body: ``{"body_md": str, "parent_comment_id": int | None}``.

    Threading capped at depth 2: a POST whose
    ``parent_comment_id`` itself has a non-NULL
    ``parent_comment_id`` returns 400.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        Serialised comment row.

    Raises:
        HTTPException: 400 on empty body, missing parent, or
            over-deep nesting.
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
            if parent.parent_comment_id is not None:
                # Depth cap = 2 (one reply level).
                # bare-http-ok: enforce thread depth.
                raise HTTPException(
                    status_code=400,
                    detail=f"thread depth exceeds {_MAX_THREAD_DEPTH}",
                )

        emails = _extract_mention_emails(body_md)
        mentioned_ids = _resolve_mentions(session, emails)
        now = datetime.datetime.now(datetime.UTC)
        comment = DataProductComment(
            workspace_id=workspace_id,
            data_product_id=row.id,
            parent_comment_id=parent_comment_id,
            author_user_id=user["id"],
            body_md=body_md,
            mentioned_user_ids_json=json.dumps(mentioned_ids),
            created_at=now,
        )
        session.add(comment)
        session.commit()
        session.refresh(comment)

        author = session.get(User, comment.author_user_id)
        author_email = author.email if author else None
        author_display = author.display_name if author else None
        comment_id = comment.id
        comment_dp_id = comment.data_product_id

    # Phase 72.5: audit-log mirror so the Phase-18.7 FTS picks
    # comments up in `/audit/search`.  The DataProductComment
    # table stays system-of-record; this row is discoverability
    # only.  body_preview is truncated to keep storage bounded.
    audit_service.log_action(
        factory,
        user_id=user["id"],
        user_email=user.get("email", ""),
        action=_DISCUSSION_POSTED,
        target=(
            f"data_product:{catalog}.{schema}#tab-discussion-comment-"
            f"{comment_id}"
        ),
        detail={
            "data_product_id": comment_dp_id,
            "comment_id": comment_id,
            "parent_comment_id": parent_comment_id,
            "body_preview": _body_preview(body_md),
        },
        workspace_id=workspace_id,
    )

    # Phase 71.4: per-user inbox fan-out + governance CloudEvent.
    source_url = (
        f"/data-products/{catalog}/{schema}#tab-discussion-comment-{comment_id}"
    )
    summary = f"@{author_email or 'someone'} commented on {catalog}.{schema}"
    fanout_dataproduct_event(
        factory,
        event_type=EVENT_TYPE_DATA_PRODUCT_COMMENTED,
        data_product_id=comment_dp_id,
        workspace_id=workspace_id,
        actor_user_id=user["id"],
        source_url=source_url,
        summary_md=summary,
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
    )


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
        audit_service.log_action(
            factory,
            user_id=user["id"],
            user_email=user.get("email", ""),
            action=_DISCUSSION_DELETED,
            target=(
                f"data_product:{catalog}.{schema}#tab-discussion-comment-"
                f"{comment.id}"
            ),
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
