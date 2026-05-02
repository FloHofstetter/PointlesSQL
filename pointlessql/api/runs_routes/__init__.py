"""Agent-run supervision pages — package facade.

Splits the previous 1641-LOC ``runs_routes.py`` monolith into
per-axis modules: list, detail, lineage, rollback, diff.  Public
surface (the FastAPI router and the cross-module data loaders) is
re-exported here so that existing imports like
``from pointlessql.api.runs_routes import router`` and
``from pointlessql.api.runs_routes import load_lineage_summary_for_run``
continue to work unchanged.

``load_operations_for_run`` is package-internal but is also imported
by :mod:`tests.test_runs_op_filter`, so it is re-exported too.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.runs_routes._loaders import (
    load_lineage_summary_for_run,
    load_operations_for_run,
    load_rejects_for_run,
    load_unattributed_for_run,
)
from pointlessql.api.runs_routes.detail_view import router as _detail_router
from pointlessql.api.runs_routes.diff import router as _diff_router
from pointlessql.api.runs_routes.lineage import router as _lineage_router
from pointlessql.api.runs_routes.list_view import router as _list_router
from pointlessql.api.runs_routes.rollback import router as _rollback_router

router = APIRouter(tags=["runs"])
router.include_router(_list_router)
router.include_router(_detail_router)
router.include_router(_lineage_router)
router.include_router(_rollback_router)
router.include_router(_diff_router)

__all__ = [
    "load_lineage_summary_for_run",
    "load_operations_for_run",
    "load_rejects_for_run",
    "load_unattributed_for_run",
    "router",
]
