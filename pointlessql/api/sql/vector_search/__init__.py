"""``/api/sql/vector_search/*`` — Phase 92 REST surface.

Three routers:

* ``_search``       — ``POST /api/sql/vector_search``: free-text
                      semantic search over an indexed Delta column.
                      Reuses the SQL dispatcher's
                      :func:`enforce_select_per_table` so a user
                      cannot vector-search a table they can't SELECT.
* ``_index_admin``  — ``POST /api/sql/vector_search/indices`` +
                      ``GET`` + ``DELETE``.  Index creation /
                      rebuild / drop is workspace-admin only;
                      listing is open to anyone with a session.

Audit-mirroring + RFC 9457 envelopes match the editor routes.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.sql.vector_search._embed import router as _embed_router
from pointlessql.api.sql.vector_search._index_admin import (
    router as _index_admin_router,
)
from pointlessql.api.sql.vector_search._search import router as _search_router

router = APIRouter()
router.include_router(_search_router)
router.include_router(_index_admin_router)
router.include_router(_embed_router)

__all__ = ["router"]
