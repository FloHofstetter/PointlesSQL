"""SQLAlchemy ORM models for PointlesSQL's own metadata database.

The ORM is split into per-domain sub-modules.  Import order in this
file is **load-bearing**: SQLAlchemy resolves ``ForeignKey("table.col")``
strings at mapper-configuration time, so referenced tables must
already be registered when the referrers are imported.  The sequence
below

* ``base`` (Base class)
* ``auth`` (User — referenced by Job, Dashboard, SavedQuery, Alert)
* ``audit`` package (AuditLog, AuditSink, GovernanceEvent,
  SavedAuditQuery, AnomalyAck, BranchAuditLog — no model FKs)
* ``scheduler`` (Job, JobRun, JobTask, TaskRun, JobLog — Job FKs User)
* ``catalog`` package (Dashboard FKs Job/User; QueryHistory +
  RateLimitEvent + SavedQuery + TableStats + QueryHistoryTable +
  RecentTable + AutoloadCheckpoint + DataProduct +
  DataProductContractEvent + SyncRun)
* ``alerts`` (Alert FKs SavedQuery + User + Job; AlertDestination
  + AlertEvent FK Alert)
* ``notebook`` (NotebookOutput, NotebookCellRun, NotebookCellRunSource
  — no model FKs; the ``agent_run_id`` column is logical-link only)
* ``lens`` package (LensSession, LensMessage, LensPinnedAnswer,
  LensProviderCreds — Phase 65 read-only Q&A surface; FKs to
  Workspace + User)
* ``agent`` package (AgentRun, AgentRunSource, AgentRunOperation,
  AgentRunEvent, AgentRunToolCall, AgentReview, ReviewDestination,
  RewriteAttempt — internal FKs to AgentRun)
* ``workspace`` package (Workspace, WorkspaceMember,
  WorkspaceCatalogPin, WorkspaceRepo, WorkspaceRepoSecret, ApiKey
  — governance container; ``users.default_workspace_id`` and
  ``api_keys.workspace_id`` FKs are added in the same migration so
  this module imports last)

honours every cross-module FK without resorting to circular imports.
The Alembic env.py keeps doing ``from pointlessql.models import Base``
unchanged, and every existing call site that imported a specific model
from ``pointlessql.models`` continues to resolve via the re-exports
below.
"""

from __future__ import annotations

from pointlessql.models.agent import (
    REVIEW_SEVERITIES,
    REWRITE_VERDICTS,
    VERDICT_AUTO_REWRITE_FAILED,
    VERDICT_AUTO_REWRITE_SUCCEEDED,
    VERDICT_HUMAN_APPROVAL_REQUIRED,
    VERDICT_ORIGINAL_APPROVED,
    AgentReview,
    AgentRun,
    AgentRunEvent,
    AgentRunOperation,
    AgentRunSource,
    AgentRunToolCall,
    ReviewDestination,
    RewriteAttempt,
)
from pointlessql.models.alerts import Alert, AlertDestination, AlertEvent
from pointlessql.models.audit import (
    BRANCH_ACTIONS,
    SINK_TYPES,
    AnomalyAck,
    AuditLog,
    AuditSink,
    BranchAuditLog,
    GovernanceEvent,
    SavedAuditQuery,
)
from pointlessql.models.auth import User
from pointlessql.models.base import Base
from pointlessql.models.catalog import (
    CONTRACT_EVENT_OUTCOMES,
    AutoloadCheckpoint,
    Dashboard,
    DataProduct,
    DataProductContractEvent,
    QueryHistory,
    QueryHistoryTable,
    RateLimitEvent,
    RecentTable,
    SavedQuery,
    SyncRun,
    TableStats,
)
from pointlessql.models.lens import (
    LENS_PROVIDERS,
    LensMessage,
    LensPinnedAnswer,
    LensProviderCreds,
    LensSession,
)
from pointlessql.models.lineage import (
    REJECT_REASONS,
    TRANSFORM_KINDS,
    CdfTailEvent,
    CdfTailSubscription,
    ExpectedLineageInbound,
    LineageColumnMap,
    LineageRowEdge,
    LineageRowReject,
    LineageValueChange,
    UnattributedWrite,
)
from pointlessql.models.notebook import (
    NotebookCellRun,
    NotebookCellRunSource,
    NotebookJobLink,
    NotebookOutput,
)
from pointlessql.models.scheduler import (
    Job,
    JobLog,
    JobRun,
    JobTask,
    TaskRun,
)
from pointlessql.models.system_keys import SystemKey
from pointlessql.models.workspace import (
    WORKSPACE_PIN_MODES,
    WORKSPACE_REPO_PROVIDER_KINDS,
    WORKSPACE_REPO_SECRET_KINDS,
    WORKSPACE_REPO_SYNC_STATES,
    WORKSPACE_ROLES,
    ApiKey,
    Workspace,
    WorkspaceCatalogPin,
    WorkspaceMember,
    WorkspaceRepo,
    WorkspaceRepoSecret,
)

__all__ = [
    "AgentReview",
    "AgentRun",
    "AgentRunEvent",
    "AgentRunOperation",
    "AgentRunSource",
    "AgentRunToolCall",
    "Alert",
    "AlertDestination",
    "AlertEvent",
    "AnomalyAck",
    "ApiKey",
    "AuditLog",
    "AuditSink",
    "AutoloadCheckpoint",
    "BRANCH_ACTIONS",
    "Base",
    "BranchAuditLog",
    "CONTRACT_EVENT_OUTCOMES",
    "CdfTailEvent",
    "CdfTailSubscription",
    "DataProduct",
    "DataProductContractEvent",
    "Dashboard",
    "ExpectedLineageInbound",
    "GovernanceEvent",
    "Job",
    "JobLog",
    "JobRun",
    "JobTask",
    "LENS_PROVIDERS",
    "LensMessage",
    "LensPinnedAnswer",
    "LensProviderCreds",
    "LensSession",
    "LineageColumnMap",
    "LineageRowEdge",
    "LineageRowReject",
    "LineageValueChange",
    "REJECT_REASONS",
    "TRANSFORM_KINDS",
    "NotebookCellRun",
    "NotebookCellRunSource",
    "NotebookJobLink",
    "NotebookOutput",
    "QueryHistory",
    "QueryHistoryTable",
    "REVIEW_SEVERITIES",
    "RateLimitEvent",
    "RecentTable",
    "REWRITE_VERDICTS",
    "ReviewDestination",
    "RewriteAttempt",
    "VERDICT_AUTO_REWRITE_FAILED",
    "VERDICT_AUTO_REWRITE_SUCCEEDED",
    "VERDICT_HUMAN_APPROVAL_REQUIRED",
    "VERDICT_ORIGINAL_APPROVED",
    "SINK_TYPES",
    "SavedAuditQuery",
    "SavedQuery",
    "SyncRun",
    "SystemKey",
    "TableStats",
    "TaskRun",
    "UnattributedWrite",
    "User",
    "WORKSPACE_PIN_MODES",
    "WORKSPACE_REPO_PROVIDER_KINDS",
    "WORKSPACE_REPO_SECRET_KINDS",
    "WORKSPACE_REPO_SYNC_STATES",
    "WORKSPACE_ROLES",
    "Workspace",
    "WorkspaceCatalogPin",
    "WorkspaceMember",
    "WorkspaceRepo",
    "WorkspaceRepoSecret",
]
