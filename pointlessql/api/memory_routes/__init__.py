"""Memory JSON API package.

Three sub-modules: recall (filterable read), branch (create), and
replay (re-invoke).  Each one mounts its endpoints under
``/api/memory/{agent_id}/...`` and shares the FastAPI router
exported from this package's ``router`` attribute.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.memory_routes._branch import router as _branch_router
from pointlessql.api.memory_routes._recall import router as _recall_router
from pointlessql.api.memory_routes._replay import router as _replay_router

router = APIRouter(prefix="/api/memory", tags=["memory"])
router.include_router(_recall_router)
router.include_router(_branch_router)
router.include_router(_replay_router)

__all__ = ["router"]
