"""Sprint 43.2 — Reparented orphan exception families.

Locks the contract that every domain exception in the project
inherits from :class:`PointlessSQLError`, carries a
:class:`ErrorCode` value, and renders with its declared
``status_code`` through the centralised handler.
"""

from __future__ import annotations

import pytest

from pointlessql.exceptions import (
    AuthorizationError,
    PermissionDeniedError,
    PointlessSQLError,
)
from pointlessql.pql._branch_errors import (
    BranchAlreadyExistsError,
    BranchCloudUnsupportedError,
    BranchError,
    BranchInUseError,
    BranchNotFoundError,
    BranchOfBranchError,
    BranchPromotionConflictError,
)
from pointlessql.pql.sql_parser import SQLParseError
from pointlessql.services.agent_runs.operations import (
    RollbackAmbiguous,
    RollbackError,
    RollbackInvalid,
    RollbackStale,
    RollbackTargetNotFound,
)
from pointlessql.services.audit import AuditIntegrityError
from pointlessql.services.branch_tags import BranchTagsCorruptError
from pointlessql.services.dbt_executor import DBTExecutionError
from pointlessql.services.dbt_subprocess import DBTStartupError
from pointlessql.services.mlflow_subprocess import MLflowStartupError
from pointlessql.services.model_promotion import PromotionError
from pointlessql.services.oidc import OIDCError
from pointlessql.types import ErrorCode


@pytest.mark.parametrize(
    ("cls", "expected_code", "expected_status"),
    [
        # Branch family.
        (BranchError, ErrorCode.BRANCH_ERROR, 409),
        (BranchAlreadyExistsError, ErrorCode.BRANCH_ALREADY_EXISTS, 409),
        (BranchNotFoundError, ErrorCode.BRANCH_NOT_FOUND, 404),
        (BranchCloudUnsupportedError, ErrorCode.BRANCH_CLOUD_UNSUPPORTED, 422),
        (BranchPromotionConflictError, ErrorCode.BRANCH_PROMOTION_CONFLICT, 409),
        (BranchInUseError, ErrorCode.BRANCH_IN_USE, 409),
        (BranchOfBranchError, ErrorCode.BRANCH_OF_BRANCH, 422),
        # Rollback family.
        (RollbackError, ErrorCode.ROLLBACK_ERROR, 422),
        (RollbackTargetNotFound, ErrorCode.ROLLBACK_TARGET_NOT_FOUND, 404),
        (RollbackAmbiguous, ErrorCode.ROLLBACK_AMBIGUOUS, 409),
        (RollbackInvalid, ErrorCode.ROLLBACK_INVALID, 422),
        (RollbackStale, ErrorCode.ROLLBACK_STALE, 409),
        # Subprocess plumbing.
        (DBTStartupError, ErrorCode.DBT_STARTUP_ERROR, 503),
        (DBTExecutionError, ErrorCode.DBT_EXECUTION_ERROR, 503),
        (MLflowStartupError, ErrorCode.MLFLOW_STARTUP_ERROR, 503),
        # Storage integrity.
        (AuditIntegrityError, ErrorCode.AUDIT_INTEGRITY_ERROR, 500),
        (BranchTagsCorruptError, ErrorCode.BRANCH_TAGS_CORRUPT, 500),
        # Other co-located.
        (OIDCError, ErrorCode.OIDC_ERROR, 401),
        (PromotionError, ErrorCode.PROMOTION_ERROR, 422),
        (SQLParseError, ErrorCode.SQL_PARSE_ERROR, 422),
        # Auth siblings.
        (PermissionDeniedError, ErrorCode.PERMISSION_DENIED, 403),
    ],
)
def test_orphans_reparented_under_pointlessql_error(
    cls: type[PointlessSQLError],
    expected_code: ErrorCode,
    expected_status: int,
) -> None:
    """Each orphan now inherits PointlessSQLError + carries enum + status."""
    assert issubclass(cls, PointlessSQLError), cls.__name__
    assert cls.error_code is expected_code, cls.__name__
    assert cls.status_code == expected_status, cls.__name__


def test_subprocess_errors_keep_runtime_error_compatibility() -> None:
    """Dual-parent preserves legacy ``except RuntimeError`` clauses."""
    assert issubclass(DBTStartupError, RuntimeError)
    assert issubclass(DBTExecutionError, RuntimeError)
    assert issubclass(MLflowStartupError, RuntimeError)
    # And is still a PointlessSQLError so the central handler picks it up.
    assert issubclass(DBTStartupError, PointlessSQLError)


def test_sql_parse_error_keeps_value_error_compatibility() -> None:
    """``except ValueError`` still catches via ValidationError MRO."""
    assert issubclass(SQLParseError, ValueError)
    assert issubclass(SQLParseError, PointlessSQLError)


def test_permission_denied_isinstance_authorization_error() -> None:
    """``except AuthorizationError`` keeps catching the no-context sibling."""
    err = PermissionDeniedError("auditor scope required")
    assert isinstance(err, AuthorizationError)
    assert isinstance(err, PointlessSQLError)
    # Empty structured fields — the envelope stays clean.
    assert err.principal == ""
    assert err.privilege == ""
    assert err.securable_type == ""
    assert err.full_name == ""
    assert err.detail == "auditor scope required"


def test_extension_members_authorization_error() -> None:
    """AuthorizationError surfaces principal+privilege+securable triple."""
    err = AuthorizationError("u@x.io", "SELECT", "table", "cat.sch.tbl")
    extras = err.extension_members()
    assert extras == {
        "required_privilege": "SELECT",
        "securable_type": "table",
        "full_name": "cat.sch.tbl",
    }


def test_extension_members_rollback_stale() -> None:
    """RollbackStale surfaces version-triple as extension members."""
    err = RollbackStale(
        current_version=12,
        expected_version=10,
        intervening_op_count=2,
    )
    extras = err.extension_members()
    assert extras == {
        "current_version": 12,
        "expected_version": 10,
        "intervening_op_count": 2,
    }


def test_extension_members_branch_promotion_conflict() -> None:
    """BranchPromotionConflictError surfaces table+version triple."""
    err = BranchPromotionConflictError(
        table_name="silver.orders",
        expected_version=3,
        actual_version=5,
    )
    extras = err.extension_members()
    assert extras == {
        "table_name": "silver.orders",
        "expected_version": 3,
        "actual_version": 5,
    }


def test_extension_members_default_is_none() -> None:
    """The base class returns None — no extension members by default."""

    class _Plain(PointlessSQLError):
        pass

    err = _Plain("boom")
    assert err.extension_members() is None
