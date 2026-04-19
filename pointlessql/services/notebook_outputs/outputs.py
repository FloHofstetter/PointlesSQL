"""Persist + replay native-editor notebook output frames.

Sprint 79 split out of the monolithic ``notebook_outputs.py``.
Owns the ``NotebookOutput`` table — append-on-iopub, replay-on-open,
and the cross-table ``clear_*`` / ``rename_path`` cleanup helpers
that scrub output frames + cell-run lifecycle rows together when a
notebook is re-executed, restarted, deleted, or renamed.

Sprint 96 renamed the cell-identity column from ``cell_id`` (UUID)
to ``content_hash`` (``sha256(source)[:16]``); all function
signatures here follow that rename.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import NotebookCellRun, NotebookCellRunSource, NotebookOutput

_PERSISTED_MSG_TYPES = frozenset(
    {"stream", "execute_result", "display_data", "error"}
)


def is_persistable(msg_type: str) -> bool:
    """Return whether a Jupyter iopub message carries output content.

    Status + execute_input messages are pure metadata (kernel
    busy/idle, code echo) and never land in ``notebook_outputs``.

    Args:
        msg_type: Jupyter ``msg_type`` string from the iopub
            envelope.

    Returns:
        ``True`` for ``stream`` / ``execute_result`` /
        ``display_data`` / ``error``; ``False`` otherwise.
    """
    return msg_type in _PERSISTED_MSG_TYPES


def append_output(
    factory: sessionmaker[Session],
    *,
    file_path: str,
    content_hash: str,
    kernel_session_id: str,
    output_index: int,
    msg_type: str,
    content: dict[str, Any],
    metadata: dict[str, Any] | None = None,
) -> None:
    """Persist one iopub output message.

    Args:
        factory: SQLAlchemy session factory.
        file_path: Relative notebook path.
        content_hash: Cell identity — ``sha256(source)[:16]``.
        kernel_session_id: Current :class:`KernelSession`
            ``session_id``.
        output_index: 0-based position within the cell's outputs
            *for this kernel session*. The caller owns the
            counter.
        msg_type: One of :data:`_PERSISTED_MSG_TYPES`.
        content: The raw ``content`` dict from the Jupyter
            message. Stored verbatim as JSON.
        metadata: Optional ``metadata`` dict; ``None`` stores
            ``NULL`` in the column.
    """
    now = datetime.datetime.now(datetime.UTC)
    row = NotebookOutput(
        file_path=file_path,
        content_hash=content_hash,
        kernel_session_id=kernel_session_id,
        output_index=output_index,
        msg_type=msg_type,
        mime_bundle=json.dumps(content),
        output_metadata=json.dumps(metadata) if metadata else None,
        created_at=now,
    )
    with factory() as session:
        session.add(row)
        session.commit()


def load_outputs_for_path(
    factory: sessionmaker[Session],
    file_path: str,
) -> list[dict[str, Any]]:
    """Return every persisted output for a notebook, newest session first.

    Sprint-60 editor mount reads the latest session's outputs off
    this call and injects them into the initial Alpine payload.
    Multi-session UI is a future-sprint concern; this function
    returns ALL rows and leaves session filtering to the caller.

    Args:
        factory: SQLAlchemy session factory.
        file_path: Relative notebook path.

    Returns:
        One dict per row, in
        ``(content_hash, output_index, created_at)`` order. Each dict
        carries the keys ``content_hash`` / ``kernel_session_id`` /
        ``output_index`` / ``msg_type`` / ``content`` / ``metadata``
        / ``created_at``. ``content`` and ``metadata`` are
        JSON-decoded back into Python dicts.
    """
    with factory() as session:
        stmt = (
            select(NotebookOutput)
            .where(NotebookOutput.file_path == file_path)
            .order_by(
                NotebookOutput.content_hash,
                NotebookOutput.output_index,
                NotebookOutput.created_at,
            )
        )
        rows = session.execute(stmt).scalars().all()
    out: list[dict[str, Any]] = []
    for r in rows:
        out.append(
            {
                "content_hash": r.content_hash,
                "kernel_session_id": r.kernel_session_id,
                "output_index": r.output_index,
                "msg_type": r.msg_type,
                "content": json.loads(r.mime_bundle),
                "metadata": json.loads(r.output_metadata) if r.output_metadata else None,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
        )
    return out


def clear_cell(
    factory: sessionmaker[Session],
    *,
    file_path: str,
    content_hash: str,
) -> None:
    """Delete every persisted output for one cell, across sessions.

    Called on explicit "Clear outputs" or before a re-execute so
    the cell's view starts blank.

    Args:
        factory: SQLAlchemy session factory.
        file_path: Relative notebook path.
        content_hash: Cell identity.
    """
    with factory() as session:
        session.execute(
            delete(NotebookOutput).where(
                NotebookOutput.file_path == file_path,
                NotebookOutput.content_hash == content_hash,
            )
        )
        session.execute(
            delete(NotebookCellRun).where(
                NotebookCellRun.file_path == file_path,
                NotebookCellRun.content_hash == content_hash,
            )
        )
        # Sprint 73: deliberately do NOT cascade into
        # NotebookCellRunSource here — clear_cell is called on every
        # re-execute, and the per-execute history table is the audit
        # trail we want to PRESERVE across re-runs.  Cascade only
        # lives in clear_path + rename_path (file-level operations).
        session.commit()


def clear_session(
    factory: sessionmaker[Session],
    *,
    file_path: str,
    kernel_session_id: str,
) -> None:
    """Delete every persisted row for one kernel session.

    Called when the user restarts the kernel — the outgoing
    session's rows are purged so the editor view matches the
    new empty namespace.

    Args:
        factory: SQLAlchemy session factory.
        file_path: Relative notebook path.
        kernel_session_id: Session UUID to drop.
    """
    with factory() as session:
        session.execute(
            delete(NotebookOutput).where(
                NotebookOutput.file_path == file_path,
                NotebookOutput.kernel_session_id == kernel_session_id,
            )
        )
        session.execute(
            delete(NotebookCellRun).where(
                NotebookCellRun.file_path == file_path,
                NotebookCellRun.kernel_session_id == kernel_session_id,
            )
        )
        # Sprint 73: deliberately do NOT cascade into
        # NotebookCellRunSource on kernel restart — the history
        # table survives restarts so users can compare before-vs-
        # after-restart runs.  Cascade only on file delete / rename.
        session.commit()


def clear_path(
    factory: sessionmaker[Session],
    file_path: str,
) -> None:
    """Delete every persisted row for a notebook (e.g. on file delete).

    Wired from the Sprint 67 ``DELETE /api/notebooks`` route so that
    removing a file from the workspace also drops every output frame
    and per-cell run row for that path. The cascade is intentional:
    those rows are a replay cache keyed by ``file_path``, so leaving
    them orphaned would surface confusingly in a future notebook
    reusing the same name.

    Args:
        factory: SQLAlchemy session factory.
        file_path: Relative notebook path.
    """
    with factory() as session:
        session.execute(
            delete(NotebookOutput).where(NotebookOutput.file_path == file_path)
        )
        session.execute(
            delete(NotebookCellRun).where(NotebookCellRun.file_path == file_path)
        )
        session.execute(
            delete(NotebookCellRunSource).where(
                NotebookCellRunSource.file_path == file_path
            )
        )
        session.commit()


def rename_path(
    factory: sessionmaker[Session],
    old_path: str,
    new_path: str,
) -> None:
    """Re-key every output / run row from ``old_path`` to ``new_path``.

    Sprint 67 sidebar rename action. Rather than throw the replay
    cache away on rename (which would surprise a user whose only
    intent was to change the filename), we ``UPDATE`` the
    ``file_path`` column on both output and run tables so the next
    editor open at the new path replays the prior session verbatim.

    Args:
        factory: SQLAlchemy session factory.
        old_path: Relative path the rows are currently keyed under.
        new_path: New relative path to re-key onto.
    """
    with factory() as session:
        session.execute(
            update(NotebookOutput)
            .where(NotebookOutput.file_path == old_path)
            .values(file_path=new_path)
        )
        session.execute(
            update(NotebookCellRun)
            .where(NotebookCellRun.file_path == old_path)
            .values(file_path=new_path)
        )
        session.execute(
            update(NotebookCellRunSource)
            .where(NotebookCellRunSource.file_path == old_path)
            .values(file_path=new_path)
        )
        session.commit()
