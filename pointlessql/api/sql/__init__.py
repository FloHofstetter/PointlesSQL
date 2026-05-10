"""SQL execution + write + saved-queries route surface, split per concern.

This package consolidates the four eng-coupled SQL route modules
that used to live as flat siblings at ``pointlessql/api/`` root
(sql_routes 1126 + sql_dispatcher 1009 + pql_write_routes 731 +
queries_routes 547 = 3413 LOC).  ``api/main.py`` now mounts one
combined router from this package instead of four individual ones.

Layout:

* ``editor``        — ``/sql/*`` and ``/api/sql/*`` user-facing
                       editor + execution endpoints.
* ``write``         — ``/api/pql/*`` write endpoints (the bridge
                       Hermes-plugin agents call).
* ``saved_queries`` — ``/queries/*`` saved-query CRUD + history.
* ``_dispatcher``   — internal AST → handler routing; private,
                       called from ``editor`` and ``write`` only.

The dispatcher is private because no surface outside the package
should call it directly — it sits between the route handlers and
the underlying PQL primitives.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.sql.editor import router as _editor_router
from pointlessql.api.sql.saved_queries import router as _saved_queries_router
from pointlessql.api.sql.write import router as _write_router

router = APIRouter()
router.include_router(_editor_router)
router.include_router(_write_router)
router.include_router(_saved_queries_router)

__all__ = ["router"]
