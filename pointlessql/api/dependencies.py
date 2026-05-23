"""Per-request dependency-injection helpers for the API layer.

Every route in the FastAPI app reaches for one of these to recover
the principal-forwarded :class:`UnityCatalogClient`
(``get_uc_client``), the authenticated :class:`UserInfo`
(``get_user``), the admin gate (``require_admin``), or the client
IP for audit rows (``client_ip``).
"""

from __future__ import annotations

from fastapi import Request
from fastapi.templating import Jinja2Templates

from pointlessql.exceptions import AuthorizationError
from pointlessql.models import Workspace
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.services.workspace import _crud as workspaces_service
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
        return UserInfo(
            id=0,
            email="",
            display_name="",
            is_admin=False,
            is_supervisor=False,
            is_auditor=False,
        )
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


def require_user(request: Request) -> None:
    """Raise :class:`AuthorizationError` if no authenticated user is bound.

    Member-accessible routes (notebook workspace, SQL editor read,
    runs list) use this in place of :func:`require_admin` to drop the
    role gate while keeping anonymous callers out.  The auth
    middleware already redirects HTML routes and 401s API routes for
    anonymous traffic, so this dep is a backstop for the rare path
    where middleware did not run (unit tests bypassing it, mounted
    sub-app).

    Args:
        request: Incoming FastAPI request.

    Raises:
        AuthorizationError: When ``request.state.user`` is the
            zero-id placeholder returned by :func:`get_user` for
            anonymous requests.
    """
    user = get_user(request)
    if not user.get("id"):
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege="authenticated",
            securable_type="system",
            full_name="session",
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
    # OIDC-group-derived flags on the User row let session-cookie
    # callers reach Family-B routes without minting an API key.  Both
    # flags pass — same asymmetric ladder as the API-key path: an
    # auditor's read-only mandate covers per-run inspection, not just
    # tenant-wide aggregates.
    if user.get("is_supervisor") or user.get("is_auditor"):
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
    # OIDC-group-derived auditor flag lets a session user read
    # tenant-wide aggregates.  ``is_supervisor`` deliberately does
    # NOT pass here — supervisor scope is run-scoped and would leak
    # data the auditor mandate is the right shape for.
    if user.get("is_auditor"):
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="auditor",
        securable_type="system",
        full_name="audit_read",
    )


def require_analyst(request: Request) -> None:
    """Raise :class:`AuthorizationError` if the caller lacks analyst scope.

    Phase 65 Lens read-only Q&A surface: ``/api/lens/*`` routes,
    the ``/lens`` browser chat UI, and the MCP server (stdio + SSE)
    are gated by this scope.  The analyst sees catalog + lineage +
    bounded-cost SELECT execution; write paths stay closed.

    Pass conditions (any one is sufficient):

    * Bearer key with ``analyst=True`` flag (the canonical Lens
      consumer path — IDE / MCP).
    * Bearer key with ``auditor=True`` flag (auditor sees a
      superset; they can already read everything Lens exposes).
    * Cookie-authenticated admin (admin is strictly stronger).
    * Cookie-authenticated user with the ``is_auditor`` OIDC group
      flag (analog the auditor scope path — auditors get Lens for
      free as part of the read-only mandate).

    Supervisor keys do NOT pass: the supervisor scope is run-scoped
    write-supervision telemetry, which is orthogonal to analyst-style
    data exploration.

    Args:
        request: Incoming FastAPI request.

    Raises:
        AuthorizationError: When the caller is none of the above.
    """
    if getattr(request.state, "api_key_analyst", False):
        return
    if getattr(request.state, "api_key_auditor", False):
        return
    user = get_user(request)
    if user.get("is_admin"):
        return
    if user.get("is_auditor"):
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="analyst",
        securable_type="system",
        full_name="lens",
    )


def require_sql_execute(request: Request) -> None:
    """Raise :class:`AuthorizationError` if the caller lacks sql_execute scope.

    Phase 117: ``/api/2.0/sql/statements`` is the public DBX-compatible
    SQL Statement Execution API.  This surface is **token-only** —
    cookie sessions (browser) are deliberately rejected with 401 by
    the middleware before we reach this gate.  Even an admin cookie
    does not pass: the public API is for external clients (dbt, BI,
    httpx), not for in-browser humans.

    Pass conditions:

    * Bearer key with ``sql_execute=True`` flag.

    Admin / supervisor / auditor / analyst scopes do NOT promote
    into ``sql_execute`` because the surface targets external
    integrations that need narrow grants (e.g. a dbt-databricks
    runner shouldn't also inherit Lens read-only-Q&A).

    Args:
        request: Incoming FastAPI request.

    Raises:
        AuthorizationError: When the caller is not authenticated via
            a Bearer key with the sql_execute flag set.
    """
    if getattr(request.state, "api_key_sql_execute", False):
        return
    user = get_user(request)
    raise AuthorizationError(
        principal=user.get("email", "") or "anonymous",
        privilege="sql_execute",
        securable_type="system",
        full_name="sql_statements_api",
    )


def require_lineage_inbound(request: Request) -> None:
    """Raise :class:`AuthorizationError` if the caller lacks lineage_inbound scope.

    Phase 40: ``POST /api/lineage/openlineage`` is the inbound
    lineage ingestion route.  Federation producers (Kafka-Connect,
    Airflow, dbt-cloud, peer PointlesSQL installs) carry a
    Bearer key minted with ``lineage_inbound=True``.  Supervisor /
    auditor scopes deliberately do **not** pass — they grant read
    access to existing audit data, which is orthogonal to the right
    to *write* federated lineage edges.  Cookie-authenticated admins
    pass: admin is strictly stronger.

    Args:
        request: Incoming FastAPI request.

    Raises:
        AuthorizationError: When the caller is neither an admin
            nor authenticated via a Bearer key with the
            lineage_inbound flag set.
    """
    if getattr(request.state, "api_key_lineage_inbound", False):
        return
    user = get_user(request)
    if user.get("is_admin"):
        return
    raise AuthorizationError(
        principal=user.get("email", ""),
        privilege="lineage_inbound",
        securable_type="system",
        full_name="lineage_inbound",
    )


def current_workspace_id(request: Request) -> int:
    """Return the active workspace id resolved by :func:`auth_middleware`.

    The auth middleware attaches ``request.state.workspace_id`` on
    every request via
    :func:`pointlessql.services.workspace._crud.resolve_workspace_id`.
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
    cross-workspace lens and admin CRUD don't need to special-case
    themselves.  Workspace-local admins
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


def get_templates(request: Request) -> Jinja2Templates:
    """Return the shared :class:`Jinja2Templates` instance from app state.

    The template factory is configured once at app startup (filters,
    autoescape, search path) and stashed on
    ``request.app.state.templates``.  Routes used to redefine a private
    ``_templates`` helper file-by-file — Phase 86 promoted it here so
    HTML routes share one helper and bug-fixes to the rendering shim
    only land in one place.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The shared :class:`Jinja2Templates`.
    """
    return request.app.state.templates


def is_htmx_request(request: Request) -> bool:
    """Return True when the request carries the ``HX-Request`` marker.

    HTMX sets ``HX-Request: true`` on every fetch it issues (inline
    edits, fragment swaps, boosted navigations).  Use this when the
    distinction between "any HTMX call" and "full-page request"
    matters, regardless of boost mode.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` iff the ``HX-Request`` header equals ``"true"``.
    """
    return request.headers.get("HX-Request") == "true"


def is_htmx_boosted(request: Request) -> bool:
    """Return True when the request is an HTMX boosted navigation.

    Boosted nav (``hx-boost``) asks HTMX to behave like a full-page
    swap of ``#main-content``.  The client still expects a complete
    HTML shell with the target block — partial-only renderers must
    skip this branch.  Implies :func:`is_htmx_request`.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` iff the ``HX-Boosted`` header equals ``"true"``.
    """
    return request.headers.get("HX-Boosted") == "true"


def is_htmx_partial(request: Request) -> bool:
    """Return True when the request is an HTMX fragment (non-boosted) call.

    The common shape for inline edits, Load-More buttons, and toast
    targets.  Boosted navigations are *not* partials — they want the
    full HTML shell.  Three call sites had this same expression
    spelled out by hand before Phase 86 centralised it.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` iff ``HX-Request`` is set and ``HX-Boosted`` is not.
    """
    return is_htmx_request(request) and not is_htmx_boosted(request)


def wants_json(request: Request) -> bool:
    """Return True when the caller prefers a JSON / problem+json body.

    ``/api/...`` paths always return JSON.  For other paths, honour
    an explicit ``Accept: application/json`` (or the RFC-9457 media
    type ``application/problem+json``) that does not also include
    ``text/html`` — browsers send ``text/html`` first, so they land
    on the HTML shell.  Promoted from ``error_handlers._wants_json``
    in Phase 86 so non-error routes can negotiate the same way.

    Args:
        request: Incoming FastAPI request.

    Returns:
        ``True`` when JSON / problem+json is preferred, ``False`` for
        an HTML fallback.
    """
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "")
    if not accept:
        return False
    lower = accept.lower()
    has_json = "application/json" in lower or "application/problem+json" in lower
    return has_json and "text/html" not in lower


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
