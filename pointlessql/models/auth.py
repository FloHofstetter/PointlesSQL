"""User accounts (local + OIDC)."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class User(Base):
    """A user account — either local (email/password) or OIDC-provisioned.

    Local users have a ``password_hash``; OIDC users have ``oidc_provider``
    and ``oidc_subject`` instead (password_hash is ``None``).  A user can
    have both if a local account is later linked to an OIDC identity.

    Attributes:
        id: Auto-incremented primary key.
        email: Unique email address (max 254 chars).
        display_name: Human-readable name shown in the navbar.
        password_hash: Bcrypt-hashed password string, or ``None`` for
            OIDC-only users.
        is_admin: Whether the user has administrator privileges.
        created_at: Timestamp when the user was created.
        oidc_provider: OIDC discovery URL that authenticated this user.
        oidc_subject: The ``sub`` claim from the OIDC provider.
        feed_token: Opaque token authenticating pull-feed requests
            (Sprint 55); ``None`` until the user first hits the
            feed-token endpoint.
    """

    __tablename__ = "users"

    # Indexes mirror the migration-created shapes so autogen
    # round-trips cleanly. ``ix_users_oidc_identity`` is a **partial**
    # unique index (only constrains rows with an OIDC identity) — the
    # ``*_where`` dialect kwargs emit ``WHERE oidc_provider IS NOT
    # NULL`` on both SQLite and Postgres.
    __table_args__ = (
        Index("ix_users_email", "email", unique=True),
        Index(
            "ix_users_oidc_identity",
            "oidc_provider",
            "oidc_subject",
            unique=True,
            sqlite_where=text("oidc_provider IS NOT NULL"),
            postgresql_where=text("oidc_provider IS NOT NULL"),
        ),
        Index(
            "ix_users_feed_token",
            "feed_token",
            unique=True,
            sqlite_where=text("feed_token IS NOT NULL"),
            postgresql_where=text("feed_token IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    oidc_provider: Mapped[str | None] = mapped_column(String(500), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Sprint 55: opaque token used to authenticate pull-feed requests
    # (Atom + JSON Feed).  Materialised lazily on first feed GET via
    # ``secrets.token_urlsafe``; stays ``NULL`` for users who never
    # access the feed.
    feed_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
