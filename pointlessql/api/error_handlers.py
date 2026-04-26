"""Centralized FastAPI exception handlers for PointlesSQL.

Every non-OK response that the app emits flows through one of three
rendering paths: RFC 9457 ``application/problem+json`` for API clients
and JSON-preferring callers, an ``HX-Trigger`` toast header for
in-page HTMX fragment requests, and a branded HTML page for browser
navigations. All three paths share the same problem body shape so the
machine-readable ``code``, the human ``detail``, and the ``request_id``
stay identical across surfaces.

The problem envelope follows RFC 9457 (``type``/``title``/``status``/
``detail``/``code``/``request_id``); the legacy nested
``{"error": {"code", "message", "request_id"}}`` shape is no longer
emitted.
"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from pointlessql.exceptions import AuthorizationError, PointlessSQLError

logger = logging.getLogger(__name__)

PROBLEM_JSON = "application/problem+json"


_STATUS_TITLES: dict[int, str] = {
    400: "Bad request",
    401: "Not signed in",
    403: "Access denied",
    404: "Page not found",
    422: "Invalid input",
    500: "Something went wrong",
    502: "Upstream catalog unavailable",
}


def _json_safe(value: Any) -> Any:
    """Coerce a validation-error field value into a JSON-encodable shape.

    ``RequestValidationError.errors()`` can carry raw ``bytes`` in
    the ``input`` slot when a client posts a body without a JSON
    ``Content-Type`` (FastAPI then surfaces the payload verbatim).
    ``json.dumps`` doesn't know how to handle ``bytes`` and the
    response body itself would 500 — keep this helper close to the
    trigger so the failure stays self-evident if anyone touches it
    later.

    Args:
        value: Any field value harvested from
            :meth:`RequestValidationError.errors`.

    Returns:
        The value unchanged when JSON-encodable; otherwise a short
        ``repr`` (truncated to 200 chars) so the operator can still
        see what tripped the validator.
    """
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, bytes):
        try:
            return value.decode("utf-8", errors="replace")[:500]
        except Exception:  # noqa: BLE001 — fall through to repr
            pass
    if isinstance(value, dict):
        return {
            str(k): _json_safe(v)  # pyright: ignore[reportUnknownArgumentType]
            for k, v in value.items()  # pyright: ignore[reportUnknownVariableType]
        }
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]  # pyright: ignore[reportUnknownVariableType,reportUnknownArgumentType]
    return repr(value)[:200]


def _title_for_status(status_code: int) -> str:
    """Return a short human-readable title for ``status_code``.

    Falls back to :class:`http.HTTPStatus` phrase for any status that
    ``_STATUS_TITLES`` does not explicitly override, so less common
    codes (429, 504, …) still get a meaningful title.

    Args:
        status_code: HTTP status code.

    Returns:
        str: Branded title when overridden, otherwise the standard
            HTTP reason phrase, otherwise ``"Error"``.
    """
    if status_code in _STATUS_TITLES:
        return _STATUS_TITLES[status_code]
    try:
        return HTTPStatus(status_code).phrase
    except ValueError:
        return "Error"


def _wants_json(request: Request) -> bool:
    """Return True when the caller prefers a JSON problem response.

    ``/api/...`` paths always return JSON.  For other paths, honour an
    explicit ``Accept: application/json`` (or the RFC-9457 media type
    ``application/problem+json``) that does not also include
    ``text/html`` — browsers send ``text/html`` first, so they land on
    the HTML shell.
    """
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "")
    if not accept:
        return False
    lower = accept.lower()
    has_json = "application/json" in lower or "application/problem+json" in lower
    return has_json and "text/html" not in lower


def _wants_htmx_toast(request: Request) -> bool:
    """Return True when the caller is an HTMX fragment request.

    Boosted navigations (``HX-Boosted: true``) ask htmx to behave like
    a full-page load — we keep returning the branded HTML error page
    for those because the client expects to swap ``#main-content``.
    Non-boosted HTMX requests (e.g. inline edits, deferred partials)
    cannot gracefully absorb a full HTML page, so we convert the
    error into an ``HX-Trigger`` toast event instead.
    """
    if request.headers.get("HX-Request") != "true":
        return False
    return request.headers.get("HX-Boosted") != "true"


def _problem_body(
    *,
    status_code: int,
    error_code: str,
    detail: str,
    request_id: str | None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the RFC 9457 problem+json payload shared by all renderers.

    Args:
        status_code: HTTP status code that will be sent.
        error_code: Machine-readable identifier (``catalog_unavailable``,
            ``validation_error``, …). Surfaced as the ``code``
            extension member.
        detail: Human-readable explanation specific to this occurrence.
        request_id: Correlation ID stamped by the request-id
            middleware, or ``None`` if the middleware did not run.
        extra: Additional RFC 9457 extension members merged into the
            envelope (for example, ``required_privilege`` for
            :class:`AuthorizationError`).

    Returns:
        dict[str, Any]: Problem-details dict, safe to pass to
            :class:`JSONResponse`.
    """
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": _title_for_status(status_code),
        "status": status_code,
        "detail": detail,
        "code": error_code,
    }
    if request_id:
        body["request_id"] = request_id
    if extra:
        body.update(extra)
    return body


def _problem_json(
    *,
    status_code: int,
    error_code: str,
    detail: str,
    request_id: str | None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Render an RFC 9457 problem response with the ``problem+json`` media type.

    Args:
        status_code: HTTP status code to send.
        error_code: Machine-readable identifier.
        detail: Human-readable explanation.
        request_id: Correlation ID from middleware.
        extra: Extra extension members (see :func:`_problem_body`).

    Returns:
        JSONResponse: Response with ``Content-Type: application/problem+json``.
    """
    body = _problem_body(
        status_code=status_code,
        error_code=error_code,
        detail=detail,
        request_id=request_id,
        extra=extra,
    )
    return JSONResponse(status_code=status_code, content=body, media_type=PROBLEM_JSON)


def _problem_toast(
    *,
    status_code: int,
    error_code: str,
    detail: str,
    request_id: str | None,
) -> Response:
    """Render an HTMX toast trigger for a non-boosted fragment request.

    Returns an empty body with the real error status (htmx won't swap
    on 4xx/5xx by default). The ``HX-Trigger`` header carries a
    ``pqlToast`` event that the base-template listener feeds into
    ``window.pqlToast.error`` so the user sees an inline notification
    without losing the current page.

    Args:
        status_code: HTTP status code to send.
        error_code: Machine-readable identifier.
        detail: Human-readable toast body.
        request_id: Correlation ID stamped into both the ``X-Request-ID``
            response header (already set by middleware) and the toast
            payload so users can cite it in bug reports.

    Returns:
        Response: Empty body, error status, ``HX-Trigger`` populated.
    """
    trigger_payload = {
        "pqlToast": {
            "level": "error",
            "message": detail,
            "code": error_code,
            "request_id": request_id,
        }
    }
    return Response(
        status_code=status_code,
        content=b"",
        headers={"HX-Trigger": json.dumps(trigger_payload)},
    )


def _render_error_page(
    request: Request,
    status_code: int,
    *,
    error_code: str,
    message: str,
    request_id: str | None,
    extra: dict[str, Any] | None = None,
) -> HTMLResponse:
    """Render a branded error page on the app shell.

    Args:
        request: Incoming request, used to locate the templates object
            on ``app.state`` and to pass through to Jinja.
        status_code: HTTP status code (selects the template variant).
        error_code: Machine-readable identifier, surfaced on 500.html
            next to the request ID.
        message: Human-readable error message rendered into the page.
        request_id: Correlation ID surfaced on the page so users can
            cite it.
        extra: Extra template context (used by 403.html for
            ``required_privilege`` etc.).

    Returns:
        HTMLResponse: Rendered Jinja template, or a tiny HTML stub
            when templates are unavailable (bare unit-test apps).
    """
    templates: Jinja2Templates | None = getattr(request.app.state, "templates", None)
    if templates is None:
        return HTMLResponse(
            content=f"<h1>{status_code}</h1><p>{message}</p>",
            status_code=status_code,
        )

    if status_code == 404:
        template_name = "pages/404.html"
    elif status_code == 403:
        template_name = "pages/403.html"
    else:
        template_name = "pages/500.html"

    context: dict[str, Any] = {
        "status_code": status_code,
        "status_title": _title_for_status(status_code),
        "error_code": error_code,
        "message": message,
        "request_id": request_id,
        "current_user": getattr(request.state, "user", None),
        "hide_sidebar": True,
    }
    if extra:
        context.update(extra)

    return templates.TemplateResponse(
        request,
        template_name,
        context,
        status_code=status_code,
    )


def _dispatch(
    request: Request,
    *,
    status_code: int,
    error_code: str,
    detail: str,
    extra: dict[str, Any] | None = None,
) -> Response:
    """Route an error through the appropriate renderer for *request*.

    One switch point for every handler so the JSON-versus-toast-versus-
    HTML decision is never duplicated. The ordering matters: API
    callers always win (machine consumers must get problem+json even
    from a browser-ish Accept header), then HTMX fragment requests,
    then plain browser navigations.

    Args:
        request: Incoming request (drives the content-negotiation).
        status_code: HTTP status code to send.
        error_code: Machine-readable identifier.
        detail: Human-readable explanation.
        extra: Extra extension members propagated to JSON and page
            contexts alike.

    Returns:
        Response: Concrete response object for the chosen surface.
    """
    request_id: str | None = getattr(request.state, "request_id", None)

    if _wants_json(request):
        return _problem_json(
            status_code=status_code,
            error_code=error_code,
            detail=detail,
            request_id=request_id,
            extra=extra,
        )

    if _wants_htmx_toast(request):
        return _problem_toast(
            status_code=status_code,
            error_code=error_code,
            detail=detail,
            request_id=request_id,
        )

    return _render_error_page(
        request,
        status_code,
        error_code=error_code,
        message=detail,
        request_id=request_id,
        extra=extra,
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register centralized exception handlers on *app*.

    Args:
        app: The FastAPI application to register handlers on.
    """

    @app.exception_handler(PointlessSQLError)
    async def _handle_pointlessql_error(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: PointlessSQLError
    ) -> Response:
        # Authorization denials are expected traffic, not anomalies —
        # don't warn on them. Every other domain error gets a single
        # warning line so ops can grep for domain failures in one place.
        if not isinstance(exc, AuthorizationError):
            logger.warning(
                "handled domain error: %s (%s)",
                exc.error_code,
                exc.detail,
                exc_info=exc,
            )

        extra: dict[str, Any] | None = None
        if isinstance(exc, AuthorizationError):
            extra = {
                "required_privilege": exc.privilege,
                "securable_type": exc.securable_type,
                "full_name": exc.full_name,
            }

        return _dispatch(
            request,
            status_code=exc.status_code,
            error_code=exc.error_code,
            detail=exc.detail,
            extra=extra,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_request_validation_error(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: RequestValidationError
    ) -> Response:
        # FastAPI's per-field details are useful for API clients but
        # noisy in a browser toast; we forward them as a problem-body
        # extension member and let the toast show a single sentence.
        # The ``input`` field can be raw ``bytes`` when a request
        # arrives without a JSON Content-Type — coerce non-JSON-
        # safe values to a short ``repr`` so the response body
        # itself doesn't 500 (first surfaced by the live Hermes
        # ``hermes chat`` smoke run when the plugin's POST forgot
        # the Content-Type header).
        errors = [{k: _json_safe(v) for k, v in err.items() if k != "ctx"} for err in exc.errors()]
        return _dispatch(
            request,
            status_code=422,
            error_code="validation_error",
            detail="Request validation failed",
            extra={"errors": errors},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        detail = str(exc.detail) if exc.detail else _title_for_status(exc.status_code)
        error_code = f"http_{exc.status_code}"

        response = _dispatch(
            request,
            status_code=exc.status_code,
            error_code=error_code,
            detail=detail,
        )
        # Preserve any headers the caller attached to the exception
        # (e.g. ``WWW-Authenticate`` on a 401, ``Retry-After`` on a 429).
        headers = getattr(exc, "headers", None)
        if headers:
            response.headers.update(headers)
        return response

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: Exception
    ) -> Response:
        logger.exception("unhandled exception on %s %s", request.method, request.url.path)

        return _dispatch(
            request,
            status_code=500,
            error_code="internal_error",
            detail="An unexpected error occurred.",
        )
