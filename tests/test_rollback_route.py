"""POST ``/api/runs/{id}/rollback`` route + CloudEvent (Sprint 16.3).

End-to-end through the FastAPI app.  A real Delta table on
``tmp_path`` carries the data; a stub on ``_resolve_target_location``
maps the UC FQN to that path.  The conftest's ``_auth_db`` autouse
fixture wires up the admin cookie + session factory.

Coverage:

* admin gating (non-admin → 403)
* body validation (missing / non-string ``target`` → 422)
* refusal mappings: ``RollbackTargetNotFound`` → 404,
  ``RollbackInvalid`` → 422, ``RollbackStale`` → 422
* happy path: spawns a fresh agent_runs row, records the rollback
  op, returns ``new_run_id`` / ``new_op_id`` / version delta,
  emits a ``pointlessql.rollback.executed`` CloudEvent
"""

from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any

import deltalake
import httpx
import pyarrow as pa
import pytest
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from pointlessql.api.main import app
from pointlessql.models import AgentRun, AgentRunEvent, AgentRunOperation
from pointlessql.pql import _rollback as rollback_module
from pointlessql.pql._cdf import cdf_creation_config


@pytest.fixture(autouse=True)
def _patch_target_location(
    monkeypatch: pytest.MonkeyPatch,
    silver_path: Path,
) -> None:
    """Stub soyuz so rollback resolves ``main.silver.orders`` to ``silver_path``."""

    def fake_resolve(_client: Any, _full_name: str, _msg: str) -> str:
        return str(silver_path)

    monkeypatch.setattr(rollback_module, "_resolve_target_location", fake_resolve)


@pytest.fixture(autouse=True)
def _patch_get_session_factory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Wire the app's session factory into ``pointlessql.db.get_session_factory``.

    The conftest sets ``app.state.session_factory`` but does NOT call
    ``init_db``, so ``rollback_table``'s ``get_session_factory()``
    would otherwise raise.
    """
    factory = getattr(app.state, "session_factory", None)
    assert factory is not None
    monkeypatch.setattr("pointlessql.db.get_session_factory", lambda: factory)


@pytest.fixture
def silver_path(tmp_path: Path) -> Path:
    return tmp_path / "silver"


@pytest.fixture
def factory() -> sessionmaker:  # type: ignore[type-arg]
    factory = getattr(app.state, "session_factory", None)
    assert factory is not None
    return factory


def _bootstrap_silver(target: Path) -> int:
    """Create v0 with three rows and CDF on; return the version (0)."""
    rows = pa.table(
        {
            "order_id": ["A", "B", "C"],
            "qty": [1, 2, 3],
            "unit_price": [2.5, 3.0, 4.5],
        }
    )
    deltalake.write_deltalake(str(target), rows, configuration=cdf_creation_config())
    return int(deltalake.DeltaTable(str(target)).version())


def _append_to_silver(target: Path, *, order_id: str, unit_price: float) -> int:
    rows = pa.table({"order_id": [order_id], "qty": [1], "unit_price": [unit_price]})
    deltalake.write_deltalake(str(target), rows, mode="append")
    return int(deltalake.DeltaTable(str(target)).version())


def _seed_run_op(
    factory: sessionmaker,  # type: ignore[type-arg]
    *,
    target: str,
    delta_version_before: int | None,
    delta_version_after: int | None,
    op_name: str = "merge",
    notebook: str = "rollback_route.py",
) -> tuple[str, int]:
    run_id = str(uuid.uuid4())
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            AgentRun(
                id=run_id,
                principal="test",
                agent_id="phase-16-test",
                notebook_path=notebook,
                status="running",
                started_at=now,
            )
        )
        session.flush()
        op = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=1,
            op_name=op_name,
            params_json=json.dumps({"target": target}),
            target_table=target,
            delta_version_before=delta_version_before,
            delta_version_after=delta_version_after,
            started_at=now,
            finished_at=now,
        )
        session.add(op)
        session.commit()
        session.refresh(op)
        return run_id, op.id


@pytest.mark.asyncio
async def test_admin_required(
    silver_path: Path,
    factory: sessionmaker,  # type: ignore[type-arg]
    non_admin_cookies: dict[str, str],
) -> None:
    _bootstrap_silver(silver_path)
    run_id, _op = _seed_run_op(
        factory,
        target="main.silver.orders",
        delta_version_before=0,
        delta_version_after=0,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            f"/api/runs/{run_id}/rollback",
            json={"target": "main.silver.orders"},
            cookies=non_admin_cookies,
        )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_missing_target_returns_422(auth_cookies: dict[str, str]) -> None:
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            f"/api/runs/{uuid.uuid4()}/rollback",
            json={},
            cookies=auth_cookies,
        )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_target_not_found_returns_404(
    silver_path: Path,
    auth_cookies: dict[str, str],
) -> None:
    _bootstrap_silver(silver_path)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            f"/api/runs/{uuid.uuid4()}/rollback",
            json={"target": "main.silver.orders"},
            cookies=auth_cookies,
        )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_creation_op_returns_422(
    silver_path: Path,
    factory: sessionmaker,  # type: ignore[type-arg]
    auth_cookies: dict[str, str],
) -> None:
    _bootstrap_silver(silver_path)
    run_id, _op = _seed_run_op(
        factory,
        target="main.silver.orders",
        op_name="write_table",
        delta_version_before=None,
        delta_version_after=0,
    )
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            f"/api/runs/{run_id}/rollback",
            json={"target": "main.silver.orders"},
            cookies=auth_cookies,
        )
    assert resp.status_code == 422
    assert "drop" in resp.text.lower()


@pytest.mark.asyncio
async def test_stale_returns_422(
    silver_path: Path,
    factory: sessionmaker,  # type: ignore[type-arg]
    auth_cookies: dict[str, str],
) -> None:
    v0 = _bootstrap_silver(silver_path)
    v1 = _append_to_silver(silver_path, order_id="D", unit_price=5.0)
    run_id, _op = _seed_run_op(
        factory,
        target="main.silver.orders",
        delta_version_before=v0,
        delta_version_after=v1,
    )
    # Move past the targeted op via a second unrelated append.
    _append_to_silver(silver_path, order_id="E", unit_price=6.0)

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            f"/api/runs/{run_id}/rollback",
            json={"target": "main.silver.orders"},
            cookies=auth_cookies,
        )
    assert resp.status_code == 422
    assert "stale" in resp.text.lower()


@pytest.mark.asyncio
async def test_happy_path_spawns_rollback_run_and_emits_event(
    silver_path: Path,
    factory: sessionmaker,  # type: ignore[type-arg]
    auth_cookies: dict[str, str],
) -> None:
    v0 = _bootstrap_silver(silver_path)
    v1 = _append_to_silver(silver_path, order_id="D", unit_price=5.0)
    run_id, op_id = _seed_run_op(
        factory,
        target="main.silver.orders",
        delta_version_before=v0,
        delta_version_after=v1,
    )

    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t") as c:
        resp = await c.post(
            f"/api/runs/{run_id}/rollback",
            json={"target": "main.silver.orders"},
            cookies=auth_cookies,
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rolled_back_run_id"] == run_id
    assert body["target"] == "main.silver.orders"
    assert body["target_version_restored"] == v0
    assert body["version_before"] == v1
    assert body["version_after"] == v1 + 1
    assert body["new_op_id"] is not None

    # Spawned rollback run is succeeded and carries one rollback op.
    with factory() as session:
        rb_run = session.scalar(select(AgentRun).where(AgentRun.id == body["new_run_id"]))
        assert rb_run is not None
        assert rb_run.status == "succeeded"
        rb_op = session.scalar(
            select(AgentRunOperation).where(AgentRunOperation.agent_run_id == body["new_run_id"])
        )
        assert rb_op is not None
        assert rb_op.op_name == "rollback"
        assert rb_op.target_table == "main.silver.orders"
        params = json.loads(rb_op.params_json)
        assert params["rolled_back_run"] == run_id
        assert params["rolled_back_op_id"] == op_id

    # CloudEvent persisted.
    with factory() as session:
        events = list(
            session.scalars(
                select(AgentRunEvent).where(
                    AgentRunEvent.event_type == "pointlessql.rollback.executed"
                )
            )
        )
    assert len(events) == 1
    envelope = json.loads(events[0].payload_json)
    assert envelope["data"]["rolled_back_run_id"] == run_id
    assert envelope["data"]["target_table"] == "main.silver.orders"
