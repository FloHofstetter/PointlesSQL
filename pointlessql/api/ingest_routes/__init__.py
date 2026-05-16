"""Phase 82 — ingest API package facade.

Bundles the source CRUD, probe, table-listing, mapping, schedule, and
pull endpoints under one ``ingest_routes.router`` so
``_bootstrap/_routers.py`` mounts the whole surface with a single
``include_router`` call.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.ingest_routes._serializers import (
    redact_secrets,
    serialize_source,
)
from pointlessql.api.ingest_routes.mappings import router as _mappings_router
from pointlessql.api.ingest_routes.probe import router as _probe_router
from pointlessql.api.ingest_routes.pulls import router as _pulls_router
from pointlessql.api.ingest_routes.schedule import router as _schedule_router
from pointlessql.api.ingest_routes.sources import router as _sources_router
from pointlessql.api.ingest_routes.tables import router as _tables_router

router = APIRouter(tags=["ingest"])
router.include_router(_sources_router)
router.include_router(_probe_router)
router.include_router(_tables_router)
router.include_router(_mappings_router)
router.include_router(_pulls_router)
router.include_router(_schedule_router)

__all__ = ["redact_secrets", "router", "serialize_source"]
