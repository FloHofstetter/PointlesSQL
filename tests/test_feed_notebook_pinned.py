"""pin-to-memory feed-card classification.

The pin path ([api/notebooks_routes/facts.py]) emits a
``notebook_revision_pinned`` event through
:func:`pointlessql.services.notifications.fanout_event` with a
dedicated ``render_kind = "fact"`` so the feed Alpine renderer
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
            session.execute(select(User.id).where(User.email == "test@test.com")).scalar_one()
        )


@pytest.fixture
def nonadmin_user_id() -> int:
    """Resolve the non-admin seeded by ``tests/conftest.py``."""
    factory = app.state.session_factory
    with factory() as session:
        from pointlessql.models.auth import User

        return int(
            session.execute(select(User.id).where(User.email == "nonadmin@test.com")).scalar_one()
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


def test_resolve_notebook_followers_pulls_subscribers(
    admin_user_id: int,
    nonadmin_user_id: int,
    clean_pin_notifications: None,
) -> None:
    """The pin helper looks up notebook-level followers, not pin-level."""
    del clean_pin_notifications
    import datetime
    import uuid

    from pointlessql.api.notebooks_routes.facts import (
        _resolve_notebook_followers,
    )
    from pointlessql.models import Notebook
    from pointlessql.models.social._social_follow import SocialFollow
    from pointlessql.services.social import get_or_create_target

    nb_id = str(uuid.uuid4())
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            Notebook(
                id=nb_id,
                workspace_id=1,
                file_path=f"fanout-test-{nb_id[:8]}.py",
            )
        )
        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="notebook",
            ref=nb_id,
        )
        session.add(
            SocialFollow(
                workspace_id=1,
                social_target_id=int(anchor.id),
                user_id=nonadmin_user_id,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()
    followers = _resolve_notebook_followers(
        factory,
        workspace_id=1,
        notebook_id=nb_id,
    )
    assert nonadmin_user_id in followers
    # The actor (admin) is *not* in the follower set — admin hasn't followed.
    assert admin_user_id not in followers


def test_emit_pin_summary_uses_notebook_path_not_uuid(
    admin_user_id: int,
    nonadmin_user_id: int,
    clean_pin_notifications: None,
) -> None:
    """``summary_md`` resolves the notebook ``file_path`` so the feed
    card never surfaces a raw 36-char UUID to the user."""
    del clean_pin_notifications
    import datetime
    import uuid
    from unittest.mock import MagicMock

    from pointlessql.api.notebooks_routes.facts import _emit_pin_feed_event
    from pointlessql.models import Notebook
    from pointlessql.models.social._social_follow import SocialFollow
    from pointlessql.services.social import get_or_create_target

    nb_id = str(uuid.uuid4())
    file_path = f"smoke-pin-summary-{nb_id[:8]}.py"
    factory = app.state.session_factory
    with factory() as session:
        session.add(Notebook(id=nb_id, workspace_id=1, file_path=file_path))
        anchor = get_or_create_target(session, workspace_id=1, kind="notebook", ref=nb_id)
        session.add(
            SocialFollow(
                workspace_id=1,
                social_target_id=int(anchor.id),
                user_id=nonadmin_user_id,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()

    fake_request = MagicMock()
    fake_request.app.state.session_factory = factory
    envelope = {
        "fact_uuid": str(uuid.uuid4()),
        "notebook_id": nb_id,
        "cell_content_hash": None,
        "title": "Smoke pin",
    }
    _emit_pin_feed_event(
        fake_request,
        envelope=envelope,
        workspace_id=1,
        actor_user_id=admin_user_id,
    )
    with factory() as session:
        row = session.execute(
            select(UserNotification).where(
                UserNotification.event_type == "notebook_revision_pinned",
                UserNotification.recipient_user_id == nonadmin_user_id,
            )
        ).scalar_one()
        assert file_path in row.summary_md, row.summary_md
        # Crucially: the 36-char notebook UUID must NOT appear in the
        # rendered summary line — that's the regression we're guarding.
        assert nb_id not in row.summary_md, row.summary_md
