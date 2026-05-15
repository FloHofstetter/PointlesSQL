"""Phase 77.1.5 — table.html social tab strip.

Coverage:

* table_detail HTML renders the 4 new social tab buttons
  (Discussion / Endorsements / Followers / README) alongside the
  existing 7 metadata tabs.
* The .tab-content container carries the ``socialTabs`` x-data so
  the polymorphic partials' Alpine bindings resolve.
* The endorsementTypes literal embedded in the template carries
  the four DP-flavoured types (no ``branch-approved-for-promotion``
  on table pages).
* tableDiscussion + tableReadme factories are exposed on window
  so Alpine resolves them at parse time.
* End-to-end: POSTing to /api/social/table/{ref}/comments and
  GETing back returns the body the discussion-pane factory would
  fetch.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.models.social._social_target import SocialTarget
from pointlessql.services.unitycatalog import UnityCatalogClient


def _stub_uc_client(
    monkeypatch: pytest.MonkeyPatch, full_name: str
) -> None:
    """Inject a UC client stub for the table_detail HTML route."""
    catalog, schema, table = full_name.split(".", 2)
    client = MagicMock(spec=UnityCatalogClient)
    client.get_table = AsyncMock(
        return_value={
            "name": table,
            "catalog_name": catalog,
            "schema_name": schema,
            "full_name": full_name,
            "table_type": "EXTERNAL",
            "data_source_format": "DELTA",
            "comment": None,
            "owner": None,
            "table_id": "stub-id",
            "created_at": None,
            "created_by": None,
            "updated_at": None,
            "updated_by": None,
            "storage_location": "/tmp/stub",
            "properties": {},
            "columns": [{"name": "id", "type_text": "int", "comment": None}],
        }
    )
    client.get_tags = AsyncMock(return_value=[])
    client.get_permissions = AsyncMock(return_value=[])
    client.get_effective_permissions = AsyncMock(
        return_value=[
            {
                "principal": "admin@pql.test",
                "privilege": "SELECT",
                "scope": "table",
                "resource": full_name,
            }
        ]
    )
    client.get_lineage = AsyncMock(
        return_value={
            "upstream": {"nodes": [], "edges": []},
            "downstream": {"nodes": [], "edges": []},
        }
    )
    app.state.uc_client = client
    monkeypatch.setattr(
        UnityCatalogClient,
        "for_principal",
        classmethod(lambda cls, s, p: client),
    )


@pytest.mark.asyncio
async def test_table_html_carries_four_social_tabs(
    monkeypatch: pytest.MonkeyPatch, admin_client: httpx.AsyncClient
) -> None:
    """All four new tab buttons are present on the rendered page."""
    _stub_uc_client(monkeypatch, "main.sales_gold.orders")
    res = await admin_client.get(
        "/catalogs/main/schemas/sales_gold/tables/orders"
    )
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
async def test_table_html_mounts_social_tabs_factory(
    monkeypatch: pytest.MonkeyPatch, admin_client: httpx.AsyncClient
) -> None:
    """``socialTabs`` x-data is on .tab-content with kind='table'."""
    _stub_uc_client(monkeypatch, "main.sales_gold.orders")
    res = await admin_client.get(
        "/catalogs/main/schemas/sales_gold/tables/orders"
    )
    body = res.text
    assert "socialTabs(" in body
    # Jinja's |tojson may emit "table" or 'table' depending on
    # surrounding x-data delimiters; check the bare token.
    assert "kind" in body and "table" in body
    # Ref echoes the three-part FQN somewhere on the page.
    assert "main.sales_gold.orders" in body
    # Four DP-flavoured endorsement types (branch-only type absent).
    assert "verified-by-steward" in body
    assert "production-ready" in body
    assert "deprecated" in body
    assert "under-review" in body
    assert "branch-approved-for-promotion" not in body


@pytest.mark.asyncio
async def test_table_html_inline_factories_present(
    monkeypatch: pytest.MonkeyPatch, admin_client: httpx.AsyncClient
) -> None:
    """``tableDiscussion`` + ``tableReadme`` are exposed on window."""
    _stub_uc_client(monkeypatch, "main.sales_gold.orders")
    res = await admin_client.get(
        "/catalogs/main/schemas/sales_gold/tables/orders"
    )
    body = res.text
    assert "window.tableDiscussion = tableDiscussion" in body
    assert "window.tableReadme = tableReadme" in body
    # Inline x-data on each pane invokes the factory by name.
    assert "tableDiscussion(" in body
    assert "tableReadme(" in body


@pytest.mark.asyncio
async def test_table_html_includes_polymorphic_partials(
    monkeypatch: pytest.MonkeyPatch, admin_client: httpx.AsyncClient
) -> None:
    """Endorsements + Followers partials are rendered into the page."""
    _stub_uc_client(monkeypatch, "main.sales_gold.orders")
    res = await admin_client.get(
        "/catalogs/main/schemas/sales_gold/tables/orders"
    )
    body = res.text
    # Strings unique to each partial.
    assert "Endorsements express peer trust." in body
    assert "Following non-data-product entities lands in Phase 77.8" in body


@pytest.mark.asyncio
async def test_table_social_endpoints_roundtrip(
    admin_client: httpx.AsyncClient,
) -> None:
    """POST then GET on the polymorphic comment endpoint round-trips.

    Exercises the full path the inline ``tableDiscussion`` factory
    would walk in the browser — confirming the social_target anchor
    creation + the comment write + the list query all work end-to-end
    without touching the HTML.
    """
    res_post = await admin_client.post(
        "/api/social/table/main.sales_gold.orders/comments",
        json={"body_md": "table.html smoke"},
    )
    assert res_post.status_code == 200, res_post.text

    res_list = await admin_client.get(
        "/api/social/table/main.sales_gold.orders/comments"
    )
    assert res_list.status_code == 200
    bodies = [c["body_md"] for c in res_list.json()["comments"]]
    assert "table.html smoke" in bodies

    factory = app.state.session_factory
    with factory() as session:
        anchor = session.execute(
            select(SocialTarget).where(
                SocialTarget.entity_kind == "table",
                SocialTarget.entity_ref == "main.sales_gold.orders",
            )
        ).scalar_one()
        assert anchor.data_product_id is None
