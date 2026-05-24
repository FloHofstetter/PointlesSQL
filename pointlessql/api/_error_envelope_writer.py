"""Write RFC 9457 problem responses from middleware-level code paths.

FastAPI's ``exception_handler`` registrations do not fire for
exceptions raised inside middleware once the response cycle has
started — middleware therefore cannot share the route-layer's
``PointlessSQLError → handler`` dispatch.  This module packages the
same RFC 9457 envelope body that :mod:`pointlessql.api.error_handlers`
builds for routes into a :class:`JSONResponse` middleware can return
directly, preserving the synchronous audit-write ordering those
sites require (audit row INSERT must complete before the response
goes on the wire).
"""

from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse

from pointlessql.api.error_handlers import (
    PROBLEM_JSON,
    _problem_body,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.types import ErrorCode


def problem_response(
    request: Request,
    *,
    status_code: int,
    error_code: str | ErrorCode,
    detail: str,
    extra: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Return an RFC 9457 ``application/problem+json`` :class:`JSONResponse`.

    Args:
        request: Incoming request — used to look up the correlation
            ID stamped on ``request.state.request_id`` by the
            request-id middleware.  ``None`` is tolerated and simply
            omits the ``request_id`` member.
        status_code: HTTP status to send.
        error_code: ErrorCode member or stable string identifier
            surfaced as the ``code`` extension member.
        detail: Human-readable explanation.
        extra: Extension members merged into the envelope (for
            example ``{"source_ip": "203.0.113.1"}``).
        headers: Optional response headers (``Retry-After``,
            ``WWW-Authenticate``, …).

    Returns:
        JSONResponse: Body shaped exactly like the route-layer's
            problem+json envelope so machine consumers parse both
            surfaces identically.
    """
    request_id: str | None = getattr(request.state, "request_id", None)
    body = _problem_body(
        status_code=status_code,
        error_code=error_code,
        detail=detail,
        request_id=request_id,
        extra=extra,
    )
    return JSONResponse(
        status_code=status_code,
        content=body,
        media_type=PROBLEM_JSON,
        headers=headers,
    )
