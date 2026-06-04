"""Volume browser API + pages — package facade.

Splits the previous flat ``volumes_routes.py`` into per-axis
sub-modules behind one combined router so
``from pointlessql.api.volumes_routes import router`` keeps working:

* ``files``   — file browse / upload / delete JSON endpoints.
* ``convert`` — convert a volume file to a managed Delta table.
* ``pages``   — server-rendered volume browser HTML.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.volumes_routes.convert import DELTA_PRIMITIVE_TO_UC, delta_field_to_uc
from pointlessql.api.volumes_routes.convert import router as _convert_router
from pointlessql.api.volumes_routes.files import router as _files_router
from pointlessql.api.volumes_routes.pages import router as _pages_router

router = APIRouter(tags=["volumes"])
router.include_router(_files_router)
router.include_router(_convert_router)
router.include_router(_pages_router)

__all__ = ["DELTA_PRIMITIVE_TO_UC", "delta_field_to_uc", "router"]
