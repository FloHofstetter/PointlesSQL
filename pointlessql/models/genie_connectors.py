"""Genie bot connectors — outbound chat bridges (Teams / M365 Copilot).

A connector lets an external chat tool (a Microsoft Teams ``@Genie`` bot
or an M365 Copilot Studio connector) reach a workspace's Genie engine.
Each row registers one bot: a stable public id that addresses its inbound
messaging endpoint, a shared-secret token (stored only as a SHA-256
hash), an optional bound Genie space (the curated table scope answers run
against), and an enabled flag.  The inbound webhook authenticates the
presented token against the hash, then routes the question through the
ordinary grant-enforced Genie answer path.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    true,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

#: Chat platforms a connector can target.
GENIE_CONNECTOR_PLATFORMS: tuple[str, ...] = ("teams", "copilot")


class GenieBotConnector(Base):
    """A registered outbound chat connector for the Genie engine.

    Attributes:
        id: Surrogate primary key.
        workspace_id: Owning workspace.
        name: Human-readable connector name, unique per workspace.
        platform: One of :data:`GENIE_CONNECTOR_PLATFORMS`.
        public_id: Stable opaque id addressing the inbound messaging
            endpoint (safe to expose in a URL; not a secret).
        genie_space_slug: Optional Genie space the bot answers over; the
            space's curated tables scope the bot's reach.
        token_hash: SHA-256 hex digest of the shared-secret token.
        token_prefix: First characters of the plaintext token, kept for
            display so an admin can recognise which token is active.
        enabled: Whether the connector accepts inbound messages.
        created_by: Authoring principal's email.
        created_at: Row creation timestamp.
        updated_at: Latest mutation timestamp.
    """

    __tablename__ = "genie_bot_connectors"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_genie_bot_connectors_ws_name"),
        UniqueConstraint("public_id", name="uq_genie_bot_connectors_public_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(16), nullable=False, server_default="teams")
    public_id: Mapped[str] = mapped_column(String(32), nullable=False)
    genie_space_slug: Mapped[str | None] = mapped_column(String(200), nullable=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_prefix: Mapped[str] = mapped_column(String(16), nullable=False, server_default="")
    enabled: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=true()
    )
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
