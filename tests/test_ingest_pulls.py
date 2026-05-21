"""Phase 82.3 — manual pull endpoint smoke tests.

These exercise the synchronous pull path against a tiny CSV fixture
so we don't need a live external DB.  The full per-connector matrix
is covered in Phase 82.4.

We patch out the soyuz UC client at the PQL boundary so the write
path doesn't need a running soyuz-catalog server.
"""

from __future__ import annotations

import datetime
import json
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


def _seed_source(
    *,
    name: str,
    kind: str,
    config: dict[str, Any],
    mappings: list[dict[str, Any]] | None = None,
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
            secrets="{}",
            table_mappings=json.dumps(mappings or []),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(src)
        session.commit()
        return int(src.id)


@pytest.mark.asyncio
async def test_pull_now_with_no_mappings_returns_400(
    admin_client: httpx.AsyncClient,
) -> None:
    """A source without table_mappings cannot run a pull."""
    source_id = _seed_source(
        name="empty",
        kind="file_upload",
        config={"path": "/tmp/missing.csv"},
    )
    res = await admin_client.post(f"/api/ingest/sources/{source_id}/pulls")
    # Phase 82 follow-up: ValidationError maps to RFC-9457 422 (was 400).
    assert res.status_code == 422


@pytest.mark.asyncio
async def test_pull_now_writes_stats_to_mapping(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """A successful pull records last_pull_stats on the mapping.

    PQL.write_table is patched to a no-op so the test stays
    deterministic without a soyuz / Delta backend.
    """
    csv_path = tmp_path / "tiny.csv"
    csv_path.write_text("id,name\n1,a\n2,b\n", encoding="utf-8")
    source_id = _seed_source(
        name="csv-pull",
        kind="file_upload",
        config={"path": str(csv_path)},
        mappings=[
            {
                "source_table": "tiny.csv",
                "target_fqn": "main.ingest.tiny",
                "mode": "full",
            }
        ],
    )

    with patch(
        "pointlessql.pql.pql.PQL"
    ) as mock_pql_cls:
        instance = MagicMock()
        instance.write_table = MagicMock(return_value=None)
        mock_pql_cls.return_value = instance
        res = await admin_client.post(
            f"/api/ingest/sources/{source_id}/pulls", json={}
        )

    assert res.status_code == 200, res.text
    body = res.json()
    assert body["ok"] is True
    assert len(body["results"]) == 1
    assert body["results"][0]["rows_written"] == 2

    # Stats persisted on the mapping.
    factory = app.state.session_factory
    with factory() as session:
        row = session.get(IngestSource, source_id)
        assert row is not None
        mappings = json.loads(row.table_mappings)
        stats = mappings[0]["last_pull_stats"]
        assert stats["ok"] is True
        assert stats["rows_written"] == 2


@pytest.mark.asyncio
async def test_pull_now_specific_mapping_index(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """``mapping_index`` filters which mapping runs."""
    csv1 = tmp_path / "a.csv"
    csv1.write_text("x\n1\n", encoding="utf-8")
    csv2 = tmp_path / "b.csv"
    csv2.write_text("y\n2\n", encoding="utf-8")
    source_id = _seed_source(
        name="multi",
        kind="file_upload",
        config={"path": str(csv1)},
        mappings=[
            {
                "source_table": "a.csv",
                "target_fqn": "main.ingest.a",
                "mode": "full",
            },
            {
                "source_table": "b.csv",
                "target_fqn": "main.ingest.b",
                "mode": "full",
            },
        ],
    )

    with patch("pointlessql.pql.pql.PQL") as mock_pql_cls:
        instance = MagicMock()
        instance.write_table = MagicMock(return_value=None)
        mock_pql_cls.return_value = instance
        res = await admin_client.post(
            f"/api/ingest/sources/{source_id}/pulls",
            json={"mapping_index": 1},
        )

    body = res.json()
    assert len(body["results"]) == 1
    assert body["results"][0]["mapping_index"] == 1


@pytest.mark.asyncio
async def test_runs_history_lists_latest_stats(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """GET /runs returns latest_per_mapping after a pull."""
    csv_path = tmp_path / "x.csv"
    csv_path.write_text("a\n1\n", encoding="utf-8")
    source_id = _seed_source(
        name="runs",
        kind="file_upload",
        config={"path": str(csv_path)},
        mappings=[
            {
                "source_table": "x.csv",
                "target_fqn": "main.ingest.x",
                "mode": "full",
            }
        ],
    )

    with patch("pointlessql.pql.pql.PQL") as mock_pql_cls:
        instance = MagicMock()
        instance.write_table = MagicMock(return_value=None)
        mock_pql_cls.return_value = instance
        await admin_client.post(f"/api/ingest/sources/{source_id}/pulls")

    res = await admin_client.get(f"/api/ingest/sources/{source_id}/runs")
    assert res.status_code == 200
    body = res.json()
    assert len(body["latest_per_mapping"]) == 1
    assert body["latest_per_mapping"][0]["stats"]["ok"] is True
    assert body["scheduled_history"] == []
