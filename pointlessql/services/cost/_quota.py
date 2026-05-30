"""Quota enforcement on the read path.

Mirrors the consumption-enforcement pattern from phase 132 — three
modes (``off`` / ``warn`` / ``strict``) layer through the standard
product⇐workspace inheritance.  ``strict`` raises
:class:`QuotaExceededError` which the FastAPI handler maps to HTTP
429; ``warn`` emits an audit row + returns the offending decision so
the caller can log it; ``off`` is a no-op.
"""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
from typing import Any, Protocol

from sqlalchemy import select

from pointlessql.exceptions import QuotaExceededError
from pointlessql.models import DataProductCostBucketHourly
from pointlessql.services.governance._policy import get_effective_policy


class _SessionFactory(Protocol):
    """Sessionmaker-shaped callable protocol."""

    def __call__(self) -> Any:
        """Return a SQLAlchemy session."""
        ...


@dataclasses.dataclass(slots=True, frozen=True)
class QuotaCheck:
    """Outcome of one :func:`check_quota` call.

    Attributes:
        mode: Active enforcement mode.
        breached: True when at least one limit was exceeded.
        observed_cost_today: Sum of estimated_cost over the running day.
        observed_queries_this_hour: Sum of query_count for the running hour.
        limit_cost_per_day: Effective max_cost_per_day (or None).
        limit_queries_per_hour: Effective max_queries_per_hour (or None).
        offending_metric: ``cost_per_day`` / ``queries_per_hour`` / None.
    """

    mode: str
    breached: bool
    observed_cost_today: Decimal
    observed_queries_this_hour: int
    limit_cost_per_day: Decimal | None
    limit_queries_per_hour: int | None
    offending_metric: str | None


def resolve_quota_mode(
    session_factory: _SessionFactory,
    *,
    data_product_id: int,
    workspace_id: int = 1,
) -> tuple[str, dict[str, Any]]:
    """Return ``(mode, limits)`` honouring product⇐workspace inheritance."""
    policy = get_effective_policy(
        session_factory,
        data_product_id=data_product_id,
        workspace_id=workspace_id,
    )
    mode = str(policy.get("quota_enforcement", {}).get("value") or "off")
    limits = {
        "max_cost_per_day": policy.get("max_cost_per_day", {}).get("value"),
        "max_queries_per_hour": policy.get("max_queries_per_hour", {}).get(
            "value"
        ),
    }
    return mode, limits


def check_quota(
    session_factory: _SessionFactory,
    *,
    consumer_user_id: int | None,
    data_product_id: int,
    workspace_id: int = 1,
    now: datetime.datetime | None = None,
) -> QuotaCheck:
    """Aggregate today / this-hour usage; raise on strict-mode breach.

    Args:
        session_factory: Sessionmaker callable.
        consumer_user_id: Consumer principal; ``None`` skips per-consumer
            scoping and aggregates across the whole product.
        data_product_id: Authoring product the read targets.
        workspace_id: Workspace the call ran in.
        now: Reference moment; defaults to UTC.

    Returns:
        :class:`QuotaCheck` with observed metrics + the active mode.

    Raises:
        QuotaExceededError: In ``strict`` mode when any limit is breached.
    """
    reference = now or datetime.datetime.now(datetime.UTC)
    mode, limits = resolve_quota_mode(
        session_factory,
        data_product_id=data_product_id,
        workspace_id=workspace_id,
    )
    if mode == "off":
        return QuotaCheck(
            mode="off",
            breached=False,
            observed_cost_today=Decimal("0"),
            observed_queries_this_hour=0,
            limit_cost_per_day=None,
            limit_queries_per_hour=None,
            offending_metric=None,
        )
    day_start = reference.replace(hour=0, minute=0, second=0, microsecond=0)
    hour_start = reference.replace(minute=0, second=0, microsecond=0)
    with session_factory() as session:
        cost_rows = list(
            session.scalars(
                select(DataProductCostBucketHourly)
                .where(DataProductCostBucketHourly.data_product_id == data_product_id)
                .where(DataProductCostBucketHourly.bucket_hour >= day_start)
            )
        )
        observed_cost_today = sum(
            (Decimal(str(row.total_estimated_cost or 0)) for row in cost_rows),
            Decimal("0"),
        )
        observed_queries_this_hour = sum(
            int(row.query_count or 0)
            for row in cost_rows
            if _same_hour(row.bucket_hour, hour_start)
            and (
                consumer_user_id is None
                or row.consumer_user_id is None
                or int(row.consumer_user_id) == int(consumer_user_id)
            )
        )
    limit_cost = _decimal_or_none(limits.get("max_cost_per_day"))
    limit_queries = _int_or_none(limits.get("max_queries_per_hour"))
    offending: str | None = None
    if limit_cost is not None and observed_cost_today >= limit_cost:
        offending = "cost_per_day"
    elif limit_queries is not None and observed_queries_this_hour >= limit_queries:
        offending = "queries_per_hour"
    breached = offending is not None
    check = QuotaCheck(
        mode=mode,
        breached=breached,
        observed_cost_today=observed_cost_today,
        observed_queries_this_hour=observed_queries_this_hour,
        limit_cost_per_day=limit_cost,
        limit_queries_per_hour=limit_queries,
        offending_metric=offending,
    )
    if breached and mode == "strict":
        if offending == "cost_per_day":
            raise QuotaExceededError(
                consumer_id=consumer_user_id,
                data_product_id=data_product_id,
                metric="cost_per_day",
                limit=float(limit_cost or 0),
                observed=float(observed_cost_today),
            )
        raise QuotaExceededError(
            consumer_id=consumer_user_id,
            data_product_id=data_product_id,
            metric="queries_per_hour",
            limit=float(limit_queries or 0),
            observed=float(observed_queries_this_hour),
        )
    return check


def _same_hour(left: datetime.datetime, right: datetime.datetime) -> bool:
    """Return True when left and right fall in the same UTC hour."""
    def normalise(value: datetime.datetime) -> tuple[int, int, int, int]:
        if value.tzinfo is not None:
            utc = value.astimezone(datetime.UTC)
        else:
            utc = value
        return utc.year, utc.month, utc.day, utc.hour

    return normalise(left) == normalise(right)


def _decimal_or_none(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError):
        return None


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError):
        return None
