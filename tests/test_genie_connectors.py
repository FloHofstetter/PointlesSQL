"""Tests for Genie bot connectors (registry, token auth, Teams webhook)."""

from __future__ import annotations

import hashlib

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.exceptions import ValidationError
from pointlessql.services import genie_connectors, genie_teams


def _factory():
    return fastapi_app.state.session_factory


# --------------------------------------------------------------------------
# Pure Bot Framework Activity adapter
# --------------------------------------------------------------------------


def test_strip_mention_handles_at_tags_and_bare_prefix() -> None:
    assert genie_teams.strip_mention("<at>Genie</at> how many orders?") == "how many orders?"
    assert genie_teams.strip_mention("@Genie  show revenue") == "show revenue"
    assert genie_teams.strip_mention("  plain   question ") == "plain question"


def test_parse_activity_defaults_missing_fields() -> None:
    parsed = genie_teams.parse_activity({"type": "message", "text": "hi", "channelId": "msteams"})
    assert parsed["type"] == "message"
    assert parsed["text"] == "hi"
    assert parsed["channel_id"] == "msteams"
    assert parsed["conversation"] is None
    # An empty payload never raises.
    assert genie_teams.parse_activity({})["text"] == ""


def test_is_message_and_extract_question() -> None:
    assert genie_teams.is_message({"type": "message"}) is True
    assert genie_teams.is_message({"type": "conversationUpdate"}) is False
    assert genie_teams.extract_question({"text": "<at>Genie</at> total sales"}) == "total sales"


def test_build_reply_activity_swaps_roles_and_threads() -> None:
    incoming = {
        "id": "act-1",
        "from": {"id": "user-1"},
        "recipient": {"id": "bot-1"},
        "conversation": {"id": "conv-1"},
        "channelId": "msteams",
        "serviceUrl": "https://smba.example/",
    }
    reply = genie_teams.build_reply_activity(incoming, "the answer")
    assert reply["type"] == "message"
    assert reply["text"] == "the answer"
    assert reply["replyToId"] == "act-1"
    assert reply["from"] == {"id": "bot-1"}  # bot now sends
    assert reply["recipient"] == {"id": "user-1"}
    assert reply["conversation"] == {"id": "conv-1"}


# --------------------------------------------------------------------------
# Token hashing + registry service
# --------------------------------------------------------------------------


def test_token_hash_roundtrip() -> None:
    digest = hashlib.sha256(b"secret-token").hexdigest()
    assert genie_connectors.verify_token(digest, "secret-token") is True
    assert genie_connectors.verify_token(digest, "wrong-token") is False


def test_create_lists_and_serializes_without_hash() -> None:
    connector, token = genie_connectors.create_connector(
        _factory(),
        workspace_id=1,
        name="sales-genie",
        platform="teams",
        genie_space_slug=None,
        created_by="admin@test",
    )
    assert token.startswith("pqlbot_")
    assert "token_hash" not in connector  # the hash never leaves the service
    assert connector["messaging_path"] == f"/api/genie/teams/{connector['public_id']}/messages"
    listed = genie_connectors.list_connectors(_factory(), workspace_id=1)
    assert any(c["name"] == "sales-genie" for c in listed)


def test_create_rejects_blank_duplicate_and_bad_platform() -> None:
    with pytest.raises(ValidationError, match="name is required"):
        genie_connectors.create_connector(_factory(), workspace_id=1, name="  ")
    with pytest.raises(ValidationError, match="unknown connector platform"):
        genie_connectors.create_connector(_factory(), workspace_id=1, name="x", platform="slack")
    genie_connectors.create_connector(_factory(), workspace_id=1, name="dup")
    with pytest.raises(ValidationError, match="already exists"):
        genie_connectors.create_connector(_factory(), workspace_id=1, name="dup")


def test_update_binds_space_and_toggles_enabled() -> None:
    connector, _ = genie_connectors.create_connector(_factory(), workspace_id=1, name="bind-me")
    updated = genie_connectors.update_connector(
        _factory(),
        connector_id=connector["id"],
        workspace_id=1,
        genie_space_slug="my-space",
        enabled=False,
    )
    assert updated["genie_space_slug"] == "my-space"
    assert updated["enabled"] is False
    # Omitting genie_space_slug leaves the binding intact.
    again = genie_connectors.update_connector(
        _factory(), connector_id=connector["id"], workspace_id=1, enabled=True
    )
    assert again["genie_space_slug"] == "my-space"
    assert again["enabled"] is True


def test_rotate_invalidates_old_token() -> None:
    connector, old = genie_connectors.create_connector(_factory(), workspace_id=1, name="rot")
    _, new = genie_connectors.rotate_token(_factory(), connector_id=connector["id"], workspace_id=1)
    assert new != old
    assert (
        genie_connectors.authenticate(
            _factory(), public_id=connector["public_id"], presented_token=old
        )
        is None
    )
    assert (
        genie_connectors.authenticate(
            _factory(), public_id=connector["public_id"], presented_token=new
        )
        is not None
    )


def test_authenticate_rejects_disabled_and_bad_token() -> None:
    connector, token = genie_connectors.create_connector(_factory(), workspace_id=1, name="auth")
    pid = connector["public_id"]
    assert genie_connectors.authenticate(_factory(), public_id=pid, presented_token="nope") is None
    genie_connectors.update_connector(
        _factory(), connector_id=connector["id"], workspace_id=1, enabled=False
    )
    assert genie_connectors.authenticate(_factory(), public_id=pid, presented_token=token) is None


def test_delete_connector() -> None:
    connector, _ = genie_connectors.create_connector(_factory(), workspace_id=1, name="del")
    assert (
        genie_connectors.delete_connector(_factory(), connector_id=connector["id"], workspace_id=1)
        is True
    )
    assert (
        genie_connectors.delete_connector(_factory(), connector_id=connector["id"], workspace_id=1)
        is False
    )


# --------------------------------------------------------------------------
# Inbound Teams webhook
# --------------------------------------------------------------------------


def _seed_connector(name: str = "hook-bot") -> tuple[str, str]:
    connector, token = genie_connectors.create_connector(
        _factory(), workspace_id=1, name=name, platform="teams", created_by="admin@test"
    )
    return connector["public_id"], token


@pytest.mark.asyncio
async def test_webhook_rejects_missing_or_bad_token(anonymous_client: httpx.AsyncClient) -> None:
    public_id, _ = _seed_connector("bad-token-bot")
    no_auth = await anonymous_client.post(
        f"/api/genie/teams/{public_id}/messages", json={"type": "message", "text": "hi"}
    )
    assert no_auth.status_code == 401, no_auth.text
    bad = await anonymous_client.post(
        f"/api/genie/teams/{public_id}/messages",
        json={"type": "message", "text": "hi"},
        headers={"Authorization": "Bearer nope"},
    )
    assert bad.status_code == 401, bad.text


@pytest.mark.asyncio
async def test_webhook_answers_unbound_connector(anonymous_client: httpx.AsyncClient) -> None:
    public_id, token = _seed_connector("unbound-bot")
    activity = {
        "type": "message",
        "id": "act-1",
        "text": "<at>Genie</at> how many orders?",
        "from": {"id": "user-1"},
        "recipient": {"id": "bot-1"},
        "conversation": {"id": "conv-1"},
        "channelId": "msteams",
    }
    resp = await anonymous_client.post(
        f"/api/genie/teams/{public_id}/messages",
        json=activity,
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    reply = resp.json()
    assert reply["type"] == "message"
    assert reply["replyToId"] == "act-1"
    assert reply["recipient"] == {"id": "user-1"}  # swapped back to the asker
    assert "isn't bound" in reply["text"]


@pytest.mark.asyncio
async def test_webhook_ignores_non_message_activity(anonymous_client: httpx.AsyncClient) -> None:
    public_id, token = _seed_connector("ack-bot")
    resp = await anonymous_client.post(
        f"/api/genie/teams/{public_id}/messages",
        json={"type": "conversationUpdate"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["ignored"] is True


# --------------------------------------------------------------------------
# Admin console
# --------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_create_returns_one_time_token(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.post(
        "/api/admin/genie-connectors", json={"name": "console-bot", "platform": "teams"}
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["token"].startswith("pqlbot_")
    assert data["connector"]["name"] == "console-bot"
    listed = await admin_client.get("/api/admin/genie-connectors")
    assert any(c["name"] == "console-bot" for c in listed.json()["connectors"])


@pytest.mark.asyncio
async def test_admin_create_forbidden_for_non_admin(non_admin_client: httpx.AsyncClient) -> None:
    resp = await non_admin_client.post("/api/admin/genie-connectors", json={"name": "x"})
    assert resp.status_code == 403, resp.text
