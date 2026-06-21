"""Tests for the AI-spend governance overlay.

The service-level tests each run in a freshly-created workspace with
freshly-created owners so the session-scoped test DB (no per-test
rollback) cannot leak Lens spend between cases; the route tests hit the
admin endpoints in the default workspace and assert shape + auth.
"""

from __future__ import annotations

import datetime
import uuid
from decimal import Decimal
from typing import Any

import httpx
import pytest

from pointlessql.api.main import app as fastapi_app
from pointlessql.models import LensMessage, LensSession, User, Workspace
from pointlessql.services import ai_gateway


def _factory():
    return fastapi_app.state.session_factory


def _fresh_workspace() -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        ws = Workspace(
            slug=f"aigw-{uuid.uuid4().hex[:10]}",
            name="AI gateway test workspace",
            created_at=now,
        )
        session.add(ws)
        session.commit()
        session.refresh(ws)
        return int(ws.id)


def _fresh_user(email: str) -> int:
    now = datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        user = User(
            email=email,
            display_name=email.split("@")[0],
            password_hash="x",
            is_admin=False,
            default_workspace_id=1,
            created_at=now,
        )
        session.add(user)
        session.commit()
        session.refresh(user)
        return int(user.id)


def _seed_session(
    ws: int,
    *,
    owner_id: int,
    provider: str = "anthropic",
    model: str = "claude-haiku-4-5-20251001",
    turns: list[dict[str, Any]],
    base: datetime.datetime | None = None,
) -> int:
    """Seed one Lens session with the given message turns.

    Each turn dict carries ``role`` + ``cost`` and optional ``tin`` /
    ``tout`` token counts and ``offset`` seconds from *base*.
    """
    now = base or datetime.datetime.now(datetime.UTC)
    with _factory()() as session:
        sess = LensSession(
            workspace_id=ws,
            owner_id=owner_id,
            title="ai-gateway-test",
            llm_provider=provider,
            llm_model=model,
            total_cost_estimate=sum(float(t["cost"]) for t in turns),
            created_at=now,
            updated_at=now,
            last_message_at=now,
        )
        session.add(sess)
        session.commit()
        session.refresh(sess)
        sid = int(sess.id)
        for turn in turns:
            session.add(
                LensMessage(
                    session_id=sid,
                    role=turn["role"],
                    content="x",
                    tokens_in=turn.get("tin", 0),
                    tokens_out=turn.get("tout", 0),
                    cost_estimate=float(turn["cost"]),
                    created_at=now + datetime.timedelta(seconds=turn.get("offset", 0)),
                )
            )
        session.commit()
    return sid


def test_overview_rolls_up_by_provider_model_user() -> None:
    ws = _fresh_workspace()
    alice_email = f"alice-{uuid.uuid4().hex[:8]}@x.io"
    bob_email = f"bob-{uuid.uuid4().hex[:8]}@x.io"
    alice = _fresh_user(alice_email)
    bob = _fresh_user(bob_email)
    _seed_session(
        ws,
        owner_id=alice,
        provider="anthropic",
        model="claude-haiku-4-5-20251001",
        turns=[
            {"role": "assistant", "cost": 2.0, "tin": 100, "tout": 40},
            {"role": "tool", "cost": 0.5},
            {"role": "user", "cost": 0.0},
        ],
    )
    _seed_session(
        ws,
        owner_id=bob,
        provider="openai",
        model="gpt-4o-mini",
        turns=[{"role": "assistant", "cost": 3.0, "tin": 60, "tout": 20}],
    )

    ov = ai_gateway.ai_spend_overview(_factory(), workspace_id=ws)

    assert ov["totals"]["sessions"] == 2
    assert ov["totals"]["total_cost"] == 5.5
    assert ov["totals"]["llm_cost"] == 5.0
    assert ov["totals"]["tool_cost"] == 0.5
    assert ov["totals"]["tokens_in"] == 160
    assert ov["totals"]["tokens_out"] == 60
    assert ov["totals"]["distinct_providers"] == 2
    assert ov["totals"]["distinct_users"] == 2

    by_provider = {row["key"]: row for row in ov["by_provider"]}
    assert by_provider["anthropic"]["llm_cost"] == 2.0
    assert by_provider["anthropic"]["tool_cost"] == 0.5
    assert by_provider["anthropic"]["total_cost"] == 2.5
    # Sorted by spend descending: openai (3.0) outranks anthropic (2.5).
    assert ov["by_provider"][0]["key"] == "openai"

    by_model = {row["key"]: row for row in ov["by_model"]}
    assert by_model["gpt-4o-mini"]["provider"] == "openai"
    assert by_model["claude-haiku-4-5-20251001"]["tokens_in"] == 100

    by_user = {row["key"]: row for row in ov["by_user"]}
    assert set(by_user) == {alice_email, bob_email}
    assert by_user[alice_email]["sessions"] == 1
    assert by_user[bob_email]["total_cost"] == 3.0


def test_overview_budget_thresholds() -> None:
    ws = _fresh_workspace()
    owner = _fresh_user(f"carol-{uuid.uuid4().hex[:8]}@x.io")
    _seed_session(ws, owner_id=owner, turns=[{"role": "assistant", "cost": 90.0}])

    ok = ai_gateway.ai_spend_overview(_factory(), workspace_id=ws, budget=Decimal("200"))
    assert ok["budget"]["status"] == "ok"

    warn = ai_gateway.ai_spend_overview(_factory(), workspace_id=ws, budget=Decimal("100"))
    assert warn["budget"]["status"] == "warn"
    assert warn["budget"]["signal_kind"] == "budget_warn"

    exhausted = ai_gateway.ai_spend_overview(_factory(), workspace_id=ws, budget=Decimal("50"))
    assert exhausted["budget"]["status"] == "exhausted"
    assert exhausted["budget"]["signal_kind"] == "budget_block"
    assert exhausted["budget"]["accrued"] == 90.0

    assert ai_gateway.ai_spend_overview(_factory(), workspace_id=ws)["budget"] is None


def test_overview_since_filter() -> None:
    ws = _fresh_workspace()
    owner = _fresh_user(f"dave-{uuid.uuid4().hex[:8]}@x.io")
    old = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=10)
    recent = datetime.datetime.now(datetime.UTC) - datetime.timedelta(hours=1)
    _seed_session(
        ws,
        owner_id=owner,
        provider="anthropic",
        model="old-model",
        turns=[{"role": "assistant", "cost": 1.0}],
        base=old,
    )
    _seed_session(
        ws,
        owner_id=owner,
        provider="openai",
        model="new-model",
        turns=[{"role": "assistant", "cost": 2.0}],
        base=recent,
    )

    cutoff = datetime.datetime.now(datetime.UTC) - datetime.timedelta(days=1)
    ov = ai_gateway.ai_spend_overview(_factory(), workspace_id=ws, since=cutoff)

    assert {row["key"] for row in ov["by_model"]} == {"new-model"}
    assert ov["totals"]["total_cost"] == 2.0
    assert ov["totals"]["message_count"] == 1


def test_overview_empty_workspace() -> None:
    ws = _fresh_workspace()
    ov = ai_gateway.ai_spend_overview(_factory(), workspace_id=ws, budget=Decimal("10"))
    assert ov["totals"]["sessions"] == 0
    assert ov["totals"]["total_cost"] == 0.0
    assert ov["by_provider"] == []
    assert ov["recent_sessions"] == []
    assert ov["budget"]["status"] == "ok"


@pytest.mark.asyncio
async def test_route_overview(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/api/admin/ai-gateway/overview")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    expected = {"totals", "by_provider", "by_model", "by_user", "recent_sessions", "budget"}
    assert expected <= set(data)
    assert data["budget"] is None

    with_budget = await admin_client.get("/api/admin/ai-gateway/overview?budget=100000000")
    assert with_budget.json()["budget"]["status"] == "ok"


@pytest.mark.asyncio
async def test_route_page_renders(admin_client: httpx.AsyncClient) -> None:
    resp = await admin_client.get("/admin/ai-gateway")
    assert resp.status_code == 200, resp.text
    assert "AI gateway" in resp.text


@pytest.mark.asyncio
async def test_route_requires_admin(non_admin_client: httpx.AsyncClient) -> None:
    resp = await non_admin_client.get("/api/admin/ai-gateway/overview")
    assert resp.status_code in {401, 403}
