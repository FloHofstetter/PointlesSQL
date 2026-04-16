"""SQLAlchemy ORM models for PointlesSQL's own metadata database."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all PointlesSQL models."""


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
    """

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    oidc_provider: Mapped[str | None] = mapped_column(String(500), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AuditLog(Base):
    """Append-only log of user actions for accountability.

    Attributes:
        id: Auto-incremented primary key.
        user_id: ID of the user who performed the action (no FK so
            entries survive user deletion).
        user_email: Email snapshot at time of action.
        action: Short verb describing the action (e.g. ``update_catalog``).
        target: Identifier of the affected resource (e.g. ``catalog:my_cat``).
        detail: Optional JSON context (e.g. patch body).
        created_at: Timestamp when the action occurred.
    """

    __tablename__ = "audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_email: Mapped[str] = mapped_column(String(254), nullable=False)
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    detail: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class SyncRun(Base):
    """One execution record of a foreign-catalog sync.

    Written by :mod:`pointlessql.services.pg_sync` when a Postgres
    sync worker runs against a foreign catalog — either through the
    manual "Sync now" button (Sprint 18) or later on a schedule
    (Sprint 19).  Entries are append-only and double as the source
    for the history card on the catalog detail page.

    ``status`` cycles through ``running`` → ``succeeded`` | ``failed``.
    ``finished_at`` stays ``NULL`` while the run is in flight, which
    the UI renders as a spinner.  ``error`` carries the exception
    message when ``status == "failed"``.

    Attributes:
        id: Auto-incremented primary key.
        catalog_name: Target foreign catalog that was synced.
        started_at: Timestamp when the sync began.
        finished_at: Timestamp when the sync ended, or ``None`` while
            still running.
        status: ``running``, ``succeeded``, or ``failed``.
        added_count: Number of schemas + tables created during the run.
        changed_count: Number of tables whose columns were modified.
        dropped_count: Number of tables removed because the source
            Postgres no longer has them.
        error: Error message if ``status == "failed"``, else ``None``.
    """

    __tablename__ = "sync_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_name: Mapped[str] = mapped_column(String(500), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    added_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    changed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    dropped_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
