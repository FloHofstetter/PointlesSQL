"""Polymorphic Issues router — split per CRUD verb.

The pre-Phase-110 layout collapsed every route + helper into one
~749 LOC ``issues.py`` module.  Phase 110.7 split it per verb-group:

* :mod:`._open`   — ``POST /api/social/{parent_kind}/{parent_ref}/issues``
  with audit + governance + fanout side-effects.  Owns the
  ``MAX_TITLE`` length cap.
* :mod:`._list`   — ``GET /api/social/.../issues`` parent-scoped
  listing + ``GET /api/issues`` global cross-entity index.
* :mod:`._detail` — ``GET /api/issues/{id}`` + ``PATCH /api/issues/{id}``.
* :mod:`._state`  — ``POST /api/issues/{id}/close`` + ``.../reopen``
  + the shared ``_transition_state`` body that audits + emits the
  governance event + feed fanout.

``router`` mounts each sub-router; ``social_routes.__init__`` imports
``issues.router`` which now resolves to the assembled router.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.social_routes.issues._detail import router as _detail_router
from pointlessql.api.social_routes.issues._list import router as _list_router
from pointlessql.api.social_routes.issues._open import router as _open_router
from pointlessql.api.social_routes.issues._state import router as _state_router

router = APIRouter()
router.include_router(_open_router)
router.include_router(_list_router)
router.include_router(_detail_router)
router.include_router(_state_router)

__all__ = ["router"]
