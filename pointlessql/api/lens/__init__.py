"""HTTP routes for the Lens read-only Q&A surface (Phase 65).

Sub-routers (mounted in :mod:`pointlessql.api.main`):

* ``provenance``    — ``/api/lens/provenance`` GET (Sprint 65.1).
* ``sessions``      — ``/api/lens/sessions`` CRUD (Sprint 65.5).
* ``messages``      — ``/api/lens/sessions/{id}/messages`` SSE
                       (Sprint 65.5).
* ``pinned``        — ``/api/lens/pinned`` CRUD (Sprint 65.6).

Every sub-router gates on :func:`require_analyst` for read access;
mutations beyond pin/session-CRUD are not exposed (Lens is read-only
by charter).
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.lens.provenance import router as _provenance_router

router = APIRouter(prefix="/api/lens", tags=["lens"])
router.include_router(_provenance_router)

__all__ = ["router"]
