"""Phase 97.X.3 — pin-to-memory feed-card classification.

The pin path ([api/notebooks_routes/facts.py]) emits a
``notebook_revision_pinned`` event through
:func:`pointlessql.services.notifications.fanout_event`.  Phase 97.X.3
adds a dedicated ``render_kind = "fact"`` so the feed Alpine renderer
shows a 📌-icon card instead of falling through to the generic
notification template.

Coverage:

* :func:`classify_notification` maps the literal event-type token
  to ``"fact"``.
* :func:`row_from_notification` carries that ``render_kind`` through
  to the feed-row dict the Alpine renderer consumes.
* The end-to-end ``fanout_event`` write still stamps the polymorphic
  ``source_entity_kind`` / ``source_entity_ref`` columns the
  ``entity_registry`` resolver depends on for the click target.
* Agent-attributed pins (``actor_user_id IS NULL``) still classify
  to ``"fact"`` so the icon does not disappear when the pin came
  from ``pql.facts.pin(...)`` rather than the UI button.
"""

from __future__ import annotations

import datetime
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from pointlessql.api.feed_routes._serializers import (
    classify_notification,
    row_from_notification,
)
from pointlessql.api.main import app
from pointlessql.models.notifications import UserNotification
from pointlessql.services.notifications import fanout_event


def test_classify_pinned_event_returns_fact_render_kind() -> None:
    """The literal event-type token maps to ``"fact"``."""
    assert classify_notification("notebook_revision_pinned") == "fact"


def test_classify_unrelated_event_still_falls_through_to_notification() -> None:
    """Sibling tokens stay on the generic bucket — proves the branch is exact."""
    assert classify_notification("notebook_revision_unpinned") == "notification"
    assert classify_notification("notebook_revision") == "notification"
    assert classify_notification("") == "notification"


def test_row_from_notification_pinned_event_carries_fact_render_kind() -> None:
    """``row_from_notification`` propagates ``render_kind="fact"`` + URL."""
    fact_uuid = "11111111-2222-3333-4444-555555555555"
    row = UserNotification(
        id=42,
        workspace_id=1,
        recipient_user_id=7,
        event_type="notebook_revision_pinned",
        source_data_product_id=None,
        source_entity_kind="notebook_revision",
        source_entity_ref=fact_uuid,
        source_url=f"/library/facts/{fact_uuid}",
        summary_md="alice pinned 'Q3 anomaly' from sales_audit.py",
        actor_user_id=3,
        read_at=None,
        created_at=datetime.datetime(2026, 5, 21, 12, 0, tzinfo=datetime.UTC),
    )
    envelope = row_from_notification(
        row,
        fqn_map={},
        actor_names={3: "alice"},
    )
    assert envelope["render_kind"] == "fact"
    assert envelope["event_type"] == "notebook_revision_pinned"
    assert envelope["source_url"] == f"/library/facts/{fact_uuid}"
    assert envelope["entity_kind"] == "notebook_revision"
    assert envelope["entity_ref"] == fact_uuid
    assert envelope["actor_display_name"] == "alice"


def test_row_from_notification_pinned_event_with_null_actor() -> None:
    """Agent-attributed pins (``actor_user_id is None``) still classify as fact."""
    fact_uuid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    row = UserNotification(
        id=99,
        workspace_id=1,
        recipient_user_id=7,
        event_type="notebook_revision_pinned",
        source_data_product_id=None,
        source_entity_kind="notebook_cell_output",
        source_entity_ref=fact_uuid,
        source_url=f"/library/facts/{fact_uuid}",
        summary_md="steward-agent pinned an output",
        actor_user_id=None,
        read_at=None,
        created_at=datetime.datetime(2026, 5, 21, 12, 0, tzinfo=datetime.UTC),
    )
    envelope = row_from_notification(
        row,
        fqn_map={},
        actor_names={},
    )
    assert envelope["render_kind"] == "fact"
    assert envelope["actor_user_id"] is None
    assert envelope["actor_display_name"] is None


@pytest.fixture
def admin_user_id() -> int:
    """Resolve the admin seeded by ``tests/conftest.py``."""
    factory = app.state.session_factory
    with factory() as session:
        from pointlessql.models.auth import User

        return int(
            session.execute(
                select(User.id).where(User.email == "test@test.com")
            ).scalar_one()
        )


@pytest.fixture
def nonadmin_user_id() -> int:
    """Resolve the non-admin seeded by ``tests/conftest.py``."""
    factory = app.state.session_factory
    with factory() as session:
        from pointlessql.models.auth import User

        return int(
            session.execute(
                select(User.id).where(User.email == "nonadmin@test.com")
            ).scalar_one()
        )


@pytest.fixture
def clean_pin_notifications() -> Iterator[None]:
    """Strip any prior ``notebook_revision_pinned`` rows so the e2e is clean."""
    factory = app.state.session_factory
    with factory() as session:
        session.execute(
            delete(UserNotification).where(
                UserNotification.event_type == "notebook_revision_pinned"
            )
        )
        session.commit()
    yield
    with factory() as session:
        session.execute(
            delete(UserNotification).where(
                UserNotification.event_type == "notebook_revision_pinned"
            )
        )
        session.commit()


def test_fanout_event_pinned_writes_polymorphic_marker(
    tmp_path: Path,
    admin_user_id: int,
    nonadmin_user_id: int,
    clean_pin_notifications: None,
) -> None:
    """End-to-end: the pin event writes a row with the right polymorphic marker."""
    del clean_pin_notifications, tmp_path
    fact_uuid = "deadbeef-1234-5678-9abc-def012345678"
    factory = app.state.session_factory
    fanout_event(
        factory,
        event_type="notebook_revision_pinned",
        entity_kind="notebook_revision",
        entity_ref=fact_uuid,
        workspace_id=1,
        actor_user_id=admin_user_id,
        source_url=f"/library/facts/{fact_uuid}",
        summary_md="phase 97.X.3 marker test",
        extra_recipients=[nonadmin_user_id],
    )
    with factory() as session:
        row = session.execute(
            select(UserNotification).where(
                UserNotification.event_type == "notebook_revision_pinned"
            )
        ).scalar_one()
        assert row.source_entity_kind == "notebook_revision"
        assert row.source_entity_ref == fact_uuid
        assert row.source_url == f"/library/facts/{fact_uuid}"
        assert row.actor_user_id == admin_user_id
        assert row.recipient_user_id == nonadmin_user_id
        # The renderer-facing envelope reports ``render_kind == "fact"``.
        envelope = row_from_notification(row, fqn_map={}, actor_names={})
        assert envelope["render_kind"] == "fact"
