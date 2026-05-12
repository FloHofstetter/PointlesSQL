"""Sprint 21.7 — inference-lineage column + bidirectional model DAG tests.

Sprint 21.7 added a ``source_model_uri`` column to
``lineage_row_edges`` so the model-detail Lineage tab can paint
prediction-tables downstream of the model node, alongside the
training source-tables upstream from Sprint 21.5.5.
"""

from __future__ import annotations

import datetime as _dt
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation, LineageRowEdge
from pointlessql.services.lineage.models_lineage import (
    aggregate_prediction_tables_for_model,
    build_model_lineage_graph,
)
from pointlessql.services.lineage_edges import record_edges


def _seed_run_and_op(factory, run_id: str) -> int:
    """Insert one ``AgentRun`` + one ``AgentRunOperation`` for FK linkage."""
    now = _dt.datetime.now(_dt.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="alice",
                notebook_path=f"/tmp/{run_id}.py",
                status="completed",
                started_at=now,
            )
        )
        session.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="write_table",
            params_json="{}",
            target_table="cat.sch.preds",
            started_at=now,
            finished_at=now,
        )
        session.add(op)
        session.commit()
        session.refresh(op)
        return op.id


def _seed_inference_edges(
    factory,
    run_id: str,
    op_id: int,
    *,
    source_table: str,
    target_table: str,
    source_model_uri: str,
    n: int,
) -> None:
    """Insert *n* lineage_row_edges rows with the given model URI."""
    record_edges(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table=source_table,
        target_table=target_table,
        source_row_ids=[f"src-{i}" for i in range(n)],
        target_row_ids=[f"tgt-{i}" for i in range(n)],
        source_model_uri=source_model_uri,
    )


def test_record_edges_persists_source_model_uri(auth_cookies) -> None:
    """``record_edges`` writes ``source_model_uri`` when supplied."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    op_id = _seed_run_and_op(factory, run_id)

    failure = record_edges(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.preds",
        source_row_ids=["a", "b"],
        target_row_ids=["x", "y"],
        source_model_uri="models:/cat.sch.smoke_model/3",
    )
    assert failure is None

    with factory() as session:
        rows = session.query(LineageRowEdge).all()
    assert len(rows) == 2
    assert {row.source_model_uri for row in rows} == {"models:/cat.sch.smoke_model/3"}


def test_record_edges_default_source_model_uri_is_null(auth_cookies) -> None:
    """Without the kwarg, the column stays ``NULL``."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    op_id = _seed_run_and_op(factory, run_id)

    record_edges(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table="cat.sch.users",
        target_table="cat.sch.preds",
        source_row_ids=["a"],
        target_row_ids=["x"],
    )
    with factory() as session:
        rows = session.query(LineageRowEdge).all()
    assert rows[0].source_model_uri is None


def test_aggregate_prediction_tables_groups_by_target(auth_cookies) -> None:
    """Distinct target tables surface with their edge counts."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    op_id = _seed_run_and_op(factory, run_id)

    _seed_inference_edges(
        factory,
        run_id,
        op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.preds_a",
        source_model_uri="models:/cat.sch.smoke_model/2",
        n=4,
    )
    _seed_inference_edges(
        factory,
        run_id,
        op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.preds_b",
        source_model_uri="models:/cat.sch.smoke_model/3",
        n=2,
    )

    rows = aggregate_prediction_tables_for_model(factory, "cat.sch.smoke_model")
    by_table = {r["target_table"]: r["edge_count"] for r in rows}
    assert by_table == {"cat.sch.preds_a": 4, "cat.sch.preds_b": 2}


def test_aggregate_prediction_tables_filters_by_model(auth_cookies) -> None:
    """Edges from a different model don't leak into the result."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    op_id = _seed_run_and_op(factory, run_id)

    _seed_inference_edges(
        factory,
        run_id,
        op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.preds_a",
        source_model_uri="models:/cat.sch.other_model/1",
        n=3,
    )

    rows = aggregate_prediction_tables_for_model(factory, "cat.sch.smoke_model")
    assert rows == []


def test_aggregate_prediction_tables_empty_when_uri_null(auth_cookies) -> None:
    """Pure table-to-table edges (URI == NULL) are excluded."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    op_id = _seed_run_and_op(factory, run_id)

    record_edges(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table="cat.sch.bronze",
        target_table="cat.sch.silver",
        source_row_ids=["a"],
        target_row_ids=["x"],
    )

    rows = aggregate_prediction_tables_for_model(factory, "cat.sch.smoke_model")
    assert rows == []


def test_build_model_lineage_graph_includes_predictions(auth_cookies) -> None:
    """Bidirectional graph: model centre + source upstream + prediction downstream."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    op_id = _seed_run_and_op(factory, run_id)

    # Training edge: source → model (Sprint 21.5.5 path).
    record_edges(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.smoke_model",
        source_row_ids=["a"],
        target_row_ids=["x"],
    )
    # Inference edge: features → preds with model_uri set.
    _seed_inference_edges(
        factory,
        run_id,
        op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.preds",
        source_model_uri="models:/cat.sch.smoke_model/1",
        n=5,
    )

    graph = build_model_lineage_graph(
        factory,
        model_full_name="cat.sch.smoke_model",
        agent_run_ids=[run_id],
    )
    kinds = {n["id"]: n.get("kind") for n in graph["nodes"]}
    assert kinds["cat.sch.smoke_model"] == "model"
    assert kinds["cat.sch.features"] == "table"
    assert kinds["cat.sch.preds"] == "prediction"

    edge_labels = {(e["source"], e["target"]): e["label"] for e in graph["edges"]}
    assert edge_labels[("cat.sch.features", "cat.sch.smoke_model")] == "trained_from"
    assert edge_labels[("cat.sch.smoke_model", "cat.sch.preds")] == "inferred_to"


def test_build_model_lineage_graph_skips_self_referential_loop(auth_cookies) -> None:
    """If a prediction-table happens to equal the model FQN, it's skipped."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    op_id = _seed_run_and_op(factory, run_id)
    _seed_inference_edges(
        factory,
        run_id,
        op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.smoke_model",  # same as model
        source_model_uri="models:/cat.sch.smoke_model/1",
        n=2,
    )
    graph = build_model_lineage_graph(
        factory,
        model_full_name="cat.sch.smoke_model",
        agent_run_ids=[],
    )
    # Only the centre node; no self-loop edge.
    assert len(graph["nodes"]) == 1


# ---------- API endpoint ----------


@pytest.fixture
def uc_for_inference(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    monkeypatch.setattr(
        "pointlessql.api.dependencies.effective_principal",
        lambda request: None,
    )
    mock = AsyncMock()

    async def _list_model_versions(full_name, max_results=None, page_token=None):
        return []

    mock.list_model_versions.side_effect = _list_model_versions
    app.state.uc_client = mock
    return mock


@pytest.mark.asyncio
async def test_api_predictions_endpoint_groups_by_target(
    uc_for_inference: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    op_id = _seed_run_and_op(factory, run_id)
    _seed_inference_edges(
        factory,
        run_id,
        op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.preds",
        source_model_uri="models:/cat.sch.smoke_model/1",
        n=3,
    )
    resp = await admin_client.get("/api/models/cat.sch.smoke_model/predictions")
    assert resp.status_code == 200
    body = resp.json()
    assert body["predictions"] == [{"target_table": "cat.sch.preds", "edge_count": 3}]


@pytest.mark.asyncio
async def test_api_predictions_endpoint_unauthenticated(
    uc_for_inference: AsyncMock, anonymous_client: httpx.AsyncClient
) -> None:
    resp = await anonymous_client.get("/api/models/cat.sch.smoke_model/predictions")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_lineage_returns_bidirectional_graph(
    uc_for_inference: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    """Endpoint surfaces both ``trained_from`` and ``inferred_to`` edges."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    op_id = _seed_run_and_op(factory, run_id)

    record_edges(
        factory,
        run_id=run_id,
        op_id=op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.smoke_model",
        source_row_ids=["a"],
        target_row_ids=["x"],
    )
    _seed_inference_edges(
        factory,
        run_id,
        op_id,
        source_table="cat.sch.features",
        target_table="cat.sch.preds",
        source_model_uri="models:/cat.sch.smoke_model/1",
        n=2,
    )

    # Patch list_model_versions to return one version with a marker so the
    # upstream half kicks in.
    import json

    marker = json.dumps(
        {"_pql_link": {"agent_run_id": run_id}},
        sort_keys=True,
    )

    async def _list_with_marker(full_name, max_results=None, page_token=None):
        return [{"version": 1, "comment": marker}]

    uc_for_inference.list_model_versions.side_effect = _list_with_marker

    resp = await admin_client.get("/api/models/cat.sch.smoke_model/lineage")
    assert resp.status_code == 200
    body = resp.json()
    labels = {e["label"] for e in body["edges"]}
    assert "trained_from" in labels
    assert "inferred_to" in labels
