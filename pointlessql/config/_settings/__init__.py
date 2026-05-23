"""Application settings loaded from environment variables.

The root :class:`Settings` is split into nested sub-models with
per-sub-model ``env_prefix``.  Each sub-model owns its own
``BaseSettings`` namespace and the root composes them via
``Field(default_factory=…)`` so every ``Settings()`` instantiation
reads the env fresh (important for papermill workers that spawn with
a CWD snapshot).

The 24 sub-models live under topical private modules
(``_auth``, ``_storage``, ``_infra``, ``_audit``, ``_features``,
``_integrations``).  This ``__init__`` re-exports every class so
``from pointlessql.config._settings import X`` continues to work for
the :mod:`pointlessql.config` facade and any historical importers.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from pointlessql.config._settings._audit import (
    AgentRunsSettings,
    AuditSettings,
    AuditStreamSettings,
    LineageRetentionSettings,
)
from pointlessql.config._settings._auth import (
    AuthSettings,
    GroupMapping,
    OIDCSettings,
)
from pointlessql.config._settings._features import (
    ApiKeyAclSettings,
    ApiKeyLifecycleSettings,
    BranchSettings,
    CoeditSettings,
    ConventionsSettings,
    DataProductsSettings,
    EditorChatSettings,
    LensSettings,
    NotificationsSettings,
    SqlExecutionApiSettings,
    SQLSettings,
)
from pointlessql.config._settings._infra import (
    CDFTailSettings,
    ExternalWritesSettings,
    LoggingSettings,
    RateLimitSettings,
    SchedulerSettings,
    ServerSettings,
)
from pointlessql.config._settings._integrations import (
    DBTSettings,
    JupyterSettings,
    MLflowSettings,
    SoyuzSettings,
    WorkspaceReposSettings,
)
from pointlessql.config._settings._storage import DatabaseSettings, DeltaSettings


class Settings(BaseSettings):
    """Root settings aggregating every sub-model.

    Each nested model is constructed via ``default_factory`` so that
    environment variables are read at instantiation time, not at class
    definition / import time.  The sub-models own their own
    ``env_prefix`` and can be instantiated independently in tests.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_")

    server: ServerSettings = Field(default_factory=ServerSettings)
    soyuz: SoyuzSettings = Field(default_factory=SoyuzSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    oidc: OIDCSettings = Field(default_factory=OIDCSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    jupyter: JupyterSettings = Field(default_factory=JupyterSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    delta: DeltaSettings = Field(default_factory=DeltaSettings)
    sql: SQLSettings = Field(default_factory=SQLSettings)
    sql_execution_api: SqlExecutionApiSettings = Field(
        default_factory=SqlExecutionApiSettings
    )
    api_key_lifecycle: ApiKeyLifecycleSettings = Field(
        default_factory=ApiKeyLifecycleSettings
    )
    api_key_acl: ApiKeyAclSettings = Field(default_factory=ApiKeyAclSettings)
    editor_chat: EditorChatSettings = Field(default_factory=EditorChatSettings)
    agent_runs: AgentRunsSettings = Field(default_factory=AgentRunsSettings)
    audit_stream: AuditStreamSettings = Field(default_factory=AuditStreamSettings)
    external_writes: ExternalWritesSettings = Field(default_factory=ExternalWritesSettings)
    cdf_tail: CDFTailSettings = Field(default_factory=CDFTailSettings)
    branch: BranchSettings = Field(default_factory=BranchSettings)
    conventions: ConventionsSettings = Field(default_factory=ConventionsSettings)
    data_products: DataProductsSettings = Field(default_factory=DataProductsSettings)
    notifications: NotificationsSettings = Field(default_factory=NotificationsSettings)
    workspace_repos: WorkspaceReposSettings = Field(default_factory=WorkspaceReposSettings)
    mlflow: MLflowSettings = Field(default_factory=MLflowSettings)
    dbt: DBTSettings = Field(default_factory=DBTSettings)
    lens: LensSettings = Field(default_factory=LensSettings)
    coedit: CoeditSettings = Field(default_factory=CoeditSettings)


__all__ = [
    "AgentRunsSettings",
    "ApiKeyAclSettings",
    "ApiKeyLifecycleSettings",
    "AuditSettings",
    "AuditStreamSettings",
    "AuthSettings",
    "BranchSettings",
    "CDFTailSettings",
    "CoeditSettings",
    "ConventionsSettings",
    "DBTSettings",
    "DataProductsSettings",
    "DatabaseSettings",
    "DeltaSettings",
    "EditorChatSettings",
    "ExternalWritesSettings",
    "GroupMapping",
    "JupyterSettings",
    "LensSettings",
    "LineageRetentionSettings",
    "LoggingSettings",
    "MLflowSettings",
    "NotificationsSettings",
    "OIDCSettings",
    "RateLimitSettings",
    "SQLSettings",
    "SchedulerSettings",
    "ServerSettings",
    "Settings",
    "SoyuzSettings",
    "SqlExecutionApiSettings",
    "WorkspaceReposSettings",
]
