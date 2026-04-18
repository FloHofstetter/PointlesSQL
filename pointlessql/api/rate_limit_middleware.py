"""Fixed-window rate-limit middleware for the ``/auth/*`` surface.

Sprint 43 closes the credential-stuffing and registration-spam
avenues on the auth surface. Buckets live in PointlesSQL's own
Alembic DB (:class:`pointlessql.models.RateLimitEvent`) so the
limiter needs no new runtime dependency — a direct fit for the
single-node €15/month-vServer deployment target.

The middleware sits between :mod:`csrf_middleware` (outer) and
:mod:`auth_middleware` (inner) in the Starlette stack so:

* Cross-site forged floods still fail the cheap CSRF check before
  they can burn a bucket slot.
* Legitimate, CSRF-clean abuse is caught *before* ``auth_middleware``
  runs the bcrypt/JWT-decode path on every request.

Each rejection also emits an ``audit_log`` row
(``action="rate_limit.blocked"``) so Sprint 41's ``/admin/audit``
viewer surfaces the feature without a second dashboard.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from fastapi import Request
from fastapi.responses import HTMLResponse, Response

from pointlessql.services import audit as audit_service
from pointlessql.services import rate_limit as rate_limit_service


@dataclass(frozen=True)
class _Dimension:
    """One axis of a rate-limit rule (e.g. per-IP, per-email)."""

    name: str
    count: int
    window_s: int


@dataclass(frozen=True)
class _Rule:
    """A route-exact rate-limit rule with one or more dimensions.

    ``settings_tag`` is the infix used in the
    ``rate_limit_<tag>_<dim>_count`` / ``_window_s`` setting names. It
    is decoupled from ``route_tag`` so multiple routes can share one
    set of settings (the OIDC start + callback pair is one example).
    """

    method: str
    path: str
    route_tag: str
    settings_tag: str
    dimensions: tuple[str, ...]


# Route-exact matches so adding a new auth endpoint is a deliberate
# edit rather than an implicit inclusion via prefix. ``auth.oidc``
# is shared between ``/auth/sso`` and ``/auth/callback`` because they
# are two halves of the same OIDC flow — flooding one is flooding the
# other, and a unified budget keeps the settings surface small.
_RULES: tuple[_Rule, ...] = (
    _Rule("POST", "/auth/login", "auth.login", "login", ("ip", "email")),
    _Rule("POST", "/auth/register", "auth.register", "register", ("ip",)),
    _Rule("GET", "/auth/sso", "auth.oidc", "oidc", ("ip",)),
    _Rule("GET", "/auth/callback", "auth.oidc", "oidc", ("ip",)),
)

_FORM_CONTENT_TYPES = ("application/x-www-form-urlencoded", "multipart/form-data")


def _client_ip(request: Request, trust_xff: bool) -> str:
    """Return the remote address the middleware should bucket on.

    Defaults to the direct socket peer (``request.client.host``).
    When ``trust_xff`` is ``True`` and an ``X-Forwarded-For`` header
    is present, the leftmost hop wins — that is the value the
    terminating reverse proxy wrote, assumed authoritative.
    """
    if trust_xff:
        xff = request.headers.get("x-forwarded-for")
        if xff:
            first = xff.split(",", 1)[0].strip()
            if first:
                return first
    client = request.client
    if client is None:
        return "unknown"
    return client.host


async def _submitted_email(request: Request) -> str | None:
    """Return the ``email`` form field from a login/register POST.

    The body is read once and re-installed on ``request._receive`` so
    the downstream FastAPI ``Form(...)`` dependency still parses the
    same payload. This is the same trick
    :mod:`csrf_middleware` uses.

    Returns ``None`` when the request is not form-encoded or the
    field is missing — callers must tolerate a missing email bucket
    and still apply the per-IP one.
    """
    content_type = request.headers.get("content-type", "")
    if not any(content_type.startswith(ct) for ct in _FORM_CONTENT_TYPES):
        return None

    body = await request.body()

    async def _receive() -> dict[str, Any]:
        return {"type": "http.request", "body": body, "more_body": False}

    request._receive = _receive  # pyright: ignore[reportPrivateUsage]

    form = await request.form()
    value = form.get("email")
    return value.strip().lower() if isinstance(value, str) and value.strip() else None


def _resolve_dimensions(rule: _Rule, settings: Any) -> list[_Dimension]:
    """Read dimension counts + windows off the settings object.

    Kept as a small lookup so new rules can refer to existing
    dimensions without hard-coding setting names in the middleware
    body. Returns an empty list (i.e. "no enforcement") if a
    dimension's setting is zero or negative, letting operators
    soft-disable a specific bucket without patching code.
    """
    out: list[_Dimension] = []
    rate_limit_cfg = settings.rate_limit
    for name in rule.dimensions:
        count = int(getattr(rate_limit_cfg, f"{rule.settings_tag}_{name}_count"))
        window = int(getattr(rate_limit_cfg, f"{rule.settings_tag}_{name}_window_s"))
        if count > 0 and window > 0:
            out.append(_Dimension(name=name, count=count, window_s=window))
    return out


def _render_429(retry_after: int) -> HTMLResponse:
    """Return the 429 HTML response used for every reject.

    Matches Sprint 42's CSRF-reject shape (bare ``HTMLResponse``, no
    templating) so operators see a consistent error surface across
    hardening layers.
    """
    body = (
        "<h1>429 — Too many attempts</h1>"
        f"<p>Please wait {retry_after} seconds before trying again.</p>"
    )
    response = HTMLResponse(body, status_code=429)
    response.headers["Retry-After"] = str(retry_after)
    return response


def _find_rule(request: Request) -> _Rule | None:
    """Return the matching rule for this request, or ``None``."""
    method = request.method.upper()
    path = request.url.path
    for rule in _RULES:
        if rule.method == method and rule.path == path:
            return rule
    return None


async def rate_limit_middleware(request: Request, call_next: Any) -> Response:
    """Apply per-route rate-limit rules before reaching the auth layer.

    Args:
        request: Incoming Starlette request.
        call_next: Downstream handler.

    Returns:
        Response: The downstream response when under the limit, or a
        429 :class:`HTMLResponse` with a ``Retry-After`` header when
        any dimension's bucket is full.
    """
    settings = getattr(request.app.state, "settings", None)
    factory = getattr(request.app.state, "session_factory", None)
    if settings is None or factory is None:
        return await call_next(request)
    rate_limit_cfg = getattr(settings, "rate_limit", None)
    if rate_limit_cfg is None or not getattr(rate_limit_cfg, "enabled", True):
        return await call_next(request)

    rule = _find_rule(request)
    if rule is None:
        return await call_next(request)

    dims = _resolve_dimensions(rule, settings)
    if not dims:
        return await call_next(request)

    trust_xff = bool(getattr(rate_limit_cfg, "trust_x_forwarded_for", False))
    ip = _client_ip(request, trust_xff)

    # Look up the submitted email once — only needed when a rule
    # declares the ``email`` dimension, and only for form POSTs.
    email: str | None = None
    if "email" in rule.dimensions:
        email = await _submitted_email(request)

    for dim in dims:
        if dim.name == "ip":
            identity = ip
        elif dim.name == "email":
            if email is None:
                # No email in the body → nothing to bucket on. The
                # per-IP dimension still applies, so we skip this one
                # rather than fabricate a key.
                continue
            identity = email
        else:  # pragma: no cover — defensive, unreachable today
            continue

        bucket = rate_limit_service.bucket_for(rule.route_tag, dim.name, identity)
        allowed, retry_after = rate_limit_service.check_and_record(
            factory, bucket, dim.count, dim.window_s
        )
        if not allowed:
            # user_id=0 + user_email="anon" keeps the audit row
            # non-null-constrained without pretending an anonymous
            # attacker maps to a real account. The identifying detail
            # lives in ``target`` (the bucket string) which the admin
            # viewer already renders verbatim.
            # Async write (Sprint 48) — the reject path is hot and
            # we do not want the audit INSERT to block the 429.
            await asyncio.to_thread(
                audit_service.log_action,
                factory,
                0,  # user_id=0 keeps the audit row non-null-constrained
                "anon",
                "rate_limit.blocked",
                bucket,
                None,
                actor_role="system",
                client_ip=ip,
            )
            return _render_429(retry_after)

    return await call_next(request)
