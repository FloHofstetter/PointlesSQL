"""Active Reviewer posts under agent identity.

Coverage:

* When ``DataProductActiveReviewerConfig.agent_slug`` is set, the
  in-proc runner stamps ``author_agent_id`` on the posted comment
  and ``applied_by_agent_id`` on the resulting endorsement.
* When the column is NULL, the existing steward-proxy path is
  used and both ``*_agent_id`` columns stay NULL — no regression
  vs Phase 74.
"""

from __future__ import annotations

import datetime
from pathlib import Path

import pytest
from sqlalchemy import select

from pointlessql.api.main import app
from pointlessql.data_products import load_contract
from pointlessql.models.agent._agents import Agent
from pointlessql.models.auth import User
from pointlessql.models.catalog._data_product_active_reviewer_config import (
    DataProductActiveReviewerConfig,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services.data_products.active_reviewer import (
    run_reviewer_for_dp,
    upsert_config,
)

VALID_YAML = """\
data_product:
  name: Sales Orders
  version: "1.0.0"
  description: Curated orders facts.
  catalog: main
  schema: sales_gold
  steward_email: test@test.com
  sla_minutes: 60
  tables:
    - name: orders
      primary_key: [order_id]
      columns:
        - {name: order_id, type: long, nullable: false}
"""


def _seed_product(tmp_path: Path) -> tuple[int, int]:
    yaml_path = tmp_path / "pointlessql.yaml"
    yaml_path.write_text(VALID_YAML, encoding="utf-8")
    factory = app.state.session_factory
    load_contract(yaml_path, factory=factory)
    with factory() as session:
        dp = session.execute(select(DataProduct)).scalar_one()
        admin = session.execute(select(User).where(User.email == "test@test.com")).scalar_one()
        return int(dp.id), int(admin.id)


async def _stub(_provider: str, _model: str, _key: str, _prompt: str) -> str:
    """Deterministic verdict body used by the active-reviewer tests."""
    return "Looks fine.\n\n## Verdict: green"


@pytest.mark.asyncio
async def test_run_reviewer_writes_agent_authorship(
    tmp_path: Path,
) -> None:
    """Config with ``agent_slug`` populates ``author_agent_id``."""
    dp_id, admin_id = _seed_product(tmp_path)
    factory = app.state.session_factory
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        session.add(
            Agent(
                workspace_id=1,
                slug="audit-reviewer",
                display_name="Audit Reviewer",
                principal_user_id=admin_id,
                avatar_kind="hermes",
                created_at=now,
                created_by_user_id=admin_id,
            )
        )
        session.commit()
        upsert_config(
            session,
            workspace_id=1,
            data_product_id=dp_id,
            enabled=True,
            runner="inproc",
            llm_provider="anthropic",
            llm_model="claude-haiku-4-5-20251001",
            prompt_override_md=None,
            acting_user_id=admin_id,
            agent_slug="audit-reviewer",
        )
        session.commit()

    await run_reviewer_for_dp(
        factory,
        workspace_id=1,
        data_product_id=dp_id,
        trigger="manual",
        api_key_resolver=lambda _provider, _ws: "test-key",
        llm_call=_stub,
    )

    with factory() as session:
        comment = (
            session.execute(
                select(DataProductComment)
                .where(DataProductComment.data_product_id == dp_id)
                .order_by(DataProductComment.id.desc())
            )
            .scalars()
            .first()
        )
        assert comment is not None
        assert comment.author_user_id == admin_id
        assert comment.author_agent_id is not None
        endorsement = (
            session.execute(
                select(DataProductEndorsement).where(
                    DataProductEndorsement.data_product_id == dp_id,
                    DataProductEndorsement.removed_at.is_(None),
                )
            )
            .scalars()
            .first()
        )
        assert endorsement is not None
        assert endorsement.applied_by_agent_id is not None
        config = session.execute(
            select(DataProductActiveReviewerConfig).where(
                DataProductActiveReviewerConfig.data_product_id == dp_id
            )
        ).scalar_one()
        assert config.agent_slug == "audit-reviewer"


@pytest.mark.asyncio
async def test_run_reviewer_no_agent_slug_keeps_steward_proxy(
    tmp_path: Path,
) -> None:
    """Config with ``agent_slug=None`` leaves ``author_agent_id`` NULL."""
    dp_id, admin_id = _seed_product(tmp_path)
    factory = app.state.session_factory
    with factory() as session:
        upsert_config(
            session,
            workspace_id=1,
            data_product_id=dp_id,
            enabled=True,
            runner="inproc",
            llm_provider="anthropic",
            llm_model="claude-haiku-4-5-20251001",
            prompt_override_md=None,
            acting_user_id=admin_id,
            agent_slug=None,
        )
        session.commit()

    await run_reviewer_for_dp(
        factory,
        workspace_id=1,
        data_product_id=dp_id,
        trigger="manual",
        api_key_resolver=lambda _provider, _ws: "test-key",
        llm_call=_stub,
    )

    with factory() as session:
        comment = (
            session.execute(
                select(DataProductComment)
                .where(DataProductComment.data_product_id == dp_id)
                .order_by(DataProductComment.id.desc())
            )
            .scalars()
            .first()
        )
        assert comment is not None
        assert comment.author_user_id == admin_id
        assert comment.author_agent_id is None
