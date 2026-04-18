"""CSRF token generation and validation.

The server uses a *double-submit cookie* pattern to protect
state-changing HTML form routes from cross-site request forgery. A
random token is set as an ``HttpOnly`` cookie and also rendered into
every form (as a hidden input) and the shared page ``<head>``
(as a meta tag for HTMX). On non-safe requests the middleware checks
that the cookie value matches either the ``X-CSRF-Token`` header or
the ``csrf_token`` form field.

Keeping the helpers in a service module (not the middleware module)
lets the auth routes reuse :func:`generate_token` when they rotate
the cookie on login / logout.
"""

from __future__ import annotations

import secrets

COOKIE_NAME = "pql_csrf"
HEADER_NAME = "X-CSRF-Token"
FORM_FIELD = "csrf_token"


def generate_token() -> str:
    """Return a fresh random CSRF token.

    Returns:
        str: A URL-safe 32-byte random string.
    """
    return secrets.token_urlsafe(32)


def tokens_match(cookie_token: str | None, submitted_token: str | None) -> bool:
    """Compare a cookie token with a submitted token in constant time.

    Returns ``False`` whenever either side is missing, empty, or the two
    values differ. Uses :func:`secrets.compare_digest` so the comparison
    is not vulnerable to timing side-channels.

    Args:
        cookie_token: Value of the ``pql_csrf`` cookie on the request,
            or ``None`` when absent.
        submitted_token: Value carried in the ``X-CSRF-Token`` header or
            the ``csrf_token`` form field, or ``None`` when absent.

    Returns:
        bool: ``True`` only when both tokens are present and equal.
    """
    if not cookie_token or not submitted_token:
        return False
    return secrets.compare_digest(cookie_token, submitted_token)
