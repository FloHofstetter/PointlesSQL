"""Smoke tests for the soyuz-catalog integration.

Every test in this module talks to a **live** soyuz-catalog server and
is marked with ``@pytest.mark.integration`` so the default test run
(``uv run pytest``) skips them. Run explicitly with::

    uv run pytest tests/test_soyuz_client.py -m integration
"""

from __future__ import annotations

import pytest

from pointlessql.config import Settings
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient


@pytest.fixture
async def uc_client() -> UnityCatalogClient:
    client = make_soyuz_client()
    uc = UnityCatalogClient(client)
    yield uc
    await uc.aclose()


@pytest.mark.integration
async def test_list_catalogs(uc_client: UnityCatalogClient) -> None:
    catalogs = await uc_client.list_catalogs()
    assert isinstance(catalogs, list)
    assert len(catalogs) > 0
    assert "name" in catalogs[0]


@pytest.mark.integration
async def test_get_catalog(uc_client: UnityCatalogClient) -> None:
    catalogs = await uc_client.list_catalogs()
    first_name = catalogs[0]["name"]
    catalog = await uc_client.get_catalog(first_name)
    assert catalog["name"] == first_name


@pytest.mark.integration
async def test_list_schemas(uc_client: UnityCatalogClient) -> None:
    catalogs = await uc_client.list_catalogs()
    first_name = catalogs[0]["name"]
    schemas = await uc_client.list_schemas(first_name)
    assert isinstance(schemas, list)


@pytest.mark.integration
async def test_get_tree(uc_client: UnityCatalogClient) -> None:
    tree = await uc_client.get_tree()
    assert isinstance(tree, list)
    assert len(tree) > 0
    first_catalog = tree[0]
    assert "name" in first_catalog
    assert "schemas" in first_catalog


@pytest.mark.integration
async def test_settings_default() -> None:
    settings = Settings()
    assert settings.soyuz.catalog_url == "http://127.0.0.1:8080"


@pytest.mark.integration
async def test_make_soyuz_client_creates_client() -> None:
    client = make_soyuz_client()
    assert client.base_url == "http://127.0.0.1:8080"
