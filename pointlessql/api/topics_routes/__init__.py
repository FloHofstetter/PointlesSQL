"""``/api/topics/...`` and ``/api/data-products/.../topics`` (Phase 76.3).

Sub-modules:

* ``index`` — workspace-wide topic list + create.
* ``detail`` — per-topic detail + DP assignment toggling.
* ``follows`` — user-topic follow link.

Public surface is one aggregated router.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.topics_routes.detail import router as _detail_router
from pointlessql.api.topics_routes.follows import router as _follows_router
from pointlessql.api.topics_routes.index import router as _index_router

router = APIRouter(tags=["topics"])
router.include_router(_index_router)
router.include_router(_detail_router)
router.include_router(_follows_router)


__all__ = ["router"]
