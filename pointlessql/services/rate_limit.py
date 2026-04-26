"""Database-backed fixed-window rate limiter.

Hardens the ``/auth/*`` surface against credential-stuffing and
registration spam. The mechanism is a fixed-window counter over the
:class:`~pointlessql.models.RateLimitEvent` table: each allowed
request inserts one row, and a subsequent check counts rows for the
same ``bucket`` within the configured window. Opportunistic cleanup
runs inside the same check so the table stays bounded without a
background sweeper — the ``(bucket, created_at)`` composite index
keeps both the count and the cleanup ``DELETE`` cheap.

The helpers are pure SQLAlchemy so they can be exercised from unit
tests without FastAPI plumbing. The web-layer integration lives in
:mod:`pointlessql.api.rate_limit_middleware`.
"""

from __future__ import annotations

import datetime
import logging
import math

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import RateLimitEvent

logger = logging.getLogger(__name__)


def bucket_for(route_tag: str, dimension: str, identity: str) -> str:
    """Return the canonical bucket key for a rate-limit rule.

    The format ``"<route_tag>.<dimension>:<identity>"`` is stable across
    the services and middleware layers so both can reason about the
    same string without passing structured data around.

    Args:
        route_tag: Short identifier for the protected route
            (e.g. ``"auth.login"``).
        dimension: The axis the bucket is keyed on, e.g. ``"ip"`` or
            ``"email"``.
        identity: The raw value for that axis — an IP address, a form
            email, etc. Not hashed: the admin audit viewer shows these
            strings verbatim so operators can tell real from forged
            traffic apart.

    Returns:
        str: The bucket key.
    """
    return f"{route_tag}.{dimension}:{identity}"


def check_and_record(
    factory: sessionmaker[Session],
    bucket: str,
    limit: int,
    window_seconds: int,
) -> tuple[bool, int]:
    """Apply a fixed-window rate-limit decision for ``bucket``.

    Opens a session, prunes rows older than the window for this bucket
    (keeps the index hot), counts the remaining rows, and either
    inserts a new event (allowed) or returns a ``Retry-After`` hint
    derived from the oldest row still inside the window (denied).

    The slight burst that fixed-window counters allow at window
    boundaries is acceptable for a brute-force brake — the goal is to
    stop credential stuffing, not to shape interactive traffic.

    Args:
        factory: SQLAlchemy session factory.
        bucket: The bucket key produced by :func:`bucket_for`.
        limit: Maximum number of allowed events within the window.
        window_seconds: Window length in seconds.

    Returns:
        A tuple ``(allowed, retry_after_seconds)``. ``allowed`` is
        ``True`` when the current request fits under the limit;
        ``retry_after_seconds`` is ``0`` in that case and a positive
        integer when denied.
    """
    now = datetime.datetime.now(datetime.UTC)
    cutoff = now - datetime.timedelta(seconds=window_seconds)

    with factory() as session:
        session.execute(
            delete(RateLimitEvent).where(
                RateLimitEvent.bucket == bucket,
                RateLimitEvent.created_at < cutoff,
            )
        )

        count = session.scalar(
            select(func.count(RateLimitEvent.id)).where(
                RateLimitEvent.bucket == bucket,
                RateLimitEvent.created_at >= cutoff,
            )
        )
        count = int(count or 0)

        if count >= limit:
            oldest = session.scalar(
                select(func.min(RateLimitEvent.created_at)).where(
                    RateLimitEvent.bucket == bucket,
                    RateLimitEvent.created_at >= cutoff,
                )
            )
            session.commit()
            if oldest is None:
                # Races are possible between the count and the min
                # query; a conservative retry-after of one second keeps
                # the rejection meaningful without pretending we know
                # the exact release instant.
                return False, 1
            # SQLite returns naive datetimes even when the column is
            # declared timezone-aware; re-attach UTC so the subtraction
            # against ``now`` does not raise.
            if oldest.tzinfo is None:
                oldest = oldest.replace(tzinfo=datetime.UTC)
            release = oldest + datetime.timedelta(seconds=window_seconds)
            remaining = (release - now).total_seconds()
            return False, max(1, int(math.ceil(remaining)))

        session.add(RateLimitEvent(bucket=bucket, created_at=now))
        session.commit()
        return True, 0
