"""public DBX-compatible SQL Statement Execution API routes."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import deltalake
import httpx
import pandas as pd
import pytest

from pointlessql.api.main import app
from pointlessql.services.unitycatalog import UnityCatalogClient
from tests.conftest import ApiKeyFixture


def _make_uc_mock(
    *, storage_location: str, principal: str = "api_key:sql-execute-fixture"
) -> MagicMock:
    """Build a UnityCatalogClient mock that resolves orders + grants SELECT."""
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": "orders",
            "catalog_name": "main",
            "schema_name": "sales",
            "storage_location": storage_location,
        }
    )
    client.get_effective_permissions = AsyncMock(
        return_value=[{"principal": principal, "privileges": ["SELECT"]}]
    )
    return client


@pytest.fixture(autouse=True)
def _patch_for_principal(monkeypatch: pytest.MonkeyPatch) -> None:
    """Route ``UnityCatalogClient.for_principal`` to ``app.state.uc_client``."""
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: app.state.uc_client),  # type: ignore[arg-type]
    )


@pytest.fixture
def orders_delta(tmp_path: Path) -> str:
    """Create a tiny Delta table at ``tmp_path/orders`` and return its path."""
    loc = str(tmp_path / "orders")
    df = pd.DataFrame({"id": [1, 2, 3], "name": ["a", "b", "c"]})
    deltalake.write_deltalake(loc, df)
    return loc


async def _client(headers: dict[str, str] | None = None) -> httpx.AsyncClient:
    """Build a non-cookie HTTP client (Bearer / anonymous)."""
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        headers=headers or {},
    )


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


async def test_post_rejects_anonymous() -> None:
    async with await _client() as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT 1"},
        )
    assert resp.status_code in (401, 403)


async def test_post_rejects_wrong_scope(api_key_secret: ApiKeyFixture) -> None:
    """A key without sql_execute=True must be refused (403)."""
    async with await _client(api_key_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT 1"},
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


async def test_post_sync_happy_path_returns_succeeded_envelope(
    orders_delta: str, sql_execute_secret: ApiKeyFixture
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={
                "statement": "SELECT id, name FROM main.sales.orders ORDER BY id",
                "wait_timeout": "10s",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"]["state"] == "SUCCEEDED", body
    assert "statement_id" in body
    manifest = body["manifest"]
    assert manifest["format"] == "JSON_ARRAY"
    assert manifest["total_row_count"] == 3
    assert manifest["schema"]["columns"][0]["type_name"] == "LONG"
    assert body["result"]["data_array"][0] == ["1", "a"]


async def test_post_default_catalog_and_schema_rewrite(
    orders_delta: str, sql_execute_secret: ApiKeyFixture
) -> None:
    """Body-level catalog+schema fill in a 1-part table ref pre-parse."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={
                "statement": "SELECT id FROM orders ORDER BY id",
                "catalog": "main",
                "schema": "sales",
                "wait_timeout": "10s",
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"]["state"] == "SUCCEEDED"


async def test_post_typed_parameter_binding(
    orders_delta: str, sql_execute_secret: ApiKeyFixture
) -> None:
    """Typed parameter substitution survives the round-trip."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={
                "statement": "SELECT id FROM main.sales.orders WHERE id = :pid",
                "wait_timeout": "10s",
                "parameters": [{"name": "pid", "value": 2, "type": "INT"}],
            },
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"]["state"] == "SUCCEEDED"
    assert body["manifest"]["total_row_count"] == 1
    assert body["result"]["data_array"][0] == ["2"]


# ---------------------------------------------------------------------------
# Failure envelopes (200 + FAILED, not 400)
# ---------------------------------------------------------------------------


async def test_post_parse_error_returns_failed_envelope(
    sql_execute_secret: ApiKeyFixture,
) -> None:
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SLECT 1"},
        )
    # The qualify/bind front-door is permissive when there are no
    # defaults — the error surfaces inside the executor and lands as
    # FAILED with SQL_PARSE_ERROR.
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"]["state"] == "FAILED"
    assert body["status"]["error"]["error_code"] == "SQL_PARSE_ERROR"


async def test_post_non_select_returns_failed(
    sql_execute_secret: ApiKeyFixture,
) -> None:
    """DML rejected — v1 is SELECT-only."""
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "DELETE FROM main.sales.orders WHERE id = 1"},
        )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"]["state"] == "FAILED"
    assert body["status"]["error"]["error_code"] in ("INVALID_PARAMETER_VALUE", "SQL_PARSE_ERROR")


# ---------------------------------------------------------------------------
# Body validation (400 from the route layer)
# ---------------------------------------------------------------------------


async def test_post_rejects_arrow_stream_format(
    sql_execute_secret: ApiKeyFixture,
) -> None:
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT 1", "format": "ARROW_STREAM"},
        )
    assert resp.status_code == 400
    assert resp.json()["detail"]["error_code"] == "INVALID_PARAMETER_VALUE"


async def test_post_rejects_external_links_disposition(
    sql_execute_secret: ApiKeyFixture,
) -> None:
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT 1", "disposition": "EXTERNAL_LINKS"},
        )
    assert resp.status_code == 400


async def test_post_rejects_empty_statement(
    sql_execute_secret: ApiKeyFixture,
) -> None:
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": ""},
        )
    assert resp.status_code == 400


async def test_post_rejects_bad_wait_timeout(
    sql_execute_secret: ApiKeyFixture,
) -> None:
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT 1", "wait_timeout": "not-a-duration"},
        )
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Polling + chunk fetch
# ---------------------------------------------------------------------------


async def test_get_poll_returns_persisted_envelope(
    orders_delta: str, sql_execute_secret: ApiKeyFixture
) -> None:
    """After a SUCCEEDED submit, GET returns the same envelope."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    async with await _client(sql_execute_secret.headers) as ac:
        submit = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT id FROM main.sales.orders ORDER BY id"},
        )
        assert submit.status_code == 200
        sid = submit.json()["statement_id"]
        get = await ac.get(f"/api/2.0/sql/statements/{sid}")
    assert get.status_code == 200
    body = get.json()
    assert body["status"]["state"] == "SUCCEEDED"
    assert body["manifest"]["total_row_count"] == 3


async def test_get_chunk_returns_result_data_array(
    orders_delta: str, sql_execute_secret: ApiKeyFixture
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    async with await _client(sql_execute_secret.headers) as ac:
        submit = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT id FROM main.sales.orders ORDER BY id"},
        )
        sid = submit.json()["statement_id"]
        chunk = await ac.get(f"/api/2.0/sql/statements/{sid}/result/chunks/0")
    assert chunk.status_code == 200
    body = chunk.json()
    assert body["row_count"] == 3
    assert body["data_array"][0] == ["1"]


async def test_get_chunk_out_of_range_404(
    orders_delta: str, sql_execute_secret: ApiKeyFixture
) -> None:
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    async with await _client(sql_execute_secret.headers) as ac:
        submit = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT id FROM main.sales.orders"},
        )
        sid = submit.json()["statement_id"]
        chunk = await ac.get(f"/api/2.0/sql/statements/{sid}/result/chunks/1")
    assert chunk.status_code == 404


async def test_get_missing_statement_404(
    sql_execute_secret: ApiKeyFixture,
) -> None:
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.get("/api/2.0/sql/statements/00000000-0000-0000-0000-000000000000")
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


async def test_cancel_on_succeeded_returns_current_envelope(
    orders_delta: str, sql_execute_secret: ApiKeyFixture
) -> None:
    """Cancel after success is a no-op that returns the SUCCEEDED envelope."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    async with await _client(sql_execute_secret.headers) as ac:
        submit = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT id FROM main.sales.orders"},
        )
        sid = submit.json()["statement_id"]
        cancel = await ac.post(f"/api/2.0/sql/statements/{sid}/cancel")
    assert cancel.status_code == 200
    assert cancel.json()["status"]["state"] == "SUCCEEDED"


# ---------------------------------------------------------------------------
# Feature flag
# ---------------------------------------------------------------------------


async def test_disabled_api_returns_503(
    sql_execute_secret: ApiKeyFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = app.state.settings
    monkeypatch.setattr(settings.sql_execution_api, "enabled", False)
    async with await _client(sql_execute_secret.headers) as ac:
        resp = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT 1"},
        )
    assert resp.status_code == 503
    assert resp.json()["detail"]["error_code"] == "WORKSPACE_TEMPORARILY_UNAVAILABLE"


# ---------------------------------------------------------------------------
# Rate limit
# ---------------------------------------------------------------------------


async def test_rate_limit_kicks_in(
    orders_delta: str,
    sql_execute_secret: ApiKeyFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the per-key budget is 1/min the 2nd call returns 429."""
    app.state.uc_client = _make_uc_mock(storage_location=orders_delta)
    settings = app.state.settings
    monkeypatch.setattr(settings.rate_limit, "sql_statements_apikey_count", 1)
    monkeypatch.setattr(settings.rate_limit, "sql_statements_apikey_window_s", 60)
    async with await _client(sql_execute_secret.headers) as ac:
        first = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT id FROM main.sales.orders"},
        )
        second = await ac.post(
            "/api/2.0/sql/statements",
            json={"statement": "SELECT id FROM main.sales.orders"},
        )
    assert first.status_code == 200
    assert second.status_code == 429
    body = second.json()
    assert body["detail"]["error_code"] == "REQUEST_LIMIT_EXCEEDED"
