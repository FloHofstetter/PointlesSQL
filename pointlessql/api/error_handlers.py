"""Centralized FastAPI exception handlers for PointlesSQL.

Registers a single handler for :class:`~pointlessql.exceptions.PointlessSQLError`
that dispatches JSON or HTML responses based on the request path.  JSON API
routes (``/api/...``) receive a structured error envelope; HTML routes receive
rendered error pages.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from pointlessql.exceptions import AuthorizationError, PointlessSQLError

logger = logging.getLogger(__name__)


def register_error_handlers(app: FastAPI) -> None:
    """Register centralized exception handlers on *app*."""

    @app.exception_handler(PointlessSQLError)
    async def _handle_pointlessql_error(  # pyright: ignore[reportUnusedFunction]
        request: Request, exc: PointlessSQLError
    ) -> JSONResponse | HTMLResponse:
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

        # JSON API routes get a structured envelope.
        if request.url.path.startswith("/api/"):
            return JSONResponse(
                status_code=exc.status_code,
                content={
                    "error": {
                        "code": exc.error_code,
                        "message": exc.detail,
                        "request_id": request_id,
                    }
                },
            )

        # HTML authorization errors → 403 page.
        if isinstance(exc, AuthorizationError):
            templates: Jinja2Templates = request.app.state.templates
            return templates.TemplateResponse(
                request,
                "pages/403.html",
                {
                    "required_privilege": exc.privilege,
                    "securable_type": exc.securable_type,
                    "full_name": exc.full_name,
                    "current_user": getattr(request.state, "user", None),
                },
                status_code=403,
            )

        # Fallback for other domain errors on HTML paths.
        return HTMLResponse(
            content=f"<h1>{exc.status_code}</h1><p>{exc.detail}</p>",
            status_code=exc.status_code,
        )
