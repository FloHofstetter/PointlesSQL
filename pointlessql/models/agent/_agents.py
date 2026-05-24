"""First-class agent identity row.

The ``agents`` table is the canonical registry of LLM reviewers
and bots that can post comments / endorsements / reviews under
their own brand while remaining accountable to a human
``principal_user_id``.  Agents are workspace-scoped; the
``slug`` is the URL-safe handle used in ``/agents/{slug}`` and
in the ``?as_agent=`` query param on the comment POST route.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

AVATAR_KINDS: tuple[str, ...] = (
    "llm-default",
    "hermes",
    "openclaw",
    "custom",
)


class Agent(Base):
    """One agent identity.

    Attributes:
        id: Surrogate primary key.
        workspace_id: Tenant scope.  Unique per ``(workspace,
            slug)``.
        slug: URL-safe handle.  Lowercase + hyphens; stable.
        display_name: Human-friendly label.
        avatar_kind: One of :data:`AVATAR_KINDS`.  Drives the
            avatar icon on profile + comment rows.
        avatar_url: Optional override for the icon.
        home_url: Optional homepage / docs link.
        principal_user_id: FK on ``users.id``.  The human
            accountable for this agent's actions; only this user
            (or install-admin) may post / endorse *as* the agent.
        is_verified: Admin-flipped trust signal.  Drives a green
            tick on the profile + comment rows.
        verified_by_user_id: Audit pointer to the admin who
            flipped the flag.
        verified_at: When verification was granted.
        bio_md: Markdown description rendered on the profile.
        created_at: Wall-clock at create time.
        created_by_user_id: FK on ``users.id`` of the creator —
            usually the same as ``principal_user_id`` but doesn't
            have to be (admin can register an agent for another
            principal).
    """

    __tablename__ = "agents"

    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_agents_slug"),
        CheckConstraint(
            "avatar_kind IN ('llm-default', 'hermes', 'openclaw', 'custom')",
            name="ck_agents_avatar_kind",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    avatar_kind: Mapped[str] = mapped_column(
        String(20), nullable=False, default="custom", server_default="custom"
    )
    avatar_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    home_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    principal_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    is_verified: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    verified_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    verified_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    bio_md: Mapped[str] = mapped_column(
        Text, nullable=False, default="", server_default=""
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    created_by_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
