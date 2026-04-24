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


def effective_principal(request: Request) -> str | None:
    """Return the effective principal for SELECT enforcement + audit.

    Sprint 13.6.  The ``X-Principal`` header takes precedence so an
    external runtime (Hermes, an ops curl) can act on behalf of an
    end user without that user holding a session cookie on
    PointlesSQL.  When the header is absent or empty we fall back
    to the session-cookie user's email.  When neither is set the
    request is anonymous and the function returns ``None`` —
    callers decide whether to short-circuit or continue with the
    default UC client.

    The header is the same one the Sprint-13.2 agent-runs registry
    already accepts; Sprint 13.6 propagates it through to the SQL
    routes and the query-history audit row.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The effective principal email, or ``None`` for anonymous.
    """
    header = request.headers.get("x-principal")
    if header and header.strip():
        return header.strip()
    user = getattr(request.state, "user", None)
    if user is not None and user.get("email"):
        return str(user["email"])
    return None


def get_uc_client(request: Request) -> UnityCatalogClient:
    """Return a per-request UC facade with the effective principal.

    Sprint 13.6: prefers :func:`effective_principal` so an
    ``X-Principal`` header overrides the cookie user (Hermes plugin
    + curl ops both depend on this hop).

    Args:
        request: Incoming FastAPI request.

    Returns:
        A :class:`UnityCatalogClient` configured with the effective
        principal, or the app-state default client when no
        principal is bound to the request.
    """
    principal = effective_principal(request)
    if principal:
        return UnityCatalogClient.for_principal(request.app.state.settings, principal)
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
