"""Sprint 21.8 — HTTP-side ``source_model_uri`` propagation tests.

The existing :mod:`tests.test_pql_write_routes` covers the happy
path; these tests pin the new optional field, the auto-derive of
``source_table_fqn`` from a single-ref SELECT, and the validation
shape so a malformed request yields a 4xx.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest

from pointlessql.api import pql_write_routes
from pointlessql.api.main import app
from pointlessql.services.unitycatalog import UnityCatalogClient


def _uc_mock(storage_location: str) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": storage_location,
        }
    )
    client.get_effective_permissions = AsyncMock(return_value=[])
    return client


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


@pytest.fixture
def orders_delta(tmp_path: Path) -> str:
    loc = str(tmp_path / "orders")
    df = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    deltalake.write_deltalake(loc, df)
    return loc


def _admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_auth_cookie,
    )


async def test_write_table_threads_source_model_uri(
    monkeypatch: pytest.MonkeyPatch, orders_delta: str
) -> None:
    """Setting ``source_model_uri`` propagates to ``pql.write_table``."""
    app.state.uc_client = _uc_mock(orders_delta)
    captured: dict[str, Any] = {}

    class _FakePQL:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        def write_table(
            self, df: Any, full_name: str, *, mode: str, **kwargs: Any
        ) -> None:
            captured["target"] = full_name
            captured["mode"] = mode
            captured["kwargs"] = kwargs

    monkeypatch.setattr(pql_write_routes, "_build_pql", lambda r, **kw: _FakePQL(**kw))
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/write_table",
            json={
                "sql": "SELECT id, name FROM main.sales.orders",
                "target": "main.gold.preds_v2",
                "mode": "overwrite",
                "source_model_uri": "models:/main.fraud.classifier/3",
            },
        )
    assert resp.status_code == 200, resp.text
    assert captured["kwargs"]["source_model_uri"] == "models:/main.fraud.classifier/3"
    # Single-ref SELECT auto-derives ``source_table_fqn`` so the
    # row-edge grain has somewhere to anchor.
    assert captured["kwargs"]["source_table_fqn"] == "main.sales.orders"


async def test_write_table_rejects_blank_source_model_uri(
    monkeypatch: pytest.MonkeyPatch, orders_delta: str
) -> None:
    """An empty / whitespace-only ``source_model_uri`` is a 400."""
    app.state.uc_client = _uc_mock(orders_delta)

    class _FakePQL:
        def __init__(self, **kwargs: Any) -> None: ...
        def write_table(
            self, df: Any, full_name: str, *, mode: str, **kwargs: Any
        ) -> None: ...

    monkeypatch.setattr(pql_write_routes, "_build_pql", lambda r, **kw: _FakePQL(**kw))
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/write_table",
            json={
                "sql": "SELECT id FROM main.sales.orders",
                "target": "main.gold.preds_v2",
                "mode": "overwrite",
                "source_model_uri": "   ",
            },
        )
    assert resp.status_code in (400, 422)


async def test_merge_threads_source_model_uri(
    monkeypatch: pytest.MonkeyPatch, orders_delta: str
) -> None:
    """``POST /api/pql/merge`` passes ``source_model_uri`` to ``PQL.merge``."""
    app.state.uc_client = _uc_mock(orders_delta)
    captured: dict[str, Any] = {}

    class _FakePQL:
        def __init__(self, **kwargs: Any) -> None: ...

        def merge(
            self,
            source: Any,
            target: str,
            *,
            on: list[str],
            strategy: str,
            **kwargs: Any,
        ) -> dict[str, Any]:
            captured["target"] = target
            captured["on"] = on
            captured["strategy"] = strategy
            captured["kwargs"] = kwargs
            return {
                "strategy": strategy,
                "num_target_rows_inserted": 0,
                "num_target_rows_updated": 3,
            }

    monkeypatch.setattr(pql_write_routes, "_build_pql", lambda r, **kw: _FakePQL(**kw))
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/merge",
            json={
                "sql": "SELECT id, name FROM main.sales.orders",
                "target": "main.silver.orders",
                "on": ["id"],
                "source_model_uri": "models:/main.fraud.classifier/4",
            },
        )
    assert resp.status_code == 200, resp.text
    assert captured["kwargs"]["source_model_uri"] == "models:/main.fraud.classifier/4"
    assert captured["kwargs"]["source_table_fqn"] == "main.sales.orders"
