"""Shared state + helpers for the per-operation audit trail.

Exposes the :class:`OperationRecorder` dataclass primitives mutate
during a call, the :data:`VALID_OP_NAMES` registry derived from the
:class:`OpName` StrEnum, and two warning-marker helpers
(:func:`_serialise_warnings`, :func:`_stamp_audit_marker`) used by
the lifecycle path and every post-commit hook in sibling modules.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError

from pointlessql.models import AgentRunOperation
from pointlessql.types import OpName

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


LINEAGE_FAILED_MARKER = "[lineage_emit_failed]"


VALID_OP_NAMES = frozenset(member.value for member in OpName)


@dataclass
class OperationRecorder:
    """Mutable state collected by a primitive while running.

    Primitives set the fields they know about on this recorder;
    :func:`operation_context` reads them at exit-time and writes the
    final ``agent_run_operations`` row.  Attribute setters are
    plain — the primitive's own logic is in charge of deciding
    whether a value applies (e.g. ``delta_version_before`` is only
    meaningful when the table existed).

    Attributes:
        input_sha: SHA-256 hex of the canonical Arrow IPC bytes (for
            writes / merges) or the concat-of-file-shas (for
            autoload).  ``None`` for read-only ``sql``.
        rows_affected: Row count produced by the primitive, or
            ``None`` when the primitive can't expose one.
        delta_version_before: ``DeltaTable.version()`` *before* the
            write, or ``None`` for new tables / read-only ops.
        delta_version_after: ``DeltaTable.version()`` *after* the
            write.
        target_table: Override for the value passed to
            :func:`operation_context` (autoload may discover the
            target's true URI mid-call).
        extra_params: Dict merged into ``params_json`` so the
            primitive can attach run-time stats (file counts, merge
            stats) without rebuilding the params dict.
        pending_lineage_edges:  hook — when a primitive
            knows the source-row → target-row mapping for a merge or
            write that carried ``_lineage_row_id`` it stashes
            ``{"source_table": str, "source_row_ids": list[str],
            "target_row_ids": list[str]}`` here.  The post-commit
            hook reads it (after ``op_id`` is known) and bulk-inserts
            into ``lineage_row_edges`` best-effort.
        pending_rejects:  hook — when a primitive ran
            with ``track_rejects=True`` and identified source rows
            that won't land in the target, it stashes
            ``{"source_table": str,
            "rejects": list[tuple[source_row_id, reason, detail]]}``
            here.  The post-commit hook bulk-inserts into
            ``lineage_row_rejects`` best-effort.
        pending_column_edges:  hook — every PQL
            primitive populates this with a list of
            :class:`~pointlessql.services.lineage_edges.ColumnEdgeSpec`
            entries describing the source-column → target-column
            mappings discovered at op time.  The post-commit hook
            bulk-inserts into ``lineage_column_map`` best-effort.
            ``None`` (the default) means the primitive had no
            mappings to record (e.g. read-only ops, or a write that
            ran without ``source_table_fqn``).
        pending_value_changes:  hook — when
            ``pql.merge(strategy="upsert", track_value_changes=True)``
            captured per-cell preimage/postimage pairs from the Delta
            CDF stream, it stashes the resulting list of
            :class:`~pointlessql.services.lineage_edges.ValueChangeSpec`
            entries here.  The post-commit hook bulk-inserts into
            ``lineage_value_changes`` best-effort.  ``None`` (the
            default) means the merge ran without opt-in or had no
            actual value differences.
        training_params_json:  hook — when ``pql.training_context()``
            wraps a training block with ``mlflow.autolog()`` enabled,
            it captures ``run.data.params`` + ``run.data.metrics`` at
            MLflow run-exit time and stashes the JSON-encoded blob
            here so :func:`record_operation` writes it onto
            ``agent_run_operations.training_params_json``.  ``None``
            for non-training ops.
        warnings: Non-fatal side-effect markers stamped by post-commit
            hooks (lineage emit, edge insert, reject, column, value-
            change failures).  Persisted into the row's
            ``warnings_json`` column so ``error_message`` stays clean.
        pending_contract_event: Phase-50 hook — when the data-product
            enforcement check fired (see
            :func:`pointlessql.data_products.check_contract_for_write`)
            the primitive stashes a tuple of
            ``(outcome, details, data_product_id)`` here.  The post-
            commit hook persists one ``data_product_contract_events``
            row keyed on the just-inserted ``op_id``.  ``None`` means
            "no enforcement attempted" — the post-commit hook is a
            no-op then.
    """

    input_sha: str | None = None
    rows_affected: int | None = None
    delta_version_before: int | None = None
    delta_version_after: int | None = None
    target_table: str | None = None
    extra_params: dict[str, Any] = field(default_factory=dict)
    pending_lineage_edges: dict[str, Any] | None = None
    pending_rejects: dict[str, Any] | None = None
    pending_column_edges: list[Any] | None = None
    pending_value_changes: list[Any] | None = None
    # autolog snapshot {"params": {...}, "metrics": {...}}
    # populated by ``training_context`` at MLflow run-exit time.
    training_params_json: str | None = None
    # BUG-grand-08 — non-fatal side-effect markers stamped by
    # post-commit hooks (lineage emit / edge insert / reject /
    # column / value-change failures).  Persisted into the row's
    # ``warnings_json`` column so ``error_message`` stays clean.
    warnings: list[str] = field(default_factory=list)
    # Phase 50 — populated by the data-product enforcement service.
    # Tuple of (outcome, details, data_product_id) where outcome is
    # one of CONTRACT_EVENT_OUTCOMES.  None means "enforcement not
    # checked" (interactive PQL or feature disabled).
    pending_contract_event: tuple[str, dict[str, Any], int | None] | None = None


def serialise_warnings(markers: list[str]) -> str | None:
    """Encode a marker list into the ``warnings_json`` blob shape.

    Returns ``None`` for an empty list so the column stays NULL when
    nothing was stamped; otherwise emits ``{"markers": [...]}`` so
    downstream consumers can extend the shape with new sub-keys
    without another schema change.

    Args:
        markers: List of bracketed-marker strings collected by the
            recorder during the op.

    Returns:
        JSON blob string, or ``None`` when ``markers`` is empty.
    """
    if not markers:
        return None
    return json.dumps({"markers": list(markers)}, sort_keys=False)


def stamp_audit_marker(session_factory: sessionmaker[Session], *, op_id: int, marker: str) -> None:
    """Append a best-effort marker to ``agent_run_operations.warnings_json``.

    Used when a side-effect (lineage emit, edge insert, reject /
    column / value-change record) failed but the underlying op
    succeeded — the audit row should still record that the
    side-effect was attempted, but ``error_message`` must stay
    reserved for "the primitive itself raised" (BUG-grand-08).

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Operation row to update.
        marker: Bracketed-marker prefixed string to append.
    """
    try:
        with session_factory() as session:
            row = session.get(AgentRunOperation, op_id)
            if row is None:
                return
            existing_markers: list[str] = []
            if row.warnings_json:
                try:
                    parsed = json.loads(row.warnings_json)
                    if isinstance(parsed, dict):
                        raw = parsed.get("markers")
                        if isinstance(raw, list):
                            existing_markers = [str(m) for m in raw]
                except TypeError, ValueError:
                    # Corrupted blob — discard and start fresh; we
                    # never lose successful primitive output here, only
                    # the previous warning history.
                    logger.warning(
                        "operation_context: warnings_json on op_id=%s was unparseable, resetting",
                        op_id,
                    )
            existing_markers.append(marker)
            row.warnings_json = json.dumps({"markers": existing_markers}, sort_keys=False)
            session.commit()
    except SQLAlchemyError:
        logger.exception(
            "operation_context: failed to stamp marker on op_id=%s: %s",
            op_id,
            marker,
        )
