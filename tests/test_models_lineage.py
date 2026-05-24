"""model-lineage DAG endpoint + aggregator tests."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation, LineageRowEdge
from pointlessql.services.lineage.models_lineage import (
    aggregate_source_tables_for_runs,
    aggregate_table_ml_relations,
    build_model_lineage_graph,
)


def _seed_run_with_edges(factory, run_id: str, source_tables: list[str]) -> None:
    """Insert an AgentRun + a LineageRowEdge per source table."""
    import datetime as _dt

    now = _dt.datetime.now(_dt.UTC)
    with factory() as session:
        run = AgentRun(
            id=run_id,
            principal="alice",
            notebook_path=f"/tmp/{run_id}.py",
            status="completed",
            started_at=now,
        )
        session.add(run)
        session.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name="merge",
            params_json="{}",
            target_table="cat1.sch1.smoke_model",
            started_at=now,
            finished_at=now,
        )
        session.add(op)
        session.flush()
        for src in source_tables:
            session.add(
                LineageRowEdge(
                    run_id=run_id,
                    op_id=op.id,
                    source_table=src,
                    source_row_id="r-1",
                    target_table="cat1.sch1.smoke_model",
                    target_row_id="r-1",
                    created_at=now,
                )
            )
        session.commit()


def test_aggregate_source_tables_dedupes_across_runs(auth_cookies) -> None:
    factory = app.state.session_factory
    run_a = str(uuid.uuid4())
    run_b = str(uuid.uuid4())
    _seed_run_with_edges(factory, run_a, ["cat1.sch1.users", "cat1.sch1.events"])
    _seed_run_with_edges(factory, run_b, ["cat1.sch1.events", "cat1.sch1.products"])

    sources = aggregate_source_tables_for_runs(factory, [run_a, run_b])
    assert sources == ["cat1.sch1.events", "cat1.sch1.products", "cat1.sch1.users"]


def test_aggregate_source_tables_empty_input() -> None:
    factory = app.state.session_factory
    assert aggregate_source_tables_for_runs(factory, []) == []
    assert aggregate_source_tables_for_runs(factory, [None, ""]) == []


def test_build_model_lineage_graph_emits_model_centre_node(auth_cookies) -> None:
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run_with_edges(factory, run_id, ["cat1.sch1.users"])

    graph = build_model_lineage_graph(
        factory,
        model_full_name="cat1.sch1.smoke_model",
        agent_run_ids=[run_id],
    )
    assert graph["model_full_name"] == "cat1.sch1.smoke_model"
    # Nodes contain the model centre node (type=model) and the source-table node.
    types = {n["id"]: n["type"] for n in graph["nodes"]}
    assert types["cat1.sch1.smoke_model"] == "model"
    assert types["cat1.sch1.users"] == "table"
    # Edge points from source → model with label="trained_from".
    assert graph["edges"] == [
        {
            "id": "cat1.sch1.users__cat1.sch1.smoke_model",
            "source": "cat1.sch1.users",
            "target": "cat1.sch1.smoke_model",
            "label": "trained_from",
        }
    ]


def test_build_model_lineage_graph_no_runs_returns_only_model_node() -> None:
    factory = app.state.session_factory
    graph = build_model_lineage_graph(
        factory,
        model_full_name="cat1.sch1.smoke_model",
        agent_run_ids=[],
    )
    assert len(graph["nodes"]) == 1
    assert graph["nodes"][0]["type"] == "model"
    assert graph["edges"] == []


# ---------- API endpoint test ----------


_LINK_MARKER = json.dumps(
    {
        "_pql_link": {
            "agent_run_id": "deadbeef",
            "mlflow_run_id": "mlf-abc",
            "linked_at": "2026-04-30T00:00:00+00:00",
        }
    },
    sort_keys=True,
)


@pytest.fixture
def uc_for_lineage(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    monkeypatch.setattr(
        "pointlessql.api.dependencies.effective_principal",
        lambda request: None,
    )
    mock = AsyncMock()

    async def _list_model_versions(full_name, max_results=None, page_token=None):
        if full_name != "cat1.sch1.smoke_model":
            return []
        return [
            {"version": 1, "comment": _LINK_MARKER},
            {"version": 2, "comment": "no marker"},
        ]

    mock.list_model_versions.side_effect = _list_model_versions
    app.state.uc_client = mock
    return mock


@pytest.mark.asyncio
async def test_api_model_lineage_returns_model_node_and_source_tables(
    uc_for_lineage: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    factory = app.state.session_factory
    _seed_run_with_edges(factory, "deadbeef", ["cat1.sch1.users"])

    resp = await admin_client.get("/api/models/cat1.sch1.smoke_model/lineage")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model_full_name"] == "cat1.sch1.smoke_model"
    types = {n["id"]: n["type"] for n in body["nodes"]}
    assert types["cat1.sch1.smoke_model"] == "model"
    assert types["cat1.sch1.users"] == "table"
    assert len(body["edges"]) == 1
    assert body["edges"][0]["label"] == "trained_from"


@pytest.mark.asyncio
async def test_api_model_lineage_empty_when_no_linked_runs(
    uc_for_lineage: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    # No seeded runs → only the centre model node, zero edges.
    resp = await admin_client.get("/api/models/cat1.sch1.smoke_model/lineage")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["nodes"]) == 1
    assert body["edges"] == []


@pytest.mark.asyncio
async def test_api_model_lineage_unauthenticated(
    uc_for_lineage: AsyncMock, anonymous_client: httpx.AsyncClient
) -> None:
    resp = await anonymous_client.get("/api/models/cat1.sch1.smoke_model/lineage")
    assert resp.status_code == 401


# ---------- table-relations reverse-index ----------


def _seed_inference_edge(
    factory,
    *,
    target_table: str,
    source_model_uri: str,
    edges: int = 1,
) -> None:
    """Insert ``edges`` LineageRowEdge rows pointing at the given target."""
    import datetime as _dt

    now = _dt.datetime.now(_dt.UTC)
    with factory() as session:
        for i in range(edges):
            session.add(
                LineageRowEdge(
                    run_id=None,
                    op_id=None,
                    source_table="cat1.sch1.scoring_input",
                    source_row_id=f"src-{i}",
                    target_table=target_table,
                    target_row_id=f"tgt-{i}",
                    source_model_uri=source_model_uri,
                    created_at=now,
                )
            )
        session.commit()


def test_aggregate_table_ml_relations_groups_by_target_and_model(auth_cookies) -> None:
    factory = app.state.session_factory
    _seed_inference_edge(
        factory,
        target_table="cat1.sch1.predictions",
        source_model_uri="models:/cat1.sch1.churn/3",
        edges=2,
    )
    _seed_inference_edge(
        factory,
        target_table="cat1.sch1.predictions",
        source_model_uri="models:/cat1.sch1.churn/4",
        edges=1,
    )
    _seed_inference_edge(
        factory,
        target_table="cat2.sch9.scores",
        source_model_uri="models:/cat2.sch9.fraud/1",
        edges=5,
    )

    relations = aggregate_table_ml_relations(factory)

    assert "cat1.sch1.predictions" in relations
    pred = relations["cat1.sch1.predictions"]
    assert pred["trained_models"] == []
    assert pred["scoring_models"] == [
        {"full_name": "cat1.sch1.churn", "version": "3", "edge_count": 2},
        {"full_name": "cat1.sch1.churn", "version": "4", "edge_count": 1},
    ]
    assert relations["cat2.sch9.scores"]["scoring_models"][0]["edge_count"] == 5

    scoped = aggregate_table_ml_relations(factory, catalog="cat1", schema="sch1")
    assert set(scoped) == {"cat1.sch1.predictions"}
