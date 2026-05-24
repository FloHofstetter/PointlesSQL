"""Integration tests for the ``detail=true`` diff route."""

from __future__ import annotations

import datetime as dt
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentRunOperation
from tests.conftest import ApiKeyFixture


async def _seed_run(client: httpx.AsyncClient, *, run_id: str) -> None:
    response = await client.post(
        "/api/agent-runs",
        json={
            "id": run_id,
            "notebook_path": "demo/run.py",
            "source": "print('seed')\n",
            "runtime_versions": {"python": "3.14.0"},
        },
    )
    assert response.status_code == 200, response.text


def _add_op(
    *,
    run_id: str,
    op_name: str,
    target: str,
    rows_affected: int = 0,
    params: dict[str, object] | None = None,
) -> None:
    factory = app.state.session_factory
    started = dt.datetime.now(dt.UTC) - dt.timedelta(minutes=1)
    finished = dt.datetime.now(dt.UTC)
    with factory() as session:
        from sqlalchemy import func, select

        max_ord = session.scalar(
            select(func.max(AgentRunOperation.ordinal)).where(
                AgentRunOperation.agent_run_id == run_id
            )
        )
        ordinal = (max_ord or 0) + 1
        session.add(
            AgentRunOperation(
                agent_run_id=run_id,
                ordinal=ordinal,
                op_name=op_name,
                params_json=json.dumps(params or {}),
                target_table=target,
                input_sha=None,
                rows_affected=rows_affected,
                delta_version_before=None,
                delta_version_after=ordinal,
                started_at=started,
                finished_at=finished,
                error_message=None,
            )
        )
        session.commit()


@pytest.mark.asyncio
async def test_detail_returns_operations_diff_when_flag_set(
    supervisor_secret: ApiKeyFixture, admin_client: httpx.AsyncClient
) -> None:
    transport = httpx.ASGITransport(app=app)
    run_a = "1111aaaa-1111-1111-1111-aaaaaaaa1111"
    run_b = "2222bbbb-2222-2222-2222-bbbbbbbb2222"
    await _seed_run(admin_client, run_id=run_a)
    await _seed_run(admin_client, run_id=run_b)
    _add_op(
        run_id=run_a,
        op_name="merge",
        target="main.silver.orders",
        rows_affected=10,
        params={"strategy": "upsert"},
    )
    _add_op(
        run_id=run_b,
        op_name="merge",
        target="main.silver.orders",
        rows_affected=25,
        params={"strategy": "scd2"},
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs/diff",
            params={"a": run_a, "b": run_b, "detail": "true"},
            headers={"Authorization": f"Bearer {supervisor_secret.secret}"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["align"] == "ordinal"
    ops_diff = payload["operations_diff"]
    assert len(ops_diff) == 1
    pair = ops_diff[0]
    assert pair["rows_affected_diff"] == 15
    assert pair["params_diff"]["changed"]["strategy"] == {
        "a": "upsert",
        "b": "scd2",
    }


@pytest.mark.asyncio
async def test_detail_includes_value_changes_and_column_lineage_diff(
    supervisor_secret: ApiKeyFixture, admin_client: httpx.AsyncClient
) -> None:
    """detail=true now also carries cell + column-lineage diff."""
    transport = httpx.ASGITransport(app=app)
    run_a = "1111aaab-1111-1111-1111-aaaaaaab1111"
    run_b = "2222bbbc-2222-2222-2222-bbbbbbbc2222"
    await _seed_run(admin_client, run_id=run_a)
    await _seed_run(admin_client, run_id=run_b)
    _add_op(
        run_id=run_a,
        op_name="merge",
        target="main.silver.orders",
        rows_affected=1,
    )
    _add_op(
        run_id=run_b,
        op_name="merge",
        target="main.silver.orders",
        rows_affected=1,
    )
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs/diff",
            params={"a": run_a, "b": run_b, "detail": "true"},
            headers={"Authorization": f"Bearer {supervisor_secret.secret}"},
        )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "value_changes_diff" in payload
    assert "column_lineage_diff" in payload
    assert "tables" in payload["value_changes_diff"]
    assert "edges_only_in_a" in payload["column_lineage_diff"]


@pytest.mark.asyncio
async def test_detail_omitted_when_flag_unset(
    supervisor_secret: ApiKeyFixture, admin_client: httpx.AsyncClient
) -> None:
    transport = httpx.ASGITransport(app=app)
    run_a = "3333cccc-3333-3333-3333-cccccccc3333"
    run_b = "4444dddd-4444-4444-4444-dddddddd4444"
    await _seed_run(admin_client, run_id=run_a)
    await _seed_run(admin_client, run_id=run_b)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs/diff",
            params={"a": run_a, "b": run_b},
            headers={"Authorization": f"Bearer {supervisor_secret.secret}"},
        )
    assert response.status_code == 200
    payload = response.json()
    assert "operations_diff" not in payload
    assert "tool_calls_diff" not in payload
    assert "value_changes_diff" not in payload
    assert "column_lineage_diff" not in payload


@pytest.mark.asyncio
async def test_detail_rejects_bad_align(
    supervisor_secret: ApiKeyFixture, admin_client: httpx.AsyncClient
) -> None:
    transport = httpx.ASGITransport(app=app)
    run_a = "5555eeee-5555-5555-5555-eeeeeeee5555"
    run_b = "6666ffff-6666-6666-6666-ffffffff6666"
    await _seed_run(admin_client, run_id=run_a)
    await _seed_run(admin_client, run_id=run_b)
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        response = await c.get(
            "/api/agent-runs/diff",
            params={
                "a": run_a,
                "b": run_b,
                "detail": "true",
                "align": "fuzzy",
            },
            headers={"Authorization": f"Bearer {supervisor_secret.secret}"},
        )
    assert response.status_code == 422
