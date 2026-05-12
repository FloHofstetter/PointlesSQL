"""Fan-out helper for Phase 71.4 data-product social events.

Given one event (someone commented / reviewed / followed a DP),
resolve the recipient set and bulk-insert one
:class:`UserNotification` row per recipient.

Recipients are the union of:

* every follower of the data product
  (:class:`DataProductFollow`), and
* any explicitly named additional recipients (``extra_recipients``)
  — used to deliver @mention pings even when the mentioned user
  doesn't follow the product.

The actor is removed from the resulting set so people aren't
notified about their own actions.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from sqlalchemy import select

from pointlessql.models.catalog._data_product_follows import DataProductFollow
from pointlessql.models.notifications import UserNotification

logger = logging.getLogger(__name__)


def fanout_dataproduct_event(
    session_factory: Any,
    *,
    event_type: str,
    data_product_id: int,
    workspace_id: int,
    actor_user_id: int | None,
    source_url: str,
    summary_md: str,
    extra_recipients: list[int] | None = None,
) -> int:
    """Fan a data-product event out to one row per recipient.

    Args:
        session_factory: SQLAlchemy session factory from app state.
        event_type: One of the Phase-71.4 governance event types.
        data_product_id: PK of the data product the event is about.
        workspace_id: Workspace the event belongs to.
        actor_user_id: Optional user that triggered the event.
            Removed from the resolved recipient set.
        source_url: Click-through URL persisted on each
            notification row.
        summary_md: One-line markdown summary for the inbox row.
        extra_recipients: Optional list of additional user ids
            (e.g. resolved @mentions).  De-duplicated against the
            follower set.

    Returns:
        Count of rows inserted (0 when no eligible recipients).
    """
    try:
        with session_factory() as session:
            follower_ids = {
                int(uid)
                for (uid,) in session.execute(
                    select(DataProductFollow.user_id).where(
                        DataProductFollow.workspace_id == workspace_id,
                        DataProductFollow.data_product_id == data_product_id,
                    )
                ).all()
            }
            recipients = follower_ids | set(extra_recipients or [])
            if actor_user_id is not None:
                recipients.discard(int(actor_user_id))
            if not recipients:
                return 0

            now = datetime.datetime.now(datetime.UTC)
            session.add_all(
                [
                    UserNotification(
                        workspace_id=workspace_id,
                        recipient_user_id=rid,
                        event_type=event_type,
                        source_data_product_id=data_product_id,
                        source_url=source_url,
                        summary_md=summary_md,
                        actor_user_id=actor_user_id,
                        created_at=now,
                    )
                    for rid in recipients
                ]
            )
            session.commit()
            return len(recipients)
    except Exception:  # noqa: BLE001 — fan-out must never break the originating write
        # bare-broad-ok: notification fan-out is best-effort.  The
        # underlying audit row + governance event already persisted;
        # losing an inbox row is annoying but never load-bearing.
        logger.exception(
            "user_notifications fan-out failed for event_type=%s dp_id=%s",
            event_type,
            data_product_id,
        )
        return 0
