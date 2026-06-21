"""AI gateway — read-only AI-spend governance overlay over Lens.

The Lens chat-loop already records every model round-trip: each
:class:`LensSession` pins a provider + model + owner, and each
:class:`LensMessage` carries the token counts and the best-effort cost
estimate of its turn.  This module is the unified governance *lens* on
that spend: it joins the two tables for one workspace, rolls the
metered turns up by provider, by model, and by user, splits the spend
into model-inference cost (assistant turns) versus tool / SQL cost
(tool turns), and — when the caller supplies a budget — evaluates the
accrued AI spend against warn / block thresholds with the shared
cost-budget evaluator.

The overlay is read-side only: every number comes from turns the
chat-loop already persisted, and nothing here mutates a session.  Hard
runtime spend-caps (refusing the next call once a budget is exhausted)
already live on the per-session cost gate; this surface is the
cross-session visibility + attribution layer on top.
"""

from __future__ import annotations

import dataclasses
import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select

from pointlessql.models import LensMessage, LensSession, User
from pointlessql.services.cost import evaluate_budget
from pointlessql.types import SessionFactory

#: Cap on the recent-session detail list returned alongside the rollups.
_RECENT_SESSIONS_LIMIT = 50


@dataclasses.dataclass
class _SpendBucket:
    """Mutable accumulator for one provider / model / user spend group.

    Attributes:
        key: The provider, model, or user the bucket aggregates.
        provider: Owning provider for a per-model bucket; ``None`` for
            the provider and user buckets.
        llm_cost: Summed cost of assistant (model-inference) turns.
        tool_cost: Summed cost of tool (SQL / EXPLAIN) turns.
        tokens_in: Summed prompt tokens across the group's turns.
        tokens_out: Summed completion tokens across the group's turns.
        sessions: Distinct session ids that contributed a turn.
        models: Distinct models seen in the group.
        users: Distinct owner emails seen in the group.
    """

    key: str
    provider: str | None = None
    llm_cost: float = 0.0
    tool_cost: float = 0.0
    tokens_in: int = 0
    tokens_out: int = 0
    sessions: set[int] = dataclasses.field(default_factory=set[int])
    models: set[str] = dataclasses.field(default_factory=set[str])
    users: set[str] = dataclasses.field(default_factory=set[str])

    def add(
        self,
        *,
        role: str,
        cost: float,
        tokens_in: int,
        tokens_out: int,
        session_id: int,
        model: str | None,
        user: str | None,
    ) -> None:
        """Fold one message turn into the bucket's running totals.

        Args:
            role: The turn's role (``assistant`` / ``tool`` / ``user``).
            cost: The turn's cost estimate (``0`` for user turns).
            tokens_in: Prompt tokens for the turn.
            tokens_out: Completion tokens for the turn.
            session_id: Owning session id, counted as distinct.
            model: The session's model, counted as distinct when set.
            user: The session owner's email, counted as distinct.
        """
        if role == "assistant":
            self.llm_cost += cost
        elif role == "tool":
            self.tool_cost += cost
        self.tokens_in += tokens_in
        self.tokens_out += tokens_out
        self.sessions.add(session_id)
        if model:
            self.models.add(model)
        if user:
            self.users.add(user)


def _bucket_dict(bucket: _SpendBucket) -> dict[str, Any]:
    """Serialize a spend bucket into a JSON-safe rollup row.

    Args:
        bucket: The accumulated bucket.

    Returns:
        A plain dict with the session count, the model-inference /
        tool / total spend split, token totals, and the distinct
        model / user counts (plus ``provider`` for per-model rows).
    """
    total = bucket.llm_cost + bucket.tool_cost
    row: dict[str, Any] = {
        "key": bucket.key,
        "sessions": len(bucket.sessions),
        "llm_cost": round(bucket.llm_cost, 6),
        "tool_cost": round(bucket.tool_cost, 6),
        "total_cost": round(total, 6),
        "tokens_in": bucket.tokens_in,
        "tokens_out": bucket.tokens_out,
        "distinct_models": len(bucket.models),
        "distinct_users": len(bucket.users),
    }
    if bucket.provider is not None:
        row["provider"] = bucket.provider
    return row


def _sort_key(row: dict[str, Any]) -> float:
    """Rank rollup rows by total spend, descending."""
    return float(row["total_cost"])


def ai_spend_overview(
    session_factory: SessionFactory,
    *,
    workspace_id: int,
    since: datetime.datetime | None = None,
    budget: Decimal | None = None,
) -> dict[str, Any]:
    """Build the AI-spend governance overlay for one workspace.

    Joins the workspace's Lens sessions to their message turns
    (optionally only turns at or after *since*), rolls the metered
    turns up by provider, model, and user, and — when *budget* is
    given — evaluates the total accrued spend against the budget's
    warn / block thresholds.

    Args:
        session_factory: Sessionmaker callable for the metadata DB.
        workspace_id: Workspace whose Lens spend forms the overlay.
        since: Lower bound on a turn's ``created_at``; ``None`` spans
            every turn.
        budget: Spend ceiling to evaluate the accrued cost against, or
            ``None`` to skip the budget verdict.

    Returns:
        A JSON-safe dict with ``totals`` (session/turn counts, the
        model-inference / tool / total spend split, token totals, and
        distinct provider/model/user counts), ``by_provider``,
        ``by_model`` and ``by_user`` rollup lists sorted by spend, a
        capped ``recent_sessions`` detail list, and ``budget`` (the
        :func:`evaluate_budget` verdict, or ``None`` when none was
        supplied).
    """
    by_provider: dict[str, _SpendBucket] = {}
    by_model: dict[str, _SpendBucket] = {}
    by_user: dict[str, _SpendBucket] = {}
    totals = _SpendBucket("__totals__")
    message_count = 0

    with session_factory() as session:
        sessions = {
            row.id: row
            for row in session.scalars(
                select(LensSession).where(LensSession.workspace_id == workspace_id)
            ).all()
        }
        owner_ids = {row.owner_id for row in sessions.values()}
        emails: dict[int, str] = {}
        if owner_ids:
            for user in session.scalars(select(User).where(User.id.in_(owner_ids))).all():
                emails[user.id] = user.email

        msg_stmt = (
            select(LensMessage)
            .join(LensSession, LensMessage.session_id == LensSession.id)
            .where(LensSession.workspace_id == workspace_id)
        )
        if since is not None:
            msg_stmt = msg_stmt.where(LensMessage.created_at >= since)
        for msg in session.scalars(msg_stmt).all():
            sess = sessions.get(msg.session_id)
            if sess is None:
                continue
            provider = sess.llm_provider
            model = sess.llm_model
            user = emails.get(sess.owner_id) or f"user:{sess.owner_id}"
            message_count += 1
            targets = (
                totals,
                by_provider.setdefault(provider, _SpendBucket(provider)),
                by_model.setdefault(f"{provider}:{model}", _SpendBucket(model, provider=provider)),
                by_user.setdefault(user, _SpendBucket(user)),
            )
            for bucket in targets:
                bucket.add(
                    role=msg.role,
                    cost=msg.cost_estimate,
                    tokens_in=msg.tokens_in,
                    tokens_out=msg.tokens_out,
                    session_id=msg.session_id,
                    model=model,
                    user=user,
                )

        recent_sessions = _recent_sessions(sessions, emails, since=since)

    total_cost = totals.llm_cost + totals.tool_cost
    budget_block: dict[str, Any] | None = None
    if budget is not None:
        # Evaluate on the same micro-dollar-rounded figure shown as
        # ``accrued`` so float summation drift cannot push a workspace
        # sitting exactly on its budget to a different verdict than the
        # number the console displays.
        accrued = round(total_cost, 6)
        verdict = evaluate_budget(Decimal(str(accrued)), budget)
        budget_block = {
            "amount": float(budget),
            "accrued": accrued,
            "status": verdict.status,
            "percent_used": round(verdict.percent_used, 2),
            "signal_kind": verdict.signal_kind,
        }

    return {
        "totals": {
            "sessions": len(totals.sessions),
            "message_count": message_count,
            "llm_cost": round(totals.llm_cost, 6),
            "tool_cost": round(totals.tool_cost, 6),
            "total_cost": round(total_cost, 6),
            "tokens_in": totals.tokens_in,
            "tokens_out": totals.tokens_out,
            "distinct_providers": len(by_provider),
            "distinct_models": len(by_model),
            "distinct_users": len(by_user),
        },
        "by_provider": sorted(
            (_bucket_dict(b) for b in by_provider.values()), key=_sort_key, reverse=True
        ),
        "by_model": sorted(
            (_bucket_dict(b) for b in by_model.values()), key=_sort_key, reverse=True
        ),
        "by_user": sorted((_bucket_dict(b) for b in by_user.values()), key=_sort_key, reverse=True),
        "recent_sessions": recent_sessions,
        "budget": budget_block,
    }


def _recent_sessions(
    sessions: dict[int, LensSession],
    emails: dict[int, str],
    *,
    since: datetime.datetime | None,
) -> list[dict[str, Any]]:
    """Return the most-recent sessions as a capped detail list.

    Args:
        sessions: Loaded sessions keyed by id.
        emails: Owner-id → email map for attribution.
        since: When set, only sessions last active at or after this
            bound are included.

    Returns:
        Up to :data:`_RECENT_SESSIONS_LIMIT` session dicts, newest
        first by last activity.
    """

    def activity(row: LensSession) -> datetime.datetime:
        # SQLite drops tzinfo on DateTime(timezone=True) round-trips, so
        # normalise the stored value (written as UTC) back to aware UTC
        # before comparing it against the timezone-aware *since* bound.
        stamp = row.last_message_at or row.created_at
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=datetime.UTC)
        return stamp

    rows = list(sessions.values())
    if since is not None:
        rows = [row for row in rows if activity(row) >= since]
    rows.sort(key=activity, reverse=True)
    return [
        {
            "id": row.id,
            "title": row.title,
            "provider": row.llm_provider,
            "model": row.llm_model,
            "owner": emails.get(row.owner_id) or f"user:{row.owner_id}",
            "total_cost": round(row.total_cost_estimate, 6),
            "last_active": activity(row).isoformat(),
        }
        for row in rows[:_RECENT_SESSIONS_LIMIT]
    ]
