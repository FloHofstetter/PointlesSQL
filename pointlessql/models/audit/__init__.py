"""ORM models for the audit subsystem: log, sinks, saved queries, anomaly acks, branch audit.

Five flat sibling modules consolidated into one
``pointlessql.models.audit`` package.  The flat
``models/__init__.py`` facade still re-exports every class so
existing ``from pointlessql.models import AuditLog`` call sites
resolve unchanged.

Layout:

* ``_log``           — :class:`AuditLog` (the canonical audit-row table).
* ``_sinks``         — :class:`AuditSink`, :class:`GovernanceEvent`,
                        + ``SINK_TYPES`` constant.
* ``_saved_queries`` — :class:`SavedAuditQuery` (admin-curated audit
                        SQL templates).
* ``_anomaly``       — :class:`AnomalyAck` (per-anomaly
                        acknowledge-state row for the Audit Inbox).
* ``_branch``        — :class:`BranchAuditLog` (branch-lifecycle
                        audit trail) + ``BRANCH_ACTIONS`` constant.
"""

from __future__ import annotations

from pointlessql.models.audit._anomaly import AnomalyAck
from pointlessql.models.audit._branch import BRANCH_ACTIONS, BranchAuditLog
from pointlessql.models.audit._log import AuditLog
from pointlessql.models.audit._saved_queries import SavedAuditQuery
from pointlessql.models.audit._sinks import (
    SINK_TYPES,
    AuditSink,
    GovernanceEvent,
)

__all__ = [
    "BRANCH_ACTIONS",
    "SINK_TYPES",
    "AnomalyAck",
    "AuditLog",
    "AuditSink",
    "BranchAuditLog",
    "GovernanceEvent",
    "SavedAuditQuery",
]
