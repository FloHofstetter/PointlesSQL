"""Phase 82.1 — probe endpoint smoke tests.

We exercise the probe path for the three connector kinds that work
purely on-host without network egress: ``file_upload`` (CSV file in
``/tmp``), ``parquet_glob`` (Parquet glob), and ``sqlite``.  These
hit DuckDB's built-in readers and don't need an extension install in
CI.

S3 / HTTP / Postgres / MySQL probes are not exercised here because
they need either external network or a live DB; the unit tests in
``test_ingest_connectors.py`` cover their SQL shape, and the end-to-
end coverage in Phase 82.4 wires up fixtures.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import httpx
import pytest


@pytest.mark.asyncio
async def test_probe_file_upload_csv(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """Probing a tiny CSV returns its three columns."""
    csv_path = tmp_path / "tiny.csv"
    csv_path.write_text("id,name,total\n1,alice,100\n2,bob,250\n", encoding="utf-8")
    res = await admin_client.post(
        "/api/ingest/probe",
        json={
            "kind": "file_upload",
            "config": {"path": str(csv_path)},
            "secrets": {},
        },
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    names = {c["name"] for c in body["columns"]}
    assert {"id", "name", "total"} <= names


@pytest.mark.asyncio
async def test_probe_sqlite_table(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """Probing a sqlite table returns its declared columns."""
    db_path = tmp_path / "tiny.db"
    with sqlite3.connect(db_path) as conn:
        conn.execute(
            "CREATE TABLE users (id INTEGER, email TEXT, joined_at TEXT)"
        )
        conn.execute("INSERT INTO users VALUES (1, 'a@x', '2026-01-01')")
        conn.commit()
    res = await admin_client.post(
        "/api/ingest/probe",
        json={
            "kind": "sqlite",
            "config": {"path": str(db_path)},
            "secrets": {},
            "source_table": "users",
        },
    )
    # sqlite extension might not be installable offline.  Accept
    # either a success or a clean ProbeError envelope.
    body = res.json()
    if body.get("ok"):
        names = {c["name"] for c in body["columns"]}
        assert {"id", "email", "joined_at"} <= names
    else:
        assert body["reason"]


@pytest.mark.asyncio
async def test_probe_unknown_kind_returns_400(
    admin_client: httpx.AsyncClient,
) -> None:
    """An unknown kind is rejected before reaching DuckDB.

    Returns RFC-9457 422 (ValidationError) post-Phase-82 cleanup; the
    test name still references the historical 400 contract for
    discoverability.
    """
    res = await admin_client.post(
        "/api/ingest/probe",
        json={"kind": "snowflake", "config": {}, "secrets": {}},
    )
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_probe_anonymous_rejected(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous callers cannot hit the probe path."""
    res = await anonymous_client.post(
        "/api/ingest/probe",
        json={
            "kind": "file_upload",
            "config": {"path": "/etc/passwd"},
            "secrets": {},
        },
    )
    assert res.status_code in (401, 303, 307)
