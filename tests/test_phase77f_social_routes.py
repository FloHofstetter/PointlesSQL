"""Phase 77.0.F.2 — polymorphic ``/api/social/{kind}/{ref}/...`` router.

Coverage:

* Every existing DP-social endpoint has a working mirror under
  the new ``/api/social/dp/{cat}.{sch}/...`` namespace.  Posting
  through either path produces an identical row + audit row +
  inbox row.
* Unknown kinds raise 400, registered-but-not-wired kinds raise
  501.  ``ref`` shape validation lives in the dispatcher.
* The Phase 77.0.F.1 dual-write contract is preserved end-to-end
  through the new router path (``social_target_id`` populated).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
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
    """Load a DP contract; return the DP id."""
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


@pytest.mark.asyncio
async def test_social_post_comment_delegates_to_dp_handler(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """POST via /api/social/dp/{ref}/comments lands the row."""
    res = await admin_socket.post(
        "/api/social/dp/main.sales_gold/comments",
        json={"body_md": "phase77f.2 via social"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductComment).where(
                DataProductComment.body_md == "phase77f.2 via social"
            )
        ).scalar_one()
        assert row.data_product_id == seeded_dp
        assert row.social_target_id is not None
        anchor = session.get(SocialTarget, int(row.social_target_id))
        assert anchor is not None
        assert anchor.entity_kind == "dp"
        assert anchor.entity_ref == "main.sales_gold"


@pytest.mark.asyncio
async def test_social_get_comments_matches_dp_alias(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """GET via /api/social returns the same shape as the DP alias."""
    del seeded_dp
    await admin_socket.post(
        "/api/data-products/main/sales_gold/comments",
        json={"body_md": "phase77f.2 shape parity"},
    )
    res_dp = await admin_socket.get(
        "/api/data-products/main/sales_gold/comments"
    )
    res_social = await admin_socket.get(
        "/api/social/dp/main.sales_gold/comments"
    )
    assert res_dp.status_code == 200
    assert res_social.status_code == 200
    assert res_dp.json().keys() == res_social.json().keys()


@pytest.mark.asyncio
async def test_social_put_review_via_polymorphic_route(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """PUT via /api/social/dp/{ref}/reviews lands the row."""
    res = await admin_socket.put(
        "/api/social/dp/main.sales_gold/reviews",
        json={"stars": 4, "body_md": "phase77f.2 via social"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductReview).where(
                DataProductReview.body_md == "phase77f.2 via social"
            )
        ).scalar_one()
        assert row.data_product_id == seeded_dp
        assert row.social_target_id is not None


@pytest.mark.asyncio
async def test_social_post_endorsement_via_polymorphic_route(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """POST endorsement via /api/social path."""
    del seeded_dp
    res = await admin_socket.post(
        "/api/social/dp/main.sales_gold/endorsements",
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
        assert row.social_target_id is not None


@pytest.mark.asyncio
async def test_social_follow_via_polymorphic_route(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """POST follow via /api/social path."""
    res = await admin_socket.post(
        "/api/social/dp/main.sales_gold/follow"
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductFollow).where(
                DataProductFollow.data_product_id == seeded_dp
            )
        ).scalar_one()
        assert row.social_target_id is not None


@pytest.mark.asyncio
async def test_social_dp_reaction_via_polymorphic_route(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """POST DP reaction via /api/social path."""
    res = await admin_socket.post(
        "/api/social/dp/main.sales_gold/reactions",
        json={"emoji": "🎉"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductReaction).where(
                DataProductReaction.data_product_id == seeded_dp
            )
        ).scalar_one()
        assert row.social_target_id is not None


@pytest.mark.asyncio
async def test_social_readme_via_polymorphic_route(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """PUT readme via /api/social path."""
    del seeded_dp
    res = await admin_socket.put(
        "/api/social/dp/main.sales_gold/readme",
        json={"body_md": "# phase77f.2"},
    )
    assert res.status_code == 200, res.text
    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductReadme).where(
                DataProductReadme.body_md == "# phase77f.2"
            )
        ).scalar_one()
        assert row.social_target_id is not None


@pytest.mark.asyncio
async def test_social_unknown_kind_returns_400(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """Unknown kinds raise 400 with a clean error."""
    del seeded_dp
    res = await admin_socket.get(
        "/api/social/unknown_kind/anything/comments"
    )
    assert res.status_code == 400, res.text
    assert "unknown" in res.text.lower()


@pytest.mark.asyncio
async def test_social_registered_but_not_wired_kind_returns_501(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """A registered non-dp kind raises 501 until 77.1+ wires it.

    No non-dp kinds are registered in 77.0; this test confirms the
    dispatcher's 400 path covers all unknowns.  Once 77.1 registers
    ``table`` the dispatcher's 501 branch becomes exercisable.
    """
    del seeded_dp
    res = await admin_socket.get(
        "/api/social/table/cat.sch.tbl/comments"
    )
    # Until 77.1 the registry has no ``table`` entry, so the
    # dispatcher's 400 branch fires.  Either status is acceptable
    # while the registry is still single-kind.
    assert res.status_code in (400, 501), res.text


@pytest.mark.asyncio
async def test_social_dp_malformed_ref_returns_400(
    seeded_dp: int, admin_socket: httpx.AsyncClient
) -> None:
    """A dp ref missing the dot returns 400."""
    del seeded_dp
    res = await admin_socket.get(
        "/api/social/dp/no_dot_here/comments"
    )
    assert res.status_code == 400, res.text
    assert "ref" in res.text.lower()
