"""Persistence helpers for the SQL editor's query history.

:func:`record_query` is the synchronous INSERT path; the HTTP
wrapper in :mod:`pointlessql.api.main` dispatches it through
:func:`asyncio.to_thread` so the request handler never blocks on
the DB round-trip.  Shape is deliberately parallel to
:mod:`pointlessql.services.audit`.

Query `status` values:

- ``"succeeded"`` — DuckDB returned a result set.
- ``"failed"`` — parse, enforcement, or runtime error.  The
  ``error_message`` column carries the human-readable detail.
- ``"cancelled"`` — user-requested cancel (currently unused).

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


_RUN_ID_LENGTH = 36

VALID_READ_KINDS: frozenset[str] = frozenset(
    {"sql_execute", "pql_table", "pql_table_at_version", "engine_direct", "audit_api"}
)


def _sanitise_run_id(value: str | None) -> str | None:
    """Drop garbage values before they hit the indexed column.

    A UUIDv4 string is exactly 36 characters (32 hex + 4 dashes).
    Anything else is logged and dropped — the column is best-effort
    metadata, never a security gate, so being tolerant of malformed
    callers keeps query history landing.

    Args:
        value: Raw caller-supplied run-id or ``None``.

    Returns:
        The trimmed 36-char run-id, or ``None`` when ``value`` is
        falsy / wrong-shaped.
    """
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) != _RUN_ID_LENGTH:
        logger.warning(
            "query_history: dropping non-UUID agent_run_id %r (len=%d)",
            cleaned,
            len(cleaned),
        )
        return None
    return cleaned


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
    agent_run_id: str | None = None,
    read_kind: str = "sql_execute",
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
        request_id: Correlates with the request-id log field.
            ``None`` when called from contexts that do not have a
            request scope.
        agent_run_id: Owning ``AgentRun.id`` when the query came
            from a registered run (resolved by the route from the
            ``X-Agent-Run-Id`` header or the
            ``POINTLESSQL_AGENT_RUN_ID`` env var).  Garbage-shaped
            values are dropped silently (UUID-like 36-char check
            only) so query history stays tolerant of malformed
            inputs.
        read_kind: Discriminator for the read path that produced this
            row.  Defaults to ``"sql_execute"`` for the historical
            ``/api/sql/execute`` writer; Sprint 14.2's read-audit
            helper passes ``"pql_table"`` / ``"engine_direct"``.
            Validated against :data:`VALID_READ_KINDS` so a typo
            cannot land an unknown value the UI cannot filter on.

    Returns:
        The auto-assigned ``QueryHistory.id`` of the new row (so
        the caller can surface it in an export deep-link etc.).

    Raises:
        ValueError: If ``read_kind`` is not in :data:`VALID_READ_KINDS`.
    """
    if read_kind not in VALID_READ_KINDS:
        raise ValueError(f"read_kind must be one of {sorted(VALID_READ_KINDS)}, got {read_kind!r}")
    sanitised_run_id = _sanitise_run_id(agent_run_id)
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
            agent_run_id=sanitised_run_id,
            read_kind=read_kind,
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
    agent_run_id: str | None = None,
    read_kind: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return recent query-history rows as plain dicts.

    Args:
        factory: SQLAlchemy session factory.
        user_id: Filter to rows with this ``user_id``.  ``None`` returns
            all users (admin-only caller).
        status: Filter to a single status string.  ``None`` returns all.
        since: Filter to ``started_at >= since``.  ``None`` returns all.
        agent_run_id: Filter to rows whose ``agent_run_id`` matches.
            ``None`` returns all.
        read_kind: Filter to rows whose ``read_kind`` matches one of
            :data:`VALID_READ_KINDS`.  Unknown values are dropped
            silently so a typo in a ``?read_kind=`` query string
            falls back to "no filter" instead of raising.  ``None``
            returns all.
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
    if agent_run_id is not None:
        stmt = stmt.where(QueryHistory.agent_run_id == agent_run_id)
    if read_kind is not None and read_kind in VALID_READ_KINDS:
        stmt = stmt.where(QueryHistory.read_kind == read_kind)

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
                "chart_config": r.chart_config,
                "agent_run_id": r.agent_run_id,
                "read_kind": r.read_kind,
            }
            for r in rows
        ]


def get_by_id(
    factory: sessionmaker[Session],
    history_id: int,
    *,
    user_id: int,
    is_admin: bool,
) -> dict[str, Any] | None:
    """Return a single history row if visible to the caller, else ``None``.

    Args:
        factory: SQLAlchemy session factory.
        history_id: ``query_history.id`` to fetch.
        user_id: Caller's user id for owner gating.
        is_admin: Whether the caller is an admin.

    Returns:
        The row as a dict (same shape as :func:`list_queries` entries),
        or ``None`` if the row is missing or the caller lacks visibility.
        Missing and forbidden collapse to the same return value so
        unguessable IDs cannot be probed.
    """
    with factory() as session:
        row = session.get(QueryHistory, history_id)
        if row is None:
            return None
        if not is_admin and row.user_id != user_id:
            return None
        tables = session.scalars(
            select(QueryHistoryTable).where(QueryHistoryTable.query_history_id == row.id)
        ).all()
        return {
            "id": row.id,
            "user_id": row.user_id,
            "user_email": row.user_email,
            "sql_text": row.sql_text,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "status": row.status,
            "row_count": row.row_count,
            "duration_ms": row.duration_ms,
            "error_message": row.error_message,
            "request_id": row.request_id,
            "tables": [t.full_name for t in tables],
            "chart_config": row.chart_config,
            "agent_run_id": row.agent_run_id,
            "read_kind": row.read_kind,
        }


def update_chart_config(
    factory: sessionmaker[Session],
    history_id: int,
    *,
    user_id: int,
    is_admin: bool,
    chart_config: str | None,
) -> dict[str, Any] | None:
    """Persist the user's chart selection on an existing history row.

    Args:
        factory: SQLAlchemy session factory.
        history_id: ``query_history.id`` to update.
        user_id: Caller's user id for owner gating.
        is_admin: Whether the caller is an admin.
        chart_config: JSON-as-text payload with ``{type, x, y}`` keys,
            or ``None`` to clear the persisted chart and revert to
            the table-only view.

    Returns:
        The updated row as a dict, or ``None`` when the row is absent
        or invisible to the caller.
    """
    with factory() as session:
        row = session.get(QueryHistory, history_id)
        if row is None:
            return None
        if not is_admin and row.user_id != user_id:
            return None
        row.chart_config = chart_config
        session.commit()
        session.refresh(row)
        tables = session.scalars(
            select(QueryHistoryTable).where(QueryHistoryTable.query_history_id == row.id)
        ).all()
        return {
            "id": row.id,
            "user_id": row.user_id,
            "user_email": row.user_email,
            "sql_text": row.sql_text,
            "started_at": row.started_at.isoformat() if row.started_at else None,
            "finished_at": row.finished_at.isoformat() if row.finished_at else None,
            "status": row.status,
            "row_count": row.row_count,
            "duration_ms": row.duration_ms,
            "error_message": row.error_message,
            "request_id": row.request_id,
            "tables": [t.full_name for t in tables],
            "chart_config": row.chart_config,
            "agent_run_id": row.agent_run_id,
            "read_kind": row.read_kind,
        }


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
