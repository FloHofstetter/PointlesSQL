"""CRUD round-trip + secret redaction.

Verifies that ``/api/ingest/sources`` POST → GET → PATCH → DELETE
honours workspace scoping and never leaks secrets on the GET path.
The PATCH "***" no-op rule is the load-bearing piece: callers can
GET, mutate one field, and PATCH the round-tripped body without
clobbering the stored credentials.
"""

from __future__ import annotations

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
    """Each test starts with an empty ingest_sources table."""
    _wipe_sources()
    yield
    _wipe_sources()


@pytest.mark.asyncio
async def test_create_round_trip_and_secret_redaction(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST → GET round-trip; secrets come back redacted."""
    res = await admin_client.post(
        "/api/ingest/sources",
        json={
            "name": "pg-prod",
            "kind": "postgres",
            "config": {
                "host": "db.internal",
                "port": 5432,
                "db": "orders",
                "user": "alice",
            },
            "secrets": {"password": "secret-value"},
        },
    )
    assert res.status_code == 200, res.text
    source = res.json()["source"]
    source_id = source["id"]
    assert source["name"] == "pg-prod"
    assert source["secrets"] == {"password": "***"}

    res = await admin_client.get(f"/api/ingest/sources/{source_id}")
    assert res.status_code == 200
    source = res.json()["source"]
    assert source["config"]["host"] == "db.internal"
    assert source["secrets"] == {"password": "***"}


@pytest.mark.asyncio
async def test_patch_keeps_redacted_secret_unchanged(
    admin_client: httpx.AsyncClient,
) -> None:
    """PATCH with ``"***"`` for a secret keeps the stored value."""
    res = await admin_client.post(
        "/api/ingest/sources",
        json={
            "name": "pg-prod-2",
            "kind": "postgres",
            "config": {"host": "db", "db": "d", "user": "u"},
            "secrets": {"password": "original"},
        },
    )
    source_id = res.json()["source"]["id"]

    # Caller echoes the redacted payload back; the original password
    # must remain in the DB.
    patch = await admin_client.patch(
        f"/api/ingest/sources/{source_id}",
        json={"secrets": {"password": "***"}, "name": "pg-prod-renamed"},
    )
    assert patch.status_code == 200, patch.text
    assert patch.json()["source"]["name"] == "pg-prod-renamed"

    # Sneak in via the ORM to confirm the secret survived.
    factory = app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        assert row is not None
        assert '"original"' in (row.secrets or "")


@pytest.mark.asyncio
async def test_patch_with_new_secret_overwrites(
    admin_client: httpx.AsyncClient,
) -> None:
    """PATCH with a real string for a secret overwrites the stored value."""
    res = await admin_client.post(
        "/api/ingest/sources",
        json={
            "name": "pg-prod-3",
            "kind": "postgres",
            "config": {"host": "db", "db": "d", "user": "u"},
            "secrets": {"password": "old"},
        },
    )
    source_id = res.json()["source"]["id"]
    await admin_client.patch(
        f"/api/ingest/sources/{source_id}",
        json={"secrets": {"password": "new"}},
    )
    factory = app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        assert row is not None
        assert '"new"' in (row.secrets or "")
        assert '"old"' not in (row.secrets or "")


@pytest.mark.asyncio
async def test_duplicate_name_returns_409(
    admin_client: httpx.AsyncClient,
) -> None:
    """Two sources with the same name in one workspace yield HTTP 409."""
    body = {
        "name": "duplicate",
        "kind": "sqlite",
        "config": {"path": "/tmp/x.db"},
        "secrets": {},
    }
    res = await admin_client.post("/api/ingest/sources", json=body)
    assert res.status_code == 200, res.text
    dup = await admin_client.post("/api/ingest/sources", json=body)
    assert dup.status_code == 409


@pytest.mark.asyncio
async def test_unknown_kind_returns_400(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown connector kind is rejected before persistence.

    Returns RFC-9457 422 (ValidationError) post-Phase-82 cleanup.
    """
    res = await admin_client.post(
        "/api/ingest/sources",
        json={"name": "weird", "kind": "snowflake", "config": {}, "secrets": {}},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_anonymous_cannot_list_sources(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Without a session cookie the route 401s."""
    res = await anonymous_client.get("/api/ingest/sources")
    # Auth middleware redirects HTML and 401s API; either is fine,
    # but never a 200.
    assert res.status_code in (401, 303, 307)


@pytest.mark.asyncio
async def test_delete_soft_deletes_via_is_active(
    admin_client: httpx.AsyncClient,
) -> None:
    """DELETE flips ``is_active`` to False; row remains for history."""
    res = await admin_client.post(
        "/api/ingest/sources",
        json={
            "name": "to-delete",
            "kind": "sqlite",
            "config": {"path": "/tmp/x.db"},
            "secrets": {},
        },
    )
    source_id = res.json()["source"]["id"]
    delete = await admin_client.delete(f"/api/ingest/sources/{source_id}")
    assert delete.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        assert row is not None
        assert row.is_active is False
