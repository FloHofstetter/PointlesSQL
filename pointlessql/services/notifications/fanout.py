"""Fan-out helper data-product social events.

Given one event (someone commented / reviewed / followed a DP),
resolve the recipient set and bulk-insert one
:class:`UserNotification` row per recipient.

Recipients are the union of:

* every follower of the entity (:class:`SocialFollow` joined
  through :class:`SocialTarget` to find the DP back-pointer),
  and
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
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._social_follow import SocialFollow
from pointlessql.models.social._social_target import SocialTarget

logger = logging.getLogger(__name__)


def _opted_in_inbox(prefs_json: str | None, event_type: str) -> bool:
    """Return True when the user's prefs do NOT disable inbox delivery.

    Missing column / missing event_type key / missing inbox key all
    default to True.
    """
    if not prefs_json:
        return True
    try:
        prefs_any: Any = json.loads(prefs_json)
    except ValueError, TypeError:
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


def fanout_event(
    session_factory: Any,
    *,
    event_type: str,
    entity_kind: str,
    entity_ref: str,
    workspace_id: int,
    actor_user_id: int | None,
    source_url: str,
    summary_md: str,
    data_product_id: int | None = None,
    extra_recipients: list[int] | None = None,
) -> int:
    """Fan a social event out to one row per recipient.

    This polymorphic shape supersedes the earlier DP-only fan-out
    helper.  Followers come from :class:`SocialFollow`
    joined through :class:`SocialTarget` so the lookup works
    uniformly for every kind that registers a polymorphic
    anchor.  ``data_product_id`` stays a legacy back-pointer for
    callers that still want to stamp the column.

    Args:
        session_factory: SQLAlchemy session factory.
        event_type: Governance event type (one of the Phase-71.4
            / Phase-20 strings; new kinds may introduce new
            event_type strings without a schema change).
        entity_kind: Discriminator from
            :data:`pointlessql.models.social.ENTITY_KINDS`.
        entity_ref: Reference string within *entity_kind*.
        workspace_id: Tenant scope.
        actor_user_id: Optional id of the user who triggered the
            event.  Removed from the recipient set so people are
            not notified about their own actions.
        source_url: Click-through URL persisted on each row.
        summary_md: One-line markdown summary for the inbox.
        data_product_id: Optional legacy back-pointer — populated
            iff ``entity_kind='dp'``.  Stamped on the
            ``UserNotification.source_data_product_id`` column so
            existing client code keyed on that FK keeps working.
        extra_recipients: Optional list of additional user ids
            (e.g. resolved @mentions).  De-duplicated against the
            follower set.

    Returns:
        Count of rows inserted (0 when no eligible recipients).
    """
    try:
        with session_factory() as session:
            follower_ids: set[int] = set()
            if entity_kind == "dp" and data_product_id is not None:
                # follows live in social_follows
                # keyed by social_target_id; join through
                # social_targets to find the DP's anchor row.
                follower_ids = {
                    int(uid)
                    for (uid,) in session.execute(
                        select(SocialFollow.user_id)
                        .join(
                            SocialTarget,
                            SocialTarget.id == SocialFollow.social_target_id,
                        )
                        .where(
                            SocialFollow.workspace_id == workspace_id,
                            SocialTarget.entity_kind == "dp",
                            SocialTarget.data_product_id == data_product_id,
                        )
                    ).all()
                }
            recipients = follower_ids | set(extra_recipients or [])
            if actor_user_id is not None:
                recipients.discard(int(actor_user_id))
            if not recipients:
                return 0

            # filter recipients by per-user inbox opt-out.
            pref_rows = session.execute(
                select(User.id, User.notification_prefs_json).where(User.id.in_(recipients))
            ).all()
            opted_in: set[int] = {
                int(uid) for uid, prefs in pref_rows if _opted_in_inbox(prefs, event_type)
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
                        source_entity_kind=entity_kind,
                        source_entity_ref=entity_ref,
                        source_url=source_url,
                        summary_md=summary_md,
                        actor_user_id=actor_user_id,
                        created_at=now,
                    )
                    for rid in opted_in
                ]
            )
            session.commit()
            # push to live SSE listeners.  Best-effort —
            # we import inside the try/except so a circular import
            # is impossible and a missing module never breaks the
            # originating write.
            try:
                from pointlessql.api.notifications_stream import (
                    publish_notification,
                )

                payload = {
                    "event_type": event_type,
                    "source_entity_kind": entity_kind,
                    "source_entity_ref": entity_ref,
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
            "user_notifications fan-out failed for event_type=%s kind=%s ref=%s",
            event_type,
            entity_kind,
            entity_ref,
        )
        return 0
