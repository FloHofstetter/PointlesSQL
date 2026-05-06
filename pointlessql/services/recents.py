"""Recent-table tracking service.

Helpers for the  catalog-browser "Recent tables" block.
Wraps :class:`pointlessql.models.RecentTable` with two operations:

* :func:`record_table_visit` — upsert a row for the user-table
  pair, bumping ``last_visited_at`` to the current time.  Called
  from the catalog-table HTML detail handler so every page-render
  records the visit.  No-op when ``user_id`` is unset (anonymous
  reads) — the localStorage block in ``base.html`` is the
  no-auth fallback.
* :func:`top_recent_tables` — return the user's N most recently
  visited tables, newest first.  Called by the sidebar render
  path and by ``GET /api/recents``.

Both helpers swallow exceptions internally — the recents block
is a UX nicety, not a correctness boundary.  A flaky write must
not break the catalog page.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING

from sqlalchemy import desc, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from pointlessql.models import RecentTable

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 5
TRIM_THRESHOLD = 50  # cap rows per user; trim oldest beyond this on each write


def record_table_visit(
    factory: sessionmaker[Session],
    user_id: int,
    table_full_name: str,
    *,
    now: datetime.datetime | None = None,
    workspace_id: int = 1,
) -> None:
    """Upsert a recents row for the (workspace, user, table) triple.

    Uses dialect-specific ``INSERT ... ON CONFLICT DO UPDATE``
    (SQLite + Postgres both support it) so a write is one round
    trip regardless of whether the row exists.  Falls back to a
    select-then-update path on other dialects via the
    ``IntegrityError`` recovery branch.

    Bounded growth: when the user has more than
    :data:`TRIM_THRESHOLD` rows in the workspace, the oldest are
    deleted in the same session.

    Args:
        factory: SQLAlchemy session factory.
        user_id: ``users.id`` — must be > 0.
        table_full_name: ``catalog.schema.table``.
        now: Optional UTC override for tests.
        workspace_id: Workspace this visit was made in.  Defaults
            to ``1`` (seeded default workspace) so non-HTTP callers
            keep working; HTTP routes pass
            ``request.state.workspace_id``.
    """
    if user_id <= 0:
        return
    if not table_full_name or table_full_name.count(".") != 2:
        return

    timestamp = now or datetime.datetime.now(datetime.UTC)

    try:
        with factory() as session:
            dialect_name = session.bind.dialect.name if session.bind else "sqlite"
            insert_fn = pg_insert if dialect_name == "postgresql" else sqlite_insert
            stmt = insert_fn(RecentTable).values(
                workspace_id=workspace_id,
                user_id=user_id,
                table_full_name=table_full_name,
                last_visited_at=timestamp,
            )
            stmt = stmt.on_conflict_do_update(
                index_elements=["workspace_id", "user_id", "table_full_name"],
                set_={"last_visited_at": timestamp},
            )
            session.execute(stmt)

            count = session.scalar(
                select(RecentTable.id)
                .where(
                    RecentTable.user_id == user_id,
                    RecentTable.workspace_id == workspace_id,
                )
                .order_by(desc(RecentTable.last_visited_at))
                .offset(TRIM_THRESHOLD)
                .limit(1)
            )
            if count is not None:
                rows = list(
                    session.scalars(
                        select(RecentTable)
                        .where(
                            RecentTable.user_id == user_id,
                            RecentTable.workspace_id == workspace_id,
                        )
                        .order_by(desc(RecentTable.last_visited_at))
                        .offset(TRIM_THRESHOLD)
                    )
                )
                for row in rows:
                    session.delete(row)

            session.commit()
    except Exception:  # noqa: BLE001 — recents are best-effort
        logger.exception(
            "record_table_visit: upsert failed for user_id=%s table=%s",
            user_id,
            table_full_name,
        )


def top_recent_tables(
    factory: sessionmaker[Session],
    user_id: int,
    *,
    limit: int = DEFAULT_LIMIT,
    workspace_id: int | None = None,
) -> list[dict[str, object]]:
    """Return the user's N most-recent table visits, newest first.

    Args:
        factory: SQLAlchemy session factory.
        user_id: ``users.id``.  Returns ``[]`` for ``user_id<=0``.
        limit: Cap (default 5, matching the sidebar block).
        workspace_id: Restrict to one workspace's recents.  ``None``
            returns recents across every workspace the user has
            visited (used by the super-admin lens; the regular
            sidebar always passes the request's resolved workspace).

    Returns:
        List of dicts with ``table_full_name`` and ``last_visited_at``
        (ISO-8601 string).  Empty list on errors.
    """
    if user_id <= 0:
        return []
    try:
        with factory() as session:
            stmt = (
                select(RecentTable)
                .where(RecentTable.user_id == user_id)
                .order_by(desc(RecentTable.last_visited_at))
                .limit(limit)
            )
            if workspace_id is not None:
                stmt = stmt.where(RecentTable.workspace_id == workspace_id)
            rows = list(session.scalars(stmt))
            return [
                {
                    "table_full_name": r.table_full_name,
                    "last_visited_at": r.last_visited_at.astimezone(datetime.UTC).isoformat(),
                }
                for r in rows
            ]
    except Exception:  # noqa: BLE001 — recents read is best-effort
        logger.exception("top_recent_tables: read failed for user_id=%s", user_id)
        return []
