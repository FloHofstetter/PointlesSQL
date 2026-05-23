"""HTTP middleware registration for the FastAPI app.

Centralises the four middleware the app stacks on every request —
auth, rate-limit, CSRF, request-id — into one
:func:`register_middleware` call so callers cannot accidentally
re-order them.

Order is **load-bearing**.  Starlette stacks middleware LIFO:
last-added runs first (outermost) on the incoming request.  This
function adds in the following order so the execution chain on an
incoming request becomes::

    request_id → csrf → rate_limit → auth → handler

* ``auth`` resolves the user from the JWT cookie before any handler.
* ``rate_limit`` runs INSIDE csrf (a CSRF-failed flood must not burn
  bucket slots) and OUTSIDE auth (a flood must not bcrypt-hash the
  payload before being throttled).
* ``csrf`` runs OUTSIDE auth so a CSRF failure short-circuits before
  bcrypt + JWT-decode.
* ``request_id`` is the outermost so the X-Request-ID echo + the
  contextvar reach into every other middleware's log lines.
"""

from __future__ import annotations

import logging
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse, Response

from pointlessql.api.csrf_middleware import csrf_middleware as _csrf_middleware
from pointlessql.api.rate_limit_middleware import (
    rate_limit_middleware as _rate_limit_middleware,
)
from pointlessql.config import request_id_var
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import auth as auth_service
from pointlessql.services.workspace import _crud as workspaces_service
from pointlessql.types import UserInfo

#: Header carrying the active workspace slug for non-cookie callers
#: (Hermes plugin, ops curl, CI scripts).  See
#: :func:`pointlessql.services.workspace._crud.resolve_workspace_id` for
#: precedence rules.
WORKSPACE_HEADER: str = "x-workspace"

#: Cookie name carrying the user's last-selected workspace slug.
#: Written by ``POST /auth/switch-workspace`` and read by
#: :func:`_read_workspace_slug_from_session` so the
#: workspace persists across page navigations without a JWT
#: re-encode hop.  Kept as a sibling of ``pql_session`` rather
#: than embedded in the JWT payload because the slug changes more
#: frequently than auth state and we do not want to invalidate the
#: session on every switch.
WORKSPACE_COOKIE_NAME: str = "pql_workspace"
WORKSPACE_COOKIE_FIELD: str = "current_workspace_slug"

logger = logging.getLogger(__name__)


# Paths that do not require authentication.
# ``/alerts/feed.atom`` + ``/alerts/feed.json`` authenticate via the
# opaque ``?token=…`` query-string, not the session cookie — feed
# readers (Miniflux, FreshRSS, …) do not have a browser session.
# They are listed here so the session auth_middleware does not
# redirect them to ``/auth/login``; the route handlers themselves
# reject unknown tokens with 401.
PUBLIC_PREFIXES: tuple[str, ...] = (
    "/auth/",
    "/static/",
    "/healthz",
    "/alerts/feed.atom",
    "/alerts/feed.json",
    # Phase 51.4: inbound webhook receiver.  Authentication is the
    # HMAC-SHA-256 signature on the body verified inside the route
    # handler; the path itself is unauthenticated so external git
    # hosts can call it without an API key.
    "/webhook/git/",
    # Phase 65.4: Lens MCP transport.  Authentication is a Bearer
    # API key with the analyst (or auditor) scope, validated inside
    # the routes themselves.  Letting the auth middleware redirect
    # /mcp/* to /auth/login would break IDE consumers (Claude
    # Desktop, Cursor) that never see an HTTP redirect.
    "/mcp/",
    # Phase 100: notebook share viewer.  Public-by-design surface;
    # the share_uuid IS the credential.  Revoked / expired shares
    # return 410 from the route itself — letting the auth middleware
    # redirect to /auth/login would break the whole publish flow.
    "/share/",
    # Phase 100 Wave-D: iframe-embed mirror of the share viewer.
    # Same auth-by-uuid contract as /share/; lives under /embed/
    # so external doc embeds can frame it like Phase-92.2's
    # /embed/semantic_search/{fqn}.
    "/embed/notebook_share/",
)


async def auth_middleware(request: Request, call_next: Any) -> Response:
    """Resolve a principal from cookie OR Bearer key; gate protected paths.

    Bearer-token verification goes through
    :func:`pointlessql.services.api_keys.verify_bearer`, which
    consults the ``api_keys`` DB table (with a 60s in-memory TTL
    cache).  On match a synthetic :class:`UserInfo` is attached so
    downstream routes (which only ever read ``request.state.user``)
    need no awareness of the alternate auth path;
    ``request.state.api_key_name`` keeps the audit attribution and
    ``request.state.api_key_supervisor`` exposes the supervisor
    scope flag for ``require_supervisor``;
    ``request.state.api_key_auditor`` exposes the
    auditor scope flag for ``require_auditor``.

    Cookie auth still wins when both are present so a human in a
    browser keeps their identity even if a misconfigured proxy
    forwards a Bearer header.
    """
    path = request.url.path

    # Always try to resolve user from cookie (even on public paths,
    # so templates can show the navbar user menu).
    token = request.cookies.get(auth_service.COOKIE_NAME)
    if token is not None:
        factory = getattr(request.app.state, "session_factory", None)
        settings = getattr(request.app.state, "settings", None)
        if factory is not None and settings is not None:
            user = auth_service.get_current_user(
                factory,
                token,
                settings.auth.secret_key,
                previous_key=settings.auth.secret_key_previous,
            )
            if user is not None:
                request.state.user = user

    # Fall back to API-key bearer token when no cookie user resolved.
    # The store is DB-backed (``api_keys`` table); the env-var path
    # remains valid as a bootstrap spilled in by
    # :func:`api_keys_service.bootstrap_from_env` at startup.  Cache
    # TTL inside :func:`verify_bearer` keeps the hot path off the DB
    # except on miss.
    api_key_workspace_id: int | None = None
    if getattr(request.state, "user", None) is None:
        factory = getattr(request.app.state, "session_factory", None)
        entry = api_keys_service.verify_bearer(
            request.headers.get("authorization"),
            factory,
        )
        if entry is not None:
            # Phase 120 — IP allowlist gate.  Runs before any state is
            # attached so a denied request looks indistinguishable from
            # an unauthenticated one + emits a distinct audit row.
            settings_for_acl = getattr(request.app.state, "settings", None)
            enforce_ip = (
                settings_for_acl is not None
                and getattr(settings_for_acl, "api_key_acl", None) is not None
                and bool(settings_for_acl.api_key_acl.enforce_ip_grants)
            )
            if enforce_ip and factory is not None:
                from pointlessql.api.rate_limit_middleware import (
                    _client_ip,  # pyright: ignore[reportPrivateUsage]
                )
                from pointlessql.services.api_keys._acl import (
                    check_ip_allowed,
                    load_ip_grants_for,
                )

                ip_grants = load_ip_grants_for(factory, api_key_id=entry.id)
                rl_settings = getattr(settings_for_acl, "rate_limit", None)
                trust_xff = bool(
                    getattr(rl_settings, "trust_x_forwarded_for", False)
                )
                source_ip = _client_ip(request, trust_xff)
                if not check_ip_allowed(ip_grants, source_ip):
                    _emit_ip_denied_audit(factory, entry, source_ip)
                    return JSONResponse(
                        status_code=403,
                        content={
                            "error_code": "IP_NOT_ALLOWED",
                            "message": (
                                f"source IP {source_ip!r} is not in the allowlist for this key"
                            ),
                        },
                    )
            request.state.api_key_name = entry.name
            request.state.api_key_supervisor = entry.supervisor
            request.state.api_key_auditor = entry.auditor
            request.state.api_key_lineage_inbound = entry.lineage_inbound
            request.state.api_key_analyst = entry.analyst
            request.state.api_key_sql_execute = entry.sql_execute
            request.state.api_key_id = entry.id
            request.state.api_key_workspace_id = entry.workspace_id
            api_key_workspace_id = entry.workspace_id
            request.state.user = UserInfo(
                id=0,
                email=f"api_key:{entry.name}",
                display_name=entry.name,
                is_admin=False,
                is_supervisor=entry.supervisor,
                is_auditor=entry.auditor,
            )
            # Phase 120 — record this successful auth into the
            # in-process usage buffer.  Flush is the background
            # ``_api_key_usage_flush_loop``.
            try:
                from pointlessql.api.rate_limit_middleware import (
                    _client_ip,  # pyright: ignore[reportPrivateUsage]
                )
                from pointlessql.services.api_keys._usage import record_use

                rl_settings = getattr(settings_for_acl, "rate_limit", None)
                trust_xff = bool(getattr(rl_settings, "trust_x_forwarded_for", False))
                record_use(
                    request.app.state,
                    api_key_id=entry.id,
                    source_ip=_client_ip(request, trust_xff),
                )
            except Exception:  # noqa: BLE001 — usage logging is non-critical
                logger.debug("Failed to record api-key usage", exc_info=True)

    # Resolve the active workspace for the request.  The resolver
    # tolerates every absence (no factory, no user, no header, fresh
    # install) and floors at the seeded ``default`` workspace (id=1)
    # so the request pipeline never observes a missing workspace.
    # Membership enforcement happens *after* the resolution so we can
    # write a meaningful audit-log row when an authenticated user
    # names a workspace they don't belong to.
    factory = getattr(request.app.state, "session_factory", None)
    user_state = getattr(request.state, "user", None)
    user_id_for_resolve = (
        int(user_state["id"])
        if user_state is not None and isinstance(user_state.get("id"), int) and user_state["id"] > 0
        else None
    )
    header_value = request.headers.get(WORKSPACE_HEADER)
    cookie_value = _read_workspace_slug_from_session(request)
    workspace_id, workspace_source = workspaces_service.resolve_workspace_id(
        factory,
        user_id=user_id_for_resolve,
        header_value=header_value,
        cookie_value=cookie_value,
        api_key_workspace_id=api_key_workspace_id,
    )
    request.state.workspace_id = workspace_id
    request.state.workspace_source = workspace_source

    # Mismatch enforcement: an explicit X-Workspace header for a
    # workspace the authenticated user is NOT a member of is a
    # 403, audit-logged with ``workspace.context_mismatch`` so the
    # cross-workspace probe is observable in the cockpit.  The
    # check skips when there is no factory (lifespan not wired) or
    # no header (fall-through path is already safe).  API-key-only
    # callers are gated by ``api_key_workspace_id`` matching the
    # header-resolved id — the pin IS the membership for Bearer
    # auth.
    if (
        header_value
        and header_value.strip()
        and factory is not None
        and workspace_source == "header"
    ):
        if api_key_workspace_id is not None:
            if workspace_id != api_key_workspace_id:
                _audit_workspace_mismatch(
                    factory,
                    actor=user_state,
                    requested_slug=header_value.strip(),
                    resolved_id=workspace_id,
                    api_key_workspace_id=api_key_workspace_id,
                )
                return _workspace_forbidden(path)
        elif user_id_for_resolve is not None and not workspaces_service.is_member(
            factory, workspace_id=workspace_id, user_id=user_id_for_resolve
        ):
            _audit_workspace_mismatch(
                factory,
                actor=user_state,
                requested_slug=header_value.strip(),
                resolved_id=workspace_id,
                api_key_workspace_id=None,
            )
            return _workspace_forbidden(path)

    # Public paths pass through regardless of auth.
    if any(path.startswith(p) for p in PUBLIC_PREFIXES):
        return await call_next(request)

    # Protected paths require authentication.
    if getattr(request.state, "user", None) is not None:
        return await call_next(request)

    # Unauthenticated — redirect HTML requests, 401 for API.
    if path.startswith("/api/"):
        return JSONResponse({"error": "Not authenticated"}, status_code=401)
    return RedirectResponse(url="/auth/login", status_code=303)


def _read_workspace_slug_from_session(request: Request) -> str | None:
    """Return the slug stashed in the ``pql_workspace`` cookie, if any.

    Written by ``POST /auth/switch-workspace`` on every successful
    workspace switch.  An invalid slug is tolerated upstream — the
    resolver falls through to the user-default tier rather than
    raising.
    """
    raw = request.cookies.get(WORKSPACE_COOKIE_NAME)
    if not raw:
        return None
    cleaned = raw.strip()
    return cleaned or None


def _emit_ip_denied_audit(factory: Any, entry: Any, source_ip: str) -> None:
    """Audit a 403 IP_NOT_ALLOWED rejection.  Best-effort; swallows failures."""
    try:
        from pointlessql.services.audit import _core as audit_core

        audit_core.log_action(
            factory,
            user_id=0,
            user_email=f"api_key:{entry.name}",
            action="api_key.access_denied.ip",
            target=f"api_key:{entry.name}",
            detail={"source_ip": source_ip, "key_name": entry.name},
            actor_role="system",
            client_ip=source_ip,
            workspace_id=int(entry.workspace_id),
        )
    except Exception:  # noqa: BLE001 — audit must never break auth
        logger.debug(
            "Failed to emit api_key.access_denied.ip audit for %s", entry.name, exc_info=True
        )


def _workspace_forbidden(path: str) -> Response:
    """Return a 403 in the right format for the request's path family."""
    if path.startswith("/api/"):
        return JSONResponse({"error": "workspace.context_mismatch"}, status_code=403)
    return JSONResponse(
        {"error": "workspace.context_mismatch"},
        status_code=403,
    )


def _audit_workspace_mismatch(
    factory: Any,
    *,
    actor: UserInfo | None,
    requested_slug: str,
    resolved_id: int,
    api_key_workspace_id: int | None,
) -> None:
    """Record a single ``workspace.context_mismatch`` audit row.

    Wraps the audit-log INSERT in a try/except because the audit
    surface is non-critical to the auth gate — a swallowed audit
    write is preferable to a 500 from the middleware itself.
    """
    try:
        from pointlessql.services import audit as audit_service

        actor_id = int(actor["id"]) if actor and "id" in actor else 0
        actor_email = actor.get("email", "") if actor else ""
        audit_service.log_action(
            factory,
            actor_id,
            actor_email,
            "workspace.context_mismatch",
            f"workspace:{requested_slug}",
            detail={
                "requested_slug": requested_slug,
                "resolved_workspace_id": resolved_id,
                "api_key_workspace_id": api_key_workspace_id,
            },
            actor_role="system",
        )
    except Exception:  # noqa: BLE001 — auditing must never break auth
        logger.debug(
            "Failed to write workspace.context_mismatch audit row",
            exc_info=True,
        )


async def request_id_middleware(request: Request, call_next: Any) -> Response:
    """Attach a unique request ID to every request and echo it in the response.

    The ID is stored both on ``request.state`` (for the error handler)
    and in the ``request_id_var`` contextvar (so service-layer log
    records emitted during this request pick it up via the
    ``RequestIdFilter``). The contextvar is reset in ``finally`` so
    concurrent requests never leak IDs into each other's scope.
    """
    request_id = request.headers.get("X-Request-ID") or str(uuid4())
    request.state.request_id = request_id
    token = request_id_var.set(request_id)
    try:
        response = await call_next(request)
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    return response


def register_middleware(app: FastAPI) -> None:
    """Stack all four middleware on *app* in the canonical order.

    See module docstring for the LIFO reasoning behind the call
    sequence below.  Calling this once during app construction
    replaces the scattered ``@app.middleware("http")`` decorators
    that previously lived in ``api/main.py``.

    Args:
        app: The FastAPI app to attach middleware to.
    """
    app.middleware("http")(auth_middleware)
    app.middleware("http")(_rate_limit_middleware)
    app.middleware("http")(_csrf_middleware)
    app.middleware("http")(request_id_middleware)
