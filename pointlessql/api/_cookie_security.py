"""Resolve the ``Secure`` attribute for auth/session cookies.

Session, CSRF, workspace and OIDC-state cookies were set without the
``Secure`` flag, so they rode over any plain-HTTP hop in cleartext and
could be lifted for a session hijack.  This resolver decides the flag the
same way the HSTS header is decided: honour an explicit operator setting,
otherwise auto-detect from the request scheme (Secure on https).
"""

from __future__ import annotations

from fastapi import Request


def resolve_cookie_secure(request: Request) -> bool:
    """Return whether auth cookies should carry the ``Secure`` attribute.

    ``POINTLESSQL_AUTH_COOKIE_SECURE`` forces the flag when set to a
    concrete ``True``/``False``; left unset (the default ``None``) it
    auto-detects, mirroring ``security_headers_middleware``'s HSTS check.

    Args:
        request: The incoming request whose scheme drives auto-detection.

    Returns:
        ``True`` when cookies should be marked ``Secure``.
    """
    configured: bool | None = request.app.state.settings.auth.cookie_secure
    if configured is not None:
        return configured
    return request.url.scheme == "https"
