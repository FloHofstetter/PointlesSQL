"""Per-event-table retention prunes old rows and is opt-out at 0.

alert_events and query_history grow one row per event with no built-in
cap.  These tests pin that query-history pruning deletes old rows (with
their child reference rows) while keeping recent ones, and that the
retention sweep is a no-op when the window is 0.
"""

from __future__ import annotations

import datetime

from sqlalchemy import func, select

from pointlessql.api._bootstrap._loops._platform import (
    _prune_event_tables,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.api.main import app
from pointlessql.config import Settings
from pointlessql.models import QueryHistory, QueryHistoryTable
from pointlessql.services.query_history import prune_history_older_than, record_query

_NOW = datetime.datetime.now(datetime.UTC)
_OLD = _NOW - datetime.timedelta(days=200)


def _seed_query(started_at: datetime.datetime, email: str) -> None:
    record_query(
        app.state.session_factory,
        user_id=1,
        user_email=email,
        sql_text="SELECT 1",
        started_at=started_at,
        finished_at=started_at,
        status="succeeded",
        row_count=1,
        duration_ms=1,
        referenced_tables=["main.s.t"],
    )


def _count(model: type) -> int:
    with app.state.session_factory() as session:
        return int(session.execute(select(func.count()).select_from(model)).scalar() or 0)


def test_prune_history_deletes_old_keeps_recent() -> None:
    """Rows older than the cutoff (and their child rows) are removed."""
    _seed_query(_OLD, "old@test.com")
    _seed_query(_NOW, "new@test.com")
    deleted = prune_history_older_than(
        app.state.session_factory, _NOW - datetime.timedelta(days=30)
    )
    assert deleted == 1
    assert _count(QueryHistory) == 1
    # the child reference row of the pruned query is gone too
    assert _count(QueryHistoryTable) == 1


def test_retention_sweep_is_noop_at_zero() -> None:
    """A retention window of 0 keeps every row."""
    _seed_query(_OLD, "keepme@test.com")
    settings = Settings()
    settings.audit.alert_event_retention_days = 0
    settings.audit.query_history_retention_days = 0
    _prune_event_tables(app.state.session_factory, settings)
    assert _count(QueryHistory) == 1


def test_retention_sweep_prunes_when_configured() -> None:
    """A positive window deletes rows older than now - window."""
    _seed_query(_OLD, "purge@test.com")
    _seed_query(_NOW, "stay@test.com")
    settings = Settings()
    settings.audit.query_history_retention_days = 30
    _prune_event_tables(app.state.session_factory, settings)
    assert _count(QueryHistory) == 1
