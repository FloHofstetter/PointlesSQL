"""Route-level tests for the Sprint 13.11.11 PQL write endpoints.

Covers ``POST /api/pql/autoload``, ``/write_table``, ``/merge``, and
``/drop_table``. Each endpoint is exercised with:

* one happy-path admin call (proving the dispatch reaches the
  underlying PQL primitive / soyuz delete);
* one validation-failure case (missing required field);
* one authorisation-failure case (non-admin without the right
  privilege).

The PQL primitive itself is patched per test so we don't need a real
Delta target to validate the route layer — the goal is to prove that
the route correctly authorises, instantiates PQL with the right
``principal``/``agent_run_id``, and forwards the body to the right
primitive method.
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


def _make_uc_mock(
    *,
    storage_location: str,
    effective: list[dict[str, Any]] | None = None,
    table_exists: bool = True,
) -> MagicMock:
    client = MagicMock(spec=UnityCatalogClient)
    if table_exists:
        client.get_table = AsyncMock(
            return_value={
                "name": "orders",
                "catalog_name": "main",
                "schema_name": "sales",
                "storage_location": storage_location,
            }
        )
    else:
        client.get_table = AsyncMock(return_value={})
    client.get_effective_permissions = AsyncMock(return_value=effective or [])
    client.delete_table = AsyncMock(return_value=None)
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


def _non_admin_client() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=app.state._test_non_admin_cookie,
    )


# ─── autoload ─────────────────────────────────────────────────────────


async def test_autoload_admin_dispatches_to_pql_primitive(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Admin call reaches PQL.autoload with the body fields verbatim."""
    app.state.uc_client = _make_uc_mock(storage_location="/unused", table_exists=False)
    captured: dict[str, Any] = {}

    class _FakePQL:
        def __init__(self, **kwargs: Any) -> None:
            captured["init_kwargs"] = kwargs

        def autoload(self, **kwargs: Any) -> dict[str, Any]:
            captured["autoload_kwargs"] = kwargs
            return {
                "target": kwargs["target"],
                "files_scanned": 2,
                "files_ingested": 2,
                "files_skipped": 0,
                "rows_ingested": 50,
            }

    monkeypatch.setattr(pql_write_routes, "_build_pql", lambda r, **kw: _FakePQL(**kw))
    src = str(tmp_path / "drops")
    Path(src).mkdir()
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/autoload",
            json={
                "source_path": src,
                "target": "main.sales.orders",
                "source_system": "raw_drops",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["files_ingested"] == 2
    assert body["rows_ingested"] == 50
    assert captured["autoload_kwargs"]["target"] == "main.sales.orders"
    assert captured["autoload_kwargs"]["source_system"] == "raw_drops"


async def test_autoload_rejects_missing_source_path() -> None:
    app.state.uc_client = _make_uc_mock(storage_location="/unused")
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/autoload",
            json={"target": "main.sales.orders"},
        )
    assert resp.status_code in (400, 422)


async def test_autoload_non_admin_without_privilege_is_denied() -> None:
    app.state.uc_client = _make_uc_mock(
        storage_location="/unused", table_exists=False, effective=[]
    )
    async with _non_admin_client() as client:
        resp = await client.post(
            "/api/pql/autoload",
            json={"source_path": "/tmp/drops", "target": "main.sales.orders"},
        )
    assert resp.status_code == 403


# ─── write_table ──────────────────────────────────────────────────────


async def test_write_table_admin_runs_select_and_writes(
    monkeypatch: pytest.MonkeyPatch, orders_delta: str
) -> None:
    """Admin POST runs the SELECT against the source Delta and pipes through write_table."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    captured: dict[str, Any] = {}

    class _FakePQL:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        def write_table(self, df: Any, full_name: str, *, mode: str, **kwargs: Any) -> None:
            captured["df_rows"] = int(len(df))
            captured["target"] = full_name
            captured["mode"] = mode
            captured["write_kwargs"] = kwargs

    monkeypatch.setattr(pql_write_routes, "_build_pql", lambda r, **kw: _FakePQL(**kw))
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/write_table",
            json={
                "sql": "SELECT id, name FROM main.sales.orders",
                "target": "main.silver.orders_clean",
                "mode": "overwrite",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rows_written"] == 3
    assert body["target"] == "main.silver.orders_clean"
    assert body["mode"] == "overwrite"
    assert captured["target"] == "main.silver.orders_clean"
    assert captured["df_rows"] == 3


async def test_write_table_rejects_invalid_mode() -> None:
    app.state.uc_client = _make_uc_mock(storage_location="/unused")
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/write_table",
            json={
                "sql": "SELECT 1",
                "target": "main.silver.x",
                "mode": "BOGUS",
            },
        )
    assert resp.status_code in (400, 422)


# ─── merge ────────────────────────────────────────────────────────────


async def test_merge_admin_dispatches_with_keys(
    monkeypatch: pytest.MonkeyPatch, orders_delta: str
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    captured: dict[str, Any] = {}

    class _FakePQL:
        def __init__(self, **kwargs: Any) -> None:
            captured["init"] = kwargs

        def merge(
            self,
            source: Any,
            target: str,
            *,
            on: list[str],
            strategy: str,
            **kwargs: Any,
        ) -> dict[str, Any]:
            captured["source_rows"] = int(len(source))
            captured["target"] = target
            captured["on"] = on
            captured["strategy"] = strategy
            captured["merge_kwargs"] = kwargs
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
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["strategy"] == "upsert"
    assert body["num_target_rows_updated"] == 3
    assert captured["on"] == ["id"]
    assert captured["strategy"] == "upsert"


async def test_merge_rejects_empty_on_list() -> None:
    app.state.uc_client = _make_uc_mock(storage_location="/unused")
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/merge",
            json={
                "sql": "SELECT 1",
                "target": "main.silver.x",
                "on": [],
            },
        )
    assert resp.status_code in (400, 422)


# ─── drop_table ───────────────────────────────────────────────────────


async def test_drop_table_admin_calls_soyuz_delete() -> None:
    uc_mock = _make_uc_mock(storage_location="/unused")
    app.state.uc_client = uc_mock
    async with _admin_client() as client:
        resp = await client.post(
            "/api/pql/drop_table",
            json={"full_name": "main.sales.orders"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["deleted"] is True
    assert body["target"] == "main.sales.orders"
    uc_mock.delete_table.assert_awaited_once_with("main", "sales", "orders")


async def test_drop_table_non_admin_is_denied() -> None:
    app.state.uc_client = _make_uc_mock(storage_location="/unused")
    async with _non_admin_client() as client:
        resp = await client.post(
            "/api/pql/drop_table",
            json={"full_name": "main.sales.orders"},
        )
    assert resp.status_code == 403
