"""per-API-key usage aggregation.

Aggregated per ``(api_key_id, bucket_minute, source_ip)`` triple to
avoid one row per request.  Hot path: middleware enqueues into an
in-process ``collections.Counter`` on ``app.state``; flusher task
drains it every 30s into the ``api_key_usage_buckets`` table.

Trade-off documented in ``docs/admin/api-key-acls.md``: a worker
crash loses up to 30s of usage events.  Acceptable for a monitoring
surface (not a billing source).

The summary endpoint at ``GET /api/admin/api-keys/{name}/usage``
returns the 30-day daily aggregate + top source IPs.
"""

from __future__ import annotations

import datetime
import logging
from collections import Counter
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import ApiKeyUsageBucket

logger = logging.getLogger(__name__)


def _truncate_to_minute(dt: datetime.datetime) -> datetime.datetime:
    """Drop seconds + microseconds.  Always returns aware UTC."""
    aware = dt if dt.tzinfo else dt.replace(tzinfo=datetime.UTC)
    return aware.replace(second=0, microsecond=0)


def record_use(app_state: Any, *, api_key_id: int, source_ip: str | None) -> None:
    """Buffer a single Bearer-auth success for the flusher.

    Args:
        app_state: ``app.state`` of the running FastAPI app.
        api_key_id: The matched key's id.
        source_ip: Client source IP; ``None`` is normalised to ``""``
            so the Counter key is hashable + the eventual DB row has
            a non-NULL value (the UNIQUE constraint covers
            ``source_ip``).
    """
    if api_key_id <= 0:
        return
    buffer: Counter[tuple[int, datetime.datetime, str]] | None = getattr(
        app_state, "api_key_usage_buffer", None
    )
    if buffer is None:
        buffer = Counter()
        app_state.api_key_usage_buffer = buffer
    bucket = _truncate_to_minute(datetime.datetime.now(datetime.UTC))
    buffer[(api_key_id, bucket, source_ip or "")] += 1


def flush_buffer(session_factory: sessionmaker[Session], app_state: Any) -> int:
    """Drain the in-process Counter into ``api_key_usage_buckets``.

    Per-tick read-modify-write UPSERT so concurrent flushes from
    different workers don't lose counts (SQLite tests; PG production
    would ideally use ``INSERT ... ON CONFLICT DO UPDATE SET count =
    count + excluded.count`` — keep that as a follow-up
    optimisation once we have multi-worker traffic).

    Args:
        session_factory: SQLAlchemy session factory.
        app_state: ``app.state`` of the running FastAPI app.

    Returns:
        Number of bucket rows touched this tick (combined inserts +
        updates).
    """
    buffer: Counter[tuple[int, datetime.datetime, str]] | None = getattr(
        app_state, "api_key_usage_buffer", None
    )
    if not buffer:
        return 0
    # Swap the buffer atomically so concurrent record_use calls don't
    # drop events while we're flushing.
    snapshot = Counter(buffer)
    buffer.clear()
    now = datetime.datetime.now(datetime.UTC)
    touched = 0
    with session_factory() as session:
        for (api_key_id, bucket_minute, source_ip), delta in snapshot.items():
            existing = session.scalar(
                select(ApiKeyUsageBucket).where(
                    ApiKeyUsageBucket.api_key_id == api_key_id,
                    ApiKeyUsageBucket.bucket_minute == bucket_minute,
                    ApiKeyUsageBucket.source_ip == source_ip,
                )
            )
            if existing is None:
                session.add(
                    ApiKeyUsageBucket(
                        api_key_id=api_key_id,
                        bucket_minute=bucket_minute,
                        source_ip=source_ip,
                        count=delta,
                        last_seen_at=now,
                    )
                )
            else:
                existing.count = (existing.count or 0) + delta
                existing.last_seen_at = now
            touched += 1
        session.commit()
    if touched:
        logger.debug("api-key usage flush: %d buckets touched", touched)
    return touched


def cleanup_stale_usage(session_factory: sessionmaker[Session], *, retention_days: int) -> int:
    """Delete usage buckets older than *retention_days*.

    Args:
        session_factory: SQLAlchemy session factory.
        retention_days: Age threshold; rows with ``bucket_minute <
            now - retention_days`` are deleted.

    Returns:
        Number of rows deleted.
    """
    if retention_days <= 0:
        return 0
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=retention_days)
    with session_factory() as session:
        result = session.execute(
            delete(ApiKeyUsageBucket).where(ApiKeyUsageBucket.bucket_minute < cutoff)
        )
        session.commit()
        deleted = int(getattr(result, "rowcount", 0) or 0)
    if deleted:
        logger.info("api-key usage retention: pruned %d rows older than %s", deleted, cutoff)
    return deleted


def _rolling_stats(values: list[int]) -> tuple[float, float]:
    """Mean + sample standard deviation of *values*; returns (0.0, 0.0) on empty."""
    if not values:
        return 0.0, 0.0
    n = len(values)
    mean = sum(values) / n
    if n < 2:
        return mean, 0.0
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return mean, variance**0.5


def get_usage_summary(
    session_factory: sessionmaker[Session], *, api_key_id: int, days: int = 30
) -> dict[str, Any]:
    """Aggregate the last *days* of usage for a key with trend annotations.

    Args:
        session_factory: SQLAlchemy session factory.
        api_key_id: Key whose usage to summarise.
        days: Window size in days.  Defaults to 30.

    Returns:
        ``{
            "days": [{"date": "YYYY-MM-DD", "count": int,
                       "is_anomaly": bool}, ...],
            "top_ips": [{"ip": str, "count": int}, ...],
            "wow": {"last_7d": int, "prev_7d": int,
                     "change_pct": float | None},
            "stats": {"mean_7d": float, "std_7d": float},
        }``.

        ``days`` covers exactly the past *days* days (zero-filled).
        ``is_anomaly`` flags a day whose count is more than 3
        standard deviations from the *rolling 7-day mean* — derived
        per-day from the prior 7 days inside the window.  ``wow``
        compares the most recent 7 days to the 7 days before that;
        ``change_pct`` is None when the prior window had zero
        traffic (avoids divide-by-zero "infinity" badges in the
        UI).  ``stats`` carries the window-end mean + stdev so the
        UI can render a baseline overlay.
    """
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=days)
    with session_factory() as session:
        rows = session.execute(
            select(
                ApiKeyUsageBucket.bucket_minute,
                ApiKeyUsageBucket.source_ip,
                ApiKeyUsageBucket.count,
            ).where(
                ApiKeyUsageBucket.api_key_id == api_key_id,
                ApiKeyUsageBucket.bucket_minute >= cutoff,
            )
        ).all()

    daily_counts: dict[datetime.date, int] = {}
    ip_counts: Counter[str] = Counter()
    for bucket_minute, source_ip, count in rows:
        bucket_aware = (
            bucket_minute if bucket_minute.tzinfo else bucket_minute.replace(tzinfo=datetime.UTC)
        )
        date_key = bucket_aware.date()
        daily_counts[date_key] = daily_counts.get(date_key, 0) + count
        ip_counts[source_ip or ""] += count

    today = datetime.datetime.now(datetime.UTC).date()
    counts_in_order = [
        daily_counts.get(today - datetime.timedelta(days=i), 0) for i in range(days - 1, -1, -1)
    ]
    days_list: list[dict[str, Any]] = []
    for idx, count in enumerate(counts_in_order):
        prior_window = counts_in_order[max(0, idx - 7) : idx]
        mean, std = _rolling_stats(prior_window)
        if std > 0:
            is_anomaly = abs(count - mean) > 3 * std
        elif mean > 0:
            # Constant baseline → no std signal; flag spikes >5× the
            # baseline so a sustained-flat pattern interrupted by a
            # burst still surfaces in the UI.
            is_anomaly = count > mean * 5
        else:
            is_anomaly = False
        d = today - datetime.timedelta(days=days - 1 - idx)
        days_list.append({"date": d.isoformat(), "count": count, "is_anomaly": bool(is_anomaly)})
    top_ips = [{"ip": ip, "count": int(c)} for ip, c in ip_counts.most_common(10)]

    last_7d = sum(counts_in_order[-7:]) if counts_in_order else 0
    prev_7d = sum(counts_in_order[-14:-7]) if len(counts_in_order) >= 14 else 0
    change_pct: float | None = None
    if prev_7d > 0:
        change_pct = round((last_7d - prev_7d) / prev_7d * 100.0, 2)
    mean_7d, std_7d = _rolling_stats(counts_in_order[-7:])

    return {
        "days": days_list,
        "top_ips": top_ips,
        "wow": {
            "last_7d": last_7d,
            "prev_7d": prev_7d,
            "change_pct": change_pct,
        },
        "stats": {
            "mean_7d": round(mean_7d, 2),
            "std_7d": round(std_7d, 2),
        },
    }
