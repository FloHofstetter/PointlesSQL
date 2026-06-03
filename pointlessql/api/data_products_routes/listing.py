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
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.catalog._domains import Domain
from pointlessql.models.social._entity_readme import EntityReadme
from pointlessql.models.social._social_follow import SocialFollow
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.data_products import compute_badges_bulk, endorsements_for_products
from pointlessql.services.glossary import terms_for_schemas

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
async def list_data_products(request: Request, q: str | None = None) -> dict[str, Any]:
    """Return every cached data product in the active workspace.

    Each row is enriched, in bulk, with everything the browse + the
    marketplace discovery view need to render without a per-product
    follow-up call: the ``avg_stars`` + ``review_count`` aggregate for
    the star badge, follow / comment / readme signals, the auto-computed
    health badges, the product's active ``endorsements`` (so a
    "certified" badge can show), and the business ``glossary_terms``
    bound to any of its columns (so discovery search can match by
    meaning, not just by name).

    Args:
        request: Incoming FastAPI request.
        q: Optional case-insensitive prefix filter on
            ``catalog_name``, ``schema_name``, or the
            ``catalog.schema`` reference used by
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
            users = session.execute(select(User).where(User.id.in_(steward_ids))).scalars().all()
            steward_map = {u.id: (u.email, u.display_name) for u in users}

        domain_ids = [r.domain_id for r in rows if r.domain_id is not None]
        domain_map: dict[int, dict[str, Any]] = {}
        if domain_ids:
            domains = session.execute(select(Domain).where(Domain.id.in_(domain_ids))).scalars()
            domain_map = {
                d.id: {"id": d.id, "slug": d.slug, "name": d.name, "archetype": d.archetype}
                for d in domains
            }

        dp_ids = [r.id for r in rows]
        review_agg: dict[int, tuple[float | None, int]] = {}
        follow_agg: dict[int, int] = {}
        comment_7d_agg: dict[int, int] = {}
        has_readme_set: set[int] = set()
        endorsement_map: dict[int, list[dict[str, Any]]] = {}
        glossary_map: dict[tuple[str, str], list[str]] = {}
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
                select(SocialTarget.data_product_id)
                .join(EntityReadme, EntityReadme.social_target_id == SocialTarget.id)
                .where(
                    EntityReadme.workspace_id == workspace_id,
                    SocialTarget.entity_kind == "dp",
                    SocialTarget.data_product_id.in_(dp_ids),
                )
                .distinct()
            ).all()
            has_readme_set = {int(r[0]) for r in readme_rows if r[0] is not None}

            # auto-computed badges (bulk).
            badges_by_id = compute_badges_bulk(
                session,
                workspace_id=workspace_id,
                dps=list(rows),
                now=now,
            )

            # active endorsements (bulk) — drives the "certified" badge.
            endorsement_map = endorsements_for_products(
                session,
                workspace_id=workspace_id,
                dp_ids=dp_ids,
            )

            # business-glossary terms bound to any column (bulk) — lets
            # discovery search match by meaning, keyed on (catalog, schema).
            glossary_map = terms_for_schemas(
                factory,
                workspace_id=workspace_id,
                pairs=[(r.catalog_name, r.schema_name) for r in rows],
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
                domain=domain_map.get(row.domain_id) if row.domain_id is not None else None,
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
            payload["endorsements"] = endorsement_map.get(row.id, [])
            payload["glossary_terms"] = glossary_map.get(
                (row.catalog_name, row.schema_name), []
            )
            items.append(payload)

    return {"workspace_id": workspace_id, "data_products": items}
