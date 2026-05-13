"""``/api/settings/...`` — per-caller settings surface (Phase 76.4+)."""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.settings_routes.notifications import (
    router as _notifications_router,
)

router = APIRouter(tags=["settings"])
router.include_router(_notifications_router)


__all__ = ["router"]
