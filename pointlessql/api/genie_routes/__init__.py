"""``/api/genie`` + ``/genie`` route bundle — curated NL data rooms.

Package layout (one concern per module, combined here):

* ``_spaces`` — space CRUD + trusted assets + transcript listing.
* ``_ask``    — the NL → SQL → governed-execution path, feedback,
  and answer promotion.
* ``_html``   — the list page and the room shell.
* ``_shared`` — serializers + ensure/guard helpers.

NOTE — not yet registered: wire this surface up by adding

    from pointlessql.api.genie_routes import router as genie_router
    app.include_router(genie_router)

to ``pointlessql/api/_bootstrap/_routers.py`` alongside the
metric-views registration.  Router registration is owned by the
bootstrap package and is intentionally left out of this change.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.genie_routes._ask import router as _ask_router
from pointlessql.api.genie_routes._html import router as _html_router
from pointlessql.api.genie_routes._spaces import router as _spaces_router

router = APIRouter(tags=["genie"])
router.include_router(_spaces_router)
router.include_router(_ask_router)
router.include_router(_html_router)

__all__ = ["router"]
