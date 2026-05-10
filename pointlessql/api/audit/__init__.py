"""``/audit/*`` and ``/api/audit/*`` route surface, split per axis.

This package consolidates the five flat ``audit_*_routes.py``
sibling modules that used to live at ``pointlessql/api/`` root.
The combined router is mounted by ``api.main`` exactly once via
``router = APIRouter(); router.include_router(...)`` in this
``__init__.py`` — callers no longer juggle five individual router
references.

Layout:

* ``_legacy``  — the pre-split monolith (1262 LOC, every legacy
  ``/api/audit/...`` endpoint).  Will be split in a follow-up
  sprint per the runs_routes/ template.  Private until that lands.
* ``inbox``    — the anomaly-inbox cockpit endpoints.
* ``sinks``    — admin CRUD for audit-stream destinations.
* ``search``   — the FTS-backed full-text audit-event search.
* ``by_table`` — per-table audit-event reverse index.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.audit._legacy import router as _legacy_router
from pointlessql.api.audit.by_table import router as _by_table_router
from pointlessql.api.audit.inbox import router as _inbox_router
from pointlessql.api.audit.search import router as _search_router
from pointlessql.api.audit.sinks import router as _sinks_router

router = APIRouter()
router.include_router(_legacy_router)
router.include_router(_inbox_router)
router.include_router(_sinks_router)
router.include_router(_search_router)
router.include_router(_by_table_router)

__all__ = ["router"]
