"""Hourly rollup of the raw query-cost ledger into bucketed rows."""

from __future__ import annotations

import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from pointlessql.models import (
    DataProductCostBucketHourly,
    DataProductQueryCost,
)
from pointlessql.types import SessionFactory


def roll_up_hourly_buckets(
    session_factory: SessionFactory,
    *,
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
) -> int:
    """Aggregate raw rows into hourly buckets; upsert on (hour, product, user).

    Args:
        session_factory: Sessionmaker callable.
        since: Window start (inclusive); defaults to one hour ago.
        until: Window end (exclusive); defaults to wall-clock now.

    Returns:
        Number of bucket rows written or refreshed.
    """
    moment = until or datetime.datetime.now(datetime.UTC)
    window_start = since or (moment - datetime.timedelta(hours=1))
    with session_factory() as session:
        raw_rows = list(
            session.scalars(
                select(DataProductQueryCost)
                .where(DataProductQueryCost.started_at >= window_start)
                .where(DataProductQueryCost.started_at < moment)
                .where(DataProductQueryCost.authoring_product_id.isnot(None))
            )
        )
        buckets: dict[tuple[Any, ...], dict[str, Any]] = {}
        for row in raw_rows:
            hour = row.started_at.replace(minute=0, second=0, microsecond=0)
            key = (
                hour,
                int(row.authoring_product_id),  # type: ignore[arg-type]
                row.principal_user_id,
            )
            bucket = buckets.setdefault(
                key,
                {
                    "bucket_hour": hour,
                    "data_product_id": int(row.authoring_product_id),  # type: ignore[arg-type]
                    "consumer_user_id": row.principal_user_id,
                    "query_count": 0,
                    "total_duration_ms": 0,
                    "total_estimated_cost": Decimal("0"),
                    "total_bytes_scanned": 0,
                },
            )
            bucket["query_count"] += 1
            bucket["total_duration_ms"] += int(row.duration_ms or 0)
            bucket["total_estimated_cost"] += Decimal(
                str(row.estimated_cost or 0)
            )
            bucket["total_bytes_scanned"] += int(row.bytes_scanned or 0)

        written = 0
        for key, payload in buckets.items():
            existing = session.scalar(
                select(DataProductCostBucketHourly)
                .where(DataProductCostBucketHourly.bucket_hour == payload["bucket_hour"])
                .where(
                    DataProductCostBucketHourly.data_product_id
                    == payload["data_product_id"]
                )
                .where(
                    DataProductCostBucketHourly.consumer_user_id.is_(None)
                    if payload["consumer_user_id"] is None
                    else DataProductCostBucketHourly.consumer_user_id
                    == payload["consumer_user_id"]
                )
            )
            if existing is None:
                existing = DataProductCostBucketHourly(**payload)
                session.add(existing)
            else:
                existing.query_count = int(payload["query_count"])
                existing.total_duration_ms = int(payload["total_duration_ms"])
                existing.total_estimated_cost = payload["total_estimated_cost"]
                existing.total_bytes_scanned = int(payload["total_bytes_scanned"])
            written += 1
        session.commit()
    return written
