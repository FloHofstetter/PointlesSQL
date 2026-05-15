"""Phase 76.1 — comment categories, reactions, accept-answer, @-autocomplete.

Covers:

* Category validation + reply inheritance.
* Accept-answer authorisation + atomicity + non-question-thread reject.
* Comment reactions add/remove/list + idempotency.
* DP-level reactions add/remove/list + follower fan-out.
* Display-name @-mentions: single-match resolves to notify, ambiguous
  match is recorded in the audit log and produces no notification.
* ``GET /api/users/search`` typeahead.
"""

from __future__ import annotations

import datetime
import json
from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.audit._log import AuditLog
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.notifications import UserNotification
from pointlessql.models.social._social_follow import SocialFollow
from pointlessql.models.social._social_reaction import SocialReaction

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


@pytest.fixture
async def anonymous_client() -> AsyncIterator[httpx.AsyncClient]:
    """``httpx.AsyncClient`` with no auth cookie."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        yield client


def _seed_product(tmp_path: Path) -> int:
    """Seed a yaml + cache row; return the data_products row id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


# ---------------------------------------------------------------------------
# Categories
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_post_with_question_category(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Top-level POST with a recognised category is persisted."""
    _seed_product(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "Why is X like that?", "category": "question"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["category"] == "question"


@pytest.mark.asyncio
async def test_unknown_category_rejected(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unknown category returns 400."""
    _seed_product(tmp_path)
    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "hi", "category": "spam"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_reply_inherits_parent_category(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Replies inherit category from the top-level ancestor."""
    _seed_product(tmp_path)
    top = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "Q?", "category": "question"},
        )
    ).json()
    reply = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={
            "body_md": "A!",
            "parent_comment_id": top["id"],
            # Even when the caller passes a category, the reply
            # inherits the parent's.
            "category": "general",
        },
    )
    assert reply.status_code == 200, reply.text
    assert reply.json()["category"] == "question"


# ---------------------------------------------------------------------------
# Accept-answer
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_accept_answer_atomicity(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Marking C2 as answer un-marks C1 in the same thread."""
    _seed_product(tmp_path)
    q = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "Q?", "category": "question"},
        )
    ).json()
    a1 = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "answer 1", "parent_comment_id": q["id"]},
        )
    ).json()
    a2 = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "answer 2", "parent_comment_id": q["id"]},
        )
    ).json()

    r1 = await admin_client.post(
        f"/api/data-products/main/sales_gold/comments/{a1['id']}/accept-answer"
    )
    assert r1.status_code == 200, r1.text
    r2 = await admin_client.post(
        f"/api/data-products/main/sales_gold/comments/{a2['id']}/accept-answer"
    )
    assert r2.status_code == 200, r2.text

    listing = (
        await admin_client.get("/api/data-products/main/sales_gold/comments")
    ).json()["comments"]
    by_id = {c["id"]: c for c in listing}
    assert by_id[a1["id"]]["is_accepted_answer"] is False
    assert by_id[a2["id"]]["is_accepted_answer"] is True


@pytest.mark.asyncio
async def test_accept_answer_only_on_question_thread(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Accept-answer on a non-question thread returns 400."""
    _seed_product(tmp_path)
    top = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "fyi", "category": "announcement"},
        )
    ).json()
    reply = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "yep", "parent_comment_id": top["id"]},
        )
    ).json()
    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/comments/{reply['id']}/accept-answer"
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_accept_answer_authz_rejects_outsider(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A user that is neither steward, admin, nor OP gets 403."""
    _seed_product(tmp_path)
    # admin asks the question + admin posts answer.
    q = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "Q?", "category": "question"},
        )
    ).json()
    a = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "A", "parent_comment_id": q["id"]},
        )
    ).json()
    res = await non_admin_client.post(
        f"/api/data-products/main/sales_gold/comments/{a['id']}/accept-answer"
    )
    assert res.status_code == 403


# ---------------------------------------------------------------------------
# Reactions on comments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reaction_idempotent(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Re-POSTing the same reaction triple is a no-op."""
    _seed_product(tmp_path)
    cid = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "hi"},
        )
    ).json()["id"]
    first = await admin_client.post(
        f"/api/data-products/main/sales_gold/comments/{cid}/reactions",
        json={"emoji": "👍"},
    )
    assert first.status_code == 200
    assert first.json()["added"] is True
    second = await admin_client.post(
        f"/api/data-products/main/sales_gold/comments/{cid}/reactions",
        json={"emoji": "👍"},
    )
    assert second.status_code == 200
    assert second.json()["added"] is False

    factory = app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(
                select(DataProductCommentReaction).where(
                    DataProductCommentReaction.comment_id == cid
                )
            )
            .scalars()
            .all()
        )
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_reaction_unknown_emoji_rejected(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Unsupported emoji returns 400."""
    _seed_product(tmp_path)
    cid = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "hi"},
        )
    ).json()["id"]
    res = await admin_client.post(
        f"/api/data-products/main/sales_gold/comments/{cid}/reactions",
        json={"emoji": "💩"},
    )
    assert res.status_code == 400


@pytest.mark.asyncio
async def test_remove_single_emoji_preserves_others(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """DELETE for one emoji leaves the caller's other reactions."""
    _seed_product(tmp_path)
    cid = (
        await admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "hi"},
        )
    ).json()["id"]
    for emoji in ("👍", "🎉"):
        await admin_client.post(
            f"/api/data-products/main/sales_gold/comments/{cid}/reactions",
            json={"emoji": emoji},
        )
    res = await admin_client.delete(
        f"/api/data-products/main/sales_gold/comments/{cid}/reactions/{'👍'}"
    )
    assert res.status_code == 200
    assert res.json()["removed"] is True

    listing = await admin_client.get(
        f"/api/data-products/main/sales_gold/comments/{cid}/reactions"
    )
    counts = {r["emoji"]: r["count"] for r in listing.json()["reactions"]}
    assert counts["👍"] == 0
    assert counts["🎉"] == 1


@pytest.mark.asyncio
async def test_comment_reaction_notifies_author_not_actor(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """A reaction notifies the comment's author — never the reactor."""
    _seed_product(tmp_path)
    # non_admin posts the comment; admin reacts.
    cid = (
        await non_admin_client.post(
            "/api/data-products/main/sales_gold/comments",
            json={"body_md": "by nonadmin"},
        )
    ).json()["id"]
    await admin_client.post(
        f"/api/data-products/main/sales_gold/comments/{cid}/reactions",
        json={"emoji": "❤️"},
    )

    factory = app.state.session_factory
    with factory() as session:
        author = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        actor = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        # author receives at least one notification typed
        # comment_reacted; actor receives none typed that way.
        recipients = (
            session.execute(
                select(UserNotification.recipient_user_id).where(
                    UserNotification.event_type
                    == "pointlessql.data_product.comment_reacted"
                )
            )
            .scalars()
            .all()
        )
    assert author.id in recipients
    assert actor.id not in recipients


# ---------------------------------------------------------------------------
# Reactions on the DP itself
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dp_reaction_notifies_followers(
    tmp_path: Path,
    admin_client: httpx.AsyncClient,
    non_admin_client: httpx.AsyncClient,
) -> None:
    """DP-level reactions fan out to followers."""
    dp_id = _seed_product(tmp_path)
    factory = app.state.session_factory
    from pointlessql.services.social import get_or_create_target

    with factory() as session:
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
        anchor = get_or_create_target(
            session,
            workspace_id=1,
            kind="dp",
            ref="main.sales_gold",
            data_product_id=dp_id,
        )
        session.add(
            SocialFollow(
                workspace_id=1,
                social_target_id=int(anchor.id),
                user_id=nonadmin.id,
                created_at=datetime.datetime.now(datetime.UTC),
            )
        )
        session.commit()

    res = await admin_client.post(
        "/api/data-products/main/sales_gold/reactions",
        json={"emoji": "🎉"},
    )
    assert res.status_code == 200
    assert res.json()["added"] is True

    with factory() as session:
        recipients = (
            session.execute(
                select(UserNotification.recipient_user_id).where(
                    UserNotification.event_type
                    == "pointlessql.data_product.reacted"
                )
            )
            .scalars()
            .all()
        )
        nonadmin = session.execute(
            select(User).where(User.email == "nonadmin@test.com")
        ).scalar_one()
    assert nonadmin.id in recipients


@pytest.mark.asyncio
async def test_dp_reaction_idempotent(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Repeated DP-reaction inserts collapse to a single row."""
    _seed_product(tmp_path)
    for _ in range(3):
        await admin_client.post(
            "/api/data-products/main/sales_gold/reactions",
            json={"emoji": "👀"},
        )
    factory = app.state.session_factory
    with factory() as session:
        rows = (
            session.execute(select(SocialReaction)).scalars().all()
        )
    assert len(rows) == 1


# ---------------------------------------------------------------------------
# Display-name mentions
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_displayname_mention_single_match_notifies(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """``@Display`` resolves when exactly one user has that display name."""
    _seed_product(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        target = User(
            email="charlie@example.com",
            display_name="Charlie",
            password_hash=None,
            is_admin=False,
            default_workspace_id=1,
            created_at=datetime.datetime.now(datetime.UTC),
        )
        session.add(target)
        session.commit()
        target_id = target.id

    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "hi @Charlie!"},
    )
    assert res.status_code == 200, res.text
    cid = res.json()["id"]
    with factory() as session:
        comment = session.get(DataProductComment, cid)
        assert comment is not None
        mentioned = json.loads(comment.mentioned_user_ids_json)
    assert target_id in mentioned


@pytest.mark.asyncio
async def test_displayname_mention_ambiguous_records_audit(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Two users sharing a display name skips the mention + audits it."""
    _seed_product(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        now = datetime.datetime.now(datetime.UTC)
        session.add_all(
            [
                User(
                    email="a@example.com",
                    display_name="Same",
                    password_hash=None,
                    is_admin=False,
                    default_workspace_id=1,
                    created_at=now,
                ),
                User(
                    email="b@example.com",
                    display_name="Same",
                    password_hash=None,
                    is_admin=False,
                    default_workspace_id=1,
                    created_at=now,
                ),
            ]
        )
        session.commit()

    res = await admin_client.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "yo @Same"},
    )
    assert res.status_code == 200
    cid = res.json()["id"]
    with factory() as session:
        comment = session.get(DataProductComment, cid)
        assert comment is not None
        assert json.loads(comment.mentioned_user_ids_json) == []
        audit = (
            session.execute(
                select(AuditLog).where(
                    AuditLog.action == "audit.discussion.mention_ambiguous"
                )
            )
            .scalars()
            .all()
        )
    assert audit, "expected an ambiguous-mention audit row"


# ---------------------------------------------------------------------------
# Users-search typeahead
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_users_search_matches_email_prefix(
    admin_client: httpx.AsyncClient,
) -> None:
    """``GET /api/users/search`` matches email prefix case-insensitively."""
    res = await admin_client.get("/api/users/search", params={"q": "test"})
    assert res.status_code == 200
    payload = res.json()
    emails = {r["email"] for r in payload["results"]}
    assert "test@test.com" in emails


@pytest.mark.asyncio
async def test_users_search_empty_returns_empty_list(
    admin_client: httpx.AsyncClient,
) -> None:
    """Empty query short-circuits to an empty result list."""
    res = await admin_client.get("/api/users/search", params={"q": "  "})
    assert res.status_code == 200
    assert res.json()["results"] == []


@pytest.mark.asyncio
async def test_users_search_anonymous_rejected(
    anonymous_client: httpx.AsyncClient,
) -> None:
    """Anonymous callers cannot enumerate users."""
    res = await anonymous_client.get("/api/users/search", params={"q": "a"})
    assert res.status_code in (302, 401, 403)
