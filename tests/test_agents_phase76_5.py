"""first-class agent identities.

Coverage:

* Admin-only agent CRUD + verify.
* Comment POST with ``?as_agent=`` honours the agent's
  ``principal_user_id`` (or admin) gating.
* Comment serialisation carries the ``agent`` payload alongside
  the human author when an agent is present.
* Agent profile aggregation surface returns recent comments +
  run-stat count.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_products import DataProduct

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



def _seed_product(tmp_path: Path) -> int:
    """Seed a yaml + cache row; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


def _admin_user_id() -> int:
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(
                select(User.id).where(User.email == "test@test.com")
            ).scalar_one()
        )


def _nonadmin_user_id() -> int:
    factory = app.state.session_factory
    with factory() as session:
        return int(
            session.execute(
                select(User.id).where(User.email == "nonadmin@test.com")
            ).scalar_one()
        )


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_agent_admin(admin_client: httpx.AsyncClient) -> None:
    """Admin can register a new agent."""
    principal_id = _admin_user_id()
    res = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Audit Reviewer",
            "principal_user_id": principal_id,
            "avatar_kind": "hermes",
        },
    )
    assert res.status_code == 200, res.text
    assert res.json()["slug"] == "audit-reviewer"
    assert res.json()["avatar_kind"] == "hermes"


@pytest.mark.asyncio
async def test_create_agent_non_admin_rejected(
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A non-admin cannot register agents."""
    principal_id = _nonadmin_user_id()
    res = await non_admin_client.post(
        "/api/agents",
        json={
            "display_name": "Sneaky Bot",
            "principal_user_id": principal_id,
        },
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_create_agent_rejects_unknown_principal(
    admin_client: httpx.AsyncClient,
) -> None:
    """An unknown principal_user_id returns 404."""
    res = await admin_client.post(
        "/api/agents",
        json={"display_name": "Bot", "principal_user_id": 99999},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_create_agent_rejects_bad_avatar(
    admin_client: httpx.AsyncClient,
) -> None:
    """An unknown avatar_kind returns 400."""
    principal_id = _admin_user_id()
    res = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Bot",
            "principal_user_id": principal_id,
            "avatar_kind": "skynet",
        },
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_verify_agent_admin(admin_client: httpx.AsyncClient) -> None:
    """Admin can flip the verified flag."""
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Verifiable",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]
    res = await admin_client.post(f"/api/agents/{slug}/verify")
    assert res.status_code == 200
    assert res.json()["is_verified"] is True


@pytest.mark.asyncio
async def test_verify_agent_non_admin_rejected(
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Non-admin cannot verify."""
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={"display_name": "Pending", "principal_user_id": principal_id},
    )
    slug = create.json()["slug"]
    res = await non_admin_client.post(f"/api/agents/{slug}/verify")
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Comment as_agent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_comment_as_agent_principal_ok(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """The agent's principal_user can post under the agent's identity."""
    _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Reviewer Bot",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]

    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/comments?as_agent={slug}",
        json={"body_md": "I am a robot"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["agent"] is not None
    assert payload["agent"]["slug"] == slug
    # author_user_id still carries the principal — accountability is
    # intact on the audit chain.
    assert payload["author"]["user_id"] == principal_id


@pytest.mark.asyncio
async def test_comment_as_agent_non_principal_rejected(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A different user cannot speak as someone else's agent."""
    _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Owner's Bot",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]
    res = await non_admin_client.post(
        f"/api/data-products/main/sales_gold/comments?as_agent={slug}",
        json={"body_md": "trying to impersonate"},
    )
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_comment_as_unknown_agent_404(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown ``?as_agent=`` slug returns 404."""
    _seed_product(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments?as_agent=nope",
        json={"body_md": "x"},
    )
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_listing_includes_agent_payload(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """The agent payload surfaces in the comment listing."""
    _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Listed Bot",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]
    await admin_client.post(
        f"/api/data-products/main/sales_gold/comments?as_agent={slug}",
        json={"body_md": "hello"},
    )
    listing = await admin_client.get("/api/data-products/main/sales_gold/comments")
    payload = listing.json()["comments"]
    agent_rows = [c for c in payload if c.get("agent")]
    assert agent_rows, "expected at least one agent-authored comment"
    assert agent_rows[0]["agent"]["slug"] == slug


# ---------------------------------------------------------------------------
# Agent profile + HTML
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_agent_profile_endpoint(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``GET /api/agents/{slug}/profile`` returns the aggregate."""
    _seed_product(tmp_path)
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={"display_name": "Profile Bot", "principal_user_id": principal_id},
    )
    slug = create.json()["slug"]
    await admin_client.post(
        f"/api/data-products/main/sales_gold/comments?as_agent={slug}",
        json={"body_md": "in profile"},
    )

    res = await admin_client.get(f"/api/agents/{slug}/profile")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["agent"]["slug"] == slug
    assert any(
        "in profile" in c["body_md"] for c in body["recent_comments"]
    )
    assert body["run_stats"]["count"] == 0


@pytest.mark.asyncio
async def test_agent_profile_html_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """``/agents/{slug}`` returns 200 + the display name in the body."""
    principal_id = _admin_user_id()
    create = await admin_client.post(
        "/api/agents",
        json={
            "display_name": "Rendered Bot",
            "principal_user_id": principal_id,
        },
    )
    slug = create.json()["slug"]
    res = await admin_client.get(f"/agents/{slug}")
    assert res.status_code == 200
    assert "Rendered Bot" in res.text


@pytest.mark.asyncio
async def test_agent_profile_html_missing_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """Unknown agent slug returns 404 from the HTML route."""
    res = await admin_client.get("/agents/nope")
    assert res.status_code == 404


@pytest.mark.asyncio
async def test_agents_index_html_renders(
    admin_client: httpx.AsyncClient,
) -> None:
    """``/agents`` returns 200."""
    res = await admin_client.get("/agents")
    assert res.status_code == 200
    assert "Agents" in res.text
