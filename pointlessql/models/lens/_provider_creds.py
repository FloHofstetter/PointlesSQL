"""Lens BYO LLM provider credentials — Fernet-encrypted at rest.

Each workspace can register one credential per provider (OpenAI,
Anthropic).  The plaintext API key is never persisted; it is
encrypted via :func:`pointlessql.services.secrets.encrypt_value`
(install-scoped Fernet master key, analogous to the workspace-repo
secrets shape) and the ciphertext is stored here.  Decryption
happens only at chat-loop invocation time
and the cleartext stays in process memory for the duration of a
single LLM round-trip.

The compound primary key ``(workspace_id, provider)`` enforces
"one credential per provider per workspace" without a synthetic id.
Switching the active provider for a session is a runtime concern (the
session row carries ``llm_provider``); this table just stores the
secrets.
"""

from __future__ import annotations

import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base

LENS_PROVIDERS: tuple[str, ...] = ("openai", "anthropic")
"""Recognised :attr:`LensProviderCreds.provider` and
:attr:`LensSession.llm_provider` values.

Mirrored to a CHECK constraint in the lens_tables migration.  Adding
a provider: bump both this tuple AND the CHECK constraint via Alembic
in lockstep with the chat-loop adapter (see
:mod:`pointlessql.services.lens.llm_provider`).
"""


class LensProviderCreds(Base):
    """One BYO LLM credential row per ``(workspace_id, provider)``.

    Attributes:
        workspace_id: Workspace this credential belongs to.  Part of
            the compound primary key.
        provider: One of :data:`LENS_PROVIDERS`.  Part of the
            compound primary key.
        api_key_encrypted: Fernet-encrypted ciphertext of the
            cleartext API key.  Always set; rotation overwrites in
            place.
        default_model: Optional default model identifier the chat-loop
            uses when the analyst does not specify one explicitly.
            ``NULL`` defers to the install-wide
            :class:`LensSettings.openai_model_default` /
            :class:`LensSettings.anthropic_model_default`.
        enabled: When ``False`` the chat-loop refuses to use this
            credential — useful for keeping a key on file but
            temporarily disabling its use without revealing the
            cleartext to revoke + re-add.
        created_at: Wall-clock at first persistence.
        updated_at: Wall-clock at last cleartext rotation or
            ``enabled`` flip.
    """

    __tablename__ = "lens_provider_creds"

    workspace_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("workspaces.id"),
        primary_key=True,
    )
    provider: Mapped[str] = mapped_column(String(32), primary_key=True)
    api_key_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    default_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
