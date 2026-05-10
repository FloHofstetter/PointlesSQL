"""Phase 15.8 — End-to-end lineage wiring contract tests.

These tests pin the contract that the seed-full-stack-demo
acceptance gate depends on: when an agent writes a frame that
carries ``_lineage_row_id``, the post-commit hook on
``pql.write_table`` (and the matching path on ``pql.merge``)
records ``lineage_row_edges`` rows; when the frame does NOT
carry the column, no edges are recorded.  The 2026-04-30
``seed-full-stack-demo.py`` Phase-2 replay surfaced that
``demo_ml.silver.*`` produced 0 edges because the silver
``PQL.sql`` projection stripped ``_lineage_row_id`` before
calling ``pql.write_table`` — these tests pin both branches of
that contract so the wiring cannot silently regress.

The five scenarios mirror the four lineage axes the demo
exercises (Sprint 15 row-edges, Sprint 15.7 value-changes,
Sprint 21.7 source_model_uri) plus the Sprint 15.8 INFO-log
diagnostic that flags drops at SELECT time.  All five pass
against the current production code; the actual demo fix lives
in ``scripts/seed-full-stack-demo.py`` (Sprint 15.8.2).
"""

from __future__ import annotations

import datetime as _dt
import logging
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import deltalake
import pandas as pd
import pytest
from soyuz_catalog_client.errors import UnexpectedStatus
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.table_info import TableInfo

import pointlessql.db
from pointlessql.api.main import app
from pointlessql.models import (
    AgentRun,
    AgentRunOperation,
    LineageRowEdge,
    LineageValueChange,
)
from pointlessql.pql import PQL, PandasEngine


def _seed_run(factory: Any, run_id: str) -> None:
    """Insert one ``AgentRun`` row so ``operation_context`` has FK target."""
    now = _dt.datetime.now(_dt.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="phase158-tester",
                notebook_path=f"/tmp/{run_id}.py",
                status="running",
                started_at=now,
            )
        )
        session.commit()


def _bind_get_session_factory(monkeypatch: pytest.MonkeyPatch, factory: Any) -> None:
    """Make ``pql.write_table`` see the conftest test factory.

    ``pointlessql.db.get_session_factory`` is the live entrypoint that
    primitives import lazily; the conftest only wires ``app.state``,
    so we monkeypatch the module-level bind for the duration of one
    test.
    """
    monkeypatch.setattr(pointlessql.db, "_session_factory", factory)


def _patched_soyuz(
    *,
    storage_root: str,
    pre_existing: bool,
    target_storage: str | None = None,
) -> Any:
    """Return a context manager stack mocking the three soyuz syncs.

    Patches the symbols ``pql._write`` resolves at runtime:

    * ``_get_table.sync`` — ``UnexpectedStatus(404)`` when
      ``pre_existing=False`` so ``write_table`` enters the create
      branch; ``TableInfo`` with ``storage_location`` otherwise.
    * ``_get_schema.sync`` — ``SchemaInfo`` with ``storage_root`` so
      ``derive_storage_location`` can compute the table path.
    * ``_create_table.sync`` — no-op success.

    The caller is expected to enter the returned ``ExitStack``.
    """
    from contextlib import ExitStack

    stack = ExitStack()
    mget = stack.enter_context(patch("pointlessql.pql._write._get_table"))
    mschema = stack.enter_context(patch("pointlessql.pql._write._get_schema"))
    mcreate = stack.enter_context(patch("pointlessql.pql._write._create_table"))

    if pre_existing:
        assert target_storage is not None
        mget.sync.return_value = TableInfo(
            storage_location=target_storage,
            name="t",
        )
    else:
        mget.sync.side_effect = UnexpectedStatus(404, b"Not Found")

    mschema.sync.return_value = SchemaInfo(
        storage_root=storage_root,
        name="silver",
    )
    mcreate.sync.return_value = TableInfo(name="t")
    return stack


def _bronze_frame(n: int = 5) -> pd.DataFrame:
    """Return a 5-row bronze-shaped DataFrame with ``_lineage_row_id``."""
    return pd.DataFrame(
        {
            "house_id": list(range(1, n + 1)),
            "size_sqft": [1000 + i * 100 for i in range(n)],
            "_lineage_row_id": [f"bronze-row-{i}" for i in range(1, n + 1)],
        }
    )


# ---------- Axis 1 — row-edges ----------


def test_write_table_records_edges_when_frame_carries_lineage_row_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    auth_cookies: dict[str, str],
) -> None:
    """Frame WITH ``_lineage_row_id`` → ``lineage_row_edges`` rows land.

    Positive contract: this is the path the seed-demo's silver step
    must reach after the Sprint-15.8.2 SELECT fix.
    """
    factory = app.state.session_factory
    _bind_get_session_factory(monkeypatch, factory)

    run_id = "phase158-row-edges-pos"
    _seed_run(factory, run_id)

    df = _bronze_frame(5)
    storage_root = str(tmp_path / "warehouse")

    with _patched_soyuz(storage_root=storage_root, pre_existing=False):
        pql = PQL(
            client=MagicMock(),
            agent_run_id=run_id,
            engine=PandasEngine(),
        )
        pql.write_table(
            df,
            "test_demo_ml.silver.houses",
            source_table_fqn="test_demo_ml.bronze.houses",
        )

    with factory() as session:
        edges = (
            session.query(LineageRowEdge)
            .filter(LineageRowEdge.target_table == "test_demo_ml.silver.houses")
            .all()
        )
    assert len(edges) == 5
    assert {e.source_table for e in edges} == {"test_demo_ml.bronze.houses"}
    assert {e.source_row_id for e in edges} == {f"bronze-row-{i}" for i in range(1, 6)}


def test_write_table_records_no_edges_when_frame_lacks_lineage_row_id(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    auth_cookies: dict[str, str],
) -> None:
    """Frame WITHOUT ``_lineage_row_id`` → zero edges.

    This is today's seed-demo silver behaviour (the SELECT projects
    only business columns).  The contract is intentional — minting
    synthetic IDs would be a lie about provenance — but the demo
    must avoid this branch to populate the lineage UI.
    """
    factory = app.state.session_factory
    _bind_get_session_factory(monkeypatch, factory)

    run_id = "phase158-row-edges-neg"
    _seed_run(factory, run_id)

    df = _bronze_frame(5).drop(columns=["_lineage_row_id"])
    assert "_lineage_row_id" not in df.columns
    storage_root = str(tmp_path / "warehouse")

    with _patched_soyuz(storage_root=storage_root, pre_existing=False):
        pql = PQL(
            client=MagicMock(),
            agent_run_id=run_id,
            engine=PandasEngine(),
        )
        pql.write_table(
            df,
            "test_demo_ml.silver.houses_clean",
            source_table_fqn="test_demo_ml.bronze.houses",
        )

    with factory() as session:
        edges = (
            session.query(LineageRowEdge)
            .filter(LineageRowEdge.target_table == "test_demo_ml.silver.houses_clean")
            .all()
        )
    assert edges == []


# ---------- Axis 3 — source_model_uri ----------


def test_write_table_stamps_source_model_uri_on_edges(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    auth_cookies: dict[str, str],
) -> None:
    """Inference write with ``source_model_uri`` → every edge stamped.

    Mirrors ``_step_inference`` in the seed-demo: predictions write
    declares the originating model URI so the model-detail Lineage
    DAG can paint the predictions table downstream.
    """
    factory = app.state.session_factory
    _bind_get_session_factory(monkeypatch, factory)

    run_id = "phase158-model-uri"
    _seed_run(factory, run_id)

    df = _bronze_frame(3)
    df["predicted_price"] = [100, 200, 300]
    storage_root = str(tmp_path / "warehouse")
    model_uri = "models:/test_demo_ml.gold.price_v1/1"

    with _patched_soyuz(storage_root=storage_root, pre_existing=False):
        pql = PQL(
            client=MagicMock(),
            agent_run_id=run_id,
            engine=PandasEngine(),
        )
        pql.write_table(
            df,
            "test_demo_ml.predictions.test_set",
            source_table_fqn="test_demo_ml.gold.test_set",
            source_model_uri=model_uri,
        )

    with factory() as session:
        edges = (
            session.query(LineageRowEdge)
            .filter(LineageRowEdge.target_table == "test_demo_ml.predictions.test_set")
            .all()
        )
    assert len(edges) == 3
    assert {e.source_model_uri for e in edges} == {model_uri}


# ---------- Axis 2 — value-changes ----------


def test_remerge_with_track_value_changes_emits_value_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    auth_cookies: dict[str, str],
) -> None:
    """``pql.merge(track_value_changes=True)`` after write_table → CDF row.

    Mirrors the in-step re-merge in ``_step_silver``: the first
    ``write_table`` bootstraps CDF, the second ``merge`` flips one
    cell and the helper records exactly one ``lineage_value_changes``
    row for it.
    """
    factory = app.state.session_factory
    _bind_get_session_factory(monkeypatch, factory)

    run_id = "phase158-value-changes"
    _seed_run(factory, run_id)

    df = _bronze_frame(3)
    storage_root = str(tmp_path / "warehouse")
    target_fqn = "test_demo_ml.silver.houses_with_changes"
    target_storage = f"{storage_root}/houses_with_changes"

    with _patched_soyuz(storage_root=storage_root, pre_existing=False):
        pql = PQL(
            client=MagicMock(),
            agent_run_id=run_id,
            engine=PandasEngine(),
        )
        pql.write_table(
            df,
            target_fqn,
            source_table_fqn="test_demo_ml.bronze.houses",
        )

    # Second pass: target now exists, soyuz returns its storage_location
    # and the merge upserts a single tweaked row.
    tweaked = df.copy()
    first_idx = tweaked.index[0]
    original = int(tweaked.at[first_idx, "size_sqft"])
    tweaked.at[first_idx, "size_sqft"] = original + 999

    with patch("pointlessql.pql._merge._get_table") as mget:
        mget.sync.return_value = TableInfo(
            storage_location=target_storage,
            name="houses_with_changes",
        )
        pql.merge(
            source=tweaked,
            target=target_fqn,
            on=["house_id"],
            strategy="upsert",
            source_table_fqn="test_demo_ml.bronze.houses",
            track_value_changes=True,
        )

    with factory() as session:
        changes = (
            session.query(LineageValueChange)
            .filter(LineageValueChange.target_table == target_fqn)
            .all()
        )
    assert len(changes) == 1
    spec = changes[0]
    assert spec.target_column == "size_sqft"
    assert spec.old_value == "1000"
    assert spec.new_value == "1999"


# ---------- 15.8.2 INFO-log diagnostic ----------


def test_pql_sql_logs_when_lineage_row_id_dropped_at_select(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    auth_cookies: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Stripping ``_lineage_row_id`` from a lineage-bearing source logs INFO.

    Pins Sprint 15.8.2's diagnostic: when the agent's SELECT references
    a table whose schema carries ``_lineage_row_id`` but the projection
    omits it, ``run_sql`` flags the op via INFO log and stamps
    ``lineage_row_id_dropped_at_select=True`` on ``params_json``.  This
    is what surfaces the seed-demo's silver bug at run-detail level.
    """
    factory = app.state.session_factory
    _bind_get_session_factory(monkeypatch, factory)

    run_id = "phase158-sql-diag"
    _seed_run(factory, run_id)

    bronze_path = tmp_path / "bronze"
    bronze_arrow = pd.DataFrame(
        {
            "house_id": [1, 2, 3],
            "size_sqft": [1000, 1100, 1200],
            "_lineage_row_id": ["bronze-1", "bronze-2", "bronze-3"],
        }
    )
    deltalake.write_deltalake(str(bronze_path), bronze_arrow)

    approved = {"phase158.bronze.houses": str(bronze_path)}

    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", run_id)
    with caplog.at_level(logging.INFO, logger="pointlessql.pql._sql"):
        result = PQL.sql(
            "SELECT house_id, size_sqft FROM phase158.bronze.houses",
            approved_tables=approved,
        )

    assert "_lineage_row_id" not in {c["name"] for c in result.columns}
    assert any(
        "PQL.sql: query projects no _lineage_row_id" in rec.getMessage() for rec in caplog.records
    )

    with factory() as session:
        op = session.query(AgentRunOperation).filter(AgentRunOperation.agent_run_id == run_id).one()
    assert '"lineage_row_id_dropped_at_select": true' in (op.params_json or "")


def test_pql_sql_does_not_log_when_lineage_row_id_projected(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    auth_cookies: dict[str, str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Projecting ``_lineage_row_id`` keeps the diagnostic silent.

    Negative pin for the Sprint 15.8.2 diagnostic — projecting the
    column passes through cleanly and never trips the warning.
    """
    factory = app.state.session_factory
    _bind_get_session_factory(monkeypatch, factory)

    run_id = "phase158-sql-quiet"
    _seed_run(factory, run_id)

    bronze_path = tmp_path / "bronze"
    bronze_arrow = pd.DataFrame(
        {
            "house_id": [1, 2, 3],
            "_lineage_row_id": ["bronze-1", "bronze-2", "bronze-3"],
        }
    )
    deltalake.write_deltalake(str(bronze_path), bronze_arrow)

    approved = {"phase158.bronze.houses": str(bronze_path)}

    monkeypatch.setenv("POINTLESSQL_AGENT_RUN_ID", run_id)
    with caplog.at_level(logging.INFO, logger="pointlessql.pql._sql"):
        PQL.sql(
            ("SELECT house_id, _lineage_row_id FROM phase158.bronze.houses"),
            approved_tables=approved,
        )

    assert not any("lineage_row_id" in rec.getMessage() for rec in caplog.records)


# ---------- 15.8.4 CDF ordering regression ----------


def test_merge_against_non_cdf_target_captures_value_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    auth_cookies: dict[str, str],
) -> None:
    """``pql.merge(track_value_changes=True)`` works on tables created without CDF.

    Pins Sprint 15.8.4 — the ordering fix that moves
    ``ensure_cdf_enabled`` ahead of ``_do_upsert``.  Pre-fix, a merge
    against a non-pql-created Delta target would record its commit
    WITHOUT CDF (because the post-merge ALTER fired too late), and
    ``load_cdf`` would return nothing for the just-committed merge.
    """
    factory = app.state.session_factory
    _bind_get_session_factory(monkeypatch, factory)

    run_id = "phase158-cdf-ordering"
    _seed_run(factory, run_id)

    from pointlessql.services.lineage_edges import synth_target_row_id

    target_loc = tmp_path / "silver_no_cdf"
    target_fqn = "test_demo_ml.silver.no_cdf_target"
    # Bootstrap WITHOUT CDF — simulates a target created outside
    # pql.  Stamp the rows with the synth IDs that ``_prepare_lineage``
    # will derive on merge so the CDF preimage/postimage events pair
    # by the same ``_lineage_row_id`` on both sides.
    source_ids = ["bronze-1", "bronze-2", "bronze-3"]
    target_synth_ids = [synth_target_row_id(s, target_fqn) for s in source_ids]
    initial = pd.DataFrame(
        {
            "house_id": [1, 2, 3],
            "size_sqft": [1000, 1100, 1200],
            "_lineage_row_id": target_synth_ids,
        }
    )
    deltalake.write_deltalake(str(target_loc), initial)

    # Source side carries the bronze-source IDs; merge will translate
    # them via ``_prepare_lineage`` into the same synth IDs on disk.
    tweaked = pd.DataFrame(
        {
            "house_id": [1, 2, 3],
            "size_sqft": [1000, 1100, 1200],
            "_lineage_row_id": source_ids,
        }
    )
    first_idx = tweaked.index[0]
    original = int(tweaked.at[first_idx, "size_sqft"])
    tweaked.at[first_idx, "size_sqft"] = original + 555

    with patch("pointlessql.pql._merge._get_table") as mget:
        mget.sync.return_value = TableInfo(
            storage_location=str(target_loc),
            name="no_cdf_target",
        )
        pql = PQL(
            client=MagicMock(),
            agent_run_id=run_id,
            engine=PandasEngine(),
        )
        pql.merge(
            source=tweaked,
            target=target_fqn,
            on=["house_id"],
            strategy="upsert",
            source_table_fqn="test_demo_ml.bronze.houses",
            track_value_changes=True,
        )

    with factory() as session:
        changes = (
            session.query(LineageValueChange)
            .filter(LineageValueChange.target_table == target_fqn)
            .all()
        )
    assert len(changes) == 1
    assert changes[0].target_column == "size_sqft"
    assert changes[0].old_value == "1000"
    assert changes[0].new_value == "1555"
