"""CSRF-validation middleware for HTML form routes.

Runs on every request and does two things:

1. Issues a :data:`pointlessql.services.csrf.COOKIE_NAME` cookie with a
   fresh random token when the incoming request has none. The token is
   also attached to ``request.state.csrf_token`` so templates can render
   it into hidden form fields and the shared ``<meta name="csrf-token">``
   tag.
2. Enforces token submission on non-safe methods (``POST``, ``PUT``,
   ``PATCH``, ``DELETE``) outside of the JSON API surface. Either the
   ``X-CSRF-Token`` header (used by HTMX via the hook in
   ``base.html``) or the ``csrf_token`` form field (used by the three
   non-JS auth forms) must match the cookie.

The JSON API under ``/api/*`` is exempt by prefix — those routes
decode ``application/json`` bodies via FastAPI's ``Body(...)`` which
browsers cannot forge cross-origin without a CORS preflight, and the
auth cookie carries ``SameSite=Lax`` as a second layer.
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from pointlessql.services import csrf

_SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
_EXEMPT_PREFIXES = ("/api/", "/static/", "/webhook/git/")
_EXEMPT_PATHS = frozenset({"/healthz"})
# The hosted-apps reverse-proxy forwards arbitrary in-iframe app
# traffic (forms, fetches) whose JS cannot know PointlesSQL's CSRF
# token.  The proxy enforces its own auth gate and the auth cookie is
# ``SameSite=Lax``, which covers the cross-site write vector the CSRF
# check exists for.
_APPS_PROXY_RE = re.compile(r"^/apps/[^/]+/proxy/")
# Content types whose body we parse to extract the ``csrf_token`` form
# field. Every other content type (e.g. ``application/json``) is only
# validated via the ``X-CSRF-Token`` header.
_FORM_CONTENT_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")


def _is_exempt_path(path: str) -> bool:
    """Return True when *path* is not subject to CSRF enforcement."""
    if path in _EXEMPT_PATHS:
        return True
    if _APPS_PROXY_RE.match(path):
        return True
    return any(path.startswith(prefix) for prefix in _EXEMPT_PREFIXES)


async def _submitted_token(request: Request) -> str | None:
    """Return the CSRF token the client submitted on this request.

    Prefers the ``X-CSRF-Token`` header (set automatically on every HTMX
    request via the hook in ``base.html``). Falls back to parsing the
    form body for a ``csrf_token`` field when the request is a
    form-encoded or multipart POST, re-injecting the buffered body so
    the route handler can still read it.
    """
    header_value = request.headers.get(csrf.HEADER_NAME)
    if header_value:
        return header_value

    content_type = request.headers.get("content-type", "")
    if not any(content_type.startswith(ct) for ct in _FORM_CONTENT_TYPES):
        return None

    # Reading ``request.form()`` consumes the ASGI body stream; cache
    # the raw bytes and install a replacement ``receive`` callable so
    # the downstream route handler can still await ``request.form()``
    # (or ``request.body()``) and get the same payload.
    body = await request.body()

    async def _receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = _receive  # pyright: ignore[reportPrivateUsage]

    form = await request.form()
    value = form.get(csrf.FORM_FIELD)
    return value if isinstance(value, str) else None


def _set_cookie(response: Response, token: str, max_age: int) -> None:
    """Write the CSRF cookie with the same attributes used by auth."""
    response.set_cookie(
        csrf.COOKIE_NAME,
        token,
        httponly=True,
        samesite="lax",
        max_age=max_age,
        path="/",
    )


async def csrf_middleware(request: Request, call_next: Any) -> Response:
    """Issue CSRF cookies on GET and validate tokens on state-changing POSTs.

    Args:
        request: The incoming Starlette request.
        call_next: Downstream handler to forward validated requests to.

    Returns:
        Response: The downstream response on success, or a 403
        :class:`HTMLResponse` when the submitted token does not match
        the cookie.
    """
    cookie_token = request.cookies.get(csrf.COOKIE_NAME)
    issued_new = False
    if not cookie_token:
        cookie_token = csrf.generate_token()
        issued_new = True
    request.state.csrf_token = cookie_token

    method = request.method.upper()
    needs_check = method not in _SAFE_METHODS and not _is_exempt_path(request.url.path)
    if needs_check:
        submitted = await _submitted_token(request)
        # When the cookie was freshly generated in this request the
        # client could not possibly have echoed it back. Reject without
        # trying to match against the new value, since ``tokens_match``
        # would succeed if the attacker guessed an empty cookie.
        if issued_new or not csrf.tokens_match(cookie_token, submitted):
            return HTMLResponse(
                "<h1>403 — CSRF token mismatch</h1>"
                "<p>Your session's CSRF token did not match. "
                "Reload the page and try again.</p>",
                status_code=403,
            )

    response = await call_next(request)

    if issued_new:
        settings = getattr(request.app.state, "settings", None)
        auth_cfg = getattr(settings, "auth", None)
        max_age = int(getattr(auth_cfg, "jwt_expiry_hours", 168)) * 3600
        _set_cookie(response, cookie_token, max_age)

    return response
