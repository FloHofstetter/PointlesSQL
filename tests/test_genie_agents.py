"""Tests for "save a Genie conversation as a reusable named agent".

The service tests drive ``save_space_as_agent`` directly to assert it
snapshots the source's curated context and distils the conversation's
successful answers into the new agent's trusted assets; the route test
exercises the public endpoint end-to-end.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models import User
from pointlessql.services import genie as genie_service


def _factory() -> Any:
    return app.state.session_factory


def _admin_id() -> int:
    with _factory()() as session:
        return int(session.scalar(select(User.id).where(User.email == "test@test.com")) or 0)


def _seed_source(*, with_transcript: bool = True) -> Any:
    """Create a curated source space with one trusted asset + a transcript."""
    space = genie_service.create_space(
        _factory(),
        workspace_id=1,
        title="Sales analytics",
        description="rev room",
        owner_id=_admin_id(),
    )
    genie_service.update_space(
        _factory(),
        space_id=space.id,
        instructions="Revenue means completed orders only.",
        tables=["shop.gold.orders", "shop.gold.customers"],
        metric_views=["shop.gold.revenue_mv"],
    )
    genie_service.add_trusted_asset(
        _factory(),
        space_id=space.id,
        question="How many orders?",
        sql_text="SELECT count(*) FROM shop.gold.orders",
        created_by=_admin_id(),
    )
    if with_transcript:
        genie_service.append_message(
            _factory(),
            space_id=space.id,
            user_id=_admin_id(),
            role="user",
            content="revenue by region?",
        )
        genie_service.append_message(
            _factory(),
            space_id=space.id,
            user_id=None,
            role="assistant",
            content="here you go",
            sql_text="SELECT region, sum(amount) FROM shop.gold.orders GROUP BY region",
            status="ok",
        )
    return space


def test_save_as_agent_inherits_context_and_distils_transcript() -> None:
    source = _seed_source()
    agent = genie_service.save_space_as_agent(
        _factory(), source_space_id=source.id, name="Revenue agent", owner_id=_admin_id()
    )

    # A new, independent space.
    assert agent.id != source.id
    assert agent.title == "Revenue agent"
    assert agent.slug.startswith("revenue-agent-")
    # Curated sources + instructions inherited.
    assert genie_service.space_tables(agent) == ["shop.gold.orders", "shop.gold.customers"]
    assert genie_service.space_metric_views(agent) == ["shop.gold.revenue_mv"]
    assert agent.instructions == "Revenue means completed orders only."

    # Trusted assets = the carried-over source asset + the distilled answer.
    agent_assets = genie_service.list_trusted_assets(_factory(), space_id=agent.id)
    agent_sql = {a.sql_text for a in agent_assets}
    assert "SELECT count(*) FROM shop.gold.orders" in agent_sql
    assert "SELECT region, sum(amount) FROM shop.gold.orders GROUP BY region" in agent_sql

    # The source is untouched (independent copy).
    source_assets = genie_service.list_trusted_assets(_factory(), space_id=source.id)
    assert len(source_assets) == 1


def test_save_as_agent_skips_failed_and_downvoted_turns() -> None:
    source = genie_service.create_space(
        _factory(), workspace_id=1, title="QA room", description=None, owner_id=_admin_id()
    )
    genie_service.append_message(
        _factory(), space_id=source.id, user_id=_admin_id(), role="user", content="q1"
    )
    genie_service.append_message(
        _factory(),
        space_id=source.id,
        user_id=None,
        role="assistant",
        content="boom",
        sql_text=None,
        status="error",
        error="bad sql",
    )
    genie_service.append_message(
        _factory(), space_id=source.id, user_id=_admin_id(), role="user", content="q2"
    )
    downvoted = genie_service.append_message(
        _factory(),
        space_id=source.id,
        user_id=None,
        role="assistant",
        content="ok",
        sql_text="SELECT 2",
        status="ok",
    )
    genie_service.set_feedback(_factory(), message_id=downvoted.id, feedback="down")

    agent = genie_service.save_space_as_agent(
        _factory(), source_space_id=source.id, name="qa agent", owner_id=_admin_id()
    )
    assets = genie_service.list_trusted_assets(_factory(), space_id=agent.id)
    # Error turn (no SQL) and the down-voted answer are both skipped.
    assert assets == []


def test_save_as_agent_without_transcript_only_carries_assets() -> None:
    source = _seed_source()
    agent = genie_service.save_space_as_agent(
        _factory(),
        source_space_id=source.id,
        name="assets only",
        owner_id=_admin_id(),
        include_transcript=False,
    )
    sql = {a.sql_text for a in genie_service.list_trusted_assets(_factory(), space_id=agent.id)}
    assert sql == {"SELECT count(*) FROM shop.gold.orders"}


def test_save_as_agent_validates_name_and_source() -> None:
    source = _seed_source(with_transcript=False)
    with pytest.raises(ValueError, match="name must be"):
        genie_service.save_space_as_agent(
            _factory(), source_space_id=source.id, name="   ", owner_id=_admin_id()
        )
    with pytest.raises(ValueError, match="not found"):
        genie_service.save_space_as_agent(
            _factory(), source_space_id=999_999, name="x", owner_id=_admin_id()
        )


@pytest.mark.asyncio
async def test_route_save_as_agent(admin_client: httpx.AsyncClient) -> None:
    source = _seed_source()
    response = await admin_client.post(
        f"/api/genie/spaces/{source.slug}/save-as-agent",
        json={"name": "Routed agent"},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["title"] == "Routed agent"
    assert body["slug"] != source.slug
    assert body["asset_count"] >= 2
    assert body["tables"] == ["shop.gold.orders", "shop.gold.customers"]

    # The agent is independently retrievable.
    fetched = await admin_client.get(f"/api/genie/spaces/{body['slug']}")
    assert fetched.status_code == 200, fetched.text


@pytest.mark.asyncio
async def test_route_save_as_agent_requires_name(admin_client: httpx.AsyncClient) -> None:
    source = _seed_source(with_transcript=False)
    response = await admin_client.post(
        f"/api/genie/spaces/{source.slug}/save-as-agent",
        json={},
    )
    assert response.status_code == 422, response.text
