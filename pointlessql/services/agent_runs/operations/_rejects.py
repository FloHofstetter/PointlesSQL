"""Post-commit reject hook (best-effort).

Persist :class:`LineageRowReject` rows when the primitive ran with
``track_rejects=True`` and identified source rows that won't land
in the target.  Like the other post-commit hooks, failures here
stamp a ``[lineage_rejects_partial]`` marker into the op row's
``warnings_json`` blob rather than blocking the underlying write.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pointlessql.services.agent_runs.operations._common import stamp_audit_marker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def record_rejects_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    pending: dict[str, Any] | None,
) -> None:
    """Persist  reject markers in a best-effort pass.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        agent_run_id: PointlesSQL run UUID.
        pending: ``OperationRecorder.pending_rejects`` payload —
            ``{"source_table": str, "rejects": list[tuple[str, str,
            str | None]]}`` where each tuple is
            ``(source_row_id, reason, detail)``.  ``None`` when the
            primitive did not run with ``track_rejects=True`` or had
            no rows to drop.
    """
    if not pending:
        return
    source_table = pending.get("source_table")
    rejects = pending.get("rejects")
    if not isinstance(source_table, str) or not isinstance(rejects, list) or not rejects:
        return

    from pointlessql.services.lineage_edges import record_rejects

    failure = record_rejects(
        session_factory,
        run_id=agent_run_id,
        op_id=op_id,
        source_table=source_table,
        rejects=rejects,
    )
    if failure is None:
        return
    stamp_audit_marker(
        session_factory, op_id=op_id, marker=f"[lineage_rejects_partial] {failure!r}"
    )
