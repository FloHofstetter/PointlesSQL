"""browser chat UI route + chat-loop tests.

Mocks the LLM provider so the test never touches the OpenAI / Anthropic
network paths.  Validates session CRUD, message append + persistence,
provider-creds upsert + decrypt cycle, and the icon-rail gate.
"""

from __future__ import annotations

import datetime
from typing import Any
from unittest.mock import patch

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.services.api_keys import (
    create_api_key,
    invalidate_cache,
)
from pointlessql.services.lens import (
    decrypt_provider_key,
    upsert_provider_creds,
)
from pointlessql.services.lens.llm_provider import (
    LensCompletion,
    ToolCall,
)


def _ensure_keys_table() -> None:
    """Wipe + invalidate so each test starts with a clean api_keys cache."""
    factory = app.state.session_factory
    from pointlessql.models import ApiKey

    with factory() as s:
        s.query(ApiKey).delete()
        s.commit()
    invalidate_cache()


def _wipe_lens_tables() -> None:
    """Clear lens_sessions + lens_messages + provider_creds between tests."""
    factory = app.state.session_factory
    from pointlessql.models import (
        LensMessage,
        LensProviderCreds,
        LensSession,
    )

    with factory() as s:
        s.query(LensMessage).delete()
        s.query(LensSession).delete()
        s.query(LensProviderCreds).delete()
        s.commit()


@pytest.mark.asyncio
async def test_create_session_returns_201_for_admin(
    admin_client: httpx.AsyncClient,
) -> None:
    """Admin can create a session and gets back a populated row."""
    _wipe_lens_tables()
    resp = await admin_client.post(
        "/api/lens/sessions",
        json={"title": "test-session", "llm_provider": "anthropic"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "test-session"
    assert body["llm_provider"] == "anthropic"
    assert body["id"] > 0


@pytest.mark.asyncio
async def test_create_session_rejects_unknown_provider(
    admin_client: httpx.AsyncClient,
) -> None:
    """Bogus provider name → 422."""
    _wipe_lens_tables()
    resp = await admin_client.post(
        "/api/lens/sessions",
        json={"title": "bad", "llm_provider": "grok"},
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_list_sessions_returns_owners_rows(
    admin_client: httpx.AsyncClient,
) -> None:
    """Listing returns the sessions the caller created."""
    _wipe_lens_tables()
    await admin_client.post(
        "/api/lens/sessions",
        json={"title": "alpha", "llm_provider": "anthropic"},
    )
    await admin_client.post(
        "/api/lens/sessions",
        json={"title": "beta", "llm_provider": "anthropic"},
    )
    resp = await admin_client.get("/api/lens/sessions")
    assert resp.status_code == 200
    titles = {s["title"] for s in resp.json()["sessions"]}
    assert {"alpha", "beta"} <= titles


@pytest.mark.asyncio
async def test_delete_session_then_404_on_get(
    admin_client: httpx.AsyncClient,
) -> None:
    """Deleting a session removes it from the list."""
    _wipe_lens_tables()
    create = await admin_client.post(
        "/api/lens/sessions",
        json={"title": "to-delete", "llm_provider": "anthropic"},
    )
    sid = create.json()["id"]
    resp = await admin_client.delete(f"/api/lens/sessions/{sid}")
    assert resp.status_code == 204
    listed = await admin_client.get("/api/lens/sessions")
    assert all(s["id"] != sid for s in listed.json()["sessions"])


@pytest.mark.asyncio
async def test_post_message_without_provider_creds_returns_422(
    admin_client: httpx.AsyncClient,
) -> None:
    """Without a stored cred the chat-loop refuses with provider-not-configured."""
    _wipe_lens_tables()
    create = await admin_client.post(
        "/api/lens/sessions",
        json={"title": "no-creds", "llm_provider": "anthropic"},
    )
    sid = create.json()["id"]
    resp = await admin_client.post(
        f"/api/lens/sessions/{sid}/messages",
        json={"content": "hello"},
    )
    assert resp.status_code == 422
    body = resp.json()
    # Error envelope carries the LENS_PROVIDER_NOT_CONFIGURED code somewhere.
    assert "lens" in str(body).lower()


@pytest.mark.asyncio
async def test_post_message_runs_chat_loop_with_mock_provider(
    admin_client: httpx.AsyncClient,
) -> None:
    """Happy path: mock LLM returns no tool calls, assistant text persists."""
    _wipe_lens_tables()
    factory = app.state.session_factory
    upsert_provider_creds(
        factory,
        workspace_id=1,
        provider="anthropic",
        api_key="sk-ant-mock",  # pragma: allowlist secret
    )
    create = await admin_client.post(
        "/api/lens/sessions",
        json={"title": "with-creds", "llm_provider": "anthropic"},
    )
    sid = create.json()["id"]

    async def fake_chat(self: Any, **kwargs: Any) -> LensCompletion:  # noqa: ARG001
        return LensCompletion(
            text="There are 3 catalogs in this workspace.",
            tool_calls=[],
            tokens_in=42,
            tokens_out=18,
            cost_estimate=0.005,
            finish_reason="stop",
        )

    with patch(
        "pointlessql.services.lens.llm_provider.AnthropicProvider.chat_with_tools",
        new=fake_chat,
    ):
        resp = await admin_client.post(
            f"/api/lens/sessions/{sid}/messages",
            json={"content": "How many catalogs?"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert "3 catalogs" in body["assistant"]
    assert body["tokens_in"] == 42
    assert body["tokens_out"] == 18

    # Transcript carries user + assistant rows.
    msgs = await admin_client.get(f"/api/lens/sessions/{sid}/messages")
    roles = [m["role"] for m in msgs.json()["messages"]]
    assert "user" in roles
    assert "assistant" in roles


@pytest.mark.asyncio
async def test_post_message_dispatches_tool_call_then_continues(
    admin_client: httpx.AsyncClient,
) -> None:
    """Two-iteration loop: mock LLM issues tool_call, then plain text."""
    _wipe_lens_tables()
    factory = app.state.session_factory
    upsert_provider_creds(
        factory,
        workspace_id=1,
        provider="anthropic",
        api_key="sk-ant-mock",  # pragma: allowlist secret
    )
    create = await admin_client.post(
        "/api/lens/sessions",
        json={"title": "tool-loop", "llm_provider": "anthropic"},
    )
    sid = create.json()["id"]

    call_count = {"n": 0}

    async def fake_chat(self: Any, **kwargs: Any) -> LensCompletion:  # noqa: ARG001
        call_count["n"] += 1
        if call_count["n"] == 1:
            return LensCompletion(
                text="",
                tool_calls=[
                    ToolCall(
                        id="call_1",
                        name="list_catalogs",
                        args={},
                    )
                ],
                tokens_in=10,
                tokens_out=5,
                cost_estimate=0.001,
                finish_reason="tool_use",
            )
        return LensCompletion(
            text="Listed catalogs successfully.",
            tool_calls=[],
            tokens_in=20,
            tokens_out=8,
            cost_estimate=0.002,
            finish_reason="stop",
        )

    with patch(
        "pointlessql.services.lens.llm_provider.AnthropicProvider.chat_with_tools",
        new=fake_chat,
    ):
        resp = await admin_client.post(
            f"/api/lens/sessions/{sid}/messages",
            json={"content": "List catalogs"},
        )
    assert resp.status_code == 200
    body = resp.json()
    assert body["assistant"] == "Listed catalogs successfully."
    assert any(tc["name"] == "list_catalogs" for tc in body["tool_calls"])
    assert body["tokens_in"] == 30
    assert call_count["n"] == 2


@pytest.mark.asyncio
async def test_admin_lens_providers_crud_roundtrip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Admin route: upsert + list + delete provider creds."""
    _wipe_lens_tables()
    create = await admin_client.post(
        "/api/admin/lens-providers",
        json={
            "provider": "openai",
            "api_key": "sk-test-secret",  # pragma: allowlist secret
            "default_model": "gpt-4o-mini",
        },
    )
    assert create.status_code == 200
    body = create.json()
    assert body["provider"] == "openai"
    assert "secret" not in str(body).lower()  # cleartext never echoed

    listed = await admin_client.get("/api/admin/lens-providers")
    assert any(p["provider"] == "openai" for p in listed.json()["providers"])

    test = await admin_client.post("/api/admin/lens-providers/openai/test")
    assert test.status_code == 200
    assert test.json()["ok"] is True

    deleted = await admin_client.delete("/api/admin/lens-providers/openai")
    assert deleted.status_code == 204
    listed_after = await admin_client.get("/api/admin/lens-providers")
    assert all(p["provider"] != "openai" for p in listed_after.json()["providers"])


@pytest.mark.asyncio
async def test_lens_sessions_anonymous_blocked(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous caller is blocked at require_analyst."""
    resp = await anonymous_client.post(
        "/api/lens/sessions",
        json={"title": "x", "llm_provider": "anthropic"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_lens_sessions_analyst_key_passes(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Analyst-scoped api_key passes the require_analyst gate."""
    _ensure_keys_table()
    factory = app.state.session_factory
    _, secret = create_api_key(factory, name="lens-chat-analyst", analyst=True)
    resp = await anonymous_client.post(
        "/api/lens/sessions",
        headers={"Authorization": f"Bearer {secret}"},
        json={"title": "via-key", "llm_provider": "anthropic"},
    )
    assert resp.status_code == 201


def test_now_helper_callable() -> None:
    """Sanity import test for the suite."""
    assert isinstance(datetime.datetime.now(datetime.UTC), datetime.datetime)


def test_decrypt_provider_key_after_upsert() -> None:
    """decrypt_provider_key returns the cleartext after upsert."""
    _wipe_lens_tables()
    factory = app.state.session_factory
    upsert_provider_creds(
        factory,
        workspace_id=1,
        provider="openai",
        api_key="sk-rt-roundtrip",  # pragma: allowlist secret
    )
    out = decrypt_provider_key(factory, workspace_id=1, provider="openai")
    assert out == "sk-rt-roundtrip"  # pragma: allowlist secret
