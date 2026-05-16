"""Home dashboard + global search — package facade.

Phase 86 B2 split the 998-LOC ``home_routes.py`` into:

* :mod:`.summary` — :func:`build_home_summary` aggregator plus the
  two endpoints that surface it (``GET /`` HTML, ``GET /api/home/summary``
  JSON).
* :mod:`.search` — ``GET /api/search`` Cmd+K command-palette aggregator.
* :mod:`._helpers` — :func:`score_match` + :func:`epoch_seconds`,
  used only by ``search.py`` today but exported here so other route
  modules can reuse them (the catalog HTML routes will pick them
  up next).

Public surface re-exports preserve every prior import path:
``from pointlessql.api.home_routes import router`` /
``... import score_match`` / ``... import build_home_summary``.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.home_routes._helpers import epoch_seconds, score_match
from pointlessql.api.home_routes.search import router as _search_router
from pointlessql.api.home_routes.summary import (
    build_home_summary,
)
from pointlessql.api.home_routes.summary import (
    router as _summary_router,
)

router = APIRouter(tags=["home"])
router.include_router(_summary_router)
router.include_router(_search_router)

__all__ = [
    "build_home_summary",
    "epoch_seconds",
    "router",
    "score_match",
]
