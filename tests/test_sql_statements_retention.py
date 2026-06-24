"""Unit tests for the SQL Statement API retention sweeper.

``cleanup_stale_statements`` deletes rows older than a retention window
(by ``submitted_at``, so stuck-PENDING rows still drop), and the
event-retention background loop's ``_prune_event_tables`` actually
invokes it on the audit cleanup cadence (gated on the SQL Statement API
being enabled).
"""

from __future__ import annotations

import datetime as _dt

from sqlalchemy import func, select

from pointlessql.api._bootstrap._loops._platform import (
    _prune_event_tables,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.api.main import app
from pointlessql.config import Settings
from pointlessql.models import SqlStatement
from pointlessql.services.sql_statements._retention import cleanup_stale_statements

_NOW = _dt.datetime.now(_dt.UTC)


def _add_statement(statement_id: str, age_hours: float) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            SqlStatement(
                statement_id=statement_id,
                api_key_id=1,
                statement_text="SELECT 1",
                status="SUCCEEDED",
                row_limit=100,
                submitted_at=_NOW - _dt.timedelta(hours=age_hours),
            )
        )
        session.commit()


def _count(prefix: str) -> int:
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(SqlStatement)
                .where(SqlStatement.statement_id.like(f"{prefix}%"))
            )
            or 0
        )


def test_prunes_only_rows_older_than_window() -> None:
    _add_statement("ret-old", age_hours=48)
    _add_statement("ret-new", age_hours=1)
    deleted = cleanup_stale_statements(app.state.session_factory, retention_hours=24)
    assert deleted >= 1
    assert _count("ret-old") == 0
    assert _count("ret-new") == 1


def test_zero_retention_is_a_noop() -> None:
    _add_statement("ret-zero", age_hours=1000)
    deleted = cleanup_stale_statements(app.state.session_factory, retention_hours=0)
    assert deleted == 0
    assert _count("ret-zero") == 1


def test_negative_retention_is_a_noop() -> None:
    deleted = cleanup_stale_statements(app.state.session_factory, retention_hours=-5)
    assert deleted == 0


def test_event_retention_sweep_prunes_sql_statements() -> None:
    """The background sweep prunes stale statements when the API is enabled."""
    _add_statement("ret-sweep-old", age_hours=48)
    _add_statement("ret-sweep-new", age_hours=1)
    settings = Settings()
    settings.sql_execution_api.result_payload_retention_hours = 24
    _prune_event_tables(app.state.session_factory, settings)
    assert _count("ret-sweep-old") == 0
    assert _count("ret-sweep-new") == 1


def test_event_retention_sweep_skips_when_api_disabled() -> None:
    """A disabled SQL Statement API leaves the store untouched."""
    _add_statement("ret-disabled", age_hours=1000)
    settings = Settings()
    settings.sql_execution_api.enabled = False
    _prune_event_tables(app.state.session_factory, settings)
    assert _count("ret-disabled") == 1
