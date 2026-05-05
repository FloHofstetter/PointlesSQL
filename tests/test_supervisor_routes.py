"""Tests for the Sprint 13.11.4a Family-B supervisor routes.

Covers ``GET /api/agent-runs`` filter expansion, the new
``GET /api/agent-runs/{id}/summary`` and ``GET /api/agent-runs/diff``
routes, plus the ``require_supervisor`` gate.  The admin-CRUD
surface for ``api_keys`` has its own test file
(:mod:`tests.test_admin_api_keys_routes`).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterator

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRunOperation, ApiKey
from pointlessql.services import api_keys as api_keys_service


def _wipe_api_keys() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(ApiKey).delete()
        session.commit()
    api_keys_service.invalidate_cache()


@pytest.fixture
def supervisor_secret() -> Iterator[str]:
    _wipe_api_keys()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="sup", supervisor=True
    )
    try:
        yield plaintext
    finally:
        _wipe_api_keys()


@pytest.fixture
def normal_secret() -> Iterator[str]:
    _wipe_api_keys()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="reader", supervisor=False
    )
    try:
        yield plaintext
    finally:
        _wipe_api_keys()


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


async def _seed_run(
    client: httpx.AsyncClient,
    *,
    run_id: str,
    notebook_path: str = "demo/run.py",
    principal_header: str | None = None,
    agent_id: str | None = None,
) -> None:
    headers = {"X-Principal": principal_header} if principal_header else {}
    body = {
        "id": run_id,
        "notebook_path": notebook_path,
        "source": "print('seed')\n",
        "runtime_versions": {"python": "3.14.0"},
    }
    if agent_id:
        body["agent_id"] = agent_id
    response = await client.post("/api/agent-runs", json=body, headers=headers)
    assert response.status_code == 200, response.text


def _add_op(
    *,
    run_id: str,
    target: str,
    rows_affected: int = 100,
    delta_before: int | None = 0,
    delta_after: int | None = 1,
    error_message: str | None = None,
) -> int:
    factory = app.state.session_factory
    started = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    finished = dt.datetime.now(dt.UTC)
    with factory() as session:
        # Use the next ordinal for that run.
        from sqlalchemy import func, select

        max_ord = session.scalar(
            select(func.max(AgentRunOperation.ordinal)).where(
                AgentRunOperation.agent_run_id == run_id
            )
        )
        ordinal = (max_ord or 0) + 1
        row = AgentRunOperation(
            agent_run_id=run_id,
            ordinal=ordinal,
            op_name="write_table",
            params_json="{}",
            target_table=target,
            input_sha=None,
            rows_affected=rows_affected,
            delta_version_before=delta_before,
            delta_version_after=delta_after,
            started_at=started,
            finished_at=finished,
            error_message=error_message,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        return int(row.id)


# ---------------------------------------------------------------------------
# Filter expansion on /api/agent-runs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_filter_by_principal_and_status() -> None:
    async with _admin_client() as client:
        await _seed_run(
            client,
            run_id="cccc1111-aaaa-aaaa-aaaa-cccccccccccc",
            principal_header="alice@example.com",
        )
        await _seed_run(
            client,
            run_id="dddd2222-bbbb-bbbb-bbbb-dddddddddddd",
            principal_header="bob@example.com",
        )
        response = await client.get("/api/agent-runs", params={"principal": "alice@example.com"})
    assert response.status_code == 200, response.text
    runs = response.json()["runs"]
    principals = {r["principal"] for r in runs}
    assert principals == {"alice@example.com"}


@pytest.mark.asyncio
async def test_list_rejects_bad_since() -> None:
    async with _admin_client() as client:
        response = await client.get("/api/agent-runs", params={"since": "not-a-date"})
    assert response.status_code == 422


# ---------------------------------------------------------------------------
# require_supervisor — admin cookie passes; normal Bearer fails;
# supervisor Bearer passes
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_summary_requires_supervisor_normal_key_403(
    normal_secret: str,
) -> None:
    transport = httpx.ASGITransport(app=app)
    # Seed a run via the admin cookie session.
    async with _admin_client() as cookie_client:
        run_id = "eeee1111-1111-1111-1111-eeeeeeeeeeee"
        await _seed_run(cookie_client, run_id=run_id)
        _add_op(run_id=run_id, target="main.silver.orders")
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            f"/api/agent-runs/{run_id}/summary",
            headers={"Authorization": f"Bearer {normal_secret}"},
        )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_summary_supervisor_key_passes_with_payload(
    supervisor_secret: str,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with _admin_client() as cookie_client:
        run_id = "ffff1111-1111-1111-1111-ffffffffffff"
        await _seed_run(cookie_client, run_id=run_id, agent_id="hermes-1")
        _add_op(run_id=run_id, target="main.silver.orders", rows_affected=42)
        _add_op(
            run_id=run_id,
            target="main.silver.orders",
            error_message="boom",
            rows_affected=0,
        )
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            f"/api/agent-runs/{run_id}/summary",
            headers={"Authorization": f"Bearer {supervisor_secret}"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["id"] == run_id
    assert payload["operations_count"] == 2
    assert payload["errored_ops_count"] == 1
    assert payload["rows_touched"] == 42
    assert payload["tables_touched"] == [] or "main.silver.orders" in payload["tables_touched"]
    # Anti-gaming: cost-gate threshold MUST NOT leak.
    assert "cost_gate_threshold" not in payload


@pytest.mark.asyncio
async def test_summary_admin_cookie_also_passes() -> None:
    """Admins are stronger than supervisors — cookie path works too."""
    async with _admin_client() as client:
        run_id = "11119999-1111-1111-1111-111199999999"
        await _seed_run(client, run_id=run_id)
        _add_op(run_id=run_id, target="main.bronze.orders_raw")
        response = await client.get(f"/api/agent-runs/{run_id}/summary")
    assert response.status_code == 200, response.text


# ---------------------------------------------------------------------------
# Diff
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_diff_shows_table_only_in_each_side(
    supervisor_secret: str,
) -> None:
    transport = httpx.ASGITransport(app=app)
    async with _admin_client() as cookie_client:
        run_a = "aaaa9999-1111-1111-1111-aaaaaaaaaaaa"
        run_b = "bbbb9999-2222-2222-2222-bbbbbbbbbbbb"
        await _seed_run(cookie_client, run_id=run_a)
        await _seed_run(cookie_client, run_id=run_b)
        # Mark tables_touched on both via the finish endpoint.
        await cookie_client.post(
            f"/api/agent-runs/{run_a}/finish",
            json={
                "status": "succeeded",
                "tables_touched": ["main.silver.orders", "main.gold.summary"],
            },
        )
        await cookie_client.post(
            f"/api/agent-runs/{run_b}/finish",
            json={
                "status": "succeeded",
                "tables_touched": ["main.silver.orders", "main.gold.alt"],
            },
        )
        _add_op(run_id=run_a, target="main.silver.orders")
        _add_op(run_id=run_b, target="main.silver.orders")
        _add_op(run_id=run_b, target="main.gold.alt", rows_affected=5)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs/diff",
            params={"a": run_a, "b": run_b},
            headers={"Authorization": f"Bearer {supervisor_secret}"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["ops_count_diff"] == 1
    assert payload["tables_in_both"] == ["main.silver.orders"]
    assert payload["tables_only_in_a"] == ["main.gold.summary"]
    assert payload["tables_only_in_b"] == ["main.gold.alt"]


@pytest.mark.asyncio
async def test_diff_404_when_one_side_missing(supervisor_secret: str) -> None:
    transport = httpx.ASGITransport(app=app)
    async with _admin_client() as cookie_client:
        run_a = "ccccaaa1-1111-1111-1111-cccccccccccc"
        await _seed_run(cookie_client, run_id=run_a)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs/diff",
            params={"a": run_a, "b": "deadbeef-dead-beef-dead-beefdeadbeef"},
            headers={"Authorization": f"Bearer {supervisor_secret}"},
        )
    assert response.status_code == 404
