"""HTML pages render and contain the expected affordances."""

from __future__ import annotations

import datetime
import json

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import IngestSource


def _wipe_sources() -> None:
    factory = app.state.session_factory
    with factory() as session:
        for src in session.query(IngestSource).all():
            session.delete(src)
        session.commit()


@pytest.fixture(autouse=True)
def _clean_sources() -> None:
    _wipe_sources()
    yield
    _wipe_sources()


@pytest.mark.asyncio
async def test_ingest_sources_new_page_renders_all_kinds(
    admin_client: httpx.AsyncClient,
) -> None:
    """The new-source form lists all seven connector kinds."""
    res = await admin_client.get("/ingest/sources/new")
    assert res.status_code == 200
    body = res.text
    for kind in (
        "file_upload",
        "s3",
        "http",
        "postgres",
        "mysql",
        "sqlite",
        "parquet_glob",
    ):
        assert f'id="kind-{kind}"' in body


@pytest.mark.asyncio
async def test_ingest_sources_list_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """The listing page renders the heading + connect button."""
    res = await admin_client.get("/ingest/sources")
    assert res.status_code == 200
    assert "Connect a source" in res.text


@pytest.mark.asyncio
async def test_ingest_source_detail_404_for_missing(
    admin_client: httpx.AsyncClient,
) -> None:
    """Hitting a non-existent source id returns 404."""
    res = await admin_client.get("/ingest/sources/9999999")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_ingest_source_detail_renders_for_existing(
    admin_client: httpx.AsyncClient,
) -> None:
    """The detail page renders for a source the user can see."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        src = IngestSource(
            workspace_id=1,
            owner_user_id=1,
            name="detail-test",
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
        source_id = src.id

    res = await admin_client.get(f"/ingest/sources/{source_id}")
    assert res.status_code == 200
    assert "detail-test" in res.text
    assert "sqlite" in res.text
