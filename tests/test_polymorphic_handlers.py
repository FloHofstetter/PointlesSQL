"""polymorphic ``/api/social/{kind}/{ref}/...`` handlers.

Coverage:

* `kind='table'` end-to-end: POST + GET + DELETE comment, POST +
  GET + DELETE endorsement, PUT + GET README, follower count.
* `kind='branch'` end-to-end: POST + GET + DELETE comment, POST +
  DELETE endorsement (``branch-approved-for-promotion``).
* Audit-target prefix uses the generic ``{kind}:{ref}`` shape
  (NOT the legacy ``data_product:`` prefix that's reserved for
  ``kind='dp'`` per locked decision #9).
* `parse_ref` shape validation: malformed table / branch refs
  return 400 with a clean error.
* Capability flags drive 404 / 501: README on `kind='branch'`
  returns 404 (`supports_readme=False`); follow / reviews /
  reactions on non-DP return 501.
* The DP path still works through the dispatcher (parity check).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.audit import AuditLog
from pointlessql.models.catalog._data_product_comments import (
    DataProductComment,
)
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.social._entity_readme import EntityReadme
from pointlessql.models.social._social_target import SocialTarget

_TABLE_REF = "main.sales_gold.orders"
_BRANCH_REF = "main.sales_gold__branch_demo"

_CONTRACT_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: test@test.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


@pytest.fixture
def seeded_dp(tmp_path: Path) -> int:
    """Load a DP contract; return the DP id (kept for parity tests)."""
    from pointlessql.models.catalog._data_products import DataProduct

    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(_CONTRACT_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return int(session.execute(select(DataProduct)).scalar_one().id)


@pytest.fixture
async def admin_socket(
    admin_client: httpx.AsyncClient,
) -> AsyncIterator[httpx.AsyncClient]:
    """Re-export the conftest admin client under an explicit name."""
    yield admin_client


# ---------------------------------------------------------------------------
# kind='table' — comments
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_post_comment_creates_polymorphic_row(
    admin_socket: httpx.AsyncClient,
) -> None:
    """POST /api/social/table/{ref}/comments lands a polymorphic row.

    No DP exists at ``main.sales_gold.orders`` — the social_target
    row is created on demand by ``get_or_create_target`` and the
    comment row has ``data_product_id=NULL``.
    """
    res = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/comments",
        json={"body_md": "first table comment"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["body_md"] == "first table comment"
    target_id = int(payload["social_target_id"])
    factory = app.state.session_factory
    with factory() as session:
        anchor = session.get(SocialTarget, target_id)
        assert anchor is not None
        assert anchor.entity_kind == "table"
        assert anchor.entity_ref == _TABLE_REF
        comment = session.execute(
            select(DataProductComment).where(
                DataProductComment.social_target_id == target_id
            )
        ).scalar_one()
        assert comment.data_product_id is None
        assert comment.body_md == "first table comment"


@pytest.mark.asyncio
async def test_table_post_comment_writes_generic_audit_prefix(
    admin_socket: httpx.AsyncClient,
) -> None:
    """Audit-log target uses ``table:`` prefix, NOT legacy ``data_product:``.

    Locked decision #9 keeps the legacy prefix only for
    ``kind='dp'`` (preserves existing SIEM queries).  Every other
    kind writes the generic ``{kind}:{ref}#...`` shape from day 1.
    """
    res = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/comments",
        json={"body_md": "prefix check"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        audit_rows = (
            session.execute(
                select(AuditLog).where(
                    AuditLog.action == "audit.discussion.posted"
                )
            )
            .scalars()
            .all()
        )
        targets = [r.target for r in audit_rows]
        assert any(
            t.startswith(f"table:{_TABLE_REF}#") for t in targets
        ), f"expected generic table: prefix, got {targets!r}"
        assert not any(
            t.startswith(f"data_product:{_TABLE_REF}#") for t in targets
        ), "legacy data_product prefix must not leak for kind='table'"


@pytest.mark.asyncio
async def test_table_list_comments_returns_polymorphic_shape(
    admin_socket: httpx.AsyncClient,
) -> None:
    """GET returns ``{entity_kind, entity_ref, comments}`` shape."""
    await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/comments",
        json={"body_md": "shape probe"},
    )
    res = await admin_socket.get(
        f"/api/social/table/{_TABLE_REF}/comments"
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["entity_kind"] == "table"
    assert payload["entity_ref"] == _TABLE_REF
    assert len(payload["comments"]) >= 1
    assert payload["comments"][0]["body_md"] == "shape probe"


@pytest.mark.asyncio
async def test_table_delete_comment_soft_deletes_row(
    admin_socket: httpx.AsyncClient,
) -> None:
    """DELETE soft-deletes by setting ``deleted_at``."""
    post = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/comments",
        json={"body_md": "doomed"},
    )
    comment_id = post.json()["id"]
    res = await admin_socket.delete(
        f"/api/social/table/{_TABLE_REF}/comments/{comment_id}"
    )
    assert res.status_code == 200, res.text
    assert res.json()["deleted_at"] is not None


# ---------------------------------------------------------------------------
# kind='table' — endorsements
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_endorsement_apply_and_list(
    admin_socket: httpx.AsyncClient,
) -> None:
    """POST + GET endorsements work for kind='table'."""
    res = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/endorsements",
        json={
            "endorsement_type": "verified-by-steward",
            "note_md": "looks good",
        },
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["endorsement_type"] == "verified-by-steward"
    listing = await admin_socket.get(
        f"/api/social/table/{_TABLE_REF}/endorsements"
    )
    assert listing.status_code == 200
    j = listing.json()
    assert j["entity_kind"] == "table"
    assert j["entity_ref"] == _TABLE_REF
    assert len(j["endorsements"]) == 1


@pytest.mark.asyncio
async def test_table_endorsement_idempotent_reapply(
    admin_socket: httpx.AsyncClient,
) -> None:
    """Re-applying the same endorsement type returns the existing row."""
    first = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/endorsements",
        json={"endorsement_type": "production-ready"},
    )
    second = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/endorsements",
        json={"endorsement_type": "production-ready"},
    )
    assert first.json()["id"] == second.json()["id"]


@pytest.mark.asyncio
async def test_table_endorsement_remove(
    admin_socket: httpx.AsyncClient,
) -> None:
    """DELETE soft-deletes by setting ``removed_at``."""
    posted = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/endorsements",
        json={"endorsement_type": "under-review"},
    )
    end_id = posted.json()["id"]
    res = await admin_socket.delete(
        f"/api/social/table/{_TABLE_REF}/endorsements/{end_id}"
    )
    assert res.status_code == 200, res.text
    assert res.json()["removed_at"] is not None
    factory = app.state.session_factory
    with factory() as session:
        row = session.get(DataProductEndorsement, int(end_id))
        assert row is not None
        assert row.removed_at is not None


# ---------------------------------------------------------------------------
# kind='table' — README
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_readme_put_and_get(
    admin_socket: httpx.AsyncClient,
) -> None:
    """PUT + GET README works for kind='table'."""
    put = await admin_socket.put(
        f"/api/social/table/{_TABLE_REF}/readme",
        json={"body_md": "# Orders table\n\nBronze layer."},
    )
    assert put.status_code == 200, put.text
    assert put.json()["version_int"] == 1

    get = await admin_socket.get(f"/api/social/table/{_TABLE_REF}/readme")
    assert get.status_code == 200
    assert "Bronze layer" in get.json()["body_md"]
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(EntityReadme).where(
                EntityReadme.body_md.like("%Bronze layer%")
            )
        ).scalar_one()
        anchor = session.get(SocialTarget, row.social_target_id)
        assert anchor is not None
        assert anchor.entity_kind == "table"


@pytest.mark.asyncio
async def test_table_readme_put_noop_on_unchanged_body(
    admin_socket: httpx.AsyncClient,
) -> None:
    """Second PUT with the same body returns the existing version."""
    first = await admin_socket.put(
        f"/api/social/table/{_TABLE_REF}/readme",
        json={"body_md": "identical bytes"},
    )
    second = await admin_socket.put(
        f"/api/social/table/{_TABLE_REF}/readme",
        json={"body_md": "identical bytes"},
    )
    assert first.json()["id"] == second.json()["id"]
    assert first.json()["version_int"] == second.json()["version_int"]


# ---------------------------------------------------------------------------
# kind='table' — polymorphic follow + count
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_follow_now_writes_polymorphic_row(
    admin_socket: httpx.AsyncClient,
) -> None:
    """Follow on kind='table' writes a ``social_follows`` row (77.8.D).

    Pre-77.8 the route returned 501 because ``data_product_follows``
    composite-PK required a real DP id.  77.8.B introduced the
    sibling polymorphic table; 77.8.D flipped the handler to use
    it.  Two consecutive POSTs are idempotent.
    """
    res = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/follow"
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"followed": True, "already": False}
    again = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/follow"
    )
    assert again.status_code == 200, again.text
    assert again.json() == {"followed": True, "already": True}


@pytest.mark.asyncio
async def test_table_followers_count_reflects_polymorphic_writes(
    admin_socket: httpx.AsyncClient,
) -> None:
    """Follower count now mirrors the actual polymorphic row state."""
    await admin_socket.delete(
        f"/api/social/table/{_TABLE_REF}/follow"
    )
    res = await admin_socket.get(
        f"/api/social/table/{_TABLE_REF}/followers/count"
    )
    assert res.status_code == 200, res.text
    assert res.json() == {"count": 0, "following": False}

    await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/follow"
    )
    res2 = await admin_socket.get(
        f"/api/social/table/{_TABLE_REF}/followers/count"
    )
    assert res2.status_code == 200, res2.text
    assert res2.json() == {"count": 1, "following": True}


# ---------------------------------------------------------------------------
# kind='branch' — comments + branch-approved-for-promotion endorsement
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_branch_post_comment_creates_polymorphic_row(
    admin_socket: httpx.AsyncClient,
) -> None:
    """POST /api/social/branch/{fqn}/comments creates a polymorphic row."""
    res = await admin_socket.post(
        f"/api/social/branch/{_BRANCH_REF}/comments",
        json={"body_md": "branch discussion"},
    )
    assert res.status_code == 200, res.text
    target_id = int(res.json()["social_target_id"])
    factory = app.state.session_factory
    with factory() as session:
        anchor = session.get(SocialTarget, target_id)
        assert anchor is not None
        assert anchor.entity_kind == "branch"
        assert anchor.entity_ref == _BRANCH_REF


@pytest.mark.asyncio
async def test_branch_approved_for_promotion_endorsement(
    admin_socket: httpx.AsyncClient,
) -> None:
    """The Phase 77.3.A endorsement type is applicable on branch entities."""
    res = await admin_socket.post(
        f"/api/social/branch/{_BRANCH_REF}/endorsements",
        json={"endorsement_type": "branch-approved-for-promotion"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["endorsement_type"] == "branch-approved-for-promotion"


@pytest.mark.asyncio
async def test_branch_readme_returns_404_supports_false(
    admin_socket: httpx.AsyncClient,
) -> None:
    """Branch kind has ``supports_readme=False`` — README endpoint 404s."""
    res = await admin_socket.put(
        f"/api/social/branch/{_BRANCH_REF}/readme",
        json={"body_md": "should be rejected"},
    )
    assert res.status_code == 404, res.text


# ---------------------------------------------------------------------------
# parse_ref shape validation
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_ref_malformed_returns_400(
    admin_socket: httpx.AsyncClient,
) -> None:
    """A table ref missing parts returns 400."""
    res = await admin_socket.get("/api/social/table/cat.sch/comments")
    assert res.status_code == 400, res.text
    assert "catalog.schema.table" in res.text


@pytest.mark.asyncio
async def test_branch_ref_malformed_returns_400(
    admin_socket: httpx.AsyncClient,
) -> None:
    """A branch ref missing the __branch_ separator returns 400."""
    res = await admin_socket.get(
        "/api/social/branch/just_some_string/comments"
    )
    assert res.status_code == 400, res.text


# ---------------------------------------------------------------------------
# Capability flags — non-DP reviews / reactions return 501
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_table_reviews_return_501(
    admin_socket: httpx.AsyncClient,
) -> None:
    """Reviews on kind='table' return 501 — supports_reviews=False."""
    res = await admin_socket.get(
        f"/api/social/table/{_TABLE_REF}/reviews"
    )
    assert res.status_code == 501, res.text


@pytest.mark.asyncio
async def test_table_reactions_now_work_polymorphic(
    admin_socket: httpx.AsyncClient,
) -> None:
    """Reactions on kind='table' work end-to-end after 77.8.

    Pre-77.8 the route returned 501 because the legacy DP-id PK
    on ``data_product_reactions`` couldn't dedupe NULL rows.
    77.8.C added a polymorphic UNIQUE on
    ``(social_target_id, user_id, emoji)``; 77.8.D flipped the
    handler to use it.  Re-applying the same emoji no-ops.
    """
    res = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/reactions",
        json={"emoji": "🎉"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["added"] is True
    assert payload["emoji"] == "🎉"

    again = await admin_socket.post(
        f"/api/social/table/{_TABLE_REF}/reactions",
        json={"emoji": "🎉"},
    )
    assert again.status_code == 200, again.text
    assert again.json()["added"] is False


# ---------------------------------------------------------------------------
# DP path still works through the dispatcher (regression check)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dp_path_still_works_through_dispatcher(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """The DP delegation path stays bit-identical to 77.0.F.2."""
    del seeded_dp
    res = await admin_socket.post(
        "/api/social/dp/main.sales_gold/comments",
        json={"body_md": "DP via dispatcher"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    # DP path returns the DP-shape (``data_product_id`` key) —
    # polymorphic shape with ``entity_kind`` / ``entity_ref`` is
    # only emitted by the non-DP path.
    assert "data_product_id" in payload
    assert payload["body_md"] == "DP via dispatcher"
