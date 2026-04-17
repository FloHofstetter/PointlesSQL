"""Application settings loaded from environment variables."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# Captured at module import time — before any papermill ``chdir`` can
# skew the process CWD. All relative-path defaults in :class:`Settings`
# anchor against this value so a later ``Settings()`` instantiation
# (e.g. fresh settings built inside a papermill worker that is racing
# another papermill's ``os.chdir``) resolves to the same absolute path
# as the scheduler's startup-time settings (BUG-28-02).
_STARTUP_CWD = Path.cwd()


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

    # Root directory that both the embedded JupyterLab subprocess and the
    # Papermill job executor use as their working tree. Defaults to
    # ``notebooks/`` relative to the process CWD (``./notebooks`` in dev,
    # ``/app/notebooks`` in Docker via the compose bind mount). Eagerly
    # resolved to an absolute path in the validator below so later
    # ``.resolve()`` calls are CWD-independent — critical because
    # Papermill's ``cwd=`` argument does a process-wide ``os.chdir`` that
    # races with concurrent ``Path("notebooks").resolve()`` calls in other
    # papermill runs and the workspace service (BUG-28-02).
    notebooks_dir: Path = Path("notebooks")
    # Per-run ceiling enforced by the Papermill executor via
    # ``asyncio.wait_for``. Kernel startup + trivial cells take a few
    # seconds, so 300 s is a comfortable default for interactive-scale
    # notebooks.
    notebook_execute_timeout_seconds: int = 300

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

    @field_validator("notebooks_dir", mode="after")
    @classmethod
    def _resolve_notebooks_dir(cls, value: Path) -> Path:
        """Anchor ``notebooks_dir`` to the process startup CWD.

        Papermill invokes ``os.chdir`` (process-wide, not thread-local)
        when its ``cwd=`` argument is set, so concurrent papermill runs
        race with any code that computes ``Path("notebooks").resolve()``
        later — the observer ends up with
        ``/app/notebooks/notebooks`` because CWD flipped to the
        notebooks dir mid-run. Anchoring a relative ``notebooks_dir``
        to :data:`_STARTUP_CWD` (captured at module import, before any
        papermill tick can run) pins the absolute path at a value
        that's invariant across concurrent ``Settings()`` constructions
        in papermill workers (BUG-28-02). ``resolve()`` on an already-
        absolute path does not consult the current CWD, so the output
        is deterministic.
        """
        if value.is_absolute():
            return value.resolve()
        return (_STARTUP_CWD / value).resolve()

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
