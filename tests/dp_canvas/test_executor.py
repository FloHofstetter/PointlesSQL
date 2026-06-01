"""End-to-end executor tests for the dp_canvas package.

These tests run real DuckDB + Delta against ``tmp_path`` and only mock
the soyuz UC client (so no live soyuz server is required).  They cover
the happy path (single source → materialise → port registration →
graph version), the multi-source join path (so lineage's referenced-
tables branch is exercised), the cycle-rejects-without-write contract,
and the graph-version monotonicity guarantee.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import MagicMock, patch

import deltalake
import pandas as pd
import pytest
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo

from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    DataProduct,
    DataProductCanvasGraph,
    DataProductOutputPort,
)
from pointlessql.services.dp_canvas import (
    CanvasDoc,
    execute_canvas,
    load_latest_graph,
    save_graph,
)
from tests.dp_canvas._helpers import edge, linear_doc, node

_EXECUTOR_MOD = "pointlessql.services.dp_canvas._executor"


@pytest.fixture
def factory():
    return app.state.session_factory


def _seed_data_product(factory, *, schema_name: str) -> int:
    """Insert a stub DataProduct row and return its primary key."""
    now = datetime.datetime.now(datetime.UTC)
    with factory.begin() as session:
        dp = DataProduct(
            workspace_id=1,
            catalog_name="main",
            schema_name=schema_name,
            description="",
            version="1.0.0",
            sla_minutes=60,
            steward_user_id=None,
            contract_yaml_hash=f"hash_{schema_name}",
            contract_json="{}",
            last_loaded_at=now,
            created_at=now,
        )
        session.add(dp)
        session.flush()
        return dp.id


def _seed_source_delta(tmp_path, *, name: str, rows: pd.DataFrame) -> str:
    """Write a tiny Delta table to *tmp_path* and return its filesystem path."""
    path = str(tmp_path / name)
    deltalake.write_deltalake(path, rows, mode="overwrite")
    return path


def _mock_soyuz(*, source_paths: dict[str, str], target_schema_root: str) -> MagicMock:
    """Build a soyuz client mock whose calls feed the executor.

    ``source_paths`` maps source FQNs to their on-disk Delta paths so
    ``_get_table.sync`` returns a ``TableInfo`` with ``storage_location``
    set.  Anything else 404s, which the executor's
    ``_register_target_if_new`` interprets as "new table — derive
    storage path from the schema".
    """
    return MagicMock()


def _install_soyuz_patches(monkeypatch, *, source_paths: dict[str, str], target_schema_root: str):
    """Patch ``_get_table`` / ``_get_schema`` / ``_create_table`` on the executor.

    Returns the three MagicMocks for assertions.
    """
    get_table = MagicMock()
    get_schema = MagicMock()
    create_table = MagicMock()

    def _table_sync(*, client: Any, full_name: str) -> Any:
        if full_name in source_paths:
            return TableInfo(
                name=full_name.split(".")[-1], storage_location=source_paths[full_name]
            )
        raise UnexpectedStatus(404, b"Not Found")

    def _schema_sync(*, client: Any, full_name: str) -> Any:
        return SchemaInfo(storage_root=target_schema_root)

    get_table.sync.side_effect = _table_sync
    get_schema.sync.side_effect = _schema_sync
    create_table.sync.return_value = TableInfo(name="created")

    monkeypatch.setattr(f"{_EXECUTOR_MOD}._get_table", get_table)
    monkeypatch.setattr(f"{_EXECUTOR_MOD}._get_schema", get_schema)
    monkeypatch.setattr(f"{_EXECUTOR_MOD}._create_table", create_table)
    return get_table, get_schema, create_table


# ---------------------------------------------------------- happy path


def test_simple_chain_materialises_and_registers_port(tmp_path, factory, monkeypatch) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_simple")
    src_path = _seed_source_delta(
        tmp_path, name="src_simple", rows=pd.DataFrame({"id": [1, 2, 3], "amt": [10, 20, 30]})
    )
    target_schema_root = str(tmp_path / "tgt_root")
    _install_soyuz_patches(
        monkeypatch,
        source_paths={"main.ex_simple.src": src_path},
        target_schema_root=target_schema_root,
    )

    doc = linear_doc(
        input_fqn="main.ex_simple.src",
        target_fqn="main.ex_simple.tgt",
        predicate="amt > 10",
        port_name="primary",
    )
    result = execute_canvas(
        factory,
        doc=doc,
        data_product_id=dp_id,
        soyuz_client=MagicMock(),
    )

    assert result.graph_version == 1
    assert len(result.sinks) == 1
    assert result.sinks[0].status == "ok"
    assert result.sinks[0].rows_written == 2
    assert result.sinks[0].target_fqn == "main.ex_simple.tgt"

    # Materialised Delta exists and carries the expected rows.
    written = deltalake.DeltaTable(f"{target_schema_root}/tgt").to_pandas()
    assert sorted(written["id"].tolist()) == [2, 3]

    # OutputPort row exists.
    with factory() as session:
        port = (
            session.query(DataProductOutputPort)
            .filter_by(data_product_id=dp_id, name="primary")
            .one()
        )
    assert port.location == "main.ex_simple.tgt"


def test_graph_version_monotonic_per_product(tmp_path, factory, monkeypatch) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_versions")
    src_path = _seed_source_delta(tmp_path, name="src_versions", rows=pd.DataFrame({"id": [1]}))
    target_schema_root = str(tmp_path / "vroot")
    _install_soyuz_patches(
        monkeypatch,
        source_paths={"main.ex_versions.src": src_path},
        target_schema_root=target_schema_root,
    )

    doc = linear_doc("main.ex_versions.src", "main.ex_versions.tgt")
    r1 = execute_canvas(factory, doc=doc, data_product_id=dp_id, soyuz_client=MagicMock())
    r2 = execute_canvas(factory, doc=doc, data_product_id=dp_id, soyuz_client=MagicMock())
    assert (r1.graph_version, r2.graph_version) == (1, 2)


def test_two_input_join_materialises(tmp_path, factory, monkeypatch) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_join")
    left = _seed_source_delta(
        tmp_path, name="left", rows=pd.DataFrame({"id": [1, 2], "v_l": ["a", "b"]})
    )
    right = _seed_source_delta(
        tmp_path, name="right", rows=pd.DataFrame({"id": [1, 2], "v_r": ["x", "y"]})
    )
    target_schema_root = str(tmp_path / "join_root")
    _install_soyuz_patches(
        monkeypatch,
        source_paths={"main.ex_join.l": left, "main.ex_join.r": right},
        target_schema_root=target_schema_root,
    )

    doc = CanvasDoc(
        nodes=[
            node("a", "InputPort", {"table_fqn": "main.ex_join.l"}),
            node("b", "InputPort", {"table_fqn": "main.ex_join.r"}),
            node("j", "Join", {"keys": ["id"], "how": "inner"}),
            node(
                "out",
                "OutputPort",
                {
                    "port_name": "joined",
                    "materialized_table": "main.ex_join.tgt",
                    "mode": "overwrite",
                },
            ),
        ],
        edges=[
            edge("e1", "a", "out", "j", "left"),
            edge("e2", "b", "out", "j", "right"),
            edge("e3", "j", "out", "out", "in"),
        ],
    )
    result = execute_canvas(factory, doc=doc, data_product_id=dp_id, soyuz_client=MagicMock())
    written = deltalake.DeltaTable(f"{target_schema_root}/tgt").to_pandas()
    assert result.sinks[0].rows_written == 2
    assert set(written.columns) >= {"id", "v_l", "v_r"}


# ---------------------------------------------------------- write modes


def _passthrough_doc(src_fqn: str, tgt_fqn: str, *, mode: str, merge_on=None) -> CanvasDoc:
    """InputPort → OutputPort with the given write mode (no transform)."""
    cfg: dict[str, Any] = {"port_name": "p", "materialized_table": tgt_fqn, "mode": mode}
    if merge_on is not None:
        cfg["merge_on"] = merge_on
    return CanvasDoc(
        nodes=[
            node("inp", "InputPort", {"table_fqn": src_fqn}),
            node("out", "OutputPort", cfg),
        ],
        edges=[edge("e", "inp", "out", "out", "in")],
    )


def test_materialize_append_adds_rows(tmp_path, factory, monkeypatch) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_append")
    src_path = _seed_source_delta(tmp_path, name="src_append", rows=pd.DataFrame({"id": [1, 2]}))
    target_root = str(tmp_path / "append_root")
    _install_soyuz_patches(
        monkeypatch,
        source_paths={"main.ex_append.src": src_path},
        target_schema_root=target_root,
    )
    doc = _passthrough_doc("main.ex_append.src", "main.ex_append.tgt", mode="append")
    r1 = execute_canvas(factory, doc=doc, data_product_id=dp_id, soyuz_client=MagicMock())
    assert r1.sinks[0].status == "ok"
    assert r1.sinks[0].rows_written == 2
    r2 = execute_canvas(factory, doc=doc, data_product_id=dp_id, soyuz_client=MagicMock())
    assert r2.sinks[0].rows_written == 2
    final = deltalake.DeltaTable(f"{target_root}/tgt").to_pandas()
    assert len(final) == 4


def test_materialize_merge_upserts(tmp_path, factory, monkeypatch) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_merge")
    src_path = _seed_source_delta(
        tmp_path, name="src_merge", rows=pd.DataFrame({"id": [1, 2, 3], "amt": [10, 20, 30]})
    )
    target_root = str(tmp_path / "merge_root")
    # Mutable source-path map: after the first run we register the target so
    # _register_target_if_new reports it as existing (target_was_new=False),
    # which routes the second run through the real MERGE INTO path.
    src_paths = {"main.ex_merge.src": src_path}
    _install_soyuz_patches(monkeypatch, source_paths=src_paths, target_schema_root=target_root)
    doc = _passthrough_doc("main.ex_merge.src", "main.ex_merge.tgt", mode="merge", merge_on=["id"])

    r1 = execute_canvas(factory, doc=doc, data_product_id=dp_id, soyuz_client=MagicMock())
    assert r1.sinks[0].status == "ok"
    seeded = deltalake.DeltaTable(f"{target_root}/tgt").to_pandas()
    assert sorted(seeded["id"].tolist()) == [1, 2, 3]  # first run seeds via overwrite

    src_paths["main.ex_merge.tgt"] = f"{target_root}/tgt"  # target now "exists"
    deltalake.write_deltalake(
        src_path, pd.DataFrame({"id": [2, 4], "amt": [999, 40]}), mode="overwrite"
    )
    r2 = execute_canvas(factory, doc=doc, data_product_id=dp_id, soyuz_client=MagicMock())
    assert r2.sinks[0].status == "ok"
    assert r2.sinks[0].rows_written == 2  # 1 updated (id=2) + 1 inserted (id=4)

    merged = deltalake.DeltaTable(f"{target_root}/tgt").to_pandas().set_index("id")
    assert sorted(merged.index.tolist()) == [1, 2, 3, 4]
    assert merged.loc[2, "amt"] == 999  # matched row updated
    assert merged.loc[4, "amt"] == 40  # unmatched row inserted
    assert merged.loc[1, "amt"] == 10  # untouched row preserved


# ---------------------------------------------------------- error paths


def test_cycle_raises_validation_error_no_write(tmp_path, factory, monkeypatch) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_cycle")
    target_schema_root = str(tmp_path / "cycle_root")
    _install_soyuz_patches(
        monkeypatch,
        source_paths={},
        target_schema_root=target_schema_root,
    )

    doc = CanvasDoc(
        nodes=[
            node("a", "Filter", {"predicate": "1=1"}),
            node("b", "Filter", {"predicate": "2=2"}),
            node(
                "out",
                "OutputPort",
                {"port_name": "p", "materialized_table": "main.ex_cycle.tgt", "mode": "overwrite"},
            ),
        ],
        edges=[
            edge("e1", "a", "out", "b", "in"),
            edge("e2", "b", "out", "a", "in"),
            edge("e3", "b", "out", "out", "in"),
        ],
    )
    with pytest.raises(ValidationError, match="cycle"):
        execute_canvas(factory, doc=doc, data_product_id=dp_id, soyuz_client=MagicMock())

    # No graph version should have been minted.
    with factory() as session:
        count = session.query(DataProductCanvasGraph).filter_by(data_product_id=dp_id).count()
    assert count == 0


def test_missing_output_port_raises_validation_error(tmp_path, factory, monkeypatch) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_noout")
    _install_soyuz_patches(monkeypatch, source_paths={}, target_schema_root=str(tmp_path))

    doc = CanvasDoc(
        nodes=[node("inp", "InputPort", {"table_fqn": "main.x.y"})],
        edges=[],
    )
    with pytest.raises(ValidationError, match="OutputPort"):
        execute_canvas(factory, doc=doc, data_product_id=dp_id, soyuz_client=MagicMock())


# ---------------------------------------------------------- agent-run lineage


def test_canvas_materialize_op_recorded_under_agent_run(tmp_path, factory, monkeypatch) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_audit")
    src_path = _seed_source_delta(tmp_path, name="src_audit", rows=pd.DataFrame({"id": [1, 2]}))
    target_schema_root = str(tmp_path / "audit_root")
    _install_soyuz_patches(
        monkeypatch,
        source_paths={"main.ex_audit.src": src_path},
        target_schema_root=target_schema_root,
    )

    run_id = "run-canvas-test"
    now = datetime.datetime.now(datetime.UTC)
    with factory.begin() as session:
        run = AgentRun(
            id=run_id,
            agent_id="canvas-test-agent",
            principal="test@test.com",
            notebook_path="canvas-test.py",
            status="running",
            workspace_id=1,
            started_at=now,
        )
        session.add(run)

    # Patch soyuz_lineage so the emit call does not actually hit the network.
    with patch(
        "pointlessql.services.soyuz_lineage.emit_event_sync",
        return_value=None,
    ):
        doc = linear_doc("main.ex_audit.src", "main.ex_audit.tgt")
        result = execute_canvas(
            factory,
            doc=doc,
            data_product_id=dp_id,
            soyuz_client=MagicMock(),
            agent_run_id=run_id,
        )
    assert result.sinks[0].rows_written == 2

    with factory() as session:
        op = (
            session.query(AgentRunOperation)
            .filter_by(agent_run_id=run_id, op_name="canvas_materialize")
            .one()
        )
    assert op.target_table == "main.ex_audit.tgt"


def test_canvas_materialize_lineage_uses_referenced_tables(tmp_path, factory, monkeypatch) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_lineage")
    left = _seed_source_delta(tmp_path, name="lin_left", rows=pd.DataFrame({"id": [1], "x": [1]}))
    right = _seed_source_delta(tmp_path, name="lin_right", rows=pd.DataFrame({"id": [1], "y": [2]}))
    target_schema_root = str(tmp_path / "lin_root")
    _install_soyuz_patches(
        monkeypatch,
        source_paths={"main.ex_lineage.l": left, "main.ex_lineage.r": right},
        target_schema_root=target_schema_root,
    )

    run_id = "run-canvas-lineage"
    now = datetime.datetime.now(datetime.UTC)
    with factory.begin() as session:
        run = AgentRun(
            id=run_id,
            agent_id="canvas-lineage-agent",
            principal="test@test.com",
            notebook_path="canvas-lineage.py",
            status="running",
            workspace_id=1,
            started_at=now,
        )
        session.add(run)

    captured_inputs: list[list[str]] = []

    def _capture(
        *,
        run_id,
        op_name,
        inputs,
        outputs,
        event_type="COMPLETE",
        column_edges=None,
        value_changes=None,
    ):
        captured_inputs.append(list(inputs))
        return None

    with patch(
        "pointlessql.services.soyuz_lineage.emit_event_sync",
        side_effect=_capture,
    ):
        doc = CanvasDoc(
            nodes=[
                node("a", "InputPort", {"table_fqn": "main.ex_lineage.l"}),
                node("b", "InputPort", {"table_fqn": "main.ex_lineage.r"}),
                node("j", "Join", {"keys": ["id"], "how": "inner"}),
                node(
                    "out",
                    "OutputPort",
                    {
                        "port_name": "lin",
                        "materialized_table": "main.ex_lineage.tgt",
                        "mode": "overwrite",
                    },
                ),
            ],
            edges=[
                edge("e1", "a", "out", "j", "left"),
                edge("e2", "b", "out", "j", "right"),
                edge("e3", "j", "out", "out", "in"),
            ],
        )
        execute_canvas(
            factory,
            doc=doc,
            data_product_id=dp_id,
            soyuz_client=MagicMock(),
            agent_run_id=run_id,
        )

    assert captured_inputs, "lineage emission was not invoked"
    flat = sorted(captured_inputs[0])
    assert flat == ["main.ex_lineage.l", "main.ex_lineage.r"]


# ---------------------------------------------------------- storage helpers


def test_save_and_load_graph_round_trip(factory) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_storage")
    doc = linear_doc("main.ex_storage.src", "main.ex_storage.tgt")
    v1 = save_graph(factory, data_product_id=dp_id, doc=doc, author_user_id=None)
    v2 = save_graph(factory, data_product_id=dp_id, doc=doc, author_user_id=None)
    assert (v1, v2) == (1, 2)
    loaded = load_latest_graph(factory, data_product_id=dp_id)
    assert loaded is not None
    loaded_doc, latest_version = loaded
    assert latest_version == 2
    assert [n.block_type for n in loaded_doc.nodes] == ["InputPort", "OutputPort"]


def test_load_latest_graph_returns_none_when_empty(factory) -> None:
    dp_id = _seed_data_product(factory, schema_name="ex_storage_empty")
    assert load_latest_graph(factory, data_product_id=dp_id) is None
