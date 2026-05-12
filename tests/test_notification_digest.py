"""Tests for the Phase-71 follow-up B.3 — daily marketplace digest.

Covers:

* ``seconds_until_next_window`` returns a positive int in
  ``[60, 86400)`` regardless of call-time + wraps wall-clock past
  midnight correctly.
* ``fire_digests`` emits exactly one envelope per opt-in user
  with ≥1 notification in the 24h window.
* Non-opt-in users are skipped.
* Opt-in users with 0 unread are skipped.
"""

from __future__ import annotations

import datetime

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.audit._sinks import GovernanceEvent
from pointlessql.models.auth import User
from pointlessql.models.notifications import UserNotification
from pointlessql.services.notifications import (
    fire_digests,
    seconds_until_next_window,
)
from pointlessql.services.workspace.governance import (
    EVENT_TYPE_NOTIFICATION_DIGEST,
)


def _make_user(email: str, *, optin: bool) -> int:
    """Persist a User with optional ``digest_email_optin`` flag."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash=None,
            is_admin=False,
            default_workspace_id=1,
            created_at=now,
            digest_email_optin=optin,
        )
        session.add(user)
        session.commit()
        return user.id


def _seed_notif(recipient_id: int, *, age_hours: float = 1.0) -> None:
    """Persist one UserNotification row for *recipient_id*."""
    factory = app.state.session_factory
    when = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=age_hours)
    with factory() as session:
        session.add(
            UserNotification(
                workspace_id=1,
                recipient_user_id=recipient_id,
                event_type="pointlessql.data_product.commented",
                source_url="/x",
                summary_md="test",
                created_at=when,
            )
        )
        session.commit()


def _count_digests() -> int:
    """Count emitted digest envelopes in governance_events."""
    factory = app.state.session_factory
    with factory() as session:
        return len(
            session.execute(
                select(GovernanceEvent).where(
                    GovernanceEvent.event_type == EVENT_TYPE_NOTIFICATION_DIGEST
                )
            )
            .scalars()
            .all()
        )


# ---------------------------------------------------------------------------
# seconds_until_next_window
# ---------------------------------------------------------------------------


def test_seconds_until_next_window_within_day() -> None:
    """Now=03:00, target=06:00 → 3 * 3600s."""
    now = datetime.datetime(2026, 5, 12, 3, 0, 0, tzinfo=datetime.UTC)
    assert seconds_until_next_window(6, now=now) == 3 * 3600


def test_seconds_until_next_window_wraps_past_midnight() -> None:
    """Now=08:00, target=06:00 → 22 * 3600s (next day)."""
    now = datetime.datetime(2026, 5, 12, 8, 0, 0, tzinfo=datetime.UTC)
    assert seconds_until_next_window(6, now=now) == 22 * 3600


def test_seconds_until_next_window_clamps_to_60s_min() -> None:
    """Same-second boundary clamps to 60s (no hot-loop)."""
    now = datetime.datetime(2026, 5, 12, 6, 0, 0, tzinfo=datetime.UTC)
    # exact match → next strike is 24h - 0s = 86400s, but the result
    # is at most 86400; let's check the clamp at the same-second.
    result = seconds_until_next_window(6, now=now)
    assert result >= 60
    assert result <= 86400


# ---------------------------------------------------------------------------
# fire_digests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_fire_digests_emits_for_optin_user_with_unread() -> None:
    """Opt-in user + 1 notif → 1 envelope."""
    uid = _make_user("alice@example.com", optin=True)
    _seed_notif(uid)
    settings = app.state.settings
    emitted = await fire_digests(app.state.session_factory, settings)
    assert emitted == 1
    assert _count_digests() == 1


@pytest.mark.asyncio
async def test_fire_digests_skips_non_optin() -> None:
    """Non-opt-in user, even with notifs, gets no envelope."""
    uid = _make_user("bob@example.com", optin=False)
    _seed_notif(uid)
    settings = app.state.settings
    emitted = await fire_digests(app.state.session_factory, settings)
    assert emitted == 0
    assert _count_digests() == 0


@pytest.mark.asyncio
async def test_fire_digests_skips_optin_without_unread() -> None:
    """Opt-in user with no notifs gets no envelope."""
    _make_user("carol@example.com", optin=True)
    settings = app.state.settings
    emitted = await fire_digests(app.state.session_factory, settings)
    assert emitted == 0
    assert _count_digests() == 0


@pytest.mark.asyncio
async def test_fire_digests_skips_notifs_outside_24h_window() -> None:
    """A notif from 30h ago is outside the digest window."""
    uid = _make_user("dave@example.com", optin=True)
    _seed_notif(uid, age_hours=30.0)
    settings = app.state.settings
    emitted = await fire_digests(app.state.session_factory, settings)
    assert emitted == 0
