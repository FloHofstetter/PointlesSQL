"""Read-audit instrumentation for direct-Delta read paths.

``/api/sql/execute`` lands in ``query_history`` via
:func:`pointlessql.services.query_history.record_query`, which kept
the DSGVO "wer hat meine Daten gelesen?" question answerable for
SQL-editor traffic.  The agent runtimes' ``pql.table()`` and any
engine-direct read path bypassed that route entirely until Sprint
14.2 — the read happened, no audit row landed.

This module is the single instrumentation point for those bypass
paths.  Every call writes a synthetic ``SELECT * FROM <fqn>`` row
into ``query_history`` with ``read_kind="pql_table"`` (or
``"engine_direct"``) so the existing ``/queries`` UI, run-detail
queries tab, and ``QueryHistoryTable`` reverse-lookup all keep
working without a parallel audit surface.

Behaviour matches Sprint 13.8's :func:`operation_context`:

* Best-effort — when no session factory is available (interactive
  PQL with no DB initialised), the call is a silent passthrough so
  the read path itself never fails because audit infrastructure is
  missing.
* Run-id and principal lookup mirrors
  :func:`pointlessql.pql._sql.run_sql` — explicit kwarg first, then
  ``POINTLESSQL_AGENT_RUN_ID`` / ``POINTLESSQL_PRINCIPAL`` env vars.
* Errors during the audit insert are logged and swallowed; the read
  is the user's primary action and a broken audit must not break it.
"""

from __future__ import annotations

import datetime
import logging
import os
from typing import TYPE_CHECKING

from pointlessql.services.query_history import record_query

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def _resolve_run_id(explicit: str | None) -> str | None:
    if explicit:
        return explicit
    env = os.environ.get("POINTLESSQL_AGENT_RUN_ID")
    return env if env else None


def _resolve_principal(explicit: str | None) -> str:
    if explicit:
        return explicit
    return os.environ.get("POINTLESSQL_PRINCIPAL", "system")


def record_read(
    factory: sessionmaker[Session] | None,
    *,
    table_fqn: str,
    read_kind: str = "pql_table",
    agent_run_id: str | None = None,
    principal: str | None = None,
    started_at: datetime.datetime,
    finished_at: datetime.datetime,
    status: str = "succeeded",
    row_count: int | None = None,
    duration_ms: int | None = None,
    error_message: str | None = None,
) -> int | None:
    """Record a Delta-direct read in ``query_history``.

    Synthesises a ``SELECT * FROM <table_fqn>`` row so the UI's
    existing rendering keeps working without a per-``read_kind``
    branch.  ``referenced_tables=[table_fqn]`` populates the
    :class:`QueryHistoryTable` reverse-lookup so "who read table T"
    queries cover the bypass paths too.

    Args:
        factory: SQLAlchemy session factory.  ``None`` makes this a
            silent passthrough (interactive PQL with no DB
            initialised).
        table_fqn: Three-part UC name (``catalog.schema.table``) the
            caller read.
        read_kind: ``"pql_table"`` for the ``pql.table()`` choke
            point in :mod:`pointlessql.pql._read`, or
            ``"engine_direct"`` for raw engine reads instrumented
            elsewhere.
        agent_run_id: Owning run UUID.  Defaults to the
            ``POINTLESSQL_AGENT_RUN_ID`` env var.
        principal: Email of the actor on whose behalf the read
            happened.  Defaults to the ``POINTLESSQL_PRINCIPAL`` env
            var, then to the literal string ``"system"`` so the
            ``user_email`` column never violates its NOT NULL.
        started_at: Wall-clock timestamp before the read began.
        finished_at: Wall-clock timestamp after the read returned.
        status: ``"succeeded"`` / ``"failed"`` / ``"cancelled"``.
        row_count: Materialised row count when the engine surfaces
            it cheaply; ``None`` when not measured.
        duration_ms: Wall-clock duration in milliseconds.
        error_message: Exception detail when ``status == "failed"``.

    Returns:
        The new ``query_history.id``, or ``None`` when the call was
        a silent passthrough.
    """
    if factory is None:
        return None
    try:
        return record_query(
            factory,
            user_id=0,
            user_email=_resolve_principal(principal),
            sql_text=f"SELECT * FROM {table_fqn}",
            started_at=started_at,
            finished_at=finished_at,
            status=status,
            row_count=row_count,
            duration_ms=duration_ms,
            referenced_tables=[table_fqn],
            error_message=error_message,
            agent_run_id=_resolve_run_id(agent_run_id),
            read_kind=read_kind,
        )
    except Exception as exc:  # noqa: BLE001 — audit must never break the read
        logger.warning(
            "read_audit: failed to record %s read of %r: %s",
            read_kind,
            table_fqn,
            exc,
        )
        return None
