"""agent-run entity-kind registration.

Coverage:

* ``run`` kind is registered in the entity registry with the
  expected ``supports_*`` flags + URL builder.
* ``#run:<uuid>`` citations resolve through the registry.
* The audit-target builder emits ``run:<uuid>#…`` (generic
  prefix; the legacy ``data_product:`` prefix is kind='dp' only —
  locked decision #9).
* The polymorphic social dispatcher routes run writes to the
  generic backend (200, not 501 like the pre-77.4 era).
* Endorsements + Followers work for ``kind='run'`` end-to-end.
* Reviews + README stay 404/501 because the registry has
  ``supports_reviews=False`` + ``supports_readme=False`` for
  agent runs (runs are transient outcomes, not curated
  artefacts).
"""

from __future__ import annotations

import httpx
import pytest

from pointlessql.api.social_routes._kind_dispatch import parse_ref
from pointlessql.services.social import entity_registry
from pointlessql.services.social.citations import resolve_citations

_RUN_UUID = "12345678-1234-1234-1234-123456789abc"


def test_run_kind_is_registered() -> None:
    """The registry exposes the ``run`` kind after 77.4."""
    assert "run" in entity_registry.all_kinds()
    spec = entity_registry.get("run")
    assert spec.label == "Run"
    assert spec.audit_target_prefix == "run"
    assert spec.supports_endorsements is True
    assert spec.supports_readme is False
    assert spec.supports_reviews is False
    assert spec.supports_stars is True
    assert spec.supports_issues is False
    assert spec.tab_keys == ("discussion", "endorsements", "followers")


def test_run_url_builder_routes_to_run_detail_page() -> None:
    """A 36-char UUID builds a ``/runs/{uuid}`` URL."""
    url = entity_registry.url_for("run", _RUN_UUID)
    assert url == f"/runs/{_RUN_UUID}"


def test_run_url_builder_falls_back_on_malformed_ref() -> None:
    """Non-UUID refs degrade to the runs index, not a crash."""
    assert entity_registry.url_for("run", "not-a-uuid") == "/runs"
    assert entity_registry.url_for("run", "") == "/runs"
    assert entity_registry.url_for("run", "12345678") == "/runs"


def test_run_audit_target_uses_generic_prefix() -> None:
    """Runs write the polymorphic ``run:`` prefix from day 1."""
    target = entity_registry.audit_target("run", _RUN_UUID, suffix="tab-discussion")
    assert target == f"run:{_RUN_UUID}#tab-discussion"


def test_run_citation_resolves_through_registry() -> None:
    """``#run:<uuid>`` renders as a markdown anchor."""
    from pointlessql.api.main import app

    body = f"see #run:{_RUN_UUID} for the failing query"
    out = resolve_citations(body, app.state.session_factory, workspace_id=1)
    short = _RUN_UUID[:8]
    assert f"[#run:{short}](/runs/{_RUN_UUID})" in out


def test_run_citation_ignores_malformed_token() -> None:
    """Refs that aren't proper UUIDs stay literal."""
    from pointlessql.api.main import app

    body = "wrong #run:not-a-uuid leftover"
    out = resolve_citations(body, app.state.session_factory, workspace_id=1)
    assert "(/runs/not-a-uuid)" not in out


def test_parse_ref_accepts_valid_uuid() -> None:
    """The polymorphic dispatcher accepts a canonical UUID."""
    assert parse_ref("run", _RUN_UUID) == _RUN_UUID


def test_parse_ref_rejects_malformed_uuid() -> None:
    """Non-UUID refs raise 400 with the contract message."""
    # converted from HTTPException to BadRequestError.
    from pointlessql.exceptions import BadRequestError

    with pytest.raises(BadRequestError) as exc:
        parse_ref("run", "not-a-uuid")
    assert exc.value.status_code == 400
    assert "36-char UUID" in exc.value.detail


@pytest.mark.asyncio
async def test_social_dispatcher_routes_run_comment_writes(
    admin_client: httpx.AsyncClient,
) -> None:
    """Run writes through ``/api/social`` succeed after 77.4."""
    res = await admin_client.post(
        f"/api/social/run/{_RUN_UUID}/comments",
        json={"body_md": "polymorphic run write OK"},
    )
    assert res.status_code == 200, res.text
    payload = res.json()
    assert payload["body_md"] == "polymorphic run write OK"
    assert "social_target_id" in payload


@pytest.mark.asyncio
async def test_social_dispatcher_rejects_malformed_run_ref(
    admin_client: httpx.AsyncClient,
) -> None:
    """Non-UUID refs return 400 with the contract message."""
    res = await admin_client.post(
        "/api/social/run/not-a-uuid/comments",
        json={"body_md": "should fail"},
    )
    assert res.status_code == 400, res.text
    assert "36-char UUID" in res.text


@pytest.mark.asyncio
async def test_run_endorsement_roundtrip(
    admin_client: httpx.AsyncClient,
) -> None:
    """Endorsement apply + list works for kind='run'."""
    res_apply = await admin_client.post(
        f"/api/social/run/{_RUN_UUID}/endorsements",
        json={"endorsement_type": "verified-by-steward"},
    )
    assert res_apply.status_code == 200, res_apply.text

    res_list = await admin_client.get(f"/api/social/run/{_RUN_UUID}/endorsements")
    assert res_list.status_code == 200
    types = {e["endorsement_type"] for e in res_list.json()["endorsements"]}
    assert "verified-by-steward" in types


@pytest.mark.asyncio
async def test_run_readme_rejected_per_registry_flag(
    admin_client: httpx.AsyncClient,
) -> None:
    """README is gated off for runs — the polymorphic handler 404s."""
    res = await admin_client.get(f"/api/social/run/{_RUN_UUID}/readme")
    assert res.status_code == 404, res.text


@pytest.mark.asyncio
async def test_run_reviews_rejected_per_registry_flag(
    admin_client: httpx.AsyncClient,
) -> None:
    """Reviews stay 501 for runs — they're transient outcomes."""
    res = await admin_client.get(f"/api/social/run/{_RUN_UUID}/reviews")
    assert res.status_code == 501, res.text
    assert "does not support reviews" in res.text
