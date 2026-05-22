"""Daily-briefing prompt renderer for the active reviewer."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from pointlessql.models.catalog._data_product_active_reviewer_config import (
    DataProductActiveReviewerConfig,
)
from pointlessql.models.catalog._data_products import (
    DataProduct,
    DataProductContractEvent,
)
from pointlessql.services.data_products.activity import fetch_activity_for_dp
from pointlessql.services.data_products.badges import compute_badges_for_dp


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
