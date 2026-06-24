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
    INSECURE_DEFAULT_SECRET_KEY,
    LOOPBACK_HOSTS,
    AuthSettings,
    GroupMapping,
    OIDCSettings,
    secret_key_is_insecure,
)
from pointlessql.config._settings._features import (
    AiFunctionsSettings,
    ApiKeyAclSettings,
    ApiKeyLifecycleSettings,
    BitemporalSettings,
    BranchSettings,
    CatalogMcpSettings,
    CoeditSettings,
    ConventionsSettings,
    DataProductsSettings,
    EditorChatSettings,
    EventPortSettings,
    LensSettings,
    NotificationsSettings,
    SqlExecutionApiSettings,
    SQLSettings,
)
from pointlessql.config._settings._infra import (
    CDFTailSettings,
    EgressSettings,
    ExecutorSettings,
    ExternalWritesSettings,
    LoggingSettings,
    ObservabilitySettings,
    RateLimitSettings,
    SchedulerSettings,
    ServerSettings,
)
from pointlessql.config._settings._integrations import (
    AppsSettings,
    DBTSettings,
    HermesSettings,
    JupyterSettings,
    MLflowSettings,
    ServingSettings,
    SoyuzSettings,
    WorkspaceReposSettings,
)
from pointlessql.config._settings._privileges import PrivilegeSettings
from pointlessql.config._settings._storage import (
    CanvasFileIoSettings,
    DatabaseSettings,
    DeltaSettings,
)


class Settings(BaseSettings):
    """Root settings aggregating every sub-model.

    Each nested model is constructed via ``default_factory`` so that
    environment variables are read at instantiation time, not at class
    definition / import time.  The sub-models own their own
    ``env_prefix`` and can be instantiated independently in tests.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_")

    server: ServerSettings = Field(default_factory=ServerSettings)
    egress: EgressSettings = Field(default_factory=EgressSettings)
    executor: ExecutorSettings = Field(default_factory=ExecutorSettings)
    soyuz: SoyuzSettings = Field(default_factory=SoyuzSettings)
    db: DatabaseSettings = Field(default_factory=DatabaseSettings)
    auth: AuthSettings = Field(default_factory=AuthSettings)
    oidc: OIDCSettings = Field(default_factory=OIDCSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    observability: ObservabilitySettings = Field(default_factory=ObservabilitySettings)
    rate_limit: RateLimitSettings = Field(default_factory=RateLimitSettings)
    jupyter: JupyterSettings = Field(default_factory=JupyterSettings)
    scheduler: SchedulerSettings = Field(default_factory=SchedulerSettings)
    audit: AuditSettings = Field(default_factory=AuditSettings)
    delta: DeltaSettings = Field(default_factory=DeltaSettings)
    canvas_file_io: CanvasFileIoSettings = Field(default_factory=CanvasFileIoSettings)
    sql: SQLSettings = Field(default_factory=SQLSettings)
    sql_execution_api: SqlExecutionApiSettings = Field(default_factory=SqlExecutionApiSettings)
    ai_functions: AiFunctionsSettings = Field(default_factory=AiFunctionsSettings)
    api_key_lifecycle: ApiKeyLifecycleSettings = Field(default_factory=ApiKeyLifecycleSettings)
    api_key_acl: ApiKeyAclSettings = Field(default_factory=ApiKeyAclSettings)
    editor_chat: EditorChatSettings = Field(default_factory=EditorChatSettings)
    agent_runs: AgentRunsSettings = Field(default_factory=AgentRunsSettings)
    audit_stream: AuditStreamSettings = Field(default_factory=AuditStreamSettings)
    external_writes: ExternalWritesSettings = Field(default_factory=ExternalWritesSettings)
    cdf_tail: CDFTailSettings = Field(default_factory=CDFTailSettings)
    branch: BranchSettings = Field(default_factory=BranchSettings)
    conventions: ConventionsSettings = Field(default_factory=ConventionsSettings)
    bitemporal: BitemporalSettings = Field(default_factory=BitemporalSettings)
    event_port: EventPortSettings = Field(default_factory=EventPortSettings)
    data_products: DataProductsSettings = Field(default_factory=DataProductsSettings)
    notifications: NotificationsSettings = Field(default_factory=NotificationsSettings)
    workspace_repos: WorkspaceReposSettings = Field(default_factory=WorkspaceReposSettings)
    mlflow: MLflowSettings = Field(default_factory=MLflowSettings)
    serving: ServingSettings = Field(default_factory=ServingSettings)
    apps: AppsSettings = Field(default_factory=AppsSettings)
    dbt: DBTSettings = Field(default_factory=DBTSettings)
    hermes: HermesSettings = Field(default_factory=HermesSettings)
    lens: LensSettings = Field(default_factory=LensSettings)
    catalog_mcp: CatalogMcpSettings = Field(default_factory=CatalogMcpSettings)
    coedit: CoeditSettings = Field(default_factory=CoeditSettings)
    privilege: PrivilegeSettings = Field(default_factory=PrivilegeSettings)


def assert_secret_key_safe(settings: Settings) -> None:
    """Refuse to boot with an insecure JWT key on a reachable address.

    A clean checkout boots on loopback with the public placeholder key
    so first-run needs no configuration.  The moment the server binds a
    non-loopback host (``0.0.0.0`` in a container, a LAN address), that
    placeholder — or any too-short key — would let anyone forge admin
    session tokens, so we fail loud at startup and name the env var to
    set instead of silently signing with a guessable key.

    Args:
        settings: The resolved root settings.

    Raises:
        RuntimeError: When the signing key is insecure
            (:func:`secret_key_is_insecure`) and the server is bound to
            a publicly reachable, non-:data:`LOOPBACK_HOSTS` address.
    """
    if settings.server.host in LOOPBACK_HOSTS:
        return
    if secret_key_is_insecure(settings.auth.secret_key):
        raise RuntimeError(
            "POINTLESSQL_AUTH_SECRET_KEY is unset or insecure while the server is "
            f"bound to {settings.server.host!r}. Generate a strong key, e.g. "
            "`python -c 'import secrets; print(secrets.token_urlsafe(48))'`, and set "
            "POINTLESSQL_AUTH_SECRET_KEY before starting outside loopback."
        )


__all__ = [
    "INSECURE_DEFAULT_SECRET_KEY",
    "LOOPBACK_HOSTS",
    "AgentRunsSettings",
    "AiFunctionsSettings",
    "ApiKeyAclSettings",
    "AppsSettings",
    "ApiKeyLifecycleSettings",
    "AuditSettings",
    "AuditStreamSettings",
    "AuthSettings",
    "BitemporalSettings",
    "BranchSettings",
    "CDFTailSettings",
    "ObservabilitySettings",
    "CanvasFileIoSettings",
    "CatalogMcpSettings",
    "CoeditSettings",
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
    "GroupMapping",
    "HermesSettings",
    "JupyterSettings",
    "LensSettings",
    "LineageRetentionSettings",
    "LoggingSettings",
    "MLflowSettings",
    "NotificationsSettings",
    "OIDCSettings",
    "PrivilegeSettings",
    "RateLimitSettings",
    "SQLSettings",
    "SchedulerSettings",
    "ServerSettings",
    "ServingSettings",
    "Settings",
    "SoyuzSettings",
    "SqlExecutionApiSettings",
    "WorkspaceReposSettings",
    "assert_secret_key_safe",
    "secret_key_is_insecure",
]
