"""``/api/data-products/{catalog}/{schema}/reviews`` — stars + body (Phase 71.2).

Three endpoints:

* ``GET`` — list every review for the product + summary
  ``{avg_stars, count, my_review?}``.
* ``PUT`` — idempotent upsert of the caller's review (one per
  ``(user, DP)``).
* ``DELETE`` — remove the caller's review (self only).

Reviews are hard-deleted; aggregates are computed on read.
"""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from sqlalchemy import func, select

from pointlessql.api.data_products_routes._shared import load_one
from pointlessql.api.dependencies import current_workspace_id, get_user, require_user
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.services.notifications import fanout_dataproduct_event
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_DATA_PRODUCT_REVIEWED,
    emit_governance_event,
)

router = APIRouter(tags=["data-products"])


def _serialise_review(
    row: DataProductReview,
    *,
    author_email: str | None,
    author_display_name: str | None,
) -> dict[str, Any]:
    """Render one review row as a JSON-friendly dict."""
    return {
        "id": row.id,
        "data_product_id": row.data_product_id,
        "author": {
            "user_id": row.author_user_id,
            "email": author_email,
            "display_name": author_display_name,
        },
        "stars": row.stars,
        "body_md": row.body_md,
        "dp_version_at_review": row.dp_version_at_review,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def _summary_for(session: Any, workspace_id: int, dp_id: int) -> dict[str, Any]:
    """Compute the ``{avg_stars, count}`` aggregate for one product."""
    avg_stars, count = (
        session.execute(
            select(
                func.avg(DataProductReview.stars),
                func.count(DataProductReview.id),
            ).where(
                DataProductReview.workspace_id == workspace_id,
                DataProductReview.data_product_id == dp_id,
            )
        )
    ).one()
    return {
        "avg_stars": float(avg_stars) if avg_stars is not None else None,
        "count": int(count),
    }


@router.get("/api/data-products/{catalog}/{schema}/reviews")
async def list_data_product_reviews(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Return every review + the aggregate summary.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        ``{"data_product_id": int, "summary": {avg_stars, count},
        "my_review": {...} | None, "reviews": [...]}``.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        rows = (
            session.execute(
                select(DataProductReview)
                .where(
                    DataProductReview.workspace_id == workspace_id,
                    DataProductReview.data_product_id == row.id,
                )
                .order_by(DataProductReview.created_at.desc())
            )
            .scalars()
            .all()
        )
        author_ids = {r.author_user_id for r in rows}
        author_map: dict[int, tuple[str, str]] = {}
        if author_ids:
            users = (
                session.execute(select(User).where(User.id.in_(author_ids)))
                .scalars()
                .all()
            )
            author_map = {u.id: (u.email, u.display_name) for u in users}

        summary = _summary_for(session, workspace_id, row.id)

    payload = []
    my_review: dict[str, Any] | None = None
    for r in rows:
        author_email, author_display = author_map.get(r.author_user_id, (None, None))
        s = _serialise_review(
            r,
            author_email=author_email,
            author_display_name=author_display,
        )
        payload.append(s)
        if r.author_user_id == user["id"]:
            my_review = s

    return {
        "data_product_id": row.id,
        "summary": summary,
        "my_review": my_review,
        "reviews": payload,
    }


@router.put("/api/data-products/{catalog}/{schema}/reviews")
async def upsert_data_product_review(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Idempotent upsert of the caller's review on this product.

    Body: ``{"stars": int (1..5), "body_md": str?}``.

    Args:
        catalog: UC catalog segment.
        schema: UC schema segment.
        request: Incoming FastAPI request.

    Returns:
        Serialised review row.

    Raises:
        HTTPException: 400 on invalid stars or missing payload.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    body = await request.json()
    raw_stars = body.get("stars")
    if raw_stars is None:
        # bare-http-ok: required field.
        raise HTTPException(status_code=400, detail="stars is required")
    try:
        stars = int(raw_stars)
    except (TypeError, ValueError):
        # bare-http-ok: stars must be int.
        raise HTTPException(status_code=400, detail="stars must be an int") from None
    if stars < 1 or stars > 5:
        # bare-http-ok: stars range — DB CHECK is the canonical gate
        # but we raise a clean 400 instead of a 500 from an IntegrityError.
        raise HTTPException(status_code=400, detail="stars must be in 1..5")
    body_md = (body.get("body_md") or "").strip()

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        existing = session.execute(
            select(DataProductReview).where(
                DataProductReview.workspace_id == workspace_id,
                DataProductReview.data_product_id == row.id,
                DataProductReview.author_user_id == user["id"],
            )
        ).scalar_one_or_none()

        if existing is not None:
            existing.stars = stars
            existing.body_md = body_md
            existing.dp_version_at_review = row.version
            existing.updated_at = now
            session.add(existing)
            review = existing
        else:
            review = DataProductReview(
                workspace_id=workspace_id,
                data_product_id=row.id,
                author_user_id=user["id"],
                stars=stars,
                body_md=body_md,
                dp_version_at_review=row.version,
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
        review_dp_id = review.data_product_id
        review_stars = review.stars

    # Phase 71.4: fan-out + governance event.  We always emit on
    # PUT — including the upsert case — because a star change is
    # something followers want to know about.
    source_url = f"/data-products/{catalog}/{schema}#tab-reviews"
    summary = (
        f"@{author_email or 'someone'} reviewed {catalog}.{schema} "
        f"({stars}/5)"
    )
    fanout_dataproduct_event(
        factory,
        event_type=EVENT_TYPE_DATA_PRODUCT_REVIEWED,
        data_product_id=review_dp_id,
        workspace_id=workspace_id,
        actor_user_id=user["id"],
        source_url=source_url,
        summary_md=summary,
    )
    await emit_governance_event(
        EVENT_TYPE_DATA_PRODUCT_REVIEWED,
        {
            "data_product_id": review_dp_id,
            "data_product_ref": f"{catalog}.{schema}",
            "review_id": review_id,
            "author_user_id": user["id"],
            "author_email": author_email,
            "stars": review_stars,
        },
        settings=request.app.state.settings,
        session_factory=factory,
        workspace_id=workspace_id,
    )

    return _serialise_review(
        review,
        author_email=author_email,
        author_display_name=author_display,
    )


@router.delete("/api/data-products/{catalog}/{schema}/reviews")
async def delete_data_product_review(
    catalog: str,
    schema: str,
    request: Request,
) -> dict[str, Any]:
    """Remove the caller's review on this product.

    Self only — there is no per-product moderator role for reviews
    (steward + admin do not get a "delete a customer review" gate).
    Idempotent on a missing row.

    Returns:
        ``{"deleted": bool}`` — true when a row was removed.
    """
    require_user(request)
    user = get_user(request)
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    row, _contract, _email, _display = load_one(factory, workspace_id, catalog, schema)

    with factory() as session:
        existing = session.execute(
            select(DataProductReview).where(
                DataProductReview.workspace_id == workspace_id,
                DataProductReview.data_product_id == row.id,
                DataProductReview.author_user_id == user["id"],
            )
        ).scalar_one_or_none()
        if existing is None:
            return {"deleted": False}
        session.delete(existing)
        session.commit()
    return {"deleted": True}
