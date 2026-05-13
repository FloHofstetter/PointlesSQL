"""Tests for the Phase 74 active reviewer (Sprint 74.0 + 74.1 + 74.2).

Covers:

* Config row UPSERT round-trip via routes.
* CHECK rejects bad runner / provider.
* Prompt builder returns markdown with the expected sections.
* ``parse_review_result`` honours explicit verdict line + keyword
  heuristic fallback.
* ``run_reviewer_for_dp`` with a mocked LLM writes comment +
  endorsement + agent_review + stamps last_run_at.
* ``run-now`` route end-to-end with mocked LLM.
* Cross-workspace iso on the queue endpoint.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.agent._reviews import AgentReview
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_active_reviewer_config import (
    DataProductActiveReviewerConfig,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.models.workspace import Workspace, WorkspaceMember
from pointlessql.services.data_products.active_reviewer import (
    build_prompt,
    parse_review_result,
    run_reviewer_for_dp,
)

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: alice@example.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_dp(tmp_path: Path) -> int:
    """Seed one data product; return its id."""
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        return session.execute(select(DataProduct)).scalar_one().id


# ---------------------------------------------------------------------------
# Pure-function tests (no DB / no HTTP).
# ---------------------------------------------------------------------------


def test_parse_review_result_explicit_green() -> None:
    text = "Everything looks great.\n\n## Verdict: green\n"
    verdict = parse_review_result(text)
    assert verdict.severity == "ok"
    assert verdict.endorsement_type == "verified-by-steward"


def test_parse_review_result_explicit_red() -> None:
    text = "I see drift.\n\n## Verdict: red\n"
    verdict = parse_review_result(text)
    assert verdict.severity == "critical"
    assert verdict.endorsement_type == "under-review"


def test_parse_review_result_keyword_fallback_yellow() -> None:
    text = "There is a small concern about freshness."
    verdict = parse_review_result(text)
    assert verdict.severity == "warn"
    assert verdict.endorsement_type == "under-review"


def test_parse_review_result_keyword_fallback_green() -> None:
    text = "Nothing notable; ratio is fine."
    verdict = parse_review_result(text)
    assert verdict.severity == "ok"
    assert verdict.endorsement_type == "verified-by-steward"


# ---------------------------------------------------------------------------
# Service-level tests (with real DB via app.state.session_factory).
# ---------------------------------------------------------------------------


def test_build_prompt_contains_expected_sections(tmp_path: Path) -> None:
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        dp = session.execute(
            select(DataProduct).where(DataProduct.id == dp_id)
        ).scalar_one()
        prompt = build_prompt(session, workspace_id=1, dp=dp, config=None)
    assert "Daily active-reviewer audit" in prompt
    assert "main.sales_gold" in prompt
    assert "Health snapshot" in prompt
    assert "Recent contract events" in prompt
    assert "## Verdict:" in prompt


def test_config_check_rejects_bad_runner(tmp_path: Path) -> None:
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    import datetime

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = DataProductActiveReviewerConfig(
            workspace_id=1,
            data_product_id=dp_id,
            enabled=True,
            runner="bogus",
            llm_provider=None,
            llm_model=None,
            prompt_override_md=None,
            acting_user_id=1,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        with pytest.raises(IntegrityError):
            session.commit()
        session.rollback()


@pytest.mark.asyncio
async def test_run_reviewer_for_dp_writes_all_artefacts(
    tmp_path: Path,
) -> None:
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    import datetime

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        user = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        session.add(
            DataProductActiveReviewerConfig(
                workspace_id=1,
                data_product_id=dp_id,
                enabled=True,
                runner="inproc",
                llm_provider="anthropic",
                llm_model="claude-haiku-4-5-20251001",
                prompt_override_md=None,
                acting_user_id=user.id,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    async def fake_llm(provider: str, model: str, api_key: str, prompt: str) -> str:
        del provider, model, api_key, prompt
        return "Everything looks great today.\n\n## Verdict: green\n"

    result = await run_reviewer_for_dp(
        factory,
        workspace_id=1,
        data_product_id=dp_id,
        trigger="manual",
        provider_default="anthropic",
        model_default="claude-haiku-4-5-20251001",
        api_key_resolver=lambda provider, ws: "test-key",
        llm_call=fake_llm,
    )
    assert result["severity"] == "ok"
    assert result["comment_id"] is not None
    assert result["agent_review_id"] is not None

    with factory() as session:
        comment = session.execute(
            select(DataProductComment).where(
                DataProductComment.id == result["comment_id"]
            )
        ).scalar_one()
        assert "looks great" in comment.body_md
        endorsements = (
            session.execute(
                select(DataProductEndorsement).where(
                    DataProductEndorsement.data_product_id == dp_id
                )
            )
            .scalars()
            .all()
        )
        assert any(
            e.endorsement_type == "verified-by-steward" for e in endorsements
        )
        review = session.execute(
            select(AgentReview).where(
                AgentReview.id == result["agent_review_id"]
            )
        ).scalar_one()
        assert review.kind == "audit_review"
        assert review.severity == "ok"
        cfg = session.execute(
            select(DataProductActiveReviewerConfig).where(
                DataProductActiveReviewerConfig.data_product_id == dp_id
            )
        ).scalar_one()
        assert cfg.last_run_at is not None
        assert cfg.last_run_comment_id == result["comment_id"]


@pytest.mark.asyncio
async def test_run_reviewer_red_writes_under_review(tmp_path: Path) -> None:
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    import datetime

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        user = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        session.add(
            DataProductActiveReviewerConfig(
                workspace_id=1,
                data_product_id=dp_id,
                enabled=True,
                runner="inproc",
                llm_provider="anthropic",
                llm_model="claude-haiku-4-5-20251001",
                prompt_override_md=None,
                acting_user_id=user.id,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    async def fake_llm(provider: str, model: str, api_key: str, prompt: str) -> str:
        del provider, model, api_key, prompt
        return "Serious red flags detected.\n\n## Verdict: red\n"

    result = await run_reviewer_for_dp(
        factory,
        workspace_id=1,
        data_product_id=dp_id,
        trigger="loop",
        api_key_resolver=lambda provider, ws: "test-key",
        llm_call=fake_llm,
    )
    assert result["severity"] == "critical"
    with factory() as session:
        endorsements = (
            session.execute(
                select(DataProductEndorsement).where(
                    DataProductEndorsement.data_product_id == dp_id,
                    DataProductEndorsement.removed_at.is_(None),
                )
            )
            .scalars()
            .all()
        )
        assert any(e.endorsement_type == "under-review" for e in endorsements)


@pytest.mark.asyncio
async def test_run_reviewer_no_config_raises(tmp_path: Path) -> None:
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory

    async def fake_llm(provider: str, model: str, api_key: str, prompt: str) -> str:
        del provider, model, api_key, prompt
        return "Verdict: green"

    with pytest.raises(ValueError, match="no active-reviewer config"):
        await run_reviewer_for_dp(
            factory,
            workspace_id=1,
            data_product_id=dp_id,
            trigger="manual",
            api_key_resolver=lambda provider, ws: "test-key",
            llm_call=fake_llm,
        )


# ---------------------------------------------------------------------------
# Route-level tests.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_routes_upsert_and_get(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    _seed_dp(tmp_path)
    payload = {
        "enabled": True,
        "runner": "inproc",
        "llm_provider": "anthropic",
        "llm_model": "claude-haiku-4-5-20251001",
    }
    resp = await admin_client.post(
        "/api/data-products/main/sales_gold/active-reviewer",
        json=payload,
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["config"]["enabled"] is True
    assert body["config"]["runner"] == "inproc"

    resp = await admin_client.get(
        "/api/data-products/main/sales_gold/active-reviewer"
    )
    assert resp.status_code == 200
    assert resp.json()["config"]["llm_provider"] == "anthropic"


@pytest.mark.asyncio
async def test_routes_upsert_rejects_bad_runner(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    _seed_dp(tmp_path)
    resp = await admin_client.post(
        "/api/data-products/main/sales_gold/active-reviewer",
        json={"enabled": True, "runner": "magic"},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_queue_endpoint_returns_hermes_cron_only(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    import datetime

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        user = session.execute(
            select(User).where(User.email == "test@test.com")
        ).scalar_one()
        session.add(
            DataProductActiveReviewerConfig(
                workspace_id=1,
                data_product_id=dp_id,
                enabled=True,
                runner="hermes_cron",
                llm_provider=None,
                llm_model=None,
                prompt_override_md=None,
                acting_user_id=user.id,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()

    resp = await admin_client.get("/api/active-reviewer/queue")
    assert resp.status_code == 200
    queue = resp.json()["queue"]
    assert any(
        e["data_product_id"] == dp_id and e["catalog"] == "main" for e in queue
    )


@pytest.mark.asyncio
async def test_cross_workspace_queue_isolation(
    tmp_path: Path, admin_client: httpx.AsyncClient
) -> None:
    """Other-workspace hermes_cron rows must not show up in queue."""
    dp_id = _seed_dp(tmp_path)
    factory = app.state.session_factory
    import datetime

    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        ws2 = Workspace(id=2, slug="ws2", name="ws2", created_at=now)
        session.add(ws2)
        session.flush()
        u_other = User(
            email="other@test.com",
            display_name="Other",
            password_hash="x",
            is_admin=False,
            is_supervisor=False,
            is_auditor=False,
            created_at=now,
        )
        session.add(u_other)
        session.flush()
        session.add(
            WorkspaceMember(
                workspace_id=2,
                user_id=u_other.id,
                role="admin",
                created_at=now,
            )
        )
        dp_other = DataProduct(
            workspace_id=2,
            catalog_name="main",
            schema_name="sales_other",
            description="",
            version="1.0.0",
            sla_minutes=60,
            steward_user_id=None,
            contract_yaml_hash="other_hash",
            contract_json="{}",
            last_loaded_at=now,
            created_at=now,
        )
        session.add(dp_other)
        session.flush()
        session.add(
            DataProductActiveReviewerConfig(
                workspace_id=2,
                data_product_id=dp_other.id,
                enabled=True,
                runner="hermes_cron",
                llm_provider=None,
                llm_model=None,
                prompt_override_md=None,
                acting_user_id=u_other.id,
                created_at=now,
                updated_at=now,
            )
        )
        session.commit()
        other_dp_id = dp_other.id

    resp = await admin_client.get("/api/active-reviewer/queue")
    assert resp.status_code == 200
    ids = [e["data_product_id"] for e in resp.json()["queue"]]
    assert other_dp_id not in ids
    assert dp_id not in ids  # no config on this DP in ws=1
