"""Sprint 21.5.2/21.5.3 — registered-model browse + detail JSON endpoints.

Mocks the ``ModelsMixin`` methods on the test ``UnityCatalogClient``
so the contract under test is the FastAPI router shape, not the
soyuz wire layer (already covered by Sprint 21.1 conformance tests).
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock

import httpx
import pytest

from pointlessql.api.main import app


def _client(**kwargs) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        follow_redirects=False,
        **kwargs,
    )


_LINK_MARKER = json.dumps(
    {
        "_pql_link": {
            "agent_run_id": "run-123",
            "mlflow_run_id": "mlf-abc",
            "linked_at": "2026-04-30T00:00:00+00:00",
            "mlflow_experiment_id": "0",
        }
    },
    sort_keys=True,
)


@pytest.fixture
def uc_with_models(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    monkeypatch.setattr(
        "pointlessql.api.dependencies.effective_principal",
        lambda request: None,
    )
    mock = AsyncMock()

    async def _list_catalogs():
        return [{"name": "cat1"}]

    async def _list_registered_models(
        catalog_name=None, schema_name=None, max_results=None, page_token=None
    ):
        if catalog_name == "cat1" or catalog_name is None:
            return [
                {
                    "name": "smoke_model",
                    "full_name": "cat1.sch1.smoke_model",
                    "catalog_name": "cat1",
                    "schema_name": "sch1",
                    "owner": "alice",
                    "comment": None,
                    "updated_at": 1700000000000,
                }
            ]
        return []

    async def _list_model_versions(full_name, max_results=None, page_token=None):
        if full_name != "cat1.sch1.smoke_model":
            return []
        return [
            {
                "version": 1,
                "status": "READY",
                "source": "file:///tmp/v1",
                "run_id": "mlf-abc",
                "comment": _LINK_MARKER,
                "model_name": "smoke_model",
            },
            {
                "version": 2,
                "status": "READY",
                "source": "file:///tmp/v2",
                "run_id": None,
                "comment": "manual entry",
                "model_name": "smoke_model",
            },
        ]

    async def _get_registered_model(full_name):
        if full_name != "cat1.sch1.smoke_model":
            return {}
        return {
            "name": "smoke_model",
            "full_name": full_name,
            "catalog_name": "cat1",
            "schema_name": "sch1",
            "owner": "alice",
            "comment": None,
        }

    async def _get_model_version(full_name, version):
        all_versions = await _list_model_versions(full_name)
        for v in all_versions:
            if v["version"] == version:
                return v
        return {}

    mock.list_catalogs.side_effect = _list_catalogs
    mock.list_registered_models.side_effect = _list_registered_models
    mock.list_model_versions.side_effect = _list_model_versions
    mock.get_registered_model.side_effect = _get_registered_model
    mock.get_model_version.side_effect = _get_model_version

    app.state.uc_client = mock
    return mock


@pytest.mark.asyncio
async def test_models_index_anonymous_redirects(uc_with_models: AsyncMock) -> None:
    async with _client() as c:
        resp = await c.get("/models")
    # Auth middleware redirects HTML pages to /auth/login (without ?next=)
    # before our route's own redirect ever runs.
    assert resp.status_code == 303
    assert resp.headers["location"] == "/auth/login"


@pytest.mark.asyncio
async def test_models_index_renders_for_authenticated_user(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/models")
    assert resp.status_code == 200
    body = resp.text
    assert "Registered Models" in body
    assert "modelsBrowse" in body  # x-data binding rendered


@pytest.mark.asyncio
async def test_api_models_unauthenticated_returns_401(
    uc_with_models: AsyncMock,
) -> None:
    async with _client() as c:
        resp = await c.get("/api/models")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_api_models_lists_models(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/api/models")
    assert resp.status_code == 200
    body = resp.json()
    assert any(m["full_name"] == "cat1.sch1.smoke_model" for m in body["models"])


@pytest.mark.asyncio
async def test_api_models_filters_by_catalog(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/api/models?catalog_name=other")
    assert resp.status_code == 200
    assert resp.json()["models"] == []


@pytest.mark.asyncio
async def test_api_models_enrich_latest_populates_version_summary(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/api/models?enrich_latest=true")
    assert resp.status_code == 200
    rows = resp.json()["models"]
    assert rows[0]["latest_version"] == 2
    assert rows[0]["latest_status"] == "READY"
    assert rows[0]["linked_run_count"] == 1


@pytest.mark.asyncio
async def test_api_get_model_returns_model_plus_versions(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/api/models/cat1.sch1.smoke_model")
    assert resp.status_code == 200
    body = resp.json()
    assert body["model"]["full_name"] == "cat1.sch1.smoke_model"
    versions = body["versions"]
    assert len(versions) == 2
    v1 = next(v for v in versions if v["version"] == 1)
    assert v1["link_marker"]["agent_run_id"] == "run-123"
    v2 = next(v for v in versions if v["version"] == 2)
    assert v2["link_marker"] is None


@pytest.mark.asyncio
async def test_api_get_model_404(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/api/models/cat1.sch1.missing")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_api_model_linked_runs_extracts_markers(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/api/models/cat1.sch1.smoke_model/runs")
    assert resp.status_code == 200
    runs = resp.json()["runs"]
    assert len(runs) == 1
    assert runs[0]["agent_run_id"] == "run-123"
    assert runs[0]["mlflow_run_id"] == "mlf-abc"
    assert runs[0]["version"] == 1


@pytest.mark.asyncio
async def test_model_detail_anonymous_redirects(
    uc_with_models: AsyncMock,
) -> None:
    async with _client() as c:
        resp = await c.get("/models/cat1.sch1.smoke_model")
    assert resp.status_code == 303


@pytest.mark.asyncio
async def test_model_detail_renders_all_tabs(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/models/cat1.sch1.smoke_model")
    assert resp.status_code == 200
    body = resp.text
    # Header + tab nav rendered.
    assert "cat1.sch1.smoke_model" in body
    assert 'id="tab-overview"' in body
    assert 'id="tab-versions"' in body
    assert 'id="tab-lineage"' in body
    assert 'id="tab-mlflow"' in body
    assert 'id="tab-promotion"' in body
    # Versions table has both versions.
    assert ">v1<" in body
    assert ">v2<" in body


@pytest.mark.asyncio
async def test_model_detail_404_for_unknown_model(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/models/cat1.sch1.unknown")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_model_detail_overview_shows_linked_run(
    uc_with_models: AsyncMock, auth_cookies: dict[str, str]
) -> None:
    async with _client(cookies=auth_cookies) as c:
        resp = await c.get("/models/cat1.sch1.smoke_model")
    assert resp.status_code == 200
    body = resp.text
    # Overview card lists the agent_run_id from the _pql_link marker.
    assert "/runs/run-123" in body
