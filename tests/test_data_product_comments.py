"""Tests for the data-product comment threads surface.

Covers the three JSON endpoints (list / post / soft-delete), the
threading depth cap, the soft-delete + placeholder rules, the
@mention resolution, and cross-workspace isolation.
"""

from __future__ import annotations

import datetime
import json
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.workspace import Workspace, WorkspaceMember

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
    """Seed a yaml + load it into the cache; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        row = session.execute(select(DataProduct)).scalar_one()
        return row.id


def _seed_product_with_steward(tmp_path: Path, steward_email: str) -> tuple[int, int]:
    """Seed a product whose steward resolves to a freshly-created user.

    Returns ``(data_product_id, steward_user_id)``.
    """
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        steward = User(
            email=steward_email,
            display_name="Alice Steward",
            password_hash=None,
            is_admin=False,
            default_workspace_id=1,
            created_at=now,
        )
        session.add(steward)
        session.commit()
        steward_id = steward.id
    dp_id = _seed_product(tmp_path)
    return dp_id, steward_id


# ---------------------------------------------------------------------------
# GET / POST happy path
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_and_list_top_level_comment(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Creating one top-level comment surfaces it in the list."""
    _seed_product(tmp_path)
    create = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "Hello world"},
    )
    assert create.status_code == 200, create.text
    payload = create.json()
    assert payload["body_md"] == "Hello world"
    assert payload["parent_comment_id"] is None

    listing = await admin_client.get("/api/data-products/main/sales_gold/comments")
    assert listing.status_code == 200
    body = listing.json()
    assert len(body["comments"]) == 1
    assert body["comments"][0]["body_md"] == "Hello world"


@pytest.mark.asyncio
async def test_post_threaded_reply_depth_one_ok(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """A reply to a top-level comment is accepted (depth 1)."""
    _seed_product(tmp_path)
    parent_id = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "parent"},
        )
    ).json()["id"]
    reply = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "reply", "parent_comment_id": parent_id},
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["parent_comment_id"] == parent_id


@pytest.mark.asyncio
async def test_threading_accepts_up_to_depth_five(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """five-deep is fine, six is rejected."""
    _seed_product(tmp_path)
    parent_id: int | None = None
    for level in range(5):
        res = await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": f"level-{level}", "parent_comment_id": parent_id},
        )
        assert res.status_code == 200, (level, res.text)
        parent_id = res.json()["id"]
    too_deep = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "level-6", "parent_comment_id": parent_id},
    )
    assert too_deep.status_code == 400
    assert "depth" in too_deep.json()["detail"]


@pytest.mark.asyncio
async def test_post_rejects_empty_body(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """Empty / whitespace-only body returns 400."""
    _seed_product(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "   "},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_post_unknown_parent(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """A POST with a parent_comment_id that doesn't exist returns 400."""
    _seed_product(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "x", "parent_comment_id": 99999},
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# Soft-delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_author_can_soft_delete_own_comment(
    tmp_path: Path, non_admin_client: httpx.AsyncClient
) -> None:
    """Non-admin author can soft-delete their own comment."""
    _seed_product(tmp_path)
    cid = (
        await non_admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "mine"},
        )
    ).json()["id"]
    res = await non_admin_client.delete(f"/api/data-products/main/sales_gold/comments/{cid}")
    assert res.status_code == 200
    assert res.json()["deleted_at"] is not None


@pytest.mark.asyncio
async def test_non_author_non_admin_cannot_delete(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A different non-admin user gets 403 on someone else's comment."""
    _seed_product(tmp_path)
    cid = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "admin's"},
        )
    ).json()["id"]
    res = await non_admin_client.delete(f"/api/data-products/main/sales_gold/comments/{cid}")
    assert res.status_code == 403


@pytest.mark.asyncio
async def test_steward_can_soft_delete_any_comment(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """When the product's steward matches the caller, delete is allowed.

    We rewire the seeded product's ``steward_user_id`` to the
    non-admin test user so a delete request from that user passes
    the steward gate even though they did not author the comment.
    """
    _seed_product(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        dp = session.execute(select(DataProduct)).scalar_one()
        dp.steward_user_id = nonadmin.id
        session.add(dp)
        session.commit()

    cid = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "to-be-deleted"},
        )
    ).json()["id"]
    res = await non_admin_client.delete(f"/api/data-products/main/sales_gold/comments/{cid}")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_admin_can_soft_delete_any_comment(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """Install-admin can always soft-delete."""
    _seed_product(tmp_path)
    cid = (
        await non_admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "by nonadmin"},
        )
    ).json()["id"]
    res = await admin_client.delete(f"/api/data-products/main/sales_gold/comments/{cid}")
    assert res.status_code == 200


@pytest.mark.asyncio
async def test_soft_deleted_leaf_dropped_from_listing(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """A soft-deleted top-level comment with no live children is omitted."""
    _seed_product(tmp_path)
    cid = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "leaf"},
        )
    ).json()["id"]
    await admin_client.delete(f"/api/data-products/main/sales_gold/comments/{cid}")
    body = (await admin_client.get("/api/data-products/main/sales_gold/comments")).json()
    assert body["comments"] == []


@pytest.mark.asyncio
async def test_soft_deleted_parent_with_live_reply_renders_placeholder(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Soft-deleting a parent that has a live reply keeps the parent row.

    The body is blanked (so callers can render ``[deleted]``) but
    the row survives so the reply thread stays coherent.
    """
    _seed_product(tmp_path)
    parent_id = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "parent"},
        )
    ).json()["id"]
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "reply", "parent_comment_id": parent_id},
    )
    await admin_client.delete(f"/api/data-products/main/sales_gold/comments/{parent_id}")
    body = (await admin_client.get("/api/data-products/main/sales_gold/comments")).json()
    parent_row = next(c for c in body["comments"] if c["id"] == parent_id)
    assert parent_row["deleted_at"] is not None
    assert parent_row["body_md"] == ""
    assert any(c["parent_comment_id"] == parent_id for c in body["comments"])


# ---------------------------------------------------------------------------
# Auth / cross-workspace
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_anonymous_get_returns_401_or_redirect(
    tmp_path: Path, anonymous_client: httpx.AsyncClient
) -> None:
    """Anonymous callers cannot list comments."""
    _seed_product(tmp_path)
    res = await anonymous_client.get("/api/data-products/main/sales_gold/comments")
    # auth middleware returns 401 for /api/* and 303 for HTML; either
    # counts as "rejected" here.
    assert res.status_code in (401, 403, 303)


@pytest.mark.asyncio
async def test_cross_workspace_isolation(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A comment in workspace 1 is invisible from workspace 2.

    We mint a second workspace, move the non-admin user to it, and
    confirm that their listing of the product (now scoped to ws 2)
    returns 404 — the product itself doesn't exist in ws 2.
    """
    _seed_product(tmp_path)
    await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "ws1 only"},
    )

    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            Workspace(
                id=2,
                slug="second",
                name="Second",
                description="iso test",
                created_at=now,
            )
        )
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        session.add(
            WorkspaceMember(
                workspace_id=2,
                user_id=nonadmin.id,
                role="member",
                created_at=now,
            )
        )
        nonadmin.default_workspace_id = 2
        session.add(nonadmin)
        session.commit()

    res = await non_admin_client.get(
        "/api/data-products/main/sales_gold/comments",
        headers={"X-Workspace": "second"},
    )
    assert res.status_code == 404


# ---------------------------------------------------------------------------
# @mention resolution
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_known_mention_resolves(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """``@<email>`` resolves to the matching user id."""
    _seed_product_with_steward(tmp_path, "alice@example.com")
    payload = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "ping @alice@example.com"},
    )
    assert payload.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        comment = session.execute(select(DataProductComment)).scalar_one()
        mentioned = json.loads(comment.mentioned_user_ids_json)
        assert len(mentioned) == 1


@pytest.mark.asyncio
async def test_unknown_mention_is_ignored(tmp_path: Path, admin_client: httpx.AsyncClient) -> None:
    """An unknown ``@<email>`` does NOT raise — it is silently skipped."""
    _seed_product(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "ping @nobody@nowhere.invalid"},
    )
    assert res.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        comment = session.execute(select(DataProductComment)).scalar_one()
        assert json.loads(comment.mentioned_user_ids_json) == []


@pytest.mark.asyncio
async def test_mention_inside_fenced_code_block_skipped(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``@email`` inside a fenced code block is NOT treated as a mention."""
    _seed_product_with_steward(tmp_path, "alice@example.com")
    body = "look at this code\n```\nhello @alice@example.com\n```\nthanks"
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": body},
    )
    assert res.status_code == 200
    factory = app.state.session_factory
    with factory() as session:
        comment = session.execute(select(DataProductComment)).scalar_one()
        assert json.loads(comment.mentioned_user_ids_json) == []
