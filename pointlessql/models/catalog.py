"""Catalog-surface models: dashboards, query history, saved queries, table stats, rate limit."""

from __future__ import annotations

import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from pointlessql.models.base import Base


class Dashboard(Base):
    """A named, publishable view of a notebook job's latest output.

    Dashboards differ from the per-run viewer in two ways: they
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
    """One recorded hit against an auth-surface rate limiter.

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

    __table_args__ = (Index("ix_rate_limit_events_bucket_created", "bucket", "created_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bucket: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class QueryHistory(Base):
    """One execution of an ad-hoc SQL query from the editor.

    Written on every ``POST /api/sql/execute`` call — including
    failures — so the ``/queries`` page can render the full stream of
    activity without "phantom" gaps for errors.  Non-admin users see
    only their own rows; admin sees everyone's.

    Retention of successful + failed rows is currently unbounded; no
    cleanup job ships because the per-row volume is tiny compared to
    the audit log.  If retention becomes a concern it can reuse the
    audit-cleanup task pattern.

    ``request_id`` lets ops cross-reference a history row with the
    request-id-tagged log line for the same execution.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this query was executed in (Phase
            28.1b).  FK to :class:`Workspace.id`; resolved from
            request.state at insert time so cross-workspace
            ``/queries`` traffic stays isolated.
        user_id: ID of the user who ran the query (no FK so entries
            survive user deletion).
        user_email: Email snapshot at time of run.
        sql_text: Verbatim query as submitted (NOT the DuckDB-rewritten
            form, since the original is what the UI re-runs).
        started_at: Timestamp when the route handler began.
        finished_at: Timestamp when the DuckDB call returned (or the
            route raised on enforcement / parse).
        status: ``"succeeded"`` / ``"failed"`` / ``"cancelled"``.
        row_count: Result row count after :meth:`PQL.sql` row-cap
            slicing, or ``None`` on failure.
        duration_ms: DuckDB wall-clock time in milliseconds, or
            ``None`` on failure.
        error_message: Exception detail on failure, else ``None``.
        request_id: Correlates with structured log lines.
        chart_config: JSON-as-text payload capturing the user's
            chart selection (type, X column, Y column) so re-runs
            from ``/queries`` replay the same visualisation.
            ``None`` means "show the table view".
        agent_run_id: Owning :class:`AgentRun` UUID when the query
            came from a registered run.  ``None`` for plain
            interactive editor traffic.  No FK by design so deleting
            a run does not cascade-erase its query history.
        read_kind: Discriminator across the read paths that converge
            on ``query_history`` — ``"sql_execute"`` for ``/api/sql/
            execute`` traffic (the default and the only writer
            before ), ``"pql_table"`` for direct
            ``pql.table()`` reads recorded via
            :func:`pointlessql.services.read_audit.record_read`,
            and ``"engine_direct"`` for raw engine reads instrumented
            by the same helper.  Validation lives in
            :func:`pointlessql.services.query_history.record_query`.
    """

    __tablename__ = "query_history"

    # ``ix_query_history_agent_run_id`` is a partial index — only rows
    # whose ``agent_run_id`` is non-NULL are indexed, so the run-detail
    # view's filter is index-backed without bloating writes from the
    # plain interactive-editor traffic that has no run attached.
    __table_args__ = (
        Index("ix_query_history_user_started", "user_id", "started_at"),
        Index("ix_query_history_started", "started_at"),
        Index("ix_query_history_workspace_started", "workspace_id", "started_at"),
        Index(
            "ix_query_history_agent_run_id",
            "agent_run_id",
            sqlite_where=text("agent_run_id IS NOT NULL"),
            postgresql_where=text("agent_run_id IS NOT NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Phase 28.1b — every query-history row is workspace-scoped.
    # Resolved from request.state at insert time by services.query_history.
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
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
    chart_config: Mapped[str | None] = mapped_column(Text, nullable=True)
    agent_run_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    read_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="sql_execute")


class QueryHistoryTable(Base):
    """One UC table referenced by a :class:`QueryHistory` row.

    Populated from the sqlglot parse of ``sql_text``.  Exists as a
    separate relation so "who queried table X" is a fast reverse
    lookup via ``full_name``.  ``access_type`` is ``"read"`` for the
    SELECT-only editor surface; reserved so agent-workload write
    paths can distinguish read vs. write access for the same
    history surface.

    Attributes:
        id: Auto-incremented primary key.
        workspace_id: Workspace this reference belongs to (Phase
            28.1b).  Denormalised from the parent QueryHistory.
        query_history_id: FK to ``query_history.id``.
        full_name: Dotted UC identifier (``catalog.schema.table``).
        access_type: ``"read"`` or ``"write"``.
    """

    __tablename__ = "query_history_tables"

    __table_args__ = (
        Index("ix_query_history_tables_full_name", "full_name", "query_history_id"),
        Index("ix_query_history_tables_workspace_full", "workspace_id", "full_name"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    workspace_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("workspaces.id"), nullable=False, server_default="1"
    )
    query_history_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("query_history.id"), nullable=False
    )
    full_name: Mapped[str] = mapped_column(String(500), nullable=False)
    access_type: Mapped[str] = mapped_column(
        String(10), nullable=False, default="read", server_default="read"
    )


class SavedQuery(Base):
    """A named, slug-addressable snippet of SQL the user saved.

    The "save current query" flow lets operators park frequently-run
    analyses and re-open them from the editor's sidebar drawer.

    Visibility model: the ``owner_id`` user and all admins always
    see the row; every other logged-in user sees it only when
    ``is_shared`` is ``True``.  Admin can also mutate any row
    (edit / delete / toggle sharing) — everyone else can only
    mutate rows they own.  Enforcement lives in
    :mod:`pointlessql.services.saved_queries` and the API layer.

    The slug is the canonical URL-visible identifier.  Generated
    from ``slugify(title) + "-" + short-random`` so two saved
    queries sharing a title don't collide.

    Attributes:
        id: Auto-incremented primary key.
        slug: URL-visible identifier, unique across all rows.
        title: Human-readable name shown in the drawer.
        description: Optional free-form description.
        sql_text: The verbatim SQL to load back into the editor.
        owner_id: FK to ``users.id``.  The user who saved the query.
        is_shared: When ``True`` every logged-in user sees this row
            in their drawer; when ``False`` only the owner and
            admins do.
        created_at: Timestamp when the row was saved.
        updated_at: Timestamp of the most recent mutation.
    """

    __tablename__ = "saved_queries"

    __table_args__ = (Index("ix_saved_queries_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(String(2000), nullable=True)
    sql_text: Mapped[str] = mapped_column(Text, nullable=False)
    owner_id: Mapped[int] = mapped_column(Integer, ForeignKey("users.id"), nullable=False)
    is_shared: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    updated_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class TableStats(Base):
    """Cached per-column statistics for a UC table at a Delta version.

    The profile button computes count / null_count / distinct_count
    / min / max / mean / top_5 for every column of a Delta table;
    each column lands as its own row so the cache survives partial
    failures.  Results are keyed by
    ``(full_name, delta_log_version, column_name)`` — re-profiling
    the same version is a single index seek.

    Attributes:
        id: Auto-incremented primary key.
        full_name: UC three-part dotted name.
        delta_log_version: Delta log ``version()`` at profile time.
        column_name: Column identifier from the Delta schema.
        stats_json: Serialised dict of per-column stats.
        computed_at: When the profile run finished.
    """

    __tablename__ = "table_stats"
    __table_args__ = (
        UniqueConstraint(
            "full_name",
            "delta_log_version",
            "column_name",
            name="uq_table_stats_col_version",
        ),
        Index("ix_table_stats_lookup", "full_name", "delta_log_version"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    full_name: Mapped[str] = mapped_column(String(500), nullable=False)
    delta_log_version: Mapped[int] = mapped_column(BigInteger, nullable=False)
    column_name: Mapped[str] = mapped_column(String(255), nullable=False)
    stats_json: Mapped[str] = mapped_column(Text, nullable=False)
    computed_at: Mapped[datetime.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
