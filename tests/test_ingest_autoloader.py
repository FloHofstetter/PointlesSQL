"""Auto-loader tests — incremental file discovery + per-file append.

The ``autoloader_files`` model is not exported from
``pointlessql.models`` yet (no migration shipped), so the module is
imported directly here to register the table on ``Base.metadata``
before the session-scoped test engine runs ``create_all``.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Literal
from unittest.mock import MagicMock, patch

import deltalake
import httpx
import pytest

import pointlessql.models.autoloader  # noqa: F401  # pyright: ignore[reportUnusedImport]
from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import IngestSource
from pointlessql.services.ingest import autoloader
from pointlessql.services.ingest.pull import PullError


def _factory() -> Any:
    return app.state.session_factory


def _seed_source(
    *,
    name: str = "files",
    kind: str = "file_upload",
    config: dict[str, Any] | None = None,
    mappings: list[dict[str, Any]] | None = None,
) -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        src = IngestSource(
            workspace_id=1,
            owner_user_id=1,
            name=name,
            kind=kind,
            config=json.dumps(config or {}),
            secrets="{}",
            table_mappings=json.dumps(mappings or []),
            is_active=True,
            created_at=now,
            updated_at=now,
        )
        session.add(src)
        session.commit()
        return int(src.id)


_WriteMode = Literal["error", "append", "overwrite", "ignore"]


class _DeltaAppendPQL:
    """Minimal PQL stand-in that appends frames to one local Delta dir."""

    def __init__(self, target_location: Path) -> None:
        self.target_location = str(target_location)
        self.calls: list[tuple[str, str]] = []

    def write_table(self, df: Any, full_name: str, *, mode: _WriteMode = "overwrite") -> None:
        self.calls.append((full_name, mode))
        deltalake.write_deltalake(self.target_location, df, mode=mode)


class _FailingPQL(_DeltaAppendPQL):
    """Appends normally except for frames whose first id is poisoned."""

    def __init__(self, target_location: Path, poison_id: int) -> None:
        super().__init__(target_location)
        self.poison_id = poison_id

    def write_table(self, df: Any, full_name: str, *, mode: _WriteMode = "overwrite") -> None:
        if int(df["id"].iloc[0]) == self.poison_id:
            raise RuntimeError("poisoned file")
        super().write_table(df, full_name, mode=mode)


def test_discover_then_mark_then_rediscover(tmp_path: Path) -> None:
    """Discovery returns unseen files only; marking is idempotent."""
    source_id = _seed_source()
    (tmp_path / "a.csv").write_text("id\n1\n", encoding="utf-8")
    (tmp_path / "b.csv").write_text("id\n2\n", encoding="utf-8")
    pattern = str(tmp_path / "*.csv")

    found = autoloader.discover_new_files(
        _factory(), source_id=source_id, mapping_index=0, pattern=pattern
    )
    assert found == sorted(found)
    assert [Path(p).name for p in found] == ["a.csv", "b.csv"]

    assert (
        autoloader.mark_processed(_factory(), source_id=source_id, mapping_index=0, paths=found)
        == 2
    )
    # Idempotent: re-marking the same paths inserts nothing.
    assert (
        autoloader.mark_processed(_factory(), source_id=source_id, mapping_index=0, paths=found)
        == 0
    )
    assert (
        autoloader.discover_new_files(
            _factory(), source_id=source_id, mapping_index=0, pattern=pattern
        )
        == []
    )

    # A new file surfaces on the next discovery.
    (tmp_path / "c.csv").write_text("id\n3\n", encoding="utf-8")
    again = autoloader.discover_new_files(
        _factory(), source_id=source_id, mapping_index=0, pattern=pattern
    )
    assert [Path(p).name for p in again] == ["c.csv"]


def test_registry_is_scoped_per_mapping(tmp_path: Path) -> None:
    """Marking under one mapping_index does not hide files from another."""
    source_id = _seed_source()
    (tmp_path / "a.csv").write_text("id\n1\n", encoding="utf-8")
    pattern = str(tmp_path / "*.csv")

    found = autoloader.discover_new_files(
        _factory(), source_id=source_id, mapping_index=0, pattern=pattern
    )
    autoloader.mark_processed(_factory(), source_id=source_id, mapping_index=0, paths=found)

    other = autoloader.discover_new_files(
        _factory(), source_id=source_id, mapping_index=1, pattern=pattern
    )
    assert [Path(p).name for p in other] == ["a.csv"]


def test_directory_discovery_filters_unsupported_extensions(tmp_path: Path) -> None:
    """Plain-directory patterns keep only reader-supported extensions."""
    source_id = _seed_source()
    (tmp_path / "a.csv").write_text("id\n1\n", encoding="utf-8")
    (tmp_path / "notes.txt").write_text("not data", encoding="utf-8")

    found = autoloader.discover_new_files(
        _factory(), source_id=source_id, mapping_index=0, pattern=str(tmp_path)
    )
    assert [Path(p).name for p in found] == ["a.csv"]


def test_pattern_for_kind_rejects_remote_and_sql_kinds() -> None:
    """Auto-loader discovery is local-filesystem only."""
    with pytest.raises(ValidationError):
        autoloader.pattern_for_kind("s3", {"url": "s3://bucket/*.parquet"})
    with pytest.raises(ValidationError):
        autoloader.pattern_for_kind("postgres", {"host": "db"})
    with pytest.raises(ValidationError):
        autoloader.pattern_for_kind("parquet_glob", {"pattern": "s3://bucket/*.parquet"})
    with pytest.raises(ValidationError):
        autoloader.pattern_for_kind("file_upload", {})
    assert autoloader.pattern_for_kind("parquet_glob", {"pattern": "/data/*.parquet"}) == (
        "/data/*.parquet"
    )


def test_pull_incremental_appends_only_new_files(tmp_path: Path) -> None:
    """Each pull appends exactly the not-yet-registered files."""
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    (data_dir / "a.csv").write_text("id\n1\n2\n", encoding="utf-8")
    (data_dir / "b.csv").write_text("id\n3\n", encoding="utf-8")
    target = tmp_path / "delta" / "events"
    source_id = _seed_source(config={"path": str(data_dir / "*.csv")})
    mapping = {"target_fqn": "main.ingest.events", "mode": "full", "pull_mode": "auto_loader"}
    pql = _DeltaAppendPQL(target)

    result = autoloader.pull_incremental(
        _factory(),
        source_id=source_id,
        mapping_index=0,
        kind="file_upload",
        config={"path": str(data_dir / "*.csv")},
        mapping=mapping,
        pql_instance=pql,
    )
    assert result.files_processed == 2
    assert result.rows_written == 3
    assert result.mode == "auto_loader"
    assert all(mode == "append" for _, mode in pql.calls)
    assert len(deltalake.DeltaTable(str(target)).to_pandas()) == 3

    # Second pull with one new file appends only its rows.
    (data_dir / "c.csv").write_text("id\n4\n", encoding="utf-8")
    result2 = autoloader.pull_incremental(
        _factory(),
        source_id=source_id,
        mapping_index=0,
        kind="file_upload",
        config={"path": str(data_dir / "*.csv")},
        mapping=mapping,
        pql_instance=pql,
    )
    assert result2.files_processed == 1
    assert result2.rows_written == 1
    assert len(deltalake.DeltaTable(str(target)).to_pandas()) == 4

    # Third pull discovers nothing and writes nothing.
    result3 = autoloader.pull_incremental(
        _factory(),
        source_id=source_id,
        mapping_index=0,
        kind="file_upload",
        config={"path": str(data_dir / "*.csv")},
        mapping=mapping,
        pql_instance=pql,
    )
    assert result3.files_processed == 0
    assert result3.rows_written == 0
    assert len(deltalake.DeltaTable(str(target)).to_pandas()) == 4


def test_pull_incremental_failure_leaves_failing_file_unmarked(tmp_path: Path) -> None:
    """A mid-pull failure stops the loop; the bad file retries next pull."""
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    (data_dir / "a.csv").write_text("id\n1\n", encoding="utf-8")
    (data_dir / "b.csv").write_text("id\n2\n", encoding="utf-8")
    target = tmp_path / "delta" / "events"
    source_id = _seed_source(config={"path": str(data_dir / "*.csv")})
    mapping = {"target_fqn": "main.ingest.events", "mode": "full"}

    poisoned = _FailingPQL(target, poison_id=2)
    with pytest.raises(PullError):
        autoloader.pull_incremental(
            _factory(),
            source_id=source_id,
            mapping_index=0,
            kind="file_upload",
            config={"path": str(data_dir / "*.csv")},
            mapping=mapping,
            pql_instance=poisoned,
        )
    # a.csv landed and is registered; b.csv stays pending.
    assert len(deltalake.DeltaTable(str(target)).to_pandas()) == 1
    pending = autoloader.discover_new_files(
        _factory(), source_id=source_id, mapping_index=0, pattern=str(data_dir / "*.csv")
    )
    assert [Path(p).name for p in pending] == ["b.csv"]

    # Retry with a healthy writer processes only the failed file.
    healthy = _DeltaAppendPQL(target)
    result = autoloader.pull_incremental(
        _factory(),
        source_id=source_id,
        mapping_index=0,
        kind="file_upload",
        config={"path": str(data_dir / "*.csv")},
        mapping=mapping,
        pql_instance=healthy,
    )
    assert result.files_processed == 1
    assert len(deltalake.DeltaTable(str(target)).to_pandas()) == 2


@pytest.mark.asyncio
async def test_manual_pull_routes_through_auto_loader(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
) -> None:
    """``pull_mode: auto_loader`` reroutes the manual-pull executor."""
    data_dir = tmp_path / "in"
    data_dir.mkdir()
    (data_dir / "a.csv").write_text("id\n1\n2\n", encoding="utf-8")
    source_id = _seed_source(
        config={"path": str(data_dir / "*.csv")},
        mappings=[
            {
                "source_table": "a.csv",
                "target_fqn": "main.ingest.events",
                "mode": "full",
                "pull_mode": "auto_loader",
            }
        ],
    )

    with patch("pointlessql.pql.pql.PQL") as mock_pql_cls:
        instance = MagicMock()
        instance.write_table = MagicMock(return_value=None)
        mock_pql_cls.return_value = instance
        res = await admin_client.post(f"/api/ingest/sources/{source_id}/pulls", json={})
        assert res.status_code == 200, res.text
        body = res.json()
        assert body["results"][0]["files_processed"] == 1
        assert body["results"][0]["rows_written"] == 2
        assert body["results"][0]["mode"] == "auto_loader"
        instance.write_table.assert_called_once()
        assert instance.write_table.call_args.kwargs["mode"] == "append"

        # Second manual pull: nothing new, nothing written.
        res2 = await admin_client.post(f"/api/ingest/sources/{source_id}/pulls", json={})
        assert res2.json()["results"][0]["files_processed"] == 0
        instance.write_table.assert_called_once()


@pytest.mark.asyncio
async def test_mappings_endpoint_round_trips_pull_mode(
    admin_client: httpx.AsyncClient,
) -> None:
    """Only the non-default ``auto_loader`` value is persisted."""
    source_id = _seed_source()
    res = await admin_client.post(
        f"/api/ingest/sources/{source_id}/mappings",
        json={
            "mappings": [
                {
                    "source_table": "a.csv",
                    "target_fqn": "main.ingest.a",
                    "mode": "full",
                    "pull_mode": "auto_loader",
                },
                {
                    "source_table": "b.csv",
                    "target_fqn": "main.ingest.b",
                    "mode": "full",
                    "pull_mode": "full_reload",
                },
            ]
        },
    )
    assert res.status_code == 200, res.text
    stored = res.json()["mappings"]
    assert stored[0]["pull_mode"] == "auto_loader"
    assert "pull_mode" not in stored[1]

    bad = await admin_client.post(
        f"/api/ingest/sources/{source_id}/mappings",
        json={
            "mappings": [
                {
                    "source_table": "a.csv",
                    "target_fqn": "main.ingest.a",
                    "mode": "full",
                    "pull_mode": "bogus",
                }
            ]
        },
    )
    assert bad.status_code == 422
