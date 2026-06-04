"""Catalog tree API routes — package facade.

Splits the previous flat ``catalog_routes.py`` into two per-axis
sub-modules behind one combined router so existing imports
(``from pointlessql.api.catalog_routes import router`` and
``... import humanize_preview_error``) keep working:

* ``browse``  — tree / catalogs / schemas / tables / recents listing.
* ``preview`` — table row-preview + stats (mask-at-source, no-store).
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.catalog_routes.browse import router as _browse_router
from pointlessql.api.catalog_routes.preview import (
    humanize_preview_error,
)
from pointlessql.api.catalog_routes.preview import (
    router as _preview_router,
)

router = APIRouter(tags=["catalog"])
router.include_router(_browse_router)
router.include_router(_preview_router)

__all__ = ["humanize_preview_error", "router"]
