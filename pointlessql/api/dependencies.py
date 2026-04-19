"""Per-request dependency-injection helpers for the API layer.

Sprint 85 split out of ``api/main.py``.  Every route in the FastAPI
app reaches for one of these to recover the principal-forwarded
:class:`UnityCatalogClient` (``get_uc_client``), the authenticated
:class:`UserInfo` (``get_user``), the admin gate
(``require_admin``), or the client IP for audit rows
(``client_ip``).
"""

from __future__ import annotations

from fastapi import Request

from pointlessql.exceptions import AuthorizationError
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo


def get_uc_client(request: Request) -> UnityCatalogClient:
    """Return a per-request UC facade with the current user's principal.

    Args:
        request: Incoming FastAPI request.

    Returns:
        A :class:`UnityCatalogClient` configured with the current
        user's ``X-Principal``, or the app-state default client when
        no user is bound to the request.
    """
    user = getattr(request.state, "user", None)
    if user is not None:
        return UnityCatalogClient.for_principal(request.app.state.settings, user["email"])
    return request.app.state.uc_client


def get_user(request: Request) -> UserInfo:
    """Return the current user dict from request state.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The :class:`UserInfo` set by :func:`auth_middleware`, or a
        zero-id placeholder when the request is anonymous.
    """
    user: UserInfo | None = getattr(request.state, "user", None)
    if user is None:
        return UserInfo(id=0, email="", display_name="", is_admin=False)
    return user


def require_admin(request: Request) -> None:
    """Raise :class:`AuthorizationError` if the current user is not an admin.

    Args:
        request: Incoming FastAPI request.

    Raises:
        AuthorizationError: When ``request.state.user`` is missing
            or its ``is_admin`` flag is false.
    """
    user = get_user(request)
    if not user.get("is_admin"):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="admin",
            securable_type="system",
            full_name="admin",
        )


def client_ip(request: Request) -> str | None:
    """Best-effort extraction of the client IP for audit rows.

    ASGI's ``request.client`` returns ``None`` for ASGI transports
    without a remote peer (unit tests hit this path). Behind a
    trusted reverse proxy the operator should configure Starlette's
    ``ProxyHeadersMiddleware`` upstream of this call; Sprint 48
    deliberately does not honour ``X-Forwarded-For`` here because
    the audit surface has no separate "trusted-proxy" opt-in like
    Sprint 43's rate limiter does.

    Args:
        request: The incoming HTTP request.

    Returns:
        IPv4/IPv6 address or ``None`` if unavailable.
    """
    return request.client.host if request.client else None
