"""Machine-readable error code registry.

Central :class:`ErrorCode` enum referenced by every domain exception
in the project.  Members subclass :class:`str` (via :class:`StrEnum`)
so existing wire-format consumers that compare against string
literals (``body["code"] == "validation_error"``) keep working
unchanged.

Adding a code: add the member here, point the exception at it via a
class attribute (``error_code: ErrorCode = ErrorCode.X``), and the
RFC 9457 envelope renderer in
:mod:`pointlessql.api.error_handlers` surfaces it automatically.
"""

from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    """Every machine-readable error code emitted by the API.

    Grouped by domain in declaration order.  String values are
    snake_case so they read cleanly in JSON envelopes and in
    Grafana dashboards filtered on ``code``.
    """

    # Generic / catch-all.
    INTERNAL_ERROR = "internal_error"

    # Catalog (soyuz) plumbing.
    CATALOG_UNAVAILABLE = "catalog_unavailable"
    CATALOG_NOT_FOUND = "catalog_not_found"

    # Auth / authz.
    AUTHENTICATION_ERROR = "authentication_error"
    AUTHORIZATION_ERROR = "authorization_error"
    PERMISSION_DENIED = "permission_denied"
    OIDC_ERROR = "oidc_error"

    # Validation / request shape.
    VALIDATION_ERROR = "validation_error"
    SQL_PARSE_ERROR = "sql_parse_error"

    # Engine / compute.
    ENGINE_ERROR = "engine_error"
    PQL_WRITE_ERROR = "pql_write_error"
    SQL_EXECUTION_ERROR = "sql_execution_error"

    # Scheduler / notebook plumbing.
    SCHEDULER_ERROR = "scheduler_error"
    NOTEBOOK_RENDER_ERROR = "notebook_render_error"

    # Audit / integrity.
    AUDIT_UNAVAILABLE = "audit_unavailable"
    AUDIT_INTEGRITY_ERROR = "audit_integrity_error"

    # Resource lifecycle.
    RESOURCE_NOT_FOUND = "resource_not_found"
    CONFLICT = "conflict"

    # Branch primitives.
    BRANCH_ERROR = "branch_error"
    BRANCH_ALREADY_EXISTS = "branch_already_exists"
    BRANCH_NOT_FOUND = "branch_not_found"
    BRANCH_CLOUD_UNSUPPORTED = "branch_cloud_unsupported"
    BRANCH_PROMOTION_CONFLICT = "branch_promotion_conflict"
    BRANCH_IN_USE = "branch_in_use"
    BRANCH_OF_BRANCH = "branch_of_branch"
    BRANCH_TAGS_CORRUPT = "branch_tags_corrupt"

    # Rollback primitives.
    ROLLBACK_ERROR = "rollback_error"
    ROLLBACK_TARGET_NOT_FOUND = "rollback_target_not_found"
    ROLLBACK_AMBIGUOUS = "rollback_ambiguous"
    ROLLBACK_INVALID = "rollback_invalid"
    ROLLBACK_STALE = "rollback_stale"

    # Model registry / promotion.
    PROMOTION_ERROR = "promotion_error"

    # Subprocess plumbing (dbt, mlflow).
    DBT_STARTUP_ERROR = "dbt_startup_error"
    DBT_EXECUTION_ERROR = "dbt_execution_error"
    MLFLOW_STARTUP_ERROR = "mlflow_startup_error"
