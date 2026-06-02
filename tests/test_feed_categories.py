"""Feed category taxonomy — classification + the ``?category=`` slice.

The category registry derives a coarse lane + severity from each
row's ``event_type`` (no stored column).  ``GET /api/feed`` stamps
both onto every row, returns stable ``category_counts`` across all
lanes, and narrows to one lane when ``?category=`` is set.
"""

from __future__ import annotations

import datetime

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.auth import User
from pointlessql.models.notifications import UserNotification
from pointlessql.services.notifications.categories import (
    classify_category,
    classify_signal,
    count_by_category,
)


class TestClassifyCategory:
    """event_type → (category, severity)."""

    @pytest.mark.parametrize(
        ("event_type", "expected"),
        [
            ("pointlessql.agent_run.needs_approval", ("approval", "warn")),
            ("pointlessql.agent_run.approved", ("approval", "info")),
            ("pointlessql.agent_run.denied", ("approval", "warn")),
            ("pointlessql.agent_run.failed", ("pipeline", "error")),
            ("pointlessql.agent_run.completed", ("pipeline", "info")),
            ("pointlessql.alert.fired", ("health", "error")),
            ("pointlessql.slo.breached", ("health", "warn")),
            ("pointlessql.contract.violated", ("health", "error")),
            ("pointlessql.freshness.stale", ("health", "warn")),
            ("pointlessql.job_run.failed", ("pipeline", "error")),
            ("pointlessql.ingest.failed", ("pipeline", "error")),
            ("pointlessql.ingest.completed", ("pipeline", "info")),
            ("pointlessql.branch.promoted", ("governance", "info")),
            ("pointlessql.agent_review.published", ("governance", "info")),
            ("pointlessql.issue.opened", ("social", "info")),
            ("pointlessql.user.badge_awarded", ("social", "info")),
            ("pointlessql.data_product.commented", ("social", "info")),
            ("pointlessql.data_product.mentioned", ("social", "info")),
            ("", ("social", "info")),
            (None, ("social", "info")),
            ("totally.unknown.event", ("social", "info")),
        ],
    )
    def test_classify(self, event_type, expected):
        assert classify_category(event_type) == expected

    def test_mention_anywhere_is_social(self):
        # A mention on any entity stays social even if the prefix would
        # otherwise route elsewhere.
        assert classify_category("pointlessql.table.mentioned")[0] == "social"


class TestClassifySignal:
    """signal_kind → (category, severity) for the actionable ledger."""

    @pytest.mark.parametrize(
        ("kind", "expected"),
        [
            ("alert_firing", ("health", "error")),
            ("slo_breach", ("health", "warn")),
            ("contract_violation", ("health", "error")),
            ("freshness_stale", ("health", "warn")),
            ("job_failed", ("pipeline", "error")),
            ("ingest_failed", ("pipeline", "error")),
            ("unknown", ("health", "warn")),
        ],
    )
    def test_classify_signal(self, kind, expected):
        assert classify_signal(kind) == expected


class TestCountByCategory:
    def test_counts_stamped_rows(self):
        rows = [
            {"category": "social"},
            {"category": "social"},
            {"category": "approval"},
        ]
        assert count_by_category(rows) == {"social": 2, "approval": 1}

    def test_falls_back_to_event_type_when_unstamped(self):
        rows = [{"event_type": "pointlessql.alert.fired"}]
        assert count_by_category(rows) == {"health": 1}


def _admin_id() -> int:
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(select(User.id).where(User.email == "test@test.com")).scalar_one()
        )


def _seed_notification(event_type: str, entity_kind: str, entity_ref: str) -> None:
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            UserNotification(
                workspace_id=1,
                recipient_user_id=_admin_id(),
                event_type=event_type,
                source_entity_kind=entity_kind,
                source_entity_ref=entity_ref,
                source_url=f"/x/{entity_ref}",
                summary_md=f"{event_type} on {entity_ref}",
                actor_user_id=None,
                read_at=None,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()


class TestCategorySlice:
    """``GET /api/feed?category=`` narrows; counts stay stable."""

    @pytest.mark.asyncio
    async def test_counts_and_slice(self, admin_client: httpx.AsyncClient) -> None:
        _seed_notification("pointlessql.agent_run.approved", "run", "r-1")
        _seed_notification("pointlessql.data_product.commented", "dp", "main.sales")
        _seed_notification("pointlessql.data_product.commented", "dp", "main.gold")

        # No category → every lane, counts present.
        r = await admin_client.get("/api/feed")
        assert r.status_code == 200
        body = r.json()
        counts = body["category_counts"]
        assert counts.get("approval") == 1
        assert counts.get("social") == 2
        assert len(body["rows"]) == 3

        # Slice to approvals → only the approval row, but counts still
        # reflect every lane (stable chip badges).
        r = await admin_client.get("/api/feed?category=approval")
        body = r.json()
        assert body["category"] == "approval"
        assert len(body["rows"]) == 1
        assert body["rows"][0]["category"] == "approval"
        assert body["category_counts"].get("social") == 2

        # Slice to social → both comment rows.
        r = await admin_client.get("/api/feed?category=social")
        body = r.json()
        assert len(body["rows"]) == 2
        assert all(row["category"] == "social" for row in body["rows"])
