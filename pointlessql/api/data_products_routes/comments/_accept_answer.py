"""``POST .../comments/{id}/accept-answer`` — mark a reply as the accepted answer."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.data_products_routes.comments._constants import (
    DISCUSSION_ANSWER_ACCEPTED,
)
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import (
    AuthorizationError,
    BadRequestError,
    ResourceNotFoundError,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.services.notifications.fanout import fanout_event
from pointlessql.services.social.audit_mirror import mirror_social_to_audit
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_ANSWER_ACCEPTED,
    emit_governance_event,
)

router = APIRouter(tags=["data-products"])


@router.post("/api/data-products/{catalog}/{schema}/comments/{comment_id}/accept-answer")
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
        ResourceNotFoundError: When the comment is missing.
        BadRequestError: When the comment is not a reply in a
            ``question`` thread.
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
            raise ResourceNotFoundError.not_found(what=f"comment id={comment_id}")

        if comment.parent_comment_id is None:
            raise BadRequestError("accept-answer is only valid on a reply")
        top_level = session.get(DataProductComment, comment.parent_comment_id)
        # Walk up to the actual top-level question (replies may be
        # depth 3-5 after the threading lift).
        while top_level is not None and top_level.parent_comment_id is not None:
            top_level = session.get(DataProductComment, top_level.parent_comment_id)
        if top_level is None or top_level.category != "question":
            raise BadRequestError("accept-answer requires a 'question' top-level thread")

        is_steward = row.steward_user_id is not None and row.steward_user_id == user["id"]
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
        action=DISCUSSION_ANSWER_ACCEPTED,
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
    source_url = f"/data-products/{catalog}/{schema}#tab-discussion-comment-{comment_id}"
    summary = f"Answer accepted on {catalog}.{schema}"
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
