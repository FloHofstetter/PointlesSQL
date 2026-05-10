"""Unit tests for the Phase 16.5.6 branch auto-cleanup pass."""

from __future__ import annotations

import datetime as dt
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from pointlessql.config import BranchSettings, Settings
from pointlessql.services import branch_cleanup as cleanup_mod
from pointlessql.services.branch_cleanup import (
    _is_eligible_for_cleanup,
    _parse_iso8601,
    cleanup_old_branches,
)
from pointlessql.services.branch_tags import (
    STATUS_ACTIVE,
    STATUS_DISCARDED,
    STATUS_PROMOTED,
    STRATEGY_SYMLINK,
    BranchTags,
)


def _settings(*, enabled: bool = True, retention_days: int = 30) -> Settings:
    s = Settings()
    s.branch = BranchSettings(  # type: ignore[arg-type]
        auto_cleanup_enabled=enabled,
        auto_cleanup_retention_days=retention_days,
    )
    return s


def _tags(
    *,
    status: str = STATUS_ACTIVE,
    created_at: str = "2026-01-01T00:00:00+00:00",
    is_pre_promote_backup: bool = False,
) -> BranchTags:
    return BranchTags(
        parent_schema="playground.bronze",
        parent_version_at_create={"events": 0},
        created_at=created_at,
        created_by_run_id=None,
        strategy=STRATEGY_SYMLINK,
        status=status,
        is_pre_promote_backup=is_pre_promote_backup,
    )


class TestParseIso8601:
    def test_parses_offset_format(self) -> None:
        assert _parse_iso8601("2026-04-29T12:00:00+00:00") == dt.datetime(
            2026, 4, 29, 12, 0, 0, tzinfo=dt.UTC
        )

    def test_garbage_returns_none(self) -> None:
        assert _parse_iso8601("not a date") is None


class TestIsEligibleForCleanup:
    @pytest.fixture
    def now(self) -> dt.datetime:
        return dt.datetime(2026, 4, 30, 0, 0, tzinfo=dt.UTC)

    def test_too_young_skipped(self, now: dt.datetime) -> None:
        # 2026-04-25 is 5 days old vs a 30-day retention.
        tags = _tags(created_at="2026-04-25T00:00:00+00:00")
        assert not _is_eligible_for_cleanup(tags, now=now, retention_days=30)

    def test_old_active_eligible(self, now: dt.datetime) -> None:
        # 2026-01-01 is ~120 days old; well past 30-day retention.
        tags = _tags(created_at="2026-01-01T00:00:00+00:00")
        assert _is_eligible_for_cleanup(tags, now=now, retention_days=30)

    def test_promoted_skipped(self, now: dt.datetime) -> None:
        tags = _tags(status=STATUS_PROMOTED, created_at="2026-01-01T00:00:00+00:00")
        assert not _is_eligible_for_cleanup(tags, now=now, retention_days=30)

    def test_discarded_skipped(self, now: dt.datetime) -> None:
        tags = _tags(status=STATUS_DISCARDED, created_at="2026-01-01T00:00:00+00:00")
        assert not _is_eligible_for_cleanup(tags, now=now, retention_days=30)

    def test_pre_promote_backup_skipped(self, now: dt.datetime) -> None:
        tags = _tags(
            created_at="2026-01-01T00:00:00+00:00",
            is_pre_promote_backup=True,
        )
        assert not _is_eligible_for_cleanup(tags, now=now, retention_days=30)


class TestCleanupOldBranches:
    def test_disabled_short_circuits(self) -> None:
        client = MagicMock()
        with patch.object(cleanup_mod, "list_catalogs_api") as mock_catalogs:
            summary = cleanup_old_branches(
                client=client,
                settings=_settings(enabled=False),
            )
        assert summary == {
            "deleted": 0,
            "skipped": 0,
            "errored": 0,
            "enabled": False,
        }
        mock_catalogs.sync.assert_not_called()

    def test_enabled_with_no_catalogs(self) -> None:
        client = MagicMock()
        with patch.object(cleanup_mod, "list_catalogs_api") as mock_catalogs:
            mock_catalogs.sync.return_value = None
            summary = cleanup_old_branches(
                client=client,
                settings=_settings(),
            )
        assert summary["enabled"] is True
        assert summary["deleted"] == 0

    def test_walks_and_discards_eligible_only(self) -> None:
        client = MagicMock()
        catalog = MagicMock()
        catalog.name = "playground"
        schema_old = MagicMock()
        schema_old.name = "branch_old"
        schema_young = MagicMock()
        schema_young.name = "branch_young"
        catalogs_response = MagicMock()
        catalogs_response.catalogs = [catalog]
        schemas_response = MagicMock()
        schemas_response.schemas = [schema_old, schema_young]

        old_tags = _tags(created_at="2026-01-01T00:00:00+00:00")
        young_tags = _tags(created_at="2026-04-29T00:00:00+00:00")

        def _fake_read(_client: Any, fqn: str) -> Any:
            if fqn == "playground.branch_old":
                return old_tags
            if fqn == "playground.branch_young":
                return young_tags
            return None

        with (
            patch.object(cleanup_mod, "list_catalogs_api") as mock_catalogs,
            patch.object(cleanup_mod, "list_schemas_api") as mock_schemas,
            patch(
                "pointlessql.services.branch_cleanup.branch_tags.read_branch_tags_sync",
                side_effect=_fake_read,
            ),
            patch("pointlessql.services.branch_cleanup.discard_branch_schema") as mock_discard,
        ):
            mock_catalogs.sync.return_value = catalogs_response
            mock_schemas.sync.return_value = schemas_response
            summary = cleanup_old_branches(
                client=client,
                settings=_settings(retention_days=30),
                now=dt.datetime(2026, 4, 30, 0, 0, tzinfo=dt.UTC),
            )

        assert summary["deleted"] == 1
        assert summary["skipped"] == 1
        assert summary["errored"] == 0
        mock_discard.assert_called_once()
        assert mock_discard.call_args.kwargs["branch_schema_fqn"] == "playground.branch_old"

    def test_discard_failure_counted_not_raised(self) -> None:
        client = MagicMock()
        catalog = MagicMock()
        catalog.name = "playground"
        schema = MagicMock()
        schema.name = "branch_old"
        catalogs_response = MagicMock()
        catalogs_response.catalogs = [catalog]
        schemas_response = MagicMock()
        schemas_response.schemas = [schema]

        from pointlessql.pql._branch_errors import BranchInUseError

        with (
            patch.object(cleanup_mod, "list_catalogs_api") as mock_catalogs,
            patch.object(cleanup_mod, "list_schemas_api") as mock_schemas,
            patch(
                "pointlessql.services.branch_cleanup.branch_tags.read_branch_tags_sync",
                return_value=_tags(created_at="2026-01-01T00:00:00+00:00"),
            ),
            patch(
                "pointlessql.services.branch_cleanup.discard_branch_schema",
                side_effect=BranchInUseError("nope"),
            ),
        ):
            mock_catalogs.sync.return_value = catalogs_response
            mock_schemas.sync.return_value = schemas_response
            summary = cleanup_old_branches(
                client=client,
                settings=_settings(retention_days=30),
                now=dt.datetime(2026, 4, 30, 0, 0, tzinfo=dt.UTC),
            )

        assert summary["errored"] == 1
        assert summary["deleted"] == 0
