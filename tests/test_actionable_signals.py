"""Actionable-signal ledger — emit / resolve / dedup + feed union.

A signal is one ongoing problem.  Emitting twice for the same problem
keeps exactly one open card (storm guard); resolving it drops the
card from the feed's live union.  Data-health cards are admin-gated
and acknowledgeable inline.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import func, select

from pointlessql.api.main import app
from pointlessql.models.actionable_signals import STATUS_OPEN, ActionableSignal
from pointlessql.services.signals import emit_signal, resolve_signal


def _open_count(dedupe_key: str) -> int:
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.scalar(
                select(func.count())
                .select_from(ActionableSignal)
                .where(
                    ActionableSignal.dedupe_key == dedupe_key,
                    ActionableSignal.status == STATUS_OPEN,
                )
            )
            or 0
        )


class TestEmitResolveDedup:
    def test_emit_opens_once_and_dedups(self):
        factory = app.state.session_factory
        opened = emit_signal(
            factory,
            signal_kind="alert_firing",
            workspace_id=1,
            entity_kind="alert",
            entity_ref="rev-drop",
            summary_md="Revenue dropped below 1000",
        )
        assert opened is True
        # Re-firing the same problem opens no new card.
        again = emit_signal(
            factory,
            signal_kind="alert_firing",
            workspace_id=1,
            entity_kind="alert",
            entity_ref="rev-drop",
            summary_md="Revenue dropped below 1000 (still)",
        )
        assert again is False
        assert _open_count("alert_firing:1:alert:rev-drop") == 1

    def test_resolve_closes_open_signal(self):
        factory = app.state.session_factory
        emit_signal(
            factory,
            signal_kind="slo_breach",
            workspace_id=1,
            entity_kind="table",
            entity_ref="main.sales.orders",
            summary_md="Freshness SLO breached",
        )
        key = "slo_breach:1:table:main.sales.orders"
        assert _open_count(key) == 1
        closed = resolve_signal(
            factory,
            signal_kind="slo_breach",
            workspace_id=1,
            entity_kind="table",
            entity_ref="main.sales.orders",
        )
        assert closed is True
        assert _open_count(key) == 0
        # Resolving again is a no-op.
        assert (
            resolve_signal(
                factory,
                signal_kind="slo_breach",
                workspace_id=1,
                entity_kind="table",
                entity_ref="main.sales.orders",
            )
            is False
        )

    def test_recurrence_after_resolve_opens_fresh(self):
        factory = app.state.session_factory
        kw = dict(
            signal_kind="job_failed",
            workspace_id=1,
            entity_kind="job",
            entity_ref="42",
        )
        assert emit_signal(factory, summary_md="run failed", **kw) is True
        assert resolve_signal(factory, **kw) is True
        # Same problem recurs → a brand-new open card (history kept).
        assert emit_signal(factory, summary_md="run failed again", **kw) is True
        assert _open_count("job_failed:1:job:42") == 1


class TestFeedUnion:
    @pytest.mark.asyncio
    async def test_open_signal_shows_for_admin_as_data_health(
        self, admin_client: httpx.AsyncClient
    ) -> None:
        emit_signal(
            app.state.session_factory,
            signal_kind="alert_firing",
            workspace_id=1,
            entity_kind="alert",
            entity_ref="rev-drop",
            summary_md="Revenue dropped below 1000",
            source_url="/alerts/rev-drop",
        )
        r = await admin_client.get("/api/feed")
        body = r.json()
        health = [row for row in body["rows"] if row.get("render_kind") == "data_health"]
        assert len(health) == 1
        card = health[0]
        assert card["category"] == "health"
        assert card["signal_kind"] == "alert_firing"
        assert card["source_url"] == "/alerts/rev-drop"
        assert body["category_counts"].get("health") == 1

    @pytest.mark.asyncio
    async def test_open_signal_hidden_from_non_admin(
        self, non_admin_client: httpx.AsyncClient
    ) -> None:
        emit_signal(
            app.state.session_factory,
            signal_kind="alert_firing",
            workspace_id=1,
            entity_kind="alert",
            entity_ref="rev-drop",
            summary_md="Revenue dropped",
        )
        r = await non_admin_client.get("/api/feed")
        signals = [row for row in r.json()["rows"] if row.get("kind") == "signal"]
        assert signals == []

    @pytest.mark.asyncio
    async def test_resolving_drops_the_card(self, admin_client: httpx.AsyncClient) -> None:
        emit_signal(
            app.state.session_factory,
            signal_kind="job_failed",
            workspace_id=1,
            entity_kind="job",
            entity_ref="7",
            summary_md="Nightly load failed",
        )
        r = await admin_client.get("/api/feed?category=pipeline")
        assert [row for row in r.json()["rows"] if row.get("render_kind") == "pipeline"]

        resolve_signal(
            app.state.session_factory,
            signal_kind="job_failed",
            workspace_id=1,
            entity_kind="job",
            entity_ref="7",
        )
        r = await admin_client.get("/api/feed?category=pipeline")
        assert [row for row in r.json()["rows"] if row.get("render_kind") == "pipeline"] == []


class TestAcknowledgeEndpoint:
    @pytest.mark.asyncio
    async def test_ack_resolves_and_drops(self, admin_client: httpx.AsyncClient) -> None:
        emit_signal(
            app.state.session_factory,
            signal_kind="alert_firing",
            workspace_id=1,
            entity_kind="alert",
            entity_ref="rev-drop",
            summary_md="Revenue dropped",
        )
        r = await admin_client.get("/api/feed")
        card = next(row for row in r.json()["rows"] if row.get("kind") == "signal")
        signal_id = card["signal_id"]

        ack = await admin_client.post(f"/api/feed/signals/{signal_id}/ack")
        assert ack.status_code == 200
        assert ack.json()["resolved"] is True

        r = await admin_client.get("/api/feed")
        assert [row for row in r.json()["rows"] if row.get("kind") == "signal"] == []

    @pytest.mark.asyncio
    async def test_ack_requires_admin(self, non_admin_client: httpx.AsyncClient) -> None:
        emit_signal(
            app.state.session_factory,
            signal_kind="alert_firing",
            workspace_id=1,
            entity_kind="alert",
            entity_ref="rev-drop",
            summary_md="Revenue dropped",
        )
        factory = app.state.session_factory
        with factory() as session:
            sid = session.scalar(select(ActionableSignal.id))
        resp = await non_admin_client.post(f"/api/feed/signals/{sid}/ack")
        assert resp.status_code in (401, 403)
