"""Persistence helpers for the Phase-12 query history.

:func:`record_query` is the synchronous INSERT path; the HTTP
wrapper in :mod:`pointlessql.api.main` dispatches it through
:func:`asyncio.to_thread` so the request handler never blocks on
the DB round-trip.  Shape is deliberately parallel to
:mod:`pointlessql.services.audit`.

Query `status` values:

- ``"succeeded"`` — DuckDB returned a result set.
- ``"failed"`` — parse, enforcement, or runtime error.  The
  ``error_message`` column carries the human-readable detail.
- ``"cancelled"`` — reserved for Sprint 52's cancel path.

Non-admin users see only their own rows; admin sees every row.
Enforcement is the list route's job (see
:func:`pointlessql.api.main.api_list_queries`).
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy import desc, func, select

from pointlessql.models import QueryHistory, QueryHistoryTable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def record_query(
    factory: sessionmaker[Session],
    *,
    user_id: int,
    user_email: str,
    sql_text: str,
    started_at: datetime.datetime,
    finished_at: datetime.datetime,
    status: str,
    row_count: int | None,
    duration_ms: int | None,
    referenced_tables: list[str],
    error_message: str | None = None,
    request_id: str | None = None,
) -> int:
    """Insert a :class:`QueryHistory` row plus its table-reference rows.

    Args:
        factory: SQLAlchemy session factory from ``app.state``.
        user_id: ID of the user who ran the query.  ``0`` for anonymous
            (never happens today — the route requires auth).
        user_email: Email snapshot at time of run.
        sql_text: Verbatim user-submitted SQL.
        started_at: Wall-clock timestamp when the route began.
        finished_at: Wall-clock timestamp when the route returned
            (success *or* failure).
        status: ``"succeeded"`` / ``"failed"`` / ``"cancelled"``.
        row_count: Result row count after row-cap slicing, or
            ``None`` on failure / cancel.
        duration_ms: DuckDB wall-clock time in ms, or ``None`` on
            failure / cancel.
        referenced_tables: Full-name list extracted by sqlglot at
            execute time.  One ``query_history_tables`` row is
            written per entry, with ``access_type="read"``.
        error_message: Exception detail for failures; ``None`` on
            success.
        request_id: Correlates with the Sprint-16 request-id log
            field.  ``None`` when called from contexts that do not
            have a request scope.

    Returns:
        The auto-assigned ``QueryHistory.id`` of the new row (so
        the caller can surface it in an export deep-link etc.).
    """
    with factory() as session:
        entry = QueryHistory(
            user_id=user_id,
            user_email=user_email,
            sql_text=sql_text,
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            row_count=row_count,
            duration_ms=duration_ms,
            error_message=error_message,
            request_id=request_id,
        )
        session.add(entry)
        session.flush()  # assigns entry.id for the FK below
        for full_name in referenced_tables:
            session.add(
                QueryHistoryTable(
                    query_history_id=entry.id,
                    full_name=full_name,
                    access_type="read",
                )
            )
        session.commit()
        logger.debug(
            "query_history: %s %s %s rows=%s",
            user_email,
            status,
            referenced_tables,
            row_count,
        )
        return entry.id


def list_queries(
    factory: sessionmaker[Session],
    *,
    user_id: int | None = None,
    status: str | None = None,
    since: datetime.datetime | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return recent query-history rows as plain dicts.

    Args:
        factory: SQLAlchemy session factory.
        user_id: Filter to rows with this ``user_id``.  ``None`` returns
            all users (admin-only caller).
        status: Filter to a single status string.  ``None`` returns all.
        since: Filter to ``started_at >= since``.  ``None`` returns all.
        limit: Hard row cap.  Also enforces ORDER BY ``started_at DESC``
            so the most recent activity is at the top.

    Returns:
        A list of dicts, each with scalar keys from :class:`QueryHistory`
        plus a ``tables`` list carrying the joined
        :class:`QueryHistoryTable` ``full_name`` values.
    """
    stmt = select(QueryHistory).order_by(desc(QueryHistory.started_at)).limit(limit)
    if user_id is not None:
        stmt = stmt.where(QueryHistory.user_id == user_id)
    if status is not None:
        stmt = stmt.where(QueryHistory.status == status)
    if since is not None:
        stmt = stmt.where(QueryHistory.started_at >= since)

    with factory() as session:
        rows = session.scalars(stmt).all()
        if not rows:
            return []
        ids = [r.id for r in rows]
        tables_by_id: dict[int, list[str]] = {i: [] for i in ids}
        joined = session.scalars(
            select(QueryHistoryTable).where(QueryHistoryTable.query_history_id.in_(ids))
        ).all()
        for t in joined:
            tables_by_id.setdefault(t.query_history_id, []).append(t.full_name)

        return [
            {
                "id": r.id,
                "user_id": r.user_id,
                "user_email": r.user_email,
                "sql_text": r.sql_text,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "row_count": r.row_count,
                "duration_ms": r.duration_ms,
                "error_message": r.error_message,
                "request_id": r.request_id,
                "tables": tables_by_id.get(r.id, []),
            }
            for r in rows
        ]


def count_queries(factory: sessionmaker[Session]) -> int:
    """Return the total number of history rows.

    Args:
        factory: SQLAlchemy session factory.

    Returns:
        The ``COUNT(*)`` of ``query_history``.  Used by the
        ``/queries`` page header's "N entries" line.
    """
    with factory() as session:
        result = session.execute(select(func.count()).select_from(QueryHistory))
        return int(result.scalar() or 0)
