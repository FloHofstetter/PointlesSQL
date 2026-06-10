"""Unit tests for the catalog-CRUD UC mixin wrapper logic.

The conftest UC fixture mocks the whole ``UnityCatalogClient``, so the real
wrapper code in ``_catalogs.py`` (type guards, ``.to_dict()`` projection,
empty-body fallbacks, request-body construction) is otherwise unexercised.
These tests host ``CatalogsMixin`` on a stub and monkeypatch each generated
endpoint's ``.asyncio`` coroutine. ``asyncio_mode = auto`` — no markers.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from soyuz_catalog_client.models.catalog_info import CatalogInfo
from soyuz_catalog_client.models.list_catalogs_response import ListCatalogsResponse

from pointlessql.services.unitycatalog import _catalogs as mod
from pointlessql.services.unitycatalog._catalogs import CatalogsMixin


class _Catalogs(CatalogsMixin):
    def __init__(self) -> None:
        self._client = object()


def _row(**kw: Any) -> SimpleNamespace:
    return SimpleNamespace(to_dict=lambda: kw)


# --- list_catalogs --------------------------------------------------------


async def test_list_catalogs_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = ListCatalogsResponse(catalogs=[_row(name="main"), _row(name="other")])
    monkeypatch.setattr(mod._list_catalogs, "asyncio", AsyncMock(return_value=resp))
    assert await _Catalogs().list_catalogs() == [{"name": "main"}, {"name": "other"}]


async def test_list_catalogs_wrong_type_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._list_catalogs, "asyncio", AsyncMock(return_value=None))
    assert await _Catalogs().list_catalogs() == []


async def test_list_catalogs_non_list_payload_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = ListCatalogsResponse(catalogs=None)  # type: ignore[arg-type]
    monkeypatch.setattr(mod._list_catalogs, "asyncio", AsyncMock(return_value=resp))
    assert await _Catalogs().list_catalogs() == []


# --- get_catalog ----------------------------------------------------------


async def test_get_catalog_maps_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._get_catalog, "asyncio", AsyncMock(return_value=_row(name="main")))
    assert await _Catalogs().get_catalog("main") == {"name": "main"}


async def test_get_catalog_none_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._get_catalog, "asyncio", AsyncMock(return_value=None))
    assert await _Catalogs().get_catalog("main") == {}


# --- create_catalog -------------------------------------------------------


async def test_create_catalog_returns_created(monkeypatch: pytest.MonkeyPatch) -> None:
    created = CatalogInfo.from_dict({"name": "fresh"})
    monkeypatch.setattr(mod._create_catalog, "asyncio", AsyncMock(return_value=created))
    out = await _Catalogs().create_catalog({"name": "fresh"})
    assert out.get("name") == "fresh"


async def test_create_catalog_wrong_type_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._create_catalog, "asyncio", AsyncMock(return_value=None))
    assert await _Catalogs().create_catalog({"name": "x"}) == {}


# --- delete_catalog -------------------------------------------------------


async def test_delete_catalog_forwards_force(monkeypatch: pytest.MonkeyPatch) -> None:
    spy = AsyncMock(return_value=None)
    monkeypatch.setattr(mod._delete_catalog, "asyncio", spy)
    await _Catalogs().delete_catalog("main", force=True)
    assert spy.await_args.kwargs["force"] is True
    assert spy.await_args.kwargs["name"] == "main"


# --- update_catalog -------------------------------------------------------


async def test_update_catalog_maps_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._update_catalog, "asyncio", AsyncMock(return_value=_row(comment="hi")))
    assert await _Catalogs().update_catalog("main", {"comment": "hi"}) == {"comment": "hi"}


async def test_update_catalog_none_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._update_catalog, "asyncio", AsyncMock(return_value=None))
    assert await _Catalogs().update_catalog("main", {"comment": "x"}) == {}
