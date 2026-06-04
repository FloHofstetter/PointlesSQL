"""Aggregator for the mesh-cost dashboard + per-product / per-consumer reads."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from pointlessql.models import (
    DataProduct,
    DataProductCostBucketHourly,
    DataProductSLO,
)
from pointlessql.types import SessionFactory


def cost_by_product(
    session_factory: SessionFactory,
    *,
    workspace_id: int = 1,
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
) -> list[dict[str, Any]]:
    """Aggregate hourly buckets by product within the window."""
    moment = until or datetime.datetime.now(datetime.UTC)
    start = since or (moment - datetime.timedelta(days=7))
    by_product: dict[int, dict[str, Any]] = {}
    with session_factory() as session:
        products = list(
            session.scalars(
                select(DataProduct).where(DataProduct.workspace_id == workspace_id)
            )
        )
        ref_by_id = {
            int(p.id): f"{p.catalog_name}.{p.schema_name}" for p in products
        }
        rows = session.scalars(
            select(DataProductCostBucketHourly)
            .where(DataProductCostBucketHourly.bucket_hour >= start)
            .where(DataProductCostBucketHourly.bucket_hour < moment)
        )
        for row in rows:
            product_id = int(row.data_product_id)
            entry = by_product.setdefault(
                product_id,
                {
                    "data_product_id": product_id,
                    "ref": ref_by_id.get(product_id, "unknown"),
                    "query_count": 0,
                    "total_duration_ms": 0,
                    "total_estimated_cost": Decimal("0"),
                    "total_bytes_scanned": 0,
                },
            )
            entry["query_count"] += int(row.query_count or 0)
            entry["total_duration_ms"] += int(row.total_duration_ms or 0)
            entry["total_estimated_cost"] += Decimal(
                str(row.total_estimated_cost or 0)
            )
            entry["total_bytes_scanned"] += int(row.total_bytes_scanned or 0)
    for entry in by_product.values():
        entry["total_estimated_cost"] = float(entry["total_estimated_cost"])
    return sorted(
        by_product.values(),
        key=lambda e: float(e["total_estimated_cost"]),
        reverse=True,
    )


def cost_by_consumer(
    session_factory: SessionFactory,
    *,
    workspace_id: int = 1,
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
) -> list[dict[str, Any]]:
    """Aggregate hourly buckets by consumer within the window."""
    moment = until or datetime.datetime.now(datetime.UTC)
    start = since or (moment - datetime.timedelta(days=7))
    by_consumer: dict[int | None, dict[str, Any]] = {}
    with session_factory() as session:
        rows = session.scalars(
            select(DataProductCostBucketHourly)
            .where(DataProductCostBucketHourly.bucket_hour >= start)
            .where(DataProductCostBucketHourly.bucket_hour < moment)
        )
        for row in rows:
            consumer = row.consumer_user_id
            key = int(consumer) if consumer is not None else None
            entry = by_consumer.setdefault(
                key,
                {
                    "consumer_user_id": key,
                    "query_count": 0,
                    "total_duration_ms": 0,
                    "total_estimated_cost": Decimal("0"),
                    "total_bytes_scanned": 0,
                },
            )
            entry["query_count"] += int(row.query_count or 0)
            entry["total_duration_ms"] += int(row.total_duration_ms or 0)
            entry["total_estimated_cost"] += Decimal(
                str(row.total_estimated_cost or 0)
            )
            entry["total_bytes_scanned"] += int(row.total_bytes_scanned or 0)
    for entry in by_consumer.values():
        entry["total_estimated_cost"] = float(entry["total_estimated_cost"])
    return sorted(
        by_consumer.values(),
        key=lambda e: int(e["query_count"]),
        reverse=True,
    )


def mesh_health_full(
    session_factory: SessionFactory,
    *,
    workspace_id: int = 1,
    sigma: float = 2.0,
) -> dict[str, Any]:
    """Return the comprehensive mesh-health-dashboard payload.

    Builds on :func:`services.mesh.mesh_health` and layers per-domain
    rollups, cost trend, top consumers, and recent deliveries.
    """
    from pointlessql.services.mesh import mesh_health

    base = mesh_health(session_factory, workspace_id=workspace_id, sigma=sigma)
    per_domain = _aggregate_per_domain(session_factory, workspace_id, base)
    cost_trend = cost_by_product(session_factory, workspace_id=workspace_id)
    top_consumers = cost_by_consumer(
        session_factory, workspace_id=workspace_id
    )[:10]
    base["per_domain"] = per_domain
    base["cost_trend"] = cost_trend
    base["top_consumers"] = top_consumers
    return base


def _aggregate_per_domain(
    session_factory: SessionFactory,
    workspace_id: int,
    base: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    """Group :func:`mesh_health`'s products by domain."""
    domain_by_id: dict[int, str | None] = {}
    with session_factory() as session:
        for product in session.scalars(
            select(DataProduct).where(DataProduct.workspace_id == workspace_id)
        ):
            domain_by_id[int(product.id)] = (
                product.domain if hasattr(product, "domain") else None
            )
        # SLO presence informs the unknown count.
        _ = session.scalars(select(DataProductSLO)).all()
    by_domain: dict[str, dict[str, Any]] = {}
    for product in base.get("products", []):
        domain = (
            domain_by_id.get(int(product.get("data_product_id", -1)))
            or "uncategorised"
        )
        entry = by_domain.setdefault(
            domain,
            {"green": 0, "red": 0, "unknown": 0, "total": 0},
        )
        band = str(product.get("band", "unknown"))
        if band == "green":
            entry["green"] += 1
        elif band == "red":
            entry["red"] += 1
        else:
            entry["unknown"] += 1
        entry["total"] += 1
    return by_domain
