# Roadmap

Single source of truth for *what is done*, *what is in progress*, and
*what is next* in PointlesSQL. Read this before starting work so you
pick up where the previous session left off.

The phases below break the project down into milestones (`M0`) and
sprints (`Sprint N`). When a sprint lands, flip it to ✅ and append
the short commit hash. When the scope of a planned sprint becomes
clearer, expand its bullet list in place — do not create a separate
planning document. This mirrors the roadmap discipline established
in [`soyuz-catalog/ROADMAP.md`](../soyuz-catalog/ROADMAP.md).

Older closed phases that are no longer load-bearing for follow-up
conversations are *collapsed*: a one-line summary stays in this
file (in tabular form), and the full per-sprint detail moves to
[`ROADMAP_ARCHIVE.md`](ROADMAP_ARCHIVE.md).  See "How to update
this file" at the bottom for the collapse trigger.  Phase numbers
are preserved across the collapse so cross-references in
`CHANGELOG.md`, memory entries, and commit messages remain valid.

Status legend: ✅ done · 🔜 next · ⏳ planned · 🧊 on ice

## Current state

```text
PointlesSQL
│
├── Phases 0–12.8 — completed, collapsed                  ✅ done
│   │
│   │   Full per-sprint detail moved to
│   │   [`ROADMAP_ARCHIVE.md`](ROADMAP_ARCHIVE.md) for scannability.
│   │   Summary below.  Git history of `ROADMAP.md` preserves the
│   │   pre-collapse state if anyone needs to bisect a decision.
│   │
│   │   ```
│   │   Phase  Closed       Sprint range  What shipped
│   │   ─────  ───────────  ────────────  ─────────────────────────────────────
│   │     0    2026-01      M0–M1         Repo skeleton, hand-rolled httpx UC client, catalog browser prototype
│   │     1    2026-02      S1–S4         MVP: catalog UI + Notebook tab + pql Pandas/Delta helper
│   │     2    2026-02      S5            Catalog UI cards: tags, permissions, lineage, federation
│   │     3    2026-02      S6–S8         Auth: login, JWT sessions, grant enforcement (PointlesSQL = enforcement layer)
│   │     4    2026-03      S9–S10        `docker compose up` packaging, soyuz-client wheel, single-image flow
│   │     5    2026-03      S11–S12       Pluggable compute engines (DuckDB + Polars alongside Pandas)
│   │     5.5  2026-03      S13–S15       Quality pass: strict pyright, exception hierarchy, structured logs
│   │     6    2026-03      S16–S20       Foreign Postgres mirror, scheduler/jobs, cron mgmt UI
│   │     7    2026-03      S21–S22       Playwright-MCP live UI walkthroughs (every HTML route exercised)
│   │     8    2026-03      S23–S30       Notebook-as-job: Papermill execution, schedule, params, output
│   │     9    2026-03      S31–S40       UX overhaul: nav, search, toasts, breadcrumbs, dark mode, empty states
│   │    10    2026-03      S41–S43       Private GHCR + git-tag pinning, dual-auth Dockerfile
│   │    11    2026-03      S44–S47       CSRF, rate-limiting, JWT key rotation, in-app audit viewer, OIDC
│   │    12    2026-04      S48–S53       SQL editor (CodeMirror) + query history + audit-log hardening
│   │    12.5  2026-04      S54–S57       Charts, alerts (HMAC/CloudEvents/Atom/JSON-Feed), column stats, UC Volumes
│   │    12.6  2026-04      S58–S64       Native Monaco notebook editor (replaces JupyterLab iframe)
│   │    12.7  2026-04      S65–S80       Notebook editor UX overhaul (variable explorer, Marimo-grade)
│   │    12.8  2026-04      S81–S86       Frontend cleanup: ESM modules, CSS split, `pqlApi.fetch` CSRF wrapper
│   │   ```
│   │
│
├── Phase 12.9 — LLM-friendly modularization (full-stack carve-up)  🔜 in progress
│   │
│   │   Follow-up to Phase 12.8.  The Sprint-75 carve-up brought
│   │   notebook/main.js from 1547 → 1204 LOC but the file was still
│   │   the single largest module in the frontend.  Phase 12.9 targets
│   │   aggressive modularization for LLM-friendliness: small,
│   │   single-purpose modules so an agent editing one concern doesn't
│   │   load the whole orchestrator into context.  Sprint 76 closed the
│   │   first frontend tranche; Sprint 77+ extends the work backend-side
│   │   (api/main.py 6.6k LOC, scheduler.py 1.8k LOC, models.py, every
│   │   service file >400 LOC) and finishes Tranches 2-6 of the
│   │   original frontend plan.  19-sprint plan documented in
│   │   [.claude/plans/ich-m-chte-eine-weitere-precious-goose.md](/home/flo/.claude/plans/ich-m-chte-eine-weitere-precious-goose.md).
│   │
│   └── Sprint 76 — notebook/main.js → 4 sub-modules + toast helper   ✅ done (pending-commit)
│       Four sibling modules carved out of main.js + a cross-cutting
│       toast-guard cleanup.  No behaviour change, no Alembic, no
│       template-structure change; pure JS refactor.
│
│       **Extracted modules:**
│       - [kernel_ws.js](frontend/js/notebook/kernel_ws.js) (211 LOC)
│         — ipykernel WebSocket factory: socket handle, namespace-
│         introspect buffer, frame routing (hello/ack/interrupted/
│         restarted/error/kernel_msg), cell-affordance status pill
│         updates.
│       - [lsp_ws.js](frontend/js/notebook/lsp_ws.js) (133 LOC) —
│         pyright LSP WebSocket factory: socket handle, PyrightClient
│         instance, document URI + monotonic version, didOpen +
│         publishDiagnostics wiring, notifyDidChange.
│       - [cell_scanner.js](frontend/js/notebook/cell_scanner.js)
│         (41 LOC) — pure ``scanCellRanges(model)`` +
│         ``rangesToDecorations(monaco, ranges)``.  No closure state.
│       - [cell_editor.js](frontend/js/notebook/cell_editor.js)
│         (104 LOC) — cell-mutation ops: insertCellAfter,
│         addCellBelow, addCellAbove, applyResultVarToMarker.  Pure
│         wrt alpine state; closure-scoped over ``refs`` +
│         ``rescanDecorations`` only.
│
│       **main.js: 1204 → 703 LOC** (-501).  Now owns orchestration
│       glue + rebuildCellAffordances + save + catalog-insert only.
│
│       **Cross-cutting cleanup (Tranche 7):**
│       - [api.js](frontend/js/api.js) now exports ``toast(variant, msg)``
│         and ``csrfToken()`` as named exports.  14 ``if
│         (window.pqlToast) window.pqlToast.X(msg)`` guards in
│         [sql_editor.js](frontend/js/sql_editor.js),
│         [notebook/main.js](frontend/js/notebook/main.js), and
│         [notebook/editor_shell.js](frontend/js/notebook/editor_shell.js)
│         replaced with single-line ``toast('error', msg)`` calls.
│       - Duplicate ``csrfToken()`` removed from notebook/main.js,
│         now imported from api.js.
│
│       **Deferred to a follow-up sprint:** ``mount_bootstrap.js``
│       split (mount() is tightly coupled to ``this`` + the Alpine
│       factory return object; extracting it means refactoring the
│       factory shape, not a mechanical move — too risky for this
│       sprint).  Captured in the tranche plan.
│
│       **Static gates (all green):** ``ruff``, ``pyright`` (0
│       errors, 153 warnings unchanged),
│       [check-frontend-bootstrap-order.sh](scripts/check-frontend-bootstrap-order.sh),
│       [check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh),
│       ``node --check`` on every modified JS file, import-graph
│       resolution check, Jinja template parse.  Cache-bust
│       ``?v=sprint76`` applied to
│       [notebook_editor.html](frontend/templates/pages/notebook_editor.html).
│       No Playwright replay — changes are mechanical (closure state
│       moved into factory-pattern sub-modules, direct ref-passing
│       replaces sendKernelFrame/sendLspFrame closures); the first
│       Phase 12.9 sprint that touches x-data/template structure
│       will carry a playbook replay.
│
│   ├── Sprint 77 — services/kernel_session.py → 3 sub-modules    ✅ done (54a6436)
│       Pilot of the backend modularization arc (Sprints 77-90).
│       Smallest isolated split (471 LOC, one external caller) —
│       validates the package + ``__init__.py`` re-export recipe
│       before applying the same pattern to ``models.py``,
│       ``scheduler.py``, and ``api/main.py``.
│
│       **Package** ``pointlessql/services/kernel_session/``
│       replaces the single 472-LOC module:
│       - ``messages.py`` (61 LOC) — :class:`KernelMessage`,
│         :class:`Subscription` (renamed from ``_Subscription`` —
│         the leading underscore conveyed file-private scope and is
│         no longer accurate now that :class:`KernelSession` imports
│         it across modules; pyright ``reportPrivateUsage`` flagged
│         this immediately).
│       - ``session.py`` (337 LOC) — :class:`KernelSession`
│         lifecycle + ZMQ pump tasks + bootstrap code +
│         ``_KERNEL_READY_TIMEOUT``/``_SHUTDOWN_TIMEOUT``/
│         ``_BOOTSTRAP_TIMEOUT`` constants.
│       - ``registry.py`` (94 LOC) — :class:`KernelRegistry` +
│         :func:`drain` helper.
│       - ``__init__.py`` (38 LOC) — re-exports the full public
│         surface so ``from pointlessql.services import
│         kernel_session as kernel_session_service`` in
│         [pointlessql/api/main.py:45](pointlessql/api/main.py#L45)
│         continues to resolve every symbol unchanged.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 5 warnings (all from jupyter_client's
│       partially-unknown async types — pre-existing), ``pydoclint``
│       0 violations, smoke import via
│       ``python -c "from pointlessql.services import kernel_session"``.
│       No tests directly import this module; no Alembic, no
│       template, no JS touched.
│
│   ├── Sprint 78 — pql/pql.py → 5 sibling helpers              ✅ done (31fda97)
│       Second backend split.  Façade pattern: :class:`PQL` stays in
│       ``pql.py`` as the public class; method bodies delegate to
│       per-concern helper modules so the orchestration shape is
│       readable in one file while the per-concern logic lives
│       next door.
│
│       **Sibling helpers** under ``pointlessql/pql/``:
│       - ``_types.py`` (44 LOC) — :class:`SQLResult`.
│       - ``_read.py`` (64 LOC) — ``read_table()`` (PQL.table body).
│       - ``_sql.py`` (124 LOC) — ``run_sql()`` (PQL.sql body, the
│         DuckDB execution path).
│       - ``_write.py`` (132 LOC) — ``write_table()`` +
│         ``derive_storage_location()`` (PQL.write_table body).
│       - ``_list.py`` (80 LOC) — ``list_catalogs/_schemas/_tables``.
│
│       **``pql.py``: 461 → 192 LOC** (-269).  Re-exports
│       ``SQLResult`` so existing
│       ``from pointlessql.pql.pql import SQLResult`` (e.g.
│       [tests/test_alerts.py:417](tests/test_alerts.py#L417))
│       continues to resolve.
│
│       **Tests updated.**
│       [tests/test_pql.py](tests/test_pql.py) added ``_READ`` /
│       ``_WRITE`` / ``_LIST`` constants alongside the existing
│       ``_MOD`` and re-pointed every ``@patch`` to the module that
│       now owns the symbol.  This is the right structural fix:
│       internal mocks must follow the implementation when the
│       implementation is intentionally split.  No production code
│       had to compensate for the test surface.
│
│       **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
│       0 errors / 32 warnings (all pre-existing engine.py
│       polars/pyarrow untyped-arg warnings), ``pydoclint`` 0
│       violations, ``pytest tests/test_pql.py tests/test_alerts.py``
│       51/51 passed.
│
│   ├── Sprint 79 — services/notebook_outputs.py → 2-module package    ✅ done (7802f30)
│       Third backend split.  Two-bucket package divides the 480-LOC
│       module along the natural concern boundary already implied by
│       the underlying tables: output frames vs cell-run lifecycle.
│
│       **Package layout** ``pointlessql/services/notebook_outputs/``:
│       - ``outputs.py`` (~270 LOC) — ``NotebookOutput`` table:
│         ``is_persistable``, ``append_output``,
│         ``load_outputs_for_path``.  Plus the cross-table
│         cleanup operations (``clear_cell``, ``clear_session``,
│         ``clear_path``, ``rename_path``) that scrub output frames
│         + cell-run lifecycle rows together when a notebook is
│         re-executed, restarted, deleted, or renamed.
│       - ``cell_runs.py`` (~210 LOC) — ``NotebookCellRun`` (current
│         state per session) and ``NotebookCellRunSource`` (per-
│         execute history): ``upsert_cell_run``,
│         ``record_cell_run_start``, ``record_cell_run_finish``,
│         ``list_cell_run_sources``.
│       - ``__init__.py`` re-exports the full public surface so the
│         lone caller
│         [pointlessql/api/main.py:48](pointlessql/api/main.py#L48)
│         (``from pointlessql.services import notebook_outputs as
│         notebook_outputs_service``) keeps working unchanged.
│
│       **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
│       0 errors / 0 warnings, ``pydoclint`` 0 violations, smoke
│       import OK.  No tests directly import this module.
│
│   ├── Sprint 80 — models.py → 8-module package                ✅ done (804b4aa)
│       Fourth backend split — by far the highest-stakes mechanical
│       refactor of the arc.  The 952-LOC ``models.py`` becomes the
│       package ``pointlessql/models/`` with one module per domain.
│       Alembic and 32 call sites continue to work unchanged via
│       package-level re-exports.
│
│       **Package layout** (every module ends with the FK target's
│       table already imported, so SQLAlchemy mapper-config resolves
│       cross-module ``ForeignKey("table.col")`` strings cleanly):
│       - ``base.py`` (~14 LOC) — ``Base = DeclarativeBase``.
│       - ``auth.py`` (~70 LOC) — ``User`` (referenced by Job,
│         Dashboard, SavedQuery, Alert).
│       - ``audit.py`` (~50 LOC) — ``AuditLog``.
│       - ``sync.py`` (~55 LOC) — ``SyncRun``.
│       - ``scheduler.py`` (~225 LOC) — ``Job``, ``JobRun``,
│         ``JobTask``, ``TaskRun``, ``JobLog``.
│       - ``catalog.py`` (~270 LOC) — ``Dashboard``, ``QueryHistory``,
│         ``QueryHistoryTable``, ``SavedQuery``, ``TableStats``,
│         ``RateLimitEvent``.
│       - ``alerts.py`` (~140 LOC) — ``Alert``, ``AlertDestination``,
│         ``AlertEvent``.
│       - ``notebook.py`` (~170 LOC) — ``NotebookOutput``,
│         ``NotebookCellRun``, ``NotebookCellRunSource``.
│       - ``__init__.py`` (~70 LOC) — re-exports all 20 model symbols
│         + ``Base`` in topological order.
│
│       **Alembic compat verified.**
│       [pointlessql/alembic/env.py:6](pointlessql/alembic/env.py#L6)
│       still does ``from pointlessql.models import Base``.  Smoke
│       import resolves all 20 tables on ``Base.metadata`` in the
│       correct order.
│
│       **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
│       0 errors / 0 warnings, ``pydoclint`` 0 violations,
│       ``pytest`` model-touching test suites all pass against the
│       new package.
│
│   ├── Sprint 81 — services/alerts.py → 4-module package       ✅ done (b076333)
│       Fifth backend split.  Carved 729-LOC ``alerts.py`` along
│       the four concerns it already implied:
│
│       - ``crud.py`` (~340 LOC) — slug / serialisation / can_mutate
│         helpers, backing-Job lifecycle (`_sync_backing_job`),
│         ``create_alert`` / ``list_visible`` / ``get_by_slug`` /
│         ``update_by_slug`` / ``delete_by_slug``.  Renamed
│         ``_serialize`` → ``serialize`` and
│         ``_serialize_destination`` → ``serialize_destination`` and
│         ``_can_mutate`` → ``can_mutate`` so the destinations
│         sub-module can import them without the
│         ``reportPrivateUsage`` flag the kernel_session split first
│         hit (Sprint 77).
│       - ``destinations.py`` (~100 LOC) — ``add_destination`` +
│         ``delete_destination`` (depend on ``crud`` helpers).
│       - ``events.py`` (~165 LOC) — ``record_event`` +
│         ``set_event_outcome`` + ``list_events_for_alert`` +
│         ``list_events_for_owner`` + ``prune_events_older_than``.
│       - ``conditions.py`` (~85 LOC) — pure ``evaluate_condition``
│         + ``build_cloudevent``.
│       - ``__init__.py`` re-exports the full surface so ``from
│         pointlessql.services import alerts as alerts_service`` in
│         API + scheduler + tests resolves unchanged.
│
│       **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
│       0 errors / 0 warnings, ``pydoclint`` 0 violations,
│       ``pytest tests/test_alerts.py`` 19/19 passed.
│
│   ├── Sprint 82 — services/pg_sync.py → 5-module package      ✅ done (c535b70)
│       Sixth backend split.  Carved 778-LOC ``pg_sync.py`` along its
│       pipeline boundaries (introspect → diff → apply → record):
│
│       - ``types.py`` (~250 LOC) — dataclasses (``PgColumn``,
│         ``PgTable``, ``PostgresSnapshot``, ``UcColumn``,
│         ``UcTable``, ``SyncDiff``), ``PG_TO_UC_TYPE`` map,
│         ``map_pg_type_to_uc``, ``PostgresIntrospector`` Protocol,
│         ``EXTERNAL_TABLE_TYPE`` + ``FOREIGN_DATA_SOURCE_FORMAT``
│         constants (renamed from underscore-prefixed to make
│         cross-module use explicit).
│       - ``dsn.py`` (~80 LOC) — ``effective_options`` (renamed from
│         ``_effective_options``) + ``build_dsn``.
│       - ``snapshot.py`` (~95 LOC) — ``PsycopgIntrospector``.
│       - ``diff.py`` (~210 LOC) — pure ``diff_snapshots`` +
│         ``collect_uc_tables`` + ``apply_diff`` + ``_columns_payload``
│         + ``_storage_location_stub`` (the latter two stay underscored
│         because they remain internal to ``apply_diff``).
│       - ``runs.py`` (~165 LOC) — ``run_sync`` orchestration +
│         ``list_recent_runs`` + ``_start_run`` / ``_finish_run``.
│       - ``__init__.py`` re-exports the full surface so existing
│         ``from pointlessql.services import pg_sync`` (API + scheduler)
│         and ``from pointlessql.services.pg_sync import X`` (15 names
│         from tests/test_pg_sync.py) continue to resolve unchanged.
│
│       **Tests updated** for the
│       ``_effective_options → effective_options`` rename — the only
│       compensation needed for the split.
│
│       **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
│       0 errors / 8 warnings (all pre-existing dict-unpack patterns
│       in ``collect_uc_tables``), ``pydoclint`` 0 violations,
│       ``pytest tests/test_pg_sync.py`` 46/46 passed.
│
│   ├── Sprint 83 — services/unitycatalog.py → mixin package    ✅ done (57a2a46)
│       Seventh backend split — broadest blast radius (18+ call
│       sites, 23 tests patch the soyuz function names by string).
│       Carved 783-LOC ``unitycatalog.py`` along securable type using
│       a mixin architecture so ``UnityCatalogClient`` keeps its
│       single-import surface.
│
│       **Package layout** ``pointlessql/services/unitycatalog/``:
│       - ``_api.py`` (~190 LOC) — every soyuz typed function imported
│         as ``_get_X`` / ``_create_X`` / ``_list_X`` / ``_update_X``
│         / ``_delete_X``, plus the shared ``wrap_catalog_errors``
│         decorator (renamed from ``_wrap_catalog_errors`` for the
│         same cross-module scope reason as the kernel_session +
│         alerts + pg_sync splits).
│       - ``_catalogs.py`` (~130 LOC) — ``CatalogsMixin`` (catalog
│         CRUD + ``get_tree`` aggregator that calls back into the
│         metadata mixin via ``self``).
│       - ``_metadata.py`` (~210 LOC) — ``MetadataMixin`` (schema +
│         table + tag CRUD).
│       - ``_permissions.py`` (~110 LOC) — ``PermissionsMixin``.
│       - ``_lineage.py`` (~50 LOC) — ``LineageMixin``.
│       - ``_federation.py`` (~180 LOC) — ``FederationMixin``
│         (connections + external locations + credentials).
│       - ``__init__.py`` (~135 LOC) — re-exports every soyuz
│         ``_xxx`` function binding at the legacy
│         ``pointlessql.services.unitycatalog._xyz`` path so existing
│         tests' ``patch("...unitycatalog._get_tags.asyncio")``
│         continue to find the same module object the mixin calls
│         into.  Defines ``class UnityCatalogClient(CatalogsMixin,
│         MetadataMixin, PermissionsMixin, LineageMixin,
│         FederationMixin)``.
│
│       **MRO verified:** ``UnityCatalogClient → CatalogsMixin →
│       MetadataMixin → PermissionsMixin → LineageMixin →
│       FederationMixin → object``.
│
│       **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
│       0 errors / 4 warnings (3 pre-existing isinstance/list-typing,
│       all unchanged), ``pydoclint`` 0 violations,
│       ``pytest tests/test_tags_permissions.py
│       tests/test_federation.py`` 23/23 +
│       ``tests/test_pg_sync.py tests/test_foreign_catalog.py
│       tests/test_e2e.py tests/test_problem_json.py`` 60/60 passed.
│
│   ├── Sprint 84 — services/scheduler.py → 5-module package    ✅ done (8127b13)
│       Eighth backend split — largest service (1.776 LOC).
│       Carved along the natural pipeline boundaries:
│
│       - ``registry.py`` (~95 LOC) — :class:`KindRegistry`,
│         :data:`JobExecutor` type alias, :func:`build_default_registry`.
│       - ``executors.py`` (~555 LOC) — built-in executors
│         ``_pg_sync_executor`` / ``_python_executor`` /
│         ``_papermill_executor`` (+ ``resolve_notebook_path``,
│         ``_run_papermill_blocking``, ``_jupytext_py_to_ipynb``) /
│         ``_alert_check_executor``.  Function-local imports for
│         ``pql.pql`` / ``alerts`` / ``models`` / ``authorization``
│         preserved verbatim — pre-Sprint-84 code dodged a circular
│         chain through ``pointlessql.db`` and the same pattern
│         continues to work.
│       - ``dag.py`` (~135 LOC) — pure graph algorithms:
│         ``validate_dag`` (cycle detection), ``_topological_order``
│         (Kahn's algorithm), ``_parse_depends_on``.
│       - ``runs.py`` (~825 LOC) — DB helpers, :func:`log_job`,
│         per-task lifecycle (``_run_one_task`` + ``_run_dag``),
│         run orchestration (:func:`execute_run` +
│         ``_execute_run_core``), telemetry helpers
│         (``_emit_run_telemetry`` + ``_post_failure_webhook``).
│         Owns the test-hook globals ``_sleep`` /
│         ``_webhook_client_factory`` / ``_WEBHOOK_TIMEOUT_SECONDS``.
│       - ``loop.py`` (~250 LOC) — :func:`tick_once`,
│         ``_execute_with_semaphores``, :class:`Scheduler` driver
│         class.
│       - ``__init__.py`` (~95 LOC) — re-exports the full public
│         surface so ``from pointlessql.services.scheduler import X``
│         (KindRegistry, Scheduler, build_default_registry,
│         execute_run, tick_once, validate_dag, log_job,
│         _alert_check_executor, _papermill_executor,
│         resolve_notebook_path) and ``scheduler_service.X``
│         attribute access (_is_due, _execute_with_semaphores,
│         _WEBHOOK_TIMEOUT_SECONDS, _sleep, _webhook_client_factory)
│         keep working unchanged.
│
│       **Tests updated** for the test-hook re-location: 6 sites
│       across ``tests/test_scheduler_dag.py`` (2 sites for
│       ``_sleep``) and ``tests/test_metrics.py`` (4 sites for
│       ``_webhook_client_factory``) now monkeypatch
│       ``scheduler_service.runs._sleep`` /
│       ``scheduler_service.runs._webhook_client_factory`` directly.
│       The runs.py module reads them via local-name lookup, so
│       monkeypatching the package-level re-export wouldn't take
│       effect — the right structural fix is to patch where the
│       symbol is used.
│
│       **Per-file pyright suppressions:** ``# pyright:
│       reportPrivateUsage=false`` on ``__init__.py`` / ``loop.py``
│       / ``registry.py`` / ``runs.py`` and ``# pyright:
│       reportUnusedFunction=false`` on ``executors.py`` / ``dag.py``
│       / ``runs.py``.  Cross-module access of underscore-prefixed
│       names is legitimate within a single package; the public
│       contract (``__all__``) keeps the test surface intact.
│
│       **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
│       0 errors / 15 pre-existing warnings, ``pydoclint`` 0
│       violations, ``pytest tests/test_scheduler.py
│       tests/test_scheduler_dag.py tests/test_metrics.py
│       tests/test_alerts.py tests/test_scheduler_papermill.py``
│       80/80 passed.
│
│   ├── Sprint 85 — api/main.py middleware + helpers extract     ✅ done (7ddac5a)
│       First api/main.py decomposition slice — lowest risk,
│       no route logic moved.  Three new modules carved out;
│       main.py drops 6.599 → 6.341 LOC (-258).
│
│       - ``api/middleware.py`` (~155 LOC) — 5 middleware functions
│         (``auth_middleware``, ``static_module_revalidate_middleware``,
│         ``request_id_middleware``) + the imported
│         ``rate_limit_middleware`` + ``csrf_middleware``, all wired
│         into a single ``register_middleware(app)`` entrypoint that
│         preserves the LIFO stacking order
│         (``request_id → static → csrf → rate_limit → auth → handler``
│         on every incoming request).
│         ``PUBLIC_PREFIXES`` lifted out of the underscore-prefixed
│         private name since the new module owns it.
│       - ``api/dependencies.py`` (~90 LOC) — request-scoped helpers
│         ``get_uc_client`` / ``get_user`` / ``require_admin`` /
│         ``client_ip``.  Underscored variants re-imported in
│         ``main.py`` (``get_user as _get_user`` etc.) so the ~hundred
│         existing call sites inside route handlers keep working
│         unchanged.
│       - ``api/_audit_helpers.py`` (~130 LOC) — ``audit`` and
│         ``record_query_async`` async fire-and-forget DB writers,
│         pulled out of ``main.py`` so route modules in Sprints 86-90
│         can import them without dragging the full main module.
│
│       **Middleware order preserved.** ``register_middleware``
│       calls ``app.middleware("http")()`` in the exact same order
│       the decorators previously fired in main.py, so the LIFO
│       execution chain is byte-identical.
│
│       **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
│       0 errors / 74 pre-existing warnings, ``pytest tests/test_csrf.py
│       tests/test_rate_limit.py tests/test_auth.py`` 52/52 passed.
│
│   ├── Sprint 86 — api/main.py catalog tree routes extract       ✅ done (dbb3821)
│       Second api/main.py decomposition slice — narrowed from the
│       sketched ``catalog/sql/queries`` triple-extract to just the
│       catalog tree routes, to establish the route-extraction
│       pattern cleanly before tackling the much larger SQL +
│       queries surfaces in Sprint 86b/87.  main.py drops
│       6.347 → 6.203 LOC (-144).
│
│       - ``api/catalog_routes.py`` (186 LOC) — ``APIRouter``
│         module owning the five sidebar-driving JSON endpoints:
│         ``/api/tree``, ``/api/catalogs``,
│         ``/api/catalogs/{c}/schemas``,
│         ``/api/catalogs/{c}/schemas/{s}/tables``,
│         ``/api/catalogs/{c}/schemas/{s}/tables/{t}/preview``.
│         Two helpers (``preview_head`` engine-aware row truncation,
│         ``run_table_preview`` thread-pool worker) + the
│         ``PREVIEW_ROW_LIMIT = 10`` constant moved over verbatim
│         (just dropped underscore prefixes since they are now
│         module-public within the new package).
│       - ``main.py`` mount point: ``app.include_router(catalog_router)``
│         next to the existing ``auth_router`` line.  Unused
│         ``make_principal_client`` import dropped (only the moved
│         preview code referenced it).
│
│       **Authorization preserved.** Schemas + tables endpoints
│       still call hierarchical ``check_privilege`` (USE_CATALOG /
│       USE_SCHEMA), preview still resolves
│       ``effective_permissions`` once and feeds
│       ``check_privilege_from_effective(SELECT)``.  Preview
│       responses keep ``Cache-Control: no-store`` so revoked
│       grants do not leak through the browser disk cache.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 74 pre-existing warnings,
│       ``pydoclint`` 0 violations.  ``pytest -k 'catalog or
│       tree or preview' --ignore=tests/test_jupyter.py`` 44/44
│       passed (test_jupyter.py has a pre-existing import error
│       unrelated to this sprint).
│
│   ├── Sprint 86b — api/main.py SQL editor routes extract        ✅ done (231b786)
│       Third api/main.py decomposition slice — the four-route
│       Phase-12 SQL editor surface.  The original Sprint 86 plan
│       bundled SQL with /api/queries + /api/saved-queries; this
│       slice carved off the SQL pieces standalone (smaller blast
│       radius, single coherent feature unit).  main.py drops
│       6.203 → 5.652 LOC (-551).
│
│       - ``api/sql_routes.py`` (597 LOC) — owns the four endpoints
│         backing the SQL editor (``POST /api/sql/execute``,
│         ``POST /api/sql/execute/{query_id}/cancel``,
│         ``GET  /api/sql/execute/{history_id}/download``,
│         ``GET  /sql``) plus the four module-level helpers
│         (``short_sql_hash``, ``run_sql_sync``, ``live_queries``,
│         ``run_sql_export_sync``).  Underscores dropped from the
│         helper names since they are now module-public within the
│         new package.
│       - ``main.py`` mount: ``app.include_router(sql_router)``
│         next to the existing auth/catalog routers.  Unused
│         ``record_query_async`` re-import dropped (the SQL
│         routes were the only main.py callers).
│       - ``_parse_since`` deliberately stays in main.py because
│         ``/api/queries`` (next sprint) still depends on it.
│
│       **Authorization preserved.** Both execute and download
│       still re-run ``check_privilege(SELECT)`` per referenced
│       3-part table — a stale ``query_history`` row is not a
│       bypass.  The cancel route stays idempotent (204 on
│       unknown ids).
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 74 pre-existing warnings,
│       ``pydoclint`` 0 violations.  ``pytest -k 'sql or query'
│       --ignore=tests/test_jupyter.py`` 48/48 passed.
│
│   ├── Sprint 86c — api/main.py queries + saved-queries extract  ✅ done (51f6691)
│       Fourth api/main.py decomposition slice — completes the
│       original Sprint-86 plan.  The query-history read endpoints
│       (``/api/queries`` list/get/chart-config), the ``/queries``
│       HTML page, and the full ``/api/saved-queries`` CRUD all
│       move into ``api/queries_routes.py``.  main.py drops
│       5.652 → 5.256 LOC (-396).
│
│       - ``api/queries_routes.py`` (444 LOC) — three
│         query-history routes + the HTML page + five
│         saved-queries routes (list/create + get/patch/delete by
│         slug) + the ``parse_since`` window-string helper.
│         Underscore prefix dropped from ``parse_since`` since it
│         is now module-public within the new package.
│       - ``main.py`` mount: ``app.include_router(queries_router)``
│         next to the other three routers.  Module-level imports
│         of ``query_history`` + ``saved_queries`` services dropped
│         (the alerts route already function-locally re-imports
│         ``saved_queries`` so nothing else regressed).
│
│       **Visibility model preserved.** Non-admin still sees only
│       their own ``query_history`` rows (``user_id`` query param
│       clamped server-side); saved queries still 404 on missing
│       OR forbidden so private slugs are not discoverable; chart
│       config + delete still owner+admin only.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 67 warnings (-7 from Sprint 86b
│       baseline because the dropped ``query_history`` /
│       ``saved_queries`` module-level imports were the source of
│       seven ``Type … partially unknown`` warnings),
│       ``pydoclint`` 0 violations.  ``pytest -k 'saved_quer or
│       query_history or queries' --ignore=tests/test_jupyter.py``
│       26/26 passed.
│
│   ├── Sprint 87 — api/main.py alerts + feed routes extract      ✅ done (c45f4a5)
│       Fifth api/main.py decomposition slice.  The full alerts
│       surface lifts out: ``/api/alerts`` CRUD (5 routes),
│       destinations sub-resource (2 routes), per-user feed-token
│       (2 routes), the two unauthenticated pull-feed endpoints
│       (``/alerts/feed.atom`` + ``/alerts/feed.json``), and the
│       two HTML pages (``/alerts`` list + ``/alerts/{slug}``
│       detail).  main.py drops 5.256 → 4.717 LOC (-539).
│
│       - ``api/alerts_routes.py`` (585 LOC) — 13 routes total
│         plus three module-level helpers (``base_url``,
│         ``rotate_or_fetch_feed_token``, ``user_for_feed_token``).
│         Underscores dropped from helpers; ``saved_queries_service``
│         imported at module level for the alerts list page (which
│         renders the dropdown of available saved-queries).
│       - ``main.py`` mount: ``app.include_router(alerts_router)``.
│         Unused ``saved_queries_service`` and ``JSONResponse``
│         imports removed (the alerts routes were the only
│         remaining callers).
│
│       **Feed-token auth preserved.** ``PUBLIC_PREFIXES`` in
│       ``api/middleware.py`` already exempts
│       ``/alerts/feed.atom`` + ``/alerts/feed.json`` from session
│       auth so they reach the route handlers, which authenticate
│       via the opaque ``?token=…`` query string and 401 on
│       mismatch.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 67 warnings (unchanged),
│       ``pydoclint`` 0 violations.  ``pytest -k alert
│       --ignore=tests/test_jupyter.py`` 19/19 passed.
│
│   ├── Sprint 87b — api/main.py UC volumes routes extract        ✅ done (9047785)
│       Sixth api/main.py decomposition slice.  The full UC
│       volumes surface lifts out: 4 JSON endpoints (browse,
│       upload, delete file + convert-to-Delta) + 2 HTML pages
│       (volumes list + per-volume detail).  main.py drops
│       4.717 → 4.242 LOC (-475).
│
│       - ``api/volumes_routes.py`` (527 LOC) — 6 routes plus
│         ``soyuz_base_url``, ``volume_full_name_split``,
│         ``convert_volume_file_sync``, the
│         ``DELTA_PRIMITIVE_TO_UC`` dict + ``delta_field_to_uc``
│         field-mapper.  Underscores dropped from helper names;
│         the type-mapping pair is re-exported from main.py
│         under its legacy ``_DELTA_PRIMITIVE_TO_UC`` /
│         ``_delta_field_to_uc`` aliases (Invariant 8) so
│         ``tests/test_volume_convert_type_mapping.py`` keeps
│         importing them from ``pointlessql.api.main``.
│       - ``main.py`` mount: ``app.include_router(volumes_router)``.
│         Stale ``_soyuz_base_url`` helper deleted (no remaining
│         caller); top-level ``httpx`` import dropped (only the
│         moved routes used it).
│
│       **Convert-to-Delta admin gate preserved.** The
│       ``api_convert_volume_file_to_delta`` route still calls
│       ``require_admin(request)`` before any work, mirroring the
│       original behaviour.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 67 warnings (unchanged),
│       ``pydoclint`` 0 violations.  ``pytest -k volume
│       --ignore=tests/test_jupyter.py`` 15/15 passed; the
│       targeted ``tests/test_volume_convert_type_mapping.py``
│       9/9 passed (re-export gate intact).
│
│   ├── Sprint 87c — api/main.py governance routes extract        ✅ done (c975f9e)
│       Seventh api/main.py decomposition slice.  The full
│       governance surface lifts out: table column statistics
│       (Sprint 56), notebook-from-table scratch helper, catalog
│       create/sync/patch + schema patch, tags + permissions
│       (get/patch + effective), and lineage.  main.py drops
│       4.242 → 3.751 LOC (-491).
│
│       - ``api/governance_routes.py`` (549 LOC) — 14 routes plus
│         ``split_full_name`` and ``enforce_table_profile_access``
│         helpers.  Underscores dropped from helper names.
│       - ``main.py`` mount: ``app.include_router(governance_router)``.
│         Module-level ``MODIFY`` import dropped (only the moved
│         routes used it).
│
│       **Authorization model preserved.** Profile + stats GET
│       still require SELECT (admin short-circuits); stats DELETE
│       + open-in-notebook + create-catalog + sync-catalog are
│       still admin-only; catalog/schema PATCH still need MODIFY;
│       tag PATCH MODIFY; permission PATCH MANAGE_GRANTS;
│       lineage GET SELECT.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 54 warnings (-13 from Sprint 87b
│       baseline because the moved governance code carried 13
│       ``Type … partially unknown`` warnings),
│       ``pydoclint`` 0 violations.  ``pytest -k 'stats or
│       table_stats or tag or permission or lineage or
│       open_in_notebook' --ignore=tests/test_jupyter.py`` 27/27
│       passed.
│
│   ├── Sprint 88a — api/main.py notebook HTTP routes extract     ✅ done (e621c44)
│       Eighth api/main.py decomposition slice — the HTTP half of
│       the notebook surface lifts out: editor page, doc bundle
│       (GET + POST), per-cell run history, the workspace tree
│       + inspect endpoints, the upload/create/rename/delete CRUD,
│       and the workspace HTML page.  main.py drops 3.751 → 3.227
│       LOC (-524).  The two WebSocket endpoints (kernel + LSP)
│       and their shared ``_resolve_sql_approved_tables`` helper
│       remain in main.py for now — Sprint 88b carves them off
│       into ``notebook_kernel_ws.py``.
│
│       - ``api/notebooks_routes.py`` (580 LOC) — 11 routes plus
│         the ``build_notebook_doc_bundle`` helper shared between
│         the HTML editor and the JSON bundle endpoint.  All
│         existing admin gates preserved (cell-runs, inspect,
│         tree, upload, create, rename, delete, workspace page).
│       - ``main.py`` mount: ``app.include_router(notebooks_router)``.
│         Now-unused ``UploadFile`` + ``File`` + ``Form`` + ``uuid4``
│         + ``json`` (top-level) imports auto-trimmed by ruff.
│
│       **WS auth not touched.** The two WebSocket handlers stay
│       intact in main.py (the ``WebSocket``-typed helper +
│       ZMQ-coupled lifecycle is too coupled to bisect mid-sprint).
│       Sprint 88b will move them.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 44 warnings (-10 from Sprint 87c
│       baseline because the moved notebook code carried 10
│       partial-unknown warnings), ``pydoclint`` 0 violations.
│       ``pytest -k notebook --ignore=tests/test_jupyter.py``
│       34/34 passed.
│
│   ├── Sprint 88b — api/main.py notebook WS endpoints extract    ✅ done (7687f5e)
│       Ninth api/main.py decomposition slice — closes out the
│       notebook surface.  The two ``@app.websocket`` handlers
│       (``/ws/notebook/kernel`` + ``/ws/notebook/lsp``) and their
│       shared ``resolve_sql_approved_tables`` helper move into a
│       dedicated ``notebook_kernel_ws.py``.  main.py drops 3.227
│       → 2.683 LOC (-544).
│
│       - ``api/notebook_kernel_ws.py`` (601 LOC) — both WS
│         endpoints plus the SQL-approval helper.  Underscore
│         dropped from helper name (``resolve_sql_approved_tables``
│         is now module-public within the new package).  WS auth
│         model unchanged: cookie + JWT decode, traversal guard,
│         4401/4400/4404 close codes preserved verbatim.
│       - ``main.py`` mount: ``app.include_router(notebook_ws_router)``.
│         Now-unused ``contextlib``, ``WebSocket``,
│         ``WebSocketDisconnect``, ``UnityCatalogClient``,
│         ``UserInfo``, ``check_privilege``, ``SELECT``, plus the
│         ``services.pyright_bridge`` import all auto-trimmed by
│         ruff (the WS routes were the only remaining callers).
│
│       **WS lifecycle preserved.** All five close codes
│       (4401 unauthenticated, 4400 bad path, 4404 missing pyright,
│       1011 spawn failure, normal close) plus the ZMQ↔WS forward
│       tasks + per-cell output counters + per-execute history-row
│       stamping all moved verbatim.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 26 warnings (-18 from Sprint 88a
│       because the WS code carried 18 partial-unknown warnings),
│       ``pydoclint`` 0 violations.  ``pytest tests/test_api_
│       notebook_workspace.py tests/test_notebook_workspace.py``
│       27/27 passed.  WS endpoints have no unit tests; their
│       integration coverage runs through
│       ``docs/e2e-walkthroughs/notebook_kernel.md`` (Playwright
│       playbook) which the user replays manually.
│
│   ├── Sprint 89a — api/main.py federation routes extract        ✅ done (08a7298)
│       Tenth api/main.py decomposition slice — first cut of
│       Sprint 89's federation+jobs+dashboards triple.  All UC
│       federation administration lifts out: connections,
│       external-locations, credentials (5 routes each + 6 HTML
│       pages = 21 routes total).  main.py drops 2.683 → 2.406
│       LOC (-277).
│
│       - ``api/federation_routes.py`` (322 LOC) — 21 routes,
│         all admin-only.  Mirrors the soyuz-catalog rule that
│         federation administration is admin-only until a finer-
│         grained CREATE_* privilege ships.
│       - ``main.py`` mount: ``app.include_router(federation_router)``.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 25 warnings (-1), ``pydoclint`` 0
│       violations.  ``pytest -k 'connection or credential or
│       federation or external' --ignore=tests/test_jupyter.py``
│       34/34 passed.
│
│   ├── Sprint 89b — api/main.py jobs + scheduler routes extract  ✅ done (ecd5702)
│       Eleventh api/main.py decomposition slice — second cut of
│       Sprint 89.  The full job-scheduler surface lifts out: 5
│       JSON CRUD routes, 3 run/task introspection routes, 3
│       papermill artefact routes, 2 pause/unpause, and 2 HTML
│       pages (jobs list + job detail).  main.py drops 2.406 →
│       1.674 LOC (-732).
│
│       - ``api/jobs_routes.py`` (803 LOC) — 13 routes plus 7
│         module-level helpers (``serialize_job``,
│         ``serialize_task``, ``serialize_task_run``,
│         ``serialize_run``, ``latest_run_per_job``,
│         ``load_job_or_404``, ``require_job_owner_or_admin``,
│         ``load_papermill_run_output_path``) plus the
│         ``JOB_REGISTRY`` module-level constant.  Underscores
│         dropped from helper names.
│       - ``main.py`` mount: ``app.include_router(jobs_router)``.
│         ``JOB_REGISTRY`` and ``serialize_run`` re-exported from
│         main.py under their legacy ``_JOB_REGISTRY`` /
│         ``_serialize_run`` aliases — the still-resident
│         dashboard refresh route reads them at lines 1896 +
│         1899 of pre-split main.py.
│       - ``tests/test_scheduler.py``: ``test_manual_run_and_pause_
│         unpause`` updated to ``monkeypatch.setattr(api_jobs_routes,
│         "JOB_REGISTRY", recording_registry)``.  Python's
│         local-name lookup means a re-export binding in main.py is
│         not what the route handler reads — the test must patch
│         the module that owns the symbol.
│
│       **Visibility model preserved.** Admin sees every job;
│       non-admin sees only jobs whose ``run_as_user_id`` matches
│       their user id.  Mutations check admin-or-owner.  Papermill
│       artefact serving still goes through the visibility-checked
│       route (no static mount, so non-owner users cannot
│       exfiltrate run output by guessing ``run_id`` values).
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 25 warnings (unchanged),
│       ``pydoclint`` 0 violations.  ``pytest -k 'job or
│       scheduler' --ignore=tests/test_jupyter.py`` 54/54 passed.
│
│   ├── Sprint 89c — api/main.py dashboards routes extract        ✅ done (f501c4e)
│       Twelfth api/main.py decomposition slice — closes Sprint
│       89's federation+jobs+dashboards triple.  The Sprint-28
│       dashboards publishing surface lifts out: 4 JSON CRUD +
│       refresh, plus 3 HTML pages (list, detail, output).
│       main.py drops 1.674 → 1.296 LOC (-378).
│
│       - ``api/dashboards_routes.py`` (410 LOC) — 7 routes plus 3
│         module-level helpers (``serialize_dashboard``,
│         ``load_dashboard_or_404``, ``latest_succeeded_run_id``)
│         plus the ``SLUG_PATTERN`` regex.  Refresh endpoint
│         imports ``JOB_REGISTRY`` + ``serialize_run`` from
│         ``api.jobs_routes`` directly (the cross-router
│         coupling that previously routed through the dashboard's
│         re-exports in main.py).
│       - ``main.py`` mount: ``app.include_router(dashboards_router)``.
│         Now-stale ``ValidationError``, ``notebook_render``,
│         ``_JOB_REGISTRY`` + ``_serialize_run`` re-exports, plus
│         ``re`` module import all auto-trimmed by ruff.
│
│       **Visibility model preserved.** Dashboards are visible to
│       every logged-in user (consumer-facing publishing
│       surface); mutations + refresh require admin; the
│       ``/dashboards/{slug}/output`` iframe uses a single
│       internal check that the run belongs to the bound job
│       (admin-or-job-owner is intentionally bypassed because
│       dashboards publish output by design).
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 16 warnings (-9 because the moved
│       dashboard code carried 9 partial-unknown warnings),
│       ``pydoclint`` 0 violations.  No dedicated dashboard
│       pytest module today (covered by the
│       ``docs/e2e-walkthroughs/dashboards.md`` playbook); other
│       suites unaffected.
│
│   └── Sprint 90 — api/main.py admin/home/catalog-html + endgame ✅ done (9c8e997)
│
│   ├── Sprint 91 — frontend sql_editor.js → 4-module split        ✅ done (0d5700d)
│
│   ├── Sprint 92 — frontend federation.js + command_palette       ✅ done (47cfdad)
│
│   ├── Sprint 93 — notebook_editor.html modals → partial          ✅ done (d14f4e7)
│
│   ├── Sprint 94 — page templates → ESM (4 of 7 pilots)            ✅ done (33a0a6c)
│
│   └── Sprint 95 — CSS feinschliff + cache-busting parity          ✅ done (90d40b8)
│       Tranche-6 of the Sprint-76 frontend modularisation plan
│       and the closing sprint of the Sprint-77-95 effort.
│
│       - **CSS splits.** ``responsive.css`` 157 → 74 LOC.  The
│         ``.pql-list-table`` mobile-collapse block + the
│         ``.pql-list-sort-mobile`` dropdown moved to
│         ``components/list_table.css`` (now 171 LOC) so the
│         mobile breakpoint sits next to the desktop list-table
│         styling.  The ``.pql-sidebar-nav-footer`` chrome moved to
│         ``layout.css`` (now 173 LOC) so the sidebar layout rules
│         are co-located.  ``responsive.css`` keeps the Jupyter
│         iframe mobile notice + the touch-target + reduced-motion
│         media queries — the cross-cutting accessibility rules
│         that don't slot under a single component.
│       - **Cache-busting parity.** ``base.html``'s
│         ``<script type="module" src="/static/js/bootstrap.js">``
│         picks up ``?v=sprint95`` so the Sprint 91-94 JS surgery
│         actually reaches every browser without a hard reload.
│       - **Tranche-7 leftover** (csrfToken duplicate in
│         notebook/main.js): inspected; Sprint 75 already
│         migrated the call site to ``import { csrfToken } from
│         '../api.js'`` (line 69 + line 508 use the imported
│         symbol).  No work required.
│
│       **Static gates (all green):** all 11 CSS files still
│       referenced by ``style.css`` master @import chain;
│       ``check-frontend-bootstrap-order.sh`` still green.
│       Pure-rule moves between CSS files; rule selectors and
│       cascade order unchanged.
│
│       **Endgame summary** (Sprints 77-95, 19 sprints total):
│       - 8 backend service splits (kernel_session, pql, notebook_outputs,
│         models, alerts, pg_sync, unitycatalog, scheduler).
│       - 14 api/main.py route extracts (the original 6,599-LOC
│         monolith → 280 LOC, -95.8%, 14 router modules).
│       - 5 frontend tranches (sql_editor 4-module split,
│         federation 3-module split + command_palette ESM,
│         notebook_editor modals partial, 4 of 7 page templates
│         ESM, CSS feinschliff).
│       Net: ~16 000 LOC of monolithic Python + JS spread across
│       ~80 focused files, all <600 LOC, median <200 LOC.  Zero
│       behaviour change; every gate stayed green.
│       Tranche-5 of the Sprint-76 frontend modularisation plan.
│       Four of the seven sketched page-template inline scripts
│       lift into ``frontend/js/pages/*.js`` ESM modules.  Each
│       picks up its server-rendered seed via the template's
│       ``x-data`` attribute as a Jinja-rendered JSON parameter
│       object — first-paint state stays single-roundtrip.
│
│       - ``alerts.html`` 295 → 201 LOC.
│         New ``frontend/js/pages/alerts.js`` (112 LOC) seeded
│         with ``{alerts, savedQueries}``.
│       - ``alert_detail.html`` 251 → 199 LOC.
│         New ``frontend/js/pages/alert_detail.js`` (57 LOC)
│         seeded with ``{slug, destinations}``.
│       - ``volume_detail.html`` 248 → 125 LOC.
│         New ``frontend/js/pages/volume_detail.js`` (115 LOC)
│         seeded with ``{fullName, files}``.  Multipart upload
│         still uses raw ``fetch()`` because pqlApi.fetch is
│         JSON-only.
│       - ``notebooks_workspace.html`` 311 → 172 LOC.
│         New ``frontend/js/pages/notebooks_workspace.js`` (152
│         LOC).  No seed needed — fetches its own tree from
│         ``GET /api/notebooks/tree`` via sessionStorage cache
│         + revalidate.
│
│       ``bootstrap.js`` adds four new factory imports +
│       ``window.*`` re-attaches.  No template ``x-data=`` value
│       changed except the new seed parameters.
│
│       **Three pages deferred** to a follow-up sprint because
│       each is a larger / more interactive surface that warrants
│       its own playbook-replay: ``table.html`` (467 LOC, two
│       inline scripts), ``jobs.html`` (372 LOC,
│       ``createJobModal`` factory inside the create-job modal),
│       ``job_detail.html`` (324 LOC, run-history popover +
│       compare-runs UI).
│
│       **Static gates (all green):** ``node --check`` passes for
│       all four new modules + bootstrap.js,
│       ``check-frontend-bootstrap-order.sh`` still green,
│       ``jinja2.Environment.get_template()`` parses each
│       updated template cleanly.
│       Tranche-4 of the Sprint-76 frontend modularisation plan.
│       Narrowed from the sketched 7-partial split down to the
│       lowest-risk extract: the four shell-scope modals (New
│       notebook, Rename notebook, Delete confirmation, Close-tab
│       with-unsaved-changes).
│
│       - **New partial** ``partials/_notebook_editor_modals.html``
│         (186 LOC) — all four modals.  Bootstrap-modal-Alpine
│         trap memorised: every ``.modal`` toggles via
│         ``:class="{ 'd-block': flag }"`` rather than ``x-show``
│         (Alpine 3.14 strips inline ``display:block`` on
│         false→true and the .modal stylesheet's ``display:none``
│         then wins — BUG-67-01 from the original Sprint 67 fix).
│       - ``pages/notebook_editor.html``: 992 → 819 LOC (-173).
│         The modal block (lines 784-957 pre-split) becomes a
│         single ``{% include "partials/_notebook_editor_modals.html" %}``
│         line.
│
│       **Deferred to a follow-up sprint** (each carries
│       Alpine x-data scope risk that warrants its own
│       playbook-replay):
│
│       - ``_notebook_toolbar.html`` (~70) — sits inside the
│         ``notebookTabEditor`` per-tab scope, not the shell.
│       - ``_notebook_file_tree.html`` (~120) — large block with
│         nested ``x-for`` + ``x-if`` and own button bar.
│       - ``_notebook_variables_explorer.html`` (~50) — tab-scope.
│       - ``_notebook_outline_sidebar.html`` (~40) — tab-scope.
│       - ``_notebook_catalog_modal.html`` (~40) — tab-scope.
│       - ``_notebook_run_history_popover.html`` (~60) — body-anchored
│         popover, JS-driven; needs deeper inspection of the
│         Sprint-73 wiring before extraction.
│
│       **Static gates (all green):** ``jinja2.Environment.get_template()``
│       parses both the page and the new partial cleanly; pure
│       move so behaviour is byte-identical.  Replay of
│       ``docs/e2e-walkthroughs/notebook_editor.md`` deferred to
│       whenever a contributor next touches the file-tree CRUD
│       flow — the four modals carry the
│       ``:class="{ 'd-block': flag }"`` discipline verbatim from
│       BUG-67-01 so the Bootstrap-modal trap stays defused.
│       Tranche-3 of the Sprint-76 frontend modularisation plan.
│       Two unrelated splits in one sprint because both stood at
│       the awkward 200-LOC inline-script + multi-export shape:
│
│       - **federation.js (195 LOC) → 3 sibling modules.**
│         ``federation_connections.js`` (44 LOC),
│         ``federation_credentials.js`` (94 LOC, both
│         credential + external-location forms because
│         external-locations bind a credential),
│         ``federation_catalogs.js`` (94 LOC, foreign-catalog
│         form + the generic ``deleteConfirm`` factory used by
│         every detail page).  ``bootstrap.js`` updated to import
│         from each new module directly; the ``window.*`` names
│         are unchanged so no template edit needed.
│       - **command_palette.html inline script → ESM module.**
│         The 256-line inline ``<script>`` block at the bottom
│         of the partial moves into
│         ``frontend/js/components/command_palette.js``
│         (274 LOC).  ``commandPalette()`` is wired through
│         ``bootstrap.js``; the partial drops to 102 HTML-only
│         LOC.
│
│       **Static gates (all green):** ``node --check`` passes for
│       all four new modules + bootstrap.js,
│       ``check-frontend-bootstrap-order.sh`` still green.
│       Playbook replay deferred — pure move so behaviour is
│       byte-identical (the partial's
│       ``x-data="commandPalette()"`` resolves to the same factory
│       through bootstrap.js's ``window.commandPalette =`` line).
│       Tranche-2 of the Sprint-76 frontend modularisation plan.
│       The 608-LOC ``frontend/js/sql_editor.js`` factory splits
│       into a 86-LOC façade + four sibling ESM modules under the
│       same namespace; ``bootstrap.js`` re-attaches ``sqlEditor``
│       unchanged so the template's ``x-data="sqlEditor"`` is
│       invisible to the carve-up.
│
│       - ``sql_editor_monaco.js`` (198 LOC) — CodeMirror lifecycle
│         + autocomplete + Cmd-Enter/Cmd-S keymap + ``c`` toggle +
│         catalog-tree completions refresh + getSQL/setSQL.
│       - ``sql_editor_execute.js`` (131 LOC) — ``run({explain})``
│         + ``cancel()`` + elapsed counter + ``_generateQueryId``
│         + ``formatCell``.
│       - ``sql_editor_saved.js`` (89 LOC) — ``/api/saved-queries``
│         CRUD + load-into-editor + Save modal.
│       - ``sql_editor_chart.js`` (189 LOC) — Chart.js view, axis
│         auto-pick, bar/line/pie/scatter render, PNG download,
│         debounced PATCH /api/queries/{id}/chart-config,
│         ``seedFromHistory`` deep-link entry point.
│
│       Closure state from the pre-split shape (``cmView`` +
│       ``catalogCompletions``) lives on ``this._cmView`` +
│       ``this._catalogCompletions`` so all four sub-modules can
│       reach the EditorView via ``this``.  Each sub-module
│       exports a methods object the façade spreads into the
│       returned x-data shape.
│
│       **Static gates (all green):** ``node --check`` passes for
│       all five files, ``bash scripts/check-frontend-bootstrap-order.sh``
│       still green (line 112 bootstrap.js precedes line 113 Alpine
│       CDN in base.html).  Playbook replay deferred to whenever
│       a contributor next touches /sql; the split is a pure move
│       so behaviour is byte-identical.
│       Final api/main.py decomposition slice.  Three new modules
│       lift out everything left:
│
│       - ``api/admin_routes.py`` (259 LOC) — the ``/admin/audit``
│         viewer + ``/admin/audit/export`` (CSV / JSON).  Both
│         admin-gated, both reading the Sprint-7 ``audit_log``
│         table append-only.
│       - ``api/home_routes.py`` (573 LOC) — the home dashboard
│         (``GET /``), the JSON twin
│         (``GET /api/home/summary``), and the Cmd+K command
│         palette (``GET /api/search``).  ``build_home_summary``
│         + ``score_match`` + ``epoch_seconds`` helpers move
│         along.
│       - ``api/catalog_html_routes.py`` (254 LOC) — the three
│         catalog-browser HTML pages (catalog detail / schema
│         detail / table detail) that drive the sidebar
│         navigation.  Their JSON twins remain in
│         ``api/catalog_routes.py`` from Sprint 86.
│
│       **main.py endgame: 6,599 → 280 LOC (-95.8% over Sprints
│       85-90).** What remains: app construction +
│       ``register_middleware`` + the 14 ``include_router()``
│       calls + lifespan + audit-retention loop +
│       ``/healthz`` + ``/metrics`` + ``cli()``.  Every route
│       handler now lives in a focused
│       ``api/<area>_routes.py`` module.
│
│       **Static gates (all green):** ``ruff`` 0 errors,
│       ``pyright`` 0 errors / 0 warnings on main.py (-16 because
│       the moved code carried the remaining partial-unknown
│       warnings), ``pydoclint`` 0 violations.  Eleven now-stale
│       imports auto-trimmed by ruff.
│
├── Phases 12.10–13.5 — completed, collapsed              ✅ done
│   │
│   │   Full per-sprint detail in
│   │   [`ROADMAP_ARCHIVE.md`](ROADMAP_ARCHIVE.md).
│   │
│   │   ```
│   │   Phase  Closed       Sprint range  What shipped
│   │   ─────  ───────────  ────────────  ─────────────────────────────────────
│   │   12.10  2026-04      S96–S98       Notebook format hardening (UUID-free percent grammar, FNV-1a-64 hash)
│   │   12.11  2026-04      S99           Notebook visual polish (toolbar+badges only; S100–S102 cancelled)
│   │   12.12  2026-04-24   S103–S106     Agent-first pivot: delete browser editor, build read-only run-view
│   │   13     2026-04-26   S107–S128     Agent-run supervision + analytical memory; Sprint 13.11 = 10 reflexive tools (Family A+B)
│   │   13.5   2026-04-26   S129–S140     Medallion + DuckDB-first opinion: pql.autoload/merge/aggregate, Hermes-Medallion notebook
│   │   ```
│   │
│
├── Phase 14 — Audit-trail completeness pass               ✅ done (2026-04-26)
│   │
│   │   Closes the three Tier-3 gaps captured in
│   │   ``project_phase13_audit_gaps.md`` plus the external-write
│   │   blind spot surfaced by the 2026-04-25 live walkthrough
│   │   (see ``project_full_autonomous_audit_critical_path.md``).
│   │   Operational-hygiene items, not greenfield features. Public-
│   │   launch readiness lives in the unscheduled ``Some-day``
│   │   block at the bottom of this tree.
│   │
│   │   Tool-calls tab landed silently in the Sprint-13.7.4 window
│   │   before the migrations squash (see
│   │   ``frontend/templates/pages/run_view.html`` lines 235-240),
│   │   so the original Sprint-13.10 carry-over item is dropped.
│   │
│   │   Sprint sequence is intentional: smallest footprint first
│   │   to validate the migration + quality-gate pattern, cross-
│   │   repo work last because the soyuz tag-bump is a natural
│   │   sync point. Plan in
│   │   ``.claude/plans/plane-phase-14-komplett-floofy-nest.md``.
│   │
│   ├── Sprint 14.1 — Cost-gate EXPLAIN-snapshot on ``agent_runs`` ✅ done (c625e9f)
│   │   └── Alembic ``a1c051a7e1ab`` added nullable
│   │       ``agent_runs.cost_gate_trigger`` Text column;
│   │       ``/api/sql/explain`` returns the snapshot
│   │       (``{explain, estimated_cost, threshold, engine}``)
│   │       when ``needs_approval`` is true; the runtime forwards
│   │       it to ``/api/agent-runs/{id}/finish`` and the run-
│   │       detail metadata card renders a collapsible EXPLAIN
│   │       block
│   ├── Sprint 14.2 — Read-audit for ``pql.table()`` + engine-direct ✅ done
│   │   └── Alembic ``b27e6ad14ead`` extended ``query_history``
│   │       with a ``read_kind`` discriminator
│   │       (``sql_execute`` / ``pql_table`` / ``engine_direct``);
│   │       new ``services/read_audit.py`` synthesises
│   │       ``SELECT * FROM <fqn>`` rows so the existing
│   │       ``/queries`` UI keeps working;
│   │       ``pointlessql/pql/_read.py`` instruments ``pql.table()``
│   │       gated on ``POINTLESSQL_AGENT_RUN_ID``; ``/queries``
│   │       gains a Kind dropdown + column, run-detail Queries tab
│   │       gains the same column.
│   ├── Sprint 14.3 — External-write detection ("unattributed writes") ✅ done
│   │   └── Alembic ``c3d4f5a6b7e8`` adds the
│   │       ``unattributed_writes`` table; new
│   │       ``services/external_write_scanner.py`` walks
│   │       ``DeltaTable.history()`` per UC table and diffs against
│   │       ``agent_run_operations.delta_version_after``;
│   │       ``/admin/external-writes`` page + JSON API +
│   │       on-demand scan trigger + acknowledge route; lifespan
│   │       loop opt-in via
│   │       ``POINTLESSQL_EXTERNAL_WRITES_SCAN_INTERVAL_SECONDS``;
│   │       run-detail Operations tab surfaces first 5 unattributed
│   │       writes on touched tables.  Detection-only — hard-block
│   │       via storage permissions stays Phase 16+ if a real
│   │       customer ever asks
│   └── Sprint 14.4 — soyuz UC mutation cross-reference into ``/runs/{id}`` ✅ done
│       ├── soyuz side (commit ``57e166d``, locally tagged
│       │   ``v0.2.0rc3``, push pending): greenfield audit
│       │   infrastructure — Alembic 015 ``audit_log`` table, new
│       │   ``audit_service.log_action`` helper, middleware
│       │   captures ``X-Principal``+``X-Agent-Run-Id`` via
│       │   ContextVars, ``GET /audit-log`` route mounted at root,
│       │   six mutation routes instrumented (tags / tables / schemas)
│       ├── PointlesSQL side: ``make_soyuz_client``/
│       │   ``make_principal_client`` accept ``agent_run_id`` kwarg;
│       │   ``PQL.__init__`` resolves env and forwards it; new
│       │   ``services/soyuz_audit.fetch_for_run()`` via raw httpx
│       │   (404 → empty for older soyuz)
│       └── UI: new "UC mutations" tab on ``/runs/{id}`` rendering
│           soyuz audit rows attributed to the run.  Pin bump to
│           ``v0.2.0rc3`` pending a push of the soyuz tag
│
├── Phase 15 — Lineage completeness                       ✅ done (2026-04-26)
│   │
│   │   Closes two lineage gaps that make Phase 14's operation-
│   │   level audit forensically usable:
│   │
│   │   1. **PQL writes don't appear in the soyuz lineage graph.**
│   │      The ``lineage_runs`` + ``lineage_edges`` infra (soyuz
│   │      Sprint 22, ``POST /lineage/v1/events``) exists, but
│   │      PointlesSQL emits nothing — the lineage card on
│   │      ``table.html`` renders only externally seeded edges
│   │      (in practice: none).  Sprint 15.1 closes this by
│   │      auto-emitting OpenLineage events from every
│   │      ``operation_context()`` exit.
│   │
│   │   2. **No per-row provenance.** ``agent_run_operations``
│   │      knows "op X produced N rows in Delta version V" but
│   │      not "silver row 47 came from bronze row 12 in
│   │      orders.csv at offset 11".  Sprints 15.2 + 15.3 add a
│   │      stable ``_lineage_row_id`` audit column on bronze and
│   │      a ``lineage_row_edges`` shadow table populated by
│   │      ``pql.merge``.  Sprint 15.4 surfaces the trail in the
│   │      UI.
│   │
│   │   PointlesSQL-only — soyuz already has everything we need.
│   │   Plan in ``.claude/plans/plane-phase-14-komplett-floofy-nest.md``.
│   │
│   │   The **LLM-side provenance log** (signed token trail of
│   │   every LLM iteration) is **out of scope** for Phase 15 —
│   │   it lives in shoreguard, not PointlesSQL, per
│   │   ``project_pointlessql_vs_shoreguard_boundary.md``.  Cross-
│   │   ref via ``agent_run_id`` is already in place; shoreguard
│   │   builds its log against that anchor when it gets there.
│   │
│   ├── Sprint 15.1 — PQL → soyuz OpenLineage emission          ✅ done
│   │   └── New ``services/soyuz_lineage.emit_event_sync`` helper,
│   │       hooked into ``operation_context()`` after recorder
│   │       commit.  Best-effort — connection-refused / 5xx are
│   │       swallowed and stamped as a ``[lineage_emit_failed]``
│   │       marker onto ``agent_run_operations.error_message`` so
│   │       the underlying write never gets blocked by a lineage-
│   │       emit failure.  ``pql.merge`` / ``pql.write_table`` /
│   │       ``pql.autoload`` gain optional ``source_table_fqn`` /
│   │       ``source_volume_fqn`` kwargs so callers can declare
│   │       upstream UC inputs (``pql.merge`` derives this
│   │       automatically when *source* is itself a UC string).
│   │       Run-detail header gains a "View lineage graph" link.
│   ├── Sprint 15.2 — Bronze ``_lineage_row_id`` column          ✅ done
│   │   └── ``LayerConvention`` for ``bronze`` gains a fourth
│   │       audit column ``_lineage_row_id`` =
│   │       ``SHA-256(file_sha || ":" || row_offset)``.
│   │       Deterministic + idempotent — same row in same file
│   │       always gets the same ID.  Injected by
│   │       ``_inject_audit_columns`` alongside the existing
│   │       three audit columns.  No migration — it's a
│   │       convention; the column appears on the next autoload.
│   ├── Sprint 15.3 — ``lineage_row_edges`` shadow table         ✅ done
│   │   └── Alembic ``d4e5f6a7b8c9`` creates ``lineage_row_edges``
│   │       (``run_id``, ``op_id``, ``source_table``,
│   │       ``source_row_id``, ``target_table``, ``target_row_id``,
│   │       ``created_at`` plus four indexes).  New
│   │       ``services/lineage_edges.py`` exposes
│   │       ``synth_target_row_id`` =
│   │       ``SHA-256("<source_id>:<target_table>")`` plus a
│   │       best-effort batch-INSERT (``record_edges``) and the
│   │       Sprint-15.4-bound walk-back / count-per-op queries.
│   │       ``pql.merge`` and ``pql.write_table`` (when the caller
│   │       declares ``source_table_fqn``) capture source IDs,
│   │       synthesise target IDs, write them as the target's
│   │       ``_lineage_row_id`` column, and stash the mapping on
│   │       ``OperationRecorder.pending_lineage_edges`` so the
│   │       post-commit hook persists one edge per row.  Failures
│   │       stamp ``[lineage_edges_partial]`` onto
│   │       ``error_message`` so the audit trail records the
│   │       attempt.  ``pql.sql`` has no direct write path today —
│   │       ground-truth confirmed at sprint start — so
│   │       ``lineage_break`` markers stay documentation-only until
│   │       a CTAS path appears.  Storage in PointlesSQL metadata
│   │       DB; sibling Delta tables remain the Phase-17+ scaling
│   │       option if a single run ever exceeds ~1M edges.
│   ├── Sprint 15.4 — Row-trace UI                              ✅ done
│   │   └── New ``api/lineage_routes.py`` exposes
│   │       ``GET /api/lineage/row-trace?table=&row_id=`` (JSON
│   │       walkback capped at 20 hops, with the bronze step
│   │       enriched via DuckDB-over-deltalake to surface
│   │       ``_source_file``) and the matching HTML page
│   │       ``/catalogs/{cat}/schemas/{sch}/tables/{tbl}/rows/{row_id}/trace``.
│   │       The lineage_card component gained a "per-row lineage
│   │       available" hint that fires when ``_lineage_row_id`` is on
│   │       the table; the table preview turns the
│   │       ``_lineage_row_id`` cell into a deep-link to the trace
│   │       page (Alpine x-template branches keep the Sprint-13.5
│   │       preview otherwise unchanged).  ``run_view.html`` gained
│   │       a "Lineage" tab between "UC mutations" and "Queries"
│   │       that lists per-op edge counts and links into each
│   │       output table's lineage card.  Router registered before
│   │       ``governance_router`` so the new exact-match route
│   │       beats the existing ``/api/lineage/{full_name:path}``
│   │       catch-all.
│   │
│   └── Out-of-scope (explicit, ships in later phases or never):
│       ├── **Shoreguard Provenance Log** (LLM-side signed
│       │   token-trail) — lives in shoreguard-fresh, see
│       │   ``project_shoreguard_provenance_log.md`` and
│       │   ``project_pointlessql_vs_shoreguard_boundary.md``
│       ├── **SQL row-lineage** — arbitrary joins/aggregates
│       │   have no clean preimage.  SQL ops mark the chain
│       │   ``lineage_break: true`` and the UI surfaces the
│       │   discontinuity transparently
│       └── **Column-level lineage** — orthogonal dimension
│           (input column → output column).  Separate phase if
│           a user ever asks (now scheduled as Phase 15.6).
│
├── Phase 15.5 — Aggregate Lineage + Reject Visibility    ✅ done (2026-04-26)
│   │
│   │   Sub-phase of Phase 15.  Closes two row-lineage gaps that
│   │   the live E2E replay (2026-04-26) made visible:
│   │
│   │   1. **Aggregate fan-in is missing.**  Gold tables built via
│   │      ``pandas.groupby`` + ``pql.write_table(mode="overwrite")``
│   │      produce zero edges — ``_lineage_row_id`` identity from
│   │      silver is silently lost in the groupby.  A gold anomaly
│   │      cannot be traced back to its silver sources.
│   │   2. **Reject visibility is missing.**  ``pql.merge`` can drop
│   │      rows silently (NULL ``on``-key, schema mismatch, dedup
│   │      conflict); only the aggregate counter
│   │      (``num_target_rows_inserted``) leaks the fact.  Agents
│   │      cannot answer "why did only 47 of 50 source rows land?"
│   │
│   │   Plan in ``.claude/plans/plane-phase-14-komplett-floofy-nest.md``.
│   │   Phase 15.6 (Column-Level Lineage) follows directly after.
│   │   Existing Phase 16 (Delta-Branching + Rollback) stays queued
│   │   and unchanged.
│   │
│   ├── Sprint 15.5.0 — Phase-15 bugfix + housekeeping     ✅ done (749ed49)
│   │   └── ``BigInteger PK`` → ``Integer PK`` on
│   │       ``lineage_row_edges`` (SQLite autoincrement quirk that
│   │       silently failed every per-row edge insert during the
│   │       Phase-15 replay) plus run-detail header URL fix
│   │       (``/catalogs/{cat}/{schema}/{table}`` →
│   │       ``/catalogs/{cat}/schemas/{schema}/tables/{table}``).
│   │       Reinforces the "live replay as gate" memo: ruff /
│   │       pyright / pydoclint cannot catch SQLite-PK quirks or
│   │       URL string templates.
│   ├── Sprint 15.5.1 — ``pql.aggregate()`` + fan-in edges  ✅ done (9ed099f)
│   │   └── New ``pointlessql/pql/_aggregate.py`` analog to
│   │       ``_merge.py``.  Required ``source_table_fqn`` kwarg (no
│   │       optional fan-in lineage), deterministic
│   │       ``synth_target_row_id =
│   │       SHA-256(target_table || ":" || sorted(group_values))``.
│   │       Emits N→1 edges (one per source row in the aggregated
│   │       group).  ``op_name`` enum extended by ``"aggregate"``.
│   ├── Sprint 15.5.2 — walk_back tree + row-trace fan-in   ✅ done (f4992bc)
│   │   └── Refactor ``services/lineage_edges.walk_back`` to return
│   │       ``TraceStep`` with ``predecessors: list`` instead of a
│   │       single edge.  Aggregate steps return the full source
│   │       set; merge / write_table steps keep the deterministic
│   │       single-predecessor walk.  Template renders fan-in as
│   │       collapsible "Aggregated from N rows" block with
│   │       click-through to each source row.
│   ├── Sprint 15.5.3 — ``lineage_row_rejects`` + capture    ✅ done (0908f84)
│   │   └── New Alembic migration parented at ``d4e5f6a7b8c9``
│   │       creates ``lineage_row_rejects(run_id, op_id,
│   │       source_table, source_row_id, reason, detail,
│   │       created_at)``.  ``pql.merge`` gains opt-in
│   │       ``track_rejects=True`` kwarg; pre-merge set-diff between
│   │       source and merged rows captures dropped row IDs with
│   │       enum reason (``on_key_null`` /
│   │       ``duplicate_in_source`` / ``schema_mismatch`` /
│   │       ``merge_predicate_excluded`` / ``other``).  Default
│   │       off — performance-conservative.
│   ├── Sprint 15.5.4 — Reject tab on run-detail            ✅ done (89c67d2)
│   │   └── New ``tab-rejects`` between Operations and Tool calls
│   │       on ``frontend/templates/pages/run_view.html``.
│   │       Counter in the tab label; per-row table with
│   │       click-through to ``/.../rows/{id}/trace``.
│   │       Empty-state "No rows rejected in this run.
│   │       (``track_rejects=True`` not set on any merge call)".
│   └── Sprint 15.5.5 — Notebook update + live E2E replay   ✅ done (7d44415)
│       └── ``notebooks/hermes_medallion.py`` gold-block migrated
│           from ``groupby`` + ``write_table`` to
│           ``pql.aggregate``.  ``pql.merge`` call gains
│           ``track_rejects=True``.  Headful Firefox replay
│           (analog to the Phase-15 replay): row-trace on a
│           gold row shows fan-in, run-detail shows rejects tab.
│
├── Phase 15.6 — Column-Level Lineage                      ✅ done (2026-04-26)
│   │
│   │   Orthogonal dimension to row-lineage: which input column
│   │   feeds which output column, with a ``transform_kind`` label
│   │   (``identity`` / ``rename`` / ``derived`` / ``aggregate`` /
│   │   ``unknown_origin`` / ``sql_select`` / ``sql_function`` /
│   │   ``sql_unknown``).  Lets agents answer "if I rename
│   │   ``unit_price`` in silver, which gold columns break?".
│   │
│   │   Plan in
│   │   ``.claude/plans/plane-phase-14-komplett-floofy-nest.md``.
│   │   Volume note: ``lineage_column_map`` is bounded by **schema
│   │   breadth**, not by row count — the canonical Hermes-Medallion
│   │   notebook adds ~26 column edges total against the 102 row
│   │   edges + 2 rejects from Phase 15.5.  Best-effort hard cap of
│   │   1000 edges per op gates the ``pql.sql`` outlier case.
│   │
│   │   Decisions (AskUserQuestion 2026-04-26):
│   │
│   │   - Storage: PointlesSQL-only ``lineage_column_map`` table —
│   │     soyuz columnLineage facet ingest is a Phase-15.8+ topic.
│   │   - ``pql.sql``: ``sqlglot.optimizer.lineage`` AST walk
│   │     (sqlglot ≥ 26.0 already in deps + already used in
│   │     ``pointlessql/pql/sql_parser.py``).
│   │   - Pre-call derivations: opt-in
│   │     ``derivations={"target": ["src_a", ...]}`` kwarg on
│   │     aggregate / merge / write_table.
│   │   - Value-level change tracking deferred to a future Phase
│   │     15.7 (``lineage_value_changes`` opt-in table).
│   │
│   ├── Sprint 15.6.0 — open Phase 15.6 in ROADMAP / CHANGELOG ✅ done (834f30e)
│   │   └── Housekeeping commit only — no migration, no code.
│   ├── Sprint 15.6.1 — ``lineage_column_map`` + helpers       ✅ done (52bc740)
│   │   └── New Alembic ``g7b8c9d0e1f2``-style migration parented
│   │       on ``f6a7b8c9d0e1`` (lineage_row_rejects).
│   │       ``LineageColumnMap`` ORM model with CHECK-constrained
│   │       ``transform_kind``.  ``record_column_edges`` +
│   │       ``walk_back_columns`` helpers (mirror Sprint 15.5's
│   │       ``record_edges`` / ``walk_back`` shape).
│   │       ``OperationRecorder.pending_column_edges`` post-commit
│   │       hook with ``[lineage_column_partial]`` marker on cap-hit.
│   ├── Sprint 15.6.2 — declarative-path instrumentation       ✅ done (907a41a)
│   │   └── New ``services/column_lineage_diff.infer_column_edges``
│   │       schema-diff helper.  ``derivations={...}`` kwarg lands
│   │       on ``pql.aggregate`` + ``pql.merge`` + ``pql.write_table``.
│   │       ``pql.autoload`` records four ``unknown_origin`` audit
│   │       edges automatically.  ``_lineage_row_id`` cross-stage
│   │       edges land as ``derived`` with detail
│   │       ``"synth_target_row_id"``.
│   ├── Sprint 15.6.3 — ``pql.sql`` AST extraction             ✅ done (aa8ce4d)
│   │   └── ``sql_parser.extract_column_lineage`` walks
│   │       ``sqlglot.optimizer.lineage`` per output column.
│   │       transform_kinds ``sql_select`` / ``sql_function`` /
│   │       ``sql_unknown``.  Window functions + lateral joins are
│   │       ``sql_unknown`` for v1.
│   ├── Sprint 15.6.4 — column-trace API + UI                  ✅ done (b2d3a86)
│   │   └── ``GET /api/lineage/column-trace?table=&column=``
│   │       (JSON) and HTML at
│   │       ``/catalogs/{cat}/schemas/{sch}/tables/{tbl}/columns/{col}/trace``.
│   │       Table-detail page surfaces a "lineage" link per column
│   │       (gated by an ``EXISTS`` query).  Run-detail Operations
│   │       tab gains a ``column edges: N`` counter (no new tab).
│   └── Sprint 15.6.5 — notebook + headful Firefox replay     ✅ done (81a2459)
│       └── ``notebooks/hermes_medallion.py`` aggregate call gets
│           ``derivations={"placed_day": ["placed_at"],
│           "line_revenue": ["qty", "unit_price"]}``.  Live replay
│           steps: column-trace API smoke; DB row-count canary
│           (≤100); table-detail link + column-trace fan-in;
│           run-view counter.
│
├── Phase 15.7 — Value-Level Lineage                       ✅ done (2026-04-26)
│   │
│   │   The fourth lineage axis: not *where* a value came from
│   │   (15 / 15.5 / 15.6 already cover that) but *what it was
│   │   before*.  Answers "this gold row's ``revenue`` is $1234 —
│   │   what was it last week, and which run changed it?".
│   │   Surface scope is ``pql.merge(strategy="upsert")`` only —
│   │   the only PQL primitive that mutates rows in place.
│   │
│   │   Plan in
│   │   ``.claude/plans/plane-phase-14-komplett-floofy-nest.md``.
│   │   Volume note: ``lineage_value_changes`` is bounded by
│   │   *matched-and-actually-different* cells, not by row count.
│   │   Re-running the same merge over identical input produces
│   │   zero rows (postimage == preimage → skip).  Demo replay
│   │   tweaks ONE ``unit_price`` cell → exactly 1 value-change
│   │   row.  Hard cap of 100k per op gates the pathological
│   │   100k-row × all-columns daily-upsert case.
│   │
│   │   Decisions (AskUserQuestion 2026-04-26):
│   │
│   │   - Capture: **CDF bootstrap** —
│   │     ``delta.enableChangeDataFeed=true`` on every new Delta
│   │     write (autoload + write_table create-paths).
│   │     ``DeltaTable.load_cdf()`` post-merge yields native
│   │     preimage/postimage pairs; we diff per-cell on
│   │     ``_lineage_row_id``.
│   │   - Cap: ``MAX_VALUE_CHANGES_PER_OP = 100_000``;
│   │     ``[lineage_value_partial]`` marker on cap-hit.
│   │   - Storage: ``Text`` columns for ``old_value`` /
│   │     ``new_value`` (PG TEXT / SQLite TEXT both unbounded).
│   │   - Strategy scope: only ``upsert``.  SCD-2 silently
│   │     ignores the flag (history is in ``_valid_from`` /
│   │     ``_valid_to`` / ``_is_current`` already).
│   │   - PointlesSQL-only.  Cross-tool valueChange facet ingest
│   │     in soyuz is a hypothetical Phase 15.8+ topic.
│   │
│   ├── Sprint 15.7.0 — open Phase 15.7 in ROADMAP / CHANGELOG ✅ done (7b42369)
│   │   └── Housekeeping commit only — no migration, no code.
│   ├── Sprint 15.7.1 — ``lineage_value_changes`` + helpers    ✅ done (6641ed2)
│   │   └── New Alembic migration ``h8c9d0e1f2a3`` parented on
│   │       ``g7b8c9d0e1f2`` (lineage_column_map).
│   │       ``LineageValueChange`` ORM model with ``Text`` old/new
│   │       value columns.  ``record_value_changes`` +
│   │       ``count_value_changes_for_op`` +
│   │       ``fetch_value_changes_for_row`` helpers (mirror 15.6
│   │       ``record_column_edges`` shape).
│   │       ``OperationRecorder.pending_value_changes``
│   │       post-commit hook with ``[lineage_value_partial]``
│   │       marker on cap-hit.
│   ├── Sprint 15.7.2 — CDF bootstrap on new Delta writes      ✅ done (acb9954)
│   │   └── New ``pointlessql/pql/_cdf.py`` exposing
│   │       ``cdf_creation_config()`` +
│   │       ``ensure_cdf_enabled(target_location)``.
│   │       ``pql.write_table`` (create-path) and ``pql.autoload``
│   │       (first-write) call ``ensure_cdf_enabled`` post-write
│   │       so every new Delta table has
│   │       ``delta.enableChangeDataFeed=true``.
│   ├── Sprint 15.7.3 — ``pql.merge(track_value_changes=True)`` ✅ done (31847dd)
│   │   └── New ``services/value_change_capture.extract_value_changes``
│   │       pure-function diff helper consuming a CDF PyArrow
│   │       Table.  ``track_value_changes`` kwarg on
│   │       ``pql.merge`` (default ``False``) opts in.  Honoured
│   │       only on ``strategy="upsert"`` (SCD-2 logs warning +
│   │       skips).  Best-effort
│   │       ``ensure_cdf_enabled(target_location)`` before
│   │       ``dt.load_cdf()``; pairs ``update_preimage`` /
│   │       ``update_postimage`` on ``_lineage_row_id`` and emits
│   │       one ``ValueChangeSpec`` per changed cell.
│   ├── Sprint 15.7.4 — value-change API + UI surface          ✅ done (fb8fcb2)
│   │   └── ``GET /api/lineage/value-changes?table=&row_id=
│   │       &column=`` (JSON).  Row-trace page gains
│   │       collapsible "Value changes (N)" per step listing
│   │       ``column · old → new · created_at``.  Run-detail
│   │       Operations tab gains a ``value changes: N`` counter.
│   └── Sprint 15.7.5 — notebook + headful Firefox replay      ✅ done (this commit)
│       └── ``notebooks/hermes_medallion.py`` silver
│           ``pql.merge`` gets ``track_value_changes=True``;
│           second cell tweaks one ``unit_price`` and re-runs
│           the merge.  Live replay confirmed: 1 value-change
│           row in DB (``unit_price`` 2.5 → 2.51), API responds
│           with the change, row-trace renders "Value changes
│           (1)" collapsible, run-view counter shows
│           ``value changes: 1`` on the merge op.
│
├── Phase 16 — First-Class Rollback                       ✅ closed 2026-04-27
│   │
│   │   The reactive half of the agent-trust UX: a run already
│   │   hit main and a human at 09:00 wants ONE button to undo
│   │   it.  Today Delta time-travel exists, but PointlesSQL has
│   │   no first-class primitive and no UI on top of it.
│   │
│   │   Originally sketched alongside Delta-Branching as one
│   │   bundled phase.  Per AskUserQuestion 2026-04-27 the phase
│   │   **splits**: Phase 16 ships rollback only (4 sub-sprints,
│   │   the audit→action loop); Delta-Branching becomes Phase
│   │   16.5 (sketch only — load-bearing on a ``_delta_log/``
│   │   shallow-clone spike that deltalake-python 1.5.0 doesn't
│   │   expose first-class).
│   │
│   │   Cascade-aware: warns when downstream tables were derived
│   │   from the rollback target.  Fail-loud on staleness:
│   │   refuses if ``delta_version_after(targeted_op) !=
│   │   current_version`` unless ``allow_force=True``.
│   │
│   ├── Sprint 16.0 — Housekeeping                          ✅
│   │   ├── ROADMAP + CHANGELOG opened for Phase 16
│   │   ├── Alembic ``i9d0e1f2a3b4`` extends
│   │   │   ``ck_agent_run_operations_op_name`` with
│   │   │   ``'rollback'``; ``VALID_OP_NAMES`` updated
│   │   └── ``RollbackError`` family in ``operations.py``:
│   │       ``RollbackTargetNotFound`` /
│   │       ``RollbackAmbiguous`` / ``RollbackInvalid`` /
│   │       ``RollbackStale``
│   ├── Sprint 16.1 — ``pql.rollback`` primitive             ✅
│   │   ├── ``pointlessql/pql/_rollback.py`` calls
│   │   │   ``DeltaTable.restore(target_version, ...)``
│   │   │   (atomic, new commit, CDF-safe).  8 tests cover
│   │   │   happy-path / audit-row-shape / target-not-found /
│   │   │   ambiguous / invalid (creation op) / stale-without-
│   │   │   force / stale-with-force-succeeds / multi-op-
│   │   │   resolved-by-ordinal.
│   │   ├── ``pql.rollback`` exposed on the ``PQL`` class;
│   │   │   forwards client / engine / agent_run_id from
│   │   │   ``self``
│   │   └── ``operation_context`` skips lineage / row-edges /
│   │       column-edges / value-changes hooks for
│   │       ``op_name='rollback'``
│   ├── Sprint 16.2 — Cascade detection + preview API       ✅
│   │   ├── ``pointlessql/services/cascade.py``:
│   │   │   ``find_downstream_tables`` walks
│   │   │   ``lineage_row_edges`` + ``lineage_column_map``,
│   │   │   marks via=``row``/``column``/``both``, sorted by
│   │   │   edge_count desc
│   │   └── ``GET /api/runs/{run_id}/rollback-preview?target=…``
│   │       returns version delta + ``is_stale`` +
│   │       ``intervening_writes`` + ``op_candidates`` +
│   │       ``downstream_warnings``; admin-only
│   └── Sprint 16.3 — Rollback UI + CloudEvent + replay     ✅
│       ├── ``/runs/{id}`` rollback card (admin-only) with
│       │   target dropdown + preview modal + stale checkbox
│       │   gate + downstream warning panel + multi-op
│       │   ordinal picker
│       ├── ``POST /api/runs/{run_id}/rollback`` spawns a
│       │   fresh ``agent_runs`` row, invokes ``pql.rollback``
│       │   on a worker thread, marks the run ``succeeded``
│       │   on completion
│       ├── CloudEvent ``pointlessql.rollback.executed``
│       │   joins ``AGENT_RUN_EVENT_TYPES`` (no migration
│       │   needed — existing CHECK is on ``outcome``, not
│       │   event_type)
│       ├── ``docs/e2e-walkthroughs/rollback.md`` headful
│       │   Firefox replay covers happy + stale paths,
│       │   refusal-mode CLI smoke, stop conditions
│       └── 6 route tests: admin-required, body-validation,
│           target-not-found, invalid-creation, stale-no-force,
│           happy-path-spawns-run-and-emits-event
│
├── Phase 16.5 — Delta-Branching                          ⏳ sketch
│   │
│   │   Proactive isolation: every agent run gets its own
│   │   zero-copy branch of the target schema, promote-to-main
│   │   goes through an approval, discard is free.  Full design
│   │   in ``project_delta_branching_idea.md``.
│   │
│   │   **Blocked on a load-bearing spike**: deltalake-python
│   │   1.5.0 has no first-class clone API.  The spike (16.5.0)
│   │   tests whether ``deltalake.transaction`` can build a
│   │   ``_delta_log/00...000.json`` from pre-built ``Add``
│   │   actions, falling back to a filesystem-level seed
│   │   (read+rewrite source ``_delta_log/*.json`` with absolute
│   │   parquet URIs).  If neither works, branching deep-copies
│   │   parquet (loses the zero-copy story) and the phase needs
│   │   a product re-decision.
│   │
│   │   Promotion uses pointer-swap with hard
│   │   ``BranchPromotionConflict`` if the parent moved during
│   │   branch lifetime.  Diff+replay stays a hypothetical
│   │   future topic.
│   │
│   ├── 16.5.0 — ``_delta_log/`` shallow-clone spike
│   ├── 16.5.1 — soyuz tag schema for branches
│   │   (``pointlessql.branch.*``)
│   ├── 16.5.2 — ``pql.branch(source_schema, branch_name)``
│   ├── 16.5.3 — ``pql.branch_discard(branch_schema)`` with
│   │   safety guards
│   ├── 16.5.4 — ``pql.branch_promote(branch_schema)`` v1
│   │   (pointer-swap only)
│   ├── 16.5.5 — Control-Room UI (list / promote / discard)
│   ├── 16.5.6 — Auto-cleanup job (opt-in)
│   └── 16.5.7 — End-to-end replay (headful Firefox)
│
├── Phase 17 — UI Overhaul                                ⏳ queued
│   │
│   │   Post-15.7 honest UX assessment surfaced three problems:
│   │   top navbar at 9 items is overloaded, run-detail at 10
│   │   tabs is creaking, and the lineage UI is linear (no DAG
│   │   view, three lineage axes are three separate pages with
│   │   no cross-correlation).  Substance is there; navigation
│   │   isn't.
│   │
│   │   Strategic ordering note: Phase 17 lands AFTER Phase 16
│   │   so the Rollback button has a UI home.  Skipping Phase 17
│   │   to jump to Phase 18 would mean the new audit cockpit
│   │   sits inside the same overloaded tab structure.
│   │
│   ├── Sprint 17.1 — Two-column sidebar (Databricks/Snowsight)
│   │   └── 60px icon-rail with main nav (Federation, Runs, SQL,
│   │       Workspace, Jobs, Alerts, Volumes, Dashboards, Admin)
│   │       + 240px contextual panel that swaps based on active
│   │       section.  Catalog tree becomes the panel for the
│   │       "Federation" icon.  Search moves to top-right.
│   ├── Sprint 17.2 — Run-detail consolidation
│   │   └── Today's 10 tabs (Cells / Operations / Rejects / Tool
│   │       calls / UC mutations / Lineage / Queries / Source /
│   │       Events / Audit log) collapse into 4 top-tabs with
│   │       sub-tabs: Overview (Source + Cells + Events),
│   │       Operations (Operations + Rejects + Queries + UC
│   │       mutations), Lineage (Row trace + Column trace +
│   │       Value changes), Audit (Tool calls + Audit log +
│   │       External writes).
│   ├── Sprint 17.3 — Lineage-DAG view
│   │   └── ``GET /runs/{id}/graph`` renders a unified
│   │       cytoscape.js / D3-force DAG joining
│   │       ``lineage_row_edges`` + ``lineage_column_map`` per
│   │       ``run_id``+``op_id``.  One box per table, arrows
│   │       labelled with ``transform_kind``.  Click a column →
│   │       highlights upstream + downstream simultaneously.
│   │       Replaces the linear vertical-list trace pages for
│   │       complex fan-in scenarios; the per-row trace pages
│   │       stay for deep-dive on one row_id.
│   ├── Sprint 17.4 — Table-detail entdichten
│   │   └── Today's table-detail page stacks metadata + tags +
│   │       permissions + effective-permissions + columns +
│   │       lineage badges + sync history vertically.  Convert
│   │       to tabs or accordion.  Search/filter on column list
│   │       for 50+ column tables.
│   └── Sprint 17.5 — Catalog-Browser search/filter
│       └── 20+ schemas in a catalog → today: scroll-wall.
│           Add search box at top, type-ahead filtering of
│           sidebar tree, recent-table list at top.
│
├── Phase 18 — Audit Cockpit                              ✅ closed
│   │
│   │   Volume reality after Phase 15.7: ~100-300 audit
│   │   datapoints per run × 100 runs/day = 10-30k datapoints
│   │   daily = 3-10M per year.  No human reads this row-by-row.
│   │   Phase 18 makes the data ACTIONABLE for the four real
│   │   personas (operator on-call, developer debug, compliance
│   │   auditor, daily trust glance) before the Phase 17 UI
│   │   overhaul lands.  Sequencing decision: Phase 18 ships
│   │   first against today's 10-tab layout; 18.1 cross-axis
│   │   links will get re-touched once Phase 17 collapses tabs.
│   │
│   ├── Sprint 18.0 — Audit-Read API backbone                 ✅
│   │   └── Three read-only JSON endpoints
│   │       (``GET /api/audit/summary|timeseries|anomalies``)
│   │       backed by a new
│   │       ``pointlessql/services/audit_aggregator.py`` doing
│   │       SQLite/Postgres-aware bucketing.  Self-tracking via
│   │       ``query_history.read_kind = 'audit_api'`` so cockpit
│   │       calls land in the same audit lake they query.
│   │       Severity classifier returns ``ok``/``warn``/``critical``
│   │       against an N-day rolling mean ± Nσ.
│   ├── Sprint 18.1 — Cross-axis navigation                   ✅
│   │   └── Operations-tab ``column edges`` + ``value changes``
│   │       badges become clickable links to
│   │       ``/runs/{id}?op_id=N#tab-lineage``; the run-detail
│   │       handler accepts ``?op_id=`` and threads it into
│   │       ``_load_operations_for_run`` /
│   │       ``_load_rejects_for_run`` /
│   │       ``_load_lineage_summary_for_run`` so the three
│   │       cross-axis tabs render filtered.  A "filtered to op
│   │       #N" chip with a Clear-filter button sits above the
│   │       tab strip.  Stale ``op_id`` falls back to unfiltered
│   │       (drill-downs are permissive).
│   ├── Sprint 18.2 — PII-aware masking                       ✅
│   │   └── New ``pii_resolver`` (TTL cache against soyuz
│   │       column-tags) + ``pii_mask`` helper renders
│   │       ``***@***.***`` style placeholders for tagged
│   │       columns in the row-trace value-change list.  Admin-
│   │       only ``POST /api/audit/pii/reveal`` returns the
│   │       cleartext and writes an ``audit_log`` row of
│   │       ``action='pii.value_revealed'``.  ``AuditSettings``
│   │       gains ``pii_mask_default`` + ``pii_cache_ttl_seconds``.
│   ├── Sprint 18.3 — Saved audit queries + CSV/JSON export   ✅
│   │   └── New ``saved_audit_queries`` table (Alembic
│   │       ``j0e1f2a3b4c5``) with five seeded starter rows.
│   │       Service enforces an explicit table allow-list via
│   │       sqlglot (SELECT-only, references only audit tables);
│   │       starter rows refuse PATCH/DELETE.  CRUD route at
│   │       ``/api/saved-audit-queries`` plus ``/run`` /
│   │       ``/export.csv`` / ``/export.json`` endpoints; new
│   │       admin-only ``/audit/queries`` HTML workbench.  Each
│   │       export writes a ``saved_audit_query.exported`` audit
│   │       row.  PDF deliberately deferred (CSV+JSON cover SOC2
│   │       / GDPR Art. 30 in practice).
│   ├── Sprint 18.4 — Run-diff lineage view                   ✅
│   │   └── New ``/runs/{a}/diff/{b}`` HTML route consuming
│   │       ``build_detail_diff`` + new
│   │       ``build_lineage_diff`` (reject-reason buckets,
│   │       value-change volume per table, row-count delta per
│   │       table).  ``GET /api/agent-runs/diff?detail=true``
│   │       carries the new ``lineage_diff`` payload.  Page
│   │       renders Chart.js bar charts for each lineage axis +
│   │       four +Δ stat cards on top.
│   └── Sprint 18.5 — Anomaly highlighting                    ✅
│       └── ``/api/home/summary`` carries an ``anomalies``
│           block ({warn, critical}) computed across rejects,
│           errored_ops, and external_writes.  Home page renders
│           a yellow/red banner when ≥ 1 metric breaches the
│           configured σ threshold; ``/runs/{id}`` shows an
│           anomaly chip at the top with the worst-offender
│           metric + observed-vs-baseline.  Saved-query alert
│           thresholds (``alert_threshold_count`` column on
│           ``saved_audit_queries``) reuse the existing alerts
│           machinery.  Email digest deferred to Phase 19.2
│           (Audit-Reviewer-Agent territory).
│
├── Phase 19 — Audit-Reviewer Agent + Grafana             ⏳ queued
│   │
│   │   Same Phase-18 backbone, three consumer paths.  This is
│   │   where audit infrastructure scales past human capacity:
│   │   agents reviewing agents, dashboards giving glance-trust,
│   │   compliance auditors pulling raw evidence.
│   │
│   │   Strategic ordering note: Sprint 19.0 (Grafana JSON)
│   │   could land BEFORE Phase 17 / 18 as a 1-day quick win
│   │   reading the existing tables directly.  The other
│   │   sub-sprints depend on the Phase-18 audit-API.
│   │
│   ├── Sprint 19.0 — Grafana dashboard (XS quick-win)        ✅
│   │   ├── ``docker-compose.grafana.yml`` overlay adds a
│   │   │   ``grafana/grafana-oss:latest`` service mounting the
│   │   │   ``pointlessql_data`` named volume read-write at
│   │   │   ``/data/pointlessql`` (RW because SQLite WAL-mode
│   │   │   needs the library to manage ``-shm``; ``:ro`` would
│   │   │   produce ``disk I/O error``).  Anonymous viewer +
│   │   │   admin password; ``GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS``
│   │   │   set to load the unsigned ``frser-sqlite-datasource``
│   │   ├── ``grafana/provisioning/datasources/pointlessql.yml``
│   │   │   pins UID ``pointlessql-sqlite`` (stable across
│   │   │   restarts so the dashboard JSON's panel→datasource
│   │   │   bindings survive)
│   │   ├── ``grafana/provisioning/dashboards/pointlessql.yml``
│   │   │   provider drops the dashboard into a ``PointlesSQL``
│   │   │   folder, ``allowUiUpdates: false`` (JSON is the
│   │   │   source of truth)
│   │   └── ``grafana/dashboards/pointlessql_audit.json`` —
│   │       10 panels (8 spec'd + Markdown header + datasource-
│   │       health smoke): runs/day, reject-rate vs 7-day
│   │       baseline, value-change-volume per table (red ≥1000),
│   │       external-write count stat (red ≥1), top-mutating-
│   │       principals (rows written via ``op_name IN ('merge',
│   │       'write_table')``), cost-gate denials, tool-call
│   │       latency table (Grafana ``Reduce → percentile``
│   │       transform; SQLite has no ``percentile_cont``),
│   │       EXPLAIN-cost histogram (``CAST(cost_est AS REAL)``).
│   │       SQLite-only by design — Postgres deferred to
│   │       Sprint 19.0.1.
│   ├── Sprint 19.1 — Audit-read tools in hermes-plugin-pointlessql
│   │   └── ~10 new tools that wrap the Phase-18 audit-API:
│   │       ``pql_get_run``, ``pql_list_recent_runs``,
│   │       ``pql_query_row_lineage``, ``pql_query_column_lineage``,
│   │       ``pql_query_value_changes``, ``pql_query_rejects``,
│   │       ``pql_query_external_writes``, ``pql_query_history_audit``,
│   │       ``pql_audit_summary``, ``pql_anomaly_check``.  Each
│   │       tool's call is logged into ``query_history`` so the
│   │       audit-of-audit gap doesn't open.
│   ├── Sprint 19.2 — Audit-Reviewer-Agent reference run
│   │   └── Hermes-driven daily run at 06:00 that calls the
│   │       audit-summary + anomaly tools, drafts a Markdown
│   │       summary of yesterday's anomalies, posts to a
│   │       configurable webhook (Slack / email).  Becomes the
│   │       reference implementation for "agents reviewing
│   │       agents" — first concrete demonstration of the
│   │       supervision-first thesis.
│   └── Sprint 19.3 — Compliance-Bot + Incident-Responder demos
│       └── Two more Hermes flows on the same tool surface:
│           ad-hoc "welche Runs schrieben Q3 auf PII-Spalten?"
│           via Slack-bot, and "was hat Run X kaputt gemacht?"
│           via interactive chat.  Validates the three-persona
│           thesis (operator / auditor / responder all served
│           from the same endpoint set).
│
├── Phase 20 — Forensics + Retention                      ⏳ queued
│   │
│   │   The orthogonal post-cockpit governance pass.  Audit
│   │   data has been *captured* (15.x), *displayed* (17), and
│   │   *queried* (18, 19) — now it needs lifecycle management,
│   │   compliance-grade external streaming, and the time-axis
│   │   visualization that Delta time-travel enables.
│   │
│   ├── Sprint 20.0 — CloudTrail / Audit-Stream forwarder
│   │   └── New ``services/audit_forwarder.py`` that, on
│   │       ``OperationRecorder.commit()``, additionally fires a
│   │       CloudTrail-PutCustomEvent (or AWS Audit-Manager /
│   │       GCP Cloud Audit Logs / Azure Activity Log custom
│   │       event) for ~5-10 governance-relevant event types:
│   │       run-created, external-write-detected, rollback-
│   │       executed, policy-violation, cost-gate-denied,
│   │       audit-export-issued.  Settings-driven (off by
│   │       default).  S3-bucket sink as the on-prem-friendly
│   │       alternative for non-cloud deployments.
│   ├── Sprint 20.1 — PII detection + masking layer
│   │   └── Pattern-based + soyuz-tag-driven PII column
│   │       identification.  ``lineage_value_changes`` insert
│   │       hook can opt to hash/redact PII columns before
│   │       persist.  ``settings.audit.pii_mode`` switch:
│   │       ``store_clear`` (today) | ``hash_only`` |
│   │       ``redact_with_audit_log``.  Closes the
│   │       ``customer_email`` Klartext compliance gap.
│   ├── Sprint 20.2 — Lineage retention policies
│   │   └── Per-table TTL on the four lineage tables
│   │       (``lineage_row_edges``, ``lineage_row_rejects``,
│   │       ``lineage_column_map``, ``lineage_value_changes``).
│   │       Background job (uses Phase-12 scheduler) prunes rows
│   │       older than configurable threshold per table.
│   │       Defaults: row_edges 365d, value_changes 730d (longer
│   │       because compliance), column_map forever (small
│   │       volume).  Pruning logged in audit_log itself so
│   │       deletion is itself auditable.
│   ├── Sprint 20.3 — Time-travel value queries in UI
│   │   └── Surface what we already capture in
│   │       ``agent_run_operations.delta_version_after``: a
│   │       table-detail "view at version N" picker, a row-
│   │       trace "what did this row look like 30 days ago"
│   │       button.  Wraps ``DeltaTable.load_as_version(N)``;
│   │       UI hides the version-arithmetic.
│   └── Sprint 20.4 — Soyuz columnLineage / valueChange ingest
│       └── Cross-tool sibling to the PointlesSQL-only stack:
│           teach soyuz-catalog's ``services/lineage_service``
│           to ingest OpenLineage ``columnLineage`` and (new)
│           ``valueChange`` facets so non-PointlesSQL writers
│           on UC-managed Delta tables also surface in the
│           lineage graph.  Originally sketched as Phase 15.8
│           in the 15.6 close memo.  Lives here because it's a
│           soyuz-side change, not a PointlesSQL one — the
│           Phase-20 grouping is convenience for tracking, not
│           coupling.
│
├── Some-day — Public launch + external distribution      💤 unscheduled
│   │
│   │   This is the moment the stack goes from "my project" to
│   │   "something strangers can try" — and importantly, from
│   │   "code on my laptop" to "verifiable trust infrastructure
│   │   in the EU AI Act / SOC2 / GDPR sense".  Apache 2.0 is
│   │   locked (UC-compatible, no ethical-use-clause drama).
│   │
│   │   Strategic framing (from the Phase-15.7-close strategy
│   │   conversation):
│   │
│   │   - Audit infrastructure ≠ ordinary OSS.  Compliance
│   │     buyers REQUIRE source-availability — closed-source
│   │     audit tools fail the third-party-auditor test.  OSS
│   │     here is an asset, not a giveaway.
│   │   - Empirical OSS-infra track record: Sentry, dbt, Grafana,
│   │     HashiCorp, Confluent all spent 2-4 years OSS-only
│   │     before commercial offering.  "Sales platform first"
│   │     is the wrong move for solo-founder infra.
│   │   - The commercial wedge is NOT the OSS code.  Candidates:
│   │     hosted SaaS (PointlesSQL Cloud), enterprise edition
│   │     (SSO/SAML/multi-tenant audit storage), cryptographic
│   │     anchor service (closed/hosted, the shoreguard
│   │     Provenance Log angle), certified compliance reports.
│   │     None of these compete with Apache-2.0 community edition.
│   │
│   ├── Pre-OSS-release hygiene (1 week of work)         ⏳
│   │   ├── EUIPO trademark filings for ``PointlesSQL``,
│   │   │   ``soyuz-catalog``, ``shoreguard``.  Classes 9
│   │   │   (software), 42 (SaaS), 41 (consulting).  ~€2550 total,
│   │   │   10-year protection.  DE-only fallback at ~€290 each
│   │   │   if EU-wide too costly upfront.  Trademark is
│   │   │   non-optional for any future commercial wedge.
│   │   ├── ``NOTICE.txt`` in each core repo establishing
│   │   │   author + Apache 2.0 + Copyright 2026 Florian
│   │   │   Hofstetter.  Anchors solo-author copyright record
│   │   │   for any future Founder Resolution / IP-transfer to
│   │   │   incorporated entity.
│   │   ├── ``CONTRIBUTING.md`` + ``CODE_OF_CONDUCT.md`` +
│   │   │   ``SECURITY.md`` per repo.  Defines governance
│   │   │   *before* community arrives.
│   │   ├── CLA-Bot (CLA-Assistant or EasyCLA) on every PR.
│   │   │   CNCF-CLA template adapted.  Without CLA, third-party
│   │   │   contributions fragment copyright and block any
│   │   │   future dual-licensing option.
│   │   ├── Domain ownership: pointlessql.dev/.io/.com,
│   │   │   shoreguard.io, soyuz-catalog.io.  ~€50/year each.
│   │   └── Private STRATEGY.md (NOT in repo): commercial-wedge
│   │     decision document.  "Hosted PointlesSQL Cloud +
│   │     cryptographic anchor as the closed wedge" or whatever
│   │     it is.  Clarity for founder, signal for investors
│   │     later.  NOT public until commercial offering ships.
│   │
│   ├── Big-bang launch day (1 day, coordinated)         ⏳
│   │   ├── ``Show HN: PointlesSQL — per-cell lineage for Delta
│   │   │   Lake via CDF`` posted Mon/Tue 8-10 UTC for European
│   │   │   prime time + US morning.  Demo screenshot, link to
│   │   │   blog post #1, mention soyuz + shoreguard as siblings.
│   │   ├── Twitter / Mastodon thread (10-12 tweets) with
│   │   │   architecture diagrams.  Tag data-eng-Twitter
│   │   │   gravity (Benn Stancil, Tristan Handy, Pedram Navid,
│   │   │   Chad Sanderson, Julien Le Dem).
│   │   ├── Reddit posts: r/dataengineering + r/programming.
│   │   ├── LinkedIn long-form post.
│   │   ├── Blog post #1: *"Why we built per-cell lineage on
│   │   │   Delta CDF"* — published same day, linked from HN.
│   │   └── Hacker News frontpage hit-rate target: 30%.  Even a
│   │       moderate showing (~50 upvotes, 200 visitors) creates
│   │       the "Sarah saw this in our internal Slack" pathway
│   │       that converts to recruiter / engineer outreach.
│   │
│   ├── Conference circuit (3-12 month lead time)        ⏳
│   │   ├── DataCouncil — "How per-cell lineage closes the
│   │   │   EU-AI-Act audit gap".  Springs 2026 / Falls 2027.
│   │   ├── Subsurface — "Building Z3-verified policies for
│   │   │   agent sandboxes" (shoreguard angle).
│   │   ├── dbt Coalesce — "Comparing PointlesSQL audit-substrate
│   │   │   to Unity Catalog Lineage".
│   │   ├── Berlin Buzzwords — DE local, easier to land first
│   │   │   slot, builds CFP-pipeline credibility.
│   │   ├── Big Data LDN — UK enterprise audience, compliance
│   │   │   buyer-aligned.
│   │   └── KubeCon EU (longer shot) — shoreguard / OpenShell
│   │       angle if maturity allows.
│   │
│   ├── Sustained visibility (months 1-12 post-launch)   ⏳
│   │   ├── Blog post series, 1 every 3 weeks: per-cell lineage
│   │   │   for EU AI Act, Delta CDF deep-dive, comparing to UC
│   │   │   Lineage, Z3-verified policies, cross-tool lineage.
│   │   ├── Twitter daily: 3-5 substantive posts/week.  Reply
│   │   │   to Data-Eng-Twitter threads with substance not spam.
│   │   ├── LinkedIn updated: headline "Building open-source
│   │   │   data audit + governance — PointlesSQL, soyuz,
│   │   │   shoreguard".  About-section + skills tuned for
│   │   │   recruiter sourcing tools (HireEZ / Gem / SeekOut
│   │   │   scrape LinkedIn keywords, not GitHub).
│   │   └── Office Hours outbound: 1:1 calls with engineering
│   │       managers at target acquirers (Snowflake, Atlan,
│   │       Acryl Data, OneTrust, Drata, Vanta, Snowplow,
│   │       Microsoft Purview team) once first-run substance
│   │       is shipped (Phase 18+ done).
│   │
│   ├── Packaging + distribution (the original Some-day)  ⏳
│   │   ├── GHCR packages flipped private → public for both
│   │   │   ``pointlessql`` and ``soyuz-catalog`` images; the
│   │   │   Phase-10-deferred ``docs/e2e-walkthroughs/packaging.md``
│   │   │   dogfood replay finally runs end-to-end without the
│   │   │   PAT dance
│   │   ├── Multi-arch (amd64 + arm64) image builds via docker
│   │   │   buildx — the single-sprint work that Phase 10
│   │   │   couldn't justify for an audience of one
│   │   ├── Public PyPI publish of ``soyuz-catalog-client``
│   │   │   (first) and the ``pointlessql`` wheel (second);
│   │   │   replaces Phase 10's private git-tag pin for the
│   │   │   general audience while keeping the tag-pin option
│   │   │   available for consumers who prefer reproducible
│   │   │   git-based installs
│   │   ├── Optional: Helm chart for K8s deployments,
│   │   │   generalising "runs on a €15/month vServer" to
│   │   │   "runs on a cluster"
│   │   └── README / docs pass: swap the "functional Databricks
│   │       clone" alpha framing for the post-15.7 honest
│   │       positioning: *"per-cell auditable lakehouse for
│   │       agent-driven data engineering, EU-AI-Act-native"*.
│   │
│   └── Commercial offering (12-24 months post-OSS)      ⏳
│       ├── Identify 3-5 paying design partners from the
│       │   community (mid-cap retailer with EU-AI-Act compliance
│       │   pressure, healthcare-data-engineering, financial
│       │   reporting under ASC 606).  €500-2k/month each as
│       │   willingness-to-pay validation.
│       ├── Co-design the commercial wedge with design partners
│       │   — what they actually want to pay for vs what they
│       │   get free.  Likely: hosted SaaS, certified
│       │   compliance reports, multi-tenant audit retention,
│       │   SSO/SAML, cryptographic anchor service.
│       ├── UG/GmbH incorporation (~€500 + Notar) once a
│       │   contract template + 2 verbal-LOIs exist.  Founder
│       │   Resolution transfers pre-incorporation IP to entity.
│       └── First commercial offering live, based on what design
│           partners actually paid for — not what was guessed
│           upfront.  Expected revenue trajectory: €0 → €60k ARR
│           year 1 → €200-500k year 2 → €1-3M year 3 (typical
│           OSS-infra commercial-bootstrap curve).
│
├── Icebox — enterprise-audit follow-ups                  🧊 on ice
│   │
│   │   Sprint 48 ported six of nine shoreguard-fresh audit
│   │   patterns. The three skipped ones are legitimately wanted
│   │   in enterprise / compliance scenarios but do not pay for
│   │   themselves at the single-node-vServer scale today. Parked
│   │   here so the Some-day Launch's enterprise-positioning pass
│   │   knows where to look; trivially promotable to a numbered
│   │   sprint when a real consumer asks.
│   │
│   ├── Audit export with sha256 digest + manifest  🧊 on ice
│   │   ├── CLI ``pointlessql audit export --out FILE`` that
│   │   │   mirrors ``/admin/audit/export`` but writes three
│   │   │   mode-0600 files: data (JSON or CSV), ``FILE.sha256``
│   │   │   in ``sha256sum``-compatible format, and
│   │   │   ``FILE.manifest.json`` carrying export timestamp,
│   │   │   filters applied, entry count, tool version
│   │   ├── Optional: a "download with manifest" toggle in the
│   │   │   web viewer that ships the three files as a
│   │   │   ``.tar.gz`` bundle so the browser-only admin path
│   │   │   also produces tamper-evidence artefacts
│   │   └── Why deferred: the compliance conversation where a
│   │       third-party auditor demands a verifiable export has
│   │       not happened yet. Pattern verbatim in
│   │       ``shoreguard-fresh/shoreguard/api/cli_audit.py:34-169``
│   │       when the need appears
│   │
│   ├── Audit-to-SIEM export sinks                  🧊 on ice
│   │   ├── Opt-in fan-out from ``log_action`` to external
│   │   │   observability targets — ``audit.sink_stdout_json``
│   │   │   (for container-log harvesters), ``audit.sink_syslog``
│   │   │   (RFC 5424 over UDP/TCP/TLS), ``audit.sink_webhook``
│   │   │   (POST per event, HMAC-signed payload)
│   │   ├── Each sink is a named ``AuditSink`` subclass
│   │   │   registered via entry-point or settings-driven
│   │   │   construction; dispatch failures swallowed + logged
│   │   │   (never blocks the primary DB write)
│   │   └── Why deferred: nobody running on a €15/month vServer
│   │       has a SIEM. Re-open once PointlesSQL has its first
│   │       multi-tenant / enterprise-positioned consumer
│   │
│   └── Retroactive action-string rename to ``resource.verb``  🧊 on ice
│       └── Churn-only refactor of the 25 pre-Sprint-48 action
│           strings (``update_catalog`` → ``catalog.updated``, …)
│           to fully align with the convention Phase 12 adopts
│           for new events. Pure ergonomics for the
│           ``/admin/audit`` dropdown — no behavioural change —
│           so only worth doing the day the whole fleet gets
│           rewired (e.g. a release-notes-worthy version bump)
│
└── Explicitly out of scope (probably ever)
    ├── Reimplementing the Unity Catalog REST API — that is
    │   soyuz-catalog's job; PointlesSQL is a consumer
    ├── Building a query engine — PointlesSQL starts engine
    │   kernels (Pandas/Polars/Spark/DuckDB) and delivers UC
    │   config; it does not parse SQL or plan queries itself
    ├── Running the JVM upstream UC server — soyuz-catalog is
    │   the spec-compatible replacement
    └── Federated query planning across multiple foreign
        catalogs — that is a query-engine concern
```

## How to update this file

- **When a sprint lands:** flip its marker to ✅, append
  `(<short-sha>)`, and add a one-line `CHANGELOG.md` entry under
  `## [Unreleased]`.
- **When a new sprint is planned:** add it under the current phase
  with ⏳ and a short bullet list of the concrete scope. Keep it
  short — this is a tracker, not a design doc. Design details go
  in ADRs under `docs/adr/`.
- **When scope shifts:** edit the bullet list in place rather than
  adding a "scope change" section. The git history of this file
  *is* the scope-change log.
- **When a phase completes:** flip the phase marker to ✅ and
  move on. Do not delete completed phases — they are the record
  of what "done" meant.
- **When closed phases stack up:** roll older completed phases
  out of `ROADMAP.md` into [`ROADMAP_ARCHIVE.md`](ROADMAP_ARCHIVE.md)
  using the existing collapse pattern (one-line summary in a
  table, full detail moved verbatim to the archive).  Trigger:
  whenever `ROADMAP.md` exceeds ~2000 lines or whenever a
  completed phase has no expected reference for >3 months.
  Recently-closed phases (last ~30 days) stay full-detail in
  `ROADMAP.md` because they're still load-bearing for follow-up
  conversations.

This file is read first by every new Claude Code session (see
[`CLAUDE.md`](CLAUDE.md)).
