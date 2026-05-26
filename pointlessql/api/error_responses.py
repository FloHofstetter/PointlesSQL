"""Convenience constants for declaring error responses on FastAPI routes.

Routes opt into the OpenAPI-visible error contract by passing
``responses=STANDARD_ERROR_RESPONSES`` (or one of the more specific
constants) to ``@router.get()`` / ``@router.post()``.  Plugin-facing
routes apply this selectively today; the other routes keep their
default OpenAPI rendering until a follow-up sweep.
"""

from __future__ import annotations

from typing import Any

from pointlessql.api.error_envelope import (
    AuthorizationErrorEnvelope,
    ErrorEnvelope,
    ValidationErrorEnvelope,
)

#: Status-keyed responses for the four most-common error shapes.
#:
#: Use as ``@router.get("...", responses=STANDARD_ERROR_RESPONSES)``.
#: 403 maps to :class:`AuthorizationErrorEnvelope` so the structured
#: ``required_privilege`` extension is exposed in the schema.
STANDARD_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {
        "model": ErrorEnvelope,
        "description": "Bad request (sql_execution_error or similar)",
    },
    401: {
        "model": ErrorEnvelope,
        "description": "Unauthenticated",
    },
    403: {
        "model": AuthorizationErrorEnvelope,
        "description": "Forbidden (insufficient privilege)",
    },
    404: {
        "model": ErrorEnvelope,
        "description": "Resource not found",
    },
    409: {
        "model": ErrorEnvelope,
        "description": "Conflict with current state",
    },
    422: {
        "model": ValidationErrorEnvelope,
        "description": "Request validation failed",
    },
    500: {
        "model": ErrorEnvelope,
        "description": "Internal error",
    },
    502: {
        "model": ErrorEnvelope,
        "description": "Upstream catalog unavailable",
    },
    503: {
        "model": ErrorEnvelope,
        "description": "Service unavailable (audit/scheduler/subprocess)",
    },
}
