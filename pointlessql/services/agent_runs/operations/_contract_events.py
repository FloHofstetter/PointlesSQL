"""Post-commit hook: persist one ``data_product_contract_events`` row.

When :func:`pointlessql.data_products.check_contract_for_write`
fires for a primitive, the recorder stashes
``(outcome, details, data_product_id)`` on
:attr:`OperationRecorder.pending_contract_event`.  After the
``agent_run_operations`` row is inserted (so we have a real
``op_id`` to FK against) this hook reads the recorder and writes
one event row.  Failures stamp a ``[contract_event_failed]`` marker
onto the op's ``warnings_json`` blob rather than blocking the
underlying write.

The recorder is the only state path: when ``pending_contract_event``
is ``None`` (interactive PQL, or the target schema has no contract)
this hook is a no-op.
"""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError

from pointlessql.models.catalog._data_products import (
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.services.agent_runs.operations._common import stamp_audit_marker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def record_contract_event_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    pending: tuple[str, dict[str, Any], int | None] | None,
) -> None:
    """Persist one contract-event row keyed on *op_id*.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        pending: ``OperationRecorder.pending_contract_event`` payload
            — ``(outcome, details_dict, data_product_id_or_None)``.
            ``None`` short-circuits to a no-op (no enforcement was
            attempted).

    Notes:
        Failures here stamp ``[contract_event_failed]`` into the op's
        ``warnings_json`` rather than raising — the underlying write
        already succeeded by the time this hook runs.
    """
    if pending is None:
        return

    outcome, details, data_product_id = pending
    try:
        with session_factory() as session:
            row = DataProductContractEvent(
                agent_run_operation_id=op_id,
                data_product_id=data_product_id,
                outcome=outcome,
                details_json=json.dumps(details, sort_keys=True, default=str),
                created_at=datetime.datetime.now(datetime.UTC),
            )
            session.add(row)
            session.commit()
    except SQLAlchemyError as exc:
        logger.exception(
            "contract_event_after_commit: insert failed for op_id=%s outcome=%s",
            op_id,
            outcome,
        )
        stamp_audit_marker(
            session_factory,
            op_id=op_id,
            marker=f"[contract_event_failed] {exc!r}",
        )
        return

    # fire-and-forget governance event on
    # contract violations.  The DataProductContractEvent row above is
    # the authoritative audit record; this emit only adds the
    # streaming-delivery leg (webhook / S3 / CloudTrail sinks).  We
    # only stream on the ``violated`` outcome — schema-drift warnings
    # and compliant writes are already covered by the per-row audit
    # surface and don't warrant an extra envelope per write.
    if outcome != "violated" or data_product_id is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        # No event loop (sync test harness, REPL).  The
        # DataProductContractEvent row already persisted; the streaming
        # event is best-effort and is skipped gracefully.
        return

    workspace_id = _resolve_workspace_id(session_factory, data_product_id)
    if workspace_id is None:
        return
    # Imported inside the function so the sync codepath (no event
    # loop) doesn't pay the import cost when emit is a no-op.
    from pointlessql.services.workspace.governance import (
        EVENT_TYPE_DATA_PRODUCT_CONTRACT_VIOLATED,
        emit_governance_event,
        spawn_governance_event,
    )

    spawn_governance_event(
        loop,
        emit_governance_event(
            EVENT_TYPE_DATA_PRODUCT_CONTRACT_VIOLATED,
            {
                "data_product_id": data_product_id,
                "agent_run_operation_id": op_id,
                "outcome": outcome,
                "details": details,
            },
            session_factory=session_factory,
            workspace_id=workspace_id,
        ),
        label="contract_violated",
    )


def _resolve_workspace_id(
    session_factory: sessionmaker[Session],
    data_product_id: int,
) -> int | None:
    """Look up the workspace_id for *data_product_id*; ``None`` on miss."""
    try:
        with session_factory() as session:
            row = session.get(DataProduct, data_product_id)
            return row.workspace_id if row is not None else None
    except SQLAlchemyError:
        logger.exception(
            "contract_event_after_commit: workspace lookup failed for dp_id=%s",
            data_product_id,
        )
        return None
