"""``DELETE /api/data-products/{catalog}/{schema}/comments/{comment_id}`` — soft delete."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.data_products_routes.comments._constants import (
    DISCUSSION_DELETED,
)
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.exceptions import AuthorizationError, ResourceNotFoundError
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.services.social.audit_mirror import mirror_social_to_audit

router = APIRouter(tags=["data-products"])


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
            raise ResourceNotFoundError.not_found(what=f"comment id={comment_id}")

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
            action=DISCUSSION_DELETED,
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
