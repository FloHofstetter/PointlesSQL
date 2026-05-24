"""Tests for the branch tag wrapper."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pointlessql.services import branch_tags as bt
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
def uc() -> UnityCatalogClient:
    """A UnityCatalogClient with mocked ``get_tags`` / ``update_tags``."""
    client = UnityCatalogClient(MagicMock())
    client.get_tags = AsyncMock()  # type: ignore[method-assign]
    client.update_tags = AsyncMock(return_value=[])  # type: ignore[method-assign]
    return client


def _as_tag_list(items: dict[str, Any]) -> list[dict[str, Any]]:
    """Shape a key->value mapping into the soyuz tag-dict response."""
    return [{"key": k, "value": v} for k, v in items.items()]


class TestApplyBranchTags:
    async def test_writes_full_initial_set(self, uc: UnityCatalogClient) -> None:
        await bt.apply_branch_tags(
            uc,
            "playground.bronze_branch_42",
            parent_schema="playground.bronze",
            parent_version_at_create={"events": 7, "users": 3},
            created_by_run_id="run-abc",
            strategy=bt.STRATEGY_SYMLINK,
            created_at="2026-04-29T12:00:00+00:00",
        )

        args, _ = uc.update_tags.call_args  # type: ignore[attr-defined]
        assert args[0] == "schema"
        assert args[1] == "playground.bronze_branch_42"

        changes = args[2]
        by_key = {c["key"]: c for c in changes}

        assert by_key[bt.TAG_PARENT_SCHEMA]["value"] == "playground.bronze"
        assert by_key[bt.TAG_STATUS]["value"] == bt.STATUS_ACTIVE
        assert by_key[bt.TAG_STRATEGY]["value"] == bt.STRATEGY_SYMLINK
        assert by_key[bt.TAG_CREATED_AT]["value"] == "2026-04-29T12:00:00+00:00"
        assert by_key[bt.TAG_CREATED_BY_RUN_ID]["value"] == "run-abc"

        decoded = json.loads(by_key[bt.TAG_PARENT_VERSION_AT_CREATE]["value"])
        assert decoded == {"events": 7, "users": 3}

    async def test_skips_run_id_when_none(self, uc: UnityCatalogClient) -> None:
        await bt.apply_branch_tags(
            uc,
            "playground.x",
            parent_schema="playground.y",
            parent_version_at_create={},
            created_by_run_id=None,
            strategy=bt.STRATEGY_DEEP_COPY,
        )

        args, _ = uc.update_tags.call_args  # type: ignore[attr-defined]
        changes = args[2]
        keys = {c["key"] for c in changes}
        assert bt.TAG_CREATED_BY_RUN_ID not in keys

    async def test_rejects_unknown_strategy(self, uc: UnityCatalogClient) -> None:
        with pytest.raises(ValueError, match="invalid strategy"):
            await bt.apply_branch_tags(
                uc,
                "playground.x",
                parent_schema="playground.y",
                parent_version_at_create={},
                created_by_run_id=None,
                strategy="hardlink",
            )


class TestReadBranchTags:
    async def test_returns_none_for_non_branch(self, uc: UnityCatalogClient) -> None:
        uc.get_tags.return_value = _as_tag_list({"env": "prod"})  # type: ignore[attr-defined]
        assert await bt.read_branch_tags(uc, "playground.bronze") is None

    async def test_returns_typed_tags_when_complete(self, uc: UnityCatalogClient) -> None:
        uc.get_tags.return_value = _as_tag_list(  # type: ignore[attr-defined]
            {
                bt.TAG_PARENT_SCHEMA: "playground.bronze",
                bt.TAG_PARENT_VERSION_AT_CREATE: json.dumps({"events": 5}),
                bt.TAG_CREATED_AT: "2026-04-29T12:00:00+00:00",
                bt.TAG_CREATED_BY_RUN_ID: "run-xyz",
                bt.TAG_STRATEGY: bt.STRATEGY_SYMLINK,
                bt.TAG_STATUS: bt.STATUS_ACTIVE,
            }
        )

        result = await bt.read_branch_tags(uc, "playground.bronze_branch")
        assert result is not None
        assert result.parent_schema == "playground.bronze"
        assert result.parent_version_at_create == {"events": 5}
        assert result.status == bt.STATUS_ACTIVE
        assert result.strategy == bt.STRATEGY_SYMLINK
        assert result.created_by_run_id == "run-xyz"
        assert result.is_pre_promote_backup is False

    async def test_raises_on_partial_tag_set(self, uc: UnityCatalogClient) -> None:
        uc.get_tags.return_value = _as_tag_list(  # type: ignore[attr-defined]
            {
                bt.TAG_PARENT_SCHEMA: "playground.bronze",
                bt.TAG_STATUS: bt.STATUS_ACTIVE,
            }
        )
        with pytest.raises(bt.BranchTagsCorruptError, match="missing keys"):
            await bt.read_branch_tags(uc, "playground.broken_branch")

    async def test_raises_on_invalid_status(self, uc: UnityCatalogClient) -> None:
        uc.get_tags.return_value = _as_tag_list(  # type: ignore[attr-defined]
            {
                bt.TAG_PARENT_SCHEMA: "playground.bronze",
                bt.TAG_PARENT_VERSION_AT_CREATE: "{}",
                bt.TAG_CREATED_AT: "2026-04-29T12:00:00+00:00",
                bt.TAG_STRATEGY: bt.STRATEGY_SYMLINK,
                bt.TAG_STATUS: "halfway",
            }
        )
        with pytest.raises(bt.BranchTagsCorruptError, match="not in"):
            await bt.read_branch_tags(uc, "playground.broken_branch")

    async def test_raises_on_malformed_version_json(self, uc: UnityCatalogClient) -> None:
        uc.get_tags.return_value = _as_tag_list(  # type: ignore[attr-defined]
            {
                bt.TAG_PARENT_SCHEMA: "playground.bronze",
                bt.TAG_PARENT_VERSION_AT_CREATE: "{not json",
                bt.TAG_CREATED_AT: "2026-04-29T12:00:00+00:00",
                bt.TAG_STRATEGY: bt.STRATEGY_SYMLINK,
                bt.TAG_STATUS: bt.STATUS_ACTIVE,
            }
        )
        with pytest.raises(bt.BranchTagsCorruptError, match="not valid JSON"):
            await bt.read_branch_tags(uc, "playground.broken_branch")

    async def test_recognises_pre_promote_backup_tag(self, uc: UnityCatalogClient) -> None:
        uc.get_tags.return_value = _as_tag_list(  # type: ignore[attr-defined]
            {
                bt.TAG_PARENT_SCHEMA: "playground.bronze",
                bt.TAG_PARENT_VERSION_AT_CREATE: json.dumps({"events": 1}),
                bt.TAG_CREATED_AT: "2026-04-29T12:00:00+00:00",
                bt.TAG_STRATEGY: bt.STRATEGY_SYMLINK,
                bt.TAG_STATUS: bt.STATUS_PROMOTED,
                bt.TAG_PROMOTED_AT: "2026-04-29T13:00:00+00:00",
                bt.TAG_IS_PRE_PROMOTE_BACKUP: "true",
            }
        )
        result = await bt.read_branch_tags(uc, "playground.bronze_pre_promote_X")
        assert result is not None
        assert result.is_pre_promote_backup is True
        assert result.status == bt.STATUS_PROMOTED
        assert result.promoted_at == "2026-04-29T13:00:00+00:00"


class TestSetBranchStatus:
    async def test_promoted_writes_promoted_at(self, uc: UnityCatalogClient) -> None:
        await bt.set_branch_status(
            uc, "p.b_branch", bt.STATUS_PROMOTED, timestamp="2026-04-29T14:00:00+00:00"
        )
        args, _ = uc.update_tags.call_args  # type: ignore[attr-defined]
        by_key = {c["key"]: c for c in args[2]}
        assert by_key[bt.TAG_STATUS]["value"] == bt.STATUS_PROMOTED
        assert by_key[bt.TAG_PROMOTED_AT]["value"] == "2026-04-29T14:00:00+00:00"
        assert bt.TAG_DISCARDED_AT not in by_key

    async def test_discarded_writes_discarded_at(self, uc: UnityCatalogClient) -> None:
        await bt.set_branch_status(
            uc, "p.b_branch", bt.STATUS_DISCARDED, timestamp="2026-04-29T15:00:00+00:00"
        )
        args, _ = uc.update_tags.call_args  # type: ignore[attr-defined]
        by_key = {c["key"]: c for c in args[2]}
        assert by_key[bt.TAG_STATUS]["value"] == bt.STATUS_DISCARDED
        assert by_key[bt.TAG_DISCARDED_AT]["value"] == "2026-04-29T15:00:00+00:00"

    async def test_active_clears_terminal_timestamps(self, uc: UnityCatalogClient) -> None:
        await bt.set_branch_status(uc, "p.b_branch", bt.STATUS_ACTIVE)
        args, _ = uc.update_tags.call_args  # type: ignore[attr-defined]
        ops = {(c["key"], c["op"]) for c in args[2]}
        assert (bt.TAG_PROMOTED_AT, "remove") in ops
        assert (bt.TAG_DISCARDED_AT, "remove") in ops

    async def test_rejects_unknown_status(self, uc: UnityCatalogClient) -> None:
        with pytest.raises(ValueError, match="invalid status"):
            await bt.set_branch_status(uc, "p.b_branch", "deleted")


class TestMarkPrePromoteBackup:
    async def test_writes_backup_tag(self, uc: UnityCatalogClient) -> None:
        await bt.mark_pre_promote_backup(uc, "playground.bronze_pre_promote_X")
        args, _ = uc.update_tags.call_args  # type: ignore[attr-defined]
        by_key = {c["key"]: c for c in args[2]}
        assert by_key[bt.TAG_IS_PRE_PROMOTE_BACKUP]["value"] == "true"
