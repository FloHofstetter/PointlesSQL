"""Tests for the Genie App Builder (NL → runnable hosted app)."""

from __future__ import annotations

import ast
import datetime
import uuid

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.config import get_settings
from pointlessql.models import Workspace
from pointlessql.services import app_hosting, genie_app_builder


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(slug=f"gab-{uuid.uuid4().hex[:10]}", name="Genie App WS", created_at=now)
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def test_extract_python_fenced_and_raw() -> None:
    fenced = "Here you go:\n```python\nimport streamlit as st\nst.title('x')\n```\nDone."
    assert genie_app_builder.extract_python(fenced) == "import streamlit as st\nst.title('x')"
    assert genie_app_builder.extract_python("st.write('hi')") == "st.write('hi')"


def test_default_title() -> None:
    assert genie_app_builder.default_title("") == "Genie App"
    assert (
        genie_app_builder.default_title("a dashboard listing the top ten customers by revenue now")
        == "a dashboard listing the top ten"
    )


@pytest.mark.parametrize("kind", ["fastapi", "streamlit"])
def test_scaffold_is_valid_python_and_carries_prompt(kind: str) -> None:
    prompt = "Show sales by region with a {weird} brace and a 'quote'"
    src = genie_app_builder.scaffold_app(prompt=prompt, kind=kind)
    ast.parse(src)  # raises on a malformed scaffold
    assert prompt in src
    assert "Drafted by the Genie App Builder" in src
    if kind == "fastapi":
        assert "FastAPI" in src
    else:
        assert "streamlit" in src


def test_scaffold_uses_runnable_body_verbatim() -> None:
    body = "from fastapi import FastAPI\napp = FastAPI()\n"
    src = genie_app_builder.scaffold_app(prompt="anything", kind="fastapi", body=body)
    ast.parse(src)
    assert "app = FastAPI()" in src
    # The deterministic placeholder marker must be absent — the body won.
    assert "Generated scaffold" not in src


def test_scaffold_falls_back_when_body_not_runnable() -> None:
    # A bare print has no FastAPI entry point, so the scaffold wins.
    src = genie_app_builder.scaffold_app(prompt="hello", kind="fastapi", body="print('hi')")
    assert "Generated scaffold" in src
    assert "FastAPI" in src


def test_scaffold_falls_back_when_fastapi_body_lacks_app_binding() -> None:
    # Importing FastAPI and merely mentioning "app" in a comment is not a
    # runnable app — without a module-level `app =` the hosting worker
    # could not import the entry point, so the placeholder scaffold wins.
    body = "from fastapi import FastAPI\n# build the app here later\nprint('todo')\n"
    src = genie_app_builder.scaffold_app(prompt="hello", kind="fastapi", body=body)
    assert "Generated scaffold" in src
    assert "app = FastAPI()" in src


def test_scaffold_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="Unknown app kind"):
        genie_app_builder.scaffold_app(prompt="x", kind="command")


def test_build_system_prompt_unknown_kind_raises() -> None:
    with pytest.raises(ValueError, match="Unknown app kind"):
        genie_app_builder.build_system_prompt("command")


@pytest.mark.asyncio
async def test_generate_app_source_falls_back_without_llm() -> None:
    ws = _fresh_workspace()
    source, used_llm = await genie_app_builder.generate_app_source(
        "  a tiny status page  ",
        "streamlit",
        factory=_factory(),
        workspace_id=ws,
        settings=get_settings(),
    )
    assert used_llm is False
    ast.parse(source)
    assert "a tiny status page" in source


def test_resolve_provider_uses_per_provider_model_default() -> None:
    # A BYO credential without an explicit default_model must fall back to
    # the provider's own configured default, not a hard-coded Anthropic id.
    from pointlessql.services.lens._provider_creds import upsert_provider_creds

    ws = _fresh_workspace()
    upsert_provider_creds(
        _factory(), workspace_id=ws, provider="kimi", api_key="sk-test", default_model=None
    )
    settings = get_settings()
    resolved = genie_app_builder._resolve_provider(_factory(), workspace_id=ws, settings=settings)
    assert resolved is not None
    provider_name, _api_key, model = resolved
    assert provider_name == "kimi"
    assert model == settings.lens.kimi_model_default


@pytest.mark.asyncio
async def test_generate_app_source_rejects_blank_prompt() -> None:
    with pytest.raises(ValueError, match="prompt is required"):
        await genie_app_builder.generate_app_source(
            "   ",
            "fastapi",
            factory=_factory(),
            workspace_id=1,
            settings=get_settings(),
        )


@pytest.mark.asyncio
async def test_route_builds_and_creates_app(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/apps/genie-build",
        json={"prompt": "A page that lists open incidents", "kind": "fastapi"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["used_llm"] is False  # no LLM credential in the test workspace
    slug = data["app"]["slug"]
    assert data["app"]["kind"] == "fastapi"
    ast.parse(data["app"]["source_code"])

    # The app is now managed on the regular apps surface.
    listed = await admin_client.get("/api/apps")
    assert any(a["slug"] == slug for a in listed.json()["apps"])
    # And it really landed in the hosting store.
    stored = app_hosting.get_app(_factory(), workspace_id=1, slug=slug)
    assert stored is not None


@pytest.mark.asyncio
async def test_route_rejects_blank_prompt(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/apps/genie-build", json={"prompt": "  ", "kind": "fastapi"}
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_route_rejects_unbuildable_kind(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/apps/genie-build", json={"prompt": "do a thing", "kind": "command"}
    )
    assert resp.status_code == 422, resp.text


@pytest.mark.asyncio
async def test_route_forbidden_for_non_admin(non_admin_client: httpx.AsyncClient) -> None:
    resp = await non_admin_client.post(
        "/api/apps/genie-build", json={"prompt": "do a thing", "kind": "fastapi"}
    )
    assert resp.status_code == 403, resp.text
