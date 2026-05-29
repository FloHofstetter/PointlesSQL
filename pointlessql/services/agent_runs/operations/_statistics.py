"""Post-commit hook: persist one ``data_product_statistics`` row.

When a write resolves to a data product the write path stashes
``(data_product_id, table_name, delta_log_version, row_count, shape,
profile_kind)`` on :attr:`OperationRecorder.pending_statistics`.
After the ``agent_run_operations`` row is inserted (so we have a real
``op_id`` to FK against) this hook reads the recorder and writes one
snapshot row, upgrading the shape from the on-demand profile cache
when one already exists for the exact delta version.

The recorder is the only state path: ``pending_statistics is None``
(interactive PQL, or a non-product write) makes this a no-op.
Failures stamp a ``[statistics_failed]`` marker rather than blocking
the underlying write, which already committed by the time this runs.
"""

from __future__ import annotations

import datetime
import json
import logging
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import SQLAlchemyError

from pointlessql.models.catalog._data_products import DataProductStatistics
from pointlessql.services.agent_runs.operations._common import stamp_audit_marker

if TYPE_CHECKING:
    from sqlalchemy.orm import Session, sessionmaker

logger = logging.getLogger(__name__)


def record_statistics_after_commit(
    session_factory: sessionmaker[Session],
    *,
    op_id: int,
    target_table: str | None,
    pending: tuple[int, str, int | None, int | None, dict[str, Any], str] | None,
) -> None:
    """Persist one statistics snapshot row keyed on *op_id*.

    Args:
        session_factory: SQLAlchemy session factory.
        op_id: Just-committed ``agent_run_operations.id``.
        target_table: Final ``catalog.schema.table`` of the write —
            used to look up an existing full profile in the
            ``table_stats`` cache for a shape upgrade.
        pending: ``OperationRecorder.pending_statistics`` payload —
            ``(data_product_id, table_name, delta_log_version,
            row_count, shape, profile_kind)``.  ``None`` short-circuits
            to a no-op.

    Notes:
        Failures here stamp ``[statistics_failed]`` into the op's
        ``warnings_json`` rather than raising.
    """
    if pending is None:
        return

    data_product_id, table_name, delta_log_version, row_count, shape, profile_kind = pending

    # When a full on-demand profile already exists for this exact delta
    # version, upgrade the cheap light shape from it so the discovery
    # surface shows richer per-column stats for free.
    if delta_log_version is not None and target_table:
        try:
            from pointlessql.services.table_stats import read_cached

            cached = read_cached(
                session_factory,
                full_name=target_table,
                delta_log_version=delta_log_version,
            )
            if cached:
                shape = _shape_from_cache(cached)
                profile_kind = "reused"
        except SQLAlchemyError:
            logger.exception(
                "statistics_after_commit: cache read failed for table=%s version=%s",
                target_table,
                delta_log_version,
            )

    try:
        with session_factory() as session:
            row = DataProductStatistics(
                data_product_id=data_product_id,
                agent_run_operation_id=op_id,
                table_name=table_name,
                delta_log_version=delta_log_version,
                row_count=row_count,
                shape_json=json.dumps(shape, sort_keys=True, default=str),
                profile_kind=profile_kind,
                freshness_lag_minutes=None,
                created_at=datetime.datetime.now(datetime.UTC),
            )
            session.add(row)
            session.commit()
    except SQLAlchemyError as exc:
        logger.exception(
            "statistics_after_commit: insert failed for op_id=%s dp_id=%s",
            op_id,
            data_product_id,
        )
        stamp_audit_marker(
            session_factory,
            op_id=op_id,
            marker=f"[statistics_failed] {exc!r}",
        )


def _shape_from_cache(cached: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a shape dict from cached per-column ``table_stats`` rows.

    Args:
        cached: Rows from :func:`pointlessql.services.table_stats.read_cached`
            — each ``{column_name, stats, ...}``.

    Returns:
        ``{column_count, columns:{<col>:{null_count, distinct, min,
        max}}}`` distilled from the cached profile.
    """
    columns: dict[str, Any] = {}
    for entry in cached:
        name = entry.get("column_name")
        stats = entry.get("stats") or {}
        if not isinstance(name, str) or not isinstance(stats, dict):
            continue
        columns[name] = {
            "null_count": stats.get("null_count"),
            "distinct": stats.get("distinct_count"),
            "min": stats.get("min"),
            "max": stats.get("max"),
        }
    return {"column_count": len(columns), "columns": columns}
