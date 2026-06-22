"""Principal, UC-client, user, and client-IP request dependencies.

These recover the effective principal for SELECT enforcement + audit,
the principal-forwarded :class:`UnityCatalogClient`, the authenticated
:class:`UserInfo`, and the best-effort client IP — the primitives every
authenticated route builds on.
"""

from __future__ import annotations

from fastapi import Request

from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo


def _caller_may_impersonate(request: Request) -> bool:
    """Whether this request is trusted to set ``X-Principal`` to another identity.

    Only two callers may speak for someone else: a request authenticated
    with an API key (Hermes, ops curl — server-to-server credentials an
    admin issued) and an admin cookie session.  A normal non-admin cookie
    session must not be able to forge a higher-privileged principal.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` for API-key or admin callers; ``False`` otherwise.
    """
    if getattr(request.state, "api_key_id", None) is not None:
        return True
    user = getattr(request.state, "user", None)
    return bool(user is not None and user.get("is_admin"))


def effective_principal(request: Request) -> str | None:
    """Return the effective principal for SELECT enforcement + audit.

    The ``X-Principal`` header lets a *trusted* caller act on behalf of an
    end user without that user holding a session cookie — but only when
    the request is API-key authenticated or the cookie user is an admin
    (:func:`_caller_may_impersonate`).  For a normal non-admin cookie
    session the header is ignored and we fall back to that user's own
    email, so it cannot impersonate a higher-privileged principal to
    bypass grants or forge the audit trail.  When neither a trusted
    override nor a cookie user is present the request is anonymous and the
    function returns ``None``.

    The header is the same one the agent-runs registry accepts and is also
    propagated through to the SQL routes and the query-history audit row
    so attribution stays consistent across hops.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The effective principal email, or ``None`` for anonymous.
    """
    header = request.headers.get("x-principal")
    if header and header.strip() and _caller_may_impersonate(request):
        return header.strip()
    user = getattr(request.state, "user", None)
    if user is not None and user.get("email"):
        return str(user["email"])
    return None


def get_uc_client(request: Request) -> UnityCatalogClient:
    """Return a per-request UC facade with the effective principal.

    Prefers :func:`effective_principal` so an ``X-Principal``
    header overrides the cookie user (Hermes plugin + curl ops both
    depend on this hop).

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
    user = get_optional_user(request)
    if user is None:
        return UserInfo(
            id=0,
            email="",
            display_name="",
            is_admin=False,
            is_supervisor=False,
            is_auditor=False,
        )
    return user


def get_optional_user(request: Request) -> UserInfo | None:
    """Return the current user, or ``None`` for anonymous requests.

    The ``None``-preserving sibling of :func:`get_user` for call sites
    that branch on anonymity or feed nullable ``actor_id`` /
    ``actor_email`` columns — :func:`get_user`'s zero-id placeholder
    would silently turn "anonymous" into "user 0" there.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The :class:`UserInfo` set by the auth middleware, or ``None``
        when the request carries no authenticated user.
    """
    user: UserInfo | None = getattr(request.state, "user", None)
    return user


def client_ip(request: Request) -> str | None:
    """Best-effort extraction of the client IP for audit rows.

    ASGI's ``request.client`` returns ``None`` for ASGI transports
    without a remote peer (unit tests hit this path). Behind a
    trusted reverse proxy the operator should configure Starlette's
    ``ProxyHeadersMiddleware`` upstream of this call; the audit
    surface deliberately does not honour ``X-Forwarded-For`` here
    because it has no separate "trusted-proxy" opt-in like the
    rate limiter does.

    Args:
        request: The incoming HTTP request.

    Returns:
        IPv4/IPv6 address or ``None`` if unavailable.
    """
    return request.client.host if request.client else None
