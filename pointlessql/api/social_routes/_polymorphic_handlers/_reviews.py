"""Polymorphic review list / upsert / delete.

Each axis lives in its own sub-module now while the
public handler names re-export from the package facade.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import Request
from sqlalchemy import func, select

from pointlessql.api.dependencies import (
    get_user,
    require_user,
)
from pointlessql.api.social_routes._polymorphic_handlers._shared import (
    resolve_target_id,
    reviews_supported,
    serialise_review,
)
from pointlessql.exceptions import BadRequestError
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.services.notifications.fanout import fanout_event
from pointlessql.services.social import (
    resolve_citations,
)
from pointlessql.services.social.entity_registry import (
    get as registry_get,
)
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_REVIEWED,
    emit_governance_event,
)

# ---------------------------------------------------------------------------
# Reviews
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
    """  # noqa: DOC502 — raised by reviews_supported helper
    require_user(request)
    reviews_supported(kind)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
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
        s = serialise_review(
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
        BadRequestError: On invalid stars or missing payload.
        HTTPException: 501 when *kind* has reviews disabled.
    """  # noqa: DOC502 — raised by reviews_supported helper
    require_user(request)
    reviews_supported(kind)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
    factory = request.app.state.session_factory

    body = await request.json()
    raw_stars = body.get("stars")
    if raw_stars is None:
        raise BadRequestError("stars is required")
    try:
        stars = int(raw_stars)
    except (TypeError, ValueError):
        raise BadRequestError("stars must be an int") from None
    if stars < 1 or stars > 5:
        raise BadRequestError("stars must be in 1..5")
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

    return serialise_review(
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
    """  # noqa: DOC502 — raised by reviews_supported helper
    require_user(request)
    reviews_supported(kind)
    user = get_user(request)
    workspace_id, target_id = resolve_target_id(request, kind, ref)
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

