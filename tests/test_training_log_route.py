"""Sprint 21.8 — HTTP wrapper around ``pql.training_context()``.

The route is the agent-side bridge for the post-hoc training-log
flow.  These tests verify that POST persists an
``agent_run_operations`` row with the right ``op_name``,
``training_params_json`` shape, and run-id resolution semantics.
"""

from __future__ import annotations

import datetime as _dt
import json
import uuid

import httpx

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunOperation


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


def _admin_client(*, agent_run_id: str | None = None) -> httpx.AsyncClient:
    headers: dict[str, str] = {}
    if agent_run_id is not None:
        headers["X-Agent-Run-Id"] = agent_run_id
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
        headers=headers,
    )


async def test_training_log_persists_op_with_training_params() -> None:
    """A successful POST writes a ``train_model`` row with both blocks."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    async with _admin_client(agent_run_id=run_id) as client:
        resp = await client.post(
            "/api/pql/training/log",
            json={
                "framework": "sklearn",
                "params": {"learning_rate": "0.01", "epochs": "10"},
                "metrics": {"accuracy": 0.92, "loss": 0.13},
                "mlflow_run_id": "mlf-abc-123",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["agent_run_id"] == run_id
    op_id = body["op_id"]

    parsed = json.loads(body["training_params_json"])
    assert parsed["params"]["learning_rate"] == "0.01"
    assert parsed["metrics"]["accuracy"] == 0.92

    with factory() as session:
        op = session.get(AgentRunOperation, op_id)
        assert op is not None
        assert op.op_name == "train_model"
        assert op.training_params_json is not None
        op_params = json.loads(op.params_json)
        assert op_params["framework"] == "sklearn"
        assert op_params["mlflow_run_id"] == "mlf-abc-123"


async def test_training_log_body_run_id_overrides_header() -> None:
    """A body-supplied ``agent_run_id`` wins over the header."""
    factory = app.state.session_factory
    body_run = str(uuid.uuid4())
    header_run = str(uuid.uuid4())
    _seed_run(factory, body_run)
    _seed_run(factory, header_run)

    async with _admin_client(agent_run_id=header_run) as client:
        resp = await client.post(
            "/api/pql/training/log",
            json={
                "framework": "torch",
                "params": {},
                "metrics": {},
                "agent_run_id": body_run,
            },
        )
    assert resp.status_code == 200, resp.text
    assert resp.json()["agent_run_id"] == body_run


async def test_training_log_rejects_missing_framework() -> None:
    """Missing ``framework`` raises 400."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    async with _admin_client(agent_run_id=run_id) as client:
        resp = await client.post(
            "/api/pql/training/log",
            json={"params": {}, "metrics": {}},
        )
    assert resp.status_code in (400, 422)


async def test_training_log_rejects_non_dict_params() -> None:
    """``params`` and ``metrics`` must be objects."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    async with _admin_client(agent_run_id=run_id) as client:
        resp = await client.post(
            "/api/pql/training/log",
            json={"framework": "sklearn", "params": [1, 2, 3], "metrics": {}},
        )
    assert resp.status_code in (400, 422)


async def test_training_log_without_run_id_is_400() -> None:
    """No header + no body run-id → validation failure."""
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/training/log",
            json={"framework": "sklearn", "params": {}, "metrics": {}},
        )
    assert resp.status_code in (400, 422)


async def test_training_log_accepts_iso_timestamps() -> None:
    """``started_at`` / ``finished_at`` parse as ISO-8601."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    async with _admin_client(agent_run_id=run_id) as client:
        resp = await client.post(
            "/api/pql/training/log",
            json={
                "framework": "sklearn",
                "params": {},
                "metrics": {},
                "started_at": "2026-04-30T10:00:00Z",
                "finished_at": "2026-04-30T10:05:00Z",
            },
        )
    assert resp.status_code == 200, resp.text


async def test_training_log_unknown_op_name_is_400() -> None:
    """``op_name`` not in VALID_OP_NAMES is rejected."""
    factory = app.state.session_factory
    run_id = str(uuid.uuid4())
    _seed_run(factory, run_id)

    async with _admin_client(agent_run_id=run_id) as client:
        resp = await client.post(
            "/api/pql/training/log",
            json={
                "framework": "sklearn",
                "params": {},
                "metrics": {},
                "op_name": "bogus_op",
            },
        )
    assert resp.status_code in (400, 422)
