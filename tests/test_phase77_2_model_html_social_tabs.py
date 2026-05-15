"""Phase 77.2 — model.html social tab strip.

Coverage:

* model_detail HTML renders the 4 new social tab buttons
  (Discussion / Endorsements / Followers / README) alongside the
  existing 4 metadata tabs (Overview / Versions / Lineage /
  Promotion).
* The .tab-content container carries the ``socialTabs`` x-data so
  the polymorphic partials' Alpine bindings resolve.
* The endorsementTypes literal embedded in the template carries
  the four DP-flavoured types (no ``branch-approved-for-promotion``
  on model pages).
* modelDiscussion + modelReadme factories are exposed on window so
  Alpine resolves them at parse time.
* End-to-end: POSTing to /api/social/model/{ref}/comments and
  GETing back returns the body the discussion-pane factory would
  fetch.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.social._social_target import SocialTarget


@pytest.fixture
def _stub_model_client(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Inject a UC client stub for the model_detail HTML route."""
    monkeypatch.setattr(
        "pointlessql.api.dependencies.effective_principal",
        lambda request: None,
    )
    mock = AsyncMock()

    async def _get_registered_model(full_name: str) -> dict:
        if full_name != "main.ml_silver.churn":
            return {}
        return {
            "name": "churn",
            "full_name": full_name,
            "catalog_name": "main",
            "schema_name": "ml_silver",
            "owner": "alice@pql.test",
            "comment": None,
        }

    async def _list_model_versions(
        full_name: str, max_results: int | None = None, page_token: str | None = None
    ) -> list[dict]:
        del max_results, page_token
        if full_name != "main.ml_silver.churn":
            return []
        return [
            {
                "version": 1,
                "status": "READY",
                "source": "file:///tmp/v1",
                "run_id": "mlf-abc",
                "comment": None,
                "model_name": "churn",
            }
        ]

    mock.get_registered_model.side_effect = _get_registered_model
    mock.list_model_versions.side_effect = _list_model_versions
    app.state.uc_client = mock
    return mock


@pytest.mark.asyncio
async def test_model_html_carries_four_social_tabs(
    _stub_model_client: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    """All four new tab buttons + panes are present on the rendered page."""
    res = await admin_client.get("/models/main.ml_silver.churn")
    assert res.status_code == 200, res.text
    body = res.text
    for tab_id in (
        'id="tab-discussion-btn"',
        'id="tab-endorsements-btn"',
        'id="tab-followers-btn"',
        'id="tab-readme-btn"',
    ):
        assert tab_id in body, f"missing tab button: {tab_id}"
    for pane_id in (
        'id="tab-discussion"',
        'id="tab-endorsements"',
        'id="tab-followers"',
        'id="tab-readme"',
    ):
        assert pane_id in body, f"missing tab pane: {pane_id}"


@pytest.mark.asyncio
async def test_model_html_mounts_social_tabs_factory(
    _stub_model_client: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    """``socialTabs`` x-data is on .tab-content with kind='model'."""
    res = await admin_client.get("/models/main.ml_silver.churn")
    body = res.text
    assert "socialTabs(" in body
    assert "kind" in body and "model" in body
    assert "main.ml_silver.churn" in body
    # Four DP-flavoured endorsement types (branch-only type absent).
    assert "verified-by-steward" in body
    assert "production-ready" in body
    assert "deprecated" in body
    assert "under-review" in body
    assert "branch-approved-for-promotion" not in body


@pytest.mark.asyncio
async def test_model_html_inline_factories_present(
    _stub_model_client: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    """``modelDiscussion`` + ``modelReadme`` are exposed on window."""
    res = await admin_client.get("/models/main.ml_silver.churn")
    body = res.text
    assert "window.modelDiscussion = modelDiscussion" in body
    assert "window.modelReadme = modelReadme" in body
    assert "modelDiscussion(" in body
    assert "modelReadme(" in body


@pytest.mark.asyncio
async def test_model_html_includes_polymorphic_partials(
    _stub_model_client: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    """Endorsements + Followers partials are rendered into the page."""
    res = await admin_client.get("/models/main.ml_silver.churn")
    body = res.text
    # Strings unique to each partial.
    assert "Endorsements express peer trust." in body
    assert "Following non-data-product entities lands in Phase 77.8" in body


@pytest.mark.asyncio
async def test_model_social_endpoints_roundtrip(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST then GET on the polymorphic comment endpoint round-trips.

    Confirms the social_target anchor creation + the comment write +
    the list query all work end-to-end for kind='model' without
    touching the HTML.
    """
    res_post = await admin_client.post(
        "/api/social/model/main.ml_silver.churn/comments",
        json={"body_md": "model.html smoke"},
    )
    assert res_post.status_code == 200, res_post.text

    res_list = await admin_client.get(
        "/api/social/model/main.ml_silver.churn/comments"
    )
    assert res_list.status_code == 200
    bodies = [c["body_md"] for c in res_list.json()["comments"]]
    assert "model.html smoke" in bodies

    factory = app.state.session_factory
    with factory() as session:
        anchor = session.execute(
            select(SocialTarget).where(
                SocialTarget.entity_kind == "model",
                SocialTarget.entity_ref == "main.ml_silver.churn",
            )
        ).scalar_one()
        assert anchor.data_product_id is None
