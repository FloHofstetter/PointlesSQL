"""Jobs + scheduler routes — package facade.

B3 split the 927-LOC ``jobs_routes.py`` monolith.  Public
imports continue to resolve through this facade:

* ``router`` — aggregates the sub-routers (crud, runs,
  papermill, canvas, pages).
* ``JOB_REGISTRY`` — eagerly built scheduler kind registry.
* ``serialize_job`` / ``serialize_run`` / ``latest_run_per_job`` —
  used by :mod:`pointlessql.api.dashboards_routes` and
  :mod:`pointlessql.api.notebooks_routes.jobs`.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.jobs_routes._access import JOB_REGISTRY
from pointlessql.api.jobs_routes._serializers import (
    latest_run_per_job,
    serialize_job,
    serialize_run,
)
from pointlessql.api.jobs_routes.canvas import router as _canvas_router
from pointlessql.api.jobs_routes.crud import router as _crud_router
from pointlessql.api.jobs_routes.pages import router as _pages_router
from pointlessql.api.jobs_routes.papermill import router as _papermill_router
from pointlessql.api.jobs_routes.runs import router as _runs_router

router = APIRouter(tags=["jobs"])
router.include_router(_crud_router)
router.include_router(_runs_router)
router.include_router(_papermill_router)
router.include_router(_canvas_router)
router.include_router(_pages_router)

__all__ = [
    "JOB_REGISTRY",
    "latest_run_per_job",
    "router",
    "serialize_job",
    "serialize_run",
]
