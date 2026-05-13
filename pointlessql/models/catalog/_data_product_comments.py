"""Threaded comments on data products (Phase 71.1).

One table:

* ``data_product_comments`` — one row per posted comment, soft-
  deleted via ``deleted_at``.  Threading via ``parent_comment_id``
  capped at depth 2 (app-level check at POST time; the column
  itself accepts arbitrary nesting).

Soft-delete preserves audit-trail integrity: a removed comment
keeps its row + parent links so the Discussion tab can render a
``[deleted]`` placeholder and any downstream notification log
remains coherent.

@mention resolution: the POST handler scans ``body_md`` for
``@<email>`` tokens, looks them up in ``users``, and stores the
resolved id list in ``mentioned_user_ids_json`` so the Phase 71.4
notification fan-out picks them up without re-parsing markdown.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class DataProductComment(Base):
    """One comment posted by a user on a data product.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace the comment belongs to.  FK on
            ``workspaces.id`` so the comment lives in the same
            tenant as the product.
        data_product_id: FK on ``data_products.id`` with
            ``ondelete='CASCADE'`` so a yaml deletion cleans up
            stray comments.
        parent_comment_id: Optional self-FK for replies.  NULL on
            top-level comments.  App-level guard caps the chain
            depth (Phase 76.1 lifted 2 → 5 with auto-collapse on
            render at depth ≥ 3).
        author_user_id: FK on ``users.id``.  Who posted.  Always
            a human — caller when direct, agent's principal when
            ``author_agent_id`` is set (Phase 76.5).
        author_agent_id: Optional FK on ``agents.id`` (Phase 76.5)
            — when set, the row renders as authored *by the agent
            on behalf of* ``author_user_id``.  Nullable; falls
            back to the existing user-only path when ``None``.
        body_md: Markdown body, rendered via the shared
            ``render_markdown`` Jinja filter (``html: False``).
        mentioned_user_ids_json: JSON-encoded list of resolved
            mention ids (``[12, 47]``).  Empty list when no
            mentions matched.
        category: GitHub-Discussions-style category — one of
            ``general`` / ``question`` / ``announcement`` /
            ``idea``.  Top-level only (replies inherit from
            their parent at serialise time).  Phase 76.1.
        is_accepted_answer: True when a steward or the OP marked
            this reply as the answer to a ``question`` thread.
            Atomicity is enforced in the accept-answer route —
            at most one reply per thread carries the flag.
            Phase 76.1.
        created_at: Wall-clock at POST time.
        deleted_at: Wall-clock when soft-deleted; NULL while live.
            Filters in list queries.
    """

    __tablename__ = "data_product_comments"

    __table_args__ = (
        Index(
            "ix_dp_comments_dp_created",
            "data_product_id",
            "created_at",
        ),
        Index("ix_dp_comments_parent", "parent_comment_id"),
        Index(
            "ix_data_product_comments_social_target",
            "social_target_id",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Phase 77.0.B — polymorphic anchor.  Nullable in this
    # revision so the legacy DP write path keeps working while
    # the dual-write phase rolls out; flipped to NOT NULL +
    # ``data_product_id`` dropped in Phase 77.0.G.
    social_target_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("social_targets.id"),
        nullable=True,
    )
    parent_comment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_product_comments.id", ondelete="CASCADE"),
        nullable=True,
    )
    author_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    # Phase 76.5 — presentation-layer override.  When set, the
    # comment is rendered as authored *by the agent on behalf of*
    # ``author_user_id`` (the principal).  The audit chain stays
    # intact because the human accountable stays in the
    # non-nullable column.
    author_agent_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("agents.id", ondelete="SET NULL"),
        nullable=True,
    )
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    mentioned_user_ids_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    category: Mapped[str] = mapped_column(
        String(20), nullable=False, default="general", server_default="general"
    )
    is_accepted_answer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="0"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
