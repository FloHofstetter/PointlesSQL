"""SQL editor routes — execute, batch, cancel, download, explain, page.

Six FastAPI surfaces glued into a single router exported as
``pointlessql.api.sql.editor.router``:

* ``POST /api/sql/execute`` — single-statement parse → enforce →
  dispatch → audit pipeline.
* ``POST /api/sql/execute_batch`` — multi-statement runner with
  optional atomic rollback.
* ``POST /api/sql/execute/{query_id}/cancel`` — interrupt a running
  query.
* ``GET  /api/sql/execute/{history_id}/download`` — stream a
  historical query result as CSV / Parquet.
* ``GET  /api/sql/explain`` — DuckDB EXPLAIN with cost-gate verdict.
* ``GET  /sql`` — the Jinja2 page.

The four helper functions consumed by the dispatcher
(``run_sql_sync``) and by tests (``short_sql_hash``, ``live_queries``,
``run_sql_export_sync``) re-export from this facade so external
imports stay unchanged.

Phase 88.2 split this module from a 1127-LOC monolith into the
sub-package below.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.sql.editor._batch import router as _batch_router
from pointlessql.api.sql.editor._cancel import router as _cancel_router
from pointlessql.api.sql.editor._download import router as _download_router
from pointlessql.api.sql.editor._execute import router as _execute_router
from pointlessql.api.sql.editor._explain import router as _explain_router
from pointlessql.api.sql.editor._helpers import (
    live_queries,
    run_sql_export_sync,
    run_sql_sync,
    short_sql_hash,
)
from pointlessql.api.sql.editor._page import router as _page_router

router = APIRouter()
router.include_router(_execute_router)
router.include_router(_batch_router)
router.include_router(_cancel_router)
router.include_router(_download_router)
router.include_router(_explain_router)
router.include_router(_page_router)

__all__ = [
    "live_queries",
    "router",
    "run_sql_export_sync",
    "run_sql_sync",
    "short_sql_hash",
]
