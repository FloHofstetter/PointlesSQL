"""HTTP middleware registration for the FastAPI app.

Sprint 85 split out of ``api/main.py``.  Centralises the four
middleware the app stacks on every request — auth, rate-limit, CSRF,
request-id — into one :func:`register_middleware` call so callers
cannot accidentally re-order them.

Order is **load-bearing**.  Starlette stacks middleware LIFO:
last-added runs first (outermost) on the incoming request.  This
function adds in the following order so the execution chain on an
incoming request becomes::

    request_id → csrf → rate_limit → auth → handler

* ``auth`` resolves the user from the JWT cookie before any handler.
* ``rate_limit`` runs INSIDE csrf (a CSRF-failed flood must not burn
  bucket slots) and OUTSIDE auth (a flood must not bcrypt-hash the
  payload before being throttled).  Sprint 43.
* ``csrf`` runs OUTSIDE auth so a CSRF failure short-circuits before
  bcrypt + JWT-decode.  Sprint 42.
* ``request_id`` is the outermost so the X-Request-ID echo + the
  contextvar reach into every other middleware's log lines.

Phase 12.12.2 removed the ``static_module_revalidate`` layer with
the browser notebook editor; the editor's vendored ESM modules no
longer exist, so the ``/static/js/notebook/`` no-cache hook has no
consumer.
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
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import auth as auth_service
from pointlessql.types import UserInfo

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
    """Resolve a principal from cookie OR Bearer key; gate protected paths.

    Sprint 13.7.0.5 added the Bearer-token branch.  Sprint 13.11.4a
    moved the credential store from a process-wide env-parsed dict
    into the ``api_keys`` DB table — verification now goes through
    :func:`pointlessql.services.api_keys.verify_bearer` which
    consults the DB (with a 60s in-memory TTL cache).  On match a
    synthetic :class:`UserInfo` is attached so downstream routes
    (which only ever read ``request.state.user``) need no awareness
    of the alternate auth path; ``request.state.api_key_name``
    keeps the audit attribution and
    ``request.state.api_key_supervisor`` exposes the Sprint-13.11.4a
    scope flag for ``require_supervisor``.

    Cookie auth still wins when both are present so a human in a
    browser keeps their identity even if a misconfigured proxy
    forwards a Bearer header.
    """
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

    # Sprint 13.7.0.5 + 13.11.4a: fall back to API-key bearer token
    # when no cookie user resolved.  The store is now DB-backed
    # (Alembic 025); the env-var path remains valid as a bootstrap
    # spilled in by :func:`api_keys_service.bootstrap_from_env` at
    # startup.  Cache TTL inside :func:`verify_bearer` keeps the
    # hot path off the DB except on miss.
    if getattr(request.state, "user", None) is None:
        factory = getattr(request.app.state, "session_factory", None)
        entry = api_keys_service.verify_bearer(
            request.headers.get("authorization"),
            factory,
        )
        if entry is not None:
            request.state.api_key_name = entry.name
            request.state.api_key_supervisor = entry.supervisor
            request.state.user = UserInfo(
                id=0,
                email=f"api_key:{entry.name}",
                display_name=entry.name,
                is_admin=False,
            )

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
    """Stack all four middleware on *app* in the canonical order.

    See module docstring for the LIFO reasoning behind the call
    sequence below.  Calling this once during app construction
    replaces the scattered ``@app.middleware("http")`` decorators
    that previously lived in ``api/main.py``.

    Args:
        app: The FastAPI app to attach middleware to.
    """
    app.middleware("http")(auth_middleware)
    app.middleware("http")(_rate_limit_middleware)
    app.middleware("http")(_csrf_middleware)
    app.middleware("http")(request_id_middleware)
