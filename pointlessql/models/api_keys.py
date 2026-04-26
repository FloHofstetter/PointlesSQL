"""API-key store — DB-backed Bearer-token gate.

Replaces the earlier env-var ``POINTLESSQL_API_KEYS`` parser with
a real table so admins can rotate keys without a process restart,
and so the ``supervisor`` scope (gating the supervisor routes)
lives next to the secret it authorises.
"""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class ApiKey(Base):
    """One Bearer-token credential addressable by ``Authorization: Bearer``.

    Secrets are stored hashed; the plaintext is shown to the admin
    once at creation time and never persisted.  ``secret_prefix`` is
    the first 8 characters of the plaintext so the admin UI can
    label the key without revealing the secret.

    Attributes:
        id: Auto-incremented primary key.
        name: Unique human-readable label (used as audit attribution
            via ``api_key:<name>``).
        secret_hash: SHA-256-hex of the plaintext secret.  API keys
            are high-entropy random, so a fast hash is enough — bcrypt
            would only buy resistance against brute-force on weak
            secrets, and we control the secrets here.
        secret_prefix: First 8 plaintext characters for UI display.
        supervisor: When ``True``, the key may invoke the supervisor
            routes.
        created_at: Timestamp the key was created.
        created_by_user_id: Admin who created the key, or ``None``
            for env-var-bootstrapped keys + CLI-provisioned keys.
        revoked_at: Timestamp the key was revoked, or ``None`` when
            still active.  Revoked keys stay in the table so the
            audit trail keeps resolving ``api_key:<name>`` after a
            rotation.
        last_used_at: Best-effort wall-clock of the most recent
            successful auth.  Updated by the middleware on each
            cache-miss verification — not transactionally critical
            (a swallowed UPDATE is fine).
    """

    __tablename__ = "api_keys"

    __table_args__ = (Index("ix_api_keys_secret_hash", "secret_hash"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    secret_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    secret_prefix: Mapped[str] = mapped_column(String(8), nullable=False)
    supervisor: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_by_user_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=True
    )
    revoked_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_used_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
