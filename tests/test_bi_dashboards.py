"""Tests for the BI-dashboard surface (CRUD, params, widgets, data path)."""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from pointlessql.api.bi_dashboards_routes import _data as data_module
from pointlessql.api.main import app
from pointlessql.pql._types import SQLResult
from pointlessql.services import bi_dashboards as svc


def _factory():
    return app.state.session_factory


def _client(cookies: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies,
    )


async def _create(cookies: dict[str, str], title: str) -> dict[str, Any]:
    async with _client(cookies) as client:
        resp = await client.post("/api/bi/dashboards", json={"title": title})
    assert resp.status_code == 200, resp.text
    return resp.json()


# ---------------------------------------------------------------------------
# parameter substitution — the security-relevant core
# ---------------------------------------------------------------------------


_SPECS = [
    {"name": "region", "label": "Region", "type": "string", "default": "emea"},
    {"name": "min_n", "label": "Min", "type": "number", "default": 10},
    {"name": "day", "label": "Day", "type": "date", "default": "2026-01-01"},
]


def test_substitute_params_strings_are_quoted_and_escaped() -> None:
    out = svc.substitute_params(
        "SELECT * FROM t WHERE r = {{region}}",
        specs=_SPECS,
        values={"region": "o'brien'; DROP TABLE x; --"},
    )
    assert out == "SELECT * FROM t WHERE r = 'o''brien''; DROP TABLE x; --'"


def test_substitute_params_numbers_cannot_smuggle_sql() -> None:
    out = svc.substitute_params(
        "SELECT * FROM t WHERE n > {{min_n}}", specs=_SPECS, values={"min_n": "42"}
    )
    assert out == "SELECT * FROM t WHERE n > 42"
    with pytest.raises(ValueError, match="not a number"):
        svc.substitute_params(
            "SELECT * FROM t WHERE n > {{min_n}}",
            specs=_SPECS,
            values={"min_n": "1; DROP TABLE x"},
        )


def test_substitute_params_dates_validated() -> None:
    out = svc.substitute_params("SELECT * FROM t WHERE d = {{day}}", specs=_SPECS, values={})
    assert out == "SELECT * FROM t WHERE d = DATE '2026-01-01'"
    with pytest.raises(ValueError, match="ISO date"):
        svc.substitute_params(
            "SELECT * FROM t WHERE d = {{day}}",
            specs=_SPECS,
            values={"day": "tomorrow' OR 1=1"},
        )


def test_substitute_params_unknown_placeholder_raises() -> None:
    with pytest.raises(ValueError, match="unknown dashboard parameter"):
        svc.substitute_params("SELECT {{nope}}", specs=_SPECS, values={})


def test_validate_params_rejects_bad_shapes() -> None:
    with pytest.raises(ValueError, match="identifier"):
        svc.validate_params([{"name": "has space"}])
    with pytest.raises(ValueError, match="duplicate"):
        svc.validate_params([{"name": "a"}, {"name": "a"}])
    with pytest.raises(ValueError, match="type"):
        svc.validate_params([{"name": "a", "type": "blob"}])


def test_widget_source_validation() -> None:
    dash = svc.create_dashboard(
        _factory(), workspace_id=1, title="src rules", description=None, owner_id=1
    )
    with pytest.raises(ValueError, match="exactly one"):
        svc.add_widget(
            _factory(),
            dashboard_id=dash.id,
            kind="chart",
            title=None,
            sql_text="SELECT 1",
            saved_query_id=7,
            markdown=None,
            chart_spec=None,
            position=None,
        )
    with pytest.raises(ValueError, match="markdown"):
        svc.add_widget(
            _factory(),
            dashboard_id=dash.id,
            kind="markdown",
            title=None,
            sql_text=None,
            saved_query_id=None,
            markdown=None,
            chart_spec=None,
            position=None,
        )


# ---------------------------------------------------------------------------
# REST CRUD + ownership
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dashboard_crud_roundtrip() -> None:
    body = await _create(app.state._test_auth_cookie, "Revenue Overview")
    slug = body["slug"]
    assert body["title"] == "Revenue Overview"
    assert slug.startswith("revenue-overview-")

    async with _client(app.state._test_auth_cookie) as client:
        add = await client.post(
            f"/api/bi/dashboards/{slug}/widgets",
            json={
                "kind": "chart",
                "title": "Orders",
                "sql_text": "SELECT region, n FROM c.s.orders",
                "chart_spec": {"type": "bar", "x": "region", "y": "n"},
                "position": {"x": 0, "y": 0, "w": 6, "h": 4},
            },
        )
        assert add.status_code == 200, add.text
        widget_id = add.json()["id"]

        detail = await client.get(f"/api/bi/dashboards/{slug}")
        assert detail.json()["widget_count"] == 1
        assert detail.json()["widgets"][0]["chart_spec"]["type"] == "bar"

        layout = await client.put(
            f"/api/bi/dashboards/{slug}/layout",
            json={"positions": {str(widget_id): {"x": 3, "y": 1, "w": 4, "h": 2}}},
        )
        assert layout.json()["updated"] == 1
        detail = await client.get(f"/api/bi/dashboards/{slug}")
        assert detail.json()["widgets"][0]["position"] == {"x": 3, "y": 1, "w": 4, "h": 2}

        gone = await client.delete(f"/api/bi/dashboards/{slug}")
        assert gone.json()["deleted"] is True
        missing = await client.get(f"/api/bi/dashboards/{slug}")
        assert missing.status_code == 404


@pytest.mark.asyncio
async def test_mutations_are_owner_or_admin_only() -> None:
    body = await _create(app.state._test_auth_cookie, "Admin Owned")
    slug = body["slug"]
    async with _client(app.state._test_non_admin_cookie) as client:
        # every logged-in user may view…
        view = await client.get(f"/api/bi/dashboards/{slug}")
        assert view.status_code == 200
        # …but not mutate someone else's dashboard.
        patch = await client.patch(f"/api/bi/dashboards/{slug}", json={"title": "Hijack"})
        assert patch.status_code == 403
        delete = await client.delete(f"/api/bi/dashboards/{slug}")
        assert delete.status_code == 403

    own = await _create(app.state._test_non_admin_cookie, "Mine")
    async with _client(app.state._test_non_admin_cookie) as client:
        patch = await client.patch(f"/api/bi/dashboards/{own['slug']}", json={"title": "Mine v2"})
        assert patch.status_code == 200
        assert patch.json()["title"] == "Mine v2"


@pytest.mark.asyncio
async def test_params_patch_validates() -> None:
    body = await _create(app.state._test_auth_cookie, "Param Board")
    async with _client(app.state._test_auth_cookie) as client:
        ok = await client.patch(
            f"/api/bi/dashboards/{body['slug']}",
            json={"params": [{"name": "region", "type": "string", "default": "emea"}]},
        )
        assert ok.status_code == 200
        assert ok.json()["params"][0]["label"] == "region"
        bad = await client.patch(
            f"/api/bi/dashboards/{body['slug']}",
            json={"params": [{"name": "1bad"}]},
        )
        assert bad.status_code == 422


# ---------------------------------------------------------------------------
# data path (execution monkeypatched — engine has its own tests)
# ---------------------------------------------------------------------------


def _fake_result() -> SQLResult:
    return SQLResult(
        columns=[{"name": "region", "type": "VARCHAR"}, {"name": "n", "type": "BIGINT"}],
        rows=[["emea", 7]],
        row_count=1,
        truncated=False,
        duration_ms=3,
        executed_sql="…",
        rewritten_sql="…",
        referenced_tables=["c.s.orders"],
    )


@pytest.mark.asyncio
async def test_widget_data_substitutes_and_frames(monkeypatch) -> None:
    body = await _create(app.state._test_auth_cookie, "Data Board")
    slug = body["slug"]
    async with _client(app.state._test_auth_cookie) as client:
        await client.patch(
            f"/api/bi/dashboards/{slug}",
            json={"params": [{"name": "region", "type": "string", "default": "emea"}]},
        )
        add = await client.post(
            f"/api/bi/dashboards/{slug}/widgets",
            json={
                "kind": "table",
                "sql_text": "SELECT * FROM c.s.orders WHERE region = {{region}}",
            },
        )
        widget_id = add.json()["id"]

    seen: dict[str, Any] = {}

    async def _fake_resolve(sql: str, **kwargs: Any) -> dict[str, str]:
        seen["sql"] = sql
        return {"c.s.orders": "memory://orders"}

    def _fake_exec(sql: str, approved: dict[str, str], max_rows: int) -> SQLResult:
        seen["max_rows"] = max_rows
        return _fake_result()

    monkeypatch.setattr(data_module, "resolve_approved_tables", _fake_resolve)
    monkeypatch.setattr(data_module, "_run_widget_sql", _fake_exec)

    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(
            f"/api/bi/dashboards/{slug}/widgets/{widget_id}/data",
            json={"params": {"region": "apac"}},
        )
    assert resp.status_code == 200, resp.text
    assert seen["sql"] == "SELECT * FROM c.s.orders WHERE region = 'apac'"
    assert seen["max_rows"] == 1_000
    payload = resp.json()
    assert payload["rows"] == [["emea", 7]]
    assert payload["columns"][0]["name"] == "region"


@pytest.mark.asyncio
async def test_public_data_requires_valid_token(monkeypatch) -> None:
    body = await _create(app.state._test_auth_cookie, "Public Board")
    slug = body["slug"]
    async with _client(app.state._test_auth_cookie) as client:
        add = await client.post(
            f"/api/bi/dashboards/{slug}/widgets",
            json={"kind": "counter", "sql_text": "SELECT count(*) FROM c.s.orders"},
        )
        widget_id = add.json()["id"]
        published = await client.post(f"/api/bi/dashboards/{slug}/publish", json={"publish": True})
        token = published.json()["public_token"]
        assert token

    async def _fake_resolve(sql: str, **kwargs: Any) -> dict[str, str]:
        seen_actor.append(kwargs["actor_email"])
        return {"c.s.orders": "memory://orders"}

    seen_actor: list[str] = []
    monkeypatch.setattr(data_module, "resolve_approved_tables", _fake_resolve)
    monkeypatch.setattr(data_module, "_run_widget_sql", lambda *args: _fake_result())

    # anonymous client, no cookies — the token is the credential.
    async with _client({}) as anon:
        ok = await anon.post(f"/api/bi/public/{token}/widgets/{widget_id}/data", json={})
        assert ok.status_code == 200, ok.text
        bad = await anon.post(f"/api/bi/public/deadbeef/widgets/{widget_id}/data", json={})
        assert bad.status_code == 404
    # the public path executed as the dashboard owner.
    assert seen_actor == ["test@test.com"]

    async with _client(app.state._test_auth_cookie) as client:
        revoked = await client.post(f"/api/bi/dashboards/{slug}/publish", json={"publish": False})
        assert revoked.json()["is_published"] is False
    async with _client({}) as anon:
        gone = await anon.post(f"/api/bi/public/{token}/widgets/{widget_id}/data", json={})
        assert gone.status_code == 404


@pytest.mark.asyncio
async def test_markdown_widget_has_no_data_endpoint(monkeypatch) -> None:
    body = await _create(app.state._test_auth_cookie, "Md Board")
    slug = body["slug"]
    async with _client(app.state._test_auth_cookie) as client:
        add = await client.post(
            f"/api/bi/dashboards/{slug}/widgets",
            json={"kind": "markdown", "markdown": "# hello"},
        )
        widget_id = add.json()["id"]
        resp = await client.post(f"/api/bi/dashboards/{slug}/widgets/{widget_id}/data", json={})
        assert resp.status_code == 422
