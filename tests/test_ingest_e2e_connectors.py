"""end-to-end connector coverage.

For each connector kind that works in a sandboxed CI environment we
exercise the full create → mapping → pull cycle.  Live-network kinds
(S3 / Postgres / MySQL) are gated on env vars so the test suite stays
deterministic offline.

Per-connector tests:

* **file_upload** — covered in ``test_ingest_pulls.py``.  We add one
  CSV write-to-Delta assertion here.
* **parquet_glob** — local pandas-produced Parquet under ``tmp_path``.
* **http** — stdlib ``http.server`` thread serving a tiny CSV.
* **sqlite** — temp ``.db`` file.  Skips gracefully if DuckDB's
  ``sqlite_scanner`` extension cannot install offline.
* **s3** — requires ``MOTO_S3_AVAILABLE=1`` env override (not enabled
  by default).
* **postgres** — requires ``POINTLESSQL_TEST_LIVE_PG=1``.
* **mysql** — requires ``POINTLESSQL_TEST_LIVE_MY=1``.

The PQL.write_table side is patched to a MagicMock so the test
doesn't need a live soyuz / Delta backend; the assertion is "the
DuckDB reader read N rows" + "the write_table call carried the
right target".
"""

from __future__ import annotations

import datetime
import json
import os
import sqlite3
import threading
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

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


def _seed(
    *,
    kind: str,
    config: dict[str, Any],
    mapping: dict[str, Any],
    secrets: dict[str, Any] | None = None,
) -> int:
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        src = IngestSource(
            workspace_id=1,
            owner_user_id=1,
            name=f"e2e-{kind}-{id(config)}",
            kind=kind,
            config=json.dumps(config),
            secrets=json.dumps(secrets or {}),
            table_mappings=json.dumps([mapping]),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(src)
        session.commit()
        return int(src.id)


async def _pull_and_capture(
    admin_client: httpx.AsyncClient, source_id: int
) -> tuple[dict[str, Any], MagicMock]:
    """Run a pull with PQL.write_table mocked; return body + mock."""
    with patch("pointlessql.pql.pql.PQL") as mock_pql_cls:
        instance = MagicMock()
        instance.write_table = MagicMock(return_value=None)
        instance.merge = MagicMock(return_value={})
        mock_pql_cls.return_value = instance
        res = await admin_client.post(
            f"/api/ingest/sources/{source_id}/pulls"
        )
        return res.json(), instance


@pytest.mark.asyncio
async def test_e2e_file_upload_csv_pull(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """End-to-end CSV file_upload pull lands the rows in the target."""
    csv = tmp_path / "users.csv"
    csv.write_text("id,name\n1,a\n2,b\n3,c\n", encoding="utf-8")
    source_id = _seed(
        kind="file_upload",
        config={"path": str(csv)},
        mapping={
            "source_table": "users.csv",
            "target_fqn": "main.ingest.users",
            "mode": "full",
        },
    )
    body, pql_instance = await _pull_and_capture(admin_client, source_id)
    assert body["ok"] is True
    assert body["results"][0]["rows_written"] == 3
    pql_instance.write_table.assert_called_once()
    call_args = pql_instance.write_table.call_args
    assert call_args.args[1] == "main.ingest.users"


@pytest.mark.asyncio
async def test_e2e_parquet_glob_pull(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """Parquet glob ingests rows from a directory of parquet files."""
    pd = pytest.importorskip("pandas")
    df1 = pd.DataFrame({"id": [1, 2], "v": ["a", "b"]})
    df2 = pd.DataFrame({"id": [3, 4], "v": ["c", "d"]})
    df1.to_parquet(tmp_path / "part-1.parquet")
    df2.to_parquet(tmp_path / "part-2.parquet")
    source_id = _seed(
        kind="parquet_glob",
        config={"pattern": str(tmp_path / "*.parquet")},
        mapping={
            "source_table": "events",
            "target_fqn": "main.ingest.events",
            "mode": "full",
        },
    )
    body, pql_instance = await _pull_and_capture(admin_client, source_id)
    assert body["ok"] is True
    assert body["results"][0]["rows_written"] == 4
    pql_instance.write_table.assert_called_once()


@pytest.mark.asyncio
async def test_e2e_http_pull(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """HTTP connector pulls a CSV served by a local stdlib http.server."""
    csv = tmp_path / "tiny.csv"
    csv.write_text("k,v\n1,one\n2,two\n", encoding="utf-8")

    server = HTTPServer(
        ("127.0.0.1", 0),
        lambda *args, **kwargs: SimpleHTTPRequestHandler(  # type: ignore[misc]
            *args, directory=str(tmp_path), **kwargs
        ),
    )
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        source_id = _seed(
            kind="http",
            config={"url": f"http://127.0.0.1:{port}/tiny.csv"},
            mapping={
                "source_table": "tiny.csv",
                "target_fqn": "main.ingest.tiny",
                "mode": "full",
            },
        )
        body, pql_instance = await _pull_and_capture(admin_client, source_id)
    finally:
        server.shutdown()
        thread.join(timeout=2)

    # ``httpfs`` may fail to install offline; accept either outcome
    # but require the harness to surface a clean structured failure.
    if body["results"]:
        assert body["results"][0]["rows_written"] == 2
        pql_instance.write_table.assert_called_once()
    else:
        assert body["failures"]
        assert body["failures"][0]["reason"]


@pytest.mark.asyncio
async def test_e2e_sqlite_pull(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """Sqlite connector pulls rows from a local .db file when the ext loads."""
    db = tmp_path / "x.db"
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE customers (id INTEGER, name TEXT)")
        conn.executemany(
            "INSERT INTO customers VALUES (?, ?)",
            [(1, "alice"), (2, "bob"), (3, "carol")],
        )
        conn.commit()
    source_id = _seed(
        kind="sqlite",
        config={"path": str(db)},
        mapping={
            "source_table": "customers",
            "target_fqn": "main.ingest.customers",
            "mode": "full",
        },
    )
    body, pql_instance = await _pull_and_capture(admin_client, source_id)
    if body["results"]:
        assert body["results"][0]["rows_written"] == 3
        pql_instance.write_table.assert_called_once()
    else:
        # sqlite_scanner unavailable — verify the hint is informative.
        assert body["failures"]
        assert "DuckDB" in body["failures"][0]["reason"]


@pytest.mark.asyncio
async def test_e2e_unknown_extension_surfaces_hint(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """The PullError hint reaches the API caller on extension failure.

    We force a Postgres pull to fail by pointing at a bogus host; the
    extension install itself may succeed but the connection won't.
    Either way the failure should propagate as a structured envelope
    rather than a raw traceback.
    """
    source_id = _seed(
        kind="postgres",
        config={
            "host": "127.0.0.1",
            "port": 1,
            "db": "nope",
            "user": "u",
        },
        secrets={"password": "p"},
        mapping={
            "source_table": "public.x",
            "target_fqn": "main.ingest.x",
            "mode": "full",
        },
    )
    res = await admin_client.post(f"/api/ingest/sources/{source_id}/pulls")
    body = res.json()
    # Either the extension fails to install (offline CI) or the
    # connection fails — both must produce a clean failure envelope.
    assert body["ok"] is True  # the API call itself returns 200
    assert body["failures"]
    assert body["failures"][0]["reason"]


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("POINTLESSQL_TEST_LIVE_PG"),
    reason="set POINTLESSQL_TEST_LIVE_PG=1 to exercise a live Postgres",
)
async def test_e2e_postgres_live(
    admin_client: httpx.AsyncClient,
) -> None:  # pragma: no cover - opt-in
    """Live Postgres smoke test — wires up against $PGHOST etc."""
    host = os.environ.get("PGHOST", "127.0.0.1")
    port = int(os.environ.get("PGPORT", "5432"))
    db = os.environ.get("PGDATABASE", "postgres")
    user = os.environ.get("PGUSER", "postgres")
    password = os.environ.get("PGPASSWORD", "")
    source_id = _seed(
        kind="postgres",
        config={"host": host, "port": port, "db": db, "user": user},
        secrets={"password": password},
        mapping={
            "source_table": "pg_catalog.pg_database",
            "target_fqn": "main.ingest.pg_database",
            "mode": "full",
        },
    )
    body, _pql = await _pull_and_capture(admin_client, source_id)
    assert body["ok"] is True
    if body["failures"]:
        pytest.fail(
            f"live-postgres pull failed: {body['failures']}"
        )
    assert body["results"][0]["rows_written"] >= 1


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("MOTO_S3_AVAILABLE"),
    reason="set MOTO_S3_AVAILABLE=1 to exercise a moto-backed S3",
)
async def test_e2e_s3_moto(
    admin_client: httpx.AsyncClient,
) -> None:  # pragma: no cover - opt-in
    """S3 connector against a moto in-memory bucket."""
    moto = pytest.importorskip("moto")  # type: ignore[unused-ignore]
    import boto3  # type: ignore[import-untyped]

    with moto.mock_aws():
        s3 = boto3.client("s3", region_name="us-east-1")
        s3.create_bucket(Bucket="test-bucket")
        s3.put_object(
            Bucket="test-bucket", Key="data.csv", Body=b"a,b\n1,2\n3,4\n"
        )
        source_id = _seed(
            kind="s3",
            config={"url": "s3://test-bucket/data.csv"},
            secrets={
                "access_key": "testing",
                "secret_key": "testing",
                "region": "us-east-1",
            },
            mapping={
                "source_table": "data.csv",
                "target_fqn": "main.ingest.data",
                "mode": "full",
            },
        )
        body, _pql = await _pull_and_capture(admin_client, source_id)
    assert body["ok"] is True


@pytest.mark.asyncio
@pytest.mark.skipif(
    not os.environ.get("POINTLESSQL_TEST_LIVE_MY"),
    reason="set POINTLESSQL_TEST_LIVE_MY=1 to exercise a live MySQL",
)
async def test_e2e_mysql_live(
    admin_client: httpx.AsyncClient,
) -> None:  # pragma: no cover - opt-in
    """Live MySQL smoke test — wires up against $MYSQL_HOST etc."""
    host = os.environ.get("MYSQL_HOST", "127.0.0.1")
    port = int(os.environ.get("MYSQL_PORT", "3306"))
    db = os.environ.get("MYSQL_DATABASE", "mysql")
    user = os.environ.get("MYSQL_USER", "root")
    password = os.environ.get("MYSQL_PASSWORD", "")
    source_id = _seed(
        kind="mysql",
        config={"host": host, "port": port, "db": db, "user": user},
        secrets={"password": password},
        mapping={
            "source_table": "mysql.user",
            "target_fqn": "main.ingest.mysql_user",
            "mode": "full",
        },
    )
    body, _pql = await _pull_and_capture(admin_client, source_id)
    assert body["ok"] is True
    if body["failures"]:
        pytest.fail(f"live-mysql pull failed: {body['failures']}")
