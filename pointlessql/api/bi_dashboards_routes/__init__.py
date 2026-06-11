"""``/api/bi`` route bundle — AI/BI widget dashboards.

Package layout (one concern per module, combined here):

* ``_crud``    — dashboard CRUD + publish/unpublish.
* ``_widgets`` — widget CRUD + gridstack layout bulk-save.
* ``_data``    — widget query execution (viewer-principal on the
  authenticated path, owner-principal on the public-token path).
* ``_shared``  — serializers + ensure/guard helpers.

The HTML pages live in :mod:`pointlessql.api.bi_html_routes` so the
JSON surface stays template-free.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.bi_dashboards_routes._crud import router as _crud_router
from pointlessql.api.bi_dashboards_routes._data import router as _data_router
from pointlessql.api.bi_dashboards_routes._widgets import router as _widgets_router

router = APIRouter(tags=["bi-dashboards"])
router.include_router(_crud_router)
router.include_router(_widgets_router)
router.include_router(_data_router)

__all__ = ["router"]
