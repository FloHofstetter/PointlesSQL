"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import (
    Response,
)
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

import pointlessql
from pointlessql.api._bootstrap._loops import (
    _active_reviewer_loop,  # pyright: ignore[reportPrivateUsage]
    _audit_retention_loop,  # pyright: ignore[reportPrivateUsage]
    _branch_cleanup_loop,  # pyright: ignore[reportPrivateUsage]
    _cdf_tail_loop,  # pyright: ignore[reportPrivateUsage]
    _data_product_cooccurrence_loop,  # pyright: ignore[reportPrivateUsage]
    _data_product_freshness_loop,  # pyright: ignore[reportPrivateUsage]
    _data_product_passport_loop,  # pyright: ignore[reportPrivateUsage]
    _data_product_promotion_loop,  # pyright: ignore[reportPrivateUsage]
    _data_product_trending_loop,  # pyright: ignore[reportPrivateUsage]
    _external_writes_loop,  # pyright: ignore[reportPrivateUsage]
    _lineage_pruner_loop,  # pyright: ignore[reportPrivateUsage]
    _user_badges_loop,  # pyright: ignore[reportPrivateUsage]
    _user_notification_digest_loop,  # pyright: ignore[reportPrivateUsage]
    _workspace_repos_sync_loop,  # pyright: ignore[reportPrivateUsage]
)
from pointlessql.api._template_context import install_template_wrapper
from pointlessql.api._template_filters import register_template_filters
from pointlessql.api.dependencies import (
    require_admin as _require_admin,
)
from pointlessql.api.middleware import register_middleware
from pointlessql.api.volumes_routes import (
    DELTA_PRIMITIVE_TO_UC as _DELTA_PRIMITIVE_TO_UC,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from pointlessql.api.volumes_routes import (
    delta_field_to_uc as _delta_field_to_uc,  # noqa: F401  # pyright: ignore[reportUnusedImport]
)
from pointlessql.config import Settings, configure_logging
from pointlessql.db import get_session_factory, init_db
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import metrics as metrics_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.dbt import (
    DBTStartupError,
    DBTSubprocess,
    dbt_duckdb_available,
)
from pointlessql.services.mlflow_subprocess import (
    MLflowStartupError,
    MLflowSubprocess,
    mlflow_available,
)
from pointlessql.services.notebook.kernel_session import KernelRegistry
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient

# Configure logging at module import time so it takes effect in every
# process that serves traffic — the uvicorn --reload worker imports
# this module but does not go through cli(). Idempotent; subsequent
# calls replace our own handlers without disturbing pytest's caplog.
_startup_settings = Settings()
configure_logging(
    _startup_settings.logging.level,
    _startup_settings.logging.format,
    third_party_levels=_startup_settings.logging.third_party_levels,
)

logger = logging.getLogger(__name__)

# In a dev checkout the frontend dir is at the repo root; in an
# installed wheel hatchling force-includes it as pointlessql/_frontend.
_dev_dir = Path(__file__).resolve().parents[2] / "frontend"
_FRONTEND_DIR = _dev_dir if _dev_dir.is_dir() else Path(__file__).resolve().parents[1] / "_frontend"
_TEMPLATES = Jinja2Templates(directory=str(_FRONTEND_DIR / "templates"))
register_template_filters(_TEMPLATES)
install_template_wrapper(_TEMPLATES)


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

    # When the test conftest pre-wires ``app.state`` (engine,
    # session_factory, uc_client stubs), running the full production
    # lifespan re-overwrites all of it: ``init_db`` runs ``alembic
    # upgrade head`` against the on-disk default URL,
    # ``make_soyuz_client`` clobbers stubbed UC clients, and the
    # background tasks tick uselessly.  ``POINTLESSQL_TEST_LIFESPAN_FAST=1``
    # short-circuits everything the conftest has already set up,
    # leaving real production startup untouched.  Tests that need
    # the full lifespan (alembic verification, UC-client real
    # http path, etc.) simply unset the env var.
    fast_test_lifespan = os.environ.get("POINTLESSQL_TEST_LIFESPAN_FAST") == "1"

    if not fast_test_lifespan:
        soyuz = make_soyuz_client(settings)
        app.state.uc_client = UnityCatalogClient(soyuz)
    elif not hasattr(app.state, "uc_client") or app.state.uc_client is None:
        soyuz = make_soyuz_client(settings)
        app.state.uc_client = UnityCatalogClient(soyuz)

    app.state.settings = (
        getattr(app.state, "settings", None) if fast_test_lifespan else None
    ) or settings
    app.state.templates = _TEMPLATES
    if not fast_test_lifespan or not hasattr(app.state, "session_factory"):
        init_db(settings.db.url)
        app.state.session_factory = get_session_factory()

    # API keys are persisted in the ``api_keys`` table.  The env
    # var ``POINTLESSQL_API_KEYS`` stays valid as a *bootstrap* path
    # so clean-machine docker-compose deployments without an admin
    # UI mounted still work — the helper below idempotently spills
    # any declared ``name:secret[:supervisor]`` pairs into the DB on
    # startup.  Existing rows are left untouched (DB is the single
    # source of truth once the table is populated).
    if not fast_test_lifespan:
        inserted = api_keys_service.bootstrap_from_env(app.state.session_factory)
        if inserted:
            logger.info("Bootstrapped %d API key(s) from POINTLESSQL_API_KEYS", inserted)

    scheduler: scheduler_service.Scheduler | None = None
    if settings.scheduler.enabled and not fast_test_lifespan:
        scheduler = scheduler_service.Scheduler(app.state.session_factory, settings)
        scheduler.start()
    app.state.scheduler = scheduler

    # Periodic audit-log retention sweep. Runs on its own tick
    # cadence (``audit.cleanup_interval_seconds``) so it does not
    # compete with the job scheduler; swallows its own errors via
    # ``cleanup_old_entries`` so a transient DB hiccup never takes
    # the lifespan down.
    audit_task: asyncio.Task[None] | None = None
    if not fast_test_lifespan:
        audit_task = asyncio.create_task(
            _audit_retention_loop(app.state.session_factory, settings),
            name="audit-retention",
        )

    # Periodic external-write scanner.  Disabled by default
    # (``scan_interval_seconds == 0``); admins opt in via
    # ``POINTLESSQL_EXTERNAL_WRITES_SCAN_INTERVAL_SECONDS``.  The
    # admin page's "Run scan now" button works regardless.
    external_writes_task: asyncio.Task[None] | None = None
    if settings.external_writes.scan_interval_seconds > 0 and not fast_test_lifespan:
        external_writes_task = asyncio.create_task(
            _external_writes_loop(app.state.session_factory, app.state.uc_client, settings),
            name="external-writes-scan",
        )

    # Phase 50.4 — data-product freshness scanner.  Same opt-in
    # discipline as the external-write scanner: zero-config installs
    # see no extra Delta IO.  Activated by setting
    # ``POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS`` non-zero.
    data_product_freshness_task: asyncio.Task[None] | None = None
    if settings.data_products.scan_interval_seconds > 0 and not fast_test_lifespan:
        data_product_freshness_task = asyncio.create_task(
            _data_product_freshness_loop(
                app.state.session_factory, app.state.uc_client, settings
            ),
            name="data-product-freshness",
        )

    # CDF tail worker (Phase 40.5 — pull-modell to complement the
    # 40.1 push-modell).  Disabled by default
    # (``interval_seconds == 0``); admins opt in via
    # ``POINTLESSQL_CDF_TAIL_INTERVAL_SECONDS`` after registering
    # one or more subscriptions.
    cdf_tail_task: asyncio.Task[None] | None = None
    if settings.cdf_tail.interval_seconds > 0 and not fast_test_lifespan:
        cdf_tail_task = asyncio.create_task(
            _cdf_tail_loop(app.state.session_factory, app.state.uc_client, settings),
            name="cdf-tail",
        )

    # Phase 51.4 — workspace-repos sync cron.  Opt-in
    # default-disabled (``sync_interval_seconds == 0``).  When
    # active, the loop pulls every stale repo every interval; the
    # webhook receiver still triggers immediate syncs regardless.
    workspace_repos_task: asyncio.Task[None] | None = None
    if settings.workspace_repos.sync_interval_seconds > 0 and not fast_test_lifespan:
        workspace_repos_task = asyncio.create_task(
            _workspace_repos_sync_loop(app.state.session_factory, settings),
            name="workspace-repos-sync",
        )

    #  lineage retention pruner.  Runs as its own
    # asyncio task next to the audit-retention loop — the existing
    # scheduler is built around per-user JobExecutor callbacks that
    # don't fit a system-maintenance task without per-axis None
    # thresholds the loop also short-circuits.
    lineage_pruner_task: asyncio.Task[None] | None = None
    retention = settings.audit.lineage_retention
    if (
        any(
            v is not None and v > 0
            for v in (
                retention.row_edges_days,
                retention.row_rejects_days,
                retention.column_map_days,
                retention.value_changes_days,
            )
        )
        and not fast_test_lifespan
    ):
        lineage_pruner_task = asyncio.create_task(
            _lineage_pruner_loop(app.state.session_factory, settings),
            name="lineage-pruner",
        )

    #  branch auto-cleanup.  Opt-in default-disabled
    # (``branch.auto_cleanup_enabled=False``); the loop body itself
    # short-circuits when disabled, so we always start it but it's a
    # cheap no-op until the operator flips the flag.
    branch_cleanup_task: asyncio.Task[None] | None = None
    if not fast_test_lifespan:
        branch_cleanup_task = asyncio.create_task(
            _branch_cleanup_loop(app.state.uc_client, settings),
            name="branch-cleanup",
        )

    # Phase 72.3 — cached "trending in agent workloads" refresh.
    # Opt-in default-disabled
    # (``trending_refresh_interval_seconds == 0``); the join
    # query stays cheap for < 10⁴ ops/week but adds noise on
    # quiet single-tenant installs.
    data_product_trending_task: asyncio.Task[None] | None = None
    if (
        settings.data_products.trending_refresh_interval_seconds > 0
        and not fast_test_lifespan
    ):
        data_product_trending_task = asyncio.create_task(
            _data_product_trending_loop(app.state.session_factory, settings),
            name="data-product-trending",
        )

    # Phase 73.1 — promote-to-DP candidate scanner.  Always
    # safe to schedule: the loop body short-circuits when
    # ``promote_enabled`` is false (default).
    data_product_promotion_task: asyncio.Task[None] | None = None
    if (
        settings.data_products.promote_enabled
        and not fast_test_lifespan
    ):
        data_product_promotion_task = asyncio.create_task(
            _data_product_promotion_loop(app.state.session_factory, settings),
            name="data-product-promotion",
        )

    # Phase 73.4 — auto-passport stale-refresh loop.  Opt-in
    # via ``passport_loop_enabled`` (default off).
    data_product_passport_task: asyncio.Task[None] | None = None
    if (
        settings.data_products.passport_loop_enabled
        and not fast_test_lifespan
    ):
        data_product_passport_task = asyncio.create_task(
            _data_product_passport_loop(app.state.session_factory, settings),
            name="data-product-passport",
        )

    # Phase 73.5 — cross-DP cooccurrence cache refresh.  Opt-in.
    data_product_cooccurrence_task: asyncio.Task[None] | None = None
    if (
        settings.data_products.cooccurrence_enabled
        and not fast_test_lifespan
    ):
        data_product_cooccurrence_task = asyncio.create_task(
            _data_product_cooccurrence_loop(app.state.session_factory, settings),
            name="data-product-cooccurrence",
        )

    # Phase 74.1 — active-reviewer daily tick.  Opt-in
    # default-disabled (``data_products.active_reviewer_enabled``);
    # the loop body short-circuits when disabled, so registering it
    # is cheap.
    active_reviewer_task: asyncio.Task[None] | None = None
    if (
        settings.data_products.active_reviewer_enabled
        and not fast_test_lifespan
    ):
        active_reviewer_task = asyncio.create_task(
            _active_reviewer_loop(app.state.session_factory, settings),
            name="active-reviewer",
        )

    # Phase 71.4 follow-up B.3 — daily marketplace digest.  Opt-in
    # default-disabled (``notifications.digest_enabled=False``); the
    # loop body itself short-circuits when disabled, so we always
    # start it but it's a cheap no-op until the operator flips the
    # flag.
    user_notification_digest_task: asyncio.Task[None] | None = None
    if not fast_test_lifespan:
        user_notification_digest_task = asyncio.create_task(
            _user_notification_digest_loop(app.state.session_factory, settings),
            name="user-notification-digest",
        )

    # Phase 76.2 — sticky reputation badges recomputed every 24h.
    user_badges_task: asyncio.Task[None] | None = None
    if not fast_test_lifespan:
        user_badges_task = asyncio.create_task(
            _user_badges_loop(app.state.session_factory, settings),
            name="user-badges",
        )

    #  MLflow Tracking subprocess.  Optional — only spawned
    # when ``settings.mlflow.enabled`` AND the optional ``mlflow``
    # package is installed (``pip install pointlessql[ml]``).  A
    # startup failure (port collision, missing dep, broken sqlite)
    # logs a warning and leaves ``app.state.mlflow_subprocess = None``
    # so the ``/mlflow/`` proxy can return a clear 503 instead of
    # bringing the entire PointlesSQL up-cycle down.
    app.state.mlflow_subprocess = None
    if settings.mlflow.enabled and mlflow_available():
        mlflow_proc = MLflowSubprocess(settings.mlflow, settings.soyuz.catalog_url)
        try:
            await mlflow_proc.start()
            app.state.mlflow_subprocess = mlflow_proc
        except MLflowStartupError as exc:
            logger.warning(
                "MLflow subprocess failed to start; /mlflow tab unavailable: %s",
                exc,
            )

    # dbt-docs subprocess.  Optional — only spawned when
    # ``settings.dbt.enabled`` is true, ``dbt-duckdb`` is installed
    # *and* the project has a compiled ``target/manifest.json``.  The
    # last condition keeps a fresh repo (no compiled project yet) from
    # logging a startup error: we just leave the subprocess unstarted
    # and let the ``/dbt`` page render a "compile first" hint.
    app.state.dbt_subprocess = None
    if settings.dbt.enabled and dbt_duckdb_available():
        dbt_proc = DBTSubprocess(settings.dbt)
        if dbt_proc.project_ready():
            try:
                await dbt_proc.start()
                app.state.dbt_subprocess = dbt_proc
            except DBTStartupError as exc:
                logger.warning(
                    "dbt-docs subprocess failed to start; /dbt tab unavailable: %s",
                    exc,
                )
        else:
            logger.info(
                "dbt-docs subprocess skipped: %s missing — run `dbt compile` first",
                dbt_proc.manifest_path,
            )

    # Phase 66.0 — the browser notebook editor is back.  Build a
    # process-global :class:`KernelRegistry` keyed by
    # ``(user_id, notebook_path)`` and attach it to ``app.state``
    # so the WebSocket handler in ``notebook_kernel_ws.py`` can
    # get-or-start a kernel session per editor connection.  The
    # registry's ``shutdown_all`` runs in the ``finally`` block to
    # graceful-stop every live kernel subprocess on app exit.
    notebooks_dir = settings.jupyter.notebooks_dir.resolve()
    notebooks_dir.mkdir(parents=True, exist_ok=True)
    app.state.kernel_registry = KernelRegistry(notebooks_dir=notebooks_dir)

    try:
        yield
    finally:
        await app.state.kernel_registry.shutdown_all()
        if app.state.mlflow_subprocess is not None:
            await app.state.mlflow_subprocess.stop()
        if app.state.dbt_subprocess is not None:
            await app.state.dbt_subprocess.stop()
        if audit_task is not None:
            audit_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await audit_task
        if external_writes_task is not None:
            external_writes_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await external_writes_task
        if cdf_tail_task is not None:
            cdf_tail_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await cdf_tail_task
        if data_product_freshness_task is not None:
            data_product_freshness_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await data_product_freshness_task
        if workspace_repos_task is not None:
            workspace_repos_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await workspace_repos_task
        if lineage_pruner_task is not None:
            lineage_pruner_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await lineage_pruner_task
        if branch_cleanup_task is not None:
            branch_cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await branch_cleanup_task
        if user_notification_digest_task is not None:
            user_notification_digest_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await user_notification_digest_task
        if user_badges_task is not None:
            user_badges_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await user_badges_task
        if data_product_trending_task is not None:
            data_product_trending_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await data_product_trending_task
        if data_product_promotion_task is not None:
            data_product_promotion_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await data_product_promotion_task
        if data_product_passport_task is not None:
            data_product_passport_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await data_product_passport_task
        if data_product_cooccurrence_task is not None:
            data_product_cooccurrence_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await data_product_cooccurrence_task
        if active_reviewer_task is not None:
            active_reviewer_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await active_reviewer_task
        if scheduler is not None:
            await scheduler.stop()
        if not fast_test_lifespan and app.state.uc_client is not None:
            await app.state.uc_client.aclose()




app = FastAPI(title="PointlesSQL", version="0.1.0", lifespan=_lifespan)

from pointlessql.api._bootstrap._routers import register_routers  # noqa: E402
from pointlessql.api.error_handlers import register_error_handlers  # noqa: E402

register_error_handlers(app)
register_routers(app)

_STYLE_CSS_PATH = _FRONTEND_DIR / "css" / "style.css"


_CSS_DIR = _FRONTEND_DIR / "css"
_ASSET_VERSION_RE = re.compile(r'url\("(\./[^"]+)\?v=ASSET_VERSION"\)')


@app.get("/static/css/style.css", include_in_schema=False)
async def _style_css() -> Response:  # pyright: ignore[reportUnusedFunction]
    """Serve the master stylesheet with per-import mtime cache-busters.

    Browsers cache ``@import`` URLs independently of their referring
    sheet, so the parent's cache-bust does not propagate.  Earlier the
    token expanded to ``pointlessql.__version__``; that meant dev
    iteration required a version bump to invalidate sub-imports.

    Instead we stamp each ``@import url("./foo.css?v=ASSET_VERSION")``
    with the imported file's own mtime.  In dev, editing a sub-sheet
    bumps its mtime → browser refetches that one file.  In prod the
    wheel's install-time mtime is stable → identical caching as
    before.  Files that are missing fall back to ``__version__``.
    """
    body = _STYLE_CSS_PATH.read_text()

    def _stamp(match: re.Match[str]) -> str:
        rel = match.group(1)
        target = (_CSS_DIR / rel.removeprefix("./")).resolve()
        try:
            mtime = int(target.stat().st_mtime)
            stamp = f"{pointlessql.__version__}-{mtime}"
        except OSError:
            stamp = pointlessql.__version__
        return f'url("{rel}?v={stamp}")'

    body = _ASSET_VERSION_RE.sub(_stamp, body)
    return Response(body, media_type="text/css")


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
    # reload — kernel + Pyright WebSockets get torn down mid-typing.  Pinning
    # reload_dirs to the source trees keeps autosave invisible to the watcher;
    # SQLite files (.db) and Delta tables (notebooks/, /tmp) stay outside
    # scope.
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
# Why:  needed an admin-side helper to mint an auditor-scoped
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


@cli.command("lens-mcp")
def _lens_mcp_cmd() -> None:  # pyright: ignore[reportUnusedFunction]
    """Run the Lens read-only Q&A MCP server on stdio (Phase 65.4).

    Reads ``LENS_API_KEY`` (an analyst-scoped api_keys secret) from
    the env, resolves it to a workspace, and exposes every Lens tool
    to the connected MCP client (Claude Desktop, Cursor, etc.).
    Blocks until stdin closes.
    """
    from pointlessql.services.lens.mcp_server import (
        LensMcpAuthError,
        run_lens_mcp_stdio,
    )

    try:
        run_lens_mcp_stdio()
    except LensMcpAuthError as exc:
        typer.echo(f"lens-mcp: {exc}", err=True)
        raise typer.Exit(code=2) from exc


@cli.command("audit-export")
def _audit_export_cmd(  # pyright: ignore[reportUnusedFunction]
    out: Path = typer.Option(
        ...,
        "--out",
        help="Destination path for the data file.  Sidecars go next to it.",
    ),
    fmt: str = typer.Option(
        "json",
        "--fmt",
        help="Output format: 'json' (default) or 'csv'.",
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        help="ISO-8601 cutoff (inclusive).  Omit for no lower bound.",
    ),
    until: str | None = typer.Option(
        None,
        "--until",
        help="ISO-8601 end (exclusive).  Omit for no upper bound.",
    ),
    action: str | None = typer.Option(
        None,
        "--action",
        help="Optional exact-match action filter.",
    ),
    actor: str | None = typer.Option(
        None,
        "--actor",
        help="Optional substring filter on user_email.",
    ),
    target: str | None = typer.Option(
        None,
        "--target",
        help="Optional substring filter on target.",
    ),
    db_url: str | None = typer.Option(
        None,
        "--db-url",
        help="SQLAlchemy URL override; defaults to POINTLESSQL_DB_URL.",
    ),
) -> None:
    """Export the audit log + tamper-evidence sidecars (Phase 75.1).

    Writes three mode-0600 files at ``--out``:

    * ``<out>`` — JSON array or CSV table.
    * ``<out>.sha256`` — sha256sum-compatible.
    * ``<out>.manifest.json`` — filters + count + tool version.

    Compliance buyers run ``sha256sum -c <out>.sha256`` to verify
    the data file wasn't tampered with after export, and match
    the manifest's ``entry_count`` + filter set against their
    expected scope.
    """
    from pointlessql.cli.audit_export import cli_entrypoint as audit_export_run

    if fmt not in ("json", "csv"):
        typer.echo(f"--fmt must be 'json' or 'csv' (got {fmt!r})", err=True)
        raise typer.Exit(code=2)
    code = audit_export_run(
        out=out,
        fmt=fmt,  # type: ignore[arg-type]
        since=since,
        until=until,
        action=action,
        actor=actor,
        target=target,
        db_url=db_url,
    )
    raise typer.Exit(code=code)


@cli.command("migrate-to-postgres")
def _migrate_to_postgres_cmd(  # pyright: ignore[reportUnusedFunction]
    source: str = typer.Option(
        ...,
        "--source",
        help="SQLAlchemy URL of the existing SQLite metadata DB.",
    ),
    target: str = typer.Option(
        ...,
        "--target",
        help="SQLAlchemy URL of the empty Postgres metadata DB.",
    ),
    batch_size: int = typer.Option(
        1000,
        "--batch-size",
        help="Rows per INSERT batch when streaming source rows.",
        min=1,
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Read source row counts but skip writes; exit cleanly.",
    ),
) -> None:
    """Bulk-copy a SQLite PointlesSQL deployment to Postgres.

    Refuses to overwrite a non-empty target.  Runs ``alembic
    upgrade head`` against the target first so the schema chain
    matches.  Streams source rows in ``--batch-size`` chunks,
    syncs PG sequences past the largest copied id, rebuilds the
    PG-side FTS index, and verifies row counts (with a sample-hash
    for tables ≥ 100 rows).
    """
    from pointlessql.cli import migrate_to_postgres as mtp

    code = mtp.cli_entrypoint(
        source_url=source,
        target_url=target,
        batch_size=batch_size,
        dry_run=dry_run,
    )
    if code != 0:
        raise typer.Exit(code=code)
