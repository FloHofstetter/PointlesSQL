"""Notebook workspace HTTP routes — package facade.

Splits the previous 904-LOC ``notebooks_routes.py`` module into
per-axis sub-modules.  The public surface stays
identical: callers continue to import ``router`` from
``pointlessql.api.notebooks_routes`` and the FastAPI app sees one
combined router with every endpoint registered.

Sub-modules:

* :mod:`._shared` — template + UUID lookup helpers
* :mod:`.discovery` — ``GET /api/notebooks/inspect|tree``
* :mod:`.crud` — create / rename / delete
* :mod:`.io` — load / save / cell-history / render-markdown
* :mod:`.jobs` — notebook-job listing + run-once trigger
* :mod:`.pages` — HTML page renders (editor + workspace browser)
* :mod:`.tags` — notebook-level tag CRUD
* :mod:`.templates` — starter-template gallery + create
* :mod:`.cell_lineage` — cell-level write-op badges
* :mod:`.export` — HTML / PDF export pipeline
* :mod:`.revisions` — save-snapshot history + diff
* :mod:`.facts` — pinned-fact promotion of revisions
* :mod:`.cell_authorship` — per-cell attribution
* :mod:`.widgets` — parameter-widget CRUD
* :mod:`.permissions` — per-notebook share permissions
* :mod:`.shares` — public-share + dashboard render
* :mod:`.branch_bindings` — per-notebook Delta-branch binding
* :mod:`.replay` — replay / scenario-mode
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.notebooks_routes.branch_bindings import (
    router as _branch_bindings_router,
)
from pointlessql.api.notebooks_routes.cell_authorship import (
    router as _cell_authorship_router,
)
from pointlessql.api.notebooks_routes.cell_lineage import (
    router as _cell_lineage_router,
)
from pointlessql.api.notebooks_routes.crud import router as _crud_router
from pointlessql.api.notebooks_routes.discovery import (
    router as _discovery_router,
)
from pointlessql.api.notebooks_routes.export import (
    router as _export_router,
)
from pointlessql.api.notebooks_routes.facts import (
    router as _facts_router,
)
from pointlessql.api.notebooks_routes.io import router as _io_router
from pointlessql.api.notebooks_routes.jobs import router as _jobs_router
from pointlessql.api.notebooks_routes.pages import router as _pages_router
from pointlessql.api.notebooks_routes.permissions import (
    router as _permissions_router,
)
from pointlessql.api.notebooks_routes.replay import (
    router as _replay_router,
)
from pointlessql.api.notebooks_routes.revisions import (
    router as _revisions_router,
)
from pointlessql.api.notebooks_routes.shares import (
    router as _shares_router,
)
from pointlessql.api.notebooks_routes.tags import router as _tags_router
from pointlessql.api.notebooks_routes.templates import (
    router as _templates_router,
)
from pointlessql.api.notebooks_routes.widgets import (
    router as _widgets_router,
)

router = APIRouter(tags=["notebooks"])
router.include_router(_discovery_router)
router.include_router(_crud_router)
router.include_router(_io_router)
router.include_router(_jobs_router)
router.include_router(_tags_router)
router.include_router(_templates_router)
router.include_router(_cell_lineage_router)
router.include_router(_export_router)
router.include_router(_revisions_router)
router.include_router(_facts_router)
router.include_router(_cell_authorship_router)
router.include_router(_widgets_router)
router.include_router(_permissions_router)
router.include_router(_shares_router)
router.include_router(_branch_bindings_router)
router.include_router(_replay_router)
router.include_router(_pages_router)


__all__ = ["router"]
