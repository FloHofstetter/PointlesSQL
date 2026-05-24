"""Post-commit value-change hook (best-effort).

Persist :class:`LineageValueChange` rows when
``pql.merge(strategy="upsert", track_value_changes=True)`` captured
per-cell preimage/postimage pairs from the Delta CDF stream.  Like
the other post-commit hooks, failures stamp a
``[lineage_value_partial]`` marker rather than blocking the write.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pointlessql.services.agent_runs.operations._common import stamp_audit_marker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def record_value_changes_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    pending: list[Any] | None,
) -> None:
    """Persist  per-cell value changes in a best-effort pass.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        agent_run_id: PointlesSQL run UUID.
        pending: ``OperationRecorder.pending_value_changes`` payload —
            a list of
            :class:`~pointlessql.services.lineage_edges.ValueChangeSpec`
            entries.  ``None`` or empty when the merge ran without
            opt-in or had no actual value differences.
    """
    if not pending:
        return

    from pointlessql.config import get_settings
    from pointlessql.services.lineage_edges import record_value_changes

    settings = get_settings()
    failure = record_value_changes(
        session_factory,
        run_id=agent_run_id,
        op_id=op_id,
        changes=pending,
        pii_mode=settings.audit.pii_mode,
        pii_hash_secret=settings.audit.pii_hash_secret,
    )
    if failure is None:
        return
    stamp_audit_marker(session_factory, op_id=op_id, marker=f"[lineage_value_partial] {failure!r}")
