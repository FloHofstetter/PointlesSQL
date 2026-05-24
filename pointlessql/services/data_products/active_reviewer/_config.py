"""Per-DP active-reviewer config CRUD + opt-in enumerator."""

from __future__ import annotations

import datetime
from typing import Any, Literal

from sqlalchemy import select

from pointlessql.models.catalog._data_product_active_reviewer_config import (
    DataProductActiveReviewerConfig,
)
from pointlessql.models.catalog._data_products import DataProduct


def upsert_config(
    session: Any,
    *,
    workspace_id: int,
    data_product_id: int,
    enabled: bool,
    runner: str,
    llm_provider: str | None,
    llm_model: str | None,
    prompt_override_md: str | None,
    acting_user_id: int,
    agent_slug: str | None = None,
) -> DataProductActiveReviewerConfig:
    """UPSERT one per-DP active-reviewer config row.

    Args:
        session: Live SQLAlchemy session (caller commits).
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id``.
        enabled: Master switch.
        runner: ``'inproc'`` or ``'hermes_cron'``.
        llm_provider: ``'anthropic'`` / ``'openai'`` / ``None``.
        llm_model: Per-DP model override.
        prompt_override_md: Markdown appended to the default prompt.
        acting_user_id: Steward / admin who enabled or updated the
            reviewer.  Future comments + endorsements written by the
            in-proc runner carry this as the author.
        agent_slug: Optional agent slug — when set,
            the reviewer's comment + endorsement are additionally
            stamped with the agent identity so the row renders as
            authored *by the agent on behalf of* ``acting_user_id``.
            ``None`` falls back to the steward-proxy posting path.

    Returns:
        The persisted row (attached to *session*).
    """
    now = datetime.datetime.now(datetime.UTC)
    existing = session.execute(
        select(DataProductActiveReviewerConfig).where(
            DataProductActiveReviewerConfig.workspace_id == workspace_id,
            DataProductActiveReviewerConfig.data_product_id == data_product_id,
        )
    ).scalar_one_or_none()
    if existing is None:
        row = DataProductActiveReviewerConfig(
            workspace_id=workspace_id,
            data_product_id=data_product_id,
            enabled=enabled,
            runner=runner,
            llm_provider=llm_provider,
            llm_model=llm_model,
            prompt_override_md=prompt_override_md,
            acting_user_id=acting_user_id,
            agent_slug=agent_slug,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        return row
    existing.enabled = enabled
    existing.runner = runner
    existing.llm_provider = llm_provider
    existing.llm_model = llm_model
    existing.prompt_override_md = prompt_override_md
    existing.acting_user_id = acting_user_id
    existing.agent_slug = agent_slug
    existing.updated_at = now
    session.add(existing)
    return existing


def iter_opted_in_dp_ids(
    factory: Any,
    *,
    runner: Literal["inproc", "hermes_cron"],
) -> list[tuple[int, int, str, str]]:
    """Return ``(workspace_id, dp_id, catalog, schema)`` tuples opted into *runner*.

    Used by:

    * the in-proc loop (``runner='inproc'``) to enumerate which DPs
      to tick on this wake;
    * the Hermes-cron queue endpoint (``runner='hermes_cron'``) to
      list which DPs the cron job should process.

    Args:
        factory: SQLAlchemy sessionmaker.
        runner: Which runner type to filter on.

    Returns:
        A list of ``(workspace_id, data_product_id, catalog,
        schema)`` tuples.  Empty list when nothing is opted in.
    """
    with factory() as session:
        rows = (
            session.execute(
                select(
                    DataProductActiveReviewerConfig.workspace_id,
                    DataProductActiveReviewerConfig.data_product_id,
                    DataProduct.catalog_name,
                    DataProduct.schema_name,
                )
                .join(
                    DataProduct,
                    DataProduct.id
                    == DataProductActiveReviewerConfig.data_product_id,
                )
                .where(
                    DataProductActiveReviewerConfig.enabled.is_(True),
                    DataProductActiveReviewerConfig.runner == runner,
                )
            )
            .all()
        )
    return [(int(ws), int(dp_id), str(cat), str(sch)) for ws, dp_id, cat, sch in rows]
