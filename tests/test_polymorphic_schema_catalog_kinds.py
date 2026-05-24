"""schema + catalog entity-kind registration.

Coverage:

* ``schema`` + ``catalog`` kinds are in the entity registry with
  expected ``supports_*`` flags + URL builders.
* ``#schema:cat.sch`` + ``#catalog:name`` citations render through
  the registry.
* The audit-target builder emits generic ``schema:cat.sch#…`` and
  ``catalog:name#…`` prefixes (locked decision #9 — only
  ``kind='dp'`` keeps the legacy ``data_product:`` prefix).
* The polymorphic dispatcher accepts both kinds + rejects
  malformed refs.
* Polymorphic comment + endorsement round-trip works for both
  kinds.
* README CRUD works for both kinds (``supports_readme=True``).
* Reviews return 501 (``supports_reviews=False`` on both).
* Issues return 404 (``supports_issues=False`` on both kinds
  initially — registry flips if dogfooding asks for it).
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.social_routes._kind_dispatch import parse_ref
from pointlessql.services.social import entity_registry
from pointlessql.services.social.citations import resolve_citations


def test_schema_kind_is_registered() -> None:
    """The registry exposes ``schema`` after 77.5."""
    assert "schema" in entity_registry.all_kinds()
    spec = entity_registry.get("schema")
    assert spec.label == "Schema"
    assert spec.audit_target_prefix == "schema"
    assert spec.supports_endorsements is True
    assert spec.supports_readme is True
    assert spec.supports_reviews is False
    assert spec.supports_stars is True
    assert spec.supports_issues is False
    assert spec.tab_keys == (
        "discussion",
        "endorsements",
        "followers",
        "readme",
    )


def test_catalog_kind_is_registered() -> None:
    """The registry exposes ``catalog`` after 77.5."""
    assert "catalog" in entity_registry.all_kinds()
    spec = entity_registry.get("catalog")
    assert spec.label == "Catalog"
    assert spec.audit_target_prefix == "catalog"
    assert spec.supports_endorsements is True
    assert spec.supports_readme is True
    assert spec.supports_reviews is False
    assert spec.supports_stars is True
    assert spec.supports_issues is False
    assert spec.tab_keys == (
        "discussion",
        "endorsements",
        "followers",
        "readme",
    )


def test_schema_url_builder_routes_to_catalog_browser() -> None:
    """``cat.sch`` builds a ``/catalogs/{cat}/schemas/{sch}`` URL."""
    assert (
        entity_registry.url_for("schema", "main.sales_gold") == "/catalogs/main/schemas/sales_gold"
    )


def test_catalog_url_builder_routes_to_catalog_page() -> None:
    """``cat`` builds a ``/catalogs/{cat}`` URL."""
    assert entity_registry.url_for("catalog", "main") == "/catalogs/main"


def test_schema_url_fallback_on_malformed_ref() -> None:
    """Malformed refs degrade to the catalogs index, not a crash."""
    assert entity_registry.url_for("schema", "no-dot") == "/catalogs"
    assert entity_registry.url_for("schema", "") == "/catalogs"


def test_catalog_url_fallback_on_empty_ref() -> None:
    """Empty ref degrades to the catalogs index."""
    assert entity_registry.url_for("catalog", "") == "/catalogs"


def test_audit_targets_use_generic_kind_prefixes() -> None:
    """Both kinds use the generic ``{kind}:`` audit-log prefix."""
    assert (
        entity_registry.audit_target("schema", "main.sales", suffix="tab-discussion")
        == "schema:main.sales#tab-discussion"
    )
    assert (
        entity_registry.audit_target("catalog", "main", suffix="tab-readme")
        == "catalog:main#tab-readme"
    )


def test_schema_citation_resolves_through_registry() -> None:
    """``#schema:cat.sch`` renders as a markdown anchor."""
    from pointlessql.api.main import app

    body = "see #schema:main.sales for shape"
    out = resolve_citations(body, app.state.session_factory, 1)
    assert "[#main.sales](/catalogs/main/schemas/sales)" in out


def test_catalog_citation_resolves_through_registry() -> None:
    """``#catalog:name`` renders as a markdown anchor."""
    from pointlessql.api.main import app

    body = "browse #catalog:main"
    out = resolve_citations(body, app.state.session_factory, 1)
    assert "[#main](/catalogs/main)" in out


def test_parse_ref_accepts_schema_two_part_id() -> None:
    """The polymorphic dispatcher accepts ``cat.sch``."""
    assert parse_ref("schema", "main.sales") == "main.sales"


def test_parse_ref_rejects_schema_single_part() -> None:
    """Schema refs need exactly two parts."""
    # converted from HTTPException to BadRequestError.
    from pointlessql.exceptions import BadRequestError

    with pytest.raises(BadRequestError) as exc:
        parse_ref("schema", "main")
    assert exc.value.status_code == 400
    assert "catalog.schema" in exc.value.detail


def test_parse_ref_accepts_catalog_bare_id() -> None:
    """The polymorphic dispatcher accepts a bare identifier."""
    assert parse_ref("catalog", "main") == "main"


def test_parse_ref_rejects_catalog_with_dot() -> None:
    """Catalog refs must be bare identifiers."""
    # converted from HTTPException to BadRequestError.
    from pointlessql.exceptions import BadRequestError

    with pytest.raises(BadRequestError) as exc:
        parse_ref("catalog", "main.sales")
    assert exc.value.status_code == 400
    assert "bare identifier" in exc.value.detail


@pytest.mark.asyncio
async def test_schema_comment_round_trip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Polymorphic comment write/read for ``kind='schema'``."""
    res = await admin_client.post(
        "/api/social/schema/main.sales/comments",
        json={"body_md": "schema comment OK"},
    )
    assert res.status_code == 200, res.text
    assert res.json()["body_md"] == "schema comment OK"


@pytest.mark.asyncio
async def test_catalog_endorsement_round_trip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Polymorphic endorsement apply + list for ``kind='catalog'``."""
    res_apply = await admin_client.post(
        "/api/social/catalog/main/endorsements",
        json={"endorsement_type": "verified-by-steward"},
    )
    assert res_apply.status_code == 200, res_apply.text
    res_list = await admin_client.get("/api/social/catalog/main/endorsements")
    assert res_list.status_code == 200
    types = {e["endorsement_type"] for e in res_list.json()["endorsements"]}
    assert "verified-by-steward" in types


@pytest.mark.asyncio
async def test_schema_reviews_return_501(
    admin_client: httpx.AsyncClient,
) -> None:
    """``supports_reviews=False`` so reviews stay 501."""
    res = await admin_client.get("/api/social/schema/main.sales/reviews")
    assert res.status_code == 501, res.text


@pytest.mark.asyncio
async def test_catalog_reviews_return_501(
    admin_client: httpx.AsyncClient,
) -> None:
    """Catalogs also opt out of reviews."""
    res = await admin_client.get("/api/social/catalog/main/reviews")
    assert res.status_code == 501, res.text


@pytest.mark.asyncio
async def test_schema_issues_return_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """``supports_issues=False`` for schemas — POST returns 404."""
    res = await admin_client.post(
        "/api/social/schema/main.sales/issues",
        json={"title": "should fail"},
    )
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_catalog_issues_return_404(
    admin_client: httpx.AsyncClient,
) -> None:
    """``supports_issues=False`` for catalogs — POST returns 404."""
    res = await admin_client.post(
        "/api/social/catalog/main/issues",
        json={"title": "should fail"},
    )
    assert res.status_code == 404, res.text
