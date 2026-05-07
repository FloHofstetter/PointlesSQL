"""Single registry for every CloudEvents type literal the project emits.

Re-exports the constants from :mod:`pointlessql.services.cloudevents.types`
so consumers can do
``from pointlessql.services.cloudevents import AGENT_RUN_STARTED``
without thinking about whether the literal lived in
``services.agent_runs.events`` or ``services.governance_events``.

The legacy ``EVENT_TYPE_*`` aliases continue to live on the
original modules so already-imported consumers keep working
without churn.
"""

from pointlessql.services.cloudevents.types import (
    AGENT_RUN_COMPLETED,
    AGENT_RUN_FAILED,
    AGENT_RUN_STARTED,
    AGENT_RUN_TOOL_CALL,
    AUDIT_EXPORT_ISSUED,
    BRANCH_CREATED_V1,
    BRANCH_DISCARDED_V1,
    BRANCH_PROMOTED_V1,
    COST_GATE_DENIED,
    DBT_AUTO_ROLLBACK_EXECUTED,
    DBT_RUN_COMPLETED,
    DBT_TEST_FAILED,
    DBT_TEST_WARNED,
    EXTERNAL_WRITE_DETECTED,
    LINEAGE_PRUNED,
    POLICY_VIOLATED,
    ROLLBACK_EXECUTED,
)

__all__ = [
    "AGENT_RUN_COMPLETED",
    "AGENT_RUN_FAILED",
    "AGENT_RUN_STARTED",
    "AGENT_RUN_TOOL_CALL",
    "AUDIT_EXPORT_ISSUED",
    "BRANCH_CREATED_V1",
    "BRANCH_DISCARDED_V1",
    "BRANCH_PROMOTED_V1",
    "COST_GATE_DENIED",
    "DBT_AUTO_ROLLBACK_EXECUTED",
    "DBT_RUN_COMPLETED",
    "DBT_TEST_FAILED",
    "DBT_TEST_WARNED",
    "EXTERNAL_WRITE_DETECTED",
    "LINEAGE_PRUNED",
    "POLICY_VIOLATED",
    "ROLLBACK_EXECUTED",
]
