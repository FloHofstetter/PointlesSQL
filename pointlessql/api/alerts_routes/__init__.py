"""Alerts + per-user feed-token + pull-feed routes — package facade.

B5 split the 626-LOC ``alerts_routes.py`` into per-axis
sub-modules:

* :mod:`.crud` — ``/api/alerts`` list / create / get / patch / delete.
* :mod:`.destinations` — ``POST/DELETE /api/alerts/{slug}/destinations``.
* :mod:`.feed_tokens` — ``GET/POST /api/me/feed-token``.
* :mod:`.feeds` — unauthenticated ``/alerts/feed.atom`` + ``.json``.
* :mod:`.pages` — HTML pages.
* :mod:`._helpers` — ``base_url``, ``rotate_or_fetch_feed_token``,
  ``user_for_feed_token``.

Public surface (``router`` + the three helpers) is re-exported here
so prior imports keep working.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.alerts_routes._helpers import (
    base_url,
    rotate_or_fetch_feed_token,
    user_for_feed_token,
)
from pointlessql.api.alerts_routes.crud import router as _crud_router
from pointlessql.api.alerts_routes.destinations import (
    router as _destinations_router,
)
from pointlessql.api.alerts_routes.feed_tokens import (
    router as _feed_tokens_router,
)
from pointlessql.api.alerts_routes.feeds import router as _feeds_router
from pointlessql.api.alerts_routes.pages import router as _pages_router

router = APIRouter(tags=["alerts"])
router.include_router(_crud_router)
router.include_router(_destinations_router)
router.include_router(_feed_tokens_router)
router.include_router(_feeds_router)
router.include_router(_pages_router)

__all__ = [
    "base_url",
    "rotate_or_fetch_feed_token",
    "router",
    "user_for_feed_token",
]
