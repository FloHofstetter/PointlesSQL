"""Phase 77.0.F — DP-route call-site swap populates ``social_target_id``.

Every social write that flows through a DP-scoped route now has to
populate ``social_target_id`` on the new row.  The seven tables —
comments / reviews / endorsements / follows / DP-reactions /
comment-reactions / readmes — are checked individually so a future
refactor that drops the swap on one path fails loudly here instead
of much later when 77.0.G flips the column to NOT NULL.

Coverage runs end-to-end through the real FastAPI route stack so the
test catches both the resolver wiring and the model-side column.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.catalog._data_product_comment_reaction import (
    DataProductCommentReaction,
)
from pointlessql.models.catalog._data_product_comments import (
    DataProductComment,
)
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_product_follows import (
    DataProductFollow,
)
from pointlessql.models.catalog._data_product_reaction import (
    DataProductReaction,
)
from pointlessql.models.catalog._data_product_readme import (
    DataProductReadme,
)
from pointlessql.models.catalog._data_product_reviews import (
    DataProductReview,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.social._social_target import SocialTarget

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
    """Load a DP contract through the real route stack."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(_CONTRACT_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return int(session.execute(select(DataProduct)).scalar_one().id)


def _assert_anchor(target_id: int | None, dp_id: int) -> None:
    """Resolve ``target_id`` and verify it points at the DP anchor."""
    assert target_id is not None
    factory = app.state.session_factory
    with factory() as session:
        anchor = session.execute(
            select(SocialTarget).where(SocialTarget.id == target_id)
        ).scalar_one()
        assert anchor.entity_kind == "dp"
        assert anchor.data_product_id == dp_id
        assert anchor.entity_ref == "main.sales_gold"


@pytest.fixture
async def admin_socket(
    admin_client: httpx.AsyncClient,
) -> AsyncIterator[httpx.AsyncClient]:
    """Re-export the conftest admin client under an explicit name."""
    yield admin_client


@pytest.mark.asyncio
async def test_post_comment_writes_social_target_id(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """A POSTed comment carries a non-NULL anchor pointer."""
    res = await admin_socket.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "phase77f comment"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductComment).where(
                DataProductComment.body_md == "phase77f comment"
            )
        ).scalar_one()
        _assert_anchor(row.social_target_id, seeded_dp)


@pytest.mark.asyncio
async def test_put_review_writes_social_target_id(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """A PUT review row carries a non-NULL anchor pointer."""
    res = await admin_socket.put(
        "/api/data-products/main/sales_gold/reviews",
        json={"stars": 5, "body_md": "phase77f review"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductReview).where(
                DataProductReview.body_md == "phase77f review"
            )
        ).scalar_one()
        _assert_anchor(row.social_target_id, seeded_dp)


@pytest.mark.asyncio
async def test_post_endorsement_writes_social_target_id(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """A POSTed endorsement row carries a non-NULL anchor pointer."""
    res = await admin_socket.post(
        "/api/data-products/main/sales_gold/endorsements",
        json={"endorsement_type": "verified-by-steward"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductEndorsement).where(
                DataProductEndorsement.endorsement_type
                == "verified-by-steward"
            )
        ).scalar_one()
        _assert_anchor(row.social_target_id, seeded_dp)


@pytest.mark.asyncio
async def test_post_follow_writes_social_target_id(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """A POSTed follow row carries a non-NULL anchor pointer."""
    res = await admin_socket.post(
        "/api/data-products/main/sales_gold/follow"
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductFollow).where(
                DataProductFollow.data_product_id == seeded_dp
            )
        ).scalar_one()
        _assert_anchor(row.social_target_id, seeded_dp)


@pytest.mark.asyncio
async def test_post_dp_reaction_writes_social_target_id(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """A POSTed DP-level reaction carries a non-NULL anchor pointer."""
    res = await admin_socket.post(
        "/api/data-products/main/sales_gold/reactions",
        json={"emoji": "👍"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductReaction).where(
                DataProductReaction.data_product_id == seeded_dp
            )
        ).scalar_one()
        _assert_anchor(row.social_target_id, seeded_dp)


@pytest.mark.asyncio
async def test_post_comment_reaction_writes_social_target_id(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """A POSTed comment-reaction inherits the DP anchor."""
    res_comment = await admin_socket.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "phase77f host"},
    )
    assert res_comment.status_code == 200, res_comment.text
    comment_id = int(res_comment.json()["id"])
    res_react = await admin_socket.post(
        f"/api/data-products/main/sales_gold/comments/{comment_id}/reactions",
        json={"emoji": "🎉"},
    )
    assert res_react.status_code == 200, res_react.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductCommentReaction).where(
                DataProductCommentReaction.comment_id == comment_id
            )
        ).scalar_one()
        _assert_anchor(row.social_target_id, seeded_dp)


@pytest.mark.asyncio
async def test_put_readme_writes_social_target_id(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """A PUT readme version carries a non-NULL anchor pointer."""
    res = await admin_socket.put(
        "/api/data-products/main/sales_gold/readme",
        json={"body_md": "# phase77f"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductReadme).where(
                DataProductReadme.body_md == "# phase77f"
            )
        ).scalar_one()
        _assert_anchor(row.social_target_id, seeded_dp)
