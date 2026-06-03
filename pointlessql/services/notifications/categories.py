"""Central feed-category registry.

Every feed row carries a coarse ``category`` (which lane of the
platform it belongs to) and a ``severity`` (how loud it should be).
Both are *derived* from the row's ``event_type`` (for fanned-out
notifications) or ``signal_kind`` (for the actionable-signal ledger),
so there is no stored column to migrate or backfill — ``event_type``
is already persisted on every ``user_notifications`` row.

The categories are the filter chips the feed exposes:

* ``social``     — comments, reviews, reactions, mentions, issues, badges
* ``approval``   — agent runs waiting on / resolved by a human
* ``health``     — alerts, SLO / contract / freshness breaches
* ``pipeline``   — job / ingest failures and other run lifecycle events
* ``governance`` — branch promotions, published audit reviews

Severity is one of ``info`` / ``warn`` / ``error`` and drives the
card's left-border accent.

The frontend mirrors this map in ``feed.js`` (``_classifyCategory``)
so SSE-built rows bucket the same way without a round-trip.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

# Valid category keys, in display order. ``all`` is the implicit
# no-filter view and is not stored on rows.
CATEGORIES: tuple[str, ...] = ("approval", "health", "social", "pipeline", "governance")

DEFAULT_CATEGORY = "social"
DEFAULT_SEVERITY = "info"

# Attention tiers — a second axis orthogonal to category. Where
# ``category`` says *which lane* a row belongs to, ``attention`` says
# *how much it wants from the reader*: ``act`` rows are unresolved work
# (approvals / open signals), ``for_you`` rows are explicitly addressed
# to the reader (an @mention, a directed terminal fact), and ``ambient``
# rows are awareness-only (activity on followed entities). The feed
# drains ``act`` + ``for_you`` to a finishable "needs you" inbox and
# lets ``ambient`` flow on forever behind a seen-cursor.
ATTENTION_ACT = "act"
ATTENTION_FOR_YOU = "for_you"
ATTENTION_AMBIENT = "ambient"

# Ordered (event_type_prefix, category, severity) rules. First match
# wins, so put exact/longer prefixes before their broader siblings.
_EVENT_RULES: tuple[tuple[str, str, str], ...] = (
    ("pointlessql.agent_run.needs_approval", "approval", "warn"),
    ("pointlessql.agent_run.approved", "approval", "info"),
    ("pointlessql.agent_run.denied", "approval", "warn"),
    ("pointlessql.agent_run.failed", "pipeline", "error"),
    ("pointlessql.agent_run.", "pipeline", "info"),
    ("pointlessql.alert.", "health", "error"),
    ("pointlessql.slo.", "health", "warn"),
    ("pointlessql.contract.", "health", "error"),
    ("pointlessql.freshness.", "health", "warn"),
    ("pointlessql.job_run.failed", "pipeline", "error"),
    ("pointlessql.ingest.failed", "pipeline", "error"),
    ("pointlessql.ingest.", "pipeline", "info"),
    ("pointlessql.branch.", "governance", "info"),
    ("pointlessql.agent_review.", "governance", "info"),
    ("pointlessql.issue.", "social", "info"),
    ("pointlessql.user.badge_", "social", "info"),
    ("pointlessql.data_product.", "social", "info"),
)

# Actionable-signal ledger kinds → (category, severity). Used by the
# Wave-4 signal serializer; kept here so both lanes share one source
# of truth.
_SIGNAL_RULES: dict[str, tuple[str, str]] = {
    "alert_firing": ("health", "error"),
    "slo_breach": ("health", "warn"),
    "contract_violation": ("health", "error"),
    "freshness_stale": ("health", "warn"),
    "job_failed": ("pipeline", "error"),
    "ingest_failed": ("pipeline", "error"),
}


def classify_category(event_type: str | None) -> tuple[str, str]:
    """Return ``(category, severity)`` for a notification event type.

    Mentions are special-cased to ``social`` regardless of the entity
    they fired on; everything else matches by prefix. Unknown event
    types fall through to ``(social, info)`` so a new social event is
    never hidden from the default stream.

    Args:
        event_type: ``pointlessql.<scope>.<verb>`` identifier, or
            ``None`` for rows that predate event typing.

    Returns:
        A ``(category, severity)`` tuple.
    """
    if not event_type:
        return (DEFAULT_CATEGORY, DEFAULT_SEVERITY)
    if "mention" in event_type:
        return ("social", "info")
    for prefix, category, severity in _EVENT_RULES:
        if event_type == prefix or event_type.startswith(prefix):
            return (category, severity)
    return (DEFAULT_CATEGORY, DEFAULT_SEVERITY)


def attention_for_event(event_type: str | None) -> str:
    """Return the attention tier a fanned-out notification falls into.

    Used both as the legacy fallback when ``user_notifications.attention``
    is ``NULL`` (rows written before the column existed) and as the JS
    mirror's reference behaviour. An @mention is always ``for_you``;
    everything else delivered through the fan-out defaults to
    ``ambient`` since, absent the stored stamp, we can't tell a directed
    delivery from a follower delivery.

    Args:
        event_type: ``pointlessql.<scope>.<verb>`` identifier, or
            ``None``.

    Returns:
        ``'for_you'`` for mentions, otherwise ``'ambient'``.
    """
    if event_type and "mention" in event_type:
        return ATTENTION_FOR_YOU
    return ATTENTION_AMBIENT


def classify_signal(signal_kind: str | None) -> tuple[str, str]:
    """Return ``(category, severity)`` for an actionable-signal kind.

    Args:
        signal_kind: One of the ledger ``signal_kind`` values
            (``alert_firing``, ``slo_breach``, …).

    Returns:
        A ``(category, severity)`` tuple; unknown kinds default to
        ``(health, warn)`` since a signal is, by definition, a thing
        that needs attention.
    """
    return _SIGNAL_RULES.get(signal_kind or "", ("health", "warn"))


def count_by_category(rows: Iterable[Mapping[str, Any]]) -> dict[str, int]:
    """Tally how many rows fall into each category.

    Powers the count badges on the feed's category chips. Rows are
    expected to already carry a ``category`` field (stamped by the
    serializers); rows without one are bucketed via their
    ``event_type``.

    Args:
        rows: Iterable of serialized feed-row dicts.

    Returns:
        ``{category: count}`` for every category present (zero
        categories are omitted).
    """
    counts: dict[str, int] = {}
    for row in rows:
        category = row.get("category")
        if not category:
            category = classify_category(row.get("event_type"))[0]
        counts[category] = counts.get(category, 0) + 1
    return counts
