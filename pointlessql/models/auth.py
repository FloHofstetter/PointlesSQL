"""User accounts (local + OIDC)."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, text
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
        feed_token: Opaque token authenticating pull-feed requests;
            ``None`` until the user first hits the feed-token endpoint.
        default_workspace_id: Workspace the user lands in when neither
            an ``X-Workspace`` header nor a ``current_workspace_slug``
            cookie field overrides it (Phase 28.0).  Backfilled to the
            seeded ``default`` workspace (id=1) by the bootstrap
            migration; stays nullable in 28.0 so the FK column can
            co-exist with legacy code paths, then flipped to NOT NULL
            in Sprint 28.6 once the admin UI exposes a chooser.
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
    # Opaque token used to authenticate pull-feed requests
    # (Atom + JSON Feed).  Materialised lazily on first feed GET via
    # ``secrets.token_urlsafe``; stays ``NULL`` for users who never
    # access the feed.
    feed_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Phase 28.0: every user pre-seeded into the ``default`` workspace
    # at migration time.  Stays nullable in 28.0 so the FK column can
    # be added before workspace_members backfill completes; flipped to
    # NOT NULL in Sprint 28.6 once the admin UI exists.  The middleware
    # falls back to id=1 when this is NULL so the request path is safe
    # even mid-rollout.
    default_workspace_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=True
    )
