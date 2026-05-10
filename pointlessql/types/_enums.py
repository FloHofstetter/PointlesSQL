"""Central StrEnum registry for the project's enum-shaped string columns.

Mirrors the :mod:`pointlessql.error_codes` pattern: every member
subclasses :class:`str` (via :class:`enum.StrEnum`) so existing
wire-format consumers and DB-stored values keep working
unchanged.  ``RunStatus.RUNNING == "running"`` is ``True`` and
``json.dumps({"status": RunStatus.RUNNING})`` emits
``'{"status": "running"}'`` -- not ``'"RunStatus.RUNNING"'``.

These enums live at the function-signature / service / route
boundary.  The model layer keeps ``Mapped[str]`` per anti-goal
-- SQLAlchemy native StrEnum integration is unspec'd on column
read/write and would cascade autogenerate diffs.
"""

from __future__ import annotations

from enum import StrEnum


class RunStatus(StrEnum):
    """Lifecycle states of an :class:`AgentRun`.

    Pinned to :data:`pointlessql.models.agent._runs.VALID_STATUSES`.
    """

    QUEUED = "queued"
    RUNNING = "running"
    NEEDS_APPROVAL = "needs_approval"
    APPROVED = "approved"
    DENIED = "denied"
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class OpName(StrEnum):
    """Recognised primitive labels on ``agent_run_operations.op_name``.

    Pinned to :data:`pointlessql.services.agent_runs.operations.VALID_OP_NAMES`
    and to the ``ck_agent_run_operations_op_name`` SQL CHECK
    constraint.  Adding a value: bump both this enum AND the CHECK
    constraint via Alembic in lockstep.
    """

    AUTOLOAD = "autoload"
    MERGE = "merge"
    WRITE_TABLE = "write_table"
    SQL = "sql"
    AGGREGATE = "aggregate"
    ROLLBACK = "rollback"
    TRAIN_MODEL = "train_model"
    BRANCH_CREATE = "branch_create"
    BRANCH_PROMOTE = "branch_promote"
    BRANCH_DISCARD = "branch_discard"
    DBT_MODEL = "dbt_model"
    DBT_TEST = "dbt_test"
    SQL_EXPLAIN = "sql_explain"
    UPDATE = "update"
    DELETE = "delete"
    DROP_TABLE = "drop_table"
    CREATE_SCHEMA = "create_schema"
    DROP_SCHEMA = "drop_schema"
    ALTER_TABLE = "alter_table"


class ReadKind(StrEnum):
    """Discriminator for read-path producers of ``query_history`` rows.

    Pinned to :data:`pointlessql.services.query_history.VALID_READ_KINDS`.
    """

    SQL_EXECUTE = "sql_execute"
    SQL_DML = "sql_dml"
    SQL_DDL = "sql_ddl"
    PQL_TABLE = "pql_table"
    PQL_TABLE_AT_VERSION = "pql_table_at_version"
    ENGINE_DIRECT = "engine_direct"
    AUDIT_API = "audit_api"
    AUDIT_API_CROSS_WORKSPACE = "audit_api_cross_workspace"


class QueryStatus(StrEnum):
    """Lifecycle states of a single :class:`QueryHistory` row."""

    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class ReviewSeverity(StrEnum):
    """Severity grade of an :class:`AgentReview`.

    Pinned to :data:`pointlessql.models.agent._reviews.REVIEW_SEVERITIES`
    and to the ``ck_agent_reviews_severity`` /
    ``ck_review_destinations_min_severity`` SQL CHECK constraints.
    """

    OK = "ok"
    WARN = "warn"
    CRITICAL = "critical"


class ReviewKind(StrEnum):
    """Variants of an :class:`AgentReview` row.

    Pinned to :data:`pointlessql.models.agent._reviews.REVIEW_KINDS`.
    """

    AUDIT_REVIEW = "audit_review"
    MODEL_PROMOTION = "model_promotion"


class AuditSinkType(StrEnum):
    """Recognised :class:`AuditSink.type` values.

    Pinned to :data:`pointlessql.models.audit_sinks.SINK_TYPES`
    and to the ``ck_audit_sinks_type`` SQL CHECK constraint.
    """

    WEBHOOK = "webhook"
    S3 = "s3"
    AWS_CLOUDTRAIL = "aws_cloudtrail"


class EventOutcome(StrEnum):
    """Delivery outcome of an audit / governance event.

    Pinned to the ``ck_agent_run_events_outcome`` /
    ``ck_governance_events_outcome`` SQL CHECK constraints.
    """

    PENDING = "pending"
    DELIVERED = "delivered"
    DELIVERY_FAILED = "delivery_failed"
    NO_DESTINATION = "no_destination"


class BranchAction(StrEnum):
    """Action label on a :class:`BranchAuditLog` row.

    Pinned to :data:`pointlessql.models.branch_audit.BRANCH_ACTIONS`.
    """

    CREATE = "create"
    PROMOTE = "promote"
    DISCARD = "discard"
    AUTO_CLEANUP = "auto_cleanup"
