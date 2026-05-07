"""Sprint 21.5.1 — Tree extension surfaces RegisteredModels per schema.

Mocks the ``ModelsMixin`` ``list_registered_models`` call so tests run
without a live soyuz instance.  The contract under test is the
``UnityCatalogClient.get_tree()`` shape and the ``/api/tree/search``
matcher honouring ``kind="model"``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest

from pointlessql.api.main import app


@pytest.fixture
def uc_with_models(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    # Force ``get_uc_client`` to fall through to ``app.state.uc_client``
    # by suppressing the per-request principal client construction.
    monkeypatch.setattr(
        "pointlessql.api.dependencies.effective_principal",
        lambda request: None,
    )
    mock = AsyncMock()

    async def _list_catalogs():
        return [{"name": "cat1"}]

    async def _list_schemas(catalog_name):
        if catalog_name == "cat1":
            return [{"name": "sch1"}]
        return []

    async def _list_tables(catalog_name, schema_name):
        return [{"name": "tbl_users"}]

    async def _list_registered_models(
        catalog_name=None, schema_name=None, max_results=None, page_token=None
    ):
        return [{"name": "smoke_model", "full_name": "cat1.sch1.smoke_model"}]

    async def _get_tree():
        # Mirror real behaviour of CatalogsMixin.get_tree() so we can
        # verify the side-by-side tables+models shape.
        catalogs = await _list_catalogs()
        out = []
        for cat in catalogs:
            schemas = await _list_schemas(cat["name"])
            sout = []
            for sch in schemas:
                tables = await _list_tables(cat["name"], sch["name"])
                models = await _list_registered_models(
                    catalog_name=cat["name"], schema_name=sch["name"]
                )
                sout.append({**sch, "tables": tables, "models": models})
            out.append({**cat, "schemas": sout})
        return out

    mock.list_catalogs.side_effect = _list_catalogs
    mock.list_schemas.side_effect = _list_schemas
    mock.list_tables.side_effect = _list_tables
    mock.list_registered_models.side_effect = _list_registered_models
    mock.get_tree.side_effect = _get_tree

    app.state.uc_client = mock
    return mock


@pytest.mark.asyncio
async def test_api_tree_includes_models_per_schema(
    uc_with_models: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    resp = await admin_client.get("/api/tree")
    assert resp.status_code == 200
    body = resp.json()
    assert body[0]["name"] == "cat1"
    schema = body[0]["schemas"][0]
    assert schema["name"] == "sch1"
    assert any(t["name"] == "tbl_users" for t in schema["tables"])
    assert any(m["name"] == "smoke_model" for m in schema["models"])


@pytest.mark.asyncio
async def test_tree_search_finds_models_by_substring(
    uc_with_models: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    resp = await admin_client.get("/api/tree/search?q=smoke")
    assert resp.status_code == 200
    body = resp.json()
    matches = body["matches"]
    assert any(m["kind"] == "model" and m["full_name"] == "cat1.sch1.smoke_model" for m in matches)


@pytest.mark.asyncio
async def test_tree_search_does_not_match_table_when_only_model_matches(
    uc_with_models: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    resp = await admin_client.get("/api/tree/search?q=smoke_model")
    assert resp.status_code == 200
    body = resp.json()
    kinds = {m["kind"] for m in body["matches"]}
    # Only the model row matches that exact name; tables and schemas
    # don't contain ``smoke_model`` substring.
    assert "model" in kinds
    assert "table" not in kinds
