"""Tests for the audit-detail PII redactor.

Covers the new ``redact_audit_detail`` helper and its wiring through
``log_action`` behind the ``audit.redact_detail_payloads`` setting.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.models import AuditLog
from pointlessql.models.base import Base
from pointlessql.models.system_keys import SystemKey  # noqa: F401  (table registration)
from pointlessql.services.audit import log_action
from pointlessql.services.pii import redact_audit_detail
from pointlessql.services.pii._redactor import REDACTED_PLACEHOLDER


@pytest.fixture()
def factory() -> sessionmaker[Session]:
    """In-memory SQLite with the audit + system-key tables seeded."""
    engine = create_engine(
        "sqlite:///:memory:", future=True, connect_args={"check_same_thread": False}
    )
    Base.metadata.create_all(engine, tables=[AuditLog.__table__, SystemKey.__table__])
    return sessionmaker(bind=engine, expire_on_commit=False)


# ---------------------------------------------------------------------
# redact_audit_detail — pure-function behaviour
# ---------------------------------------------------------------------


def test_none_passthrough() -> None:
    assert redact_audit_detail(None) is None


def test_string_passthrough() -> None:
    assert redact_audit_detail("opaque string") == "opaque string"


def test_store_clear_mode_passes_dict_through(factory: sessionmaker[Session]) -> None:
    payload = {"email": "alice@example.com", "note": "hi"}
    assert redact_audit_detail(payload, mode="store_clear", session_factory=factory) == payload


def test_flat_dict_redacts_pii_keys_default_mode() -> None:
    out = redact_audit_detail({"email": "alice@example.com", "note": "hi"})
    assert out == {"email": REDACTED_PLACEHOLDER, "note": "hi"}


def test_nested_dict_redacts_recursively() -> None:
    out = redact_audit_detail({"actor": {"email": "x@y.z", "id": 7}, "extra": "value"})
    assert out == {
        "actor": {"email": REDACTED_PLACEHOLDER, "id": 7},
        "extra": "value",
    }


def test_nested_list_walked_element_wise() -> None:
    """Lists inside dict values are walked recursively."""
    out = redact_audit_detail({"actors": [{"email": "a@b"}, {"phone": "+12345"}, {"safe": "v"}]})
    assert out == {
        "actors": [
            {"email": REDACTED_PLACEHOLDER},
            {"phone": REDACTED_PLACEHOLDER},
            {"safe": "v"},
        ]
    }


def test_hash_mode_produces_stable_hex(factory: sessionmaker[Session]) -> None:
    out = redact_audit_detail(
        {"email": "alice@example.com"},
        mode="hash_only",
        session_factory=factory,
    )
    assert isinstance(out, dict)
    digest = out["email"]
    assert isinstance(digest, str)
    assert len(digest) == 16  # 8-byte prefix → 16 hex chars
    # Same input → same hash (joinability).
    again = redact_audit_detail(
        {"email": "alice@example.com"},
        mode="hash_only",
        session_factory=factory,
    )
    assert isinstance(again, dict)
    assert again["email"] == digest


def test_pii_int_value_yields_placeholder_not_hash() -> None:
    out = redact_audit_detail({"phone": 1234567890})
    assert out == {"phone": REDACTED_PLACEHOLDER}


def test_null_pii_value_round_trips_as_none() -> None:
    out = redact_audit_detail({"email": None, "note": "x"})
    assert out == {"email": None, "note": "x"}


# ---------------------------------------------------------------------
# log_action wiring through audit.redact_detail_payloads
# ---------------------------------------------------------------------


def _read_one_detail(factory: sessionmaker[Session]) -> Any:
    with factory() as session:
        row = session.execute(select(AuditLog)).scalars().one()
    return json.loads(row.detail) if row.detail else None


def test_log_action_default_keeps_cleartext(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Default `audit.redact_detail_payloads=False` preserves cleartext."""
    from pointlessql.config import get_settings, reset_settings_cache

    reset_settings_cache()
    settings = get_settings()
    assert settings.audit.redact_detail_payloads is False

    log_action(
        factory,
        user_id=1,
        user_email="op@example.com",
        action="test_action",
        target="resource",
        detail={"email": "leaked@example.com", "note": "hi"},
    )
    assert _read_one_detail(factory) == {
        "email": "leaked@example.com",
        "note": "hi",
    }


def test_log_action_with_flag_redacts_dict_payload(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Flipping the flag pipes detail through the redactor."""
    monkeypatch.setenv("POINTLESSQL_AUDIT_REDACT_DETAIL_PAYLOADS", "true")
    monkeypatch.setenv("POINTLESSQL_AUDIT_PII_MODE", "redact_with_audit_log")
    from pointlessql.config import reset_settings_cache

    reset_settings_cache()

    log_action(
        factory,
        user_id=1,
        user_email="op@example.com",
        action="test_action",
        target="resource",
        detail={"email": "leaked@example.com", "note": "hi"},
    )
    assert _read_one_detail(factory) == {
        "email": REDACTED_PLACEHOLDER,
        "note": "hi",
    }


def test_log_action_with_flag_and_hash_mode_writes_digest(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POINTLESSQL_AUDIT_REDACT_DETAIL_PAYLOADS", "true")
    monkeypatch.setenv("POINTLESSQL_AUDIT_PII_MODE", "hash_only")
    from pointlessql.config import reset_settings_cache

    reset_settings_cache()

    log_action(
        factory,
        user_id=1,
        user_email="op@example.com",
        action="test_action",
        target="resource",
        detail={"email": "leaked@example.com", "note": "hi"},
    )
    written = _read_one_detail(factory)
    assert isinstance(written, dict)
    assert written["note"] == "hi"
    assert isinstance(written["email"], str)
    assert len(written["email"]) == 16


def test_log_action_string_detail_unaffected_by_flag(
    factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("POINTLESSQL_AUDIT_REDACT_DETAIL_PAYLOADS", "true")
    from pointlessql.config import reset_settings_cache

    reset_settings_cache()

    log_action(
        factory,
        user_id=1,
        user_email="op@example.com",
        action="test_action",
        target="resource",
        detail="plain string detail",
    )
    with factory() as session:
        row = session.execute(select(AuditLog)).scalars().one()
    assert row.detail == "plain string detail"
