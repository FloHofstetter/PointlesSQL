"""``/admin/*`` route surface, split per concern.

This package consolidates the eight flat ``admin_*_routes.py``
sibling modules that used to live at ``pointlessql/api/`` root.
The combined router is mounted by ``api.main`` exactly once via
``router = APIRouter(); router.include_router(...)`` in this
``__init__.py`` — callers no longer juggle eight individual router
references.

Layout (all per-concern, no internal coupling beyond shared
dependency injection):

* ``console``           — admin landing + system info.
* ``workspaces``        — workspace CRUD + group mappings.
* ``workspace_pins``    — pinned-workspace bookmark management.
* ``repos``             — workspace-repo registration + sync.
* ``cdf_tail``          — Change Data Feed tail viewer.
* ``expected_producers`` — UC-mutation expected-producer registry.
* ``external_writes``   — external-write audit configuration.
* ``api_keys``          — API key issuance + revocation.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.admin.api_keys import router as _api_keys_router
from pointlessql.api.admin.cdf_tail import router as _cdf_tail_router
from pointlessql.api.admin.console import router as _console_router
from pointlessql.api.admin.expected_producers import (
    router as _expected_producers_router,
)
from pointlessql.api.admin.external_writes import router as _external_writes_router
from pointlessql.api.admin.repos import router as _repos_router
from pointlessql.api.admin.workspace_pins import router as _workspace_pins_router
from pointlessql.api.admin.workspaces import router as _workspaces_router

router = APIRouter()
router.include_router(_console_router)
router.include_router(_workspaces_router)
router.include_router(_workspace_pins_router)
router.include_router(_repos_router)
router.include_router(_cdf_tail_router)
router.include_router(_expected_producers_router)
router.include_router(_external_writes_router)
router.include_router(_api_keys_router)

__all__ = ["router"]
