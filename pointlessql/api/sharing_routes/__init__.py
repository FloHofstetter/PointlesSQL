"""``/api/sharing`` route bundle — Delta Sharing, both directions.

* ``_provider`` — admin-gated management of *our* shares and
  recipients (proxied to soyuz-catalog through the UC facade).
* ``_consumer`` — provider profiles for *remote* shares this
  workspace reads, plus protocol browsing and DataFrame previews.
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.sharing_routes._consumer import router as _consumer_router
from pointlessql.api.sharing_routes._provider import router as _provider_router

router = APIRouter(tags=["sharing"])
router.include_router(_provider_router)
router.include_router(_consumer_router)

__all__ = ["router"]
