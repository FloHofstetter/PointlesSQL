"""``GET /api/data-products`` — list every cached product in workspace."""

from __future__ import annotations

import datetime
from typing import Any

from fastapi import APIRouter, Request
from sqlalchemy import func, select

from pointlessql.api.data_products_routes._shared import serialise_product
from pointlessql.api.dependencies import current_workspace_id
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_readme import DataProductReadme
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._social_follow import SocialFollow
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.data_products import compute_badges_bulk

router = APIRouter(tags=["data-products"])


def _freshness_status(
    last_loaded_at: datetime.datetime,
    sla_minutes: int | None,
    now: datetime.datetime,
) -> str:
    """Compute the per-product freshness status for the browse listing.

    SQLite returns naive datetimes even for tz-aware columns; treat
    those as UTC for the comparison so we never trip the "naive vs
    aware" TypeError when ``now`` is the standard tz-aware
    ``datetime.now(UTC)``.

    Returns ``"on_time"`` when within SLA, ``"stale"`` when over,
    and ``"no_sla"`` when no SLA expectation is set.
    """
    if sla_minutes is None:
        return "no_sla"
    loaded = last_loaded_at
    if loaded.tzinfo is None:
        loaded = loaded.replace(tzinfo=datetime.UTC)
    deadline = loaded + datetime.timedelta(minutes=sla_minutes)
    return "on_time" if now <= deadline else "stale"


@router.get("/api/data-products")
async def list_data_products(
    request: Request, q: str | None = None
) -> dict[str, Any]:
    """Return every cached data product in the active workspace.

    Each row is enriched with the Phase-71.2 ``avg_stars`` +
    ``review_count`` aggregate so the browse-page cards (and the
    Phase-71.6 sortable table) can render the star badge without
    a follow-up call per product.

    Args:
        request: Incoming FastAPI request.
        q: Optional case-insensitive prefix filter on
            ``catalog_name``, ``schema_name``, or the
            ``catalog.schema`` reference (Phase 76.6.1) used by
            the ``#dp:`` mention-autocomplete picker.

    Returns:
        ``{"workspace_id": int, "data_products": [...]}`` ordered by
        catalog/schema name.
    """
    workspace_id = current_workspace_id(request)
    factory = request.app.state.session_factory
    items: list[dict[str, Any]] = []
    with factory() as session:
        stmt = (
            select(DataProduct)
            .where(DataProduct.workspace_id == workspace_id)
            .order_by(DataProduct.catalog_name, DataProduct.schema_name)
        )
        if q:
            needle = f"{q.strip().lower()}%"
            stmt = stmt.where(
                func.lower(DataProduct.catalog_name).like(needle)
                | func.lower(DataProduct.schema_name).like(needle)
                | func.lower(
                    func.coalesce(DataProduct.catalog_name, "")
                    + "."
                    + func.coalesce(DataProduct.schema_name, "")
                ).like(needle)
            )
        rows = session.execute(stmt).scalars().all()
        steward_ids = [r.steward_user_id for r in rows if r.steward_user_id is not None]
        steward_map: dict[int, tuple[str, str]] = {}
        if steward_ids:
            users = (
                session.execute(select(User).where(User.id.in_(steward_ids)))
                .scalars()
                .all()
            )
            steward_map = {u.id: (u.email, u.display_name) for u in users}

        dp_ids = [r.id for r in rows]
        review_agg: dict[int, tuple[float | None, int]] = {}
        follow_agg: dict[int, int] = {}
        comment_7d_agg: dict[int, int] = {}
        has_readme_set: set[int] = set()
        now = datetime.datetime.now(datetime.UTC)
        seven_days_ago = now - datetime.timedelta(days=7)

        if dp_ids:
            review_rows = session.execute(
                select(
                    DataProductReview.data_product_id,
                    func.avg(DataProductReview.stars),
                    func.count(DataProductReview.id),
                )
                .where(
                    DataProductReview.workspace_id == workspace_id,
                    DataProductReview.data_product_id.in_(dp_ids),
                )
                .group_by(DataProductReview.data_product_id)
            ).all()
            review_agg = {
                int(dp_id): (float(avg) if avg is not None else None, int(cnt))
                for dp_id, avg, cnt in review_rows
            }

            follow_rows = session.execute(
                select(
                    SocialTarget.data_product_id,
                    func.count(SocialFollow.user_id),
                )
                .join(
                    SocialFollow,
                    SocialFollow.social_target_id == SocialTarget.id,
                )
                .where(
                    SocialFollow.workspace_id == workspace_id,
                    SocialTarget.entity_kind == "dp",
                    SocialTarget.data_product_id.in_(dp_ids),
                )
                .group_by(SocialTarget.data_product_id)
            ).all()
            follow_agg = {int(dp_id): int(cnt) for dp_id, cnt in follow_rows}

            comment_rows = session.execute(
                select(
                    DataProductComment.data_product_id,
                    func.count(DataProductComment.id),
                )
                .where(
                    DataProductComment.workspace_id == workspace_id,
                    DataProductComment.data_product_id.in_(dp_ids),
                    DataProductComment.deleted_at.is_(None),
                    DataProductComment.created_at >= seven_days_ago,
                )
                .group_by(DataProductComment.data_product_id)
            ).all()
            comment_7d_agg = {int(dp_id): int(cnt) for dp_id, cnt in comment_rows}

            readme_rows = session.execute(
                select(DataProductReadme.data_product_id)
                .where(
                    DataProductReadme.workspace_id == workspace_id,
                    DataProductReadme.data_product_id.in_(dp_ids),
                )
                .distinct()
            ).all()
            has_readme_set = {int(r[0]) for r in readme_rows}

            # Phase 72.2 — auto-computed badges (bulk).
            badges_by_id = compute_badges_bulk(
                session,
                workspace_id=workspace_id,
                dps=list(rows),
                now=now,
            )
        else:
            badges_by_id: dict[int, dict[str, Any]] = {}

        for row in rows:
            email, display = (
                steward_map.get(row.steward_user_id, (None, None))
                if row.steward_user_id is not None
                else (None, None)
            )
            payload = serialise_product(
                row,
                steward_email=email,
                steward_display_name=display,
            )
            avg, count = review_agg.get(row.id, (None, 0))
            payload["avg_stars"] = avg
            payload["review_count"] = count
            payload["follow_count"] = follow_agg.get(row.id, 0)
            payload["comment_count_7d"] = comment_7d_agg.get(row.id, 0)
            payload["has_readme"] = row.id in has_readme_set
            payload["freshness_status"] = _freshness_status(
                row.last_loaded_at, row.sla_minutes, now
            )
            payload["badges"] = badges_by_id.get(
                row.id,
                {
                    "downstream_count": 0,
                    "agent_run_count_7d": 0,
                    "last_rollback_passed": None,
                    "freshness_on_time_30d_pct": 100.0,
                },
            )
            items.append(payload)

    return {"workspace_id": workspace_id, "data_products": items}
