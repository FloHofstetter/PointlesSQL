"""Pydantic models describing the RFC 9457 problem-envelope shape.

Used in two places:

1. Routes that opt into typed error responses can declare them via
   ``responses=STANDARD_ERROR_RESPONSES`` (see
   :mod:`pointlessql.api.error_responses`) so the OpenAPI schema
   exposes the envelope to client-side codegen.
2. Tests that inspect ``/openapi.json`` use these classes as the
   contract reference.

The envelope itself is built by
:func:`pointlessql.api.error_handlers._problem_body` at runtime; the
Pydantic models are *descriptive* — never instantiated server-side.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from pointlessql.types import ErrorCode


class ErrorEnvelope(BaseModel):
    """RFC 9457 problem-envelope as returned by the centralised handler.

    Mirrors the shape produced by
    :func:`pointlessql.api.error_handlers._problem_body`.  Extension
    members beyond the listed fields are permitted (the model uses
    ``extra='allow'``) so endpoint-specific extras like
    ``required_privilege`` (AuthorizationError) or ``table_name``
    (BranchPromotionConflictError) ride along without per-route
    bespoke models.
    """

    model_config = ConfigDict(extra="allow")

    type: str = Field(
        default="about:blank",
        description="RFC 9457 problem type URI; ``about:blank`` for our envelope.",
    )
    title: str = Field(
        ...,
        description="Short human-readable title (e.g. ``Invalid input``).",
    )
    status: int = Field(
        ...,
        description="HTTP status code, mirrored from the response.",
    )
    detail: str = Field(
        ...,
        description="Human-readable explanation of the failure.",
    )
    code: ErrorCode | str = Field(
        ...,
        description=(
            "Machine-readable identifier from "
            ":class:`pointlessql.error_codes.ErrorCode`.  Falls back "
            "to ``http_NNN`` for unconverted residuals."
        ),
    )
    request_id: str | None = Field(
        default=None,
        description="Correlation ID stamped by the request-id middleware.",
    )


class AuthorizationErrorEnvelope(ErrorEnvelope):
    """Envelope for 403 ``authorization_error`` with structured context."""

    required_privilege: str = Field(
        ...,
        description="Privilege the caller would need (e.g. ``SELECT``).",
    )
    securable_type: str = Field(
        ...,
        description="Type of securable (``catalog``/``schema``/``table``).",
    )
    full_name: str = Field(
        ...,
        description="Dotted name of the securable that was denied.",
    )


class ValidationErrorEnvelope(ErrorEnvelope):
    """Envelope for 422 ``validation_error`` from FastAPI request validation.

    The ``errors`` extension carries the per-field validation
    breakdown produced by :class:`fastapi.exceptions.RequestValidationError`.
    """

    errors: list[dict[str, Any]] = Field(
        default_factory=list[dict[str, Any]],
        description="Per-field validation errors (``loc``/``msg``/``type``).",
    )


class RollbackStaleEnvelope(ErrorEnvelope):
    """Envelope for 409 ``rollback_stale`` with version-triple context."""

    current_version: int = Field(
        ...,
        description="``DeltaTable.version()`` at the staleness check.",
    )
    expected_version: int = Field(
        ...,
        description="The targeted op's ``delta_version_after``.",
    )
    intervening_op_count: int = Field(
        ...,
        description="Count of agent_run_operations rows past the target.",
    )


class BranchPromotionConflictEnvelope(ErrorEnvelope):
    """Envelope for 409 ``branch_promotion_conflict``."""

    table_name: str = Field(
        ...,
        description="Two-part schema.table that detected a moved parent.",
    )
    expected_version: int = Field(
        ...,
        description="Recorded version at branch creation time.",
    )
    actual_version: int = Field(
        ...,
        description="Current version at promotion time.",
    )
