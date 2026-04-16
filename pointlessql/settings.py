"""Application settings loaded from environment variables."""

from __future__ import annotations

from typing import Literal

from pydantic import computed_field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """PointlesSQL configuration.

    All fields can be overridden via environment variables prefixed with
    ``POINTLESSQL_``, e.g. ``POINTLESSQL_SOYUZ_CATALOG_URL``.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_")

    soyuz_catalog_url: str = "http://127.0.0.1:8080"

    host: str = "127.0.0.1"
    port: int = 8000

    jupyter_enabled: bool = True
    jupyter_port: int = 8888

    engine: str = "pandas"

    database_url: str = "sqlite:///./pointlessql.db"
    secret_key: str = "change-me-in-production"
    jwt_expiry_hours: int = 168  # 7 days

    # Public base URL for callback URIs (e.g. "https://pql.example.com").
    # When unset, redirect URIs are derived from the incoming request.
    base_url: str | None = None

    # OIDC / OAuth2 — opt-in. Set both discovery_url and client_id to enable.
    oidc_discovery_url: str | None = None
    oidc_client_id: str | None = None
    oidc_client_secret: str | None = None

    # Logging. POINTLESSQL_LOG_FORMAT is case-sensitive — pydantic-settings
    # rejects "JSON"/"Text". Use lowercase tokens.
    log_level: str = "INFO"
    log_format: Literal["text", "json"] = "text"

    # Scheduler. Defaults to enabled; tests flip the toggle off in
    # conftest so the background loop never ticks during normal runs.
    scheduler_enabled: bool = True
    scheduler_tick_seconds: int = 30
    # Global ceiling on concurrently-running job runs across every job
    # in the install. A per-job semaphore layered on top of this one
    # (``Job.max_parallel_runs``) enforces the per-job budget.
    scheduler_max_concurrent_runs: int = 4

    @computed_field  # type: ignore[prop-decorator]
    @property
    def oidc_enabled(self) -> bool:
        """Whether OIDC login is available.

        Empty-string env overrides (e.g. ``POINTLESSQL_OIDC_DISCOVERY_URL=``
        passed through a docker-compose ``${VAR:-}`` fallback) should count
        as "not configured" — truthy check catches both ``None`` and ``""``
        so the SSO button stays hidden and ``/auth/sso`` does not attempt a
        discovery call with an empty URL (Sprint 23 BUG-23-01).
        """
        return bool(self.oidc_discovery_url) and bool(self.oidc_client_id)
