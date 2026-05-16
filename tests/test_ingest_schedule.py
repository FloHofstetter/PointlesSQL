"""Phase 82.3 — cron schedule control round-trip."""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import IngestSource, Job


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        for src in session.query(IngestSource).all():
            session.delete(src)
        for jb in session.query(Job).filter(Job.kind == "ingest_pull").all():
            session.delete(jb)
        session.commit()


@pytest.fixture(autouse=True)
def _clean() -> None:
    _wipe()
    yield
    _wipe()


def _seed_source(name: str = "sched-test") -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        src = IngestSource(
            workspace_id=1,
            owner_user_id=1,
            name=name,
            kind="sqlite",
            config=json.dumps({"path": "/tmp/x.db"}),
            secrets="{}",
            table_mappings="[]",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(src)
        session.commit()
        return int(src.id)


@pytest.mark.asyncio
async def test_set_cron_creates_job(admin_client: httpx.AsyncClient) -> None:
    """PUT with a valid cron creates a Job row + links it to the source."""
    source_id = _seed_source()
    res = await admin_client.put(
        f"/api/ingest/sources/{source_id}/schedule",
        json={"cron_expr": "0 2 * * *"},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["cron_expr"] == "0 2 * * *"
    assert body["job_id"] is not None

    factory = app.state.session_factory
    with factory() as session:
        src = session.get(IngestSource, source_id)
        assert src is not None
        assert src.job_id == body["job_id"]
        job = session.get(Job, body["job_id"])
        assert job is not None
        assert job.kind == "ingest_pull"
        assert job.cron_expr == "0 2 * * *"


@pytest.mark.asyncio
async def test_set_cron_updates_existing_job(
    admin_client: httpx.AsyncClient,
) -> None:
    """Second PUT with a new cron updates the same Job row."""
    source_id = _seed_source()
    res = await admin_client.put(
        f"/api/ingest/sources/{source_id}/schedule",
        json={"cron_expr": "@hourly"},
    )
    original_job_id = res.json()["job_id"]
    res = await admin_client.put(
        f"/api/ingest/sources/{source_id}/schedule",
        json={"cron_expr": "0 2 * * *"},
    )
    assert res.json()["job_id"] == original_job_id


@pytest.mark.asyncio
async def test_clear_cron_deletes_job(
    admin_client: httpx.AsyncClient,
) -> None:
    """PUT with null cron deletes the Job + clears job_id on source."""
    source_id = _seed_source()
    res = await admin_client.put(
        f"/api/ingest/sources/{source_id}/schedule",
        json={"cron_expr": "@hourly"},
    )
    job_id = res.json()["job_id"]
    clr = await admin_client.put(
        f"/api/ingest/sources/{source_id}/schedule",
        json={"cron_expr": None},
    )
    assert clr.status_code == 200
    assert clr.json()["cron_expr"] is None
    factory = app.state.session_factory
    with factory() as session:
        src = session.get(IngestSource, source_id)
        assert src is not None
        assert src.job_id is None
        assert session.get(Job, job_id) is None


@pytest.mark.asyncio
async def test_invalid_cron_rejected(
    admin_client: httpx.AsyncClient,
) -> None:
    """Garbage cron expression returns HTTP 400."""
    source_id = _seed_source()
    res = await admin_client.put(
        f"/api/ingest/sources/{source_id}/schedule",
        json={"cron_expr": "this is not cron"},
    )
    assert res.status_code == 400
