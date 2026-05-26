"""``/api/users/...`` — user-directory API surface.

The package facade aggregates per-axis sub-modules:

* 76.1 — ``search`` (typeahead for @-autocomplete).
* 76.2 — ``profile`` + ``follows`` (profile page + user-to-user
  follow toggles + badges).

Public surface is the FastAPI router re-exported here so
``from pointlessql.api.users_routes import router`` works.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.users_routes.follows import router as _follows_router
from pointlessql.api.users_routes.profile import router as _profile_router
from pointlessql.api.users_routes.search import router as _search_router

router = APIRouter(tags=["users"])
router.include_router(_search_router)
router.include_router(_profile_router)
router.include_router(_follows_router)


__all__ = ["router"]
