"""Databricks-compatible SQL Statement Execution API — package facade.

Splits the previous flat ``external_sql_routes.py`` into per-axis
sub-modules behind one combined router so
``from pointlessql.api.external_sql_routes import router`` keeps working:

* ``submit``    — POST /api/2.0/sql/statements (+ parse / rate-limit / persist).
* ``lifecycle`` — poll / result-chunk / cancel.

The Databricks error-wrapper helpers (:class:`DbxApiError`,
:func:`dbx_error_response`, :func:`wrap_dbx`) are re-exported here so the
historical ``from pointlessql.api.external_sql_routes import ...`` import
path keeps resolving.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api._dbx_error_wrapper import (
    DbxApiError,
    dbx_error_response,
    wrap_dbx,
)
from pointlessql.api.external_sql_routes.lifecycle import router as _lifecycle_router
from pointlessql.api.external_sql_routes.submit import router as _submit_router

router = APIRouter(tags=["sql-statements"])
router.include_router(_submit_router)
router.include_router(_lifecycle_router)

__all__ = ["DbxApiError", "dbx_error_response", "router", "wrap_dbx"]
