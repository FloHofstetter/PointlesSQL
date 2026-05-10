"""Lineage route surface, split per direction.

Two flat sibling modules (lineage_routes 757 + lineage_inbound_routes
242 = 999 LOC) consolidated into one ``pointlessql.api.lineage``
package whose ``__init__.py`` composes the combined router.

Layout:

* ``views``   — ``/lineage/*`` and ``/api/lineage/*`` read endpoints
                + UI pages (the cockpit).
* ``inbound`` — ``POST /api/lineage/openlineage`` ingestion endpoint
                that accepts external producers' OpenLineage events.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.lineage.inbound import router as _inbound_router
from pointlessql.api.lineage.views import router as _views_router

router = APIRouter()
router.include_router(_views_router)
router.include_router(_inbound_router)

__all__ = ["router"]
