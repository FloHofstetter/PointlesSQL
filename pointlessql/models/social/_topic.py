"""Topic + DP↔topic + user↔topic-follow rows.

Three models in one module — they share the same conceptual
slice (the topic taxonomy) and are always imported together.

* :class:`Topic` is workspace-scoped; ``(workspace_id, slug)`` is
  unique so a topic created in workspace A can re-use a slug in
  workspace B.
* :class:`DataProductTopic` joins DPs to topics, composite PK.
* :class:`UserTopicFollow` joins users to topics, composite PK.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    PrimaryKeyConstraint,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class Topic(Base):
    """Workspace-scoped topic.

    Attributes:
        id: Surrogate primary key.
        workspace_id: FK on ``workspaces.id``.
        slug: URL-safe identifier (lower-case, hyphenated).
            Unique per workspace.
        display_name: Human-friendly label.
        description_md: Optional markdown body shown on the
            topic-detail page.
        created_at: Wall-clock at create time.
        created_by_user_id: FK on ``users.id``.  Audit trail.
    """

    __tablename__ = "topics"

    __table_args__ = (UniqueConstraint("workspace_id", "slug", name="uq_topics_slug"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        nullable=False,
        server_default="1",
    )
    slug: Mapped[str] = mapped_column(String(60), nullable=False)
    display_name: Mapped[str] = mapped_column(String(80), nullable=False)
    description_md: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)


class DataProductTopic(Base):
    """One DP↔topic membership row.

    Attributes:
        data_product_id: FK on ``data_products.id`` (CASCADE).
        topic_id: FK on ``topics.id`` (CASCADE).
        added_by_user_id: FK on ``users.id`` — who assigned.
        added_at: Wall-clock at assignment.
    """

    __tablename__ = "data_product_topics"

    __table_args__ = (
        PrimaryKeyConstraint("data_product_id", "topic_id", name="pk_data_product_topics"),
        Index("ix_data_product_topics_topic", "topic_id"),
    )

    data_product_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("data_products.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    added_by_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    added_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class UserTopicFollow(Base):
    """One user↔topic follow link.

    Attributes:
        user_id: FK on ``users.id`` (CASCADE).
        topic_id: FK on ``topics.id`` (CASCADE).
        created_at: Wall-clock at follow time.
    """

    __tablename__ = "user_topic_follows"

    __table_args__ = (
        PrimaryKeyConstraint("user_id", "topic_id", name="pk_user_topic_follows"),
        Index("ix_user_topic_follows_topic", "topic_id"),
    )

    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    topic_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("topics.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
