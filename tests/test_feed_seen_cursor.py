"""Tests for the feed seen-cursor (``POST /api/feed/seen`` + is_new).

The ambient stream is infinite, so the reader carries one high-water
``seen_at`` per workspace instead of a per-row read flag.  These tests
cover the upsert (create + forward-only advance + future clamp), the
per-row ``is_new`` stamping against the cursor, the ``unseen_count`` /
``caught_up`` composite, and that the cursor is per-recipient.
"""

from __future__ import annotations

import datetime

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.auth import User
from pointlessql.models.notifications import FeedReadMarker, UserNotification
from pointlessql.services.notifications.categories import ATTENTION_AMBIENT


def _user_id(email: str) -> int:
    """Resolve a seeded user's id by email."""
    factory = app.state.session_factory
    with factory() as session:
        return int(session.execute(select(User.id).where(User.email == email)).scalar_one())


def _insert_ambient(recipient_id: int, *, when: datetime.datetime, summary: str) -> None:
    """Insert one ambient (stream) notification at a given time."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            UserNotification(
                workspace_id=1,
                recipient_user_id=recipient_id,
                event_type="pointlessql.data_product.commented",
                source_entity_kind="dp",
                source_entity_ref="main.x",
                source_url="/data-products/main/x",
                summary_md=summary,
                attention=ATTENTION_AMBIENT,
                read_at=None,
                created_at=when,
            )
        )
        session.commit()


@pytest.mark.asyncio
async def test_seen_creates_then_advances_forward_only(
    admin_client: httpx.AsyncClient,
) -> None:
    """First POST creates the cursor; an older POST never rewinds it."""
    admin_id = _user_id("test@test.com")
    t1 = datetime.datetime(2026, 6, 1, 12, 0, tzinfo=datetime.UTC)
    t2 = datetime.datetime(2026, 6, 1, 18, 0, tzinfo=datetime.UTC)

    first = await admin_client.post("/api/feed/seen", json={"at": t1.isoformat()})
    assert first.status_code == 200, first.text
    assert first.json()["seen_at"].startswith("2026-06-01T12:00")

    # Forward advance sticks.
    fwd = await admin_client.post("/api/feed/seen", json={"at": t2.isoformat()})
    assert fwd.json()["seen_at"].startswith("2026-06-01T18:00")

    # A stale (earlier) request does not rewind the cursor.
    back = await admin_client.post("/api/feed/seen", json={"at": t1.isoformat()})
    assert back.json()["seen_at"].startswith("2026-06-01T18:00")

    factory = app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(select(FeedReadMarker).where(FeedReadMarker.user_id == admin_id))
            .scalars()
            .all()
        )
    assert len(rows) == 1  # upsert, never duplicated


@pytest.mark.asyncio
async def test_seen_defaults_to_now_and_clamps_future(
    admin_client: httpx.AsyncClient,
) -> None:
    """An omitted ``at`` defaults to now; a future ``at`` clamps to now."""
    before = datetime.datetime.now(datetime.UTC)
    res = await admin_client.post("/api/feed/seen", json={})
    after = datetime.datetime.now(datetime.UTC)
    seen = datetime.datetime.fromisoformat(res.json()["seen_at"])
    assert before <= seen <= after

    # A wildly future timestamp must not let the cursor outrun reality.
    far = (after + datetime.timedelta(days=3650)).isoformat()
    clamped = await admin_client.post("/api/feed/seen", json={"at": far})
    seen2 = datetime.datetime.fromisoformat(clamped.json()["seen_at"])
    assert seen2 <= datetime.datetime.now(datetime.UTC)


@pytest.mark.asyncio
async def test_is_new_and_unseen_count_track_cursor(
    admin_client: httpx.AsyncClient,
) -> None:
    """Rows after the cursor are new; advancing it drains the unseen tally."""
    admin_id = _user_id("test@test.com")
    old = datetime.datetime(2026, 5, 1, 9, 0, tzinfo=datetime.UTC)
    new = datetime.datetime(2026, 6, 2, 9, 0, tzinfo=datetime.UTC)
    _insert_ambient(admin_id, when=old, summary="old ambient")
    _insert_ambient(admin_id, when=new, summary="new ambient")

    # No cursor yet → every row is new, not caught up.
    fresh = (await admin_client.get("/api/feed")).json()
    assert fresh["seen_at"] is None
    assert all(r["is_new"] for r in fresh["rows"])
    assert fresh["unseen_count"] == 2
    assert fresh["caught_up"] is False

    # Catch up to between the two rows → exactly one stays new.
    mid = datetime.datetime(2026, 5, 15, 9, 0, tzinfo=datetime.UTC)
    await admin_client.post("/api/feed/seen", json={"at": mid.isoformat()})
    partial = (await admin_client.get("/api/feed")).json()
    by_summary = {r["summary_md"]: r["is_new"] for r in partial["rows"]}
    assert by_summary["old ambient"] is False
    assert by_summary["new ambient"] is True
    assert partial["unseen_count"] == 1

    # Catch up fully → nothing unseen, and (no act/for_you) caught up.
    await admin_client.post("/api/feed/seen", json={})
    done = (await admin_client.get("/api/feed")).json()
    assert done["unseen_count"] == 0
    assert done["caught_up"] is True


@pytest.mark.asyncio
async def test_seen_cursor_is_per_user(
    admin_client: httpx.AsyncClient, non_admin_client: httpx.AsyncClient
) -> None:
    """One user catching up does not move another user's cursor."""
    await admin_client.post("/api/feed/seen", json={})
    member = (await non_admin_client.get("/api/feed")).json()
    assert member["seen_at"] is None
