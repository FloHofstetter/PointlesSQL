"""User accounts (local + OIDC)."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
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
        is_supervisor: Whether the user has supervisor scope
            (governs Family-B routes: run summary, run diff,
            runs-by-principal).  Granted by an OIDC group mapping;
            re-resolved on every login.  Mirrors :class:`ApiKey`
            ``supervisor`` for the session-cookie auth path.
        is_auditor: Whether the user has auditor scope (governs
            tenant-wide ``/api/audit/*`` aggregates).  Same grant
            + refresh shape as :attr:`is_supervisor`.
        created_at: Timestamp when the user was created.
        oidc_provider: OIDC discovery URL that authenticated this user.
        oidc_subject: The ``sub`` claim from the OIDC provider.
        oidc_groups_json: JSON-encoded snapshot of the groups claim
            from the most recent OIDC login.  Audit-visibility only;
            authz never reads it at runtime.
        feed_token: Opaque token authenticating pull-feed requests;
            ``None`` until the user first hits the feed-token endpoint.
        default_workspace_id: Workspace the user lands in when neither
            an ``X-Workspace`` header nor a ``current_workspace_slug``
            cookie field overrides it.  Backfilled to the seeded
            ``default`` workspace (id=1) by the bootstrap migration;
            flipped to NOT NULL once the admin UI exposed a chooser.
        digest_email_optin: Phase 71.4 opt-in for the daily
            marketplace-digest email.  The
            ``_user_notification_digest_loop`` picks the user up
            when this is ``True`` and unread notifications exist;
            the audit-stream forwarder's webhook / SES-bound sink
            performs the actual delivery.
        notification_prefs_json: Phase 76.4 per-event-type
            opt-out matrix.  JSON map of
            ``{event_type: {inbox: bool, email: bool,
            webhook: bool}}``.  Missing keys default to ``true``
            on every channel; default is the empty object
            ``"{}"`` (= everything opted-in).
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
    is_supervisor: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    is_auditor: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    oidc_provider: Mapped[str | None] = mapped_column(String(500), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # Snapshot of the groups claim from the most recent OIDC login.
    # Audit-visibility only — authz reads ``is_supervisor`` /
    # ``is_auditor`` flags, never this column.  ``None`` for users who
    # never logged in via OIDC, or whose IdP doesn't surface a groups
    # claim (we re-resolve on every login, so a missing claim leaves
    # the column unchanged).
    oidc_groups_json: Mapped[str | None] = mapped_column(Text(), nullable=True)
    # Opaque token used to authenticate pull-feed requests
    # (Atom + JSON Feed).  Materialised lazily on first feed GET via
    # ``secrets.token_urlsafe``; stays ``NULL`` for users who never
    # access the feed.
    feed_token: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # Every user has a default workspace.  Originally nullable +
    # bootstrap-backfilled, then flipped to NOT NULL via migration
    # ``dd4f6h8j0l2n`` once the admin-UI rollout was in place.
    # Server-side default of 1 keeps single-tenant installs and
    # direct-ORM test fixtures working — every new user row lands
    # in the seeded ``default`` workspace unless a caller
    # explicitly names another.
    default_workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    # opt-in for the daily marketplace digest email.
    # When ``True`` the ``_user_notification_digest_loop`` picks
    # this user up at the daily wake-window if they have unread
    # notifications.  The actual mail delivery is handled by the
    # audit-stream forwarder's webhook / SES sink — this column is
    # just the opt-in gate.
    digest_email_optin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    # per-event-type opt-in toggles, JSON-encoded.
    # Shape: ``{event_type: {inbox, email, webhook}}``; missing
    # keys default to all-true so newly-shipped event types reach
    # users until they explicitly opt out.
    notification_prefs_json: Mapped[str] = mapped_column(
        Text, nullable=False, default="{}", server_default="{}"
    )
