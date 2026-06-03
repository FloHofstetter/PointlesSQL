"""HTTP surface for the embedded Hermes agent dashboard.

Three routers compose the Agent tab: :mod:`html` (the ``/agent`` page +
admin lifecycle controls), :mod:`proxy` (the same-origin ``/hermes/...``
HTTP reverse-proxy), and :mod:`ws_proxy` (the chat-PTY + gateway
WebSocket bridge).
"""

from __future__ import annotations

from fastapi import APIRouter

from pointlessql.api.hermes_routes.html import router as _html_router
from pointlessql.api.hermes_routes.proxy import router as _proxy_router
from pointlessql.api.hermes_routes.ws_proxy import router as _ws_proxy_router

router = APIRouter()
router.include_router(_html_router)
router.include_router(_ws_proxy_router)
router.include_router(_proxy_router)

__all__ = ["router"]
