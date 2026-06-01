"""Unit tests for the registered-model / model-version UC mixin.

``ModelsMixin`` wraps the generated soyuz client. The tests host the
mixin on a tiny class carrying a sentinel ``_client`` and monkeypatch
each generated endpoint's ``.asyncio`` coroutine, so the mapping logic
(type guards, ``.to_dict()`` projection, empty-body fallbacks, patch-body
construction) is covered without a live catalog. ``asyncio_mode = auto``
means the coroutine tests need no marker.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest
from soyuz_catalog_client.models.list_model_versions_response import (
    ListModelVersionsResponse,
)
from soyuz_catalog_client.models.list_registered_models_response import (
    ListRegisteredModelsResponse,
)

from pointlessql.services.unitycatalog import _models as mod
from pointlessql.services.unitycatalog._models import ModelsMixin


class _Models(ModelsMixin):
    def __init__(self) -> None:
        self._client = object()


def _row(**kw: Any) -> SimpleNamespace:
    return SimpleNamespace(to_dict=lambda: kw)


# --- list_registered_models ----------------------------------------------


async def test_list_registered_models_projects_to_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = ListRegisteredModelsResponse(registered_models=[_row(name="m1"), _row(name="m2")])
    monkeypatch.setattr(mod._list_rm, "asyncio", AsyncMock(return_value=resp))
    out = await _Models().list_registered_models(catalog_name="c", schema_name="s")
    assert out == [{"name": "m1"}, {"name": "m2"}]


async def test_list_registered_models_wrong_type_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod._list_rm, "asyncio", AsyncMock(return_value=None))
    assert await _Models().list_registered_models() == []


async def test_list_registered_models_non_list_payload_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    resp = ListRegisteredModelsResponse(registered_models=None)  # type: ignore[arg-type]
    monkeypatch.setattr(mod._list_rm, "asyncio", AsyncMock(return_value=resp))
    assert await _Models().list_registered_models() == []


# --- get_registered_model ------------------------------------------------


async def test_get_registered_model_maps_body(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._get_rm, "asyncio", AsyncMock(return_value=_row(name="m")))
    assert await _Models().get_registered_model("c.s.m") == {"name": "m"}


async def test_get_registered_model_none_is_empty_dict(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod._get_rm, "asyncio", AsyncMock(return_value=None))
    assert await _Models().get_registered_model("c.s.m") == {}


# --- list_model_versions -------------------------------------------------


async def test_list_model_versions_projects(monkeypatch: pytest.MonkeyPatch) -> None:
    resp = ListModelVersionsResponse(model_versions=[_row(version=1), _row(version=2)])
    monkeypatch.setattr(mod._list_mv, "asyncio", AsyncMock(return_value=resp))
    out = await _Models().list_model_versions("c.s.m", max_results=10)
    assert out == [{"version": 1}, {"version": 2}]


async def test_list_model_versions_wrong_type_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod._list_mv, "asyncio", AsyncMock(return_value="nope"))
    assert await _Models().list_model_versions("c.s.m") == []


# --- get_model_version ---------------------------------------------------


async def test_get_model_version_none_is_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(mod._get_mv, "asyncio", AsyncMock(return_value=None))
    assert await _Models().get_model_version("c.s.m", 3) == {}


# --- update_registered_model ---------------------------------------------


async def test_update_registered_model_builds_patch_body(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    async def _fake(*, full_name: str, client: Any, body: Any) -> Any:
        captured["comment"] = body.comment
        captured["new_name"] = body.new_name
        return _row(name="renamed", comment="hello")

    monkeypatch.setattr(mod._update_rm, "asyncio", _fake)
    out = await _Models().update_registered_model("c.s.m", comment="hello", new_name="renamed")
    assert out == {"name": "renamed", "comment": "hello"}
    assert captured == {"comment": "hello", "new_name": "renamed"}


async def test_update_registered_model_none_is_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(mod._update_rm, "asyncio", AsyncMock(return_value=None))
    assert await _Models().update_registered_model("c.s.m", comment="x") == {}
