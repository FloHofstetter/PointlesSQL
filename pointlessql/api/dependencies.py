"""Per-request dependency-injection helpers for the API layer.

Every route in the FastAPI app reaches for one of these to recover
the principal-forwarded :class:`UnityCatalogClient`
(``get_uc_client``), the authenticated :class:`UserInfo`
(``get_user``), the admin gate (``require_admin``), or the client
IP for audit rows (``client_ip``).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from fastapi import Query, Request
from fastapi.responses import Response
from fastapi.templating import Jinja2Templates

from pointlessql.exceptions import AuthorizationError, CatalogUnavailableError
from pointlessql.models import DataProduct, Workspace
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.services.workspace import _crud as workspaces_service
from pointlessql.types import UserInfo


@dataclass(frozen=True)
class PaginationParams:
    """Bounded offset+limit pair for list endpoints.

    Used as the return type of :func:`pagination`, the shared
    FastAPI dependency that replaces 30+ copy-pasted
    ``Query(default=...)`` declarations across audit, runs,
    data-products, notifications and social routes.

    Attributes:
        offset: Row offset (``>= 0``).
        limit: Page size (``1 <= limit <= 1000``).
    """

    offset: int
    limit: int


def pagination(
    offset: int = Query(0, ge=0, description="Row offset (>= 0)."),
    limit: int = Query(100, ge=1, le=1000, description="Page size (1-1000)."),
) -> PaginationParams:
    """Return bounded :class:`PaginationParams` for a list route.

    Args:
        offset: Row offset, validated by FastAPI to be non-negative.
        limit: Page size, validated by FastAPI to be in ``[1, 1000]``.

    Returns:
        A frozen :class:`PaginationParams` carrying the validated pair.
    """
    return PaginationParams(offset=offset, limit=limit)


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


def admin_uc(request: Request) -> UnityCatalogClient:
    """Combine :func:`require_admin` + :func:`get_uc_client` for admin UC routes.

    collapses the ``require_admin(request);
    client = get_uc_client(request)`` couplet repeated at the top of every
    admin-only UC route into a single :func:`Depends` injection.

    Args:
        request: Incoming FastAPI request.

    Returns:
        The per-request :class:`UnityCatalogClient` facade.

    Raises:
        AuthorizationError: When the caller is not an admin (via
            :func:`require_admin`).
    """  # noqa: DOC502
    require_admin(request)
    return get_uc_client(request)


_VALID_ROLES = frozenset({"admin", "supervisor", "auditor", "analyst", "user"})


def require_role(*roles: str) -> Callable[[Request], None]:
    """Return a Depends-compatible callable enforcing role-set membership.

    The factory generalises the single-role
    ``require_admin`` / ``require_supervisor`` / ``require_auditor``
    gates into one parametrised form.  Routes that need
    "admin OR auditor" (read-paths shared between tenant ops + audit
    reviewers) can declare
    ``_: None = Depends(require_role("admin", "auditor"))`` instead of
    hand-rolling an OR gate.

    Recognised roles (mirrors :class:`UserInfo` flags + api_key scopes
    attached by :func:`auth_middleware`):

    * ``admin`` — ``user.is_admin``.
    * ``supervisor`` — ``user.is_supervisor`` OR
      ``request.state.api_key_supervisor``.
    * ``auditor`` — ``user.is_auditor`` OR
      ``request.state.api_key_auditor``.
    * ``analyst`` — ``user.is_auditor`` (auditor scope covers analyst)
      OR ``request.state.api_key_analyst`` OR
      ``request.state.api_key_auditor``.
    * ``user`` — any authenticated principal (``user.id > 0``).

    Admin is strictly stronger than every other role: an admin caller
    passes regardless of whether ``"admin"`` was included in *roles*.
    This matches the existing :func:`require_supervisor` and
    :func:`require_auditor` semantics where admins always succeed.

    The two token-only gates (:func:`require_sql_execute` and
    :func:`require_lineage_inbound`) deliberately do not promote via
    this factory — those surfaces target external integrations that
    need narrow grants, so they keep their dedicated dep.

    Args:
        *roles: One or more role identifiers the caller must satisfy
            (logical OR).  At least one role required.

    Returns:
        A FastAPI dep callable that raises
        :class:`AuthorizationError` when none of *roles* match.

    Raises:
        ValueError: When *roles* is empty or contains an unrecognised
            role identifier.  Raised at registration time (factory
            invocation), not at request time.
    """
    if not roles:
        raise ValueError("require_role needs at least one role")
    role_set = frozenset(roles)
    unknown = role_set - _VALID_ROLES
    if unknown:
        raise ValueError(
            f"Unknown role(s): {sorted(unknown)} — must be one of {sorted(_VALID_ROLES)}"
        )

    def _dep(request: Request) -> None:
        """Raise :class:`AuthorizationError` unless the caller matches *roles*."""
        user = get_user(request)
        if user.get("is_admin"):
            return
        for role in role_set:
            if _check_role(role, user, request):
                return
        raise AuthorizationError(
            principal=user.get("email", ""),
            privilege=" OR ".join(sorted(role_set)),
            securable_type="system",
            full_name="role",
        )

    return _dep


def _check_role(role: str, user: UserInfo, request: Request) -> bool:
    """Map a role identifier to its boolean check.

    Internal helper for :func:`require_role`.  The ``admin`` branch is
    handled by the outer factory (early-return), so this function
    never needs to evaluate it.

    Args:
        role: One of the recognised role identifiers.
        user: The caller's :class:`UserInfo` from :func:`get_user`.
        request: Incoming FastAPI request (for api_key_* state).

    Returns:
        ``True`` when the caller satisfies *role*, ``False`` otherwise.
    """
    if role == "admin":
        return bool(user.get("is_admin"))
    if role == "supervisor":
        return bool(user.get("is_supervisor")) or getattr(
            request.state, "api_key_supervisor", False
        )
    if role == "auditor":
        return bool(user.get("is_auditor")) or getattr(request.state, "api_key_auditor", False)
    if role == "analyst":
        return (
            bool(user.get("is_auditor"))
            or getattr(request.state, "api_key_analyst", False)
            or getattr(request.state, "api_key_auditor", False)
        )
    if role == "user":
        return bool(user.get("id"))
    return False


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

    ``/api/lens/*`` routes,
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

    ``/api/2.0/sql/statements`` is the public DBX-compatible
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

    ``POST /api/lineage/openlineage`` is the inbound
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


_AUTHORING_PRODUCT_HEADER = "x-pointlessql-authoring-product"


def get_authoring_product(request: Request) -> int | None:
    """Return the data-product PK the caller is reading "in the context of".

    Resolved in order:

    1. The ``X-PointlesSQL-Authoring-Product`` header,
       ``catalog.schema`` form.  External agents (Hermes, dbt, an
       ops script) declare the consuming product explicitly so the
       D2 consumption check has something to enforce against.
    2. The ``?as_product=`` query param on the SQL-editor / notebook
       session — the in-browser flow that binds an editor tab to a
       product.
    3. ``request.state.authoring_data_product_id`` when the caller
       opened a notebook in product-context (set by the notebook
       open handler when 124's domain binding is present).

    When none of these set a value the function returns ``None`` —
    no enforcement; admin / free-form reads keep working untouched.
    The honest-split lives here: the *absence* of an authoring
    product is interpreted as "the request is not bound to a product
    contract" rather than "deny by default".

    Args:
        request: Incoming FastAPI request.

    Returns:
        The matching :class:`DataProduct` PK, or ``None`` when no
        authoring product is bound or the binding can't be resolved.
    """
    from sqlalchemy import select  # noqa: PLC0415 — lazy, dep-tree gain

    raw: str | None = None
    header = request.headers.get(_AUTHORING_PRODUCT_HEADER)
    if header and header.strip():
        raw = header.strip()
    if raw is None:
        query_value = request.query_params.get("as_product")
        if query_value and query_value.strip():
            raw = query_value.strip()
    if raw is None:
        state_value = getattr(request.state, "authoring_data_product_id", None)
        if isinstance(state_value, int) and state_value > 0:
            return state_value
        return None

    parts = raw.split(".")
    if len(parts) != 2 or not all(parts):
        return None
    catalog, schema = parts[0], parts[1]
    factory = getattr(request.app.state, "session_factory", None)
    if factory is None:
        return None
    workspace_id = current_workspace_id(request)
    with factory() as session:
        row = session.scalar(
            select(DataProduct).where(
                DataProduct.workspace_id == workspace_id,
                DataProduct.catalog_name == catalog,
                DataProduct.schema_name == schema,
            )
        )
    return int(row.id) if row is not None else None


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
    ``_templates`` helper file-by-file — it is promoted here so
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
    spelled out by hand centralised it.

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
    so non-error routes can negotiate the same way.

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


async def render_page_with_fallback(
    request: Request,
    template_name: str,
    fetch_fn: Callable[[], Awaitable[Any]],
    *,
    context_key: str,
    extra_context: dict[str, Any] | None = None,
) -> Response:
    """Render *template_name* with fetched data; surface UC outages as a banner.

    extracts the
    ``try/except CatalogUnavailableError`` + ``render template with
    error banner`` pattern repeated across federation_routes,
    catalog_html_routes, home_routes, and memory_routes.  Routes
    delegate the fetch + error handling to one place; their bodies
    shrink to ``return await render_page_with_fallback(...)``.

    Args:
        request: Incoming FastAPI request — needed for
            :func:`get_templates` and the template response builder.
        template_name: Jinja template path (e.g.
            ``"pages/connections.html"``).
        fetch_fn: Async no-arg callable that returns the data to
            inject under *context_key*.  Typical pattern is a bound
            method reference: ``client.list_connections``.
        context_key: Template variable name for the fetched data.
            Pages that do not expect a "found object" key (e.g. the
            error-banner-only page) still get an empty list under
            this key on UC outage.
        extra_context: Additional template variables merged into
            the rendered context.  ``error`` is reserved — the
            helper always injects it (``None`` on success,
            ``exc.detail`` on UC failure).

    Returns:
        :class:`Response` carrying the rendered template — populated
        data on success, empty + ``error`` banner on UC outage.
    """
    items: Any = []
    error: str | None = None
    try:
        items = await fetch_fn()
    except CatalogUnavailableError as exc:
        error = exc.detail
    context: dict[str, Any] = {context_key: items, "error": error}
    if extra_context:
        context.update(extra_context)
    return get_templates(request).TemplateResponse(request, template_name, context)
