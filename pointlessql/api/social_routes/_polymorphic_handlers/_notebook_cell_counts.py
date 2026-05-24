"""Bulk-count endpoint for notebook-cell social rows (Phase 95).

A notebook with 50 cells would otherwise need 50 separate
``GET /api/social/notebook_cell/{ref}/comments`` round-trips to know
which cells have a ``💬 N`` chip to render.  This handler returns the
aggregated counts for every cell of one notebook in a single query.

Counts are eventually-consistent — the editor calls this once on
notebook open and again after each save (debounced).  No SSE / WS
push for Phase 95 (the existing notification stream already covers
the realtime path for users actively watching a thread).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query, Request
from sqlalchemy import func, select

from pointlessql.api.dependencies import current_workspace_id, require_user
from pointlessql.exceptions import BadRequestError, ResourceNotFoundError
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.notebook import Notebook
from pointlessql.models.social._social_follow import SocialFollow
from pointlessql.models.social._social_reaction import SocialReaction
from pointlessql.models.social._social_target import SocialTarget

router = APIRouter(tags=["social"])


@router.get("/api/social/notebook_cell/_bulk_counts")
def bulk_counts(
    request: Request,
    notebook_id: str = Query(..., min_length=1),
) -> dict[str, Any]:
    """Return per-cell comment / reaction / follower counts for one notebook.

    Args:
        request: Active FastAPI request — authenticated user.
        notebook_id: 36-char ``notebooks.id`` UUID.

    Returns:
        ``{"notebook_id": str, "counts": {<cell_id>: {comments: N,
        reactions: {emoji: N, ...}, followers: K}, ...}}``.
        Cells with zero social rows are omitted from the dict so a
        notebook with 50 cells but no activity round-trips an empty
        ``counts`` object.

    Raises:
        BadRequestError: When the notebook UUID is malformed.
        ResourceNotFoundError: When the notebook does not exist in
            the active workspace (cross-workspace probes also 404
            so workspace existence is not leaked).
    """
    require_user(request)
    if len(notebook_id) != 36 or notebook_id.count("-") != 4:
        raise BadRequestError("notebook_id must be a 36-char UUID")
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    prefix = f"{notebook_id}:"
    with factory() as session:
        owner = session.execute(
            select(Notebook.workspace_id).where(Notebook.id == notebook_id)
        ).first()
        if owner is None or int(owner[0]) != workspace_id:
            raise ResourceNotFoundError.not_found(
                what=f"notebook {notebook_id!r}"
            )

        target_rows = session.execute(
            select(SocialTarget.id, SocialTarget.entity_ref).where(
                SocialTarget.workspace_id == workspace_id,
                SocialTarget.entity_kind == "notebook_cell",
                SocialTarget.entity_ref.like(f"{prefix}%"),
            )
        ).all()
        if not target_rows:
            return {"notebook_id": notebook_id, "counts": {}}
        target_ids = [int(r[0]) for r in target_rows]
        ref_by_id = {int(r[0]): str(r[1]) for r in target_rows}

        comment_rows = session.execute(
            select(
                DataProductComment.social_target_id,
                func.count(DataProductComment.id),
            )
            .where(
                DataProductComment.social_target_id.in_(target_ids),
                DataProductComment.deleted_at.is_(None),
            )
            .group_by(DataProductComment.social_target_id)
        ).all()
        comment_counts = {int(r[0]): int(r[1]) for r in comment_rows}

        reaction_rows = session.execute(
            select(
                SocialReaction.social_target_id,
                SocialReaction.emoji,
                func.count(SocialReaction.id),
            )
            .where(SocialReaction.social_target_id.in_(target_ids))
            .group_by(SocialReaction.social_target_id, SocialReaction.emoji)
        ).all()
        reaction_counts: dict[int, dict[str, int]] = {}
        for tid, emoji, count in reaction_rows:
            reaction_counts.setdefault(int(tid), {})[str(emoji)] = int(count)

        follower_rows = session.execute(
            select(
                SocialFollow.social_target_id,
                func.count(SocialFollow.user_id),
            )
            .where(SocialFollow.social_target_id.in_(target_ids))
            .group_by(SocialFollow.social_target_id)
        ).all()
        follower_counts = {int(r[0]): int(r[1]) for r in follower_rows}

    counts: dict[str, dict[str, Any]] = {}
    for target_id in target_ids:
        ref = ref_by_id[target_id]
        _, _, cell_id = ref.partition(":")
        if not cell_id:
            continue
        bucket = {
            "comments": comment_counts.get(target_id, 0),
            "reactions": reaction_counts.get(target_id, {}),
            "followers": follower_counts.get(target_id, 0),
        }
        # Keep the response compact — omit cells with zero activity.
        if (
            bucket["comments"]
            or bucket["reactions"]
            or bucket["followers"]
        ):
            counts[cell_id] = bucket
    return {"notebook_id": notebook_id, "counts": counts}
