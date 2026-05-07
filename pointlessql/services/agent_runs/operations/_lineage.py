"""Post-commit lineage hooks (best-effort).

Three hooks fire after a successful op insert in
:func:`operation_context`: emit the OpenLineage event to soyuz,
persist row-level edges, persist column-level edges.  All three
share the same shape — call a service helper, check for failure,
stamp a marker via :func:`stamp_audit_marker` if anything went
wrong.  ``error_message`` stays reserved for "the primitive itself
raised" (BUG-grand-08); these failures land in
``warnings_json`` instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pointlessql.enums import OpName
from pointlessql.services.agent_runs.operations._common import (
    LINEAGE_FAILED_MARKER,
    stamp_audit_marker,
)

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker


def emit_lineage_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    op_name: str,
    target_table: str | None,
    params: dict[str, Any],
    extra_params: dict[str, Any],
    pending_column_edges: list[Any] | None = None,
    pending_value_changes: list[Any] | None = None,
) -> None:
    """Fire the soyuz OpenLineage event for a freshly-committed op row.

    Best-effort. A failure stamps a ``[lineage_emit_failed]`` marker
    into the row's ``warnings_json`` blob so the audit trail records
    that the side-effect was attempted but didn't reach soyuz; the
    underlying PQL write is never blocked, and ``error_message``
    stays reserved for "the primitive itself raised" (BUG-grand-08).

     extends the body with two optional output facets when
    the recorder collected matching pending entries:

    * ``columnLineage`` (OpenLineage 1.x) — built from
      ``pending_column_edges`` (one
      :class:`pointlessql.services.lineage_edges.ColumnEdgeSpec`
      per entry).
    * ``valueChange`` (PointlesSQL extension) — built from
      ``pending_value_changes`` (one
      :class:`pointlessql.services.lineage_edges.ValueChangeSpec`
      per entry).  PointlesSQL emits **already-redacted** values so
      cleartext PII never leaves the install.

    Args:
        session_factory: SQLAlchemy session factory used both to
            update the marker on failure and (transitively) by the
            soyuz client factory.
        op_id: Auto-assigned primary key of the just-committed
            ``agent_run_operations`` row.
        agent_run_id: PointlesSQL run UUID; used as the OpenLineage
            ``runId``.
        op_name: PQL primitive name.
        target_table: Output table FQN or ``None`` for read-only ops.
        params: Merged params dict (initial + recorder extras) used
            to derive ``referenced_tables`` for SQL ops.
        extra_params: Recorder extras alone — checked for
            ``source_table_fqn`` / ``source_volume_fqn`` declared by
            merge / write_table / autoload callers.
        pending_column_edges: Optional list of
            :class:`ColumnEdgeSpec` rows the merge / declarative
            primitive collected; populates the columnLineage facet.
        pending_value_changes: Optional list of
            :class:`ValueChangeSpec` rows the
            ``track_value_changes`` opt-in collected; populates the
            valueChange facet.
    """
    if op_name == OpName.ROLLBACK:
        return
    inputs: list[str] = []
    outputs: list[str] = []
    if target_table:
        outputs = [target_table]
    if op_name == OpName.SQL:
        refs = params.get("referenced_tables")
        if isinstance(refs, list):
            inputs = [str(r) for r in refs if isinstance(r, str)]
    else:
        src = extra_params.get("source_table_fqn")
        if isinstance(src, str) and src:
            inputs = [src]

    if not inputs and not outputs:
        return

    column_edges_payload: list[dict[str, Any]] = []
    if pending_column_edges:
        for spec in pending_column_edges:
            column_edges_payload.append(
                {
                    "source_table": getattr(spec, "source_table", None),
                    "source_column": getattr(spec, "source_column", None),
                    "target_column": getattr(spec, "target_column", None),
                    "transform_kind": getattr(spec, "transform_kind", None),
                }
            )

    value_changes_payload: list[dict[str, Any]] = []
    if pending_value_changes:
        for spec in pending_value_changes:
            value_changes_payload.append(
                {
                    "row_id": getattr(spec, "target_row_id", None),
                    "column": getattr(spec, "target_column", None),
                    "old_value": getattr(spec, "old_value", None),
                    "new_value": getattr(spec, "new_value", None),
                }
            )

    from pointlessql.services.soyuz_lineage import emit_event_sync

    failure = emit_event_sync(
        run_id=agent_run_id,
        op_name=op_name,
        inputs=inputs,
        outputs=outputs,
        column_edges=column_edges_payload or None,
        value_changes=value_changes_payload or None,
    )
    if failure is None:
        return

    stamp_audit_marker(
        session_factory, op_id=op_id, marker=f"{LINEAGE_FAILED_MARKER} {failure!r}"
    )


def record_row_edges_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    target_table: str | None,
    pending: dict[str, Any] | None,
) -> None:
    """Persist  per-row lineage edges in a best-effort pass.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        agent_run_id: PointlesSQL run UUID.
        target_table: Output table FQN; required to record edges.
        pending: ``OperationRecorder.pending_lineage_edges`` payload
            populated by ``pql.merge`` / ``pql.write_table`` when the
            source carried a ``_lineage_row_id`` column and the
            caller declared ``source_table_fqn``.  ``None`` when the
            primitive had no lineage to record.
    """
    if not pending or not target_table:
        return
    source_table = pending.get("source_table")
    source_row_ids = pending.get("source_row_ids")
    target_row_ids = pending.get("target_row_ids")
    source_model_uri = pending.get("source_model_uri")
    if (
        not isinstance(source_table, str)
        or not isinstance(source_row_ids, list)
        or not isinstance(target_row_ids, list)
        or not source_row_ids
    ):
        return

    from pointlessql.services.lineage_edges import record_edges

    failure = record_edges(
        session_factory,
        run_id=agent_run_id,
        op_id=op_id,
        source_table=source_table,
        target_table=target_table,
        source_row_ids=[str(s) for s in source_row_ids],
        target_row_ids=[str(t) for t in target_row_ids],
        source_model_uri=source_model_uri if isinstance(source_model_uri, str) else None,
    )
    if failure is None:
        return
    stamp_audit_marker(session_factory, op_id=op_id, marker=f"[lineage_edges_partial] {failure!r}")


def record_column_edges_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    agent_run_id: str,
    pending: list[Any] | None,
) -> None:
    """Persist  column-level lineage edges in a best-effort pass.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        agent_run_id: PointlesSQL run UUID.
        pending: ``OperationRecorder.pending_column_edges`` payload —
            a list of
            :class:`~pointlessql.services.lineage_edges.ColumnEdgeSpec`
            entries.  ``None`` or empty when the primitive had no
            mappings to record.
    """
    if not pending:
        return

    from pointlessql.services.lineage_edges import record_column_edges

    failure = record_column_edges(
        session_factory,
        run_id=agent_run_id,
        op_id=op_id,
        edges=pending,
    )
    if failure is None:
        return
    stamp_audit_marker(
        session_factory, op_id=op_id, marker=f"[lineage_column_partial] {failure!r}"
    )
