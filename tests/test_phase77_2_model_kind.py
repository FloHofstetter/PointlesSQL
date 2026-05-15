"""Phase 77.2 — Registered-model entity-kind registration.

Coverage:

* ``model`` kind is registered in the entity registry with the
  expected ``supports_*`` flags + URL builder.
* ``#model:cat.sch.name`` citations resolve through the registry.
* The audit-target builder emits ``model:cat.sch.name#…`` (generic
  prefix from day 1; the legacy ``data_product:`` prefix is
  kind='dp' only — locked decision #9).
* The polymorphic social dispatcher routes model writes to the
  generic backend (200, not 501 like the pre-77.1.5 era).
* Endorsements + Followers + README work for ``kind='model'``
  end-to-end.  Reviews stay 404/501 because the registry has
  ``supports_reviews=False`` for now (polymorphic upsert
  idempotency needs a partial unique-index migration — deferred
  to a later sub-phase).
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.services.social import entity_registry
from pointlessql.services.social.citations import resolve_citations


def test_model_kind_is_registered() -> None:
    """The registry exposes the ``model`` kind after 77.2."""
    assert "model" in entity_registry.all_kinds()
    spec = entity_registry.get("model")
    assert spec.label == "Model"
    assert spec.audit_target_prefix == "model"
    assert spec.supports_endorsements is True
    assert spec.supports_readme is True
    # Reviews deferred until a partial unique-index migration
    # lands; tests/branches/models all stay False until then.
    assert spec.supports_reviews is False
    assert spec.supports_stars is True
    assert spec.supports_issues is False  # ships in 77.7


def test_model_url_builder_routes_to_model_detail_page() -> None:
    """``cat.sch.name`` builds a ``/models/{full_name}`` URL."""
    url = entity_registry.url_for("model", "main.ml_silver.churn")
    assert url == "/models/main.ml_silver.churn"


def test_model_url_builder_falls_back_on_malformed_ref() -> None:
    """Two-part refs degrade to the models index, not a crash."""
    assert entity_registry.url_for("model", "cat.only") == "/models"
    assert entity_registry.url_for("model", "nodots") == "/models"


def test_model_audit_target_uses_generic_prefix() -> None:
    """Models write the polymorphic ``model:`` prefix from day 1."""
    target = entity_registry.audit_target(
        "model", "main.ml_silver.churn", suffix="tab-discussion"
    )
    assert target == "model:main.ml_silver.churn#tab-discussion"


def test_model_citation_resolves_through_registry() -> None:
    """``#model:cat.sch.name`` renders as a markdown anchor."""
    from pointlessql.api.main import app

    body = "see #model:main.ml_silver.churn for the champion"
    out = resolve_citations(body, app.state.session_factory, workspace_id=1)
    assert (
        "[#main.ml_silver.churn](/models/main.ml_silver.churn)" in out
    )


def test_model_citation_ignores_malformed_token() -> None:
    """Two-segment refs like ``#model:cat.sch`` stay literal."""
    from pointlessql.api.main import app

    body = "wrong #model:main.ml_silver only-two-parts"
    out = resolve_citations(body, app.state.session_factory, workspace_id=1)
    assert "[#main.ml_silver]" not in out


@pytest.mark.asyncio
async def test_social_dispatcher_routes_model_comment_writes(
    admin_client: httpx.AsyncClient,
) -> None:
    """Model writes through ``/api/social`` succeed after 77.2."""
    res = await admin_client.post(
        "/api/social/model/main.ml_silver.churn/comments",
        json={"body_md": "polymorphic model write OK"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["body_md"] == "polymorphic model write OK"
    assert "social_target_id" in payload


@pytest.mark.asyncio
async def test_social_dispatcher_rejects_malformed_model_ref(
    admin_client: httpx.AsyncClient,
) -> None:
    """Two-part refs return 400 with the contract message."""
    res = await admin_client.post(
        "/api/social/model/only.two/comments",
        json={"body_md": "should fail"},
    )
    assert res.status_code == 400, res.text
    assert "catalog.schema.name" in res.text


@pytest.mark.asyncio
async def test_model_endorsement_roundtrip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Endorsement apply + list works for kind='model'."""
    res_apply = await admin_client.post(
        "/api/social/model/main.ml_silver.churn/endorsements",
        json={"endorsement_type": "verified-by-steward"},
    )
    assert res_apply.status_code == 200, res_apply.text

    res_list = await admin_client.get(
        "/api/social/model/main.ml_silver.churn/endorsements"
    )
    assert res_list.status_code == 200
    types = {e["endorsement_type"] for e in res_list.json()["endorsements"]}
    assert "verified-by-steward" in types


@pytest.mark.asyncio
async def test_model_readme_roundtrip(
    admin_client: httpx.AsyncClient,
) -> None:
    """README put + get works for kind='model'."""
    res_put = await admin_client.put(
        "/api/social/model/main.ml_silver.churn/readme",
        json={"body_md": "# Churn model\n\nChampion since 2026-05-15."},
    )
    assert res_put.status_code == 200, res_put.text

    res_get = await admin_client.get(
        "/api/social/model/main.ml_silver.churn/readme"
    )
    assert res_get.status_code == 200
    assert "Churn model" in res_get.json()["body_md"]


@pytest.mark.asyncio
async def test_model_reviews_return_501_pending_migration(
    admin_client: httpx.AsyncClient,
) -> None:
    """Reviews stay 501 on models until the unique-index migration lands."""
    res = await admin_client.get(
        "/api/social/model/main.ml_silver.churn/reviews"
    )
    assert res.status_code == 501, res.text
    assert "does not support reviews" in res.text
