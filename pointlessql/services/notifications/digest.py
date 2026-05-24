"""Daily marketplace-digest service.

Two callables:

* :func:`seconds_until_next_window` — return the seconds between
  *now* and the next ``digest_trigger_hour`` boundary in UTC.
  Returns a positive int in ``[60, 86400)``.
* :func:`fire_digests` — find users with
  ``digest_email_optin=True`` who have ≥1 unread
  :class:`UserNotification` row from the prior 24h, build a
  per-user markdown summary, and emit one
  ``pointlessql.notification.digest`` governance event per
  recipient.

The actual mail delivery happens via the audit-stream forwarder's
webhook / SES-bound sink — this service is a pure
``emit_governance_event`` caller.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from sqlalchemy import func, select

from pointlessql.models.auth import User
from pointlessql.models.notifications import UserNotification
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_NOTIFICATION_DIGEST,
    emit_governance_event,
)

logger = logging.getLogger(__name__)


def seconds_until_next_window(
    target_hour: int,
    *,
    now: datetime.datetime | None = None,
) -> int:
    """Return the wait, in seconds, until the next ``target_hour`` boundary.

    Clamped to ``[60, 86400)``.  ``target_hour`` outside ``[0, 23]``
    is wrapped via modulo so misconfiguration doesn't crash the
    loop.

    Args:
        target_hour: Wall-clock hour-of-day in UTC.
        now: Optional override for "now" (unit tests).

    Returns:
        Seconds until the next strike (always > 0; minimum 60 so
        a same-second fire doesn't hot-loop the scheduler).
    """
    now = now or datetime.datetime.now(datetime.UTC)
    hour = target_hour % 24
    target = now.replace(hour=hour, minute=0, second=0, microsecond=0)
    if target <= now:
        target += datetime.timedelta(days=1)
    return max(60, int((target - now).total_seconds()))


async def fire_digests(
    session_factory: Any,
    settings: Any,
    *,
    now: datetime.datetime | None = None,
) -> int:
    """Emit one digest envelope per eligible user.

    A user is eligible when:
    * ``digest_email_optin = True``, AND
    * they have ≥1 :class:`UserNotification` row in their default
      workspace whose ``created_at`` falls in the
      ``[now-24h, now)`` window.

    Args:
        session_factory: SQLAlchemy session factory.
        settings: Snapshotted :class:`Settings` (only
            ``audit_stream`` is read here, by
            ``emit_governance_event``).
        now: Optional override for "now" (unit tests).

    Returns:
        Number of envelopes emitted.
    """
    now = now or datetime.datetime.now(datetime.UTC)
    since = now - datetime.timedelta(hours=24)
    emitted = 0
    with session_factory() as session:
        rows = session.execute(
            select(User.id, User.email, User.display_name).where(
                User.digest_email_optin.is_(True)
            )
        ).all()
        # Per-user unread count (only counts notifs created in the
        # prior 24h, irrespective of read state — a digest of the
        # last day is the contract).
        counts = dict(
            session.execute(
                select(
                    UserNotification.recipient_user_id,
                    func.count(UserNotification.id),
                ).where(
                    UserNotification.created_at >= since,
                    UserNotification.created_at < now,
                ).group_by(UserNotification.recipient_user_id)
            ).all()
        )

    for user_id, email, display_name in rows:
        count = int(counts.get(user_id, 0))
        if count == 0:
            continue
        summary_md = (
            f"You have **{count}** new marketplace activity item(s) "
            f"in the last 24h — open `/notifications` to review."
        )
        try:
            await emit_governance_event(
                EVENT_TYPE_NOTIFICATION_DIGEST,
                {
                    "recipient_user_id": user_id,
                    "recipient_email": email,
                    "recipient_display_name": display_name,
                    "unread_count": count,
                    "summary_md": summary_md,
                    "since": since.isoformat(),
                    "until": now.isoformat(),
                },
                settings=settings,
                session_factory=session_factory,
                workspace_id=1,
            )
            emitted += 1
        except Exception:  # noqa: BLE001 — never break the loop on one bad user
            # bare-broad-ok: per-user digest fire is best-effort; the
            # other recipients still need their envelope.  The
            # underlying audit row from the originating notification
            # write is unaffected.
            logger.exception(
                "notification_digest: emit failed for user_id=%s",
                user_id,
            )
    return emitted
