"""Domain exception hierarchy for PointlesSQL.

Every custom exception inherits from :class:`PointlessSQLError` so that
the centralized error handlers can catch the entire family with a
single clause.  Each exception carries structured attributes that the
error handler serializes into a consistent JSON envelope.
"""

from __future__ import annotations

from typing import Any

from pointlessql.types import ErrorCode


class PointlessSQLError(Exception):
    """Base exception for all PointlesSQL domain errors.

    Attributes:
        status_code: Suggested HTTP status code for API responses.
        error_code: Machine-readable error identifier from
            :class:`ErrorCode`.

    Args:
        detail: Human-readable explanation of the error.
    """

    status_code: int = 500
    error_code: ErrorCode = ErrorCode.INTERNAL_ERROR

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)

    def extension_members(self) -> dict[str, Any] | None:
        """Return RFC 9457 extension members merged into the envelope.

        Subclasses override to surface structured context fields
        (table names, version numbers, candidate ids, …) alongside
        the standard ``status``/``code``/``detail`` triple.  Default
        ``None`` means the envelope carries only the standard fields.

        Returns:
            A dict of extension-member name → JSON-encodable value,
            or ``None`` when the exception has no structured extras.
        """
        return None


class CatalogUnavailableError(PointlessSQLError):
    """Raised when soyuz-catalog is unreachable or returns a server error.

    Attributes:
        status_code: Always 502.
        error_code: Always ``ErrorCode.CATALOG_UNAVAILABLE``.
    """

    status_code: int = 502
    error_code: ErrorCode = ErrorCode.CATALOG_UNAVAILABLE


class CatalogNotFoundError(PointlessSQLError):
    """Raised when a catalog, schema, or table is not found on soyuz-catalog.

    Attributes:
        status_code: Always 404.
        error_code: Always ``ErrorCode.CATALOG_NOT_FOUND``.
    """

    status_code: int = 404
    error_code: ErrorCode = ErrorCode.CATALOG_NOT_FOUND


class AuthenticationError(PointlessSQLError):
    """Raised when a JWT token is invalid, expired, or missing.

    Attributes:
        status_code: Always 401.
        error_code: Always ``ErrorCode.AUTHENTICATION_ERROR``.
    """

    status_code: int = 401
    error_code: ErrorCode = ErrorCode.AUTHENTICATION_ERROR


class AuthorizationError(PointlessSQLError):
    """Raised when a user lacks the required privilege on a securable.

    Attributes:
        status_code: Always 403.
        error_code: Always ``ErrorCode.AUTHORIZATION_ERROR``.

    Args:
        principal: Email of the user that was denied.
        privilege: The privilege that was required.
        securable_type: The type of securable (catalog, schema, table).
        full_name: The dotted name of the securable.
    """

    status_code: int = 403
    error_code: ErrorCode = ErrorCode.AUTHORIZATION_ERROR

    def __init__(
        self,
        principal: str,
        privilege: str,
        securable_type: str,
        full_name: str,
    ) -> None:
        self.principal = principal
        self.privilege = privilege
        self.securable_type = securable_type
        self.full_name = full_name
        detail = f"{principal} lacks {privilege} on {securable_type} '{full_name}'"
        super().__init__(detail)

    def extension_members(self) -> dict[str, Any] | None:
        """Surface privilege/securable triple as RFC 9457 extension members."""
        return {
            "required_privilege": self.privilege,
            "securable_type": self.securable_type,
            "full_name": self.full_name,
        }


class PermissionDeniedError(AuthorizationError):
    """Raised when caller has insufficient privilege without a securable to name.

    Sibling of :class:`AuthorizationError` for the call sites where
    we know the principal is denied but cannot enrich with a specific
    privilege/securable triple — for example, "auditor scope required"
    on a route guard, or a coarse admin-only check.  Skipping
    :class:`AuthorizationError`'s structured ctor keeps the
    isinstance hierarchy intact (``except AuthorizationError`` still
    catches) without forcing the caller to invent a securable.
    """

    error_code: ErrorCode = ErrorCode.PERMISSION_DENIED

    def __init__(self, detail: str = "Access denied") -> None:
        Exception.__init__(self, detail)
        self.detail = detail
        self.principal = ""
        self.privilege = ""
        self.securable_type = ""
        self.full_name = ""

    def extension_members(self) -> dict[str, Any] | None:
        """Coarse 403s carry no structured context — keep the envelope clean."""
        return None


class EngineError(PointlessSQLError):
    """Raised when a Delta Lake or compute-engine operation fails.

    Attributes:
        status_code: Always 500.
        error_code: Always ``ErrorCode.ENGINE_ERROR``.
    """

    status_code: int = 500
    error_code: ErrorCode = ErrorCode.ENGINE_ERROR


class ValidationError(PointlessSQLError, ValueError):
    """Raised for invalid input such as malformed table names.

    Inherits from both :class:`PointlessSQLError` and :class:`ValueError`
    so that existing ``except ValueError`` clauses continue to work
    during the transition period.

    Attributes:
        status_code: Always 422.
        error_code: Always ``ErrorCode.VALIDATION_ERROR``.
    """

    status_code: int = 422
    error_code: ErrorCode = ErrorCode.VALIDATION_ERROR


class SchedulerError(PointlessSQLError):
    """Raised when the job scheduler cannot persist or dispatch a run.

    Covers failures that belong to the scheduler's own plumbing —
    launching a papermill subprocess, recording a run row, applying a
    cron trigger — as opposed to the business-logic failures inside a
    notebook (those bubble up as ``NotebookRenderError`` /
    ``EngineError``).  Keeping the scheduler's own plumbing under a
    distinct code lets ops filter on ``scheduler_error`` and instantly
    know the failure was before notebook execution began.

    Attributes:
        status_code: Always 500.
        error_code: Always ``ErrorCode.SCHEDULER_ERROR``.
    """

    status_code: int = 500
    error_code: ErrorCode = ErrorCode.SCHEDULER_ERROR


class NotebookRenderError(PointlessSQLError):
    """Raised when nbconvert fails to render a completed notebook run.

    The scheduled run itself succeeded — papermill produced an
    ``.ipynb`` — but rendering that notebook to HTML for the run-detail
    page blew up (template missing, invalid output cell, etc.).
    Separating this from ``EngineError`` matters because the fix lives
    in nbconvert/Jupyter config, not in the Delta/compute path, and
    because a render failure must not mask a successful run in the
    audit trail.

    Attributes:
        status_code: Always 500.
        error_code: Always ``ErrorCode.NOTEBOOK_RENDER_ERROR``.
    """

    status_code: int = 500
    error_code: ErrorCode = ErrorCode.NOTEBOOK_RENDER_ERROR


class PQLWriteError(EngineError):
    """Raised when ``PQL.write_table`` cannot persist a DataFrame.

    Subclass of ``EngineError`` so existing catches continue to trap
    the whole engine failure family, but ``pql_write_error`` as its
    own code lets the UI distinguish "we could not write" (retriable,
    likely a schema or permission issue) from a generic read / compute
    failure.

    Attributes:
        error_code: Always ``ErrorCode.PQL_WRITE_ERROR``. ``status_code``
            inherits ``500`` from :class:`EngineError`.
    """

    error_code: ErrorCode = ErrorCode.PQL_WRITE_ERROR


class AuditUnavailableError(PointlessSQLError):
    """Raised when the forced audit trail cannot be persisted.

    PQL primitives (``autoload`` / ``merge`` / ``write_table`` /
    ``sql``) write an ``agent_run_operations`` row before touching
    DuckDB or deltalake when ``POINTLESSQL_AGENT_RUN_ID`` is set.
    If the trail insert fails (DB down, FK miss because the run id
    is unknown to the registry, table missing) the primitive
    refuses to run — a write without a trail breaks the audit
    guarantee the forced-trail contract promises.

    Attributes:
        status_code: Always 503 — the registry is part of the
            request path; without it the operation cannot be
            served safely, so a transient infrastructure problem
            is the most accurate framing.
        error_code: Always ``ErrorCode.AUDIT_UNAVAILABLE``.
    """

    status_code: int = 503
    error_code: ErrorCode = ErrorCode.AUDIT_UNAVAILABLE


class SQLExecutionError(PointlessSQLError):
    """Raised when the DuckDB execution path rejects a query.

    Covers both the parse / scope guard (``SELECT`` only, single
    statement, 3-part refs only) and DuckDB's own runtime errors
    (column not found, type mismatch, etc.).  Both are user-facing
    400s — the message is shown verbatim in the editor so the user
    can fix their query.

    Attributes:
        status_code: Always 400.
        error_code: Always ``ErrorCode.SQL_EXECUTION_ERROR``.
    """

    status_code: int = 400
    error_code: ErrorCode = ErrorCode.SQL_EXECUTION_ERROR


class ResourceNotFoundError(PointlessSQLError):
    """Raised when a non-catalog resource (run, op, subscription, ...) is missing.

    Sibling of :class:`CatalogNotFoundError` for resources that live
    in PointlesSQL's own metadata DB rather than soyuz-catalog —
    agent runs, anomaly acks, audit-sink configs, CDF subscriptions,
    and so on.  Keeping a distinct code from ``catalog_not_found``
    lets dashboards filter "operator-DB miss" vs "lakehouse miss".

    Attributes:
        status_code: Always 404.
        error_code: Always ``ErrorCode.RESOURCE_NOT_FOUND``.
    """

    status_code: int = 404
    error_code: ErrorCode = ErrorCode.RESOURCE_NOT_FOUND


class ConflictError(PointlessSQLError):
    """Raised when an operation conflicts with the current resource state.

    Examples: re-acknowledging an already-acked anomaly, registering a
    duplicate audit-sink slug, queuing a CDF subscription whose target
    table already has an active subscription.  Maps to HTTP 409 so
    clients can distinguish "you cannot do this right now" (retryable
    after a state change) from validation errors (retryable after a
    payload change).

    Attributes:
        status_code: Always 409.
        error_code: Always ``ErrorCode.CONFLICT``.
    """

    status_code: int = 409
    error_code: ErrorCode = ErrorCode.CONFLICT
