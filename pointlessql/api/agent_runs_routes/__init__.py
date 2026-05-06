"""Agent-run registry endpoints — package facade.

Splits the previous 1458-LOC ``agent_runs_routes.py`` monolith
into per-axis modules: ingestion, listing, lifecycle, summary,
tools, audit.  Public surface (``router``, ``serialize_agent_run``)
and the two helpers that :mod:`pointlessql.api.runs_routes.diff`
lazy-imports under their underscore-prefixed legacy names
(``_summarize_run``, ``_load_run_summary_bundle``) are re-exported
here so existing import paths keep working.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.agent_runs_routes._serializers import serialize_agent_run
from pointlessql.api.agent_runs_routes._summary_helpers import (
    load_run_summary_bundle as _load_run_summary_bundle,
)
from pointlessql.api.agent_runs_routes._summary_helpers import (
    summarize_run as _summarize_run,
)
from pointlessql.api.agent_runs_routes.audit import router as _audit_router
from pointlessql.api.agent_runs_routes.ingestion import router as _ingestion_router
from pointlessql.api.agent_runs_routes.lifecycle import router as _lifecycle_router
from pointlessql.api.agent_runs_routes.listing import router as _listing_router
from pointlessql.api.agent_runs_routes.rewrite_attempts import (
    router as _rewrite_attempts_router,
)
from pointlessql.api.agent_runs_routes.summary import router as _summary_router
from pointlessql.api.agent_runs_routes.tools import router as _tools_router

router = APIRouter(tags=["agent-runs"])
router.include_router(_ingestion_router)
router.include_router(_listing_router)
router.include_router(_lifecycle_router)
router.include_router(_summary_router)
router.include_router(_tools_router)
router.include_router(_audit_router)
router.include_router(_rewrite_attempts_router)

__all__ = [
    "_load_run_summary_bundle",
    "_summarize_run",
    "router",
    "serialize_agent_run",
]
