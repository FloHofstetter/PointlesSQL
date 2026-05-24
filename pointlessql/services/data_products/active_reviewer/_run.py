"""End-to-end ``run_reviewer_for_dp`` — fetch config, call LLM, persist outputs."""

from __future__ import annotations

import datetime
import logging
from typing import Any, Literal

from sqlalchemy import select

from pointlessql.models.agent._agents import Agent
from pointlessql.models.catalog._data_product_active_reviewer_config import (
    DataProductActiveReviewerConfig,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services.data_products.active_reviewer._prompt import build_prompt
from pointlessql.services.data_products.active_reviewer._verdict import (
    parse_review_result,
)
from pointlessql.services.data_products.active_reviewer._writers import (
    call_llm,
    post_comment,
    write_agent_review,
    write_endorsement,
)

logger = logging.getLogger(__name__)


async def run_reviewer_for_dp(
    factory: Any,
    *,
    workspace_id: int,
    data_product_id: int,
    trigger: Literal["loop", "manual", "hermes_cron"],
    provider_default: str | None = None,
    model_default: str | None = None,
    api_key_resolver: Any = None,
    llm_call: Any = None,
) -> dict[str, Any]:
    """End-to-end one tick of the active reviewer for one DP.

    Renders the prompt, calls the LLM, posts a comment +
    endorsement, writes an :class:`AgentReview` row, and stamps
    ``config.last_run_at`` + ``config.last_run_comment_id``.

    Args:
        factory: SQLAlchemy sessionmaker.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id``.
        trigger: ``'loop'`` for the periodic loop, ``'manual'`` for
            the "test now" steward button, ``'hermes_cron'`` for the
            Hermes-side runner.
        provider_default: Provider name when the config doesn't
            carry one.  Defaults to ``'anthropic'``.
        model_default: Model id when the config doesn't carry one.
            Defaults to a Haiku model id when the provider is
            anthropic.
        api_key_resolver: Optional callable
            ``(provider, workspace_id) -> str | None`` used for
            unit tests; defaults to
            :func:`services.lens._provider_creds.decrypt_provider_key`.
        llm_call: Optional async callable
            ``(provider, model, api_key, prompt) -> str`` used for
            unit tests; defaults to :func:`call_llm`.

    Returns:
        ``{"agent_review_id", "comment_id", "endorsement_id",
        "verdict", "severity"}``.

    Raises:
        ValueError: When the DP or its active-reviewer config row is
            missing for the requested workspace.
        RuntimeError: When no API key is stored for the configured
            LLM provider.
    """
    from pointlessql.services.lens._provider_creds import decrypt_provider_key

    resolver = api_key_resolver
    runner_llm = llm_call

    with factory() as session:
        dp = session.execute(
            select(DataProduct).where(
                DataProduct.id == data_product_id,
                DataProduct.workspace_id == workspace_id,
            )
        ).scalar_one_or_none()
        if dp is None:
            raise ValueError(
                f"data_product {data_product_id} not found in workspace {workspace_id}"
            )
        catalog_name = dp.catalog_name
        schema_name = dp.schema_name
        config = session.execute(
            select(DataProductActiveReviewerConfig).where(
                DataProductActiveReviewerConfig.workspace_id == workspace_id,
                DataProductActiveReviewerConfig.data_product_id == data_product_id,
            )
        ).scalar_one_or_none()
        if config is None:
            raise ValueError(
                f"no active-reviewer config for data_product {data_product_id} "
                f"in workspace {workspace_id}"
            )
        acting_user_id = config.acting_user_id
        config_agent_slug = config.agent_slug
        agent_id: int | None = None
        if config_agent_slug:
            agent_row = session.execute(
                select(Agent).where(
                    Agent.workspace_id == workspace_id,
                    Agent.slug == config_agent_slug,
                )
            ).scalar_one_or_none()
            if agent_row is not None:
                agent_id = int(agent_row.id)
        prompt = build_prompt(session, workspace_id=workspace_id, dp=dp, config=config)

    provider_name = (
        (config.llm_provider if config is not None else None) or provider_default or "anthropic"
    )
    model = (
        (config.llm_model if config is not None else None)
        or model_default
        or "claude-haiku-4-5-20251001"
    )

    if resolver is None:
        api_key = decrypt_provider_key(factory, workspace_id=workspace_id, provider=provider_name)
    else:
        api_key = resolver(provider_name, workspace_id)
    if not api_key:
        raise RuntimeError(
            "active reviewer: no API key for provider "
            f"{provider_name!r} in workspace {workspace_id}"
        )

    if runner_llm is None:
        response_text = await call_llm(
            provider_name=provider_name,
            model=model,
            api_key=api_key,
            prompt=prompt,
        )
    else:
        response_text = await runner_llm(provider_name, model, api_key, prompt)

    verdict = parse_review_result(response_text)
    now = datetime.datetime.now(datetime.UTC)
    payload = {
        "trigger": trigger,
        "provider": provider_name,
        "model": model,
        "prompt": prompt,
        "raw_response": verdict.raw_response,
    }

    dp_ref = f"{catalog_name}.{schema_name}"
    with factory() as session:
        comment_id = post_comment(
            session,
            workspace_id=workspace_id,
            data_product_id=data_product_id,
            dp_ref=dp_ref,
            author_user_id=acting_user_id,
            body_md=verdict.comment_md,
            now=now,
            author_agent_id=agent_id,
        )
        endorsement_id: int | None = None
        if verdict.endorsement_type is not None:
            endorsement_id = write_endorsement(
                session,
                workspace_id=workspace_id,
                data_product_id=data_product_id,
                dp_ref=dp_ref,
                applied_by_user_id=acting_user_id,
                endorsement_type=verdict.endorsement_type,
                note_md=f"active reviewer ({trigger})",
                now=now,
                applied_by_agent_id=agent_id,
            )
        dp = session.execute(
            select(DataProduct).where(DataProduct.id == data_product_id)
        ).scalar_one()
        review_id = write_agent_review(
            session,
            workspace_id=workspace_id,
            dp=dp,
            severity=verdict.severity,
            summary_md=verdict.comment_md,
            payload=payload,
            now=now,
        )
        existing = session.execute(
            select(DataProductActiveReviewerConfig).where(
                DataProductActiveReviewerConfig.workspace_id == workspace_id,
                DataProductActiveReviewerConfig.data_product_id == data_product_id,
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.last_run_at = now
            existing.last_run_comment_id = comment_id
            existing.updated_at = now
            session.add(existing)
        session.commit()

    logger.info(
        "active_reviewer.tick dp=%s.%s ws=%s severity=%s trigger=%s",
        catalog_name,
        schema_name,
        workspace_id,
        verdict.severity,
        trigger,
    )
    return {
        "agent_review_id": review_id,
        "comment_id": comment_id,
        "endorsement_id": endorsement_id,
        "verdict": verdict.severity,
        "severity": verdict.severity,
    }
