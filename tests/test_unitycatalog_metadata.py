"""Unit tests for the schema/table/tag UC mixin wrapper logic.

Same approach as the catalog/model wrapper tests: host ``MetadataMixin``
on a stub and monkeypatch each generated endpoint's ``.asyncio`` coroutine
so the type guards, ``.to_dict()`` projection, and empty-body fallbacks
are exercised without a live catalog.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from soyuz_catalog_client.models.list_schemas_response import ListSchemasResponse
from soyuz_catalog_client.models.schema_info import SchemaInfo
from soyuz_catalog_client.models.tag_list import TagList

from pointlessql.services.unitycatalog import _metadata as mod
from pointlessql.services.unitycatalog._metadata import MetadataMixin


class _Meta(MetadataMixin):
    def __init__(self) -> None:
        self._client = object()


def _row(**kw: Any) -> SimpleNamespace:
    return SimpleNamespace(to_dict=lambda: kw)


# --- get_schema / get_table ----------------------------------------------


async def test_get_schema_maps_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._get_schema, "asyncio", AsyncMock(return_value=_row(name="s")))
    assert await _Meta().get_schema("c", "s") == {"name": "s"}


async def test_get_schema_none_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._get_schema, "asyncio", AsyncMock(return_value=None))
    assert await _Meta().get_schema("c", "s") == {}


async def test_get_table_none_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._get_table, "asyncio", AsyncMock(return_value=None))
    assert await _Meta().get_table("c", "s", "t") == {}


# --- list_schemas ---------------------------------------------------------


async def test_list_schemas_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = ListSchemasResponse(schemas=[_row(name="a"), _row(name="b")])
    monkeypatch.setattr(mod._list_schemas, "asyncio", AsyncMock(return_value=resp))
    assert await _Meta().list_schemas("c") == [{"name": "a"}, {"name": "b"}]


async def test_list_schemas_wrong_type_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._list_schemas, "asyncio", AsyncMock(return_value=None))
    assert await _Meta().list_schemas("c") == []


# --- create_schema --------------------------------------------------------


async def test_create_schema_returns_created(monkeypatch: pytest.MonkeyPatch) -> None:
    created = SchemaInfo.from_dict({"name": "s", "catalog_name": "c"})
    monkeypatch.setattr(mod._create_schema, "asyncio", AsyncMock(return_value=created))
    out = await _Meta().create_schema({"name": "s", "catalog_name": "c"})
    assert out.get("name") == "s"


async def test_create_schema_wrong_type_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._create_schema, "asyncio", AsyncMock(return_value=None))
    assert await _Meta().create_schema({"name": "s", "catalog_name": "c"}) == {}


# --- delete_table ---------------------------------------------------------


async def test_delete_table_forwards_full_name(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = AsyncMock(return_value=None)
    monkeypatch.setattr(mod._delete_table, "asyncio", spy)
    await _Meta().delete_table("c", "s", "t")
    assert spy.await_args.kwargs["full_name"] == "c.s.t"


# --- tags -----------------------------------------------------------------


async def test_get_tags_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = TagList(tags=[_row(key="pii", value="true")])
    monkeypatch.setattr(mod._get_tags, "asyncio", AsyncMock(return_value=resp))
    out = await _Meta().get_tags("table", "c.s.t")
    assert out == [{"key": "pii", "value": "true"}]


async def test_get_tags_wrong_type_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._get_tags, "asyncio", AsyncMock(return_value=None))
    assert await _Meta().get_tags("table", "c.s.t") == []
