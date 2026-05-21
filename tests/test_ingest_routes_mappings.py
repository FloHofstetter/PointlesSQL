"""Phase 82.2 — mappings POST validation + persistence."""

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


def _seed_source() -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        src = IngestSource(
            workspace_id=1,
            owner_user_id=1,
            name="mappings-test",
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
async def test_full_mode_mapping_persists(
    admin_client: httpx.AsyncClient,
) -> None:
    """Valid full-refresh mapping is stored verbatim."""
    source_id = _seed_source()
    res = await admin_client.post(
        f"/api/ingest/sources/{source_id}/mappings",
        json={
            "mappings": [
                {
                    "source_table": "users",
                    "target_fqn": "main.ingest.users",
                    "mode": "full",
                }
            ]
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["mappings"][0]["target_fqn"] == "main.ingest.users"


@pytest.mark.asyncio
async def test_incremental_requires_high_water_col(
    admin_client: httpx.AsyncClient,
) -> None:
    """Incremental mode without high_water_col is rejected (422)."""
    source_id = _seed_source()
    res = await admin_client.post(
        f"/api/ingest/sources/{source_id}/mappings",
        json={
            "mappings": [
                {
                    "source_table": "users",
                    "target_fqn": "main.ingest.users",
                    "mode": "incremental",
                }
            ]
        },
    )
    assert res.status_code == 422
    assert "high_water_col" in res.json()["detail"]


@pytest.mark.asyncio
async def test_invalid_target_fqn_rejected(
    admin_client: httpx.AsyncClient,
) -> None:
    """Two-part target_fqn is rejected (must be 3 parts)."""
    source_id = _seed_source()
    res = await admin_client.post(
        f"/api/ingest/sources/{source_id}/mappings",
        json={
            "mappings": [
                {
                    "source_table": "users",
                    "target_fqn": "ingest.users",
                    "mode": "full",
                }
            ]
        },
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_post_replaces_existing(
    admin_client: httpx.AsyncClient,
) -> None:
    """Second POST replaces (not appends to) the first."""
    source_id = _seed_source()
    await admin_client.post(
        f"/api/ingest/sources/{source_id}/mappings",
        json={
            "mappings": [
                {
                    "source_table": "first",
                    "target_fqn": "main.ingest.first",
                    "mode": "full",
                }
            ]
        },
    )
    res = await admin_client.post(
        f"/api/ingest/sources/{source_id}/mappings",
        json={
            "mappings": [
                {
                    "source_table": "second",
                    "target_fqn": "main.ingest.second",
                    "mode": "full",
                }
            ]
        },
    )
    stored = res.json()["mappings"]
    assert len(stored) == 1
    assert stored[0]["source_table"] == "second"


@pytest.mark.asyncio
async def test_mappings_404_for_missing(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown source id returns 404."""
    res = await admin_client.post(
        "/api/ingest/sources/9999999/mappings",
        json={"mappings": []},
    )
    assert res.status_code == 404
