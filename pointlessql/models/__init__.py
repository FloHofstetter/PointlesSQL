"""SQLAlchemy ORM models for PointlesSQL's own metadata database.

The ORM is split into per-domain sub-modules.  Import order in this
file is **load-bearing**: SQLAlchemy resolves ``ForeignKey("table.col")``
strings at mapper-configuration time, so referenced tables must
already be registered when the referrers are imported.  The sequence
below

* ``base`` (Base class)
* ``auth`` (User — referenced by Job, Dashboard, SavedQuery, Alert)
* ``audit`` (AuditLog — no model FKs)
* ``sync`` (SyncRun — no model FKs)
* ``scheduler`` (Job, JobRun, JobTask, TaskRun, JobLog — Job FKs User)
* ``catalog`` (Dashboard FKs Job/User; QueryHistory + RateLimitEvent
  + SavedQuery + TableStats + QueryHistoryTable)
* ``alerts`` (Alert FKs SavedQuery + User + Job; AlertDestination
  + AlertEvent FK Alert)
* ``notebook`` (NotebookOutput, NotebookCellRun, NotebookCellRunSource
  — no model FKs; the ``agent_run_id`` column is logical-link only)
* ``agent_runs`` (AgentRun — logical link to notebook tables via
  ``agent_run_id``)
* ``agent_run_audit`` (AgentRunSource, AgentRunOperation,
  AgentRunEvent — FK to AgentRun)
* ``autoload`` (AutoloadCheckpoint — no model FKs, scoped per
  target_table)

honours every cross-module FK without resorting to circular imports.
The Alembic env.py keeps doing ``from pointlessql.models import Base``
unchanged, and every existing call site that imported a specific model
from ``pointlessql.models`` continues to resolve via the re-exports
below.
"""

from __future__ import annotations

from pointlessql.models.agent_run_audit import (
    AgentRunEvent,
    AgentRunOperation,
    AgentRunSource,
    AgentRunToolCall,
)
from pointlessql.models.agent_runs import AgentRun
from pointlessql.models.alerts import Alert, AlertDestination, AlertEvent
from pointlessql.models.api_keys import ApiKey
from pointlessql.models.audit import AuditLog
from pointlessql.models.auth import User
from pointlessql.models.autoload import AutoloadCheckpoint
from pointlessql.models.base import Base
from pointlessql.models.catalog import (
    Dashboard,
    QueryHistory,
    QueryHistoryTable,
    RateLimitEvent,
    SavedQuery,
    TableStats,
)
from pointlessql.models.notebook import (
    NotebookCellRun,
    NotebookCellRunSource,
    NotebookOutput,
)
from pointlessql.models.scheduler import (
    Job,
    JobLog,
    JobRun,
    JobTask,
    TaskRun,
)
from pointlessql.models.sync import SyncRun

__all__ = [
    "AgentRun",
    "AgentRunEvent",
    "AgentRunOperation",
    "AgentRunSource",
    "AgentRunToolCall",
    "Alert",
    "AlertDestination",
    "AlertEvent",
    "ApiKey",
    "AuditLog",
    "AutoloadCheckpoint",
    "Base",
    "Dashboard",
    "Job",
    "JobLog",
    "JobRun",
    "JobTask",
    "NotebookCellRun",
    "NotebookCellRunSource",
    "NotebookOutput",
    "QueryHistory",
    "QueryHistoryTable",
    "RateLimitEvent",
    "SavedQuery",
    "SyncRun",
    "TableStats",
    "TaskRun",
    "User",
]
