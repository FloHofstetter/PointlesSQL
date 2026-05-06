"""Unit tests for the Phase 16.5.4 branch-promote primitive."""

from __future__ import annotations

from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from soyuz_catalog_client.models.table_info import TableInfo

from pointlessql.pql._branch import (
    _check_promotion_conflicts,
    preview_promote_conflicts,
    promote_branch_schema,
)
from pointlessql.pql._branch_errors import (
    BranchInUseError,
    BranchNotFoundError,
    BranchPromotionConflictError,
)
from pointlessql.pql.branch import _promote as branch_mod
from pointlessql.services.branch_tags import (
    STATUS_ACTIVE,
    STATUS_PROMOTED,
    STRATEGY_SYMLINK,
    BranchTags,
)
from pointlessql.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings()


def _branch_tags(
    *,
    status: str = STATUS_ACTIVE,
    parent_versions: dict[str, int] | None = None,
) -> BranchTags:
    return BranchTags(
        parent_schema="playground.bronze",
        parent_version_at_create=parent_versions or {"events": 0},
        created_at="2026-04-29T12:00:00+00:00",
        created_by_run_id=None,
        strategy=STRATEGY_SYMLINK,
        status=status,
    )


def _table_info(location: str = "/tmp/playground/bronze/events") -> TableInfo:
    return TableInfo(
        catalog_name="playground",
        schema_name="bronze",
        name="events",
        storage_location=location,
    )


class TestCheckPromotionConflicts:
    def test_no_conflict_when_versions_match(self, tmp_path: Any) -> None:
        import pandas as pd
        from deltalake import write_deltalake

        events_dir = tmp_path / "events"
        df = pd.DataFrame({"id": [1, 2, 3]})
        write_deltalake(str(events_dir), df)

        client = MagicMock()
        with patch.object(
            branch_mod._get_table,
            "sync",
            return_value=_table_info(str(events_dir)),
        ):
            _check_promotion_conflicts(
                client=client,
                parent_schema_fqn="playground.bronze",
                parent_versions_at_create={"events": 0},
            )

    def test_version_drift_raises(self, tmp_path: Any) -> None:
        import pandas as pd
        from deltalake import write_deltalake

        events_dir = tmp_path / "events"
        df = pd.DataFrame({"id": [1, 2, 3]})
        write_deltalake(str(events_dir), df)
        # Append to bump version to 1.
        write_deltalake(str(events_dir), pd.DataFrame({"id": [4]}), mode="append")

        client = MagicMock()
        with patch.object(
            branch_mod._get_table,
            "sync",
            return_value=_table_info(str(events_dir)),
        ):
            with pytest.raises(BranchPromotionConflictError) as exc_info:
                _check_promotion_conflicts(
                    client=client,
                    parent_schema_fqn="playground.bronze",
                    parent_versions_at_create={"events": 0},
                )
            assert exc_info.value.expected_version == 0
            assert exc_info.value.actual_version == 1

    def test_missing_table_raises(self) -> None:
        client = MagicMock()
        with patch.object(branch_mod._get_table, "sync", return_value=None):
            with pytest.raises(BranchPromotionConflictError) as exc_info:
                _check_promotion_conflicts(
                    client=client,
                    parent_schema_fqn="playground.bronze",
                    parent_versions_at_create={"events": 0},
                )
            assert exc_info.value.actual_version == -1


class TestPromoteBranchSchema:
    def test_branch_not_found_raises(self, settings: Settings) -> None:
        client = MagicMock()
        with patch(
            "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
            return_value=None,
        ):
            with pytest.raises(BranchNotFoundError):
                promote_branch_schema(
                    client=client,
                    branch_schema_fqn="playground.bronze_branch_42",
                    settings=settings,
                )

    def test_promoted_branch_raises(self, settings: Settings) -> None:
        client = MagicMock()
        with patch(
            "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
            return_value=_branch_tags(status=STATUS_PROMOTED),
        ):
            with pytest.raises(BranchInUseError, match="status='promoted'"):
                promote_branch_schema(
                    client=client,
                    branch_schema_fqn="playground.bronze_branch_42",
                    settings=settings,
                )

    def test_happy_path(self, tmp_path: Any, settings: Settings) -> None:
        import pandas as pd
        from deltalake import write_deltalake

        events_dir = tmp_path / "events"
        df = pd.DataFrame({"id": [1, 2, 3]})
        write_deltalake(str(events_dir), df)

        client = MagicMock()
        rename_calls: list[tuple[str, str]] = []

        def _fake_rename(c: Any, full_name: str, new_name: str) -> None:
            rename_calls.append((full_name, new_name))

        with (
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=_branch_tags(),
            ),
            patch.object(
                branch_mod._get_table,
                "sync",
                return_value=_table_info(str(events_dir)),
            ),
            patch.object(branch_mod, "rename_schema", side_effect=_fake_rename),
            patch("pointlessql.pql._branch.branch_tags.set_branch_status_sync") as mock_set_status,
            patch(
                "pointlessql.pql._branch.branch_tags.mark_pre_promote_backup_sync"
            ) as mock_mark_backup,
            patch.object(branch_mod, "record_branch_audit_log") as mock_audit,
            patch.object(branch_mod, "emit_branch_event") as mock_emit,
        ):
            result = promote_branch_schema(
                client=client,
                branch_schema_fqn="playground.bronze_branch_42",
                settings=settings,
            )

        assert result["new_parent"] == "playground.bronze"
        assert result["backup"].startswith("playground.bronze_pre_promote_")

        # Two renames in correct order: parent → backup, then branch → parent.
        assert len(rename_calls) == 2
        assert rename_calls[0][0] == "playground.bronze"
        assert rename_calls[0][1].startswith("bronze_pre_promote_")
        assert rename_calls[1] == ("playground.bronze_branch_42", "bronze")

        # Tag updates: status=promoted on new parent, mark backup.
        mock_set_status.assert_called_once()
        assert mock_set_status.call_args.args[1] == "playground.bronze"
        assert mock_set_status.call_args.args[2] == STATUS_PROMOTED
        mock_mark_backup.assert_called_once()
        assert mock_mark_backup.call_args.args[1].startswith("playground.bronze_pre_promote_")

        # Audit + CloudEvent.
        mock_audit.assert_called_once()
        assert mock_audit.call_args.kwargs["action"] == "promote"
        mock_emit.assert_called_once()
        assert mock_emit.call_args.kwargs["event_type"] == "pointlessql.branch.promoted.v1"

    def test_conflict_aborts_before_rename(
        self,
        tmp_path: Any,
        settings: Settings,
    ) -> None:
        import pandas as pd
        from deltalake import write_deltalake

        events_dir = tmp_path / "events"
        df = pd.DataFrame({"id": [1, 2, 3]})
        write_deltalake(str(events_dir), df)
        # Bump parent version: branch was created at 0, now parent is 1.
        write_deltalake(str(events_dir), pd.DataFrame({"id": [4]}), mode="append")

        client = MagicMock()
        with (
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=_branch_tags(),
            ),
            patch.object(
                branch_mod._get_table,
                "sync",
                return_value=_table_info(str(events_dir)),
            ),
            patch.object(branch_mod, "rename_schema") as mock_rename,
        ):
            with pytest.raises(BranchPromotionConflictError):
                promote_branch_schema(
                    client=client,
                    branch_schema_fqn="playground.bronze_branch_42",
                    settings=settings,
                )
            mock_rename.assert_not_called()


class TestPreviewPromoteConflicts:
    def test_branch_not_found_raises(self) -> None:
        client = MagicMock()
        with patch(
            "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
            return_value=None,
        ):
            with pytest.raises(BranchNotFoundError):
                preview_promote_conflicts(
                    client=client,
                    branch_schema_fqn="playground.x",
                )

    def test_no_conflict_returns_ok(self, tmp_path: Any) -> None:
        import pandas as pd
        from deltalake import write_deltalake

        events_dir = tmp_path / "events"
        write_deltalake(str(events_dir), pd.DataFrame({"id": [1]}))

        client = MagicMock()
        with (
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=_branch_tags(),
            ),
            patch.object(
                branch_mod._get_table,
                "sync",
                return_value=_table_info(str(events_dir)),
            ),
        ):
            result = preview_promote_conflicts(
                client=client,
                branch_schema_fqn="playground.bronze_branch_42",
            )

        assert result["ok"] is True
        assert result["conflicts"] == []

    def test_drift_returns_conflict(self, tmp_path: Any) -> None:
        import pandas as pd
        from deltalake import write_deltalake

        events_dir = tmp_path / "events"
        write_deltalake(str(events_dir), pd.DataFrame({"id": [1]}))
        write_deltalake(str(events_dir), pd.DataFrame({"id": [2]}), mode="append")

        client = MagicMock()
        with (
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=_branch_tags(),
            ),
            patch.object(
                branch_mod._get_table,
                "sync",
                return_value=_table_info(str(events_dir)),
            ),
        ):
            result = preview_promote_conflicts(
                client=client,
                branch_schema_fqn="playground.bronze_branch_42",
            )

        assert result["ok"] is False
        assert len(result["conflicts"]) == 1
        assert result["conflicts"][0]["table"] == "events"
        assert result["conflicts"][0]["expected_version"] == 0
        assert result["conflicts"][0]["actual_version"] == 1

    def test_missing_table_returns_conflict(self) -> None:
        client = MagicMock()
        with (
            patch(
                "pointlessql.pql._branch.branch_tags.read_branch_tags_sync",
                return_value=_branch_tags(),
            ),
            patch.object(branch_mod._get_table, "sync", return_value=None),
        ):
            result = preview_promote_conflicts(
                client=client,
                branch_schema_fqn="playground.bronze_branch_42",
            )

        assert result["ok"] is False
        assert result["conflicts"][0]["reason"] == "missing"
