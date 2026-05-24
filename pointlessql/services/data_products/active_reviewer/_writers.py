"""DB-write helpers for the active-reviewer end-to-end tick.

Three side-effect writes per successful tick:

* one :class:`DataProductComment` carrying the LLM response,
* one :class:`DataProductEndorsement` (de-duplicated by type),
* one :class:`AgentReview` row stamped with the verdict severity.

Plus the LLM round-trip itself, kept here so test stubs can swap it
via the ``llm_call`` injection point in
:func:`run_reviewer_for_dp`.
"""

from __future__ import annotations

import datetime
import json
from typing import Any

from sqlalchemy import select

from pointlessql.models.agent._reviews import AgentReview
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_products import DataProduct
from pointlessql.services.data_products.active_reviewer._verdict import VerdictSeverity
from pointlessql.services.social._target_resolver import get_or_create_target


def post_comment(
    session: Any,
    *,
    workspace_id: int,
    data_product_id: int,
    dp_ref: str,
    author_user_id: int,
    body_md: str,
    now: datetime.datetime,
    author_agent_id: int | None = None,
) -> int:
    """Insert one :class:`DataProductComment` row.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id``.
        dp_ref: Canonical ``catalog.schema`` reference used to
            resolve the polymorphic ``social_target`` anchor.
        author_user_id: The steward / admin acting as comment
            author (from
            :attr:`DataProductActiveReviewerConfig.acting_user_id`).
        body_md: Comment body.
        now: Wall-clock anchor.
        author_agent_id: Optional agent identity —
            when set, the comment renders as authored *by the
            agent on behalf of* ``author_user_id``.

    Returns:
        The new comment's id.
    """
    target = get_or_create_target(
        session,
        workspace_id=workspace_id,
        kind="dp",
        ref=dp_ref,
        data_product_id=data_product_id,
    )
    row = DataProductComment(
        workspace_id=workspace_id,
        data_product_id=data_product_id,
        social_target_id=target.id,
        parent_comment_id=None,
        author_user_id=author_user_id,
        author_agent_id=author_agent_id,
        body_md=body_md,
        mentioned_user_ids_json="[]",
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row.id


def write_endorsement(
    session: Any,
    *,
    workspace_id: int,
    data_product_id: int,
    dp_ref: str,
    applied_by_user_id: int,
    endorsement_type: str,
    note_md: str | None,
    now: datetime.datetime,
    applied_by_agent_id: int | None = None,
) -> int | None:
    """Insert one :class:`DataProductEndorsement` row when not duplicate.

    The endorsement table carries a UNIQUE on ``(workspace, dp,
    type, removed_at)`` so re-applying the same endorsement is a
    no-op.  We treat the no-op as "id unchanged" and return ``None``.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Tenant scope.
        data_product_id: FK on ``data_products.id``.
        dp_ref: Canonical ``catalog.schema`` reference used to
            resolve the polymorphic ``social_target`` anchor.
        applied_by_user_id: The acting user from the config row.
        endorsement_type: One of
            :data:`ENDORSEMENT_TYPES`.
        note_md: Optional rationale.
        now: Wall-clock anchor.
        applied_by_agent_id: Optional agent identity (Phase
            76.5.1) — when set, the endorsement renders as
            applied *by the agent on behalf of*
            ``applied_by_user_id``.

    Returns:
        The new endorsement id, or ``None`` when the same
        endorsement was already active.
    """
    existing = session.execute(
        select(DataProductEndorsement).where(
            DataProductEndorsement.workspace_id == workspace_id,
            DataProductEndorsement.data_product_id == data_product_id,
            DataProductEndorsement.endorsement_type == endorsement_type,
            DataProductEndorsement.removed_at.is_(None),
        )
    ).scalar_one_or_none()
    if existing is not None:
        return None
    target = get_or_create_target(
        session,
        workspace_id=workspace_id,
        kind="dp",
        ref=dp_ref,
        data_product_id=data_product_id,
    )
    row = DataProductEndorsement(
        workspace_id=workspace_id,
        data_product_id=data_product_id,
        social_target_id=target.id,
        endorsement_type=endorsement_type,
        applied_by_user_id=applied_by_user_id,
        applied_by_agent_id=applied_by_agent_id,
        applied_at=now,
        removed_at=None,
        note_md=note_md or "",
    )
    session.add(row)
    session.flush()
    return row.id


def write_agent_review(
    session: Any,
    *,
    workspace_id: int,
    dp: DataProduct,
    severity: VerdictSeverity,
    summary_md: str,
    payload: dict[str, Any],
    now: datetime.datetime,
) -> int:
    """Insert one :class:`AgentReview` row (kind='audit_review').

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Tenant scope.
        dp: Hydrated DP row (used for the period anchor).
        severity: Maps to :class:`AgentReview.severity`.
        summary_md: Body for the row.
        payload: Trace payload (prompt + raw LLM response).
        now: Wall-clock anchor.

    Returns:
        The new agent_review id.
    """
    del dp  # only used by the caller to derive the period anchor; kept for symmetry
    period_start = now - datetime.timedelta(days=1)
    row = AgentReview(
        run_id=None,
        workspace_id=workspace_id,
        kind="audit_review",
        period_start=period_start,
        period_end=now,
        severity=severity,
        summary_md=summary_md,
        payload_json=json.dumps(payload, sort_keys=True),
        delivered_to_json=None,
        created_at=now,
    )
    session.add(row)
    session.flush()
    return row.id


async def call_llm(
    *,
    provider_name: str,
    model: str,
    api_key: str,
    prompt: str,
    max_tokens: int = 1200,
) -> str:
    """Run one LLM round-trip and return the assistant text.

    Args:
        provider_name: ``'anthropic'`` or ``'openai'``.
        model: Provider-specific model identifier.
        api_key: Cleartext API key (held for the duration of one
            round-trip, then discarded).
        prompt: User prompt (the active-reviewer briefing).
        max_tokens: Generation cap.

    Returns:
        The assistant's text response.
    """
    from pointlessql.services.lens.llm_provider import get_provider

    provider = get_provider(provider_name, api_key=api_key)
    system = (
        "You are the PointlesSQL daily active reviewer for one data "
        "product.  Output a concise markdown briefing for the steward "
        "based on the supplied snapshot.  End with an explicit Verdict "
        "line."
    )
    completion = await provider.chat_with_tools(
        system=system,
        messages=[{"role": "user", "content": prompt}],
        model=model,
        max_tokens=max_tokens,
    )
    return completion.text or ""
