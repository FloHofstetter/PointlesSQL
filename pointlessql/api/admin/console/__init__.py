"""Admin landing page + audit-log viewer + export — split per route surface.

The pre-Phase-110 layout collapsed every admin-HTML route into one
~830 LOC ``console.py`` module.  Phase 110.3 split it per page so each
surface owns its own file with the queries it needs:

* :mod:`._landing`             — ``GET /admin`` card-grid index.
* :mod:`._review_destinations` — ``GET /admin/review-destinations``.
* :mod:`._audit_sinks`         — ``GET /admin/audit-sinks``.
* :mod:`._api_keys`            — ``GET /admin/api-keys``.
* :mod:`._system_info`         — ``GET /admin/system-info``.
* :mod:`._sources`             — ``GET /admin/sources``.
* :mod:`._audit`               — ``/admin/audit`` HTML viewer + JSON/CSV
  export + ``.tar.gz`` tamper-evidence bundle.

``router`` mounts each sub-router under the shared ``admin`` tag.
The constants (``ADMIN_AUDIT_LIMIT``, ``ADMIN_AUDIT_SINCE_WINDOWS``,
``AUDIT_EXPORT_LIMIT``) live in :mod:`._constants`; they are re-exported
here so test modules that imported them from ``console`` need no edits.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.admin.console._api_keys import router as _api_keys_router
from pointlessql.api.admin.console._audit import router as _audit_router
from pointlessql.api.admin.console._audit_sinks import router as _audit_sinks_router
from pointlessql.api.admin.console._constants import (
    ADMIN_AUDIT_LIMIT,
    ADMIN_AUDIT_SINCE_WINDOWS,
    AUDIT_EXPORT_LIMIT,
)
from pointlessql.api.admin.console._landing import router as _landing_router
from pointlessql.api.admin.console._review_destinations import (
    router as _review_destinations_router,
)
from pointlessql.api.admin.console._sources import router as _sources_router
from pointlessql.api.admin.console._system_info import router as _system_info_router

router = APIRouter()
router.include_router(_landing_router)
router.include_router(_review_destinations_router)
router.include_router(_audit_sinks_router)
router.include_router(_api_keys_router)
router.include_router(_system_info_router)
router.include_router(_sources_router)
router.include_router(_audit_router)

__all__ = [
    "ADMIN_AUDIT_LIMIT",
    "ADMIN_AUDIT_SINCE_WINDOWS",
    "AUDIT_EXPORT_LIMIT",
    "router",
]
