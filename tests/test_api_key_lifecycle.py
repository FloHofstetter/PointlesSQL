"""Tests for the Phase 119 API-key lifecycle gates in ``verify_bearer``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from pointlessql.api.main import app
from pointlessql.models import ApiKey, AuditLog
from pointlessql.services import api_keys as api_keys_service


def _wipe() -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.query(ApiKey).delete()
        session.query(AuditLog).delete()
        session.commit()
    api_keys_service.invalidate_cache()


def _set_columns(name: str, **values: object) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.execute(update(ApiKey).where(ApiKey.name == name).values(**values))
        session.commit()
    api_keys_service.invalidate_cache()


def _latest_audit_actions() -> list[str]:
    factory = app.state.session_factory
    with factory() as session:
        rows = session.scalars(
            select(AuditLog).order_by(AuditLog.created_at.desc()).limit(20)
        ).all()
        return [row.action for row in rows]


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------


def test_unexpired_key_authorises() -> None:
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="future"
    )
    _set_columns("future", expires_at=datetime.now(UTC) + timedelta(days=7))
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is not None and entry.name == "future"
    _wipe()


def test_expired_key_is_rejected_and_audits() -> None:
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="past"
    )
    _set_columns("past", expires_at=datetime.now(UTC) - timedelta(seconds=5))
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is None
    assert "api_key.auth_denied.expired" in _latest_audit_actions()
    _wipe()


def test_key_with_no_expiry_authorises_indefinitely() -> None:
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="forever"
    )
    # expires_at is None by default — back-compat behaviour preserved.
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is not None
    _wipe()


# ---------------------------------------------------------------------------
# Quarantine
# ---------------------------------------------------------------------------


def test_quarantined_key_is_rejected_and_audits() -> None:
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="naughty"
    )
    _set_columns(
        "naughty",
        quarantined_at=datetime.now(UTC),
        quarantine_reason="compromise drill",
    )
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is None
    assert "api_key.auth_denied.quarantined" in _latest_audit_actions()
    _wipe()


def test_quarantined_at_without_reason_does_not_block() -> None:
    """Belt + suspenders — both columns must be set to count as quarantine."""
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="half-set"
    )
    _set_columns("half-set", quarantined_at=datetime.now(UTC))  # reason still NULL
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is not None
    _wipe()


# ---------------------------------------------------------------------------
# Rotation grace window
# ---------------------------------------------------------------------------


def test_predecessor_in_grace_window_still_authorises() -> None:
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="pred-in-grace"
    )
    _set_columns(
        "pred-in-grace",
        rotated_at=datetime.now(UTC) - timedelta(minutes=5),
        grace_until=datetime.now(UTC) + timedelta(hours=23),
    )
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is not None
    _wipe()


def test_predecessor_past_grace_is_rejected_and_audits() -> None:
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="pred-stale"
    )
    _set_columns(
        "pred-stale",
        rotated_at=datetime.now(UTC) - timedelta(days=2),
        grace_until=datetime.now(UTC) - timedelta(hours=1),
    )
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is None
    assert "api_key.auth_denied.rotated" in _latest_audit_actions()
    _wipe()


def test_predecessor_without_grace_until_is_rejected() -> None:
    """rotated_at set + grace_until NULL → predecessor blocked immediately."""
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="pred-no-grace"
    )
    _set_columns("pred-no-grace", rotated_at=datetime.now(UTC))
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is None
    _wipe()


def test_lifecycle_gates_do_not_break_back_compat_for_legacy_keys() -> None:
    """A pre-119 key (all NULL lifecycle cols) still verifies normally."""
    _wipe()
    _, plaintext = api_keys_service.create_api_key(
        app.state.session_factory, name="legacy-style"
    )
    # All lifecycle cols are NULL by default — verify the no-op path.
    entry = api_keys_service.verify_bearer(f"Bearer {plaintext}", app.state.session_factory)
    assert entry is not None and entry.name == "legacy-style"
    _wipe()
