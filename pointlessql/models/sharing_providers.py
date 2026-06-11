"""Delta Sharing providers — remote shares this install consumes.

One table for the consumer half of Delta Sharing: each row stores a
provider profile (endpoint + bearer token) exactly like a
``config.share`` profile file, with the token Fernet-encrypted via
:func:`pointlessql.services.secrets.encrypt_value`.  The provider
half (shares we *offer*) lives in soyuz-catalog and is administered
through the UC facade — no local rows needed there.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class SharingProvider(Base):
    """One remote Delta Sharing endpoint this workspace can read.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: FK to ``workspaces.id``.
        name: Provider alias, unique per workspace; appears in
            ``pql.read_share("<provider>", …)`` calls.
        endpoint_url: Base URL of the remote ``/delta-sharing``
            prefix (kept verbatim from the profile file).
        encrypted_token: Fernet-encrypted bearer token.  Decrypted
            only inside the consumer client; never returned by the
            API.
        comment: Free-form note (who shared this, expiry, …).
        created_by: E-mail of the registering principal.
        created_at: Timestamp when the provider was registered.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "sharing_providers"

    __table_args__ = (
        UniqueConstraint("workspace_id", "name", name="uq_sharing_providers_ws_name"),
        Index("ix_sharing_providers_workspace", "workspace_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    encrypted_token: Mapped[str] = mapped_column(Text, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(254), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
