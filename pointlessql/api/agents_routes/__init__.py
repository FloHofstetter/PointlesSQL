"""``/api/agents/...`` — first-class agent identity (Phase 76.5)."""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.agents_routes.crud import router as _crud_router
from pointlessql.api.agents_routes.profile import router as _profile_router

router = APIRouter(tags=["agents"])
router.include_router(_crud_router)
router.include_router(_profile_router)


__all__ = ["router"]
