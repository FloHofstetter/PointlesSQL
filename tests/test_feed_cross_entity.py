"""Phase 77.9 — cross-entity feed.

Coverage:

* ``_row_from_comment`` reads ``entity_kind`` + ``entity_ref`` from
  the joined ``social_targets`` row when supplied (non-DP path).
* ``_row_from_review`` does the same.
* ``GET /api/feed`` listing surfaces non-DP comments after they're
  authored against ``kind='table'``.
* ``GET /api/feed?kind=table`` narrows to table-only rows.
* ``GET /api/feed?kind=dp`` keeps the legacy DP-only view.
* ``feed.html`` carries the kind-pill row + ``setKindFilter`` Alpine
  factory state.
* The feed's response shape includes the ``kind`` echo so the
  client can render the active-pill state.
"""

from __future__ import annotations

import datetime
import pathlib

import httpx
import pytest

from pointlessql.api.feed_routes._serializers import (  # noqa: PLC2701  # test reaches private serializer module
    row_from_comment as _row_from_comment,
)
from pointlessql.api.feed_routes._serializers import (
    row_from_review as _row_from_review,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.models.social._social_target import SocialTarget

_TEMPLATES_ROOT = pathlib.Path(
    "/home/flo/git/PointlesSQL/frontend/templates"
)


def test_row_from_comment_uses_target_when_supplied() -> None:
    """Polymorphic anchor drives kind/ref/url when joined."""
    target = SocialTarget(
        id=42, workspace_id=1, entity_kind="table", entity_ref="m.s.t"
    )
    comment = DataProductComment(
        id=7,
        workspace_id=1,
        body_md="non-dp comment",
        social_target_id=42,
        author_user_id=1,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    row = _row_from_comment(comment, {}, {1: "Alice"}, target)
    assert row["entity_kind"] == "table"
    assert row["entity_ref"] == "m.s.t"
    assert row["source_url"] == "/catalogs/m/schemas/s/tables/t"
    assert row["actor_display_name"] == "Alice"


def test_row_from_comment_falls_back_to_dp_when_no_target() -> None:
    """No target → legacy DP-only path."""
    comment = DataProductComment(
        id=7,
        workspace_id=1,
        body_md="legacy dp comment",
        data_product_id=1,
        author_user_id=1,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    row = _row_from_comment(comment, {1: "main.sales"}, {}, None)
    assert row["entity_kind"] == "dp"
    assert row["entity_ref"] == "main.sales"
    assert row["source_url"] == "/data-products/main/sales"


def test_row_from_review_uses_target_when_supplied() -> None:
    """Polymorphic anchor drives kind/ref/url on reviews too."""
    target = SocialTarget(
        id=99, workspace_id=1, entity_kind="model", entity_ref="m.s.n"
    )
    review = DataProductReview(
        id=3,
        workspace_id=1,
        stars=5,
        body_md="model is great",
        social_target_id=99,
        author_user_id=1,
        created_at=datetime.datetime.now(datetime.UTC),
    )
    row = _row_from_review(review, {}, {1: "Bob"}, target)
    assert row["entity_kind"] == "model"
    assert row["source_url"] == "/models/m.s.n"
    assert row["stars"] == 5
    assert row["actor_display_name"] == "Bob"


@pytest.mark.asyncio
async def test_feed_lists_table_comment_after_authoring(
    admin_client: httpx.AsyncClient,
) -> None:
    """A table comment by the caller surfaces in the ``my`` filter."""
    post = await admin_client.post(
        "/api/social/table/main.sales.orders/comments",
        json={"body_md": "test table feed comment"},
    )
    assert post.status_code == 200, post.text
    res = await admin_client.get("/api/feed?filter=my&limit=200")
    assert res.status_code == 200
    summaries = [r.get("summary_md") for r in res.json()["rows"]]
    assert any(
        "test table feed comment" in (s or "") for s in summaries
    )


@pytest.mark.asyncio
async def test_feed_kind_filter_narrows_to_table(
    admin_client: httpx.AsyncClient,
) -> None:
    """``?kind=table`` keeps only table-kind rows; the response echoes the kind."""
    await admin_client.post(
        "/api/social/table/main.sales.orders/comments",
        json={"body_md": "narrow-to-table fixture"},
    )
    res = await admin_client.get(
        "/api/feed?filter=my&kind=table&limit=200"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "table"
    kinds = {r.get("entity_kind") for r in body["rows"]}
    assert kinds.issubset({"table"})


@pytest.mark.asyncio
async def test_feed_kind_filter_accepts_comma_separated(
    admin_client: httpx.AsyncClient,
) -> None:
    """Phase 81.K.2 — ``?kind=table,model`` keeps either kind."""
    await admin_client.post(
        "/api/social/table/main.sales.orders/comments",
        json={"body_md": "kind-comma-table fixture"},
    )
    res = await admin_client.get(
        "/api/feed?filter=my&kind=table,model&limit=200"
    )
    assert res.status_code == 200
    body = res.json()
    kinds = {r.get("entity_kind") for r in body["rows"]}
    assert kinds.issubset({"table", "model"})


@pytest.mark.asyncio
async def test_feed_kind_filter_dp_keeps_legacy_view(
    admin_client: httpx.AsyncClient,
) -> None:
    """``?kind=dp`` keeps the legacy DP-only response shape."""
    res = await admin_client.get(
        "/api/feed?filter=all&kind=dp&limit=200"
    )
    assert res.status_code == 200
    body = res.json()
    assert body["kind"] == "dp"
    kinds = {r.get("entity_kind") for r in body["rows"]}
    # Every surviving row that has an entity_kind must equal 'dp'.
    assert all(k in (None, "dp") for k in kinds)


def test_feed_html_carries_kind_filter_dropdown() -> None:
    """``feed.html`` renders the multi-select kind dropdown (Phase 81.K.1).

    Phase 81.K replaced the flat pill row with a checkbox-list
    dropdown driven by ``kindFilter`` (array) and ``kindOptions``.
    The page template now includes a partial; assert the partial
    carries the markup + the script registers every entity kind so
    newly-registered kinds light up without code change.
    """
    activity = (
        _TEMPLATES_ROOT / "pages/_partials/feed/activity_pane.html"
    ).read_text()
    scripts = (
        _TEMPLATES_ROOT / "pages/_partials/feed/scripts.html"
    ).read_text()
    assert "pql-feed-kind-menu" in activity
    assert "kindFilter" in activity
    for kind in ("'dp'", "'table'", "'model'", "'notebook'", "'saved_query'"):
        assert kind in scripts, kind
