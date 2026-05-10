"""FastAPI entrypoint for PointlesSQL."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
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
from markdown_it import MarkdownIt

import pointlessql
from pointlessql.api.admin import router as admin_router
from pointlessql.api.agent_reviews_routes import router as agent_reviews_router
from pointlessql.api.agent_runs_routes import router as agent_runs_router
from pointlessql.api.alerts_routes import router as alerts_router
from pointlessql.api.audit import router as audit_router
from pointlessql.api.auth_routes import router as auth_router
from pointlessql.api.branches_routes import router as branches_router
from pointlessql.api.catalog_html_routes import router as catalog_html_router
from pointlessql.api.catalog_routes import router as catalog_router
from pointlessql.api.conventions_routes import router as conventions_router
from pointlessql.api.dashboards_routes import router as dashboards_router
from pointlessql.api.data_products_html_routes import (
    router as data_products_html_router,
)
from pointlessql.api.data_products_routes import router as data_products_router
from pointlessql.api.dbt import router as dbt_router
from pointlessql.api.dependencies import (
    require_admin as _require_admin,
)
from pointlessql.api.federation_routes import router as federation_router
from pointlessql.api.governance_routes import router as governance_router
from pointlessql.api.home_routes import router as home_router
from pointlessql.api.jobs_routes import (
    router as jobs_router,
)
from pointlessql.api.lineage import router as lineage_router
from pointlessql.api.middleware import register_middleware
from pointlessql.api.ml_routes import router as ml_router
from pointlessql.api.mlflow_html_routes import router as mlflow_html_router
from pointlessql.api.mlflow_proxy import router as mlflow_proxy_router
from pointlessql.api.models_html_routes import router as models_html_router
from pointlessql.api.models_routes import router as models_router
from pointlessql.api.notebooks_routes import router as notebooks_router
from pointlessql.api.pql_introspect_routes import router as pql_introspect_router
from pointlessql.api.pql_training_routes import router as pql_training_router
from pointlessql.api.review_destinations_routes import router as review_destinations_router
from pointlessql.api.runs_routes import router as runs_router
from pointlessql.api.saved_audit_queries_routes import (
    router as saved_audit_queries_router,
)
from pointlessql.api.sql import router as sql_router
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
from pointlessql.api.webhook_routes import router as webhook_router
from pointlessql.config import Settings, configure_logging
from pointlessql.db import get_session_factory, init_db
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import audit as audit_service
from pointlessql.services import metrics as metrics_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.dbt_subprocess import (
    DBTStartupError,
    DBTSubprocess,
    dbt_duckdb_available,
)
from pointlessql.services.mlflow_subprocess import (
    MLflowStartupError,
    MLflowSubprocess,
    mlflow_available,
)
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient
from pointlessql.web import get_help as _get_help
from pointlessql.web import status_class as _status_class

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


def _format_epoch_ms(value: Any) -> str:
    """Format Unity Catalog epoch-millisecond timestamps as a local datetime."""
    if value is None:
        return "—"
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=UTC).strftime("%Y-%m-%d %H:%M UTC")
    except (TypeError, ValueError):
        return str(value)


def _format_uuid(value: Any) -> str:
    """Normalise UUID strings to canonical hyphenated form.

    PointlesSQL's API mixes hyphenated and packed UUID formats depending
    on the source row (some seeds, some FK inserts, some agent-emitted
    payloads). Templates use this filter so the user always sees the
    same shape regardless of source.
    """
    if not value:
        return ""
    s = str(value).replace("-", "")
    if len(s) != 32:
        return str(value)
    return f"{s[0:8]}-{s[8:12]}-{s[12:16]}-{s[16:20]}-{s[20:32]}"


def _format_hash(value: Any, sentinel_label: str = "(no source captured)") -> str:
    """Hide the all-zeros SHA sentinel as a human-readable label.

    Run-source capture writes ``"0" * 64`` when no bytes were captured
    (e.g. agent-only flows that never hit ``capture_run_source``). The
    raw zero-hash leaks an implementation detail; this filter swaps it
    for a readable empty-state. Real hashes pass through unchanged.
    """
    if not value:
        return ""
    s = str(value)
    if s and all(c == "0" for c in s):
        return sentinel_label
    return s


_MARKDOWN_RENDERER = MarkdownIt("commonmark", {"html": False, "linkify": True}).enable(
    ["table"]
)


def _render_markdown(value: Any) -> str:
    """Render saved-query Markdown descriptions to an HTML fragment.

    Uses markdown-it-py in CommonMark mode with ``html: false`` so any
    raw ``<script>`` / ``<iframe>`` in user input is escaped at parse
    time — descriptions are user-authored, so ``|safe`` would expose
    us to script injection without this guard.
    """
    if not value:
        return ""
    return _MARKDOWN_RENDERER.render(str(value))


_TEMPLATES.env.filters["epoch_ms"] = _format_epoch_ms
_TEMPLATES.env.filters["format_uuid"] = _format_uuid
_TEMPLATES.env.filters["format_hash"] = _format_hash
_TEMPLATES.env.filters["render_markdown"] = _render_markdown

# contextual help-popover registry (see ``pointlessql/web/
# help.py``).  Templates resolve slugs via ``{{ help('runs.what-is-a-
# run') }}`` and render through ``_macros/help_icon.html``.  Registering
# the global once here means every template — including ones rendered
# in tests via ``TestClient`` — can call it without a per-route hook.
_TEMPLATES.env.globals["help"] = _get_help  # pyright: ignore[reportArgumentType]

# Asset cache-bust token.  Bumps automatically with every release;
# templates use ``?v={{ asset_version }}`` instead of hand-edited
# per-edit strings.
_TEMPLATES.env.globals["asset_version"] = pointlessql.__version__  # pyright: ignore[reportArgumentType]

# Centralised status → Bootstrap badge class mapping.  Templates
# call ``{{ status_class(run.status) }}`` instead of hand-rolling
# {% if status == 'succeeded' %}bg-success{% elif … %} ladders.
_TEMPLATES.env.globals["status_class"] = _status_class  # pyright: ignore[reportArgumentType]


def _paginate_url(base_url: str, query_params: Any, offset: int) -> str:
    """Return ``base_url`` plus ``query_params`` with ``offset`` overridden.

    Used by ``frontend/templates/_macros/pagination.html`` to build
    page-link hrefs without losing in-flight filter chips.

    Args:
        base_url: Path the page is served from (e.g. ``request.url.path``).
        query_params: Starlette ``QueryParams`` (or any iterable of
            ``(key, value)``).  Pre-existing ``offset`` keys are dropped.
        offset: New offset value.

    Returns:
        ``"path?offset=N&filter=foo"`` style URL.
    """
    from urllib.parse import urlencode

    items: list[tuple[str, str]] = []
    if query_params is not None:
        if hasattr(query_params, "multi_items"):
            iterator = query_params.multi_items()
        else:
            iterator = list(query_params)
        for key, val in iterator:
            if key == "offset":
                continue
            items.append((str(key), str(val)))
    items.append(("offset", str(offset)))
    return f"{base_url}?{urlencode(items)}"


_TEMPLATES.env.globals["paginate_url"] = _paginate_url  # pyright: ignore[reportArgumentType]


_original_template_response = _TEMPLATES.TemplateResponse


def _resolve_workspace_context(request: Request) -> dict[str, Any]:
    """Build the workspace-scoped Jinja context for one TemplateResponse call.

    Returns a dict with ``current_workspace``, ``available_workspaces``
    (the list rendered by the topbar switcher), and
    ``current_workspace_primary_catalog`` (used by the catalog tree
    to pre-expand on first load).  Every lookup is wrapped in a
    try/except so a transient DB failure during template render
    falls back to a blank context rather than 500ing the whole
    page.
    """
    factory = getattr(request.app.state, "session_factory", None)
    workspace_id = getattr(request.state, "workspace_id", None)
    user = getattr(request.state, "user", None)
    if factory is None or workspace_id is None:
        return {
            "current_workspace": None,
            "available_workspaces": [],
            "current_workspace_primary_catalog": None,
        }
    try:
        from sqlalchemy import select as _select

        from pointlessql.models import Workspace, WorkspaceCatalogPin
        from pointlessql.services import workspaces as ws_service

        with factory() as session:
            current = session.get(Workspace, workspace_id)
            primary_pin = None
            if current is not None:
                primary_pin = session.scalar(
                    _select(WorkspaceCatalogPin).where(
                        WorkspaceCatalogPin.workspace_id == current.id,
                        WorkspaceCatalogPin.mode == "primary",
                    )
                )
            if current is not None:
                session.expunge(current)

        available: list[Any] = []
        if user is not None and isinstance(user.get("id"), int) and user["id"] > 0:
            available = ws_service.list_workspaces_for_user(factory, user_id=int(user["id"]))

        return {
            "current_workspace": current,
            "available_workspaces": available,
            "current_workspace_primary_catalog": (
                primary_pin.catalog_name if primary_pin is not None else None
            ),
        }
    except Exception:  # noqa: BLE001 — template render must not 500 on a workspace-lookup hiccup
        logger.debug("Failed to resolve workspace context for template", exc_info=True)
        return {
            "current_workspace": None,
            "available_workspaces": [],
            "current_workspace_primary_catalog": None,
        }


def _template_response_with_user(request: Request, *args: Any, **kwargs: Any) -> Response:
    """Wrap TemplateResponse to inject user + workspace context."""
    # TemplateResponse(request, name, context) or (name, context, request=request)
    # Starlette 0.37+ signature: TemplateResponse(request, name, context={}, ...)
    workspace_ctx = _resolve_workspace_context(request)
    user = getattr(request.state, "user", None)
    if "context" in kwargs:
        ctx = kwargs["context"]
        ctx.setdefault("current_user", user)
        for key, value in workspace_ctx.items():
            ctx.setdefault(key, value)
    elif len(args) >= 2 and isinstance(args[1], dict):
        mutable = list(args)
        ctx = mutable[1]
        ctx.setdefault("current_user", user)
        for key, value in workspace_ctx.items():
            ctx.setdefault(key, value)
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

    # The browser notebook editor was retired; a future
    # :class:`KernelRegistry` on ``app.state`` will serve as the
    # execution backend for the ``agent_run`` scheduler kind.
    # Nothing else to start here yet.
    try:
        yield
    finally:
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
        if scheduler is not None:
            await scheduler.stop()
        if not fast_test_lifespan and app.state.uc_client is not None:
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


async def _data_product_freshness_loop(
    factory: Any,
    uc: Any,
    settings: Settings,
) -> None:
    """Periodic SLA scan across cached data products.

    Active only when
    ``POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS`` is explicitly
    non-zero — same opt-in discipline as the external-write scanner.
    Per tick, walks every :class:`DataProduct` row whose
    ``sla_minutes`` is set, observes the latest write timestamp via
    ``DeltaTable.history()``, and emits a
    ``pointlessql.data_product.sla_violated`` CloudEvent when the age
    exceeds the SLA.  ``last_alerted_at`` suppresses re-alerts within
    ``re_alert_suppress_minutes``.

    Args:
        factory: SQLAlchemy session factory shared with the rest of
            the app.
        uc: ``UnityCatalogClient`` used to enumerate the product's
            tables (storage locations).
        settings: Snapshotted :class:`Settings` — only
            ``data_products.scan_interval_seconds`` and
            ``data_products.re_alert_suppress_minutes`` are read.
    """
    from pointlessql.services import data_product_freshness_scanner

    interval = max(60, settings.data_products.scan_interval_seconds)
    suppress = settings.data_products.re_alert_suppress_minutes
    while True:
        try:
            emitted = await data_product_freshness_scanner.scan_all(
                factory,
                uc,
                re_alert_suppress_minutes=suppress,
            )
            if emitted:
                logger.info(
                    "data_product_freshness: tick emitted %d sla_violated event(s)",
                    emitted,
                )
        except Exception:  # noqa: BLE001 — scanner loop must survive everything
            logger.exception("data_product_freshness: scan tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _cdf_tail_loop(
    factory: Any,
    uc: Any,
    settings: Settings,
) -> None:
    """Periodic CDF tail across active subscriptions.

    Active only when
    ``POINTLESSQL_CDF_TAIL_INTERVAL_SECONDS`` is explicitly non-zero
    AND at least one :class:`CdfTailSubscription` row has
    ``is_active=True``.  Same opt-in discipline as the external-write
    scanner: zero-config installs see no extra Delta IO.

    Args:
        factory: SQLAlchemy session factory shared with the rest of
            the app.
        uc: ``UnityCatalogClient`` used to resolve each
            subscription's ``storage_location`` per tick.
        settings: Snapshotted :class:`Settings` — only
            ``cdf_tail.interval_seconds`` and
            ``cdf_tail.history_limit`` are read.
    """
    from pointlessql.services import cdf_tail

    interval = max(60, settings.cdf_tail.interval_seconds)
    history_limit = settings.cdf_tail.history_limit
    while True:
        try:
            inserted = await cdf_tail.tail_all(factory, uc, history_limit=history_limit)
            if inserted:
                logger.info("cdf_tail: tick recorded %d new event(s)", inserted)
        except Exception:  # noqa: BLE001 — tail loop must survive everything
            logger.exception("cdf_tail: tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _lineage_pruner_loop(
    factory: Any,
    settings: Settings,
) -> None:
    """Periodic prune of the four lineage tables.

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


async def _workspace_repos_sync_loop(
    factory: Any,
    settings: Settings,
) -> None:
    """Periodic workspace-repo sync (Phase 51.4).

    Active only when
    ``POINTLESSQL_REPOS_SYNC_INTERVAL_SECONDS`` is non-zero — same
    opt-in discipline as every other Phase-13.x+ scanner.  Each
    tick lists the repos whose ``last_synced_at`` is older than
    the configured cadence (or ``NULL``) and pulls them
    sequentially.  Per-repo failures are recorded on the row
    itself; the loop never aborts because of a single bad upstream.

    Args:
        factory: SQLAlchemy session factory shared with the rest of
            the app.
        settings: Snapshotted :class:`Settings` — only
            ``workspace_repos.*`` is read.
    """
    from datetime import UTC, datetime, timedelta

    from pointlessql.services.workspace_repos import (
        build_post_pull_loader_hook,
        list_repos_due_for_sync,
        sync_repo,
    )

    interval = max(60, settings.workspace_repos.sync_interval_seconds)
    base_dir = settings.workspace_repos.base_dir
    hook = build_post_pull_loader_hook(factory, settings=settings)
    while True:
        try:
            cutoff = datetime.now(UTC) - timedelta(seconds=interval)
            for repo in list_repos_due_for_sync(factory, cutoff=cutoff):
                try:
                    await sync_repo(
                        factory,
                        repo_id=repo.id,
                        base_dir=base_dir,
                        trigger="cron",
                        actor_user_id=None,
                        on_post_pull=hook,
                    )
                except Exception:  # noqa: BLE001 — per-repo failure isolation
                    # bare-broad-ok: sync persists the failure on the row;
                    # the loop must continue to the next repo regardless.
                    logger.exception("workspace_repos: cron sync of %s raised", repo.id)
        except Exception:  # noqa: BLE001 — outer-loop guard
            # bare-broad-ok: never let an unforeseen error kill the loop.
            logger.exception("workspace_repos: cron tick raised")
        try:
            await asyncio.sleep(interval)
        except asyncio.CancelledError:
            return


async def _branch_cleanup_loop(
    uc: Any,
    settings: Settings,
) -> None:
    """Periodic  branch auto-cleanup pass.

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
app.include_router(pql_training_router)
app.include_router(federation_router)
app.include_router(jobs_router)
app.include_router(dashboards_router)
app.include_router(home_router)
app.include_router(admin_router)
app.include_router(review_destinations_router)
app.include_router(ml_router)
app.include_router(mlflow_html_router)
app.include_router(mlflow_proxy_router)
app.include_router(dbt_router)
app.include_router(models_router)
app.include_router(models_html_router)
app.include_router(data_products_router)
app.include_router(data_products_html_router)
app.include_router(webhook_router)
_STYLE_CSS_PATH = _FRONTEND_DIR / "css" / "style.css"


@app.get("/static/css/style.css", include_in_schema=False)
async def _style_css() -> Response:  # pyright: ignore[reportUnusedFunction]
    """Serve the master stylesheet with the cache-bust token rewritten to ``__version__``.

    Browsers cache ``@import`` URLs independently of their referring
    sheet, so the parent's cache-bust does not propagate.  Rewriting
    on the fly lets a single ``__version__`` bump invalidate every
    imported sub-sheet at once without a build step.
    """
    body = _STYLE_CSS_PATH.read_text().replace(
        "?v=ASSET_VERSION",
        f"?v={pointlessql.__version__}",
    )
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
