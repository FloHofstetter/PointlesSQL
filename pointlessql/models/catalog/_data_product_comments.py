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

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text
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
            top-level comments.  App-level guard caps the chain at
            depth 2 (no replies-to-replies).
        author_user_id: FK on ``users.id``.  Who posted.
        body_md: Markdown body, rendered via the shared
            ``render_markdown`` Jinja filter (``html: False``).
        mentioned_user_ids_json: JSON-encoded list of resolved
            mention ids (``[12, 47]``).  Empty list when no
            mentions matched.
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
    parent_comment_id: Mapped[int | None] = mapped_column(
        Integer,
        ForeignKey("data_product_comments.id", ondelete="CASCADE"),
        nullable=True,
    )
    author_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    body_md: Mapped[str] = mapped_column(Text, nullable=False)
    mentioned_user_ids_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="[]", server_default="[]"
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    deleted_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
