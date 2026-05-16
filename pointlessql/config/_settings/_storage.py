"""Persistence-layer settings: PointlesSQL's own SQLAlchemy DB and Delta engine selection.

Two stateless sub-models that don't share validators or coupling, but
sit together because they both describe *where data lives* (the
metadata DB) and *how it is read* (the Delta compute engine). Anything
about lakehouse metadata is owned by soyuz-catalog — see the project
CLAUDE.md.
"""

from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict

from pointlessql.config._settings._paths import PROJECT_ROOT


class DatabaseSettings(BaseSettings):
    """PointlesSQL's own SQLAlchemy database.

    Reads ``POINTLESSQL_DB_*`` environment variables.  Only covers
    PointlesSQL's metadata (sessions, saved queries, audit log,
    scheduler state) — soyuz-catalog owns the lakehouse metadata.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_DB_")

    # Anchored to the repo root so the default DB location is stable
    # no matter which CWD the server was started from.  Override via
    # ``POINTLESSQL_DB_URL`` when a different location is needed
    # (Docker volumes, multi-tenant installs).
    url: str = f"sqlite:///{PROJECT_ROOT / 'pointlessql.db'}"

    # Pool sizing.  Ignored on SQLite (StaticPool by default for
    # ``:memory:``, or a tiny QueuePool for file DBs); applied to
    # QueuePool on Postgres.
    pool_size: int = 5
    max_overflow: int = 10
    # Recycle connections every N seconds to dodge MITM proxies and
    # PG ``idle_in_transaction_session_timeout`` settings.  30 min
    # default — see docs/admin/postgres-deployment.md for tuning.
    pool_recycle_seconds: int = 1800

    # PG-only.  Applied per-connection via a SET statement_timeout
    # event listener; SQLite has no equivalent and ignores this.
    # 30 s default fits the cockpit's p95 budget; bump for ad-hoc
    # report queries.
    statement_timeout_ms: int = 30000


class DeltaSettings(BaseSettings):
    """Delta-Lake compute engine selection.

    Reads ``POINTLESSQL_DELTA_*`` environment variables.  Currently
    ``pandas`` is the only supported ``engine`` value; reserved for
    future ``spark`` / ``daft`` / ``polars`` backends.
    """

    model_config = SettingsConfigDict(env_prefix="POINTLESSQL_DELTA_")

    engine: str = "pandas"
