"""admin health monitor smoke tests."""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import IngestSource


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        for src in session.query(IngestSource).all():
            session.delete(src)
        session.commit()


@pytest.fixture(autouse=True)
def _clean() -> None:
    _wipe()
    yield
    _wipe()


def _seed_with_stats(name: str, *, ok: bool) -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    mapping = {
        "source_table": "t",
        "target_fqn": "main.ingest.t",
        "mode": "full",
        "last_pull_stats": {
            "ok": ok,
            "rows_written": 10 if ok else 0,
            "duration_ms": 100,
            "target_fqn": "main.ingest.t",
            "job_run_id": 0,
            "ts": now.isoformat(),
        },
    }
    with factory() as session:
        src = IngestSource(
            workspace_id=1,
            owner_user_id=1,
            name=name,
            kind="sqlite",
            config=json.dumps({"path": "/tmp/x.db"}),
            secrets="{}",
            table_mappings=json.dumps([mapping]),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(src)
        session.commit()
        return int(src.id)


@pytest.mark.asyncio
async def test_admin_list_aggregates_health(
    admin_client: httpx.AsyncClient,
) -> None:
    """Admin list rolls up last_pull_ok per source."""
    _seed_with_stats("good", ok=True)
    _seed_with_stats("bad", ok=False)
    res = await admin_client.get("/api/admin/ingest-sources")
    assert res.status_code == 200, res.text
    sources = res.json()["sources"]
    names = {s["name"]: s for s in sources}
    assert names["good"]["last_pull_ok"] is True
    assert names["bad"]["last_pull_ok"] is False


@pytest.mark.asyncio
async def test_admin_list_rejects_non_admin(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Non-admin caller gets 403."""
    res = await non_admin_client.get("/api/admin/ingest-sources")
    assert res.status_code in (401, 403)


@pytest.mark.asyncio
async def test_admin_source_health_drilldown(
    admin_client: httpx.AsyncClient,
) -> None:
    """Per-source drilldown returns source + run lists."""
    source_id = _seed_with_stats("drill", ok=True)
    res = await admin_client.get(f"/api/admin/ingest-sources/{source_id}/health")
    assert res.status_code == 200
    body = res.json()
    assert body["source"]["id"] == source_id
    assert body["runs"] == []  # no JobRun rows since no schedule
    assert body["per_day"] == []


@pytest.mark.asyncio
async def test_admin_sources_page_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """/admin/sources HTML page renders."""
    res = await admin_client.get("/admin/sources")
    assert res.status_code == 200
    assert "Ingest sources" in res.text
