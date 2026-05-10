"""Unit tests for the Phase 16.5.2 branch-creation primitive."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from deltalake import DeltaTable, write_deltalake
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.types import UNSET

from pointlessql.config import BranchSettings, Settings
from pointlessql.pql._branch import (
    _classify_storage_scheme,
    _clone_table_local,
    _derive_branch_storage_root,
    _pick_strategy,
    _split_two_part,
    _stats_from_action_row,
    _uri_to_local_path,
    create_branch_schema,
)
from pointlessql.pql._branch_errors import (
    BranchAlreadyExistsError,
    BranchCloudUnsupportedError,
    BranchOfBranchError,
)
from pointlessql.pql.branch import _create as branch_mod
from pointlessql.services.branch_tags import (
    STRATEGY_DEEP_COPY,
    STRATEGY_SYMLINK,
)


class TestClassifyStorageScheme:
    @pytest.mark.parametrize(
        "uri",
        ["/abs/path", "file:///abs/path", "file:/abs/path", "./rel/path"],
    )
    def test_local(self, uri: str) -> None:
        assert _classify_storage_scheme(uri) == "local"

    @pytest.mark.parametrize(
        "uri",
        ["s3://bucket/key", "gs://bucket/key", "abfss://c/key", "wasbs://c/key"],
    )
    def test_cloud(self, uri: str) -> None:
        assert _classify_storage_scheme(uri) == "cloud"

    def test_unknown_scheme_raises(self) -> None:
        with pytest.raises(ValueError, match="unsupported storage scheme"):
            _classify_storage_scheme("hdfs://nope")


class TestUriToLocalPath:
    def test_file_uri(self) -> None:
        assert _uri_to_local_path("file:///abs/path") == Path("/abs/path")

    def test_bare_path(self) -> None:
        assert _uri_to_local_path("/abs/path") == Path("/abs/path")

    def test_url_encoded_file_uri(self) -> None:
        assert _uri_to_local_path("file:///abs/some%20dir") == Path("/abs/some dir")

    def test_cloud_raises(self) -> None:
        with pytest.raises(ValueError, match="non-local URI"):
            _uri_to_local_path("s3://bucket/key")


class TestDeriveBranchStorageRoot:
    def test_local_path(self) -> None:
        assert (
            _derive_branch_storage_root("/data/playground/bronze", "feature_x")
            == "/data/playground/bronze/_branches/feature_x"
        )

    def test_strips_trailing_slash(self) -> None:
        assert _derive_branch_storage_root("/data/", "x") == "/data/_branches/x"

    def test_cloud_uri(self) -> None:
        assert (
            _derive_branch_storage_root("s3://bucket/data", "x") == "s3://bucket/data/_branches/x"
        )


class TestSplitTwoPart:
    def test_ok(self) -> None:
        assert _split_two_part("a.b", "src") == ("a", "b")

    def test_one_part_raises(self) -> None:
        with pytest.raises(ValueError, match="two-part"):
            _split_two_part("a", "src")

    def test_three_parts_raises(self) -> None:
        with pytest.raises(ValueError, match="two-part"):
            _split_two_part("a.b.c", "src")

    def test_empty_part_raises(self) -> None:
        with pytest.raises(ValueError, match="two-part"):
            _split_two_part("a.", "src")


class TestPickStrategy:
    def _settings(self, *, cloud_strategy: str = "error") -> Settings:
        s = Settings()
        s.branch = BranchSettings(cloud_strategy=cloud_strategy)  # type: ignore[arg-type]
        return s

    def test_explicit_symlink(self) -> None:
        assert _pick_strategy("symlink", "cloud", self._settings()) == STRATEGY_SYMLINK

    def test_explicit_deep_copy(self) -> None:
        assert _pick_strategy("deep_copy", "local", self._settings()) == STRATEGY_DEEP_COPY

    def test_auto_local(self) -> None:
        assert _pick_strategy("auto", "local", self._settings()) == STRATEGY_SYMLINK

    def test_auto_cloud_with_deep_copy_setting(self) -> None:
        s = self._settings(cloud_strategy="deep_copy")
        assert _pick_strategy("auto", "cloud", s) == STRATEGY_DEEP_COPY

    def test_auto_cloud_with_error_setting_raises(self) -> None:
        with pytest.raises(BranchCloudUnsupportedError):
            _pick_strategy("auto", "cloud", self._settings())


class TestStatsFromActionRow:
    def test_full_stats(self) -> None:
        row: dict[str, Any] = {
            "num_records": 3,
            "min.id": 1,
            "max.id": 3,
            "min.name": "a",
            "max.name": "c",
            "null_count.id": 0,
            "null_count.name": 0,
        }
        decoded = json.loads(_stats_from_action_row(row, ["id", "name"]))
        assert decoded["numRecords"] == 3
        assert decoded["minValues"] == {"id": 1, "name": "a"}
        assert decoded["maxValues"] == {"id": 3, "name": "c"}
        assert decoded["nullCount"] == {"id": 0, "name": 0}

    def test_missing_columns_skipped(self) -> None:
        row: dict[str, Any] = {"num_records": 1}
        decoded = json.loads(_stats_from_action_row(row, ["id"]))
        assert decoded == {"numRecords": 1}


class TestCloneTableLocal:
    """End-to-end clone helper exercises against real Delta + filesystem."""

    def _make_source(self, root: Path, rows: int = 3) -> Path:
        src = root / "source"
        df = pd.DataFrame({"id": list(range(rows)), "name": [chr(97 + i) for i in range(rows)]})
        write_deltalake(str(src), df)
        return src

    def test_symlink_clone_reads_same_data(self, tmp_path: Path) -> None:
        src = self._make_source(tmp_path)
        branch = tmp_path / "branch"
        version = _clone_table_local(str(src), str(branch), mode="symlink")

        branch_dt = DeltaTable(str(branch))
        rows = branch_dt.to_pyarrow_table().to_pylist()
        assert len(rows) == 3
        assert version == 0

        # The branch's parquet file is a symlink to the source's.
        parquet_files = [p for p in branch.iterdir() if p.suffix == ".parquet"]
        assert parquet_files
        assert parquet_files[0].is_symlink()

    def test_symlink_clone_isolates_writes(self, tmp_path: Path) -> None:
        src = self._make_source(tmp_path)
        branch = tmp_path / "branch"
        _clone_table_local(str(src), str(branch), mode="symlink")

        # Append two new rows to the branch.
        df_new = pd.DataFrame({"id": [10, 11], "name": ["x", "y"]})
        write_deltalake(str(branch), df_new, mode="append")

        # Source stays unchanged.
        src_dt = DeltaTable(str(src))
        assert len(src_dt.to_pyarrow_table()) == 3
        # Branch reflects the append.
        branch_dt = DeltaTable(str(branch))
        assert len(branch_dt.to_pyarrow_table()) == 5

    def test_deep_copy_clone_duplicates_files(self, tmp_path: Path) -> None:
        src = self._make_source(tmp_path)
        branch = tmp_path / "branch"
        _clone_table_local(str(src), str(branch), mode="deep_copy")

        parquet_files = [p for p in branch.iterdir() if p.suffix == ".parquet"]
        assert parquet_files
        assert not parquet_files[0].is_symlink()


class TestCreateBranchSchemaOrchestration:
    """Higher-level tests with soyuz client + DB session factory mocked.

    The actual filesystem cloning runs for real against ``tmp_path``
    so the symlink + Delta-log writes are exercised end-to-end.  Only
    the soyuz HTTP boundary is stubbed.
    """

    @pytest.fixture
    def settings(self) -> Settings:
        return Settings()

    @pytest.fixture
    def fake_source_dt(self, tmp_path: Path) -> tuple[Path, Path]:
        catalog_root = tmp_path / "playground" / "bronze"
        catalog_root.mkdir(parents=True)
        events_uri = catalog_root / "events"
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
        write_deltalake(str(events_uri), df)
        return catalog_root, events_uri

    def _make_client(
        self,
        *,
        source_storage_root: str,
        events_uri: str,
        existing_branch: bool = False,
    ) -> Any:
        client = MagicMock()
        # _get_schema.sync is called twice: once for the branch lookup,
        # once for the source.  We patch at module-level instead.
        return client

    def test_already_exists_raises(
        self,
        fake_source_dt: tuple[Path, Path],
        settings: Settings,
    ) -> None:
        catalog_root, _ = fake_source_dt
        client = MagicMock()
        existing = SchemaInfo(name="bronze_branch_x", catalog_name="playground")
        with patch.object(branch_mod._get_schema, "sync", return_value=existing):
            with pytest.raises(BranchAlreadyExistsError):
                create_branch_schema(
                    client=client,
                    source_schema_fqn="playground.bronze",
                    branch_name="bronze_branch_x",
                    settings=settings,
                )

    def test_branch_of_branch_raises(
        self,
        fake_source_dt: tuple[Path, Path],
        settings: Settings,
    ) -> None:
        client = MagicMock()
        # First _get_schema.sync (branch existence) returns None,
        # then read_branch_tags_sync detects the source IS a branch.
        with (
            patch.object(branch_mod._get_schema, "sync", return_value=None),
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=MagicMock(status="active"),
            ),
        ):
            with pytest.raises(BranchOfBranchError):
                create_branch_schema(
                    client=client,
                    source_schema_fqn="playground.bronze_branch_y",
                    branch_name="bronze_branch_z",
                    settings=settings,
                )

    def test_cloud_unsupported_raises(
        self,
        settings: Settings,
    ) -> None:
        client = MagicMock()
        source_info = SchemaInfo(
            name="bronze",
            catalog_name="playground",
            storage_root="s3://bucket/data",
            storage_location=UNSET,
        )
        with (
            patch.object(branch_mod._get_schema, "sync", side_effect=[None, source_info]),
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=None,
            ),
        ):
            with pytest.raises(BranchCloudUnsupportedError):
                create_branch_schema(
                    client=client,
                    source_schema_fqn="playground.bronze",
                    branch_name="bronze_branch_q",
                    settings=settings,
                )

    def test_invalid_branch_name_raises(self, settings: Settings) -> None:
        client = MagicMock()
        with pytest.raises(ValueError, match="must be a single name"):
            create_branch_schema(
                client=client,
                source_schema_fqn="playground.bronze",
                branch_name="catalog.dotted",
                settings=settings,
            )

    def test_happy_path_local_symlink(
        self,
        fake_source_dt: tuple[Path, Path],
        settings: Settings,
    ) -> None:
        catalog_root, events_uri = fake_source_dt
        client = MagicMock()
        source_info = SchemaInfo(
            name="bronze",
            catalog_name="playground",
            storage_root=str(catalog_root),
            storage_location=UNSET,
        )

        # _get_schema is called: 1) branch existence check (None),
        # 2) source resolution (source_info)
        with (
            patch.object(
                branch_mod._get_schema,
                "sync",
                side_effect=[None, source_info],
            ),
            patch.object(branch_mod._create_schema, "sync", return_value=None),
            patch.object(branch_mod._create_table, "sync", return_value=None),
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=None,
            ),
            patch("pointlessql.pql._branch.branch_tags.apply_branch_tags_sync") as mock_apply_tags,
            patch.object(
                branch_mod,
                "_list_source_tables",
                return_value=[
                    {
                        "name": "events",
                        "table_type": "MANAGED",
                        "data_source_format": "DELTA",
                        "columns": [],
                        "storage_location": str(events_uri),
                    }
                ],
            ),
            patch.object(branch_mod, "_emit_branch_created_event") as mock_emit,
        ):
            result = create_branch_schema(
                client=client,
                source_schema_fqn="playground.bronze",
                branch_name="bronze_branch_42",
                settings=settings,
            )

        assert result == "playground.bronze_branch_42"

        # The branch directory + symlinked table was created.
        branch_root = catalog_root / "_branches" / "bronze_branch_42"
        assert branch_root.is_dir()
        branch_events = branch_root / "events"
        assert branch_events.is_dir()
        parquets = [p for p in branch_events.iterdir() if p.suffix == ".parquet"]
        assert parquets and parquets[0].is_symlink()

        # Tags were applied with the right metadata.
        mock_apply_tags.assert_called_once()
        kwargs = mock_apply_tags.call_args.kwargs
        assert kwargs["parent_schema"] == "playground.bronze"
        assert kwargs["strategy"] == STRATEGY_SYMLINK
        assert kwargs["parent_version_at_create"] == {"events": 0}

        # CloudEvent emitter was called.
        mock_emit.assert_called_once()
