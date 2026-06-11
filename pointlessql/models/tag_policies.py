"""Tag-driven governance policy rules (attribute-based access control)."""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class TagPolicyRule(Base):
    """One tag-matching rule that injects a mask or row filter at read time.

    Rules are deployment-global by design: they govern Unity-Catalog
    tags, and the catalog itself is shared across PointlesSQL
    workspaces — a PII guardrail that only held in one workspace would
    be a bypass, not a policy.  Admins manage the rule set; admins and
    table owners stay exempt at enforcement time, exactly like the
    per-table ``pointlessql.row_filter`` / ``pointlessql.mask.*``
    properties the rules compose with.

    Attributes:
        id: Auto-incremented primary key.
        tag_key: The tag key to match (e.g. ``"pii"``).
        tag_value: Optional tag value to match; ``None`` matches any
            value of ``tag_key``.
        effect: ``"mask"`` (matches *column* tags; ``expr`` is a mask
            spec) or ``"row_filter"`` (matches *table* tags; ``expr``
            is a SQL predicate).
        expr: For masks: a builtin name (``redact`` / ``hash`` /
            ``null``) or a ``{col}`` template — the same vocabulary as
            the ``pointlessql.mask.<column>`` table property.  For row
            filters: a SQL predicate; ``current_user()`` is substituted
            with the querying principal at enforcement time.
        priority: Tie-breaker when several mask rules match the same
            column — the lowest number wins.  Explicit per-table
            properties always beat tag rules regardless of priority.
        is_active: Inactive rules are kept for audit but never applied.
        description: Free-text rationale shown in the admin UI.
        created_by_user_id: FK to the admin who created the rule.
        created_at: Creation timestamp.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "tag_policy_rules"

    __table_args__ = (Index("ix_tag_policy_rules_active", "is_active"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tag_key: Mapped[str] = mapped_column(String(200), nullable=False)
    tag_value: Mapped[str | None] = mapped_column(String(200), nullable=True)
    effect: Mapped[str] = mapped_column(String(20), nullable=False)
    expr: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(
        Integer, nullable=False, default=100, server_default="100"
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
