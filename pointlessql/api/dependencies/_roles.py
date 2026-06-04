"""Role-gate request dependencies for the API layer.

Each ``require_*`` callable raises :class:`AuthorizationError` unless
the caller satisfies the relevant role or API-key scope.  The
parametrised :func:`require_role` factory generalises the single-role
gates; the two token-only gates (:func:`require_sql_execute`,
:func:`require_lineage_inbound`) stay dedicated because they target
external integrations that need narrow grants.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import Request

from pointlessql.exceptions import AuthorizationError
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.types import UserInfo

from ._principal import get_uc_client, get_user


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
