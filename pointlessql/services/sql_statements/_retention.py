"""Retention sweeper for the public SQL Statement API store.

Every submission lives in ``sql_statements`` until the sweep
prunes it.  The default retention is 24h (configurable via
``settings.sql_execution_api.result_payload_retention_hours``);
shorter than the query-history retention because the wire client
already has the result in hand.

:func:`cleanup_stale_statements` is run by the lifespan's
event-retention background loop on the audit cleanup cadence.  Single
periodic sweep per process; safe to no-op when the table is empty or
the SQL Statement API is disabled.
"""

from __future__ import annotations

import datetime
import logging

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
