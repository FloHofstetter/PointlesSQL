"""SQLAlchemy ORM models for PointlesSQL's own metadata database."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text
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


class Job(Base):
    """A scheduled unit of work executed by the in-process scheduler.

    Sprint 19 introduces single-task jobs — ``kind`` picks the Python
    callable that executes the work and ``config`` is the free-form JSON
    payload passed through to it. Sprint 20 will fan this out to
    multi-task DAGs via the adjacent :class:`JobTask` table, so the
    current fields are the subset that survive the multi-task migration.

    ``config`` is stored as a JSON-encoded string in the ``Text`` column
    (SQLite's ``JSON`` affinity is identical to ``TEXT``, and using
    ``Text`` keeps the migration identical across SQLite and Postgres).
    Callers serialize with :func:`json.dumps` on write and
    :func:`json.loads` on read — kept explicit so the column stays a
    plain string regardless of SQLAlchemy dialect.

    Attributes:
        id: Auto-incremented primary key.
        name: Unique human-readable name shown in the UI.
        cron_expr: 5-field cron expression evaluated by ``croniter``.
        run_as_user_id: FK to ``users.id`` — the scheduler builds an
            ``X-Principal`` client for this user before invoking the
            task callable so soyuz authorization applies.
        kind: Registry key for the task executor (e.g. ``"pg_sync"``,
            ``"python"``).
        config: JSON-encoded parameters passed to the executor.
        is_paused: When ``True`` the scheduler skips this job.
        created_at: Timestamp when the job was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(120), nullable=False)
    run_as_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_paused: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )
    created_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )


class JobRun(Base):
    """One execution of a :class:`Job`.

    Rows start as ``running`` when the scheduler (or the manual-trigger
    route) claims the job, flip to ``succeeded`` or ``failed`` when the
    executor returns, or to ``skipped`` when the scheduler finds a
    previous run still in flight and refuses to double-launch.

    ``trigger`` distinguishes ``scheduled`` (cron tick) from ``manual``
    ("Run now" button) so the UI can badge them differently.

    Attributes:
        id: Auto-incremented primary key.
        job_id: FK to ``jobs.id``.
        started_at: Timestamp when the executor was invoked.
        finished_at: Timestamp when the executor returned, or ``None``
            while still running.
        status: ``running``, ``succeeded``, ``failed`` or ``skipped``.
        trigger: ``scheduled`` or ``manual``.
        error: Exception message when ``status == "failed"`` or
            ``"skipped"``; ``None`` otherwise.
    """

    __tablename__ = "job_runs"
    __table_args__ = (
        Index("ix_job_runs_job_started", "job_id", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jobs.id"), nullable=False
    )
    started_at: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobTask(Base):
    """One ordered task within a :class:`Job` — pre-created for Sprint 20.

    Sprint 19 jobs are single-task; the executor reads directly from
    the parent ``jobs.config``. Rows in this table are not consulted by
    the Sprint 19 scheduler. The table exists now so Sprint 20 can add
    ``depends_on`` / ``retries`` columns with a simple additive
    migration instead of re-shaping the schema.

    Attributes:
        id: Auto-incremented primary key.
        job_id: FK to ``jobs.id``.
        name: Human-readable task name, unique within the parent job.
        order: Ordinal within the job (Sprint 20 replaces with
            ``depends_on``; kept here as a placeholder).
        config: JSON-encoded per-task parameters.
    """

    __tablename__ = "job_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("jobs.id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")


class JobLog(Base):
    """One structured log line written during a :class:`JobRun`.

    Pre-created for Sprint 20's structured log viewer; the Sprint 19
    scheduler emits via the stdlib ``logging`` module instead so tests
    can capture output with ``caplog`` without standing up this table.

    Attributes:
        id: Auto-incremented primary key.
        job_run_id: FK to ``job_runs.id``.
        ts: Timestamp when the log line was emitted.
        level: Python log level name (``"INFO"``, ``"WARNING"`` …).
        message: Free-form log text.
    """

    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("job_runs.id"), nullable=False
    )
    ts: Mapped[datetime.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
