"""Unit tests for tags and permissions facade methods."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
def uc_client() -> UnityCatalogClient:
    """Return a UnityCatalogClient backed by a mock soyuz client."""
    mock = MagicMock()
    return UnityCatalogClient(mock)


class TestGetTags:
    async def test_returns_tag_dicts(self, uc_client: UnityCatalogClient) -> None:
        tag_entry = MagicMock()
        tag_entry.to_dict.return_value = {"key": "env", "value": "prod"}
        tag_list = MagicMock()
        tag_list.tags = [tag_entry]

        with patch(
            "pointlessql.services.unitycatalog._get_tags.asyncio",
            new_callable=AsyncMock,
            return_value=tag_list,
        ):
            from soyuz_catalog_client.models.tag_list import TagList

            tag_list.__class__ = TagList
            result = await uc_client.get_tags("catalog", "my_catalog")

        assert result == [{"key": "env", "value": "prod"}]

    async def test_returns_empty_on_none(self, uc_client: UnityCatalogClient) -> None:
        with patch(
            "pointlessql.services.unitycatalog._get_tags.asyncio",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await uc_client.get_tags("catalog", "my_catalog")

        assert result == []


class TestUpdateTags:
    async def test_sends_changes_and_returns(self, uc_client: UnityCatalogClient) -> None:
        tag_entry = MagicMock()
        tag_entry.to_dict.return_value = {"key": "env", "value": "staging"}
        tag_list = MagicMock()
        tag_list.tags = [tag_entry]

        with patch(
            "pointlessql.services.unitycatalog._update_tags.asyncio",
            new_callable=AsyncMock,
            return_value=tag_list,
        ):
            from soyuz_catalog_client.models.tag_list import TagList

            tag_list.__class__ = TagList
            result = await uc_client.update_tags(
                "catalog",
                "my_catalog",
                [{"key": "env", "op": "set", "value": "staging"}],
            )

        assert result == [{"key": "env", "value": "staging"}]


class TestGetPermissions:
    async def test_returns_assignments(self, uc_client: UnityCatalogClient) -> None:
        assignment = MagicMock()
        assignment.to_dict.return_value = {
            "principal": "admin",
            "privileges": ["SELECT"],
        }
        perm_list = MagicMock()
        perm_list.privilege_assignments = [assignment]

        with patch(
            "pointlessql.services.unitycatalog._get_permissions.asyncio",
            new_callable=AsyncMock,
            return_value=perm_list,
        ):
            from soyuz_catalog_client.models.permissions_list import (
                PermissionsList,
            )

            perm_list.__class__ = PermissionsList
            result = await uc_client.get_permissions("catalog", "my_catalog")

        assert result == [{"principal": "admin", "privileges": ["SELECT"]}]

    async def test_returns_empty_on_none(self, uc_client: UnityCatalogClient) -> None:
        with patch(
            "pointlessql.services.unitycatalog._get_permissions.asyncio",
            new_callable=AsyncMock,
            return_value=None,
        ):
            result = await uc_client.get_permissions("catalog", "my_catalog")

        assert result == []


class TestGetEffectivePermissions:
    async def test_returns_effective(self, uc_client: UnityCatalogClient) -> None:
        assignment = MagicMock()
        assignment.to_dict.return_value = {
            "principal": "user1",
            "privileges": ["SELECT", "USE CATALOG"],
        }
        perm_list = MagicMock()
        perm_list.privilege_assignments = [assignment]

        with patch(
            "pointlessql.services.unitycatalog._get_effective_permissions.asyncio",
            new_callable=AsyncMock,
            return_value=perm_list,
        ):
            from soyuz_catalog_client.models.permissions_list import (
                PermissionsList,
            )

            perm_list.__class__ = PermissionsList
            result = await uc_client.get_effective_permissions("catalog", "my_catalog")

        assert len(result) == 1
        assert result[0]["principal"] == "user1"


class TestGetLineage:
    async def test_returns_combined(self, uc_client: UnityCatalogClient) -> None:
        from soyuz_catalog_client.models.lineage_graph_response import (
            LineageGraphResponse,
        )

        upstream = MagicMock(spec=LineageGraphResponse)
        upstream.to_dict.return_value = {
            "direction": "upstream",
            "root": "cat.sch.tbl",
            "nodes": [],
            "edges": [],
        }
        downstream = MagicMock(spec=LineageGraphResponse)
        downstream.to_dict.return_value = {
            "direction": "downstream",
            "root": "cat.sch.tbl",
            "nodes": [],
            "edges": [],
        }

        with (
            patch(
                "pointlessql.services.unitycatalog._get_upstream.asyncio",
                new_callable=AsyncMock,
                return_value=upstream,
            ),
            patch(
                "pointlessql.services.unitycatalog._get_downstream.asyncio",
                new_callable=AsyncMock,
                return_value=downstream,
            ),
        ):
            result = await uc_client.get_lineage("cat.sch.tbl")

        assert "upstream" in result
        assert "downstream" in result
        assert result["upstream"]["direction"] == "upstream"
