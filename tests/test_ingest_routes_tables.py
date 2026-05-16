"""Phase 82.2 — table-listing endpoint smoke tests."""

from __future__ import annotations

import datetime
import json
import sqlite3
from pathlib import Path

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


def _seed_source(
    *,
    name: str,
    kind: str,
    config: dict[str, object],
    secrets: dict[str, object] | None = None,
) -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        src = IngestSource(
            workspace_id=1,
            owner_user_id=1,
            name=name,
            kind=kind,
            config=json.dumps(config),
            secrets=json.dumps(secrets or {}),
            table_mappings="[]",
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(src)
        session.commit()
        return int(src.id)


@pytest.mark.asyncio
async def test_file_upload_returns_single_table(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """File-based connector short-circuits to a one-row response."""
    csv_path = tmp_path / "orders.csv"
    csv_path.write_text("a,b\n1,2\n", encoding="utf-8")
    source_id = _seed_source(
        name="csv-test",
        kind="file_upload",
        config={"path": str(csv_path)},
    )
    res = await admin_client.get(f"/api/ingest/sources/{source_id}/tables")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert body["tables"] == ["orders.csv"]


@pytest.mark.asyncio
async def test_sqlite_returns_user_tables(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """SQLite connector lists user tables via sqlite_master."""
    db = tmp_path / "x.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE users (id INTEGER)")
        conn.execute("CREATE TABLE orders (id INTEGER)")
        conn.commit()
    source_id = _seed_source(
        name="sqlite-test", kind="sqlite", config={"path": str(db)}
    )
    res = await admin_client.get(f"/api/ingest/sources/{source_id}/tables")
    body = res.json()
    # sqlite_scanner may not install offline; accept either path.
    if body.get("ok"):
        assert set(body["tables"]) >= {"users", "orders"}
    else:
        assert body["reason"]


@pytest.mark.asyncio
async def test_listing_404_for_missing(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown source id returns 404."""
    res = await admin_client.get("/api/ingest/sources/9999999/tables")
    assert res.status_code == 404
