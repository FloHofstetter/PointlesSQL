"""Application settings loaded from environment variables.

The root :class:`Settings` is split into nested sub-models with
per-sub-model ``env_prefix``.  Each sub-model owns its own
``BaseSettings`` namespace and the root composes them via
``Field(default_factory=…)`` so every ``Settings()`` instantiation
reads the env fresh (important for papermill workers that spawn with
a CWD snapshot).
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Captured at module import time — before any papermill ``chdir`` can
# skew the process CWD. All relative-path defaults in
# :class:`JupyterSettings` anchor against this value so a later
# ``Settings()`` instantiation (e.g. fresh settings built inside a
# papermill worker that is racing another papermill's ``os.chdir``)
# resolves to the same absolute path as the scheduler's startup-time
# settings (BUG-28-02).
_STARTUP_CWD = Path.cwd()


class ServerSettings(BaseSettings):
    """HTTP server bind address and public URL.

    Reads ``POINTLESSQL_SERVER_*`` environment variables.  ``host`` and
    ``port`` drive uvicorn; ``base_url`` is the public URL used when
    constructing OIDC callback URIs (``None`` means derive from the
    incoming request).
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SERVER_")

    host: str = "127.0.0.1"
    port: int = 8000
    base_url: str | None = None


class SoyuzSettings(BaseSettings):
    """soyuz-catalog upstream configuration.

    Reads ``POINTLESSQL_SOYUZ_*`` environment variables.  ``catalog_url``
    is the base URL of the running soyuz-catalog server.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SOYUZ_")

    catalog_url: str = "http://127.0.0.1:8080"


class DatabaseSettings(BaseSettings):
    """PointlesSQL's own SQLAlchemy database.

    Reads ``POINTLESSQL_DB_*`` environment variables.  Only covers
    PointlesSQL's metadata (sessions, saved queries, audit log,
    scheduler state) — soyuz-catalog owns the lakehouse metadata.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_DB_")

    url: str = "sqlite:///./pointlessql.db"


class AuthSettings(BaseSettings):
    """JWT signing and session lifetime.

    Reads ``POINTLESSQL_AUTH_*`` environment variables.  ``secret_key``
    MUST be overridden in production.  ``jwt_expiry_hours`` defaults
    to 168 (seven days).

    ``secret_key_previous`` is an optional grace-period
    key: when rotating the primary key operators set
    ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS`` to the *old* value before
    changing ``POINTLESSQL_AUTH_SECRET_KEY`` to the new one, wait for
    the current ``jwt_expiry_hours`` window so every outstanding
    session re-signs on its next request, then drop the previous-
    key env var.  New tokens are always signed with the primary key;
    verification falls back to the previous key only if the primary
    rejects the token.  When unset, the rotation fallback is
    disabled and a changed primary key invalidates every live
    session immediately.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AUTH_")

    secret_key: str = "change-me-in-production"
    secret_key_previous: str | None = None
    jwt_expiry_hours: int = 168  # 7 days


class OIDCSettings(BaseSettings):
    """OpenID Connect (opt-in) provider configuration.

    Reads ``POINTLESSQL_OIDC_*`` environment variables.  Set both
    ``discovery_url`` (the provider's ``.well-known/openid-configuration``
    URL) and ``client_id`` to enable the SSO login path.  The
    ``client_secret`` may be omitted for PKCE-only public clients.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_OIDC_")

    discovery_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    http_timeout_seconds: float = 10.0

    @computed_field  # type: ignore[prop-decorator]
    @property
    def enabled(self) -> bool:
        """Whether OIDC login is available.

        Empty-string env overrides (e.g. ``POINTLESSQL_OIDC_DISCOVERY_URL=``
        passed through a docker-compose ``${VAR:-}`` fallback) should
        count as "not configured" — truthy check catches both ``None``
        and ``""`` so the SSO button stays hidden and ``/auth/sso``
        does not attempt a discovery call with an empty URL
        (BUG-23-01).

        Returns:
            bool: ``True`` iff both ``discovery_url`` and ``client_id``
                are set to non-empty strings.
        """
        return bool(self.discovery_url) and bool(self.client_id)


class LoggingSettings(BaseSettings):
    """Runtime logging configuration.

    Reads ``POINTLESSQL_LOG_*`` environment variables.  ``level`` is a
    Python logging-level name (``DEBUG``, ``INFO``, …).  ``format``
    controls whether log records render as human-readable text or
    single-line JSON for ingestion.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_LOG_")

    level: str = "INFO"
    format: Literal["text", "json"] = "text"


class RateLimitSettings(BaseSettings):
    """Rate limits on ``/auth/*``.

    Reads ``POINTLESSQL_RATE_LIMIT_*`` environment variables.  Fixed-
    window counters in ``rate_limit_events``; defaults are tuned for a
    single-node deploy — ten login attempts per IP every ten minutes is
    well above any human retry pattern but below what a credential-
    stuffing script expects.  ``trust_x_forwarded_for`` stays OFF by
    default because trusting it unconditionally would let any client
    forge the header and escape the per-IP bucket.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_RATE_LIMIT_")

    enabled: bool = True
    login_ip_count: int = 10
    login_ip_window_s: int = 600
    login_email_count: int = 5
    login_email_window_s: int = 600
    register_ip_count: int = 5
    register_ip_window_s: int = 3600
    oidc_ip_count: int = 20
    oidc_ip_window_s: int = 600
    trust_x_forwarded_for: bool = False


class JupyterSettings(BaseSettings):
    """Embedded JupyterLab and notebook-executor configuration.

    Reads ``POINTLESSQL_JUPYTER_*`` environment variables.  The
    ``notebooks_dir`` default points at ``notebooks/`` relative to the
    process CWD (``./notebooks`` in dev, ``/app/notebooks`` in Docker
    via the compose bind mount).  Relative paths are eagerly resolved
    against the startup CWD in the validator below so later
    ``.resolve()`` calls are CWD-independent — critical because
    Papermill's ``cwd=`` argument does a process-wide ``os.chdir``
    that races with concurrent ``Path("notebooks").resolve()`` calls
    in other papermill runs and the workspace service (BUG-28-02).
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_JUPYTER_")

    enabled: bool = True
    port: int = 8888
    notebooks_dir: Path = Path("notebooks")
    runs_dir: Path = Path("notebooks/runs")
    execute_timeout_seconds: int = 300

    @field_validator("notebooks_dir", "runs_dir", mode="after")
    @classmethod
    def _resolve_jupyter_paths(cls, value: Path) -> Path:
        """Anchor Jupyter paths to the process startup CWD.

        Papermill invokes ``os.chdir`` (process-wide, not thread-local)
        when its ``cwd=`` argument is set, so concurrent papermill runs
        race with any code that computes ``Path("notebooks").resolve()``
        later — the observer ends up with
        ``/app/notebooks/notebooks`` because CWD flipped to the
        notebooks dir mid-run. Anchoring a relative path
        to :data:`_STARTUP_CWD` (captured at module import, before any
        papermill tick can run) pins the absolute path at a value
        that's invariant across concurrent ``Settings()`` constructions
        in papermill workers (BUG-28-02). ``resolve()`` on an already-
        absolute path does not consult the current CWD, so the output
        is deterministic.

        Args:
            value: The raw path value from env or default.

        Returns:
            Path: Absolute path anchored to startup CWD.
        """
        if value.is_absolute():
            return value.resolve()
        return (_STARTUP_CWD / value).resolve()


class SchedulerSettings(BaseSettings):
    """Background job scheduler configuration.

    Reads ``POINTLESSQL_SCHEDULER_*`` environment variables.  Tests
    flip ``enabled=False`` in ``conftest.py`` so the background loop
    never ticks during normal runs; dedicated scheduler tests flip it
    back on.  ``max_concurrent_runs`` is a global ceiling across every
    job; a per-job semaphore (``Job.max_parallel_runs``) layers on top.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SCHEDULER_")

    enabled: bool = True
    tick_seconds: int = 30
    max_concurrent_runs: int = 4


class LineageRetentionSettings(BaseSettings):
    """Per-axis TTL on the four lineage tables (Sprint 20.2).

    Reads ``POINTLESSQL_AUDIT_LINEAGE_RETENTION_*`` environment
    variables.  Each ``*_days`` field is either a positive integer
    (rows older than ``now - N days`` get pruned at the next tick)
    or ``None`` / ``0`` (axis never pruned).

    Defaults follow the Phase 20 plan:

    * ``row_edges`` and ``row_rejects`` — 365 days (one operating
      year, enough for compliance retrospectives).
    * ``value_changes`` — 730 days (longer because value-level
      auditing is the strongest forensic surface; doubling the
      window costs little if redaction is on).
    * ``column_map`` — never (small volume, useful as a stable
      schema-evolution record).

    The pruner runs as a scheduler job at 03:00 UTC daily by default
    (off-peak for most operating timezones).
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AUDIT_LINEAGE_RETENTION_")

    row_edges_days: int | None = 365
    row_rejects_days: int | None = 365
    column_map_days: int | None = None
    value_changes_days: int | None = 730
    cron: str = "0 3 * * *"


class AuditSettings(BaseSettings):
    """Audit-log retention, cleanup, and cockpit configuration.

    Reads ``POINTLESSQL_AUDIT_*`` environment variables. Rows older
    than ``retention_days`` are deleted by the scheduler's periodic
    audit-cleanup tick.  Set ``retention_days=0`` to keep every
    audit row forever (disables retention entirely).

    Phase 18 added cockpit knobs:

    * ``anomaly_baseline_window_days`` — N-day rolling window the
      ``/api/audit/anomalies`` endpoint compares observed values
      against.  7 days mirrors the Sprint 19.0 Grafana panel.
    * ``anomaly_threshold_sigma`` — observations more than this many
      standard deviations above the baseline mean count as ``warn``
      (≥ σ) or ``critical`` (≥ 2σ × this).  Default 2.0 matches the
      common "two-sigma rule" most operators expect.
    * ``pii_mask_default`` — when ``True`` (the default) values whose
      target column is tagged ``PII`` in soyuz are rendered masked.
      Set to ``False`` to disable masking globally (single-tenant
      deployments where every viewer is already trusted).
    * ``pii_cache_ttl_seconds`` — how long the PII tag resolver
      caches a ``(table, column)`` lookup before re-querying soyuz.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AUDIT_")

    retention_days: int = 365
    cleanup_interval_seconds: int = 86400  # once per day
    anomaly_baseline_window_days: int = 7
    anomaly_threshold_sigma: float = 2.0
    pii_mask_default: bool = True
    pii_cache_ttl_seconds: int = 600
    pii_mode: Literal["store_clear", "hash_only", "redact_with_audit_log"] = "hash_only"
    pii_hash_secret: str | None = None
    lineage_retention: LineageRetentionSettings = Field(default_factory=LineageRetentionSettings)


class DeltaSettings(BaseSettings):
    """Delta-Lake compute engine selection.

    Reads ``POINTLESSQL_DELTA_*`` environment variables.  Currently
    ``pandas`` is the only supported ``engine`` value; reserved for
    future ``spark`` / ``daft`` / ``polars`` backends.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_DELTA_")

    engine: str = "pandas"


class SQLSettings(BaseSettings):
    """Ad-hoc SQL editor configuration.

    Reads ``POINTLESSQL_SQL_*`` environment variables.  ``enabled``
    hides ``/sql`` and rejects ``/api/sql/*`` at the route layer when
    ``False``.  ``max_rows`` caps the LIMIT DuckDB applies to every
    query; ``query_timeout_seconds`` aborts a long-running query so
    operators can set it once and forget.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SQL_")

    enabled: bool = True
    max_rows: int = 10_000
    query_timeout_seconds: int = 60
    cost_gate_threshold_rows: int = 1_000_000


class AgentRunsSettings(BaseSettings):
    """Agent-run lifecycle webhook configuration.

    Reads ``POINTLESSQL_AGENT_RUNS_*`` environment variables.  When
    ``webhook_url`` is set, the lifecycle emitter POSTs a
    CloudEvents envelope (``pointlessql.agent_run.started`` /
    ``.completed`` / ``.failed``) to it on every lifecycle
    transition.  Optional ``webhook_hmac_secret`` populates the
    ``X-PointlesSQL-Signature: sha256=<hex>`` header so the receiver
    can verify the payload.

    The single-URL shape is deliberately small — a richer
    per-destination subscription model (multiple URLs, per-event-type
    filters) is a future extension once the control-room UI surfaces it.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AGENT_RUNS_")

    webhook_url: str | None = None
    webhook_hmac_secret: str | None = None


class AuditStreamSettings(BaseSettings):
    """Phase 20 audit-stream forwarder configuration.

    Reads ``POINTLESSQL_AUDIT_STREAM_*`` environment variables.  All
    sinks are off by default — the stream only fires when at least
    one ``is_active`` row exists in the ``audit_sinks`` table AND
    the corresponding ``*_enabled`` toggle here is ``True``.  The
    two-gate design lets an admin pre-configure destinations without
    accidentally turning on outbound traffic.

    For the agent-run lifecycle events (``started`` / ``completed``
    / ``failed`` / ``tool_call`` / ``rollback.executed``) the
    existing single-URL pipeline at
    :class:`AgentRunsSettings` keeps working unchanged; flip
    ``mirror_lifecycle_to_sinks`` to ``True`` to additionally fan
    those envelopes into the audit-sinks table for a unified trail.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AUDIT_STREAM_")

    enabled: bool = False
    mirror_lifecycle_to_sinks: bool = False


class ExternalWritesSettings(BaseSettings):
    """External-write detection scanner configuration.

    Reads ``POINTLESSQL_EXTERNAL_WRITES_*`` environment variables.
    The Sprint 14.3 scanner walks ``DeltaTable.history()`` per UC
    table and INSERT-OR-IGNOREs into ``unattributed_writes`` for
    every commit not matched by an ``agent_run_operations`` row.

    ``scan_interval_seconds`` defaults to ``0`` (disabled) because
    on a single-node vServer the per-table ``DeltaTable.history()``
    cost adds up; admins enable it deliberately.  The on-demand
    ``POST /api/admin/external-writes/scan`` route works regardless.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_EXTERNAL_WRITES_")

    scan_interval_seconds: int = 0
    history_limit: int = 200


class BranchSettings(BaseSettings):
    """Delta-Branching strategy + auto-cleanup configuration (Sprint 16.5).

    Reads ``POINTLESSQL_BRANCH_*`` environment variables.  Two
    independent concerns:

    * ``cloud_strategy`` — how :func:`pql.branch` handles a parent
      schema whose ``storage_root`` is on object storage (``s3://``,
      ``gs://``, ``abfss://``, ``wasbs://``).  Cloud has no symlink
      primitive so the zero-copy ideal from ADR-0003 is unavailable
      there.  ``"error"`` (the default) refuses cloud branching
      outright; ``"deep_copy"`` opts into the bigger storage cost so
      branching works everywhere.  Local FS always uses the
      symlink path.
    * ``auto_cleanup_*`` — opt-in scheduler job that discards old
      ``status=active`` branches so storage doesn't drift.  Default
      disabled (``auto_cleanup_enabled=False``); operators flip it
      on once they trust the discard primitive.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_BRANCH_")

    cloud_strategy: Literal["deep_copy", "error"] = "error"
    auto_cleanup_enabled: bool = False
    auto_cleanup_retention_days: int = 30
    auto_cleanup_cron: str = "0 2 * * *"


class ConventionsSettings(BaseSettings):
    """Medallion conventions config-file pointer.

    Reads ``POINTLESSQL_CONVENTIONS_*`` environment variables.  When
    ``path`` is ``None`` (the default) the loader returns the built-
    in Medallion defaults from
    :mod:`pointlessql.conventions._defaults`; when set it points at
    a ``pointlessql.yaml`` whose top-level fields shallow-merge over
    those defaults.  See
    [`docs/data-layers.md`](../../docs/data-layers.md) for the prose
    contract and ADR ``0002-duckdb-first`` for the compute opinion
    this codifies.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_CONVENTIONS_")

    path: Path | None = None


class MLflowSettings(BaseSettings):
    """Embedded MLflow Tracking subprocess + reverse-proxy configuration.

    Reads ``POINTLESSQL_MLFLOW_*`` environment variables. When
    ``enabled=True`` and the optional ``mlflow`` package is installed
    (``pip install pointlessql[ml]``), the FastAPI ``lifespan``
    spawns ``mlflow server`` on ``port`` and the
    :class:`pointlessql.api.mlflow_proxy.router` forwards
    ``/mlflow/...`` requests through PointlesSQL's auth layer.

    The three URI fields default to ``None`` because they're derived
    at startup time from the soyuz URL and the process CWD:
    ``backend_store_uri`` becomes ``sqlite:///./mlflow.db``,
    ``artifact_root`` becomes ``file://{cwd}/mlflow_artifacts``, and
    ``registry_uri`` becomes ``uc:{soyuz_url}`` (MLflow's UC-OSS
    scheme; see Phase 21.1's ``uc_oss_proto_diff.md`` for why
    ``uc:`` not ``uc-oss:``). Operators override via
    ``POINTLESSQL_MLFLOW_BACKEND_STORE_URI`` etc.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_MLFLOW_")

    enabled: bool = True
    port: int = 5000
    backend_store_uri: str | None = None
    artifact_root: str | None = None
    registry_uri: str | None = None


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
    agent_runs: AgentRunsSettings = Field(default_factory=AgentRunsSettings)
    audit_stream: AuditStreamSettings = Field(default_factory=AuditStreamSettings)
    external_writes: ExternalWritesSettings = Field(default_factory=ExternalWritesSettings)
    branch: BranchSettings = Field(default_factory=BranchSettings)
    conventions: ConventionsSettings = Field(default_factory=ConventionsSettings)
    mlflow: MLflowSettings = Field(default_factory=MLflowSettings)
