"""Tests for the feed attention tier (act / for_you / ambient).

The feed splits a finite "needs you" inbox — unresolved approvals and
signals (``act``) plus notifications addressed to the reader
(``for_you``) — from an infinite ambient stream (``ambient``). The split
rests on a per-row ``attention`` tier stamped at fan-out time: a directed
recipient (a mention, a reaction-to-author, an approval routed to a
principal) is ``for_you``; a recipient who only got the row because they
follow the entity is ``ambient``.

These tests cover the fan-out stamp (both branches in one fan-out), the
legacy event-type fallback for rows written before the column existed,
and the ``needs_action_count`` / ``unread_for_you_count`` response
fields that power the badge.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._social_follow import SocialFollow
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.notifications.categories import (
    ATTENTION_AMBIENT,
    ATTENTION_FOR_YOU,
    attention_for_event,
)
from pointlessql.services.notifications.fanout import fanout_event
from pointlessql.services.signals import emit_signal

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _user_id(email: str) -> int:
    """Resolve a seeded user's id by email."""
    factory = app.state.session_factory
    with factory() as session:
        return int(session.execute(select(User.id).where(User.email == email)).scalar_one())


def _seed_product(tmp_path: Path) -> int:
    """Seed + load the sample product; return its data_products id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return int(session.execute(select(DataProduct)).scalar_one().id)


def _insert_notification(
    recipient_id: int,
    *,
    event_type: str,
    attention: str | None,
    read: bool = False,
) -> None:
    """Insert one notification row directly for count/fallback tests."""
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            UserNotification(
                workspace_id=1,
                recipient_user_id=recipient_id,
                event_type=event_type,
                source_entity_kind="dp",
                source_entity_ref="main.sales_gold",
                source_url="/data-products/main/sales_gold",
                summary_md="hello",
                attention=attention,
                read_at=now if read else None,
                created_at=now,
            )
        )
        session.commit()


def test_attention_for_event_helper() -> None:
    """A mention is ``for_you``; everything else falls back to ambient."""
    assert attention_for_event("pointlessql.data_product.mentioned") == ATTENTION_FOR_YOU
    assert attention_for_event("pointlessql.data_product.commented") == ATTENTION_AMBIENT
    assert attention_for_event(None) == ATTENTION_AMBIENT


def test_fanout_splits_for_you_and_ambient(tmp_path: Path) -> None:
    """One fan-out stamps a directed recipient for_you, a follower ambient.

    The admin is passed via ``extra_recipients`` (a directed delivery —
    a mention or a routed fact), so their row is ``for_you``. The
    non-admin only follows the product, so their row — from the same
    fan-out — is ``ambient``.
    """
    dp_id = _seed_product(tmp_path)
    admin_id = _user_id("test@test.com")
    non_admin_id = _user_id("nonadmin@test.com")
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        target = SocialTarget(
            workspace_id=1,
            entity_kind="dp",
            entity_ref="main.sales_gold",
            data_product_id=dp_id,
            created_at=now,
        )
        session.add(target)
        session.flush()
        session.add(
            SocialFollow(
                workspace_id=1,
                social_target_id=target.id,
                user_id=non_admin_id,
                created_at=now,
            )
        )
        session.commit()

    inserted = fanout_event(
        factory,
        event_type="pointlessql.data_product.commented",
        entity_kind="dp",
        entity_ref="main.sales_gold",
        workspace_id=1,
        actor_user_id=None,
        source_url="/data-products/main/sales_gold",
        summary_md="A new comment.",
        data_product_id=dp_id,
        extra_recipients=[admin_id],
    )
    assert inserted == 2

    with factory() as session:
        admin_row = session.execute(
            select(UserNotification).where(UserNotification.recipient_user_id == admin_id)
        ).scalar_one()
        follower_row = session.execute(
            select(UserNotification).where(UserNotification.recipient_user_id == non_admin_id)
        ).scalar_one()
    assert admin_row.attention == ATTENTION_FOR_YOU
    assert follower_row.attention == ATTENTION_AMBIENT


@pytest.mark.asyncio
async def test_legacy_null_attention_falls_back(admin_client: httpx.AsyncClient) -> None:
    """A row with NULL attention is re-derived from its event type.

    A mention reads as ``for_you``; a plain comment reads as
    ``ambient``. This keeps rows written before the column existed
    bucketed sensibly.
    """
    admin_id = _user_id("test@test.com")
    _insert_notification(admin_id, event_type="pointlessql.data_product.mentioned", attention=None)
    _insert_notification(admin_id, event_type="pointlessql.data_product.commented", attention=None)
    res = await admin_client.get("/api/feed")
    assert res.status_code == 200, res.text
    by_event = {r["event_type"]: r["attention"] for r in res.json()["rows"]}
    assert by_event["pointlessql.data_product.mentioned"] == ATTENTION_FOR_YOU
    assert by_event["pointlessql.data_product.commented"] == ATTENTION_AMBIENT


@pytest.mark.asyncio
async def test_unread_for_you_count(admin_client: httpx.AsyncClient) -> None:
    """The for_you count tallies unread, addressed-to-me rows only."""
    admin_id = _user_id("test@test.com")
    empty = await admin_client.get("/api/feed")
    assert empty.json()["unread_for_you_count"] == 0

    _insert_notification(
        admin_id, event_type="pointlessql.data_product.mentioned", attention=ATTENTION_FOR_YOU
    )
    # An ambient row must not bump the for_you count.
    _insert_notification(
        admin_id, event_type="pointlessql.data_product.commented", attention=ATTENTION_AMBIENT
    )
    one = await admin_client.get("/api/feed")
    assert one.json()["unread_for_you_count"] == 1

    # A read for_you row drops out of the count.
    _insert_notification(
        admin_id,
        event_type="pointlessql.data_product.mentioned",
        attention=ATTENTION_FOR_YOU,
        read=True,
    )
    still_one = await admin_client.get("/api/feed")
    assert still_one.json()["unread_for_you_count"] == 1


@pytest.mark.asyncio
async def test_mark_all_read_scoped_to_for_you(admin_client: httpx.AsyncClient) -> None:
    """Mark-all-read drains for-you rows but leaves ambient untouched.

    The inbox button clears the addressed-to-you tier; ambient stream
    rows keep ``read_at`` null because their newness is the seen-cursor's
    job, not a read flag.
    """
    admin_id = _user_id("test@test.com")
    _insert_notification(
        admin_id, event_type="pointlessql.data_product.mentioned", attention=ATTENTION_FOR_YOU
    )
    _insert_notification(
        admin_id, event_type="pointlessql.data_product.commented", attention=ATTENTION_AMBIENT
    )

    res = await admin_client.post("/api/notifications/mark-all-read")
    assert res.status_code == 200, res.text
    assert res.json()["count"] == 1  # only the for_you row

    factory = app.state.session_factory
    with factory() as session:
        rows = {
            r.event_type: r.read_at
            for r in session.execute(
                select(UserNotification).where(UserNotification.recipient_user_id == admin_id)
            ).scalars()
        }
    assert rows["pointlessql.data_product.mentioned"] is not None
    assert rows["pointlessql.data_product.commented"] is None


def test_nav_badge_inbox_counts_for_you_only() -> None:
    """The rail inbox badge tallies the for-you tier, not ambient.

    This is what lets "mark all read" actually clear the Home-hub badge:
    ambient stream rows (tracked by the seen-cursor) never count toward
    it.
    """
    from pointlessql.services.nav_badges import compute_nav_badges

    admin_id = _user_id("test@test.com")
    _insert_notification(
        admin_id, event_type="pointlessql.data_product.mentioned", attention=ATTENTION_FOR_YOU
    )
    _insert_notification(
        admin_id, event_type="pointlessql.data_product.commented", attention=ATTENTION_AMBIENT
    )
    result = compute_nav_badges(app.state.session_factory, user_id=admin_id, workspace_id=1)
    assert result.get("audit_unread") == 1


@pytest.mark.asyncio
async def test_needs_action_count_admin_gated(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """Open signals count toward needs-action for admins, not members."""
    factory = app.state.session_factory
    emit_signal(
        factory,
        signal_kind="alert_firing",
        workspace_id=1,
        entity_kind="dp",
        entity_ref="main.sales_gold",
        summary_md="Freshness alert firing.",
        dedupe_key="alert:main.sales_gold",
    )
    admin = await admin_client.get("/api/feed")
    member = await non_admin_client.get("/api/feed")
    assert admin.json()["needs_action_count"] >= 1
    assert member.json()["needs_action_count"] == 0
