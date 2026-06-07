"""Run real PQL primitives offline and snapshot their recorded lineage.

Wires a ``PQL`` instance to a throwaway Delta root with the three soyuz
syncs mocked (no live catalog), runs one primitive under a fresh
``agent_run_id``, then builds an :class:`OperationFacts` from the recorded
rows.  Each call uses its own run + operation id, so many Hypothesis
examples can share one test function without cross-talk (lineage rows are
always read back by ``op_id``).
"""

from __future__ import annotations

import datetime as _dt
import itertools
import os
import tempfile
from collections.abc import Sequence
from contextlib import ExitStack, contextmanager
from typing import Any
from unittest.mock import MagicMock, patch

import deltalake
import pandas as pd
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo

import pointlessql.db
from pointlessql.api.main import app
from pointlessql.models import AgentRun
from pointlessql.pql import PQL, PandasEngine
from pointlessql.pql._merge._constants import LINEAGE_ROW_ID_COLUMN
from pointlessql.pql._types import SQLResult
from pointlessql.services.lineage.verify import OperationFacts
from tests.lineage_verify._facts import facts_for_op, latest_op_id

_run_counter = itertools.count(1)

_CATALOG = "lv"


def fresh_run_id() -> str:
    """Return a process-unique ``agent_run_id`` (deterministic counter order)."""
    return f"lineage-verify-{next(_run_counter)}"


def _seed_run(factory: Any, run_id: str) -> None:
    """Insert one ``AgentRun`` so ``operation_context`` has its FK target."""
    now = _dt.datetime.now(_dt.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="lineage-verify",
                notebook_path=f"/tmp/{run_id}.py",
                status="running",
                started_at=now,
            )
        )
        session.commit()


@contextmanager
def _bound_factory(factory: Any):
    """Make ``pql`` primitives resolve the conftest test session factory."""
    with patch.object(pointlessql.db, "_session_factory", factory):
        yield


@contextmanager
def _patched_soyuz_write(
    storage_root: str, *, pre_existing: bool, target_storage: str | None = None
):
    """Mock the three soyuz syncs ``pql._write`` resolves at runtime."""
    with ExitStack() as stack:
        mget = stack.enter_context(patch("pointlessql.pql._write._get_table"))
        mschema = stack.enter_context(patch("pointlessql.pql._write._get_schema"))
        mcreate = stack.enter_context(patch("pointlessql.pql._write._create_table"))
        if pre_existing:
            mget.sync.return_value = TableInfo(storage_location=target_storage, name="t")
        else:
            mget.sync.side_effect = UnexpectedStatus(404, b"Not Found")
        mschema.sync.return_value = SchemaInfo(storage_root=storage_root, name="silver")
        mcreate.sync.return_value = TableInfo(name="t")
        yield


def run_write_op(
    *,
    frame: pd.DataFrame,
    source_fqn: str,
    table_name: str,
    source_model_uri: str | None = None,
) -> OperationFacts:
    """Run one ``write_table`` from a lineage-bearing source and snapshot it.

    Args:
        frame: The frame to write; must carry ``_lineage_row_id``.
        source_fqn: Declared upstream table (stamped on the recorded edges).
        table_name: Bare table name (also the storage subdirectory).
        source_model_uri: Optional model URI stamped on every edge.

    Returns:
        The recorded operation as a pure :class:`OperationFacts`.
    """
    factory = app.state.session_factory
    run_id = fresh_run_id()
    _seed_run(factory, run_id)
    source_ids = [v if isinstance(v, str) else "" for v in frame[LINEAGE_ROW_ID_COLUMN].tolist()]
    target_fqn = f"{_CATALOG}.silver.{table_name}"
    with tempfile.TemporaryDirectory() as root:
        storage_root = f"{root}/warehouse"
        output_path = f"{storage_root}/{table_name}"
        with _bound_factory(factory), _patched_soyuz_write(storage_root, pre_existing=False):
            pql = PQL(client=MagicMock(), agent_run_id=run_id, engine=PandasEngine())
            pql.write_table(
                frame,
                target_fqn,
                source_table_fqn=source_fqn,
                source_model_uri=source_model_uri,
            )
        op_id = latest_op_id(factory, run_id)
        return facts_for_op(
            factory,
            op_id=op_id,
            target_table=target_fqn,
            source_row_ids=source_ids,
            output_path=output_path,
        )


def _result_to_frame(result: SQLResult) -> pd.DataFrame:
    """Rebuild a DataFrame from a SQLResult's columns + rows."""
    names = [c["name"] for c in result.columns]
    return pd.DataFrame(result.rows, columns=names)


def run_sql_then_write_op(
    *,
    bronze_frame: pd.DataFrame,
    select_columns: Sequence[str],
    table_name: str,
    preserve_lineage_row_id: bool = True,
) -> OperationFacts:
    """Run bronze -> ``PQL.sql`` projection -> silver ``write_table`` and snapshot it.

    The SELECT omits ``_lineage_row_id`` (the 15.8 shape).  With
    auto-projection on, the column survives and the silver write records
    edges back to every bronze row; the returned facts use the *bronze* row
    population as the source, so a dropped column surfaces as an INV-1
    violation rather than a silent zero-edge write.

    Args:
        bronze_frame: The upstream frame; carries ``_lineage_row_id``.
        select_columns: Business columns the SELECT projects (no lineage id).
        table_name: Bare silver table name (also the storage subdirectory).
        preserve_lineage_row_id: Forwarded to ``PQL.sql``; ``False`` disables
            auto-projection (used to prove the suite catches a real drop).

    Returns:
        The silver write recorded as a pure :class:`OperationFacts`.
    """
    factory = app.state.session_factory
    bronze_ids = [str(v) for v in bronze_frame[LINEAGE_ROW_ID_COLUMN].tolist()]
    with tempfile.TemporaryDirectory() as root:
        warehouse = f"{root}/warehouse"
        bronze_fqn = f"{_CATALOG}.bronze.bronze_src"
        bronze_path = f"{warehouse}/bronze_src"
        deltalake.write_deltalake(bronze_path, bronze_frame)

        sql_run_id = fresh_run_id()
        _seed_run(factory, sql_run_id)
        query = f"SELECT {', '.join(select_columns)} FROM {bronze_fqn}"
        with (
            _bound_factory(factory),
            patch.dict(os.environ, {"POINTLESSQL_AGENT_RUN_ID": sql_run_id}),
        ):
            result = PQL.sql(
                query,
                approved_tables={bronze_fqn: bronze_path},
                preserve_lineage_row_id=preserve_lineage_row_id,
            )
        silver_frame = _result_to_frame(result)

        write_run_id = fresh_run_id()
        _seed_run(factory, write_run_id)
        target_fqn = f"{_CATALOG}.silver.{table_name}"
        output_path = f"{warehouse}/{table_name}"
        with _bound_factory(factory), _patched_soyuz_write(warehouse, pre_existing=False):
            pql = PQL(client=MagicMock(), agent_run_id=write_run_id, engine=PandasEngine())
            pql.write_table(silver_frame, target_fqn, source_table_fqn=bronze_fqn)
        op_id = latest_op_id(factory, write_run_id)
        return facts_for_op(
            factory,
            op_id=op_id,
            target_table=target_fqn,
            source_row_ids=bronze_ids,
            output_path=output_path,
        )
