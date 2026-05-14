"""Phase 77.1 — UC table entity-kind registration.

Coverage:

* ``table`` kind is registered in the entity registry with the
  expected ``supports_*`` flags + URL builder.
* ``#table:cat.sch.tbl`` citations resolve through the registry.
* The audit-target builder emits ``table:cat.sch.tbl#…`` (not
  the legacy DP-only ``data_product:`` prefix — locked decision
  #9 only protects the DP path).
* The polymorphic social router still raises 501 for table
  writes because the kind-specific handlers (comments / reviews /
  …) are scaffolded but not wired through ``/api/social`` yet.
  77.1.5+ flips this branch.

The actual social-tab UI on ``table.html`` ships in a follow-up
sub-phase — registering the kind first lets every cross-cutting
piece (citations, audit, fanout) work end-to-end without the UI
being live.  Pre-77.1.5 the UI sits on its existing 7 tabs.
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.services.social import entity_registry
from pointlessql.services.social.citations import resolve_citations


def test_table_kind_is_registered() -> None:
    """The registry exposes the ``table`` kind after 77.1."""
    assert "table" in entity_registry.all_kinds()
    spec = entity_registry.get("table")
    assert spec.label == "Table"
    assert spec.audit_target_prefix == "table"
    assert spec.supports_endorsements is True
    assert spec.supports_readme is True
    assert spec.supports_reviews is False  # tables don't get star-ratings
    assert spec.supports_stars is True
    assert spec.supports_issues is False  # ships in 77.7


def test_table_url_builder_routes_to_catalog_page() -> None:
    """``cat.sch.tbl`` builds a UC table detail URL."""
    url = entity_registry.url_for("table", "main.sales_gold.orders")
    assert url == "/catalogs/main/schemas/sales_gold/tables/orders"


def test_table_url_builder_falls_back_on_malformed_ref() -> None:
    """Two-part refs degrade to the catalog index, not a crash."""
    assert entity_registry.url_for("table", "cat.only") == "/catalogs"
    assert entity_registry.url_for("table", "nodots") == "/catalogs"


def test_table_audit_target_uses_generic_prefix() -> None:
    """Tables write the polymorphic ``table:`` prefix from day 1."""
    target = entity_registry.audit_target(
        "table", "main.sales_gold.orders", suffix="tab-discussion"
    )
    assert target == "table:main.sales_gold.orders#tab-discussion"


def test_table_citation_resolves_through_registry() -> None:
    """``#table:cat.sch.tbl`` renders as a markdown anchor."""
    from pointlessql.api.main import app

    body = "see #table:main.sales_gold.orders for reference"
    out = resolve_citations(body, app.state.session_factory, workspace_id=1)
    assert (
        "[#main.sales_gold.orders](/catalogs/main/schemas/sales_gold/tables/orders)"
        in out
    )


def test_table_citation_ignores_malformed_token() -> None:
    """Two-segment refs like ``#table:cat.sch`` stay literal."""
    from pointlessql.api.main import app

    body = "wrong #table:main.sales_gold only-two-parts"
    out = resolve_citations(body, app.state.session_factory, workspace_id=1)
    # No anchor rendered; the literal token survives.
    assert "[#main.sales_gold]" not in out


@pytest.mark.asyncio
async def test_social_dispatcher_returns_501_for_table_writes(
    admin_client: httpx.AsyncClient,
) -> None:
    """Table writes through /api/social still raise 501 in 77.1.

    The kind is registered (no longer 400) but the dispatcher
    lacks the per-kind handler glue — 77.1.5+ fills this in.
    """
    res = await admin_client.post(
        "/api/social/table/main.sales_gold.orders/comments",
        json={"body_md": "ignored until 77.1.5"},
    )
    assert res.status_code == 501, res.text
    assert "not yet wired" in res.text.lower()
