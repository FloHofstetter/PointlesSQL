"""FastAPI lifespan extracted from ``api/main.py``.

The 358-LOC lifespan body that used to inflate ``main.py`` past 1000
LOC moves here verbatim, behind a :func:`make_lifespan` factory that
binds the Jinja2 templates from ``main.py`` via closure.  This keeps
``main.py`` focused on app construction + routing while the
startup/teardown logic (16 background tasks, 2 subprocesses, the
kernel registry) lives next to the other ``_bootstrap`` helpers.

A teardown helper :func:`_cancel_task` collapses the 14× duplicated
``if X is not None: X.cancel(); with contextlib.suppress(…): await X``
ritual into one named function.

The lifespan still owns the ``POINTLESSQL_TEST_LIFESPAN_FAST=1`` short-
circuit that lets the test conftest pre-wire ``app.state`` without
re-running the full production startup path.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
from collections.abc import AsyncIterator, Callable
from contextlib import AbstractAsyncContextManager, asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.templating import Jinja2Templates

from pointlessql.api._bootstrap._loops import (
    _active_reviewer_loop,  # pyright: ignore[reportPrivateUsage]
    _api_key_lifecycle_sweep_loop,  # pyright: ignore[reportPrivateUsage]
    _api_key_usage_flush_loop,  # pyright: ignore[reportPrivateUsage]
    _api_key_usage_retention_loop,  # pyright: ignore[reportPrivateUsage]
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
from pointlessql.config import get_settings
from pointlessql.db import get_session_factory, init_db
from pointlessql.services import api_keys as api_keys_service
from pointlessql.services import scheduler as scheduler_service
from pointlessql.services.dbt import (
    DBTStartupError,
    DBTSubprocess,
    dbt_duckdb_available,
)
from pointlessql.services.hermes import (
    HermesInstanceManager,
    HermesStartupError,
    hermes_available,
)
from pointlessql.services.mlflow_subprocess import (
    MLflowStartupError,
    MLflowSubprocess,
    mlflow_available,
)
from pointlessql.services.notebook.kernel_session import KernelRegistry
from pointlessql.services.soyuz_client import make_soyuz_client
from pointlessql.services.unitycatalog import UnityCatalogClient

logger = logging.getLogger(__name__)


async def _cancel_task(task: asyncio.Task[None] | None) -> None:
    """Cancel + await *task* if it exists, swallowing ``CancelledError``.

    Collapses the 14× repeated cleanup ritual into one named helper —
    same semantics as the inline blocks the lifespan used to carry.
    """
    if task is None:
        return
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await task


def make_lifespan(
    templates: Jinja2Templates,
) -> Callable[[FastAPI], AbstractAsyncContextManager[None]]:
    """Build the lifespan context manager bound to *templates*.

    The Jinja2 templates instance lives at module scope in ``main.py``
    so it can be wired with filters + the TemplateResponse wrapper at
    import time.  We bind it into the lifespan via closure rather than
    inlining the Jinja2Templates construction here, to preserve the
    existing "filters/wrapper registered exactly once at import" shape.

    Args:
        templates: The pre-configured Jinja2Templates instance to
            attach to ``app.state.templates`` at startup.

    Returns:
        The ``@asynccontextmanager``-wrapped coroutine FastAPI uses as
        its lifespan.
    """

    @asynccontextmanager
    async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
        """Build shared app state and run the scheduler + audit retention loop."""
        settings = get_settings()
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
        app.state.templates = templates
        if not fast_test_lifespan or not hasattr(app.state, "session_factory"):
            engine = init_db(settings.db.url)
            app.state.engine = engine
            app.state.session_factory = get_session_factory()
        if not hasattr(app.state, "engine") or app.state.engine is None:
            # fast-test path: derive the engine from the pre-wired factory.
            with app.state.session_factory() as _session:
                app.state.engine = _session.get_bind()

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

        # PQL hook registry — left-shift policy / quota / schema-vers
        # enforcement to the read+write primitives so notebook, script
        # and agent callers can never bypass them.  All three
        # registrars are idempotent.
        if not fast_test_lifespan:
            from pointlessql.services.cost import register_cost_hooks
            from pointlessql.services.policy_as_code import register_cedar_hooks
            from pointlessql.services.schema_versioning import (
                register_schema_versioning_hooks,
            )

            register_cedar_hooks(app.state.session_factory)
            register_schema_versioning_hooks(app.state.session_factory)
            register_cost_hooks(app.state.session_factory)

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

        # periodic API-key lifecycle sweep.  Marks
        # expired keys (auto-quarantine if enabled) + emits one
        # expiry-warning audit row per key approaching its TTL.
        # Same opt-out as audit retention: not started under
        # ``fast_test_lifespan``.
        api_key_lifecycle_task: asyncio.Task[None] | None = None
        if not fast_test_lifespan:
            api_key_lifecycle_task = asyncio.create_task(
                _api_key_lifecycle_sweep_loop(app.state.session_factory, settings),
                name="api-key-lifecycle",
            )

        # periodic API-key usage flush + retention sweep.
        # Flush drains the in-process Counter every 30s by default;
        # retention prunes buckets older than 30d once per day.
        api_key_usage_flush_task: asyncio.Task[None] | None = None
        api_key_usage_retention_task: asyncio.Task[None] | None = None
        if not fast_test_lifespan:
            api_key_usage_flush_task = asyncio.create_task(
                _api_key_usage_flush_loop(app.state.session_factory, app.state, settings),
                name="api-key-usage-flush",
            )
            api_key_usage_retention_task = asyncio.create_task(
                _api_key_usage_retention_loop(app.state.session_factory, settings),
                name="api-key-usage-retention",
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

        # data-product freshness scanner.  Same opt-in
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

        # CDF tail worker — pull-modell complement to the push-modell.
        # Disabled by default (``interval_seconds == 0``); admins opt
        # in via ``POINTLESSQL_CDF_TAIL_INTERVAL_SECONDS`` after
        # registering one or more subscriptions.
        cdf_tail_task: asyncio.Task[None] | None = None
        if settings.cdf_tail.interval_seconds > 0 and not fast_test_lifespan:
            cdf_tail_task = asyncio.create_task(
                _cdf_tail_loop(app.state.session_factory, app.state.uc_client, settings),
                name="cdf-tail",
            )

        # workspace-repos sync cron.  Opt-in
        # default-disabled (``sync_interval_seconds == 0``).  When
        # active, the loop pulls every stale repo every interval; the
        # webhook receiver still triggers immediate syncs regardless.
        workspace_repos_task: asyncio.Task[None] | None = None
        if settings.workspace_repos.sync_interval_seconds > 0 and not fast_test_lifespan:
            workspace_repos_task = asyncio.create_task(
                _workspace_repos_sync_loop(app.state.session_factory, settings),
                name="workspace-repos-sync",
            )

        # Lineage retention pruner.  Runs as its own asyncio task
        # next to the audit-retention loop — the existing scheduler
        # is built around per-user JobExecutor callbacks that don't
        # fit a system-maintenance task without per-axis None
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

        # Branch auto-cleanup.  Opt-in default-disabled
        # (``branch.auto_cleanup_enabled=False``); the loop body
        # itself short-circuits when disabled, so we always start it
        # but it's a cheap no-op until the operator flips the flag.
        branch_cleanup_task: asyncio.Task[None] | None = None
        if not fast_test_lifespan:
            branch_cleanup_task = asyncio.create_task(
                _branch_cleanup_loop(app.state.uc_client, settings),
                name="branch-cleanup",
            )

        # cached "trending in agent workloads" refresh.
        # Opt-in default-disabled
        # (``trending_refresh_interval_seconds == 0``); the join
        # query stays cheap for < 10⁴ ops/week but adds noise on
        # quiet single-tenant installs.
        data_product_trending_task: asyncio.Task[None] | None = None
        if settings.data_products.trending_refresh_interval_seconds > 0 and not fast_test_lifespan:
            data_product_trending_task = asyncio.create_task(
                _data_product_trending_loop(app.state.session_factory, settings),
                name="data-product-trending",
            )

        # promote-to-DP candidate scanner.  Always
        # safe to schedule: the loop body short-circuits when
        # ``promote_enabled`` is false (default).
        data_product_promotion_task: asyncio.Task[None] | None = None
        if settings.data_products.promote_enabled and not fast_test_lifespan:
            data_product_promotion_task = asyncio.create_task(
                _data_product_promotion_loop(app.state.session_factory, settings),
                name="data-product-promotion",
            )

        # auto-passport stale-refresh loop.  Opt-in
        # via ``passport_loop_enabled`` (default off).
        data_product_passport_task: asyncio.Task[None] | None = None
        if settings.data_products.passport_loop_enabled and not fast_test_lifespan:
            data_product_passport_task = asyncio.create_task(
                _data_product_passport_loop(app.state.session_factory, settings),
                name="data-product-passport",
            )

        # cross-DP cooccurrence cache refresh.  Opt-in.
        data_product_cooccurrence_task: asyncio.Task[None] | None = None
        if settings.data_products.cooccurrence_enabled and not fast_test_lifespan:
            data_product_cooccurrence_task = asyncio.create_task(
                _data_product_cooccurrence_loop(app.state.session_factory, settings),
                name="data-product-cooccurrence",
            )

        # active-reviewer daily tick.  Opt-in
        # default-disabled (``data_products.active_reviewer_enabled``);
        # the loop body short-circuits when disabled, so registering
        # it is cheap.
        active_reviewer_task: asyncio.Task[None] | None = None
        if settings.data_products.active_reviewer_enabled and not fast_test_lifespan:
            active_reviewer_task = asyncio.create_task(
                _active_reviewer_loop(app.state.session_factory, settings),
                name="active-reviewer",
            )

        # daily marketplace digest.
        # Opt-in default-disabled
        # (``notifications.digest_enabled=False``); the loop body
        # itself short-circuits when disabled, so we always start
        # it but it's a cheap no-op until the operator flips the
        # flag.
        user_notification_digest_task: asyncio.Task[None] | None = None
        if not fast_test_lifespan:
            user_notification_digest_task = asyncio.create_task(
                _user_notification_digest_loop(app.state.session_factory, settings),
                name="user-notification-digest",
            )

        # sticky reputation badges recomputed every 24h.
        user_badges_task: asyncio.Task[None] | None = None
        if not fast_test_lifespan:
            user_badges_task = asyncio.create_task(
                _user_badges_loop(app.state.session_factory, settings),
                name="user-badges",
            )

        # MLflow Tracking subprocess.  Optional — only spawned when
        # ``settings.mlflow.enabled`` AND the optional ``mlflow``
        # package is installed (``pip install pointlessql[ml]``).  A
        # startup failure (port collision, missing dep, broken sqlite)
        # logs a warning and leaves ``app.state.mlflow_subprocess =
        # None`` so the ``/mlflow/`` proxy can return a clear 503
        # instead of bringing the entire PointlesSQL up-cycle down.
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
        # *and* the project has a compiled ``target/manifest.json``.
        # The last condition keeps a fresh repo (no compiled project
        # yet) from logging a startup error: we just leave the
        # subprocess unstarted and let the ``/dbt`` page render a
        # "compile first" hint.
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

        # Hermes agent dashboard.  The manager always exists (so the
        # ``/hermes`` proxy can answer), but it only spawns a child
        # process in managed mode.  A managed launch needs the
        # ``hermes`` CLI on PATH; when it is missing or the spawn
        # fails we log a warning and leave the manager with no running
        # instance so the Agent tab degrades to a clear message instead
        # of bringing the whole start-up down.  External mode reaches a
        # Hermes someone else runs and never spawns anything here.
        app.state.hermes_manager = None
        if settings.hermes.enabled:
            hermes_manager = HermesInstanceManager(settings.hermes)
            app.state.hermes_manager = hermes_manager
            if (
                hermes_manager.is_managed
                and not fast_test_lifespan
                and hermes_available(settings.hermes.command)
            ):
                try:
                    await hermes_manager.start_shared()
                except HermesStartupError as exc:
                    logger.warning(
                        "Hermes dashboard failed to start; /agent tab unavailable: %s",
                        exc,
                    )
            elif hermes_manager.is_managed and not fast_test_lifespan:
                logger.warning(
                    "Hermes managed mode enabled but the %r launcher is not on PATH; "
                    "/agent tab unavailable until it is installed or external mode is set",
                    settings.hermes.command,
                )

        # Browser notebook editor.  Build a process-global
        # :class:`KernelRegistry` keyed by ``(user_id, notebook_path)``
        # and attach it to ``app.state`` so the WebSocket handler in
        # ``notebook_kernel_ws.py`` can get-or-start a kernel session
        # per editor connection.  The registry's ``shutdown_all`` runs
        # in the ``finally`` block to graceful-stop every live kernel
        # subprocess on app exit.
        notebooks_dir = settings.jupyter.notebooks_dir.resolve()
        notebooks_dir.mkdir(parents=True, exist_ok=True)
        app.state.kernel_registry = KernelRegistry(notebooks_dir=notebooks_dir)

        # cross-worker co-edit fanout bus.  Opt-in
        # (``coedit.bus_enabled``) and PG-only — SQLite installs stay
        # single-worker and skip the bus entirely.  The bus owns its own
        # async PG connection for ``LISTEN coedit_bus`` plus a cleanup
        # loop that sweeps expired outbox rows; both are started here
        # and drained in the ``finally`` block below.  Hub instrumentation
        # in ``notebook_coedit_ws`` consults ``app.state.coedit_bus``
        # before publishing.
        app.state.coedit_bus = None
        coedit_bus: Any = None
        if settings.coedit.bus_enabled and not fast_test_lifespan:
            from sqlalchemy.engine import Engine as _Engine

            engine_any = app.state.engine
            if isinstance(engine_any, _Engine) and engine_any.dialect.name == "postgresql":
                from pointlessql.services.notebook.coedit_bus import CoeditBus

                coedit_bus = CoeditBus(
                    engine_any,
                    ttl_seconds=settings.coedit.bus_message_ttl_seconds,
                    cleanup_interval_seconds=(settings.coedit.bus_cleanup_interval_seconds),
                )
                # Wire the dispatch callback BEFORE start() so the
                # first inbound NOTIFY can already fan out into a hub.
                from pointlessql.api.notebook_coedit_ws import (
                    apply_remote_bus_frame,
                    bind_coedit_bus,
                )

                coedit_bus.set_dispatch_callback(apply_remote_bus_frame)
                await coedit_bus.start()
                bind_coedit_bus(coedit_bus)
                app.state.coedit_bus = coedit_bus
            else:
                logger.info(
                    "coedit-bus: enabled but engine is not Postgres; single-worker only — skipping",
                )

        # notebook replay re-execution worker.
        # Tiny serial loop next to the scheduler that drains pending
        # NotebookReplay rows.  Disabled in fast-test lifespan so
        # pytest stays deterministic; opt-out via
        # ``POINTLESSQL_REPLAY_WORKER_DISABLED=1`` for ops who don't
        # want it running on production (e.g. CI installs that won't
        # ever replay).
        replay_worker: Any = None
        if not fast_test_lifespan and os.environ.get("POINTLESSQL_REPLAY_WORKER_DISABLED") != "1":
            from pointlessql.services.notebook.replay_worker import (
                ReplayWorker as _ReplayWorker,
            )

            replay_worker = _ReplayWorker(
                session_factory=app.state.session_factory,
                notebooks_dir=notebooks_dir,
            )
            replay_worker.start()
        app.state.replay_worker = replay_worker

        try:
            yield
        finally:
            if replay_worker is not None:
                await replay_worker.stop()
            if coedit_bus is not None:
                from pointlessql.api.notebook_coedit_ws import bind_coedit_bus

                bind_coedit_bus(None)
                await coedit_bus.stop()
            await app.state.kernel_registry.shutdown_all()
            if app.state.mlflow_subprocess is not None:
                await app.state.mlflow_subprocess.stop()
            if app.state.dbt_subprocess is not None:
                await app.state.dbt_subprocess.stop()
            if getattr(app.state, "hermes_manager", None) is not None:
                await app.state.hermes_manager.stop_all()
            await _cancel_task(audit_task)
            await _cancel_task(api_key_lifecycle_task)
            await _cancel_task(api_key_usage_flush_task)
            await _cancel_task(api_key_usage_retention_task)
            await _cancel_task(external_writes_task)
            await _cancel_task(cdf_tail_task)
            await _cancel_task(data_product_freshness_task)
            await _cancel_task(workspace_repos_task)
            await _cancel_task(lineage_pruner_task)
            await _cancel_task(branch_cleanup_task)
            await _cancel_task(user_notification_digest_task)
            await _cancel_task(user_badges_task)
            await _cancel_task(data_product_trending_task)
            await _cancel_task(data_product_promotion_task)
            await _cancel_task(data_product_passport_task)
            await _cancel_task(data_product_cooccurrence_task)
            await _cancel_task(active_reviewer_task)
            if scheduler is not None:
                await scheduler.stop()
            if not fast_test_lifespan and app.state.uc_client is not None:
                await app.state.uc_client.aclose()

    return _lifespan
