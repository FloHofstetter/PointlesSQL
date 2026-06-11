"""Tag-driven read policies: CRUD plus the enforcement-time merge.

The merge hook (:func:`apply_tag_policies`) runs inside the two SELECT
enforcement choke points — the SQL dispatcher and the notebook/BI
``resolve_select_context`` — right after the per-table property policy
is extracted.  Matching is tag-based: a ``mask`` rule fires on *column*
tags and injects a column mask, a ``row_filter`` rule fires on *table*
tags and ANDs its predicate into the effective row filter.  Explicit
per-table ``pointlessql.mask.<col>`` properties always win over tag
rules for the same column; admins and table owners never reach this
code (the choke points exempt them before policy collection).

Failure stance: a malformed rule predicate raises (fail-closed — a
broken guardrail must not silently disappear), while transport
problems fetching tags also raise so a flaky catalog cannot be used
to race past a policy.  Both tag lookups and the active-rule list are
TTL-cached to keep the per-query overhead at zero when no rules exist
and near-zero otherwise.
"""

from __future__ import annotations

import datetime
import logging
import time
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from pointlessql.exceptions import ValidationError
from pointlessql.models.tag_policies import TagPolicyRule
from pointlessql.pql._policies import (
    TablePolicy,
    render_mask,
    substitute_current_user,
    validate_row_filter,
)

logger = logging.getLogger(__name__)

EFFECTS: tuple[str, ...] = ("mask", "row_filter")

# Active-rule snapshots, refreshed at most every _RULES_TTL seconds.
_RULES_TTL = 15.0
_rules_cache: tuple[float, tuple[RuleSnapshot, ...]] | None = None

# UC tag lookups, keyed by (securable_type, full_name).
_TAG_TTL = 60.0
_tag_cache: dict[tuple[str, str], tuple[float, list[dict[str, Any]]]] = {}


@dataclass(frozen=True)
class RuleSnapshot:
    """Immutable view of one active rule used on the query path."""

    tag_key: str
    tag_value: str | None
    effect: str
    expr: str
    priority: int


def invalidate_caches() -> None:
    """Drop the rule + tag caches (rule mutations and tests call this)."""
    global _rules_cache
    _rules_cache = None
    _tag_cache.clear()


# ---------------------------------------------------------------------------
# CRUD
# ---------------------------------------------------------------------------


def list_rules(factory: sessionmaker[Session]) -> list[TagPolicyRule]:
    """Return every rule, active first, then by priority.

    Args:
        factory: Session factory.

    Returns:
        Detached rule rows.
    """
    with factory() as session:
        rows = list(
            session.scalars(
                select(TagPolicyRule).order_by(
                    TagPolicyRule.is_active.desc(),
                    TagPolicyRule.priority,
                    TagPolicyRule.id,
                )
            ).all()
        )
        for row in rows:
            session.expunge(row)
        return rows


def create_rule(
    factory: sessionmaker[Session],
    *,
    tag_key: str,
    tag_value: str | None,
    effect: str,
    expr: str,
    priority: int = 100,
    description: str | None = None,
    created_by_user_id: int,
) -> TagPolicyRule:
    """Create one rule after validating its shape.

    Args:
        factory: Session factory.
        tag_key: Tag key to match.
        tag_value: Optional tag value (``None`` = any).
        effect: ``"mask"`` or ``"row_filter"``.
        expr: Mask spec or SQL predicate (validated here so a typo
            fails at authoring time, not at query time).
        priority: Mask tie-breaker (lowest wins).
        description: Free-text rationale.
        created_by_user_id: Authoring admin.

    Returns:
        The detached new row.

    Raises:
        ValidationError: On an unknown effect, empty key/expr, or a
            row-filter predicate that does not parse.
    """
    key = (tag_key or "").strip()
    body = (expr or "").strip()
    if not key:
        raise ValidationError("tag_key is required")
    if effect not in EFFECTS:
        raise ValidationError(f"effect must be one of {list(EFFECTS)}")
    if not body:
        raise ValidationError("expr is required")
    if effect == "row_filter":
        try:
            validate_row_filter(body)
        except ValueError as exc:
            raise ValidationError(f"invalid row-filter predicate: {exc}") from exc
    now = datetime.datetime.now(datetime.UTC)
    with factory() as session:
        row = TagPolicyRule(
            tag_key=key,
            tag_value=(tag_value or "").strip() or None,
            effect=effect,
            expr=body,
            priority=priority,
            is_active=True,
            description=(description or "").strip() or None,
            created_by_user_id=created_by_user_id,
            created_at=now,
            updated_at=now,
        )
        session.add(row)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    invalidate_caches()
    return row


def update_rule(
    factory: sessionmaker[Session],
    rule_id: int,
    *,
    is_active: bool | None = None,
    priority: int | None = None,
    description: str | None = None,
) -> TagPolicyRule:
    """Mutate the toggle-able fields of one rule.

    Matching semantics (key/value/effect/expr) are immutable on
    purpose — replacing a guardrail is an explicit delete + create,
    which keeps the audit trail honest.

    Args:
        factory: Session factory.
        rule_id: Target rule.
        is_active: New active flag, when provided.
        priority: New priority, when provided.
        description: New description, when provided.

    Returns:
        The detached updated row.

    Raises:
        ValidationError: When the rule does not exist.
    """
    with factory() as session:
        row = session.get(TagPolicyRule, rule_id)
        if row is None:
            raise ValidationError(f"tag policy rule {rule_id} not found")
        if is_active is not None:
            row.is_active = is_active
        if priority is not None:
            row.priority = priority
        if description is not None:
            row.description = description.strip() or None
        row.updated_at = datetime.datetime.now(datetime.UTC)
        session.commit()
        session.refresh(row)
        session.expunge(row)
    invalidate_caches()
    return row


def delete_rule(factory: sessionmaker[Session], rule_id: int) -> bool:
    """Delete one rule; returns whether a row was removed.

    Args:
        factory: Session factory.
        rule_id: Target rule.

    Returns:
        ``True`` when the rule existed.
    """
    with factory() as session:
        row = session.get(TagPolicyRule, rule_id)
        if row is None:
            return False
        session.delete(row)
        session.commit()
    invalidate_caches()
    return True


# ---------------------------------------------------------------------------
# Enforcement-time merge
# ---------------------------------------------------------------------------


def _active_rules(factory: sessionmaker[Session]) -> tuple[RuleSnapshot, ...]:
    """Return the cached active-rule snapshots."""
    global _rules_cache
    now = time.monotonic()
    if _rules_cache is not None and _rules_cache[0] > now:
        return _rules_cache[1]
    with factory() as session:
        rows = list(session.scalars(select(TagPolicyRule).where(TagPolicyRule.is_active)).all())
    snapshots = tuple(
        sorted(
            (
                RuleSnapshot(
                    tag_key=r.tag_key,
                    tag_value=r.tag_value,
                    effect=r.effect,
                    expr=r.expr,
                    priority=r.priority,
                )
                for r in rows
            ),
            key=lambda s: s.priority,
        )
    )
    _rules_cache = (now + _RULES_TTL, snapshots)
    return snapshots


async def _cached_tags(uc_client: Any, securable_type: str, full_name: str) -> list[dict[str, Any]]:
    """Fetch tags through the TTL cache."""
    key = (securable_type, full_name)
    now = time.monotonic()
    hit = _tag_cache.get(key)
    if hit is not None and hit[0] > now:
        return hit[1]
    tags = await uc_client.get_tags(securable_type, full_name)
    normalised = [t for t in (tags or []) if isinstance(t, dict)]
    _tag_cache[key] = (now + _TAG_TTL, normalised)
    return normalised


def _matches(rule: RuleSnapshot, tags: list[dict[str, Any]]) -> bool:
    """Return whether any tag satisfies the rule's key (+ value)."""
    for tag in tags:
        if str(tag.get("key", "")) != rule.tag_key:
            continue
        if rule.tag_value is None or str(tag.get("value", "")) == rule.tag_value:
            return True
    return False


async def apply_tag_policies(
    uc_client: Any,
    *,
    full_name: str,
    info: dict[str, Any],
    base: TablePolicy | None,
    principal: str,
    factory: sessionmaker[Session] | None = None,
) -> TablePolicy | None:
    """Merge matching tag rules into *base* for one table read.

    Args:
        uc_client: Principal-bound catalog facade (tag lookups).
        full_name: Three-part table name.
        info: The already-fetched table info (for the column list —
            no extra catalog round-trip).
        base: The per-table property policy, or ``None``.
        principal: The querying user's email (``current_user()``
            substitution in rule predicates).
        factory: Session factory override (tests); defaults to the
            application factory.

    Returns:
        The effective :class:`TablePolicy`, or ``None`` when neither
        properties nor rules constrain this read.

    Raises:
        ValidationError: When a matching row-filter rule's predicate
            fails validation (fail-closed: the query is rejected
            rather than run unguarded).
    """
    if factory is None:
        try:
            from pointlessql.db import get_session_factory

            factory = get_session_factory()
        except RuntimeError:
            # no metadata DB in this context (engine-level unit tests,
            # bare library use) — rules live in that DB, so none can
            # exist; the per-table property policy stands alone.
            return base
    rules = _active_rules(factory)
    if not rules:
        return base

    mask_rules = [r for r in rules if r.effect == "mask"]
    filter_rules = [r for r in rules if r.effect == "row_filter"]

    extra_filters: list[str] = []
    if filter_rules:
        table_tags = await _cached_tags(uc_client, "table", full_name)
        for rule in filter_rules:
            if not _matches(rule, table_tags):
                continue
            try:
                validated = validate_row_filter(rule.expr)
            except ValueError as exc:
                raise ValidationError(
                    f"tag policy rule on {full_name!r} carries a malformed row filter: {exc}"
                ) from exc
            extra_filters.append(substitute_current_user(validated, principal))

    rule_masks: dict[str, str] = {}
    if mask_rules:
        columns = [
            str(c.get("name", ""))
            for c in (info.get("columns") or [])
            if isinstance(c, dict) and c.get("name")
        ]
        for column in columns:
            column_tags = await _cached_tags(uc_client, "column", f"{full_name}.{column}")
            if not column_tags:
                continue
            for rule in mask_rules:  # already priority-sorted
                if _matches(rule, column_tags):
                    # stored masks are the RENDERED SQL expression —
                    # same convention as extract_table_policy.
                    rule_masks[column] = render_mask(rule.expr, column)
                    break

    if not extra_filters and not rule_masks:
        return base

    base_filter = base.row_filter if base else None
    parts = [f"({p})" for p in ([base_filter] if base_filter else []) + extra_filters]
    combined_filter = " AND ".join(parts) if parts else None
    # explicit table properties win per column.
    combined_masks = {**rule_masks, **(base.column_masks if base else {})}
    merged = TablePolicy(row_filter=combined_filter, column_masks=combined_masks)
    return None if merged.is_empty() else merged
