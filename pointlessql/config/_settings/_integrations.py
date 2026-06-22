"""Third-party integration settings.

Six sub-models pointing at external services or co-resident
subprocesses: soyuz-catalog (the UC backend), Jupyter, dbt-docs,
MLflow Tracking, the workspace-repo cloner, and the Hermes agent
dashboard.  Each one carries its own connection / spawn config;
nothing is shared, but they all describe "PointlesSQL plus another
process."
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from pointlessql.config._settings._paths import PROJECT_ROOT, STARTUP_CWD


class SoyuzSettings(BaseSettings):
    """soyuz-catalog upstream configuration.

    Reads ``POINTLESSQL_SOYUZ_*`` environment variables.  ``catalog_url``
    is the base URL of the running soyuz-catalog server.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SOYUZ_")

    catalog_url: str = "http://127.0.0.1:8080"


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
    in other papermill runs and the workspace service.
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
        to :data:`STARTUP_CWD` (captured at module import, before any
        papermill tick can run) pins the absolute path at a value
        that's invariant across concurrent ``Settings()`` constructions
        in papermill workers. ``resolve()`` on an already-absolute path
        does not consult the current CWD, so the output is
        deterministic.

        Args:
            value: The raw path value from env or default.

        Returns:
            Path: Absolute path anchored to startup CWD.
        """
        if value.is_absolute():
            return value.resolve()
        return (STARTUP_CWD / value).resolve()


class WorkspaceReposSettings(BaseSettings):
    """Workspace-repo clone + sync configuration.

    Reads ``POINTLESSQL_REPOS_*`` environment variables.  The
    foundation sub-sprint pinned every value at a safe default:
    ``sync_interval_seconds`` defaults to ``0`` (cron loop
    dormant; manual syncs and webhook syncs work regardless), and
    ``base_dir`` anchors clones beside the repo root so a fresh
    install needs zero env-vars to start cloning repos.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_REPOS_")

    base_dir: Path = Field(default_factory=lambda: PROJECT_ROOT / "repos")
    sync_interval_seconds: int = 0
    clone_timeout_seconds: int = 300
    pull_timeout_seconds: int = 120
    allow_file_protocol: bool = False
    """Permit ``file://`` clone URLs and the git ``file`` transport.

    Off by default — ``file://`` lets a clone read local repos, so it is
    an SSRF/LFI seam in a multi-tenant deployment.  Enable it only for
    installs that deliberately clone from a local path (and the test
    suite, which clones throwaway file:// repos)."""
    yaml_search_globs: tuple[str, ...] = (
        "pointlessql.yaml",
        "**/pointlessql.yaml",
    )

    @field_validator("base_dir", mode="after")
    @classmethod
    def _resolve_base_dir(cls, value: Path) -> Path:
        """Anchor *base_dir* to the startup CWD when relative.

        Mirrors :class:`JupyterSettings`'s anchoring trick — papermill
        and other workers can issue process-wide ``os.chdir`` calls,
        so we resolve eagerly to keep clone paths stable across
        concurrent ``Settings()`` constructions.
        """
        if value.is_absolute():
            return value.resolve()
        return (STARTUP_CWD / value).resolve()


class DBTSettings(BaseSettings):
    """Embedded ``dbt docs serve`` subprocess + reverse-proxy configuration.

    Reads ``POINTLESSQL_DBT_*`` environment variables.  When
    ``enabled=True`` and the optional ``dbt-duckdb`` package is
    installed (``pip install pointlessql[dbt]``), the FastAPI
    ``lifespan`` spawns ``dbt docs serve`` on ``docs_port`` *if* the
    project has a compiled ``target/manifest.json``.  Without a
    manifest we log info and leave the subprocess unstarted so the
    ``/dbt`` page renders a friendly hint rather than a noisy error.

    The subprocess is independent of the on-demand
    ``/api/dbt/run|test|compile`` endpoints: those
    spawn ``dbt`` as one-shot CLI invocations and write
    ``target/manifest.json`` themselves.  Once the first compile has
    landed, the docs subprocess becomes startable on the next
    PointlesSQL restart.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_DBT_")

    enabled: bool = True
    docs_port: int = 5002
    project_dir: Path = Path("examples/dbt_project")
    profiles_dir: Path = Path("examples/dbt_project/profiles")
    target: str = "dev"
    timeout_seconds: int = 600


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
    scheme; see 's ``uc_oss_proto_diff.md`` for why
    ``uc:`` not ``uc-oss:``). Operators override via
    ``POINTLESSQL_MLFLOW_BACKEND_STORE_URI`` etc.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_MLFLOW_")

    enabled: bool = True
    port: int = 5000
    backend_store_uri: str | None = None
    artifact_root: str | None = None
    registry_uri: str | None = None


class ServingSettings(BaseSettings):
    """Model-serving worker pool configuration.

    Reads ``POINTLESSQL_SERVING_*`` environment variables.  Serving
    workers are ``mlflow models serve`` subprocesses on loopback
    ports starting at ``port_range_start``; ``max_endpoints`` caps
    how many may run at once (each loads a full model into memory).
    ``startup_timeout_seconds`` bounds the health-poll after spawn,
    ``invocation_timeout_seconds`` bounds a single proxied scoring
    request.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_SERVING_")

    port_range_start: int = 9100
    max_endpoints: int = 8
    startup_timeout_seconds: float = 120.0
    invocation_timeout_seconds: float = 30.0


class AppsSettings(BaseSettings):
    """Hosted-apps worker pool configuration.

    Reads ``POINTLESSQL_APPS_*`` environment variables.  App workers
    are per-app subprocesses (uvicorn / streamlit / custom command)
    on loopback ports starting at ``port_range_start``; ``max_apps``
    caps concurrency.  ``startup_timeout_seconds`` bounds the
    post-spawn health poll, ``request_timeout_seconds`` bounds one
    proxied request.  ``apps_root`` is where app sources are
    materialised; ``None`` falls back to a temp-dir subfolder.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_APPS_")

    port_range_start: int = 9200
    max_apps: int = 8
    startup_timeout_seconds: float = 60.0
    request_timeout_seconds: float = 30.0
    apps_root: Path | None = None


class HermesSettings(BaseSettings):
    """Embedded Hermes agent dashboard + reverse-proxy configuration.

    Reads ``POINTLESSQL_HERMES_*`` environment variables.  When
    ``enabled=True`` PointlesSQL surfaces an "Agent" hub whose
    ``/hermes/...`` path reverse-proxies the Hermes web dashboard
    (its React SPA + the in-browser chat WebSocket) through
    PointlesSQL's own auth layer, so the agent is operated from
    inside the control-room rather than a separate app.

    Two process models share one proxy:

    - ``mode="managed"`` — PointlesSQL spawns ``hermes dashboard`` as
      a child process (zero-config local dev, mirroring the MLflow
      subprocess).  ``command`` is the launcher on ``PATH``; the
      dashboard binds ``host`` starting at ``port_base``.
    - ``mode="external"`` — the operator runs Hermes elsewhere (a
      Docker service or a remote host) and PointlesSQL only proxies
      to ``dashboard_url``.

    ``isolation`` controls whether every operator shares one Hermes
    identity (``"shared"``) or gets a private managed instance with
    its own home directory (``"per_user"``).  The latter is the only
    way to truly isolate sessions because a single Hermes process
    owns one home directory; ``home_root`` is the parent that holds
    the per-user homes, ``max_instances`` caps concurrent processes
    and ``idle_ttl_seconds`` reaps ones nobody is using.

    ``session_token`` pins the dashboard's pre-shared token so the
    proxy can inject it on every forwarded request; left ``None`` a
    fresh token is minted per managed instance.  ``chat_enabled``
    launches the POSIX-only chat PTY.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_HERMES_")

    enabled: bool = False
    mode: Literal["managed", "external"] = "managed"
    isolation: Literal["shared", "per_user"] = "shared"
    dashboard_url: str = "http://127.0.0.1:9119"
    command: str = "hermes"
    host: str = "127.0.0.1"
    port_base: int = 9119
    home_root: Path | None = None
    session_token: str | None = None
    chat_enabled: bool = True
    # The very first managed launch builds the Hermes web bundle, which
    # can take roughly a minute; later launches reuse the cached build
    # and come up in a few seconds.
    startup_timeout_seconds: int = 150
    max_instances: int = 8
    idle_ttl_seconds: int = 1800
