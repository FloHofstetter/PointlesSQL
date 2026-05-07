"""Sprint 43.1 — Central :class:`ErrorCode` StrEnum.

Locks the contract that every domain exception in the project carries
an :class:`ErrorCode` member and that the enum stays compatible with
the existing wire format (string equality, JSON serialization).
"""

from __future__ import annotations

import json

from pointlessql.error_codes import ErrorCode
from pointlessql.exceptions import (
    AuditUnavailableError,
    AuthenticationError,
    AuthorizationError,
    CatalogNotFoundError,
    CatalogUnavailableError,
    EngineError,
    NotebookRenderError,
    PointlessSQLError,
    PQLWriteError,
    SchedulerError,
    SQLExecutionError,
    ValidationError,
)


def test_every_domain_exception_carries_error_code_member() -> None:
    """Each PointlesSQLError subclass declares an ``ErrorCode`` value."""
    cases: list[tuple[type[PointlessSQLError], ErrorCode]] = [
        (PointlessSQLError, ErrorCode.INTERNAL_ERROR),
        (CatalogUnavailableError, ErrorCode.CATALOG_UNAVAILABLE),
        (CatalogNotFoundError, ErrorCode.CATALOG_NOT_FOUND),
        (AuthenticationError, ErrorCode.AUTHENTICATION_ERROR),
        (AuthorizationError, ErrorCode.AUTHORIZATION_ERROR),
        (EngineError, ErrorCode.ENGINE_ERROR),
        (ValidationError, ErrorCode.VALIDATION_ERROR),
        (SchedulerError, ErrorCode.SCHEDULER_ERROR),
        (NotebookRenderError, ErrorCode.NOTEBOOK_RENDER_ERROR),
        (PQLWriteError, ErrorCode.PQL_WRITE_ERROR),
        (AuditUnavailableError, ErrorCode.AUDIT_UNAVAILABLE),
        (SQLExecutionError, ErrorCode.SQL_EXECUTION_ERROR),
    ]
    for cls, expected_code in cases:
        assert cls.error_code is expected_code, cls.__name__
        assert isinstance(cls.error_code, ErrorCode), cls.__name__


def test_error_code_member_value_is_legacy_snake_case_string() -> None:
    """Wire format stays unchanged: ``ErrorCode.X.value`` equals legacy literal."""
    assert ErrorCode.VALIDATION_ERROR.value == "validation_error"
    assert ErrorCode.CATALOG_UNAVAILABLE.value == "catalog_unavailable"
    assert ErrorCode.AUTHORIZATION_ERROR.value == "authorization_error"


def test_error_code_compares_equal_to_legacy_literal() -> None:
    """Existing ``body["code"] == "validation_error"`` assertions stay green."""
    # StrEnum instances are str subclasses; equality with literals works.
    assert ErrorCode.VALIDATION_ERROR == "validation_error"
    assert "validation_error" == ErrorCode.VALIDATION_ERROR
    # Hashable, so dict-key lookup also works.
    table = {ErrorCode.AUTHORIZATION_ERROR: "authz"}
    assert table["authorization_error"] == "authz"


def test_error_code_serialises_as_plain_string_in_json() -> None:
    """``json.dumps`` emits the string value, not a tagged enum object."""
    body = {"code": ErrorCode.VALIDATION_ERROR}
    encoded = json.dumps(body)
    assert encoded == '{"code": "validation_error"}'


def test_error_code_member_count_matches_exception_inventory() -> None:
    """Sanity gate: ErrorCode covers at least the existing exception inventory.

    Every currently shipped exception has a corresponding member.  The
    enum is allowed to grow ahead of the exception classes (members
    that exist for upcoming sprints), but never the other way around.
    """
    exception_codes = {
        cls.error_code
        for cls in (
            PointlessSQLError,
            CatalogUnavailableError,
            CatalogNotFoundError,
            AuthenticationError,
            AuthorizationError,
            EngineError,
            ValidationError,
            SchedulerError,
            NotebookRenderError,
            PQLWriteError,
            AuditUnavailableError,
            SQLExecutionError,
        )
    }
    assert exception_codes.issubset(set(ErrorCode))
