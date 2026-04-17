"""Centralized FastAPI exception handlers for PointlesSQL.

Registers handlers that dispatch JSON or HTML responses based on the
request path and the client's ``Accept`` header.  JSON API routes
(``/api/...``) always receive a structured error envelope; HTML routes
receive rendered error pages (403/404/500) on the app shell unless the
client explicitly prefers JSON.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from pointlessql.exceptions import AuthorizationError, PointlessSQLError

logger = logging.getLogger(__name__)


_STATUS_TITLES: dict[int, str] = {
    400: "Bad request",
    401: "Not signed in",
    403: "Access denied",
    404: "Page not found",
    422: "Invalid input",
    500: "Something went wrong",
    502: "Upstream catalog unavailable",
}


def _wants_json(request: Request) -> bool:
    """Return True when the caller prefers a JSON error envelope.

    ``/api/...`` paths always return JSON.  For other paths, honour an
    explicit ``Accept: application/json`` that does not also include
    ``text/html`` — browsers send ``text/html`` first, so they land on
    the HTML shell.
    """
    if request.url.path.startswith("/api/"):
        return True
    accept = request.headers.get("accept", "")
    if not accept:
        return False
    lower = accept.lower()
    return "application/json" in lower and "text/html" not in lower


def _json_envelope(
    status_code: int,
    error_code: str,
    message: str,
    request_id: str | None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": error_code,
                "message": message,
                "request_id": request_id,
            }
        },
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
    """Render a branded error page on the app shell."""
    templates: Jinja2Templates | None = getattr(
        request.app.state, "templates", None
    )
    if templates is None:
        # Templates were never mounted (e.g. unit test with a bare app).
        # Fall back to a tiny HTML stub so the caller still gets HTML.
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
        "status_title": _STATUS_TITLES.get(status_code, "Error"),
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


def register_error_handlers(app: FastAPI) -> None:
    """Register centralized exception handlers on *app*."""

    @app.exception_handler(PointlessSQLError)
    async def _handle_pointlessql_error(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: PointlessSQLError
    ) -> Response:
        request_id: str | None = getattr(request.state, "request_id", None)

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

        if _wants_json(request):
            return _json_envelope(
                exc.status_code, exc.error_code, exc.detail, request_id
            )

        extra: dict[str, Any] | None = None
        if isinstance(exc, AuthorizationError):
            extra = {
                "required_privilege": exc.privilege,
                "securable_type": exc.securable_type,
                "full_name": exc.full_name,
            }

        return _render_error_page(
            request,
            exc.status_code,
            error_code=exc.error_code,
            message=exc.detail,
            request_id=request_id,
            extra=extra,
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: StarletteHTTPException
    ) -> Response:
        request_id: str | None = getattr(request.state, "request_id", None)
        detail = str(exc.detail) if exc.detail else _STATUS_TITLES.get(
            exc.status_code, "Error"
        )
        error_code = f"http_{exc.status_code}"

        if _wants_json(request):
            return _json_envelope(
                exc.status_code, error_code, detail, request_id
            )

        return _render_error_page(
            request,
            exc.status_code,
            error_code=error_code,
            message=detail,
            request_id=request_id,
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: Exception
    ) -> Response:
        request_id: str | None = getattr(request.state, "request_id", None)
        logger.exception(
            "unhandled exception on %s %s", request.method, request.url.path
        )

        if _wants_json(request):
            return _json_envelope(
                500,
                "internal_error",
                "An unexpected error occurred.",
                request_id,
            )

        return _render_error_page(
            request,
            500,
            error_code="internal_error",
            message="An unexpected error occurred.",
            request_id=request_id,
        )
