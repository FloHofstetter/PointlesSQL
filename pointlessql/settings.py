"""Application settings loaded from environment variables.

Sprint 45 migrated the single flat :class:`Settings` into nested
sub-models with per-sub-model ``env_prefix``.  The shoreguard-fresh
pattern is copied 1:1: each sub-model owns its own ``BaseSettings``
namespace and the root :class:`Settings` composes them via
``Field(default_factory=…)`` so every ``Settings()`` instantiation
reads the env fresh (important for papermill workers that spawn with
a CWD snapshot).

Most environment variables are unchanged because the old flat prefix
already overlapped the new sub-model prefixes (``POINTLESSQL_RATE_LIMIT_*``,
``POINTLESSQL_SCHEDULER_*``, ``POINTLESSQL_OIDC_*``, ``POINTLESSQL_JUPYTER_*``,
``POINTLESSQL_SOYUZ_CATALOG_URL``, ``POINTLESSQL_LOG_LEVEL``,
``POINTLESSQL_LOG_FORMAT`` all still work).  The breaking subset
(``POINTLESSQL_HOST``, ``POINTLESSQL_DATABASE_URL``,
``POINTLESSQL_SECRET_KEY``, ``POINTLESSQL_NOTEBOOKS_DIR`` and a few
others) is documented in ``CHANGELOG.md`` with a full mapping.
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

    ``secret_key_previous`` (Sprint 46) is an optional grace-period
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

    @computed_field  # type: ignore[prop-decorator]
    @property
    def enabled(self) -> bool:
        """Whether OIDC login is available.

        Empty-string env overrides (e.g. ``POINTLESSQL_OIDC_DISCOVERY_URL=``
        passed through a docker-compose ``${VAR:-}`` fallback) should
        count as "not configured" — truthy check catches both ``None``
        and ``""`` so the SSO button stays hidden and ``/auth/sso``
        does not attempt a discovery call with an empty URL
        (Sprint 23 BUG-23-01).

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
    """Sprint-43 rate limits on ``/auth/*``.

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


class AuditSettings(BaseSettings):
    """Audit-log retention and cleanup configuration (Sprint 48).

    Reads ``POINTLESSQL_AUDIT_*`` environment variables. Rows older
    than ``retention_days`` are deleted by the scheduler's periodic
    audit-cleanup tick.  Set ``retention_days=0`` to keep every
    audit row forever (the pre-Sprint-48 behaviour).
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_AUDIT_")

    retention_days: int = 365
    cleanup_interval_seconds: int = 86400  # once per day


class DeltaSettings(BaseSettings):
    """Delta-Lake compute engine selection.

    Reads ``POINTLESSQL_DELTA_*`` environment variables.  Currently
    ``pandas`` is the only supported ``engine`` value; reserved for
    future ``spark`` / ``daft`` / ``polars`` backends.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_DELTA_")

    engine: str = "pandas"


class SQLSettings(BaseSettings):
    """Phase-12 ad-hoc SQL editor configuration.

    Reads ``POINTLESSQL_SQL_*`` environment variables.  ``enabled``
    hides ``/sql`` and rejects ``/api/sql/*`` at the route layer when
    ``False``.  ``max_rows`` caps the LIMIT DuckDB applies to every
    query; ``query_timeout_seconds`` is wired in Sprint 52 but the
    knob is declared here so operators can set it once and forget.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SQL_")

    enabled: bool = True
    max_rows: int = 10_000
    query_timeout_seconds: int = 60


class ConventionsSettings(BaseSettings):
    """Phase-13.5 Medallion conventions config-file pointer.

    Reads ``POINTLESSQL_CONVENTIONS_*`` environment variables.  When
    ``path`` is ``None`` (the default) the loader returns the built-
    in Medallion defaults from
    :mod:`pointlessql.conventions._defaults`; when set it points at
    a ``pointlessql.yaml`` whose top-level fields shallow-merge over
    those defaults.  See
    [`docs/data-layers.md`](../../docs/data-layers.md) for the prose
    contract and ADR ``0002-duckdb-first`` for the compute opinion
    this phase codifies.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_CONVENTIONS_")

    path: Path | None = None


class Settings(BaseSettings):
    """Root settings aggregating every sub-model.

    Each nested model is constructed via ``default_factory`` so that
    environment variables are read at instantiation time, not at class
    definition / import time.  The sub-models own their own
    ``env_prefix`` and can be instantiated independently in tests — see
    the BREAKING env-var mapping in ``CHANGELOG.md`` for the handful of
    variable names that had to change in Sprint 45.
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
    conventions: ConventionsSettings = Field(default_factory=ConventionsSettings)
