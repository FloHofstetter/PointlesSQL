"""Domain exception hierarchy for PointlesSQL.

Every custom exception inherits from :class:`PointlessSQLError` so that
centralized error handlers (Sprint 14) can catch the entire family with
a single clause.  Each exception carries structured attributes that the
error handler serializes into a consistent JSON envelope.
"""

from __future__ import annotations


class PointlessSQLError(Exception):
    """Base exception for all PointlesSQL domain errors.

    Attributes:
        status_code: Suggested HTTP status code for API responses.
        error_code: Machine-readable error identifier (e.g.
            ``"catalog_unavailable"``).

    Args:
        detail: Human-readable explanation of the error.
    """

    status_code: int = 500
    error_code: str = "internal_error"

    def __init__(self, detail: str) -> None:
        self.detail = detail
        super().__init__(detail)


class CatalogUnavailableError(PointlessSQLError):
    """Raised when soyuz-catalog is unreachable or returns a server error.

    Attributes:
        status_code: Always 502.
        error_code: Always ``"catalog_unavailable"``.
    """

    status_code: int = 502
    error_code: str = "catalog_unavailable"


class CatalogNotFoundError(PointlessSQLError):
    """Raised when a catalog, schema, or table is not found on soyuz-catalog.

    Attributes:
        status_code: Always 404.
        error_code: Always ``"catalog_not_found"``.
    """

    status_code: int = 404
    error_code: str = "catalog_not_found"


class AuthenticationError(PointlessSQLError):
    """Raised when a JWT token is invalid, expired, or missing.

    Attributes:
        status_code: Always 401.
        error_code: Always ``"authentication_error"``.
    """

    status_code: int = 401
    error_code: str = "authentication_error"


class AuthorizationError(PointlessSQLError):
    """Raised when a user lacks the required privilege on a securable.

    Attributes:
        status_code: Always 403.
        error_code: Always ``"authorization_error"``.

    Args:
        principal: Email of the user that was denied.
        privilege: The privilege that was required.
        securable_type: The type of securable (catalog, schema, table).
        full_name: The dotted name of the securable.
    """

    status_code: int = 403
    error_code: str = "authorization_error"

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


class EngineError(PointlessSQLError):
    """Raised when a Delta Lake or compute-engine operation fails.

    Attributes:
        status_code: Always 500.
        error_code: Always ``"engine_error"``.
    """

    status_code: int = 500
    error_code: str = "engine_error"


class ValidationError(PointlessSQLError, ValueError):
    """Raised for invalid input such as malformed table names.

    Inherits from both :class:`PointlessSQLError` and :class:`ValueError`
    so that existing ``except ValueError`` clauses continue to work
    during the transition period.

    Attributes:
        status_code: Always 422.
        error_code: Always ``"validation_error"``.
    """

    status_code: int = 422
    error_code: str = "validation_error"
