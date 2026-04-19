"""HTTP middleware registration for the FastAPI app.

Sprint 85 split out of ``api/main.py``.  Centralises the five
middleware the app stacks on every request — auth, rate-limit, CSRF,
static-cache revalidation, request-id — into one
:func:`register_middleware` call so callers cannot accidentally
re-order them.

Order is **load-bearing**.  Starlette stacks middleware LIFO:
last-added runs first (outermost) on the incoming request.  This
function adds in the following order so the execution chain on an
incoming request becomes::

    request_id → static_revalidate → csrf → rate_limit → auth → handler

* ``auth`` resolves the user from the JWT cookie before any handler.
* ``rate_limit`` runs INSIDE csrf (a CSRF-failed flood must not burn
  bucket slots) and OUTSIDE auth (a flood must not bcrypt-hash the
  payload before being throttled).  Sprint 43.
* ``csrf`` runs OUTSIDE auth so a CSRF failure short-circuits before
  bcrypt + JWT-decode.  Sprint 42.
* ``static_module_revalidate`` only mutates response headers for
  ``/static/js/notebook/`` paths so the editor's ESM imports always
  conditional-revalidate.  Phase 12.7 BUG-72-01.
* ``request_id`` is the outermost so the X-Request-ID echo + the
  contextvar reach into every other middleware's log lines.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from pointlessql.api.csrf_middleware import csrf_middleware as _csrf_middleware
from pointlessql.api.rate_limit_middleware import (
    rate_limit_middleware as _rate_limit_middleware,
)
from pointlessql.logging_config import request_id_var
from pointlessql.services import auth as auth_service

logger = logging.getLogger(__name__)


# Paths that do not require authentication.
# Sprint 55: ``/alerts/feed.atom`` + ``/alerts/feed.json`` authenticate
# via the opaque ``?token=…`` query-string, not the session cookie —
# feed readers (Miniflux, FreshRSS, …) do not have a browser session.
# They are listed here so the session auth_middleware does not
# redirect them to ``/auth/login``; the route handlers themselves
# reject unknown tokens with 401.
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/auth/", "/static/", "/healthz",
    "/alerts/feed.atom", "/alerts/feed.json",
)


async def auth_middleware(request: Request, call_next: Any) -> Response:
    """Extract user from JWT cookie; redirect to login if unauthenticated."""
    path = request.url.path

    # Always try to resolve user from cookie (even on public paths,
    # so templates can show the navbar user menu).
    token = request.cookies.get(auth_service.COOKIE_NAME)
    if token is not None:
        factory = getattr(request.app.state, "session_factory", None)
        settings = getattr(request.app.state, "settings", None)
        if factory is not None and settings is not None:
            user = auth_service.get_current_user(
                factory,
                token,
                settings.auth.secret_key,
                previous_key=settings.auth.secret_key_previous,
            )
            if user is not None:
                request.state.user = user

    # Public paths pass through regardless of auth.
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)

    # Protected paths require authentication.
    if getattr(request.state, "user", None) is not None:
        return await call_next(request)

    # Unauthenticated — redirect HTML requests, 401 for API.
    if path.startswith("/api/"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return RedirectResponse(url="/auth/login", status_code=303)


async def static_module_revalidate_middleware(
    request: Request, call_next: Any,
) -> Response:
    """Force conditional revalidation for the notebook editor's ES modules.

    Phase 12.7 BUG-72-01 fix.  The notebook editor's ``bootstrap.js``
    carries a ``?v=sprintNN`` script-tag query so its own ``<script>``
    invalidates on a sprint bump, but the eleven ESM modules it
    dynamically imports do **not** carry a version param — and ES
    module URLs are cached by the browser in the regular HTTP cache
    keyed by their URL.  Without a Cache-Control header, browsers
    apply heuristic freshness based on Last-Modified, which can keep
    a stale ``output_renderer.js`` (or ``main.js`` etc.) bytes alive
    across deploys until the user hard-reloads.  This middleware
    stamps ``Cache-Control: no-cache`` on every ``/static/js/notebook/``
    response so the browser MUST issue a conditional ``If-Modified-
    Since`` request next time — Starlette's StaticFiles already
    answers 304 when unchanged, so the network cost stays minimal,
    but a sprint-fresh module is delivered immediately on the next
    page load.
    """
    response = await call_next(request)
    if request.url.path.startswith("/static/js/notebook/"):
        response.headers["Cache-Control"] = "no-cache, must-revalidate"
    return response


async def request_id_middleware(request: Request, call_next: Any) -> Response:
    """Attach a unique request ID to every request and echo it in the response.

    The ID is stored both on ``request.state`` (for the error handler)
    and in the ``request_id_var`` contextvar (so service-layer log
    records emitted during this request pick it up via the
    ``RequestIdFilter``). The contextvar is reset in ``finally`` so
    concurrent requests never leak IDs into each other's scope.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


def register_middleware(app: FastAPI) -> None:
    """Stack all five middleware on *app* in the canonical order.

    See module docstring for the LIFO reasoning behind the call
    sequence below.  Calling this once during app construction
    replaces the five scattered ``@app.middleware("http")``
    decorators that previously lived in ``api/main.py``.

    Args:
        app: The FastAPI app to attach middleware to.
    """
    app.middleware("http")(auth_middleware)
    app.middleware("http")(_rate_limit_middleware)
    app.middleware("http")(_csrf_middleware)
    app.middleware("http")(static_module_revalidate_middleware)
    app.middleware("http")(request_id_middleware)
