"""polymorphic reviews on kind='model'.

Coverage:

* ``model.supports_reviews`` is now ``True`` (was ``False`` in 77.2
  pending the unique-index migration).
* Polymorphic upsert is idempotent: two PUTs from the same user on
  the same model don't create duplicate rows.
* List endpoint returns summary + the caller's own review.
* DELETE removes the caller's own row.
* The new UNIQUE
  ``uq_dp_review_polymorphic_one_per_user`` is in the alembic-
  generated schema.
* DP reviews keep working unchanged (regression guard).
* Non-DP, non-model kinds that still have ``supports_reviews=False``
  (table, branch) keep returning 501 from the dispatcher.
"""

from __future__ import annotations

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.catalog._data_product_reviews import DataProductReview
from pointlessql.services.social import entity_registry


def test_model_supports_reviews_after_77_2_1() -> None:
    """Registry flag is flipped True now that the UNIQUE exists."""
    assert entity_registry.get("model").supports_reviews is True
    assert "reviews" in entity_registry.get("model").tab_keys


def test_polymorphic_unique_present_in_schema() -> None:
    """The new UNIQUE shows up on the model table args."""
    constraints = [c.name for c in DataProductReview.__table__.constraints if c.name is not None]
    assert "uq_dp_review_polymorphic_one_per_user" in constraints
    # Phase 78 polish dropped the legacy DP-id UNIQUE; the
    # polymorphic constraint covers DP rows via the 1:1
    # social_targets.data_product_id back-pointer.
    assert "uq_dp_review_one_per_user" not in constraints


@pytest.mark.asyncio
async def test_model_review_upsert_creates_row(
    admin_client: httpx.AsyncClient,
) -> None:
    """First PUT writes a polymorphic review row."""
    res = await admin_client.put(
        "/api/social/model/main.ml_silver.churn_rev/reviews",
        json={"stars": 4, "body_md": "Solid baseline."},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["stars"] == 4
    assert payload["body_md"] == "Solid baseline."
    assert payload["data_product_id"] is None
    assert payload["social_target_id"] is not None
    # Non-DP path leaves dp_version_at_review empty (sentinel).
    assert payload["dp_version_at_review"] == ""


@pytest.mark.asyncio
async def test_model_review_upsert_is_idempotent(
    admin_client: httpx.AsyncClient,
) -> None:
    """A second PUT updates the existing row, doesn't insert."""
    ref = "main.ml_silver.churn_idempotent"
    res_first = await admin_client.put(
        f"/api/social/model/{ref}/reviews",
        json={"stars": 3, "body_md": "v1"},
    )
    assert res_first.status_code == 200, res_first.text
    first_id = res_first.json()["id"]

    res_second = await admin_client.put(
        f"/api/social/model/{ref}/reviews",
        json={"stars": 5, "body_md": "v2"},
    )
    assert res_second.status_code == 200, res_second.text
    second = res_second.json()
    assert second["id"] == first_id  # same row, no duplicate
    assert second["stars"] == 5
    assert second["body_md"] == "v2"


@pytest.mark.asyncio
async def test_model_review_list_returns_summary_and_my_review(
    admin_client: httpx.AsyncClient,
) -> None:
    """GET returns aggregate summary + caller's row."""
    ref = "main.ml_silver.churn_list"
    await admin_client.put(
        f"/api/social/model/{ref}/reviews",
        json={"stars": 4, "body_md": "ok"},
    )
    res = await admin_client.get(f"/api/social/model/{ref}/reviews")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["summary"]["count"] == 1
    assert body["summary"]["avg_stars"] == 4.0
    assert body["my_review"] is not None
    assert body["my_review"]["stars"] == 4


@pytest.mark.asyncio
async def test_model_review_delete_removes_row(
    admin_client: httpx.AsyncClient,
) -> None:
    """DELETE drops the caller's row and is idempotent."""
    ref = "main.ml_silver.churn_delete"
    await admin_client.put(
        f"/api/social/model/{ref}/reviews",
        json={"stars": 2, "body_md": ""},
    )
    res_del = await admin_client.delete(f"/api/social/model/{ref}/reviews")
    assert res_del.status_code == 200
    assert res_del.json() == {"deleted": True}

    res_again = await admin_client.delete(f"/api/social/model/{ref}/reviews")
    assert res_again.status_code == 200
    assert res_again.json() == {"deleted": False}


@pytest.mark.asyncio
async def test_model_review_rejects_invalid_stars(
    admin_client: httpx.AsyncClient,
) -> None:
    """Out-of-range stars produce a clean 400, not a 500."""
    res = await admin_client.put(
        "/api/social/model/main.ml_silver.churn_bad/reviews",
        json={"stars": 6, "body_md": "too high"},
    )
    assert res.status_code == 400
    assert "1..5" in res.text


@pytest.mark.asyncio
async def test_table_review_still_returns_501(
    admin_client: httpx.AsyncClient,
) -> None:
    """Tables stay reviews-off in the registry."""
    res = await admin_client.get("/api/social/table/main.sales_gold.orders/reviews")
    assert res.status_code == 501
    assert "does not support reviews" in res.text


@pytest.mark.asyncio
async def test_branch_review_still_returns_501(
    admin_client: httpx.AsyncClient,
) -> None:
    """Branches stay reviews-off in the registry."""
    res = await admin_client.put(
        "/api/social/branch/main.test__branch_foo/reviews",
        json={"stars": 5},
    )
    assert res.status_code == 501


@pytest.mark.asyncio
async def test_polymorphic_review_writes_null_dp_id(
    admin_client: httpx.AsyncClient,
) -> None:
    """The persisted row has ``data_product_id`` NULL on model writes."""
    ref = "main.ml_silver.churn_nullcheck"
    res = await admin_client.put(
        f"/api/social/model/{ref}/reviews",
        json={"stars": 5, "body_md": "champion-grade"},
    )
    assert res.status_code == 200

    factory = app.state.session_factory
    with factory() as session:
        row = session.execute(
            select(DataProductReview).where(DataProductReview.id == res.json()["id"])
        ).scalar_one()
        assert row.data_product_id is None
        assert row.social_target_id is not None


@pytest.mark.asyncio
async def test_model_html_renders_reviews_tab(
    monkeypatch: pytest.MonkeyPatch, admin_client: httpx.AsyncClient
) -> None:
    """model.html ships a Reviews tab; the modelReviews factory lives
    in the ESM bundle and bootstrap.js attaches it to window.
    """
    import pathlib
    from unittest.mock import AsyncMock

    monkeypatch.setattr(
        "pointlessql.api.dependencies.effective_principal",
        lambda request: None,
    )
    mock = AsyncMock()
    mock.get_registered_model.return_value = {
        "name": "churn",
        "full_name": "main.ml_silver.churn",
        "catalog_name": "main",
        "schema_name": "ml_silver",
        "owner": "alice@pql.test",
        "comment": None,
    }
    mock.list_model_versions.return_value = []
    app.state.uc_client = mock

    res = await admin_client.get("/models/main.ml_silver.churn")
    assert res.status_code == 200, res.text
    body = res.text
    assert 'id="tab-reviews-btn"' in body
    assert 'id="tab-reviews"' in body
    assert "modelReviews(" in body  # partial carries the x-data invocation
    bootstrap = pathlib.Path("frontend/js/bootstrap.js").read_text()
    assert "window.modelReviews = modelReviews" in bootstrap
