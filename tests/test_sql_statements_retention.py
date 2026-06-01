"""Unit tests for the SQL Statement API retention sweeper.

``cleanup_stale_statements`` deletes rows older than a retention window
(by ``submitted_at``, so stuck-PENDING rows still drop), and
``register_retention_executor`` idempotently attaches the sweeper to the
scheduler executor registry on ``app.state``.
"""

from __future__ import annotations

import datetime as _dt
from types import SimpleNamespace

from sqlalchemy import func, select

from pointlessql.api.main import app
from pointlessql.models import SqlStatement
from pointlessql.services.sql_statements._retention import (
    cleanup_stale_statements,
    register_retention_executor,
)

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


def test_register_executor_is_idempotent() -> None:
    state = SimpleNamespace()
    register_retention_executor(state)
    register_retention_executor(state)
    registry = state.scheduler_executor_registry
    assert registry["sql_statements_retention"] is cleanup_stale_statements


def test_register_executor_preserves_existing_registry() -> None:
    sentinel = object()
    state = SimpleNamespace(scheduler_executor_registry={"other": sentinel})
    register_retention_executor(state)
    assert state.scheduler_executor_registry["other"] is sentinel
    assert "sql_statements_retention" in state.scheduler_executor_registry
