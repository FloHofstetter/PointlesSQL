"""Reverse-index ``runs by table`` queries.

The forward direction "what did this run touch?" is served by
:attr:`AgentRun.tables_touched` and the per-op ``target_table``
column.  The reverse direction "which runs touched this table?"
needs a join either way; this service centralises the three kinds
of relationships a reviewer typically wants:

* **touched** — present in ``AgentRun.tables_touched`` (the JSON
  list the runtime declares).
* **written** — has an op with ``target_table=fqn`` *or* a value
  change recorded against the table.
* **read** — referenced via :class:`QueryHistoryTable` from a
  ``query_history`` row owned by the run.

All three queries paginate by ``started_at DESC`` and return
serialised :class:`AgentRun` rows shaped by
:func:`agent_runs_routes.serialize_agent_run` so the HTML view can
reuse the same row partial as ``/runs``.
"""

from __future__ import annotations

import datetime
import logging
from typing import TYPE_CHECKING, Any, Literal

from sqlalchemy import distinct, exists, or_, select

from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    LineageValueChange,
    QueryHistory,
    QueryHistoryTable,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


Kind = Literal["touched", "written", "read"]
VALID_KINDS: frozenset[str] = frozenset({"touched", "written", "read"})


def _by_touched(
    session: Session,
    *,
    fqn: str,
    since: datetime.datetime | None,
    until: datetime.datetime | None,
    limit: int,
) -> list[AgentRun]:
    """Return runs whose ``tables_touched`` JSON contains ``fqn``.

    Uses ``LIKE '%"<fqn>"%'`` rather than ``json_each`` so the
    same query runs unchanged on SQLite + Postgres — the JSON is
    stored as text and quoted entries are unambiguous.
    """
    stmt = select(AgentRun).where(AgentRun.tables_touched.ilike(f'%"{fqn}"%'))
    if since is not None:
        stmt = stmt.where(AgentRun.started_at >= since)
    if until is not None:
        stmt = stmt.where(AgentRun.started_at < until)
    stmt = stmt.order_by(AgentRun.started_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def _by_written(
    session: Session,
    *,
    fqn: str,
    since: datetime.datetime | None,
    until: datetime.datetime | None,
    limit: int,
) -> list[AgentRun]:
    """Return runs that wrote to ``fqn`` (op or value-change axis).

    Combines two existence checks via OR so a run that produced a
    merge AND a value-change against the same table only surfaces
    once.
    """
    op_subq = (
        select(AgentRunOperation.id)
        .where(AgentRunOperation.agent_run_id == AgentRun.id)
        .where(AgentRunOperation.target_table == fqn)
        .correlate(AgentRun)
    )
    vc_subq = (
        select(LineageValueChange.id)
        .where(LineageValueChange.run_id == AgentRun.id)
        .where(LineageValueChange.target_table == fqn)
        .correlate(AgentRun)
    )
    stmt = select(AgentRun).where(or_(exists(op_subq), exists(vc_subq)))
    if since is not None:
        stmt = stmt.where(AgentRun.started_at >= since)
    if until is not None:
        stmt = stmt.where(AgentRun.started_at < until)
    stmt = stmt.order_by(AgentRun.started_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def _by_read(
    session: Session,
    *,
    fqn: str,
    since: datetime.datetime | None,
    until: datetime.datetime | None,
    limit: int,
) -> list[AgentRun]:
    """Return runs whose ``query_history`` referenced ``fqn``.

    Joins ``QueryHistoryTable`` (``access_type='read'``) → up to
    ``QueryHistory`` → up to ``AgentRun`` and de-duplicates so each
    run appears once.
    """
    referenced_run_ids = (
        select(distinct(QueryHistory.agent_run_id))
        .join(QueryHistoryTable, QueryHistoryTable.query_history_id == QueryHistory.id)
        .where(QueryHistoryTable.full_name == fqn)
        .where(QueryHistory.agent_run_id.is_not(None))
    )
    stmt = select(AgentRun).where(AgentRun.id.in_(referenced_run_ids))
    if since is not None:
        stmt = stmt.where(AgentRun.started_at >= since)
    if until is not None:
        stmt = stmt.where(AgentRun.started_at < until)
    stmt = stmt.order_by(AgentRun.started_at.desc()).limit(limit)
    return list(session.scalars(stmt).all())


def runs_by_table(
    factory: sessionmaker[Session],
    *,
    fqn: str,
    kind: Kind = "touched",
    since: datetime.datetime | None = None,
    until: datetime.datetime | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Return serialised :class:`AgentRun` rows for a reverse-index query.

    Args:
        factory: SQLAlchemy session factory.
        fqn: Three-part UC identifier
            (``catalog.schema.table``); compared verbatim — no
            wildcard support.
        kind: ``touched``/``written``/``read`` — see module
            docstring for the relationship each kind tracks.
        since: ISO-aware lower bound on ``AgentRun.started_at``.
        until: ISO-aware upper bound (exclusive).
        limit: Hard row cap.

    Returns:
        List of dicts shaped by
        :func:`agent_runs_routes.serialize_agent_run`,
        newest-first.

    Raises:
        ValueError: ``kind`` outside :data:`VALID_KINDS`.
    """
    if kind not in VALID_KINDS:
        raise ValueError(f"unknown kind: {kind!r}")
    # Lazy import: serialize_agent_run lives in the API package
    # which is the audit aggregator's logical sibling, but importing
    # at module-load time would create a circular dependency.
    from pointlessql.api.agent_runs_routes import serialize_agent_run

    with factory() as session:
        if kind == "touched":
            rows = _by_touched(session, fqn=fqn, since=since, until=until, limit=limit)
        elif kind == "written":
            rows = _by_written(session, fqn=fqn, since=since, until=until, limit=limit)
        else:
            rows = _by_read(session, fqn=fqn, since=since, until=until, limit=limit)
        return [serialize_agent_run(r) for r in rows]
