"""Database engine, session factory, and embedded Alembic migrations."""

from __future__ import annotations

import logging
from pathlib import Path

from alembic import command
from alembic.config import Config as AlembicConfig
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

_engine: Engine | None = None
_session_factory: sessionmaker[Session] | None = None


def _alembic_dir() -> str:
    """Return the path to the alembic directory shipped inside the package.

    Returns:
        str: Absolute path to the embedded alembic directory.
    """
    return str(Path(__file__).parent / "alembic")


def _alembic_config(url: str) -> AlembicConfig:
    """Build an Alembic config pointing at our embedded migrations.

    Args:
        url: SQLAlchemy database URL.

    Returns:
        AlembicConfig: Configured Alembic config instance.
    """
    cfg = AlembicConfig()
    cfg.set_main_option("script_location", _alembic_dir())
    cfg.set_main_option("sqlalchemy.url", url)
    return cfg


def _run_migrations(url: str) -> None:
    """Run Alembic migrations to head.

    Args:
        url: SQLAlchemy database URL.
    """
    cfg = _alembic_config(url)
    command.upgrade(cfg, "head")
    logger.info("Alembic migrations applied successfully")


def init_db(url: str) -> Engine:
    """Create the engine, run migrations, and configure the session factory.

    Called once during application startup (FastAPI lifespan).
    Pool sizing + statement timeout are read from
    :class:`pointlessql.config.DatabaseSettings` so operators can
    tune long-running PG deployments without code changes.  SQLite
    ignores the PG-only knobs.

    Args:
        url: SQLAlchemy database URL.

    Returns:
        Engine: The initialised SQLAlchemy engine.
    """
    global _engine, _session_factory  # noqa: PLW0603

    is_sqlite = url.startswith("sqlite")
    is_postgres = url.startswith("postgresql") or url.startswith("postgres+")

    if is_sqlite and not url.endswith(":memory:"):
        db_path = url.split("///", 1)[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

    connect_args: dict[str, object] = {}
    if is_sqlite:
        connect_args["check_same_thread"] = False

    # Read pool sizing + timeout out of settings so operators can
    # tune via env vars.  We re-instantiate the ``DatabaseSettings``
    # object here rather than threading it through ``init_db``'s
    # signature so the function stays backward-compatible with older
    # call-sites that pass the URL explicitly.
    from pointlessql.config import DatabaseSettings  # noqa: PLC0415

    db_settings = DatabaseSettings()

    engine_kwargs: dict[str, object] = {
        "connect_args": connect_args,
        "pool_pre_ping": True,
    }
    if is_postgres:
        engine_kwargs["pool_size"] = db_settings.pool_size
        engine_kwargs["max_overflow"] = db_settings.max_overflow
        engine_kwargs["pool_recycle"] = db_settings.pool_recycle_seconds

    _engine = sa_create_engine(url, **engine_kwargs)

    if is_sqlite:

        @event.listens_for(_engine, "connect")
        def _set_sqlite_pragmas(  # pyright: ignore[reportUnusedFunction]
            dbapi_conn: DBAPIConnection, _rec: object
        ) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA foreign_keys=ON")
            # Wait for a competing writer's lock instead of failing with
            # "database is locked" — the background loops contend for it.
            cursor.execute(f"PRAGMA busy_timeout={int(db_settings.sqlite_busy_timeout_ms)}")
            # NORMAL is durable under WAL and avoids an fsync per commit.
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    if is_postgres and db_settings.statement_timeout_ms > 0:
        timeout_ms = int(db_settings.statement_timeout_ms)

        @event.listens_for(_engine, "connect")
        def _set_pg_statement_timeout(  # pyright: ignore[reportUnusedFunction]
            dbapi_conn: DBAPIConnection, _rec: object
        ) -> None:
            cursor = dbapi_conn.cursor()
            cursor.execute(f"SET statement_timeout = {timeout_ms}")
            cursor.close()

    _run_migrations(url)

    _session_factory = sessionmaker(bind=_engine)
    logger.info("Database initialised (url=%s)", url.split("?")[0])
    return _engine


def get_session_factory() -> sessionmaker[Session]:
    """Return the session factory initialised by ``init_db``.

    Returns:
        sessionmaker[Session]: The bound session factory.

    Raises:
        RuntimeError: If ``init_db`` has not been called.
    """
    if _session_factory is None:
        msg = "Database not initialised — call init_db() first"
        raise RuntimeError(msg)
    return _session_factory


def reset() -> None:
    """Reset module state. For test teardown only."""
    global _engine, _session_factory  # noqa: PLW0603
    if _engine is not None:
        _engine.dispose()
    _engine = None
    _session_factory = None
