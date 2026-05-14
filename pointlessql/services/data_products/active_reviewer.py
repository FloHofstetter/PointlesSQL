"""Phase 74 active-reviewer service.

Promotes the Phase 19 passive ``AgentReview`` writer to an active
LLM-calling steward delegate.

Three public callables:

* :func:`build_prompt` — pure-function renderer.  Pulls
  :func:`fetch_activity_for_dp` + :func:`compute_badges_for_dp` +
  recent contract-event rows into a markdown prompt the LLM
  responds to.
* :func:`parse_review_result` — pure-function parser.  Looks for
  an explicit ``## Verdict: green | yellow | red`` line near the
  bottom of the LLM response; falls back to a keyword heuristic.
* :func:`run_reviewer_for_dp` — async entry point that fetches
  the per-DP config, builds the prompt, calls the configured LLM
  provider via :mod:`services.lens.llm_provider`, posts the
  result as a :class:`DataProductComment` + a typed
  :class:`DataProductEndorsement`, writes an
  :class:`AgentReview` row, and stamps the config's
  ``last_run_at`` / ``last_run_comment_id`` pointers.

The Hermes-cron runner (Sprint 74.2) calls the same
``run_reviewer_for_dp`` via the
``POST /api/data-products/{c}/{s}/active-reviewer/run-now``
endpoint, so both paths share one service entry-point.
"""

from __future__ import annotations

import datetime
import json
import logging
from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy import select

from pointlessql.models.agent._agents import Agent
from pointlessql.models.agent._reviews import AgentReview
from pointlessql.models.catalog._data_product_active_reviewer_config import (
    DataProductActiveReviewerConfig,
)
from pointlessql.models.catalog._data_product_comments import DataProductComment
from pointlessql.models.catalog._data_product_endorsement import (
    DataProductEndorsement,
)
from pointlessql.models.catalog._data_products import (
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.services.data_products.activity import fetch_activity_for_dp
from pointlessql.services.data_products.badges import compute_badges_for_dp
from pointlessql.services.social._target_resolver import get_or_create_target

logger = logging.getLogger(__name__)


VerdictSeverity = Literal["ok", "warn", "critical"]


@dataclass(frozen=True)
class ReviewVerdict:
    """Structured result of one active-reviewer LLM turn.

    Attributes:
        severity: Maps to :class:`AgentReview.severity` (``ok`` /
            ``warn`` / ``critical``).
        endorsement_type: ``verified-by-steward`` on green,
            ``under-review`` on yellow / red, or ``None`` when the
            steward chose to suppress endorsement writes.
        comment_md: Markdown body posted as a
            :class:`DataProductComment`.
        raw_response: The raw LLM text (kept for trace).
    """

    severity: VerdictSeverity
    endorsement_type: str | None
    comment_md: str
    raw_response: str


def build_prompt(
    session: Any,
    *,
    workspace_id: int,
    dp: DataProduct,
    config: DataProductActiveReviewerConfig | None,
) -> str:
    """Render the daily DP audit prompt the LLM responds to.

    Args:
        session: Live SQLAlchemy session.
        workspace_id: Tenant scope.
        dp: Hydrated :class:`DataProduct` row.
        config: Per-DP override config; carries the optional
            ``prompt_override_md`` appended at the end of the
            default template.  ``None`` is treated as empty.

    Returns:
        The full markdown prompt string.
    """
    activity = fetch_activity_for_dp(
        session,
        workspace_id=workspace_id,
        dp=dp,
        limit=20,
    )
    badges = compute_badges_for_dp(session, workspace_id=workspace_id, dp=dp)

    contract_events = (
        session.execute(
            select(DataProductContractEvent)
            .where(DataProductContractEvent.data_product_id == dp.id)
            .order_by(DataProductContractEvent.created_at.desc())
            .limit(5)
        )
        .scalars()
        .all()
    )

    lines: list[str] = [
        "# Daily active-reviewer audit",
        "",
        f"Data product: **{dp.catalog_name}.{dp.schema_name}**",
        f"Version: `{dp.version or 'n/a'}`",
        "",
        "## Health snapshot (last 30d)",
        f"- Agent runs touching this DP (7d): {badges.get('agent_run_count_7d', 0)}",
        f"- Freshness on-time: {badges.get('freshness_on_time_30d_pct', 0.0):.1f}%",
        f"- Downstream consumers: {badges.get('downstream_count', 0)}",
        f"- Last rollback passed: {badges.get('last_rollback_passed')}",
        "",
        "## Recent contract events (last 5)",
    ]
    if not contract_events:
        lines.append("- (none)")
    else:
        for ev in contract_events:
            ts = ev.created_at.isoformat() if ev.created_at else "?"
            lines.append(f"- `{ts}` — {ev.outcome}")
    lines.append("")

    lines.append("## Recent activity (last 20)")
    if not activity:
        lines.append("- (none)")
    else:
        for row in activity:
            lines.append(f"- [{row.kind}] {row.ts} — {row.summary}")
    lines.append("")

    if config is not None and config.prompt_override_md:
        lines.append("## Steward addendum")
        lines.append(config.prompt_override_md.strip())
        lines.append("")

    lines.extend(
        [
            "## Your task",
            (
                "Audit the data product based on the snapshot above. "
                "Write a short markdown briefing (≤ 800 words) for "
                "the steward.  Cover: notable agent activity, "
                "freshness trends, any contract drift signals, and "
                "one concrete next-step suggestion if applicable."
            ),
            "",
            (
                "End with a single line: `## Verdict: green` if "
                "everything looks healthy, `## Verdict: yellow` if "
                "you see soft warnings worth a human glance, or "
                "`## Verdict: red` if there are concrete red flags."
            ),
        ]
    )
    return "\n".join(lines)


_VERDICT_TO_SEVERITY: dict[str, VerdictSeverity] = {
    "green": "ok",
    "yellow": "warn",
    "red": "critical",
}


def parse_review_result(text: str) -> ReviewVerdict:
    """Parse one LLM response into a :class:`ReviewVerdict`.

    Looks for an explicit ``## Verdict: green | yellow | red`` line
    near the bottom.  Falls back to a keyword heuristic when the
    explicit marker is absent.

    Args:
        text: Raw LLM response body.

    Returns:
        A populated :class:`ReviewVerdict`.
    """
    raw = text or ""
    body = raw.strip()
    severity: VerdictSeverity = "ok"
    verdict_label = "green"

    for line in reversed(body.splitlines()):
        stripped = line.strip().lower()
        if stripped.startswith("## verdict:") or stripped.startswith("verdict:"):
            for marker in _VERDICT_TO_SEVERITY:
                if marker in stripped:
                    severity = _VERDICT_TO_SEVERITY[marker]
                    verdict_label = marker
                    break
            break
    else:
        lower = body.lower()
        if "red flag" in lower or "critical" in lower:
            severity = "critical"
            verdict_label = "red"
        elif "concern" in lower or "warning" in lower or "warn" in lower:
            severity = "warn"
            verdict_label = "yellow"

    endorsement_type: str | None
    if verdict_label == "green":
        endorsement_type = "verified-by-steward"
    elif verdict_label == "red":
        endorsement_type = "under-review"
    else:
        endorsement_type = "under-review"

    return ReviewVerdict(
        severity=severity,
        endorsement_type=endorsement_type,
        comment_md=body,
        raw_response=raw,
    )


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
        agent_slug: Optional agent slug (Phase 76.5.1) — when set,
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


def _post_comment(
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
        author_agent_id: Optional agent identity (Phase 76.5.1) —
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


def _write_endorsement(
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


def _write_agent_review(
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


async def _call_llm(
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
            unit tests; defaults to :func:`_call_llm`.

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
        prompt = build_prompt(
            session, workspace_id=workspace_id, dp=dp, config=config
        )

    provider_name = (
        (config.llm_provider if config is not None else None)
        or provider_default
        or "anthropic"
    )
    model = (
        (config.llm_model if config is not None else None)
        or model_default
        or "claude-haiku-4-5-20251001"
    )

    if resolver is None:
        api_key = decrypt_provider_key(
            factory, workspace_id=workspace_id, provider=provider_name
        )
    else:
        api_key = resolver(provider_name, workspace_id)
    if not api_key:
        raise RuntimeError(
            "active reviewer: no API key for provider "
            f"{provider_name!r} in workspace {workspace_id}"
        )

    if runner_llm is None:
        response_text = await _call_llm(
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
        comment_id = _post_comment(
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
            endorsement_id = _write_endorsement(
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
        review_id = _write_agent_review(
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
