"""Per-cell-run lifecycle + history tracking.

Sprint 79 split out of the monolithic ``notebook_outputs.py``. Owns
the ``NotebookCellRun`` (current state per session) and
``NotebookCellRunSource`` (per-execute history) tables. The WS
handler calls :func:`upsert_cell_run` on ``execute_request`` /
``execute_reply`` for the live status pill and
:func:`record_cell_run_start` / :func:`record_cell_run_finish` to
build the per-cell history popover that the Sprint-73 UI surfaces.
"""

from __future__ import annotations

import datetime
import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import NotebookCellRun, NotebookCellRunSource

logger = logging.getLogger(__name__)


def upsert_cell_run(
    factory: sessionmaker[Session],
    *,
    file_path: str,
    cell_id: str,
    kernel_session_id: str,
    status: str,
    execution_count: int | None = None,
    finished: bool = False,
) -> None:
    """Insert or update the lifecycle row for a cell run.

    Called on ``execute_request`` (status=``running``), on
    ``execute_reply`` (status=``ok``/``error``/``aborted`` +
    ``finished=True``), and on explicit "Clear" before re-execute.
    The in-session run is unique on ``(file_path, cell_id,
    kernel_session_id)`` so we UPSERT via get-or-create.

    Args:
        factory: SQLAlchemy session factory.
        file_path: Relative notebook path.
        cell_id: Cell UUID.
        kernel_session_id: Session UUID.
        status: Current lifecycle state.
        execution_count: Kernel's monotonic counter — present on
            the reply, absent on the start.
        finished: When ``True``, stamp ``finished_at``; otherwise
            leave the previous value intact.
    """
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = session.get(
            NotebookCellRun,
            (file_path, cell_id, kernel_session_id),
        )
        if row is None:
            row = NotebookCellRun(
                file_path=file_path,
                cell_id=cell_id,
                kernel_session_id=kernel_session_id,
                status=status,
                execution_count=execution_count,
                started_at=now,
                finished_at=now if finished else None,
            )
            session.add(row)
        else:
            row.status = status
            if execution_count is not None:
                row.execution_count = execution_count
            if finished:
                row.finished_at = now
        session.commit()


def record_cell_run_start(
    factory: sessionmaker[Session],
    *,
    file_path: str,
    cell_id: str,
    kernel_session_id: str,
    source: str,
    started_at: datetime.datetime,
) -> int:
    """Insert a fresh history row for an execute_request and return its id.

    Sprint 73 — companion to :func:`upsert_cell_run`.  Where
    ``upsert_cell_run`` keeps "current state per session" (one row
    per ``(file_path, cell_id, kernel_session_id)``), this function
    inserts a brand-new row per execute_request so the per-cell
    popover can show "last N runs" with diffs against current
    Monaco source.  The returned ``id`` is stashed in the WS
    handler's ``pending_run_sources`` map keyed by
    ``(cell_id, kernel_session_id)`` so the matching execute_reply
    can stamp the finish + status via :func:`record_cell_run_finish`.

    Args:
        factory: SQLAlchemy session factory.
        file_path: Relative notebook path.
        cell_id: Cell UUID.
        kernel_session_id: Session UUID (bumps on kernel restart).
        source: Cell source the kernel will execute.  For SQL cells
            this is the wrapped ``__pql_sql_run(...)`` snippet, not
            the raw SELECT — history is what the kernel saw.
        started_at: When the WS frame landed (UTC).

    Returns:
        The autoincrement id of the inserted row.
    """
    with factory() as session:
        row = NotebookCellRunSource(
            file_path=file_path,
            cell_id=cell_id,
            kernel_session_id=kernel_session_id,
            source=source,
            started_at=started_at,
            status="running",
        )
        session.add(row)
        session.commit()
        # SQLAlchemy populates ``id`` on flush; expire_on_commit is
        # the default, so we must read before the session closes.
        return int(row.id)


def record_cell_run_finish(
    factory: sessionmaker[Session],
    *,
    source_id: int,
    status: str,
    execution_count: int | None,
    finished_at: datetime.datetime,
) -> None:
    """Stamp the finish columns on a previously-started run-source row.

    Sprint 73 — called from the WS handler when ``execute_reply``
    arrives for a tracked execute.  No-op (with a debug log) when
    the id is unknown — for example when the kernel emits an
    execute_reply for a request we did not record (bootstrap, future
    silent introspects).

    Args:
        factory: SQLAlchemy session factory.
        source_id: id returned by :func:`record_cell_run_start`.
        status: Final lifecycle state (``"ok"`` / ``"error"`` /
            ``"aborted"`` / etc.).
        execution_count: Jupyter's monotonic counter from the reply.
        finished_at: When the reply landed (UTC).
    """
    with factory() as session:
        row = session.get(NotebookCellRunSource, source_id)
        if row is None:
            logger.debug(
                "record_cell_run_finish: source_id=%s not found", source_id,
            )
            return
        row.status = status
        if execution_count is not None:
            row.execution_count = execution_count
        row.finished_at = finished_at
        session.commit()


def list_cell_run_sources(
    factory: sessionmaker[Session],
    *,
    file_path: str,
    cell_id: str,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Return the last *limit* runs for a cell, newest-first.

    Sprint 73 — backs ``GET /api/notebook/cell-runs``.  Returns
    JSON-ready dicts with ISO-formatted timestamps so the route
    handler can pass the list to ``JSONResponse`` without further
    massaging.

    Args:
        factory: SQLAlchemy session factory.
        file_path: Relative notebook path.
        cell_id: Cell UUID.
        limit: Maximum number of rows to return.

    Returns:
        List of dicts, newest-first, each with ``id`` /
        ``execution_count`` / ``source`` / ``started_at`` /
        ``finished_at`` / ``status`` / ``kernel_session_id``.
    """
    with factory() as session:
        rows = session.execute(
            select(NotebookCellRunSource)
            .where(
                NotebookCellRunSource.file_path == file_path,
                NotebookCellRunSource.cell_id == cell_id,
            )
            .order_by(NotebookCellRunSource.started_at.desc())
            .limit(limit)
        ).scalars().all()
        return [
            {
                "id": r.id,
                "execution_count": r.execution_count,
                "source": r.source,
                "started_at": r.started_at.isoformat() if r.started_at else None,
                "finished_at": r.finished_at.isoformat() if r.finished_at else None,
                "status": r.status,
                "kernel_session_id": r.kernel_session_id,
            }
            for r in rows
        ]
