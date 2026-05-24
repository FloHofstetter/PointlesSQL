"""Tests for the Phase-21.3 forced-autolog wrapper.

The wrapper composes :func:`operation_context` with
``mlflow.autolog`` + ``mlflow.start_run``: the audit row always
lands; ``training_params_json`` is populated when MLflow is
reachable, empty when it isn't.  The MLflow module is stubbed so
the tests don't require a live tracking server.
"""

from __future__ import annotations

import datetime as _dt
import json
import types
import uuid

import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation
from pointlessql.services.agent_runs import training_context as tc


def _seed_run(factory, run_id: str) -> None:
    now = _dt.datetime.now(_dt.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="alice",
                notebook_path=f"/tmp/{run_id}.py",
                status="running",
                started_at=now,
            )
        )
        session.commit()


def _stub_mlflow(monkeypatch, *, params, metrics, run_id="mlf-stub"):
    """Install a fake mlflow module on get_mlflow_module()."""
    fake = types.SimpleNamespace()
    autolog_calls: list[str] = []

    def autolog(**kwargs):
        autolog_calls.append("auto")

    fake.autolog = autolog

    class FakeRunInfo:
        def __init__(self):
            self.run_id = run_id

    class FakeRun:
        def __init__(self):
            self.info = FakeRunInfo()

    class FakeRunCM:
        def __enter__(self):
            return FakeRun()

        def __exit__(self, exc_type, exc, tb):
            return False

    fake.start_run = lambda nested=False: FakeRunCM()
    fake.active_run = lambda: None

    class FakeData:
        def __init__(self, p, m):
            self.params = p
            self.metrics = m

    class FakeFullRun:
        def __init__(self):
            self.info = FakeRunInfo()
            self.data = FakeData(params, metrics)

    class FakeClient:
        def get_run(self, rid):
            assert rid == run_id
            return FakeFullRun()

    fake.MlflowClient = FakeClient
    monkeypatch.setattr(
        "pointlessql.services.agent_runs.training_context.get_mlflow_module",
        lambda: fake,
    )
    return fake, autolog_calls


def test_training_context_persists_params_and_metrics(monkeypatch) -> None:
    """End-to-end: autolog snapshot lands in agent_run_operations."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    _, autolog_calls = _stub_mlflow(
        monkeypatch,
        params={"learning_rate": "0.01", "epochs": "10"},
        metrics={"loss": 0.123, "accuracy": 0.91},
    )

    with tc.training_context(factory, agent_run_id=run_id) as rec:
        assert rec.mlflow_run_id == "mlf-stub"

    # autolog was enabled exactly once.
    assert autolog_calls == ["auto"]

    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()
    assert op.op_name == "train_model"
    assert op.training_params_json is not None
    parsed = json.loads(op.training_params_json)
    assert parsed["params"] == {"learning_rate": "0.01", "epochs": "10"}
    assert parsed["metrics"]["loss"] == 0.123


def test_training_context_no_mlflow_yields_noop(monkeypatch) -> None:
    """Without the mlflow extra, the wrapper still records the audit row."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    monkeypatch.setattr(
        "pointlessql.services.agent_runs.training_context.get_mlflow_module",
        lambda: None,
    )

    with tc.training_context(factory, agent_run_id=run_id) as rec:
        assert rec.mlflow_run_id is None

    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()
    assert op.training_params_json is None


def test_training_context_passthrough_when_no_run_id(monkeypatch) -> None:
    """``agent_run_id=None`` is a passthrough; no audit row written."""
    factory = app.state.session_factory
    _stub_mlflow(monkeypatch, params={}, metrics={})

    before = 0
    with factory() as session:
        before = session.query(AgentRunOperation).count()

    with tc.training_context(None, agent_run_id=None) as rec:
        # rec is still yielded so callers can introspect.
        assert rec is not None

    with factory() as session:
        after = session.query(AgentRunOperation).count()
    assert after == before


def test_training_context_captures_on_exception(monkeypatch) -> None:
    """If the body raises, the wrapper still tries to capture autolog data."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    _stub_mlflow(monkeypatch, params={"x": "1"}, metrics={"loss": 9.9})

    with pytest.raises(RuntimeError):
        with tc.training_context(factory, agent_run_id=run_id):
            raise RuntimeError("training crash")

    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()
    # Audit row records the failure AND the partial autolog snapshot.
    assert op.error_message is not None
    assert "training crash" in op.error_message
    assert op.training_params_json is not None


def test_training_context_autolog_failure_falls_back_to_passthrough(
    monkeypatch,
) -> None:
    """If autolog enable raises, the wrapper degrades to no-MLflow path."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    fake = types.SimpleNamespace()

    def boom(**kwargs):
        raise RuntimeError("autolog broken")

    fake.autolog = boom
    monkeypatch.setattr(
        "pointlessql.services.agent_runs.training_context.get_mlflow_module",
        lambda: fake,
    )

    with tc.training_context(factory, agent_run_id=run_id) as rec:
        assert rec.mlflow_run_id is None  # autolog failed → no run started

    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()
    assert op.training_params_json is None


def test_training_context_get_run_failure_keeps_audit_row(monkeypatch) -> None:
    """``MlflowClient.get_run`` raising leaves training_params_json empty."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    fake = types.SimpleNamespace()
    fake.autolog = lambda **kw: None
    fake.active_run = lambda: None

    class FakeRunInfo:
        run_id = "mlf-x"

    class FakeRun:
        info = FakeRunInfo()

    class FakeRunCM:
        def __enter__(self):
            return FakeRun()

        def __exit__(self, *a):
            return False

    fake.start_run = lambda nested=False: FakeRunCM()

    class FakeClient:
        def get_run(self, rid):
            raise RuntimeError("MLflow unreachable")

    fake.MlflowClient = FakeClient
    monkeypatch.setattr(
        "pointlessql.services.agent_runs.training_context.get_mlflow_module",
        lambda: fake,
    )

    with tc.training_context(factory, agent_run_id=run_id):
        pass

    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()
    assert op.training_params_json is None


def test_training_context_pql_method_round_trip(monkeypatch) -> None:
    """``PQL.training_context()`` exposes the same wrapper through the facade."""
    from pointlessql.pql import PQL

    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    _stub_mlflow(monkeypatch, params={"depth": "5"}, metrics={"acc": 0.81})

    monkeypatch.setattr(
        "pointlessql.db.get_session_factory",
        lambda: factory,
    )

    pql = PQL.__new__(PQL)
    pql._current_run_id = run_id  # type: ignore[attr-defined]

    with pql.training_context(framework="sklearn") as rec:
        assert rec.mlflow_run_id == "mlf-stub"

    with factory() as session:
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()
    parsed = json.loads(op.training_params_json or "{}")
    assert parsed["params"] == {"depth": "5"}


# ---------- — training-source lineage edge ----------


def test_training_context_emits_lineage_edge_when_source_and_model_set(
    monkeypatch,
) -> None:
    """Pass ``source_table_fqn`` + ``model_fqn`` → one lineage_row_edges row.

    Mirrors the contract pinned by
    ``test_inference_lineage.py:test_build_model_lineage_graph_includes_predictions``
    (lines 210-217): training-source edges must have
    ``target_table = MODEL_FQN`` for the model-detail Lineage DAG to
    paint the upstream node.  Pre-grand-tour-fix this row was never
    written and the upstream half of the DAG stayed empty.
    """
    from pointlessql.models import LineageRowEdge

    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    _stub_mlflow(monkeypatch, params={"alpha": "0.1"}, metrics={"r2": 0.95})

    with tc.training_context(
        factory,
        agent_run_id=run_id,
        source_table_fqn="cat.gold.training_set",
        model_fqn="cat.models.house_price_lr",
    ) as rec:
        assert rec.mlflow_run_id == "mlf-stub"

    with factory() as session:
        edges = (
            session.query(LineageRowEdge)
            .filter(LineageRowEdge.target_table == "cat.models.house_price_lr")
            .all()
        )
        op = session.query(AgentRunOperation).filter_by(agent_run_id=run_id).one()

    assert len(edges) == 1
    assert edges[0].source_table == "cat.gold.training_set"
    # Synthetic single-pair grain for model-artefact lineage.
    assert edges[0].source_row_id == "1"
    assert edges[0].target_row_id == "1"
    # source_model_uri stays NULL — that's for inference, not training.
    assert edges[0].source_model_uri is None
    # The op row is anchored to the model FQN so the run-detail
    # Operations tab shows the right target.
    assert op.target_table == "cat.models.house_price_lr"


def test_training_context_no_edge_when_only_source_table_set(monkeypatch) -> None:
    """Without ``model_fqn``, no edge is emitted (edge needs both ends)."""
    from pointlessql.models import LineageRowEdge

    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    _stub_mlflow(monkeypatch, params={}, metrics={})

    with tc.training_context(
        factory,
        agent_run_id=run_id,
        source_table_fqn="cat.gold.training_set",
    ):
        pass

    with factory() as session:
        edges = session.query(LineageRowEdge).all()
    assert edges == []


def test_training_context_no_edge_when_no_source_table(monkeypatch) -> None:
    """Without ``source_table_fqn``, no edge is emitted (default behaviour)."""
    from pointlessql.models import LineageRowEdge

    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)
    _stub_mlflow(monkeypatch, params={}, metrics={})

    with tc.training_context(
        factory,
        agent_run_id=run_id,
        model_fqn="cat.models.house_price_lr",
    ):
        pass

    with factory() as session:
        edges = session.query(LineageRowEdge).all()
    assert edges == []
