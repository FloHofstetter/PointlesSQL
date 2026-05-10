"""Unit tests for the Phase 16.5.3 branch-discard primitive."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest
from deltalake import write_deltalake
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.types import UNSET

from pointlessql.config import Settings
from pointlessql.pql._branch import (
    _delete_branch_storage,
    discard_branch_schema,
)
from pointlessql.pql._branch_errors import (
    BranchInUseError,
    BranchNotFoundError,
)
from pointlessql.pql.branch import _discard as branch_mod
from pointlessql.services.branch_tags import (
    STATUS_ACTIVE,
    STATUS_DISCARDED,
    STATUS_PROMOTED,
    STRATEGY_SYMLINK,
    BranchTags,
)


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _branch_tags(status: str = STATUS_ACTIVE) -> BranchTags:
    return BranchTags(
        parent_schema="playground.bronze",
        parent_version_at_create={"events": 0},
        created_at="2026-04-29T12:00:00+00:00",
        created_by_run_id=None,
        strategy=STRATEGY_SYMLINK,
        status=status,
    )


class TestDeleteBranchStorage:
    def test_no_op_when_none(self) -> None:
        _delete_branch_storage(None)  # no exception

    def test_removes_local_directory(self, tmp_path: Path) -> None:
        branch_root = tmp_path / "_branches" / "feature_x"
        events = branch_root / "events"
        events.mkdir(parents=True)
        (events / "data.parquet").write_bytes(b"x")
        _delete_branch_storage(str(branch_root))
        assert not branch_root.exists()

    def test_no_op_when_directory_missing(self, tmp_path: Path) -> None:
        # Idempotent re-discard.
        ghost = tmp_path / "ghost"
        _delete_branch_storage(str(ghost))
        assert not ghost.exists()

    def test_symlink_target_untouched(self, tmp_path: Path) -> None:
        # Branch storage with a symlink: the source must survive cleanup.
        source = tmp_path / "source"
        source.mkdir()
        source_file = source / "data.parquet"
        source_file.write_bytes(b"important")

        branch = tmp_path / "_branches" / "feature_x"
        branch.mkdir(parents=True)
        (branch / "data.parquet").symlink_to(source_file)

        _delete_branch_storage(str(branch))

        assert not branch.exists()
        assert source_file.exists()
        assert source_file.read_bytes() == b"important"

    def test_cloud_uri_raises(self) -> None:
        with pytest.raises(ValueError, match="cloud-storage discard not implemented"):
            _delete_branch_storage("s3://bucket/_branches/x")


class TestDiscardBranchSchema:
    def test_branch_not_found_raises(self, settings: Settings) -> None:
        client = MagicMock()
        with (
            patch.object(branch_mod._get_schema, "sync", return_value=None),
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=None,
            ),
        ):
            with pytest.raises(BranchNotFoundError, match="not found"):
                discard_branch_schema(
                    client=client,
                    branch_schema_fqn="playground.bronze_branch_42",
                    settings=settings,
                )

    def test_non_branch_schema_raises(self, settings: Settings) -> None:
        # Schema exists but has no branch tags — refuse to discard.
        client = MagicMock()
        existing = SchemaInfo(
            name="bronze",
            catalog_name="playground",
            storage_root="/tmp/whatever",
            storage_location=UNSET,
        )
        with (
            patch.object(branch_mod._get_schema, "sync", return_value=existing),
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=None,
            ),
        ):
            with pytest.raises(BranchNotFoundError, match="non-branch schema"):
                discard_branch_schema(
                    client=client,
                    branch_schema_fqn="playground.bronze",
                    settings=settings,
                )

    def test_promoted_raises(self, settings: Settings) -> None:
        client = MagicMock()
        existing = SchemaInfo(
            name="bronze_branch_42",
            catalog_name="playground",
            storage_root="/tmp/whatever",
            storage_location=UNSET,
        )
        with (
            patch.object(branch_mod._get_schema, "sync", return_value=existing),
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=_branch_tags(STATUS_PROMOTED),
            ),
        ):
            with pytest.raises(BranchInUseError, match="status='promoted'"):
                discard_branch_schema(
                    client=client,
                    branch_schema_fqn="playground.bronze_branch_42",
                    settings=settings,
                )

    def test_already_discarded_no_op(self, settings: Settings) -> None:
        # Idempotent: a re-discard does not raise.
        client = MagicMock()
        existing = SchemaInfo(
            name="bronze_branch_42",
            catalog_name="playground",
            storage_root="/tmp/whatever",
            storage_location=UNSET,
        )
        with (
            patch.object(branch_mod._get_schema, "sync", return_value=existing),
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=_branch_tags(STATUS_DISCARDED),
            ),
        ):
            discard_branch_schema(
                client=client,
                branch_schema_fqn="playground.bronze_branch_42",
                settings=settings,
            )

    def test_happy_path_local_symlink(
        self,
        tmp_path: Path,
        settings: Settings,
    ) -> None:
        # Set up: a real local branch storage tree with a symlinked
        # parquet, and a separate "source" the symlink points at.
        source_dir = tmp_path / "playground" / "bronze" / "events"
        source_dir.mkdir(parents=True)
        df = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
        write_deltalake(str(source_dir), df)

        # The branch storage_root.
        branch_root = tmp_path / "playground" / "bronze" / "_branches" / "bronze_branch_42"
        events_branch = branch_root / "events"
        events_branch.mkdir(parents=True)
        # Symlink the source's parquet into the branch dir.
        source_parquets = list(source_dir.glob("*.parquet"))
        assert source_parquets
        (events_branch / source_parquets[0].name).symlink_to(source_parquets[0])

        client = MagicMock()
        existing = SchemaInfo(
            name="bronze_branch_42",
            catalog_name="playground",
            storage_root=str(branch_root),
            storage_location=UNSET,
        )

        with (
            patch.object(branch_mod._get_schema, "sync", return_value=existing),
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=_branch_tags(STATUS_ACTIVE),
            ),
            patch(
                "pointlessql.services.unitycatalog._api._delete_schema.sync"
            ) as mock_delete_schema,
            patch.object(branch_mod, "emit_branch_event") as mock_emit,
            patch.object(branch_mod, "record_branch_audit_log") as mock_audit,
        ):
            discard_branch_schema(
                client=client,
                branch_schema_fqn="playground.bronze_branch_42",
                settings=settings,
            )

        # Branch storage gone, source untouched.
        assert not branch_root.exists()
        assert source_parquets[0].exists()

        # UC delete called with force=True.
        mock_delete_schema.assert_called_once()
        kwargs = mock_delete_schema.call_args.kwargs
        assert kwargs["full_name"] == "playground.bronze_branch_42"
        assert kwargs["force"] is True

        # Audit log + CloudEvent fired.
        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["action"] == "discard"
        mock_emit.assert_called_once()
        assert mock_emit.call_args.kwargs["event_type"] == "pointlessql.branch.discarded.v1"
