"""Build an OperationFacts snapshot from recorded lineage rows.

The I/O bridge between a just-run PQL primitive and the pure invariant
checkers: it reads the output Delta table's column + row-id populations and
the four lineage tables (filtered by ``op_id``), then hands everything to the
pure ``facts_from_rows`` adapter.  Lives under ``tests/`` (not the import-pure
``verify`` package) precisely because it touches Delta + SQLAlchemy.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import deltalake

from pointlessql.models import (
    AgentRunOperation,
    LineageColumnMap,
    LineageRowEdge,
    LineageRowReject,
    LineageValueChange,
)
from pointlessql.pql._merge._constants import LINEAGE_ROW_ID_COLUMN
from pointlessql.services.lineage.verify import OperationFacts, facts_from_rows


def latest_op_id(factory: Any, run_id: str) -> int:
    """Return the single operation id recorded under ``run_id``."""
    with factory() as session:
        op = (
            session.query(AgentRunOperation)
            .filter(AgentRunOperation.agent_run_id == run_id)
            .order_by(AgentRunOperation.id.desc())
            .first()
        )
        assert op is not None, f"no operation recorded under run {run_id!r}"
        return int(op.id)


def read_output_population(output_path: str) -> tuple[list[str], list[str]]:
    """Return ``(output_columns, output_row_ids)`` of a written Delta table."""
    table = deltalake.DeltaTable(output_path).to_pyarrow_table()
    columns = list(table.column_names)
    if LINEAGE_ROW_ID_COLUMN in columns:
        ids = [
            v if isinstance(v, str) else "" for v in table.column(LINEAGE_ROW_ID_COLUMN).to_pylist()
        ]
    else:
        ids = []
    return columns, ids


def facts_for_op(
    factory: Any,
    *,
    op_id: int,
    target_table: str,
    source_row_ids: Sequence[str],
    output_path: str,
    aggregate: bool = False,
) -> OperationFacts:
    """Assemble OperationFacts for one recorded op from Delta + lineage tables."""
    output_columns, output_row_ids = read_output_population(output_path)
    with factory() as session:
        edges = session.query(LineageRowEdge).filter(LineageRowEdge.op_id == op_id).all()
        rejects = session.query(LineageRowReject).filter(LineageRowReject.op_id == op_id).all()
        colmap = session.query(LineageColumnMap).filter(LineageColumnMap.op_id == op_id).all()
        values = session.query(LineageValueChange).filter(LineageValueChange.op_id == op_id).all()
        return facts_from_rows(
            target_table=target_table,
            source_row_ids=source_row_ids,
            output_columns=output_columns,
            output_row_ids=output_row_ids,
            edge_rows=edges,
            reject_rows=rejects,
            colmap_rows=colmap,
            value_rows=values,
            aggregate=aggregate,
        )
