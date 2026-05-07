"""Sanity tests for :mod:`pointlessql.enums`.

The StrEnum members defined in :mod:`pointlessql.enums` MUST equal
their legacy frozenset / tuple constants byte-for-byte, because:

* DB-stored values (``agent_runs.status``,
  ``agent_run_operations.op_name``, etc.) round-trip those exact
  strings.
* SQL CHECK constraints in the alembic history pin the literal
  list of allowed values.
* JSON wire format from FastAPI serialises StrEnum members by
  their string value (``json.dumps(RunStatus.RUNNING) == '"running"'``)
  not their fully-qualified Python name.

A regression here -- e.g. someone capitalising ``QUEUED = "Queued"``
-- would silently corrupt every audit row written after the
change.  These tests fire before any migration commits so CI
fails before any consumer migration can land.
"""

from __future__ import annotations

import json
from enum import StrEnum

from pointlessql.enums import (
    AuditSinkType,
    BranchAction,
    EventOutcome,
    OpName,
    QueryStatus,
    ReadKind,
    ReviewKind,
    ReviewSeverity,
    RunStatus,
)
from pointlessql.models.agent_reviews import REVIEW_KINDS, REVIEW_SEVERITIES
from pointlessql.models.agent_runs import VALID_STATUSES
from pointlessql.models.audit_sinks import SINK_TYPES
from pointlessql.models.branch_audit import BRANCH_ACTIONS
from pointlessql.services.agent_runs.operations import VALID_OP_NAMES
from pointlessql.services.query_history import VALID_READ_KINDS


def _values(enum_cls: type[StrEnum]) -> set[str]:
    """Return the string-value set of a StrEnum class."""
    return {member.value for member in enum_cls}


def test_run_status_values_match_models_constant() -> None:
    """``RunStatus`` matches :data:`agent_runs.VALID_STATUSES`."""
    assert _values(RunStatus) == set(VALID_STATUSES)


def test_op_name_values_match_services_constant() -> None:
    """``OpName`` matches :data:`operations.VALID_OP_NAMES`."""
    assert _values(OpName) == set(VALID_OP_NAMES)


def test_read_kind_values_match_services_constant() -> None:
    """``ReadKind`` matches :data:`query_history.VALID_READ_KINDS`."""
    assert _values(ReadKind) == set(VALID_READ_KINDS)


def test_review_severity_values_match_models_constant() -> None:
    """``ReviewSeverity`` matches :data:`agent_reviews.REVIEW_SEVERITIES`."""
    assert _values(ReviewSeverity) == set(REVIEW_SEVERITIES)


def test_review_kind_values_match_models_constant() -> None:
    """``ReviewKind`` matches :data:`agent_reviews.REVIEW_KINDS`."""
    assert _values(ReviewKind) == set(REVIEW_KINDS)


def test_audit_sink_type_values_match_models_constant() -> None:
    """``AuditSinkType`` matches :data:`audit_sinks.SINK_TYPES`."""
    assert _values(AuditSinkType) == set(SINK_TYPES)


def test_branch_action_values_match_models_constant() -> None:
    """``BranchAction`` matches :data:`branch_audit.BRANCH_ACTIONS`."""
    assert _values(BranchAction) == set(BRANCH_ACTIONS)


def test_query_status_values_pinned() -> None:
    """``QueryStatus`` covers the three observed status literals."""
    assert _values(QueryStatus) == {"succeeded", "failed", "cancelled"}


def test_event_outcome_values_pinned() -> None:
    """``EventOutcome`` covers the four CHECK-constrained outcomes."""
    assert _values(EventOutcome) == {
        "pending",
        "delivered",
        "delivery_failed",
        "no_destination",
    }


def test_strenum_json_round_trip() -> None:
    """``json.dumps`` of a StrEnum member yields the string value.

    Critical for FastAPI / CloudEvents wire format.  StrEnum's
    ``__str__`` returns the value (Python 3.11+) so JSON
    serialisation is identical to plain ``str`` callers.
    """
    assert json.dumps({"status": RunStatus.RUNNING}) == '{"status": "running"}'
    assert json.dumps({"op": OpName.MERGE}) == '{"op": "merge"}'
    assert json.dumps({"sev": ReviewSeverity.CRITICAL}) == '{"sev": "critical"}'


def test_strenum_str_equals_value() -> None:
    """``str(member)`` returns the string value, not ``"Class.NAME"``."""
    assert str(RunStatus.RUNNING) == "running"
    assert str(OpName.MERGE) == "merge"
    assert str(ReadKind.AUDIT_API_CROSS_WORKSPACE) == "audit_api_cross_workspace"


def test_strenum_member_equals_string_literal() -> None:
    """Membership in StrEnum is identical to membership-by-string."""
    assert RunStatus.RUNNING == "running"
    assert OpName.WRITE_TABLE == "write_table"
    assert AuditSinkType.S3 == "s3"
