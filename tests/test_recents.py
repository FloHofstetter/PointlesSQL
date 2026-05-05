"""Tests for the Sprint 17.5.1 recents service."""

from __future__ import annotations

import datetime as dt

from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import RecentTable, User
from pointlessql.services import recents as recents_service


def _make_user(email: str = "alice@example.com") -> int:
    factory = app.state.session_factory
    with factory() as session:
        existing = session.scalar(select(User).where(User.email == email))
        if existing is not None:
            return existing.id
        user = User(
            email=email,
            display_name="Alice",
            password_hash="x",
            is_admin=False,
            created_at=dt.datetime.now(dt.UTC),
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return user.id


def _wipe_recents(user_id: int) -> None:
    factory = app.state.session_factory
    with factory() as session:
        rows = session.scalars(select(RecentTable).where(RecentTable.user_id == user_id)).all()
        for r in rows:
            session.delete(r)
        session.commit()


class TestRecordTableVisit:
    def test_inserts_row(self) -> None:
        user_id = _make_user("recents-1@example.com")
        _wipe_recents(user_id)
        recents_service.record_table_visit(
            app.state.session_factory, user_id, "playground.bronze.events"
        )
        rows = recents_service.top_recent_tables(app.state.session_factory, user_id)
        assert len(rows) == 1
        assert rows[0]["table_full_name"] == "playground.bronze.events"

    def test_repeat_visit_upserts(self) -> None:
        user_id = _make_user("recents-2@example.com")
        _wipe_recents(user_id)
        first = dt.datetime(2026, 4, 28, 10, 0, tzinfo=dt.UTC)
        second = dt.datetime(2026, 4, 29, 10, 0, tzinfo=dt.UTC)
        recents_service.record_table_visit(
            app.state.session_factory, user_id, "playground.bronze.events", now=first
        )
        recents_service.record_table_visit(
            app.state.session_factory, user_id, "playground.bronze.events", now=second
        )
        # Single row, last_visited_at bumped to second.
        factory = app.state.session_factory
        with factory() as session:
            rows = list(session.scalars(select(RecentTable).where(RecentTable.user_id == user_id)))
        assert len(rows) == 1
        # SQLite drops tzinfo on DateTime(timezone=True) columns —
        # compare naïvely on the wall-clock components.
        stored = rows[0].last_visited_at
        if stored.tzinfo is None:
            stored = stored.replace(tzinfo=dt.UTC)
        assert stored.replace(microsecond=0) == second.replace(microsecond=0)

    def test_anonymous_user_id_no_op(self) -> None:
        recents_service.record_table_visit(
            app.state.session_factory, 0, "playground.bronze.events"
        )  # no exception, no row written

    def test_invalid_fqn_no_op(self) -> None:
        user_id = _make_user("recents-3@example.com")
        _wipe_recents(user_id)
        recents_service.record_table_visit(app.state.session_factory, user_id, "not_three_parts")
        assert recents_service.top_recent_tables(app.state.session_factory, user_id) == []


class TestTopRecentTables:
    def test_orders_newest_first_and_caps_at_limit(self) -> None:
        user_id = _make_user("recents-4@example.com")
        _wipe_recents(user_id)
        # Seed 7 visits at increasing timestamps; expect newest 5 in
        # reverse-chronological order.
        for i in range(7):
            ts = dt.datetime(2026, 4, 1 + i, 10, 0, tzinfo=dt.UTC)
            recents_service.record_table_visit(
                app.state.session_factory,
                user_id,
                f"playground.bronze.t{i}",
                now=ts,
            )
        rows = recents_service.top_recent_tables(app.state.session_factory, user_id)
        assert len(rows) == 5
        # Newest is t6 (i=6), then t5, t4, t3, t2.
        names = [r["table_full_name"] for r in rows]
        assert names == [
            "playground.bronze.t6",
            "playground.bronze.t5",
            "playground.bronze.t4",
            "playground.bronze.t3",
            "playground.bronze.t2",
        ]

    def test_anonymous_returns_empty(self) -> None:
        assert recents_service.top_recent_tables(app.state.session_factory, 0) == []

    def test_unknown_user_returns_empty(self) -> None:
        # User-id 999999 has no rows; result is [], not an error.
        assert recents_service.top_recent_tables(app.state.session_factory, 999999) == []
