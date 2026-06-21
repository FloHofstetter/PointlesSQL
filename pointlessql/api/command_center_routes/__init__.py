"""Agent command center — a parallel-run cockpit over agent-run metadata.

A supervision surface that reframes the flat ``/runs`` list for the case
where several agents work at once: a live-thread board of the in-flight
runs and candidate sets that group competing attempts over the same
notebook so a reviewer can compare them and keep the best.  It reuses the
``runs_routes`` loaders and the existing approve/deny endpoints, so it
adds a view, not a second source of truth.

The HTML page (:mod:`._page`) and its JSON siblings (:mod:`._api`) share
the cockpit builders in :mod:`._shared`, which are re-exported here so
tests can exercise them directly.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.command_center_routes._api import router as _api_router
from pointlessql.api.command_center_routes._page import router as _page_router
from pointlessql.api.command_center_routes._shared import build_command_center, compare_runs

router = APIRouter(tags=["command-center"])
router.include_router(_page_router)
router.include_router(_api_router)

__all__ = ["build_command_center", "compare_runs", "router"]
