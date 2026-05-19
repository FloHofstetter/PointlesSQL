"""App-global configuration: pydantic-settings models + logging setup.

This package consolidates the two top-level configuration modules
(``settings.py`` 838 LOC + ``logging_config.py`` 284 LOC) that
were the largest flat files at the project root.  Both are loaded
very early in the lifecycle and conceptually belong together —
:class:`Settings` carries the env-driven config, :func:`configure_logging`
applies the logging side of it.

Layout (private modules, do not import directly):

* ``_settings`` — :class:`Settings` + every nested
  ``BaseSettings`` sub-model (server, soyuz, db, auth, oidc,
  logging, jupyter, scheduler, audit, delta, sql, agent_runs,
  audit_stream, external_writes, cdf_tail, branch, conventions,
  data_products, mlflow, dbt, workspace_repos).
* ``_logging`` — :class:`JSONFormatter`, :class:`RequestIdFilter`,
  :func:`configure_logging`, and the request/job/task
  :class:`ContextVar` triplet exposed for cross-module log-context
  enrichment.
"""

from __future__ import annotations

from pointlessql.config._logging import (
    JSONFormatter,
    RequestIdFilter,
    configure_logging,
    job_run_id_var,
    request_id_var,
    task_id_var,
)
from pointlessql.config._settings import (
    AgentRunsSettings,
    AuditSettings,
    AuditStreamSettings,
    AuthSettings,
    BranchSettings,
    CDFTailSettings,
    ConventionsSettings,
    DatabaseSettings,
    DataProductsSettings,
    DBTSettings,
    DeltaSettings,
    EditorChatSettings,
    ExternalWritesSettings,
    GroupMapping,
    JupyterSettings,
    LineageRetentionSettings,
    LoggingSettings,
    MLflowSettings,
    OIDCSettings,
    RateLimitSettings,
    SchedulerSettings,
    ServerSettings,
    Settings,
    SoyuzSettings,
    SQLSettings,
    WorkspaceReposSettings,
)

__all__ = [
    "AgentRunsSettings",
    "AuditSettings",
    "AuditStreamSettings",
    "AuthSettings",
    "BranchSettings",
    "CDFTailSettings",
    "ConventionsSettings",
    "DBTSettings",
    "DataProductsSettings",
    "DatabaseSettings",
    "DeltaSettings",
    "EditorChatSettings",
    "ExternalWritesSettings",
    "GroupMapping",
    "JSONFormatter",
    "JupyterSettings",
    "LineageRetentionSettings",
    "LoggingSettings",
    "MLflowSettings",
    "OIDCSettings",
    "RateLimitSettings",
    "RequestIdFilter",
    "SQLSettings",
    "SchedulerSettings",
    "ServerSettings",
    "Settings",
    "SoyuzSettings",
    "WorkspaceReposSettings",
    "configure_logging",
    "job_run_id_var",
    "request_id_var",
    "task_id_var",
]
