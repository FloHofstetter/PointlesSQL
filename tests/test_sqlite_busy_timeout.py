"""init_db applies a SQLite busy_timeout so concurrent writers wait.

WAL allows a single writer at a time and PointlesSQL runs many background
loops that all write the metadata DB; without a busy_timeout a competing
write fails immediately with "database is locked".  This pins that
init_db sets the configured timeout (and NORMAL synchronous) on each
SQLite connection.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import text

import pointlessql.db as db_mod
from pointlessql.config import reset_settings_cache


def test_init_db_sets_sqlite_busy_timeout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """A connection from init_db reports the configured busy_timeout."""
    monkeypatch.setenv("POINTLESSQL_DB_SQLITE_BUSY_TIMEOUT_MS", "7777")
    reset_settings_cache()
    db_path = tmp_path / "busy.db"
    try:
        engine = db_mod.init_db(f"sqlite:///{db_path}")
        with engine.connect() as conn:
            busy_timeout = conn.execute(text("PRAGMA busy_timeout")).scalar()
            synchronous = conn.execute(text("PRAGMA synchronous")).scalar()
        assert busy_timeout == 7777
        assert synchronous == 1  # 1 == NORMAL
    finally:
        db_mod.reset()
        reset_settings_cache()
