"""Tests for the champion/challenger promotion service (Phase 21.6).

Marker round-trips, service-level validation, and the FastAPI POST
endpoint with supervisor-scope enforcement.  HTTP-level soyuz
patching is mocked at the ``UnityCatalogClient`` boundary; the
typed-client wire layer is already covered by Sprint 21.1
conformance tests.
"""

from __future__ import annotations

import datetime
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from pointlessql.api.main import app
from pointlessql.models import AgentReview
from pointlessql.services import model_promotion
from pointlessql.services.model_promotion import (
    EVENT_TYPE_MODEL_PROMOTED,
    PromotionError,
    build_model_promoted_event,
    parse_promotion_marker,
    serialize_promotion_marker,
)



def test_serialize_promotion_marker_roundtrip() -> None:
    """A serialized marker parses back to the same payload."""
    promoted_at = datetime.datetime(2026, 4, 30, 12, 0, tzinfo=datetime.UTC)
    payload = serialize_promotion_marker(
        champion_version=2,
        promoted_by="alice@example.com",
        promoted_at=promoted_at,
        reason="better recall",
        previous_champion=1,
        existing_comment=None,
    )
    parsed = parse_promotion_marker(payload)
    assert parsed is not None
    assert parsed["champion_version"] == 2
    assert parsed["previous_champion"] == 1
    assert parsed["reason"] == "better recall"
    assert parsed["promoted_by"] == "alice@example.com"
    assert parsed["promoted_at"] == promoted_at.isoformat()


def test_serialize_preserves_user_prose() -> None:
    """User-written comment text survives in front of the marker."""
    payload = serialize_promotion_marker(
        champion_version=3,
        promoted_by="bob@example.com",
        promoted_at=datetime.datetime(2026, 4, 30, tzinfo=datetime.UTC),
        reason="smoke test",
        previous_champion=None,
        existing_comment="Production model — handle with care",
    )
    chunks = payload.split("\n\n")
    assert chunks[0] == "Production model — handle with care"
    assert "_pql_promotion" in chunks[-1]


def test_serialize_replaces_old_marker_idempotently() -> None:
    """Re-promoting a version overwrites the prior marker only."""
    first = serialize_promotion_marker(
        champion_version=1,
        promoted_by="a@b.c",
        promoted_at=datetime.datetime(2026, 4, 30, tzinfo=datetime.UTC),
        reason="initial",
        previous_champion=None,
        existing_comment="user prose",
    )
    second = serialize_promotion_marker(
        champion_version=2,
        promoted_by="a@b.c",
        promoted_at=datetime.datetime(2026, 4, 30, 1, tzinfo=datetime.UTC),
        reason="upgrade",
        previous_champion=1,
        existing_comment=first,
    )
    assert second.count("_pql_promotion") == 1
    parsed = parse_promotion_marker(second)
    assert parsed is not None
    assert parsed["champion_version"] == 2
    assert parsed["previous_champion"] == 1
    assert "user prose" in second


def test_parse_promotion_marker_missing_returns_none() -> None:
    """Comment without the marker → ``None``."""
    assert parse_promotion_marker(None) is None
    assert parse_promotion_marker("") is None
    assert parse_promotion_marker("plain user text") is None


def test_parse_promotion_marker_coexists_with_pql_link() -> None:
    """A ``_pql_link`` marker in the same comment is ignored."""
    link = json.dumps({"_pql_link": {"agent_run_id": "r1"}}, sort_keys=True)
    promo = json.dumps(
        {"_pql_promotion": {"champion_version": 5, "promoted_by": "x"}},
        sort_keys=True,
    )
    combined = f"prose\n\n{link}\n\n{promo}"
    parsed = parse_promotion_marker(combined)
    assert parsed is not None
    assert parsed["champion_version"] == 5


def test_build_model_promoted_event_shape() -> None:
    """The CloudEvents envelope carries the expected fields."""
    promoted_at = datetime.datetime(2026, 4, 30, 12, tzinfo=datetime.UTC)
    envelope = build_model_promoted_event(
        model_full_name="cat.sch.model",
        champion_version=4,
        previous_champion=3,
        promoted_by="alice@x",
        reason="better f1",
        promoted_at=promoted_at,
        review_id=42,
    )
    assert envelope["specversion"] == "1.0"
    assert envelope["type"] == EVENT_TYPE_MODEL_PROMOTED
    assert envelope["source"] == "/pointlessql/agent_reviews/42"
    assert envelope["subject"] == "cat.sch.model@v4"
    assert envelope["data"]["champion_version"] == 4
    assert envelope["data"]["previous_champion"] == 3
    assert envelope["data"]["review_id"] == 42


def test_build_event_omits_previous_champion_when_none() -> None:
    """First-time promotion has no ``previous_champion`` field."""
    envelope = build_model_promoted_event(
        model_full_name="cat.sch.model",
        champion_version=1,
        previous_champion=None,
        promoted_by="alice@x",
        reason="initial",
        promoted_at=datetime.datetime.now(datetime.UTC),
        review_id=None,
    )
    assert "previous_champion" not in envelope["data"]
    assert "review_id" not in envelope["data"]
    assert envelope["source"] == "/pointlessql/model_promotion"


# ---------------------------------------------------------------------------
# promote_version + endpoint tests
# ---------------------------------------------------------------------------


@pytest.fixture
def uc_for_promotion(monkeypatch: pytest.MonkeyPatch) -> AsyncMock:
    """Mock UC client + force ``effective_principal`` to ``None``."""
    monkeypatch.setattr(
        "pointlessql.api.dependencies.effective_principal",
        lambda request: None,
    )
    mock = AsyncMock()
    state: dict[str, str | None] = {"comment": None}

    async def _get_registered_model(full_name):
        if full_name != "cat.sch.model":
            return {}
        return {
            "name": "model",
            "full_name": full_name,
            "catalog_name": "cat",
            "schema_name": "sch",
            "comment": state["comment"],
        }

    async def _list_model_versions(full_name, max_results=None, page_token=None):
        if full_name != "cat.sch.model":
            return []
        return [
            {"version": 1, "status": "READY", "comment": None},
            {"version": 2, "status": "READY", "comment": None},
            {"version": 3, "status": "PENDING_REGISTRATION", "comment": None},
        ]

    async def _get_model_version(full_name, version):
        for v in await _list_model_versions(full_name):
            if v["version"] == version:
                return v
        return {}

    async def _update_registered_model(full_name, comment=None, new_name=None):
        if comment is not None:
            state["comment"] = comment
        return {"full_name": full_name, "comment": state["comment"]}

    mock.get_registered_model.side_effect = _get_registered_model
    mock.list_model_versions.side_effect = _list_model_versions
    mock.get_model_version.side_effect = _get_model_version
    mock.update_registered_model.side_effect = _update_registered_model

    app.state.uc_client = mock
    return mock


@pytest.mark.asyncio
async def test_get_current_champion_falls_back_to_latest_ready(
    uc_for_promotion: AsyncMock,
) -> None:
    """No marker → highest READY version."""
    champion = await model_promotion.get_current_champion(uc_for_promotion, "cat.sch.model")
    assert champion == 2  # v3 is PENDING, v2 is highest READY


@pytest.mark.asyncio
async def test_promote_version_writes_marker_and_review(
    uc_for_promotion: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    """Successful promote: marker patched, review row inserted, event built."""
    factory = app.state.session_factory
    result = await model_promotion.promote_version(
        factory,
        uc_for_promotion,
        "cat.sch.model",
        target_version=1,
        promoted_by="alice@x",
        reason="rollback to v1",
    )
    assert result["champion_version"] == 1
    assert result["previous_champion"] == 2
    assert result["review_id"] is not None
    assert result["event"]["type"] == EVENT_TYPE_MODEL_PROMOTED

    # The ``UpdateRegisteredModel`` call must have fired with the marker.
    assert uc_for_promotion.update_registered_model.called
    call = uc_for_promotion.update_registered_model.call_args
    assert "_pql_promotion" in call.kwargs["comment"]

    # And a review row exists.
    with factory() as session:
        review = session.get(AgentReview, result["review_id"])
        assert review is not None
        assert review.kind == "model_promotion"
        assert review.severity == "ok"
        payload = json.loads(review.payload_json or "{}")
        assert payload["champion_version"] == 1
        assert payload["previous_champion"] == 2


@pytest.mark.asyncio
async def test_promote_blocks_when_already_champion(
    uc_for_promotion: AsyncMock,
) -> None:
    """v2 is the default champion (highest READY); promoting v2 is rejected."""
    factory = app.state.session_factory
    with pytest.raises(PromotionError, match="already champion"):
        await model_promotion.promote_version(
            factory,
            uc_for_promotion,
            "cat.sch.model",
            target_version=2,
            promoted_by="alice@x",
            reason="no-op",
        )


@pytest.mark.asyncio
async def test_promote_blocks_when_not_ready(
    uc_for_promotion: AsyncMock,
) -> None:
    """v3 is PENDING_REGISTRATION → rejected."""
    factory = app.state.session_factory
    with pytest.raises(PromotionError, match="not READY"):
        await model_promotion.promote_version(
            factory,
            uc_for_promotion,
            "cat.sch.model",
            target_version=3,
            promoted_by="alice@x",
            reason="ignored",
        )


@pytest.mark.asyncio
async def test_promote_blocks_empty_reason(uc_for_promotion: AsyncMock) -> None:
    """Empty reason is rejected."""
    factory = app.state.session_factory
    with pytest.raises(PromotionError, match="reason"):
        await model_promotion.promote_version(
            factory,
            uc_for_promotion,
            "cat.sch.model",
            target_version=1,
            promoted_by="alice@x",
            reason="   ",
        )


@pytest.mark.asyncio
async def test_promote_blocks_when_version_missing(
    uc_for_promotion: AsyncMock,
) -> None:
    """Unknown target version → ``PromotionError``."""
    factory = app.state.session_factory
    with pytest.raises(PromotionError, match="not found"):
        await model_promotion.promote_version(
            factory,
            uc_for_promotion,
            "cat.sch.model",
            target_version=99,
            promoted_by="alice@x",
            reason="missing",
        )


@pytest.mark.asyncio
async def test_promote_endpoint_requires_supervisor(
    uc_for_promotion: AsyncMock, non_admin_client: httpx.AsyncClient
) -> None:
    """A non-admin cookie user is rejected at the supervisor gate."""
    resp = await non_admin_client.post(
        "/api/models/cat.sch.model/promote",
        json={"target_version": 1, "reason": "test"},
    )
    assert resp.status_code in (401, 403)


@pytest.mark.asyncio
async def test_promote_endpoint_admin_succeeds(
    uc_for_promotion: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    """Admin cookie passes ``require_supervisor`` and gets the event."""
    resp = await admin_client.post(
        "/api/models/cat.sch.model/promote",
        json={"target_version": 1, "reason": "rollback"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["champion_version"] == 1
    assert body["previous_champion"] == 2
    assert body["event"]["type"] == EVENT_TYPE_MODEL_PROMOTED


@pytest.mark.asyncio
async def test_get_promotion_endpoint_returns_history(
    uc_for_promotion: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    """After promote, GET /promotion shows champion + history."""
    post = await admin_client.post(
        "/api/models/cat.sch.model/promote",
        json={"target_version": 1, "reason": "test"},
    )
    assert post.status_code == 200, post.text

    resp = await admin_client.get("/api/models/cat.sch.model/promotion")
    assert resp.status_code == 200
    body = resp.json()
    assert body["champion_version"] == 1
    assert len(body["history"]) >= 1
    assert body["history"][0]["champion_version"] == 1
    assert body["history"][0]["reason"] == "test"


@pytest.mark.asyncio
async def test_promote_endpoint_422_on_validation_error(
    uc_for_promotion: AsyncMock, admin_client: httpx.AsyncClient
) -> None:
    """Promoting the current champion → 422 ``promotion_error``."""
    resp = await admin_client.post(
        "/api/models/cat.sch.model/promote",
        json={"target_version": 2, "reason": "no-op"},
    )
    # Phase 43.3: PromotionError is now a PointlessSQLError(422); the
    # centralised handler renders it as ``promotion_error``.
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == "promotion_error"
    assert "already champion" in body["detail"]
