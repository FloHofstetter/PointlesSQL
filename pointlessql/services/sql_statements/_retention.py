"""Retention sweeper for the public SQL Statement API store.

Phase 117 keeps every submission in ``sql_statements`` until the
sweep prunes it.  The default retention is 24h (configurable via
``settings.sql_execution_api.result_payload_retention_hours``);
shorter than the query-history retention because the wire client
already has the result in hand.

The sweeper is wired into the existing scheduler executor registry
so it inherits the ``kind="sql_statements_retention"`` executor
declared in :func:`build_default_registry`.  Single periodic task
per process; safe to no-op when the table is empty.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from sqlalchemy import delete
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import SqlStatement

logger = logging.getLogger(__name__)


def cleanup_stale_statements(
    session_factory: sessionmaker[Session],
    *,
    retention_hours: int,
) -> int:
    """Delete ``sql_statements`` rows older than *retention_hours*.

    Filters by ``submitted_at`` rather than ``completed_at`` so a
    statement that hung in PENDING forever still drops out — clients
    that never polled don't get to pin disk indefinitely.

    Args:
        session_factory: SQLAlchemy session factory.
        retention_hours: Hours since ``submitted_at`` above which a
            row is eligible for deletion.

    Returns:
        Number of rows deleted (best-effort; PostgreSQL returns the
        exact count, SQLite returns the same via ``rowcount``).
    """
    if retention_hours <= 0:
        return 0
    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=retention_hours)
    with session_factory() as session:
        stmt = delete(SqlStatement).where(SqlStatement.submitted_at < cutoff)
        result = session.execute(stmt)
        session.commit()
        # ``Result.rowcount`` is typed as ``int`` on the dialect-cursor
        # but pyright sees the generic Result base.  ``getattr`` keeps
        # the path safe when a future dialect returns -1.
        deleted = int(getattr(result, "rowcount", 0) or 0)
    if deleted:
        logger.info("sql_statements retention: pruned %d rows older than %s", deleted, cutoff)
    return deleted


def register_retention_executor(app_state: Any) -> None:
    """Attach the retention executor to ``app.state`` for scheduler discovery.

    The scheduler registry is initialised at startup; this helper
    drops the retention executor into the discovered map so the
    task can be added without editing the registry bootstrap code.
    When called twice (e.g. in tests that re-run lifespan) the
    second call is idempotent.

    Args:
        app_state: ``app.state`` of the running FastAPI app.
    """
    registry: dict[str, Any] | None = getattr(app_state, "scheduler_executor_registry", None)
    if registry is None:
        registry = {}
        app_state.scheduler_executor_registry = registry
    registry.setdefault("sql_statements_retention", cleanup_stale_statements)
