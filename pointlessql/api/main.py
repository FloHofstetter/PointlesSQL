"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import (
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from pointlessql.api.admin_api_keys_routes import router as admin_api_keys_router
from pointlessql.api.admin_external_writes_routes import router as admin_external_writes_router
from pointlessql.api.admin_routes import router as admin_router
from pointlessql.api.agent_reviews_routes import router as agent_reviews_router
from pointlessql.api.agent_runs_routes import router as agent_runs_router
from pointlessql.api.alerts_routes import router as alerts_router
from pointlessql.api.audit_routes import router as audit_router
from pointlessql.api.audit_sinks_routes import router as audit_sinks_router
from pointlessql.api.auth_routes import router as auth_router
from pointlessql.api.branches_routes import router as branches_router
from pointlessql.api.catalog_html_routes import router as catalog_html_router
from pointlessql.api.catalog_routes import router as catalog_router
from pointlessql.api.conventions_routes import router as conventions_router
from pointlessql.api.dashboards_routes import router as dashboards_router
from pointlessql.api.dependencies import (
    require_admin as _require_admin,
)
from pointlessql.api.federation_routes import router as federation_router
from pointlessql.api.governance_routes import router as governance_router
from pointlessql.api.home_routes import router as home_router
from pointlessql.api.jobs_routes import (
    router as jobs_router,
)
from pointlessql.api.lineage_routes import router as lineage_router
from pointlessql.api.middleware import register_middleware
from pointlessql.api.notebooks_routes import router as notebooks_router
from pointlessql.api.pql_introspect_routes import router as pql_introspect_router
from pointlessql.api.pql_write_routes import router as pql_write_router
from pointlessql.api.queries_routes import router as queries_router
from pointlessql.api.review_destinations_routes import router as review_destinations_router
from pointlessql.api.runs_routes import router as runs_router
from pointlessql.api.saved_audit_queries_routes import (
    router as saved_audit_queries_router,
)
from pointlessql.api.sql_routes import router as sql_router
from pointlessql.api.time_travel_routes import router as time_travel_router
from pointlessql.api.volumes_routes import (
    DELTA_PRIMITIVE_TO_UC as _DELTA_PRIMITIVE_TO_UC,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from pointlessql.api.volumes_routes import (
    delta_field_to_uc as _delta_field_to_uc,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from pointlessql.api.volumes_routes import (
    router as volumes_router,
)
from pointlessql.db import get_session_factory, init_db
from pointlessql.logging_config import configure_logging
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import audit as audit_service
from pointlessql.services import metrics as metrics_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.settings import Settings

# Configure logging at module import time so it takes effect in every
# process that serves traffic — the uvicorn --reload worker imports
# this module but does not go through cli(). Idempotent; subsequent
# calls replace our own handlers without disturbing pytest's caplog.
_startup_settings = Settings()
configure_logging(_startup_settings.logging.level, _startup_settings.logging.format)

logger = logging.getLogger(__name__)

# In a dev checkout the frontend dir is at the repo root; in an
# installed wheel hatchling force-includes it as pointlessql/_frontend.
_dev_dir = Path(__file__).resolve().parents[2] / "frontend"
_FRONTEND_DIR = _dev_dir if _dev_dir.is_dir() else Path(__file__).resolve().parents[1] / "_frontend"
_TEMPLATES = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))


def _format_epoch_ms(value: Any) -> str:
    """Format Unity Catalog epoch-millisecond timestamps as a local datetime."""
    if value is None:
        return "—"
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    except TypeError, ValueError:
        return str(value)


_TEMPLATES.env.filters["epoch_ms"] = _format_epoch_ms


_original_template_response = _TEMPLATES.TemplateResponse


def _template_response_with_user(request: Request, *args: Any, **kwargs: Any) -> Response:
    """Wrap TemplateResponse to inject ``current_user`` into every context."""
    # TemplateResponse(request, name, context) or (name, context, request=request)
    # Starlette 0.37+ signature: TemplateResponse(request, name, context={}, ...)
    if "context" in kwargs:
        kwargs["context"].setdefault("current_user", getattr(request.state, "user", None))
    elif len(args) >= 2 and isinstance(args[1], dict):
        mutable = list(args)
        mutable[1].setdefault("current_user", getattr(request.state, "user", None))
        args = tuple(mutable)
    return _original_template_response(request, *args, **kwargs)


_TEMPLATES.TemplateResponse = _template_response_with_user  # type: ignore[assignment]


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Build shared app state and run the scheduler + audit retention loop."""
    settings = Settings()
    logger.info(
        "PointlesSQL starting on %s:%d (engine=%s, log_format=%s)",
        settings.server.host,
        settings.server.port,
        settings.delta.engine,
        settings.logging.format,
    )
    soyuz = make_soyuz_client(settings)
    app.state.uc_client = UnityCatalogClient(soyuz)
    app.state.settings = settings
    app.state.templates = _TEMPLATES
    init_db(settings.db.url)
    app.state.session_factory = get_session_factory()

    # API keys are persisted in the ``api_keys`` table.  The env
    # var ``POINTLESSQL_API_KEYS`` stays valid as a *bootstrap* path
    # so clean-machine docker-compose deployments without an admin
    # UI mounted still work — the helper below idempotently spills
    # any declared ``name:secret[:supervisor]`` pairs into the DB on
    # startup.  Existing rows are left untouched (DB is the single
    # source of truth once the table is populated).
    inserted = api_keys_service.bootstrap_from_env(app.state.session_factory)
    if inserted:
        logger.info("Bootstrapped %d API key(s) from POINTLESSQL_API_KEYS", inserted)

    scheduler: scheduler_service.Scheduler | None = None
    if settings.scheduler.enabled:
        scheduler = scheduler_service.Scheduler(app.state.session_factory, settings)
        scheduler.start()
    app.state.scheduler = scheduler

    # Periodic audit-log retention sweep. Runs on its own tick
    # cadence (``audit.cleanup_interval_seconds``) so it does not
    # compete with the job scheduler; swallows its own errors via
    # ``cleanup_old_entries`` so a transient DB hiccup never takes
    # the lifespan down.
    audit_task = asyncio.create_task(
        _audit_retention_loop(app.state.session_factory, settings),
        name="audit-retention",
    )

    # Periodic external-write scanner.  Disabled by default
    # (``scan_interval_seconds == 0``); admins opt in via
    # ``POINTLESSQL_EXTERNAL_WRITES_SCAN_INTERVAL_SECONDS``.  The
    # admin page's "Run scan now" button works regardless.
    external_writes_task: asyncio.Task[None] | None = None
    if settings.external_writes.scan_interval_seconds > 0:
        external_writes_task = asyncio.create_task(
            _external_writes_loop(app.state.session_factory, app.state.uc_client, settings),
            name="external-writes-scan",
        )

    # Sprint 20.2 lineage retention pruner.  Runs as its own
    # asyncio task next to the audit-retention loop — the existing
    # scheduler is built around per-user JobExecutor callbacks that
    # don't fit a system-maintenance task without per-axis None
    # thresholds the loop also short-circuits.
    lineage_pruner_task: asyncio.Task[None] | None = None
    retention = settings.audit.lineage_retention
    if any(
        v is not None and v > 0
        for v in (
            retention.row_edges_days,
            retention.row_rejects_days,
            retention.column_map_days,
            retention.value_changes_days,
        )
    ):
        lineage_pruner_task = asyncio.create_task(
            _lineage_pruner_loop(app.state.session_factory, settings),
            name="lineage-pruner",
        )

    # Sprint 16.5.6 branch auto-cleanup.  Opt-in default-disabled
    # (``branch.auto_cleanup_enabled=False``); the loop body itself
    # short-circuits when disabled, so we always start it but it's a
    # cheap no-op until the operator flips the flag.
    branch_cleanup_task: asyncio.Task[None] = asyncio.create_task(
        _branch_cleanup_loop(app.state.uc_client, settings),
        name="branch-cleanup",
    )

    # The browser notebook editor was retired; a future
    # :class:`KernelRegistry` on ``app.state`` will serve as the
    # execution backend for the ``agent_run`` scheduler kind.
    # Nothing else to start here yet.
    try:
        yield
    finally:
        audit_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await audit_task
        if external_writes_task is not None:
            external_writes_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await external_writes_task
        if lineage_pruner_task is not None:
            lineage_pruner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lineage_pruner_task
        branch_cleanup_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await branch_cleanup_task
        if scheduler is not None:
            await scheduler.stop()
        await app.state.uc_client.aclose()


async def _audit_retention_loop(
    factory: Any,
    settings: Settings,
) -> None:
    """Run ``cleanup_old_entries`` on a fixed cadence for the lifetime of the app.

    A separate task rather than a scheduler-kind keeps the
    cleanup path independent of the job scheduler — operators who
    disable the scheduler (``POINTLESSQL_SCHEDULER_ENABLED=false``)
    still want retention to run.

    Args:
        factory: SQLAlchemy session factory shared with the rest
            of the app.
        settings: Snapshotted :class:`Settings` — only
            ``audit.retention_days`` and
            ``audit.cleanup_interval_seconds`` are read.
    """
    interval = max(60, settings.audit.cleanup_interval_seconds)
    retention = settings.audit.retention_days
    while True:
        try:
            await asyncio.to_thread(audit_service.cleanup_old_entries, factory, retention)
        except Exception:  # noqa: BLE001 — retention loop must survive everything
            logger.exception("audit: retention loop tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _external_writes_loop(
    factory: Any,
    uc: Any,
    settings: Settings,
) -> None:
    """Periodic scan for unattributed Delta commits.

    Active only when
    ``POINTLESSQL_EXTERNAL_WRITES_SCAN_INTERVAL_SECONDS`` is
    explicitly non-zero — the default keeps the loop dormant on
    single-node vServer deployments where per-table
    ``DeltaTable.history()`` cost adds up.

    Args:
        factory: SQLAlchemy session factory shared with the rest
            of the app.
        uc: ``UnityCatalogClient`` used to enumerate tables.
        settings: Snapshotted :class:`Settings` — only
            ``external_writes.scan_interval_seconds`` and
            ``external_writes.history_limit`` are read.
    """
    from pointlessql.services import external_write_scanner

    interval = max(60, settings.external_writes.scan_interval_seconds)
    history_limit = settings.external_writes.history_limit
    while True:
        try:
            inserted = await external_write_scanner.scan_all(
                factory, uc, history_limit=history_limit
            )
            if inserted:
                logger.info(
                    "external_writes: scan tick recorded %d unattributed commit(s)",
                    inserted,
                )
        except Exception:  # noqa: BLE001 — scanner loop must survive everything
            logger.exception("external_writes: scan tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _lineage_pruner_loop(
    factory: Any,
    settings: Settings,
) -> None:
    """Periodic prune of the four lineage tables (Sprint 20.2).

    Active when at least one
    :class:`LineageRetentionSettings` axis has a positive
    ``*_days`` value.  The loop wakes every
    ``audit.cleanup_interval_seconds`` (default 86400 = 24h),
    matching the audit-log retention cadence — both run in the
    operator-quiet hours.

    Args:
        factory: SQLAlchemy session factory shared with the rest
            of the app.
        settings: Snapshotted :class:`Settings`.
    """
    from pointlessql.services.lineage_pruner import prune_once_async

    interval = max(60, settings.audit.cleanup_interval_seconds)
    while True:
        try:
            deleted = await prune_once_async(factory, settings)
            if deleted:
                logger.info(
                    "lineage_pruner: pruned %s",
                    ", ".join(f"{axis}={count}" for axis, count in deleted.items()),
                )
        except Exception:  # noqa: BLE001 — pruner must survive everything
            logger.exception("lineage_pruner: prune tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _branch_cleanup_loop(
    uc: Any,
    settings: Settings,
) -> None:
    """Periodic Phase-16.5 branch auto-cleanup pass.

    Wakes once per ``audit.cleanup_interval_seconds`` (default
    24h), then either short-circuits (when
    ``branch.auto_cleanup_enabled=False``) or walks UC schemas and
    discards active branches past
    ``branch.auto_cleanup_retention_days``.  The 24h cadence is
    deliberately coarse — branch cleanup is a maintenance op, not a
    realtime concern.

    Args:
        uc: ``UnityCatalogClient`` whose underlying sync client
            drives the cleanup pass.
        settings: Snapshotted :class:`Settings`.
    """
    from pointlessql.services.branch_cleanup import cleanup_old_branches

    interval = max(60, settings.audit.cleanup_interval_seconds)
    while True:
        try:
            summary = await asyncio.to_thread(
                cleanup_old_branches,
                client=uc._client,  # noqa: SLF001 — sync soyuz client
                settings=settings,
            )
            if summary.get("deleted"):
                logger.info("branch_cleanup: %s", summary)
        except Exception:  # noqa: BLE001 — cleanup loop must survive everything
            logger.exception("branch_cleanup: tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


app = FastAPI(title="PointlesSQL", version="0.1.0", lifespan=_lifespan)

from pointlessql.api.error_handlers import register_error_handlers  # noqa: E402

register_error_handlers(app)

app.include_router(auth_router)
app.include_router(catalog_router)
app.include_router(catalog_html_router)
app.include_router(conventions_router)
app.include_router(sql_router)
app.include_router(queries_router)
app.include_router(alerts_router)
app.include_router(audit_router)
app.include_router(saved_audit_queries_router)
app.include_router(volumes_router)
app.include_router(lineage_router)
app.include_router(time_travel_router)
app.include_router(governance_router)
app.include_router(notebooks_router)
app.include_router(runs_router)
app.include_router(agent_runs_router)
app.include_router(agent_reviews_router)
app.include_router(branches_router)
app.include_router(pql_introspect_router)
app.include_router(pql_write_router)
app.include_router(federation_router)
app.include_router(jobs_router)
app.include_router(dashboards_router)
app.include_router(home_router)
app.include_router(admin_router)
app.include_router(admin_api_keys_router)
app.include_router(admin_external_writes_router)
app.include_router(review_destinations_router)
app.include_router(audit_sinks_router)
app.mount(
    "/static",
    StaticFiles(directory=str(_FRONTEND_DIR)),
    name="static",
)

register_middleware(app)


@app.get("/healthz")
async def healthz() -> dict[str, str]:
    """Return service health."""
    return {"status": "ok"}


@app.get("/metrics")
async def metrics(request: Request) -> Response:
    """Expose Prometheus metrics for the scheduler (admin-only).

    Returns the default text exposition format so any Prometheus
    scraper works without extra negotiation. Gated by
    :func:`_require_admin` because the metrics surface includes the
    names of every job in the install, which is sensitive information
    on multi-tenant deployments.
    """
    _require_admin(request)
    body, content_type = metrics_service.render_metrics()
    return Response(content=body, media_type=content_type)


# -- Routes --
#
# Every JSON + HTML route the app serves now lives in a dedicated
# ``api/<area>_routes.py`` module attached above via
# ``include_router()``.  The original monolith was split into 14
# focused routers (auth, catalog tree + HTML, sql, queries, alerts,
# volumes, governance, notebooks HTTP + WS, federation, jobs,
# dashboards, home, admin).  Exceptions raised inside any handler
# propagate to the centralised handler in
# ``api/error_handlers.py``.


def _run_dev_server() -> None:
    """Start the uvicorn dev server with the project-scoped reload watcher."""
    import uvicorn

    settings = Settings()
    # Why: uvicorn's reload watcher defaults to the whole working directory.
    # That includes ``notebooks/``, so the editor's autosave triggers a server
    # reload — kernel + Pyright WebSockets get torn down mid-typing
    # (BUG-64-03). Pinning reload_dirs to the source trees keeps autosave
    # invisible to the watcher; SQLite files (.db) and Delta tables
    # (notebooks/, /tmp) stay outside scope.
    project_root = Path(__file__).resolve().parent.parent
    uvicorn.run(
        "pointlessql.api.main:app",
        host=settings.server.host,
        port=settings.server.port,
        reload=True,
        reload_dirs=[str(project_root), str(project_root.parent / "frontend")],
    )


# ---------------------------------------------------------------------------
# CLI surface — Typer app exposed via ``[project.scripts] pointlessql = "...:cli"``
# ---------------------------------------------------------------------------
#
# Why: Sprint 19.2.0 needed an admin-side helper to mint an auditor-scoped
# API key for the Audit-Reviewer-Agent's daily Hermes job. Rather than
# layering a separate console script, the existing ``pointlessql`` entry
# point grew a Typer app: the no-argument invocation still starts the dev
# server (backward-compat), and ``pointlessql admin <subcommand>`` exposes
# operational helpers.

import typer  # noqa: E402  # import below to keep heavy deps out of FastAPI import path

cli = typer.Typer(
    name="pointlessql",
    help="PointlesSQL CLI. Run with no arguments to start the dev server.",
    invoke_without_command=True,
    no_args_is_help=False,
)
_admin_cli = typer.Typer(help="Administrative helpers (key issuance, …).")
cli.add_typer(_admin_cli, name="admin")


@cli.callback()
def _root(ctx: typer.Context) -> None:  # pyright: ignore[reportUnusedFunction]
    """Default to the dev server when no subcommand is given."""
    if ctx.invoked_subcommand is None:
        _run_dev_server()


@_admin_cli.command("issue-auditor-key")
def _admin_issue_auditor_key(  # pyright: ignore[reportUnusedFunction]
    name: str = typer.Option(..., "--name", help="Unique key name (≤ 64 chars)."),
    supervisor: bool = typer.Option(
        False,
        "--supervisor",
        help="Also grant the supervisor scope (per-run write privileges).",
    ),
) -> None:
    """Issue a fresh auditor-scoped API key and print the plaintext token once.

    The token is stored as a salted hash in ``api_keys`` and cannot be
    recovered afterwards — copy it into the Hermes cron job's
    ``POINTLESSQL_API_KEY`` env overlay immediately.
    """
    settings = Settings()
    init_db(settings.db.url)
    factory = get_session_factory()
    try:
        row, plaintext = api_keys_service.create_api_key(
            factory,
            name=name,
            auditor=True,
            supervisor=supervisor,
        )
    except ValueError as exc:
        typer.echo(f"error: {exc}", err=True)
        raise typer.Exit(code=2) from exc
    typer.echo(f"name        = {row.name}")
    typer.echo(f"prefix      = {row.secret_prefix}")
    typer.echo(f"auditor     = {row.auditor}")
    typer.echo(f"supervisor  = {row.supervisor}")
    typer.echo(f"created_at  = {row.created_at.isoformat()}")
    typer.echo("")
    typer.echo("token (shown once — save it now):")
    typer.echo(plaintext)
