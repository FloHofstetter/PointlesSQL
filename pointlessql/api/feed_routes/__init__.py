"""``/api/feed`` + notification + mute endpoints — package facade.

B1 split the original 1021-LOC ``feed_routes.py`` into
per-axis sub-modules.  External imports
(``from pointlessql.api.feed_routes import router``) keep working
because the facade re-aggregates the sub-routers and re-exports
``router`` with the same ``tags=["feed"]`` annotation.

Sub-modules:

* :mod:`.feed` — the read-only ``/api/feed`` + trending + people
  endpoints.
* :mod:`.notifications` — read-state toggles for
  ``user_notifications`` rows.
* :mod:`.muting` — mute / mute-author / snooze / unmute endpoints
  plus the shared upsert helper.
* :mod:`._serializers` — row-builders, mute-key resolver, FQN
  cache.  Internal, but kept here (not in services) because the
  shape is route-specific.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.feed_routes.feed import router as _feed_router
from pointlessql.api.feed_routes.muting import router as _muting_router
from pointlessql.api.feed_routes.notifications import router as _notifications_router

router = APIRouter(tags=["feed"])
router.include_router(_feed_router)
router.include_router(_notifications_router)
router.include_router(_muting_router)

__all__ = ["router"]
