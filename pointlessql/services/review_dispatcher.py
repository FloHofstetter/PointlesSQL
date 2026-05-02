"""CloudEvents fan-out for posted agent reviews.

When the Audit-Reviewer-Agent posts a review via
``POST /api/agent-reviews``, the route handler persists the row and
then calls :func:`dispatch_review`, which:

1. Builds a CloudEvents 1.0 envelope of type
   ``pointlessql.agent_review.posted.v1``.
2. Enumerates active :class:`ReviewDestination` rows whose
   ``min_severity`` is satisfied by the review's severity.
3. Reuses the saved-query alert dispatcher's
   :func:`pointlessql.services.alert_dispatcher.dispatch_webhook`
   for the actual HTTP+HMAC+retry round-trip.
4. Records the per-destination outcome onto
   ``AgentReview.delivered_to_json`` so each review row stays
   self-contained for replay and audit-of-audit.

The dispatcher is deliberately oblivious to the markdown body — the
envelope ships ``summary_md`` verbatim, and downstream subscribers
decide whether to render it or not.
"""

from __future__ import annotations

import datetime
import hashlib
import json
import logging
from typing import Any, Protocol
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models.agent_reviews import AgentReview, ReviewDestination
from pointlessql.services.alert_dispatcher import dispatch_webhook

logger = logging.getLogger(__name__)

CLOUDEVENT_TYPE = "pointlessql.agent_review.posted.v1"

# Numeric ordering so a destination's min_severity gate is a simple
# ``>=`` comparison. Lowest = always fires; highest = critical-only.
_SEVERITY_RANK: dict[str, int] = {"ok": 0, "warn": 1, "critical": 2}


class _SessionFactory(Protocol):
    """Minimal sessionmaker contract — narrows the Sphinx dep graph."""

    def __call__(self) -> Session: ...


def build_envelope(
    review: AgentReview,
    *,
    event_id: str | None = None,
    posted_at: datetime.datetime | None = None,
) -> dict[str, Any]:
    """Build the CloudEvents 1.0 envelope for *review*.

    Args:
        review: The persisted review row.
        event_id: Optional ``id`` override; auto-generates a uuid4
            hex when omitted (production path).
        posted_at: Optional CloudEvents ``time`` override; defaults
            to ``review.created_at``.

    Returns:
        A dict ready to JSON-serialise onto the wire.
    """
    eid = event_id or uuid4().hex
    when = (posted_at or review.created_at).astimezone(datetime.UTC).isoformat()
    return {
        "specversion": "1.0",
        "id": eid,
        "source": "/pointlessql/agent-reviews",
        "type": CLOUDEVENT_TYPE,
        "time": when,
        "datacontenttype": "application/json",
        "subject": str(review.id),
        "data": {
            "review_id": review.id,
            "run_id": review.run_id,
            "period_start": review.period_start.astimezone(datetime.UTC).isoformat(),
            "period_end": review.period_end.astimezone(datetime.UTC).isoformat(),
            "severity": review.severity,
            "summary_md": review.summary_md,
        },
    }


def _hash_url(url: str) -> str:
    """Return a stable ``sha256:<hex>`` digest of *url* for the audit log."""
    return "sha256:" + hashlib.sha256(url.encode("utf-8")).hexdigest()


def _select_destinations(session: Session, *, severity: str) -> list[ReviewDestination]:
    """Return active destinations whose min_severity gate passes for *severity*.

    Args:
        session: Open SQLAlchemy session.
        severity: The review's severity (``ok`` / ``warn`` / ``critical``).

    Returns:
        Detached destination rows in primary-key order.
    """
    review_rank = _SEVERITY_RANK[severity]
    rows = list(
        session.scalars(
            select(ReviewDestination)
            .where(ReviewDestination.is_active.is_(True))
            .order_by(ReviewDestination.id.asc())
        ).all()
    )
    return [r for r in rows if _SEVERITY_RANK[r.min_severity] <= review_rank]


async def dispatch_review(
    session_factory: _SessionFactory | sessionmaker[Session],
    review_id: int,
) -> list[dict[str, Any]]:
    """Fan a posted review out to every active webhook destination.

    Args:
        session_factory: Sessionmaker callable.
        review_id: Primary key of the persisted review.

    Returns:
        The fan-out log: one entry per attempted destination, shape
        ``{kind, name, url_hash, delivered_at, status_code}``.  The
        same list is persisted back onto the review's
        ``delivered_to_json`` column so callers can read the result
        from either the return value or the row itself.

    Raises:
        ValueError: When *review_id* does not resolve to a persisted
            :class:`AgentReview` row.
    """
    with session_factory() as session:
        review = session.get(AgentReview, review_id)
        if review is None:
            raise ValueError(f"AgentReview id={review_id} not found")
        envelope = build_envelope(review)
        destinations = _select_destinations(session, severity=review.severity)

    log: list[dict[str, Any]] = []
    for dest in destinations:
        ok = await dispatch_webhook(
            dest.webhook_url,
            envelope,
            hmac_secret=dest.hmac_secret,
        )
        log.append(
            {
                "kind": "webhook",
                "name": dest.name,
                "url_hash": _hash_url(dest.webhook_url),
                "delivered_at": datetime.datetime.now(datetime.UTC).isoformat(),
                "status_code": 200 if ok else 0,
            }
        )

    with session_factory() as session:
        review = session.get(AgentReview, review_id)
        if review is not None:
            review.delivered_to_json = json.dumps(log)
            session.commit()
    return log
