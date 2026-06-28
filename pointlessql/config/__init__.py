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

from functools import lru_cache

from pointlessql.config._logging import (
    JSONFormatter,
    RequestIdFilter,
    configure_logging,
    correlation_id_var,
    job_run_id_var,
    request_id_var,
    task_id_var,
)
from pointlessql.config._settings import (
    AgentRunsSettings,
    AiFunctionsSettings,
    ApiKeyAclSettings,
    ApiKeyLifecycleSettings,
    AppsSettings,
    AuditSettings,
    AuditStreamSettings,
    AuthSettings,
    AzureSettings,
    BitemporalSettings,
    BranchSettings,
    CanvasFileIoSettings,
    CDFTailSettings,
    ConventionsSettings,
    DatabaseSettings,
    DataProductsSettings,
    DBTSettings,
    DeltaSettings,
    EditorChatSettings,
    EgressSettings,
    EventPortSettings,
    ExecutorSettings,
    ExternalWritesSettings,
    GCSSettings,
    GroupMapping,
    HermesSettings,
    JupyterSettings,
    LineageRetentionSettings,
    LoggingSettings,
    MLflowSettings,
    ObjectStoreSettings,
    OIDCSettings,
    PrivilegeSettings,
    RateLimitSettings,
    S3Settings,
    SchedulerSettings,
    ServerSettings,
    ServingSettings,
    Settings,
    SoyuzSettings,
    SqlExecutionApiSettings,
    SQLSettings,
    WorkspaceReposSettings,
    assert_secret_key_safe,
)

__all__ = [
    "AgentRunsSettings",
    "AiFunctionsSettings",
    "ApiKeyAclSettings",
    "AppsSettings",
    "ApiKeyLifecycleSettings",
    "AuditSettings",
    "AuditStreamSettings",
    "AuthSettings",
    "AzureSettings",
    "BitemporalSettings",
    "BranchSettings",
    "CDFTailSettings",
    "CanvasFileIoSettings",
    "ConventionsSettings",
    "DBTSettings",
    "DataProductsSettings",
    "DatabaseSettings",
    "DeltaSettings",
    "EditorChatSettings",
    "EgressSettings",
    "EventPortSettings",
    "ExecutorSettings",
    "ExternalWritesSettings",
    "GCSSettings",
    "GroupMapping",
    "HermesSettings",
    "JSONFormatter",
    "JupyterSettings",
    "LineageRetentionSettings",
    "LoggingSettings",
    "MLflowSettings",
    "ServingSettings",
    "ObjectStoreSettings",
    "OIDCSettings",
    "PrivilegeSettings",
    "RateLimitSettings",
    "RequestIdFilter",
    "S3Settings",
    "SQLSettings",
    "SchedulerSettings",
    "ServerSettings",
    "Settings",
    "SoyuzSettings",
    "SqlExecutionApiSettings",
    "WorkspaceReposSettings",
    "assert_secret_key_safe",
    "configure_logging",
    "correlation_id_var",
    "get_settings",
    "job_run_id_var",
    "request_id_var",
    "reset_settings_cache",
    "task_id_var",
]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return the cached process-wide :class:`Settings` instance.

    pydantic-settings re-reads env vars on each construction; caching
    eliminates that cost for the 90+ import sites.  Tests reset the
    cache via :func:`reset_settings_cache` in an autouse fixture so
    env-var monkeypatching keeps working between tests.

    Returns:
        The single process-wide :class:`Settings` instance.
    """
    return Settings()


def reset_settings_cache() -> None:
    """Clear the :func:`get_settings` LRU cache.

    Test-only — production code should never need to reset the
    cache because env vars are stable within a process lifetime.
    """
    get_settings.cache_clear()
