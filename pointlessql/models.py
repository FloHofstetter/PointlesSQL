"""SQLAlchemy ORM models for PointlesSQL's own metadata database."""

from __future__ import annotations

import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, text
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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str] = mapped_column(String(200), nullable=False)
    password_hash: Mapped[str | None] = mapped_column(String(128), nullable=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    oidc_provider: Mapped[str | None] = mapped_column(String(500), nullable=True)
    oidc_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AuditLog(Base):
    """Append-only log of user actions for accountability.

    Attributes:
        id: Auto-incremented primary key.
        user_id: ID of the user who performed the action (no FK so
            entries survive user deletion).
        user_email: Email snapshot at time of action.
        actor_role: Role of the actor at time of action
            (``admin`` / ``user`` / ``system``). Sprint 48 addition.
        action: Short verb describing the action (e.g. ``update_catalog``).
        target: Identifier of the affected resource (e.g. ``catalog:my_cat``).
        client_ip: IPv4/IPv6 address of the requesting client, or
            ``None`` for system-generated rows. Sprint 48 addition.
        detail: Optional JSON-encoded context (stored as ``Text`` to
            allow arbitrarily-sized structured payloads — Sprint 48
            widened this from ``String(2000)``).
        created_at: Timestamp when the action occurred.
    """

    __tablename__ = "audit_log"

    __table_args__ = (
        Index("ix_audit_log_user_created", "user_id", "created_at"),
        Index("ix_audit_log_target_created", "target", "created_at"),
        Index("ix_audit_log_created", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_email: Mapped[str] = mapped_column(String(254), nullable=False)
    actor_role: Mapped[str] = mapped_column(
        String(20), nullable=False, default="user", server_default="user"
    )
    action: Mapped[str] = mapped_column(String(50), nullable=False)
    target: Mapped[str] = mapped_column(String(500), nullable=False)
    client_ip: Mapped[str | None] = mapped_column(String(45), nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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

    __table_args__ = (
        Index("ix_sync_run_catalog_started", "catalog_name", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    catalog_name: Mapped[str] = mapped_column(String(500), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
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

    Sprint 19 introduced single-task jobs. Sprint 20 grows this into
    multi-task DAGs: ``job.kind`` and ``job.config`` still work as a
    single-task shortcut (when no :class:`JobTask` rows exist), but for
    multi-task DAGs the :class:`JobTask` children drive execution and
    the top-level ``config`` is largely ignored by the executor.

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
        kind: Registry key for the single-task shortcut (e.g.
            ``"pg_sync"``, ``"python"``). Ignored when :class:`JobTask`
            rows exist.
        config: JSON-encoded parameters for the single-task shortcut.
        is_paused: When ``True`` the scheduler skips this job.
        max_parallel_runs: Upper bound on concurrent :class:`JobRun`
            rows in ``running`` status for this job. Default ``1``
            preserves Sprint 19's "one at a time" behaviour; the global
            ceiling in :class:`~pointlessql.settings.Settings`
            (``scheduler_max_concurrent_runs``) clamps this further.
        on_failure_url: Optional HTTPS URL that the scheduler POSTs a
            minimal JSON payload to whenever a :class:`JobRun` finishes
            with status ``failed``. Opt-in per job; see
            :func:`pointlessql.services.scheduler._post_failure_webhook`
            for the payload shape. No retries — a one-shot 5-second
            POST, with any transport failure logged and swallowed so
            the run itself never depends on an external receiver.
        created_at: Timestamp when the job was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "jobs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    cron_expr: Mapped[str] = mapped_column(String(120), nullable=False)
    run_as_user_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(String(50), nullable=False)
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    is_paused: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    max_parallel_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    on_failure_url: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


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
    __table_args__ = (Index("ix_job_runs_job_started", "job_id", "started_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    trigger: Mapped[str] = mapped_column(String(20), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobTask(Base):
    """One node in a :class:`Job` DAG.

    The Sprint 20 scheduler builds a graph from these rows: each task
    names the tasks it depends on (via ``depends_on`` — a JSON-encoded
    list of ``job_tasks.id`` integers rooted at the *same* parent job)
    and carries its own kind + config + retry policy. A job with zero
    :class:`JobTask` rows falls back to the Sprint 19 single-task
    shortcut that reads ``job.kind`` / ``job.config``.

    Attributes:
        id: Auto-incremented primary key.
        job_id: FK to ``jobs.id``.
        name: Human-readable task name, unique within the parent job.
        order: Ordinal within the job. Still written so existing rows
            remain valid after migration; the DAG walker ignores it in
            favour of ``depends_on``.
        kind: Registry key for the task executor (e.g. ``"python"``,
            ``"pg_sync"``). Mirrors :attr:`Job.kind` so every task can
            pick its own executor.
        config: JSON-encoded per-task parameters.
        depends_on: JSON-encoded list of upstream task ids within the
            same job. Cycles raise :class:`ValidationError` at DAG
            creation time.
        max_retries: Upper bound on additional attempts after the first
            failure. ``0`` (the default) means "fail on first error".
        retry_backoff_seconds: Delay between attempts, linear. Total
            wall-clock delay is ``attempt_index * retry_backoff_seconds``
            before each retry. Linear (not exponential) because every
            retry already competes for the per-job + global scheduler
            semaphores — adding exponential growth on top makes tuning
            harder without buying much.
    """

    __tablename__ = "job_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_id: Mapped[int] = mapped_column(Integer, ForeignKey("jobs.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    kind: Mapped[str] = mapped_column(String(50), nullable=False, default="python")
    config: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    depends_on: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    retry_backoff_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class TaskRun(Base):
    """One execution of a :class:`JobTask` within a :class:`JobRun`.

    The DAG walker inserts one row per task per parent :class:`JobRun`
    and cycles its ``status`` column through ``pending`` → ``running``
    → ``succeeded`` | ``failed`` | ``skipped``. ``attempts`` counts
    retry rounds (``1`` after the first attempt, bumped on every
    retry); ``error`` snapshots the last exception when a task fails.

    Attributes:
        id: Auto-incremented primary key.
        job_run_id: FK to ``job_runs.id`` — the parent run.
        task_id: FK to ``job_tasks.id`` — which node of the DAG.
        status: ``pending``, ``running``, ``succeeded``, ``failed``,
            or ``skipped``. ``skipped`` means an upstream task failed;
            ``failed`` means every attempt of this task itself failed.
        started_at: Timestamp of the first attempt.
        finished_at: Timestamp of the final attempt.
        attempts: Number of attempts actually executed (includes the
            initial attempt; a value of ``3`` means initial + 2 retries).
        error: Last exception message, or ``None`` when the task
            succeeded or was skipped because an upstream failed.
    """

    __tablename__ = "task_runs"

    __table_args__ = (Index("ix_task_runs_job_run", "job_run_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("job_runs.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(Integer, ForeignKey("job_tasks.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    started_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class Dashboard(Base):
    """A named, publishable view of a notebook job's latest output.

    Dashboards differ from the Sprint 26 run viewer in two ways: they
    live at a stable slug-based URL (so they can be shared or bookmarked
    across run id churn), and they render via nbconvert with
    ``exclude_input=True`` so consumers see only outputs — code cells
    are hidden. A dashboard points at a notebook_path for discoverability
    and optionally at a :class:`Job`; when a job is bound, the detail
    page surfaces the latest ``succeeded`` :class:`JobRun`'s HTML and an
    admin-only "Refresh" button triggers a manual run. The FK uses
    ``ON DELETE SET NULL`` so the dashboard survives job deletion as an
    orphan pointing at its notebook_path.

    Attributes:
        id: Auto-incremented primary key.
        slug: URL-visible identifier, unique across all dashboards.
        title: Human-readable name shown in the list and detail pages.
        description: Optional free-form description.
        notebook_path: Path relative to ``settings.jupyter.notebooks_dir``. Kept
            alongside the bound job even though the job config already
            carries a notebook_path — surfaces in the list view before
            the user clicks through.
        job_id: FK to ``jobs.id`` or ``None`` when no job is bound yet.
        owner_id: FK to ``users.id`` — the user who created the
            dashboard.
        created_at: Timestamp when the dashboard was created.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "dashboards"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    notebook_path: Mapped[str] = mapped_column(String(1000), nullable=False)
    job_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RateLimitEvent(Base):
    """One recorded hit against an auth-surface rate limiter (Sprint 43).

    The :mod:`pointlessql.api.rate_limit_middleware` middleware inserts
    one row per incoming request that matches a configured rule (e.g.
    ``POST /auth/login`` keyed by IP) and counts rows within the rule's
    window to decide whether the current request exceeds the limit.

    Rows are append-only while the window is live and pruned
    opportunistically by the same middleware before each count — no
    background sweeper is needed because the ``(bucket, created_at)``
    index keeps both the count and the cleanup DELETE cheap.

    Attributes:
        id: Auto-incremented primary key.
        bucket: Rule-scoped key combining the route tag with the
            rate-limit dimension, e.g. ``"auth.login.ip:1.2.3.4"`` or
            ``"auth.login.email:flo@example.com"``. Fixed-length ceiling
            keeps the index compact.
        created_at: Timestamp when the event was recorded.
    """

    __tablename__ = "rate_limit_events"

    __table_args__ = (
        Index("ix_rate_limit_events_bucket_created", "bucket", "created_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QueryHistory(Base):
    """One execution of an ad-hoc SQL query from the Phase-12 editor.

    Written on every ``POST /api/sql/execute`` call — including
    failures — so the ``/queries`` page can render the full stream of
    activity without "phantom" gaps for errors.  Non-admin users see
    only their own rows; admin sees everyone's.

    Retention of successful + failed rows is currently unbounded;
    Phase 12 deliberately does not ship a cleanup job because the
    per-row volume is tiny compared to the audit log.  If retention
    becomes a concern it can reuse the Sprint-48 audit-cleanup task
    pattern.

    ``request_id`` lets ops cross-reference a history row with the
    Sprint-16 request-id-tagged log line for the same execution.

    Attributes:
        id: Auto-incremented primary key.
        user_id: ID of the user who ran the query (no FK so entries
            survive user deletion).
        user_email: Email snapshot at time of run.
        sql_text: Verbatim query as submitted (NOT the DuckDB-rewritten
            form, since the original is what the UI re-runs).
        started_at: Timestamp when the route handler began.
        finished_at: Timestamp when the DuckDB call returned (or the
            route raised on enforcement / parse).
        status: ``"succeeded"`` / ``"failed"`` / ``"cancelled"``.
            Cancellation is Sprint 52; Sprint 50 only writes
            succeeded / failed.
        row_count: Result row count after :meth:`PQL.sql` row-cap
            slicing, or ``None`` on failure.
        duration_ms: DuckDB wall-clock time in milliseconds, or
            ``None`` on failure.
        error_message: Exception detail on failure, else ``None``.
        request_id: Correlates with structured log lines.
    """

    __tablename__ = "query_history"

    __table_args__ = (
        Index("ix_query_history_user_started", "user_id", "started_at"),
        Index("ix_query_history_started", "started_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False)
    user_email: Mapped[str] = mapped_column(String(254), nullable=False)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    finished_at: Mapped[datetime.datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    row_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    request_id: Mapped[str | None] = mapped_column(String(36), nullable=True)


class QueryHistoryTable(Base):
    """One UC table referenced by a :class:`QueryHistory` row.

    Populated from the sqlglot parse of ``sql_text``.  Exists as a
    separate relation so "who queried table X" is a fast reverse
    lookup via ``full_name``.  ``access_type`` is always ``"read"``
    in Phase 12 (the editor only permits SELECT); reserved so
    Phase 13's agent-workload write paths can distinguish read vs.
    write access for the same history surface.

    Attributes:
        id: Auto-incremented primary key.
        query_history_id: FK to ``query_history.id``.
        full_name: Dotted UC identifier (``catalog.schema.table``).
        access_type: ``"read"`` (Phase 12) or ``"write"`` (reserved).
    """

    __tablename__ = "query_history_tables"

    __table_args__ = (
        Index("ix_query_history_tables_full_name", "full_name", "query_history_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    query_history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("query_history.id"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(500), nullable=False)
    access_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="read", server_default="read"
    )


class JobLog(Base):
    """One structured log line written during a :class:`JobRun`.

    Sprint 20 makes this the real writer: every task transition
    (``pending`` → ``running`` → terminal) produces a row via
    :func:`pointlessql.services.scheduler.log_job`, and the job detail
    page's expandable log panel reads them back with an optional
    ``task_id`` filter so the user can scope the view to one DAG node.

    Attributes:
        id: Auto-incremented primary key.
        job_run_id: FK to ``job_runs.id``.
        task_id: FK to ``job_tasks.id``, or ``None`` for run-scoped
            entries (lifecycle events that are not tied to one task).
        ts: Timestamp when the log line was emitted.
        level: Python log level name (``"INFO"``, ``"WARNING"`` …).
        message: Free-form log text.
    """

    __tablename__ = "job_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    job_run_id: Mapped[int] = mapped_column(Integer, ForeignKey("job_runs.id"), nullable=False)
    task_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("job_tasks.id"), nullable=True)
    ts: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    level: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
