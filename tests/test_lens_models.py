"""Smoke tests for the Lens persistence layer.

Pin the table shapes, scope-isolation rules, and Fernet roundtrip
that every later sprint depends on.  These run cheap (in-memory
SQLite via the project's ``app.state.session_factory``) and serve as
a canary if a model change accidentally drifts the column set.
"""

from __future__ import annotations

import datetime

import pytest

from pointlessql.api.main import app
from pointlessql.models import (
    LENS_PROVIDERS,
    ApiKey,
    LensMessage,
    LensPinnedAnswer,
    LensProviderCreds,
    LensSession,
    User,
)
from pointlessql.services.lens import (
    append_message,
    create_session,
    decrypt_provider_key,
    delete_provider_creds,
    delete_session,
    get_session,
    list_provider_creds,
    list_session_messages,
    list_sessions,
    upsert_provider_creds,
)
from pointlessql.services.lens._provider_creds import UnknownLensProviderError


def _create_user(*, email: str) -> int:
    """Insert a fresh user and return its id."""
    factory = app.state.session_factory
    with factory() as session:
        user = User(
            email=email,
            display_name=email.split("@", 1)[0],
            password_hash="x",
            is_admin=False,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(user)
        session.commit()
        return int(user.id)


def test_lens_providers_pinned() -> None:
    """``LENS_PROVIDERS`` exposes the recognised provider names."""
    assert set(LENS_PROVIDERS) == {"openai", "anthropic", "kimi", "grok"}


def test_lens_session_columns_present() -> None:
    """Session model carries every column the chat-loop expects."""
    cols = {c.name for c in LensSession.__table__.columns}
    assert {
        "id",
        "workspace_id",
        "owner_id",
        "title",
        "llm_provider",
        "llm_model",
        "total_cost_estimate",
        "created_at",
        "updated_at",
        "last_message_at",
    } <= cols


def test_lens_message_columns_present() -> None:
    """Message model carries the role-flexible payload columns."""
    cols = {c.name for c in LensMessage.__table__.columns}
    assert {
        "id",
        "session_id",
        "role",
        "content",
        "tool_name",
        "tool_args",
        "tool_result",
        "tool_status",
        "tokens_in",
        "tokens_out",
        "cost_estimate",
        "duration_ms",
        "created_at",
    } <= cols


def test_lens_pinned_answer_columns_present() -> None:
    """Pinned-answer carries the snapshot columns."""
    cols = {c.name for c in LensPinnedAnswer.__table__.columns}
    assert {
        "id",
        "workspace_id",
        "owner_id",
        "slug",
        "title",
        "source_message_id",
        "content_snapshot",
        "sql_text",
        "result_preview",
        "is_shared",
    } <= cols


def test_lens_provider_creds_columns_present() -> None:
    """Provider-creds carries Fernet ciphertext + provider PK."""
    cols = {c.name for c in LensProviderCreds.__table__.columns}
    assert {
        "workspace_id",
        "provider",
        "api_key_encrypted",
        "default_model",
        "enabled",
    } <= cols


def test_api_keys_carries_analyst_column() -> None:
    """Sprint 65.0 added ``api_keys.analyst`` boolean."""
    assert "analyst" in {c.name for c in ApiKey.__table__.columns}


def test_session_create_get_list_delete_roundtrip() -> None:
    """End-to-end: create → get → list → delete a Lens session."""
    factory = app.state.session_factory
    owner_id = _create_user(email="lens-tester@example.com")
    row = create_session(
        factory,
        workspace_id=1,
        owner_id=owner_id,
        title="Q1: revenue by region",
        llm_provider="anthropic",
        llm_model="claude-haiku-4-5-20251001",
    )
    assert row.id > 0
    assert row.title == "Q1: revenue by region"
    assert row.last_message_at is None

    fetched = get_session(
        factory,
        session_id=row.id,
        workspace_id=1,
        owner_id=owner_id,
    )
    assert fetched.id == row.id

    listed = list_sessions(factory, workspace_id=1, owner_id=owner_id)
    assert any(r.id == row.id for r in listed)

    deleted = delete_session(
        factory,
        session_id=row.id,
        workspace_id=1,
        owner_id=owner_id,
    )
    assert deleted is True


def test_message_append_bumps_last_message_at() -> None:
    """Appending a message updates the session's ``last_message_at``."""
    factory = app.state.session_factory
    owner_id = _create_user(email="lens-msg@example.com")

    row = create_session(
        factory,
        workspace_id=1,
        owner_id=owner_id,
        title="msg-test",
        llm_provider="openai",
        llm_model="gpt-4o-mini",
    )

    append_message(
        factory,
        session_id=row.id,
        role="user",
        content="How many catalogs are there?",
    )
    append_message(
        factory,
        session_id=row.id,
        role="tool",
        content="Called list_catalogs",
        tool_name="list_catalogs",
        tool_args={},
        tool_result={"count": 3},
        tool_status="ok",
        cost_estimate=10.0,
        duration_ms=12,
    )

    msgs = list_session_messages(factory, session_id=row.id)
    assert len(msgs) == 2
    assert msgs[0].role == "user"
    assert msgs[1].role == "tool"
    assert msgs[1].cost_estimate == 10.0

    refreshed = get_session(
        factory,
        session_id=row.id,
        workspace_id=1,
        owner_id=owner_id,
    )
    assert refreshed.last_message_at is not None
    assert refreshed.total_cost_estimate >= 10.0


def test_provider_creds_fernet_roundtrip() -> None:
    """Storing + retrieving a credential roundtrips the cleartext."""
    factory = app.state.session_factory
    upserted = upsert_provider_creds(
        factory,
        workspace_id=1,
        provider="anthropic",
        api_key="sk-ant-test-secret",  # pragma: allowlist secret
        default_model="claude-haiku-4-5-20251001",
    )
    assert upserted.provider == "anthropic"
    assert "sk-ant-test-secret" not in upserted.api_key_encrypted

    cleartext = decrypt_provider_key(
        factory,
        workspace_id=1,
        provider="anthropic",
    )
    assert cleartext == "sk-ant-test-secret"  # pragma: allowlist secret

    rows = list_provider_creds(factory, workspace_id=1)
    assert any(r.provider == "anthropic" for r in rows)

    delete_provider_creds(factory, workspace_id=1, provider="anthropic")
    assert decrypt_provider_key(factory, workspace_id=1, provider="anthropic") is None


def test_provider_creds_unknown_provider_raises() -> None:
    """Bogus provider name fails fast."""
    factory = app.state.session_factory
    with pytest.raises(UnknownLensProviderError):
        upsert_provider_creds(
            factory,
            workspace_id=1,
            provider="bogus",
            api_key="x",
        )
