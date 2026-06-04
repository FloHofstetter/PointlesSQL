"""Databricks-compatible JSON error envelope for token-only API routes.

The ``/api/2.0/sql/statements`` surface returns errors in
the documented Databricks Statement Execution API wire shape so the
official ``databricks-sql-python`` client, ``dbt-databricks``, and
JDBC drivers parse them identically to the upstream service.  The
envelope is **not** RFC 9457 — it is a deliberate variant kept
distinct from the in-house ``application/problem+json`` shape so
external SQL clients don't have to special-case PointlesSQL.

The three symbols below were promoted out of
``api/external_sql_routes.py`` so other token-only
DBX-compatible endpoints (federation, future admin SQL surfaces)
can reuse them without circular imports.  ``external_sql_routes``
re-exports them for backwards compatibility with the test suite that imports via the old path.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from fastapi.responses import JSONResponse


class DbxApiError(Exception):
    """Raised inside route helpers to short-circuit with a DBX-shape JSON.

    The global FastAPI exception handler stringifies
    :class:`starlette.exceptions.HTTPException`'s ``detail`` field,
    which would mangle a dict-typed JSON envelope.  Routes catch
    this locally via :func:`wrap_dbx` and turn it into a
    :class:`JSONResponse` with the headers preserved.

    Args:
        status_code: HTTP status code to send.
        body: Dict carrying ``error_code`` + ``message`` (+ optional
            ``details``) — the exact Databricks envelope shape.
        headers: Optional response headers (``Retry-After`` for 429,
            ``Location`` for 303, …).
    """

    def __init__(
        self,
        status_code: int,
        body: dict[str, Any],
        *,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(body.get("message") or f"DbxApiError {status_code}")
        self.status_code = status_code
        self.body = body
        self.headers = headers or {}


def dbx_error_response(exc: DbxApiError) -> JSONResponse:
    """Convert a :class:`DbxApiError` into a Databricks-shape JSONResponse.

    Args:
        exc: Short-circuit exception raised inside a route handler.

    Returns:
        JSONResponse: Body ``{"detail": <DBX body>}``, headers
        forwarded from the exception.
    """
    return JSONResponse(
        {"detail": exc.body},
        status_code=exc.status_code,
        headers=exc.headers,
    )


def wrap_dbx(
    handler: Callable[..., Awaitable[JSONResponse]],
) -> Callable[..., Awaitable[JSONResponse]]:
    """Decorate a route handler so ``DbxApiError`` ships JSON directly.

    Without this wrapper, raising :class:`DbxApiError` from a route
    would land in the global FastAPI exception handler, which would
    coerce the dict body to a string and break the wire contract.

    Args:
        handler: Async route function returning :class:`JSONResponse`.

    Returns:
        Wrapped coroutine that catches :class:`DbxApiError` and
        converts it via :func:`dbx_error_response`.
    """

    @wraps(handler)
    async def _wrapped(*args: Any, **kwargs: Any) -> JSONResponse:
        try:
            return await handler(*args, **kwargs)
        except DbxApiError as exc:
            return dbx_error_response(exc)

    return _wrapped
