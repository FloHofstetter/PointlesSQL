"""CloudEvents type-literal registry.

Every ``type`` field on a CloudEvents envelope ships in exactly
one place so Grafana filters and downstream forwarders have a
stable contract.  Adding a new event: add the constant here,
point the producer at it, ship.

Values match the byte-for-byte literals previously declared in
:mod:`pointlessql.services.agent_runs.events` and
:mod:`pointlessql.services.governance_events`; those modules
keep their ``EVENT_TYPE_*`` aliases for back-compat so existing
imports continue to work without churn.
"""

from __future__ import annotations

from typing import Final

# Agent-run lifecycle.
AGENT_RUN_STARTED: Final = "pointlessql.agent_run.started"
AGENT_RUN_COMPLETED: Final = "pointlessql.agent_run.completed"
AGENT_RUN_FAILED: Final = "pointlessql.agent_run.failed"
AGENT_RUN_TOOL_CALL: Final = "pointlessql.agent_run.tool_call"

# Governance.
EXTERNAL_WRITE_DETECTED: Final = "pointlessql.external_write.detected"
POLICY_VIOLATED: Final = "pointlessql.policy.violated"
COST_GATE_DENIED: Final = "pointlessql.cost_gate.denied"
AUDIT_EXPORT_ISSUED: Final = "pointlessql.audit_export.issued"
LINEAGE_PRUNED: Final = "pointlessql.lineage.pruned"
ROLLBACK_EXECUTED: Final = "pointlessql.rollback.executed"

# Branch lifecycle (versioned per ADR).
BRANCH_CREATED_V1: Final = "pointlessql.branch.created.v1"
BRANCH_PROMOTED_V1: Final = "pointlessql.branch.promoted.v1"
BRANCH_DISCARDED_V1: Final = "pointlessql.branch.discarded.v1"

# DBT.
DBT_RUN_COMPLETED: Final = "pointlessql.dbt.run.completed"
DBT_TEST_FAILED: Final = "pointlessql.dbt.test.failed"
DBT_TEST_WARNED: Final = "pointlessql.dbt.test.warned"
DBT_AUTO_ROLLBACK_EXECUTED: Final = "pointlessql.dbt.auto_rollback.executed"
