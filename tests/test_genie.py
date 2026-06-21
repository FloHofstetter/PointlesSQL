"""Tests for Genie spaces — curation, prompt context, and the ask path.

The router under test is exported but not yet registered on the app,
so a module fixture mounts it for the duration of this file (the
ingest-stream tests established the pattern).  LLM generation and
the governed execution seam are monkeypatched at the route module —
the validation + persistence in between runs real.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import httpx
import pytest
from sqlalchemy import select

import pointlessql.models.genie  # noqa: F401
from pointlessql.api.genie_routes import _ask as ask_module
from pointlessql.api.main import app
from pointlessql.exceptions import ValidationError
from pointlessql.models import User
from pointlessql.pql import SQLParseError
from pointlessql.pql._types import SQLResult
from pointlessql.services import genie as genie_service

_TABLE_INFO = {
    "full_name": "shop.gold.orders",
    "comment": "One row per order.",
    "columns": [
        {"name": "region", "type_text": "VARCHAR", "comment": "Sales region."},
        {"name": "amount", "type_text": "BIGINT", "comment": None},
    ],
}

_METRIC_VIEW = {
    "full_name": "shop.gold.revenue",
    "source_table_full_name": "shop.gold.orders",
    "comment": "Net revenue.",
    "spec": {
        "dimensions": [{"name": "region", "expr": "region"}],
        "measures": [{"name": "revenue", "expr": "sum(amount)"}],
        "filter": "status = 'completed'",
    },
}


@pytest.fixture(scope="module", autouse=True)
def _mount_genie_routes() -> Iterator[None]:
    """Mount the unregistered Genie router on the app for this module."""
    from pointlessql.api.genie_routes import router

    before = list(app.router.routes)
    app.include_router(router)
    yield
    app.router.routes[:] = before


def _client(cookies: dict[str, str]) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://test",
        cookies=cookies,
    )


def _factory() -> Any:
    return app.state.session_factory


def _admin_id() -> int:
    with _factory()() as session:
        return int(session.scalar(select(User.id).where(User.email == "test@test.com")) or 0)


def _make_space(**overrides: Any) -> Any:
    space = genie_service.create_space(
        _factory(),
        workspace_id=1,
        title=str(overrides.pop("title", "Sales analytics")),
        description=overrides.pop("description", None),
        owner_id=_admin_id(),
    )
    if overrides:
        space = genie_service.update_space(_factory(), space_id=space.id, **overrides)
    assert space is not None
    return space


# ---------------------------------------------------------------------------
# Service: CRUD + slug + validation
# ---------------------------------------------------------------------------


def test_create_space_slugifies_title() -> None:
    space = _make_space(title="Q4 Sales — EMEA!")
    assert space.slug.startswith("q4-sales-emea-")
    assert len(space.slug) > len("q4-sales-emea-")  # random suffix
    fetched = genie_service.get_space(_factory(), workspace_id=1, slug=space.slug)
    assert fetched is not None
    assert fetched.title == "Q4 Sales — EMEA!"


def test_update_space_validates_fqn_lists() -> None:
    space = _make_space()
    updated = genie_service.update_space(
        _factory(),
        space_id=space.id,
        instructions="Revenue means completed orders only.",
        tables=["shop.gold.orders", "shop.gold.orders"],
    )
    assert updated is not None
    assert genie_service.space_tables(updated) == ["shop.gold.orders"]  # de-duped
    assert updated.instructions == "Revenue means completed orders only."
    with pytest.raises(ValueError, match="three-part"):
        genie_service.update_space(_factory(), space_id=space.id, tables=["not_qualified"])


def test_delete_space_removes_children() -> None:
    space = _make_space()
    genie_service.add_trusted_asset(
        _factory(),
        space_id=space.id,
        question="Total rows?",
        sql_text="SELECT count(*) FROM shop.gold.orders",
        created_by=_admin_id(),
    )
    genie_service.append_message(
        _factory(), space_id=space.id, user_id=_admin_id(), role="user", content="hi"
    )
    assert genie_service.delete_space(_factory(), space_id=space.id) is True
    assert genie_service.list_trusted_assets(_factory(), space_id=space.id) == []
    assert genie_service.list_messages(_factory(), space_id=space.id) == []


def test_trusted_asset_rejects_non_select() -> None:
    space = _make_space()
    with pytest.raises(SQLParseError):
        genie_service.add_trusted_asset(
            _factory(),
            space_id=space.id,
            question="Drop it?",
            sql_text="DROP TABLE shop.gold.orders",
            created_by=_admin_id(),
        )


# ---------------------------------------------------------------------------
# Service: context builder
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_build_context_includes_curation(uc_client_stub) -> None:
    uc_client_stub.get_table.return_value = _TABLE_INFO
    uc_client_stub.get_metric_view.return_value = _METRIC_VIEW
    space = _make_space(
        tables=["shop.gold.orders"],
        metric_views=["shop.gold.revenue"],
        instructions="Prefer completed orders.",
    )
    genie_service.add_trusted_asset(
        _factory(),
        space_id=space.id,
        question="Revenue by region?",
        sql_text="SELECT region, sum(amount) FROM shop.gold.orders GROUP BY 1",
        created_by=_admin_id(),
    )
    space = genie_service.get_space(_factory(), workspace_id=1, slug=space.slug)
    assert space is not None
    context = await genie_service.build_context(uc_client_stub, _factory(), space)
    assert "TABLE shop.gold.orders -- One row per order." in context
    assert "region VARCHAR -- Sales region." in context
    assert "METRIC VIEW shop.gold.revenue" in context
    assert "measure revenue: sum(amount)" in context
    assert "Prefer completed orders." in context
    assert "Q: Revenue by region?" in context
    uc_client_stub.get_table.assert_awaited_once_with("shop", "gold", "orders")
    uc_client_stub.get_metric_view.assert_awaited_once_with("shop.gold.revenue")


@pytest.mark.asyncio
async def test_build_context_cap_holds(uc_client_stub) -> None:
    huge = {
        "full_name": "shop.gold.wide",
        "comment": "x" * 500,
        "columns": [
            {"name": f"col_{i}", "type_text": "VARCHAR", "comment": "y" * 200} for i in range(200)
        ],
    }
    uc_client_stub.get_table.return_value = huge
    space = _make_space(
        tables=[f"shop.gold.wide_{i}" for i in range(20)],
        instructions="z" * 3000,
    )
    context = await genie_service.build_context(uc_client_stub, _factory(), space)
    assert len(context) <= genie_service.CONTEXT_CHAR_CAP
    # Per-table truncation kicked in before the hard cap.
    assert "more columns)" in context


def test_extract_sql_strips_fences() -> None:
    fenced = "```sql\nSELECT 1;\n```"
    assert genie_service.extract_sql(fenced) == "SELECT 1"
    assert genie_service.extract_sql("  SELECT 2 ;") == "SELECT 2"


def test_validate_generated_sql_scope() -> None:
    refs = genie_service.validate_generated_sql(
        "SELECT region FROM shop.gold.orders",
        allowed_tables=["shop.gold.orders"],
    )
    assert refs == ["shop.gold.orders"]
    with pytest.raises(ValidationError, match="outside this space"):
        genie_service.validate_generated_sql(
            "SELECT * FROM hr.people.salaries",
            allowed_tables=["shop.gold.orders"],
        )
    with pytest.raises(SQLParseError):
        genie_service.validate_generated_sql(
            "DELETE FROM shop.gold.orders",
            allowed_tables=["shop.gold.orders"],
        )


# ---------------------------------------------------------------------------
# Route: ask flow
# ---------------------------------------------------------------------------


def _fake_result(sql: str) -> SQLResult:
    return SQLResult(
        columns=[{"name": "region", "type": "VARCHAR"}, {"name": "revenue", "type": "BIGINT"}],
        rows=[["emea", 30]],
        row_count=1,
        truncated=False,
        duration_ms=2,
        executed_sql=sql,
        rewritten_sql=sql,
        referenced_tables=["shop.gold.orders"],
    )


def _patch_generate(monkeypatch: pytest.MonkeyPatch, sql: str) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def _fake_generate(question: str, context: str, history: list[Any], **kwargs: Any) -> str:
        seen["question"] = question
        seen["context"] = context
        seen["history"] = history
        return sql

    monkeypatch.setattr(ask_module, "generate_sql", _fake_generate)
    return seen


def _patch_execution(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    seen: dict[str, Any] = {}

    async def _fake_resolve(sql: str, **kwargs: Any) -> tuple[dict[str, str], dict[str, Any]]:
        seen["resolved_sql"] = sql
        return {"shop.gold.orders": "memory://orders"}, {}

    def _fake_exec(
        sql: str, approved: dict[str, str], max_rows: int, policies: Any = None
    ) -> SQLResult:
        seen["max_rows"] = max_rows
        return _fake_result(sql)

    monkeypatch.setattr(ask_module, "resolve_select_context", _fake_resolve)
    monkeypatch.setattr(ask_module, "_run_genie_sql", _fake_exec)
    return seen


@pytest.mark.asyncio
async def test_ask_executes_and_persists(uc_client_stub, monkeypatch) -> None:
    uc_client_stub.get_table.return_value = _TABLE_INFO
    space = _make_space(tables=["shop.gold.orders"])
    sql = "SELECT region, sum(amount) AS revenue FROM shop.gold.orders GROUP BY 1"
    gen_seen = _patch_generate(monkeypatch, sql)
    exec_seen = _patch_execution(monkeypatch)

    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(
            f"/api/genie/spaces/{space.slug}/ask",
            json={"question": "Revenue by region?"},
        )
        assert resp.status_code == 200, resp.text
        body = resp.json()
        assert body["sql"] == sql
        assert body["rows"] == [["emea", 30]]
        assert body["row_count"] == 1
        assert body["truncated"] is False
        assert isinstance(body["message_id"], int)

        transcript = (await client.get(f"/api/genie/spaces/{space.slug}/messages")).json()

    assert gen_seen["question"] == "Revenue by region?"
    assert "TABLE shop.gold.orders" in gen_seen["context"]
    assert exec_seen["resolved_sql"] == sql
    assert exec_seen["max_rows"] == 1000
    roles = [(m["role"], m["status"]) for m in transcript["messages"]]
    assert roles == [("user", "ok"), ("assistant", "ok")]
    assert transcript["messages"][1]["sql_text"] == sql
    assert transcript["messages"][1]["id"] == body["message_id"]


@pytest.mark.asyncio
async def test_ask_rejects_out_of_space_table(uc_client_stub, monkeypatch) -> None:
    uc_client_stub.get_table.return_value = _TABLE_INFO
    space = _make_space(tables=["shop.gold.orders"])
    _patch_generate(monkeypatch, "SELECT * FROM hr.people.salaries")
    _patch_execution(monkeypatch)

    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(
            f"/api/genie/spaces/{space.slug}/ask",
            json={"question": "What do colleagues earn?"},
        )
        assert resp.status_code == 422, resp.text
        assert "outside this space" in resp.text

        transcript = (await client.get(f"/api/genie/spaces/{space.slug}/messages")).json()

    last = transcript["messages"][-1]
    assert last["role"] == "assistant"
    assert last["status"] == "error"
    assert "hr.people.salaries" in last["error"]


@pytest.mark.asyncio
async def test_ask_without_llm_credential_answers_503() -> None:
    """The real generate_sql gates on the workspace's BYO Lens creds."""
    space = _make_space()  # no tables — build_context never hits UC
    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(
            f"/api/genie/spaces/{space.slug}/ask",
            json={"question": "Anything there?"},
        )
    assert resp.status_code == 503, resp.text
    assert "credential" in resp.text


@pytest.mark.asyncio
async def test_ask_rejects_empty_question() -> None:
    space = _make_space()
    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(f"/api/genie/spaces/{space.slug}/ask", json={"question": "  "})
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Route: run trusted asset as a deterministic skill
# ---------------------------------------------------------------------------


def _add_asset(space: Any, sql: str, question: str = "Revenue?") -> Any:
    return genie_service.add_trusted_asset(
        _factory(),
        space_id=space.id,
        question=question,
        sql_text=sql,
        created_by=_admin_id(),
    )


@pytest.mark.asyncio
async def test_run_trusted_asset_executes(monkeypatch) -> None:
    space = _make_space(tables=["shop.gold.orders"])
    asset = _add_asset(space, "SELECT region, sum(amount) FROM shop.gold.orders GROUP BY region")
    exec_seen = _patch_execution(monkeypatch)

    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(f"/api/genie/spaces/{space.slug}/assets/{asset.id}/run", json={})
        assert resp.status_code == 200, resp.text
        body = resp.json()

    assert body["asset_id"] == asset.id
    assert body["sql"] == "SELECT region, sum(amount) FROM shop.gold.orders GROUP BY region"
    assert body["rows"] == [["emea", 30]]
    assert body["row_count"] == 1
    # Executed the stored SQL verbatim — no LLM round-trip.
    assert exec_seen["resolved_sql"].startswith("SELECT region")
    assert exec_seen["max_rows"] == 1000


@pytest.mark.asyncio
async def test_run_trusted_asset_unknown_is_404(monkeypatch) -> None:
    space = _make_space(tables=["shop.gold.orders"])
    _patch_execution(monkeypatch)
    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(f"/api/genie/spaces/{space.slug}/assets/999999/run", json={})
    assert resp.status_code == 404, resp.text


@pytest.mark.asyncio
async def test_run_trusted_asset_rejects_table_dropped_from_space(monkeypatch) -> None:
    space = _make_space(tables=["shop.gold.orders"])
    asset = _add_asset(space, "SELECT * FROM shop.gold.orders")
    # The curator narrowed the space after the asset was vetted.
    genie_service.update_space(_factory(), space_id=space.id, tables=["shop.gold.customers"])
    _patch_execution(monkeypatch)

    async with _client(app.state._test_auth_cookie) as client:
        resp = await client.post(f"/api/genie/spaces/{space.slug}/assets/{asset.id}/run", json={})
    assert resp.status_code == 422, resp.text


# ---------------------------------------------------------------------------
# Route: feedback + promote
# ---------------------------------------------------------------------------


def _seed_answered_question(space_id: int) -> int:
    genie_service.append_message(
        _factory(),
        space_id=space_id,
        user_id=_admin_id(),
        role="user",
        content="Revenue by region?",
    )
    answer = genie_service.append_message(
        _factory(),
        space_id=space_id,
        user_id=None,
        role="assistant",
        content="Returned 1 rows.",
        sql_text="SELECT region, sum(amount) FROM shop.gold.orders GROUP BY 1",
        status="ok",
    )
    return answer.id


@pytest.mark.asyncio
async def test_feedback_and_promote_as_owner() -> None:
    space = _make_space()
    message_id = _seed_answered_question(space.id)
    async with _client(app.state._test_auth_cookie) as client:
        thumbs = await client.post(
            f"/api/genie/messages/{message_id}/feedback", json={"feedback": "up"}
        )
        assert thumbs.status_code == 200, thumbs.text
        assert thumbs.json()["feedback"] == "up"

        bad = await client.post(
            f"/api/genie/messages/{message_id}/feedback", json={"feedback": "sideways"}
        )
        assert bad.status_code == 422

        promoted = await client.post(f"/api/genie/messages/{message_id}/promote")
        assert promoted.status_code == 200, promoted.text
        asset = promoted.json()
        assert asset["question"] == "Revenue by region?"
        assert asset["sql_text"].startswith("SELECT region")
    assets = genie_service.list_trusted_assets(_factory(), space_id=space.id)
    assert len(assets) == 1


@pytest.mark.asyncio
async def test_promote_rejected_for_stranger() -> None:
    space = _make_space()  # owned by the admin test user
    message_id = _seed_answered_question(space.id)
    async with _client(app.state._test_non_admin_cookie) as client:
        resp = await client.post(f"/api/genie/messages/{message_id}/promote")
    assert resp.status_code == 403
    assert genie_service.list_trusted_assets(_factory(), space_id=space.id) == []


@pytest.mark.asyncio
async def test_patch_space_rejected_for_stranger() -> None:
    space = _make_space()
    async with _client(app.state._test_non_admin_cookie) as client:
        resp = await client.patch(
            f"/api/genie/spaces/{space.slug}", json={"title": "Hijacked room"}
        )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# HTML pages
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_spaces_list_page_renders() -> None:
    async with _client(app.state._test_auth_cookie) as client:
        page = await client.get("/genie")
    assert page.status_code == 200
    assert 'x-data="genieSpaces()"' in page.text
    assert "genie_spaces.js" in page.text


@pytest.mark.asyncio
async def test_space_room_page_renders() -> None:
    space = _make_space(title="Sales room")
    async with _client(app.state._test_auth_cookie) as client:
        page = await client.get(f"/genie/{space.slug}")
    assert page.status_code == 200
    assert "genieSpace(" in page.text
    assert "genie_space.js" in page.text
    assert "Sales room" in page.text
