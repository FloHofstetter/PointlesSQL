"""Governance routes — package facade.

Phase 86 B6 split the 521-LOC ``governance_routes.py`` into six
per-concern sub-modules.  External imports of ``router`` keep
working through the facade.

Sub-modules:

* :mod:`.profile` — table profiling + stats GET/DELETE.
* :mod:`.catalog` — catalog/schema mutations + sync.
* :mod:`.tags` — tag GET/PATCH on any securable.
* :mod:`.permissions` — privilege + effective-permission endpoints.
* :mod:`.lineage` — read-only lineage.
* :mod:`._helpers` — shared name-split + access-check helpers.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.governance_routes.catalog import router as _catalog_router
from pointlessql.api.governance_routes.lineage import router as _lineage_router
from pointlessql.api.governance_routes.permissions import (
    router as _permissions_router,
)
from pointlessql.api.governance_routes.profile import router as _profile_router
from pointlessql.api.governance_routes.tags import router as _tags_router

router = APIRouter(tags=["governance"])
router.include_router(_profile_router)
router.include_router(_catalog_router)
router.include_router(_tags_router)
router.include_router(_permissions_router)
router.include_router(_lineage_router)

__all__ = ["router"]
