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

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError

from pointlessql.models.data_products import DataProductContractEvent
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
