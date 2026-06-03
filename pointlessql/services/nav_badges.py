"""Primary-rail badge aggregator.

Computes the three counts shown as red unread pills next to the
WATCH-section entries in the primary rail:

* ``runs_pending``  — agent runs awaiting approval in this workspace.
* ``audit_unread``  — user's unread *for-you* inbox count (mentions /
  directed deliveries).  Ambient stream activity is excluded — its
  newness is tracked by the feed seen-cursor, not a read flag — so this
  badge clears when the inbox is read rather than drifting up with
  every followed-entity event.
* ``alerts_firing`` — active alerts in this workspace.

Each query is best-effort: any failure returns ``0`` for that key
so a transient DB hiccup never blanks the entire rail.  Callers
should not rely on accuracy beyond "non-zero means there's something
to look at" — phase 81 can promote this to a cache.
"""

from __future__ import annotations

import logging
from typing import Any, TypedDict

from sqlalchemy import and_, func, or_, select
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)


class NavBadges(TypedDict, total=False):
    """Per-page badge counts threaded to ``components/primary_rail.html``."""

    runs_pending: int
    audit_unread: int
    alerts_firing: int


def compute_nav_badges(
    factory: sessionmaker[Any] | None,
    user_id: int,
    workspace_id: int,
) -> NavBadges:
    """Compute the three rail badges for one rendered page.

    Args:
        factory: Active SQLAlchemy session factory (``None`` short-circuits
            to an empty dict so test fixtures that skip DB init still render
            pages).
        user_id: Authenticated user's id; used for the inbox query.
        workspace_id: Currently-active workspace id; used to scope the
            runs and alerts queries.

    Returns:
        Dict mapping badge name to non-negative integer count.  Keys
        with value ``0`` are still included so the template's guard
        (``if value and value > 0``) keeps badges hidden — i.e. only
        positive counts ever render.
    """
    if factory is None:
        return {}
    out: NavBadges = {
        "runs_pending": 0,
        "audit_unread": 0,
        "alerts_firing": 0,
    }
    try:
        from pointlessql.models import Alert as AlertModel
        from pointlessql.models.agent._runs import (
            STATUS_NEEDS_APPROVAL,
        )
        from pointlessql.models.agent._runs import (
            AgentRun as AgentRunModel,
        )
        from pointlessql.models.notifications import UserNotification
        from pointlessql.services.notifications.categories import ATTENTION_FOR_YOU

        with factory() as session:
            if workspace_id:
                runs_stmt = (
                    select(func.count())
                    .select_from(AgentRunModel)
                    .where(AgentRunModel.status == STATUS_NEEDS_APPROVAL)
                    .where(AgentRunModel.workspace_id == workspace_id)
                )
                out["runs_pending"] = int(session.scalar(runs_stmt) or 0)

                alerts_stmt = (
                    select(func.count())
                    .select_from(AlertModel)
                    .where(AlertModel.is_active.is_(True))
                    .where(AlertModel.workspace_id == workspace_id)
                )
                out["alerts_firing"] = int(session.scalar(alerts_stmt) or 0)

            if user_id:
                inbox_stmt = (
                    select(func.count())
                    .select_from(UserNotification)
                    .where(UserNotification.recipient_user_id == user_id)
                    .where(UserNotification.read_at.is_(None))
                    .where(
                        or_(
                            UserNotification.attention == ATTENTION_FOR_YOU,
                            and_(
                                UserNotification.attention.is_(None),
                                UserNotification.event_type.like("%mention%"),
                            ),
                        )
                    )
                )
                out["audit_unread"] = int(session.scalar(inbox_stmt) or 0)
    except Exception:  # noqa: BLE001 — nav badges are best-effort
        logger.debug("nav_badges: query failed", exc_info=True)
        return {}
    return out
