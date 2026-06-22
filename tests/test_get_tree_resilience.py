"""get_tree degrades a failing schema and bounds its fan-out.

A 5xx/timeout listing one schema's children must not abort the whole
sidebar tree, and a wide catalog must not stampede soyuz with thousands
of concurrent GETs.  These tests pin both behaviours.
"""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from pointlessql.exceptions import CatalogUnavailableError
from pointlessql.services.unitycatalog import UnityCatalogClient


def _uc() -> UnityCatalogClient:
    """A UnityCatalogClient whose leaf list_* methods we override per test."""
    return UnityCatalogClient(MagicMock())


@pytest.mark.asyncio
async def test_failing_schema_degrades_to_partial_node() -> None:
    """One schema's children failing yields an empty partial node, not an abort."""
    uc = _uc()
    uc.list_catalogs = AsyncMock(return_value=[{"name": "cat"}])  # type: ignore[method-assign]
    uc.list_schemas = AsyncMock(return_value=[{"name": "good"}, {"name": "bad"}])  # type: ignore[method-assign]
    uc.list_volumes = AsyncMock(return_value=[])  # type: ignore[method-assign]
    uc.list_registered_models = AsyncMock(return_value=[])  # type: ignore[method-assign]

    async def _tables(catalog: str, schema: str) -> list[dict[str, Any]]:
        if schema == "bad":
            raise CatalogUnavailableError("soyuz down")
        return [{"name": "t1"}]

    uc.list_tables = AsyncMock(side_effect=_tables)  # type: ignore[method-assign]

    tree = await uc.get_tree()
    schemas = {s["name"]: s for s in tree[0]["schemas"]}
    assert schemas["good"]["tables"] == [{"name": "t1"}]
    assert "partial" not in schemas["good"]
    assert schemas["bad"]["tables"] == []
    assert schemas["bad"]["partial"] is True


@pytest.mark.asyncio
async def test_fan_out_is_bounded_by_setting(
    settings_override: Callable[[str, object], None],
) -> None:
    """No more than tree_fanout_concurrency schemas fetch children at once."""
    settings_override("soyuz.tree_fanout_concurrency", 2)
    uc = _uc()
    uc.list_catalogs = AsyncMock(return_value=[{"name": "cat"}])  # type: ignore[method-assign]
    uc.list_schemas = AsyncMock(  # type: ignore[method-assign]
        return_value=[{"name": f"s{i}"} for i in range(8)]
    )
    uc.list_volumes = AsyncMock(return_value=[])  # type: ignore[method-assign]
    uc.list_registered_models = AsyncMock(return_value=[])  # type: ignore[method-assign]

    active = 0
    peak = 0

    async def _tables(catalog: str, schema: str) -> list[dict[str, Any]]:
        nonlocal active, peak
        active += 1
        peak = max(peak, active)
        await asyncio.sleep(0.01)
        active -= 1
        return []

    uc.list_tables = AsyncMock(side_effect=_tables)  # type: ignore[method-assign]

    await uc.get_tree()
    assert peak <= 2
