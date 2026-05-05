"""Per-request dependency-injection helpers for the API layer.

Every route in the FastAPI app reaches for one of these to recover
the principal-forwarded :class:`UnityCatalogClient`
(``get_uc_client``), the authenticated :class:`UserInfo`
(``get_user``), the admin gate (``require_admin``), or the client
IP for audit rows (``client_ip``).
"""

from __future__ import annotations

from fastapi import Request

from pointlessql.exceptions import AuthorizationError
from pointlessql.models import Workspace
from pointlessql.services import workspaces as workspaces_service
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo


def effective_principal(request: Request) -> str | None:
    """Return the effective principal for SELECT enforcement + audit.

    The ``X-Principal`` header takes precedence so an external
    runtime (Hermes, an ops curl) can act on behalf of an end user
    without that user holding a session cookie on PointlesSQL.
    When the header is absent or empty we fall back to the
    session-cookie user's email.  When neither is set the request
    is anonymous and the function returns ``None`` — callers decide
    whether to short-circuit or continue with the default UC client.

    The header is the same one the agent-runs registry accepts and
    is also propagated through to the SQL routes and the query-
    history audit row so attribution stays consistent across hops.

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


def require_supervisor(request: Request) -> None:
    """Raise :class:`AuthorizationError` if the caller lacks supervisor scope.

    Family-B routes (run summary, run diff, runs-by-principal,
    runs-by-agent) are restricted to API keys flagged
    ``supervisor=True`` — supervision telemetry shouldn't be
    walkable by every working agent.  Cookie-authenticated admins
    also pass: the admin role is strictly stronger than supervisor.

     also accepts the ``auditor`` scope here: an
    auditor's read-only mandate spans both tenant-wide aggregates
    AND per-run inspection, so an audit-reviewer key can drill into
    any run's risk-summary without also issuing it a supervisor
    key.  Approve / deny stay :func:`require_admin` regardless.

    Args:
        request: Incoming FastAPI request.

    Raises:
        AuthorizationError: When the caller is neither an admin
            nor authenticated via a Bearer key with the supervisor
            or auditor flag set.
    """
    if getattr(request.state, "api_key_supervisor", False):
        return
    if getattr(request.state, "api_key_auditor", False):
        return
    user = get_user(request)
    if user.get("is_admin"):
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="supervisor",
        securable_type="system",
        full_name="agent_runs",
    )


def require_auditor(request: Request) -> None:
    """Raise :class:`AuthorizationError` if the caller lacks auditor scope.

    introduces a read-only audit scope that gates the
    tenant-wide ``/api/audit/*`` aggregates (summary / timeseries /
    anomalies / history) and the per-run audit-axis routes
    (``/api/agent-runs/{id}/audit/<axis>``).  Cookie-authenticated
    admins pass — admin is strictly stronger.  Supervisor keys do
    NOT pass: tenant-wide aggregates would leak data the supervisor
    scope is not chartered to see.

    PII reveal stays admin-only (``require_admin``); auditor scope
    deliberately cannot un-mask reversible values.

    Args:
        request: Incoming FastAPI request.

    Raises:
        AuthorizationError: When the caller is neither an admin
            nor authenticated via a Bearer key with the auditor
            flag set.
    """
    if getattr(request.state, "api_key_auditor", False):
        return
    user = get_user(request)
    if user.get("is_admin"):
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="auditor",
        securable_type="system",
        full_name="audit_read",
    )


def current_workspace_id(request: Request) -> int:
    """Return the active workspace id resolved by :func:`auth_middleware`.

    Sprint 28.0 attaches ``request.state.workspace_id`` on every
    request via :func:`pointlessql.services.workspaces.resolve_workspace_id`.
    Routes that need to scope SQL by workspace pull the id through
    this dependency instead of reading the request state directly so
    the contract stays grep-able and a future swap-out (e.g. flipping
    to a typed dataclass) only touches one helper.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The active workspace id, defaulting to
        :data:`workspaces_service.DEFAULT_WORKSPACE_ID` when the
        middleware did not run (e.g. unit tests bypassing it).
    """
    value = getattr(request.state, "workspace_id", None)
    if isinstance(value, int) and value > 0:
        return value
    return workspaces_service.DEFAULT_WORKSPACE_ID


def current_workspace(request: Request) -> Workspace:
    """Return the active :class:`Workspace` row resolved for this request.

    Convenience for HTML routes that want the slug / name in the
    rendered template.  Always returns a row — when the seeded
    default is missing (development-time anomaly) we synthesise a
    transient placeholder rather than raise, because the request
    pipeline must not 500 on a startup edge case.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The detached :class:`Workspace` row.
    """
    factory = getattr(request.app.state, "session_factory", None)
    workspace_id = current_workspace_id(request)
    if factory is None:
        return _placeholder_workspace(workspace_id)
    row = workspaces_service.get_workspace(factory, workspace_id=workspace_id)
    if row is None:
        return _placeholder_workspace(workspace_id)
    return row


def _placeholder_workspace(workspace_id: int) -> Workspace:
    """Synthesise a detached :class:`Workspace` row for safe template fallback.

    The pipeline must never 500 on a missing-default-workspace edge
    case (e.g. tests that bypass the seed migration).  This stand-in
    carries the resolved id and the conventional slug so templates
    that surface ``workspace.slug`` show something coherent.
    """
    import datetime

    placeholder = Workspace(
        id=workspace_id,
        slug=workspaces_service.DEFAULT_WORKSPACE_SLUG,
        name="Default workspace",
        description=None,
        created_at=datetime.datetime.now(datetime.UTC),
        archived_at=None,
    )
    return placeholder


def require_workspace_admin(request: Request) -> None:
    """Raise :class:`AuthorizationError` unless the caller is admin in this workspace.

    Tenant-wide admins (``users.is_admin = True``) always pass —
    they are strictly stronger than workspace-local admins so the
    cross-workspace lens (Sprint 28.7) and admin CRUD (Sprint 28.6)
    don't need to special-case themselves.  Workspace-local admins
    pass too via the :class:`WorkspaceMember.role` lookup.  Bearer
    keys never carry a per-workspace role today; admin UI pages are
    cookie-only by convention so this check refuses Bearer auth
    entirely.

    Args:
        request: Incoming FastAPI request.

    Raises:
        AuthorizationError: When the caller is neither a tenant
            admin nor a workspace-local admin.
    """
    user = get_user(request)
    if user.get("is_admin"):
        return
    user_id = user.get("id", 0)
    if not user_id:
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="workspace.admin",
            securable_type="workspace",
            full_name="workspace",
        )
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="workspace.admin",
            securable_type="workspace",
            full_name="workspace",
        )
    workspace_id = current_workspace_id(request)
    role = workspaces_service.get_membership_role(
        factory, workspace_id=workspace_id, user_id=int(user_id)
    )
    if role == "admin":
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="workspace.admin",
        securable_type="workspace",
        full_name=f"workspace:{workspace_id}",
    )


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
