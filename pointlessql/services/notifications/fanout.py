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
import json
import logging
from typing import Any, cast

from sqlalchemy import select

from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_follows import DataProductFollow
from pointlessql.models.notifications import UserNotification

logger = logging.getLogger(__name__)


def _opted_in_inbox(prefs_json: str | None, event_type: str) -> bool:
    """Return True when the user's prefs do NOT disable inbox delivery.

    Missing column / missing event_type key / missing inbox key all
    default to True (Phase 76.4 backwards-compat).
    """
    if not prefs_json:
        return True
    try:
        prefs_any: Any = json.loads(prefs_json)
    except (ValueError, TypeError):
        return True
    if not isinstance(prefs_any, dict):
        return True
    prefs = cast(dict[str, Any], prefs_any)
    per_event = prefs.get(event_type)
    if not isinstance(per_event, dict):
        return True
    per_event_typed = cast(dict[str, Any], per_event)
    inbox = per_event_typed.get("inbox")
    return inbox is None or bool(inbox)


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

            # Phase 76.4: filter recipients by per-user inbox opt-out.
            pref_rows = session.execute(
                select(User.id, User.notification_prefs_json).where(
                    User.id.in_(recipients)
                )
            ).all()
            opted_in: set[int] = {
                int(uid)
                for uid, prefs in pref_rows
                if _opted_in_inbox(prefs, event_type)
            }
            if not opted_in:
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
                    for rid in opted_in
                ]
            )
            session.commit()
            # Phase 76.6: push to live SSE listeners.  Best-effort —
            # we import inside the try/except so a circular import
            # is impossible and a missing module never breaks the
            # originating write.
            try:
                from pointlessql.api.notifications_stream import (
                    publish_notification,
                )

                payload = {
                    "event_type": event_type,
                    "source_data_product_id": data_product_id,
                    "source_url": source_url,
                    "summary_md": summary_md,
                    "actor_user_id": actor_user_id,
                    "created_at": now.isoformat(),
                }
                for rid in opted_in:
                    publish_notification(rid, payload)
            except Exception:  # noqa: BLE001 — SSE delivery is best-effort
                logger.exception("SSE fan-out failed for event %s", event_type)
            return len(opted_in)
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
