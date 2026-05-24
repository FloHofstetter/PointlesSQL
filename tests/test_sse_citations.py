"""SSE notifications + cross-DP citations.

Coverage:

* ``publish_notification`` delivers payloads to live listeners +
  no-ops when no one is subscribed.
* ``resolve_citations`` renders ``#dp:``, ``#topic:``, ``#user:``
  and ``#agent:`` tokens into markdown anchors and leaves
  unresolved tokens untouched.
"""

from __future__ import annotations

import asyncio
import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.api.notifications_stream import (
    _LISTENERS,
    _register_listener,
    _unregister_listener,
    active_listener_count,
    publish_notification,
)
from pointlessql.data_products import load_contract
from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._topic import Topic
from pointlessql.services.social.citations import resolve_citations

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


@pytest.fixture(autouse=True)
def _clear_sse_registry() -> None:
    """Wipe the module-level SSE registry between tests."""
    _LISTENERS.clear()


# ---------------------------------------------------------------------------
# SSE registry
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_publish_delivers_to_registered_listener() -> None:
    """A registered queue receives the published payload."""
    queue = _register_listener(42)
    try:
        delivered = publish_notification(42, {"event_type": "test.event", "summary_md": "hi"})
        assert delivered == 1
        payload = await asyncio.wait_for(queue.get(), timeout=1.0)
        assert payload["event_type"] == "test.event"
    finally:
        _unregister_listener(42, queue)


def test_publish_to_missing_recipient_is_noop() -> None:
    """No exception when nobody is subscribed."""
    delivered = publish_notification(999, {"event_type": "x"})
    assert delivered == 0


def test_unregister_cleans_up_listener() -> None:
    """Unregistering the last queue removes the user from the map."""
    queue = _register_listener(7)
    assert active_listener_count(7) == 1
    _unregister_listener(7, queue)
    assert active_listener_count(7) == 0


@pytest.mark.asyncio
async def test_publish_delivers_to_multiple_listeners() -> None:
    """A single user with multiple tabs receives the payload on each."""
    q1 = _register_listener(11)
    q2 = _register_listener(11)
    try:
        delivered = publish_notification(11, {"summary_md": "a"})
        assert delivered == 2
        p1 = await asyncio.wait_for(q1.get(), timeout=1.0)
        p2 = await asyncio.wait_for(q2.get(), timeout=1.0)
        assert p1 == p2
    finally:
        _unregister_listener(11, q1)
        _unregister_listener(11, q2)


# ---------------------------------------------------------------------------
# Citation renderer
# ---------------------------------------------------------------------------


def _seed_dp(tmp_path: Path) -> int:
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _admin_id() -> int:
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(select(User.id).where(User.email == "test@test.com")).scalar_one()
        )


def test_resolve_dp_cite(tmp_path: Path) -> None:
    """A ``#dp:cat.sch`` token resolves to a markdown anchor."""
    _seed_dp(tmp_path)
    out = resolve_citations(
        "see #dp:main.sales_gold for details",
        app.state.session_factory,
        workspace_id=1,
    )
    assert "/data-products/main/sales_gold" in out
    assert "[#main.sales_gold]" in out


def test_resolve_unknown_dp_cite_stays_literal(tmp_path: Path) -> None:
    """Unknown DP cite tokens are left as literal text."""
    _seed_dp(tmp_path)
    out = resolve_citations(
        "see #dp:main.ghost — does not exist",
        app.state.session_factory,
        workspace_id=1,
    )
    assert "#dp:main.ghost" in out
    assert "/data-products/main/ghost" not in out


def test_resolve_topic_cite() -> None:
    """A ``#topic:slug`` token resolves when the topic exists."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            Topic(
                workspace_id=1,
                slug="finance",
                display_name="Finance",
                created_at=datetime.datetime.now(datetime.UTC),
                created_by_user_id=_admin_id(),
            )
        )
        session.commit()
    out = resolve_citations(
        "join #topic:finance",
        app.state.session_factory,
        workspace_id=1,
    )
    assert "/topics/finance" in out


def test_resolve_user_cite() -> None:
    """A ``#user:email`` token resolves to the user's profile URL."""
    admin_id = _admin_id()
    out = resolve_citations(
        "ping #user:test@test.com please",
        app.state.session_factory,
        workspace_id=1,
    )
    assert f"/users/{admin_id}" in out


def test_resolve_agent_cite() -> None:
    """A ``#agent:slug`` token resolves when the agent exists."""
    factory = app.state.session_factory
    with factory() as session:
        session.add(
            Agent(
                workspace_id=1,
                slug="reviewer-bot",
                display_name="Reviewer Bot",
                principal_user_id=_admin_id(),
                created_at=datetime.datetime.now(datetime.UTC),
                created_by_user_id=_admin_id(),
            )
        )
        session.commit()
    out = resolve_citations(
        "ask #agent:reviewer-bot",
        app.state.session_factory,
        workspace_id=1,
    )
    assert "/agents/reviewer-bot" in out


def test_resolve_returns_input_when_no_hash() -> None:
    """A body without any ``#`` is returned verbatim."""
    out = resolve_citations("plain text", app.state.session_factory, workspace_id=1)
    assert out == "plain text"
