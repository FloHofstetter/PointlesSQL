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
├── Phase 12.9 — LLM-friendly modularization (full-stack carve-up)  ✅ closed 2026-05-05 (Sprint 76–95: 90d40b8)
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
│   │   **Closed 2026-05-05.**  All 19 sprints (76–95) landed.
│   │   Frontend is 99.3 % ESM (28 modules / 5852 LOC); the 40-LOC
│   │   ``help_popovers.js`` IIFE is the only non-ESM file left and
│   │   is deliberately retained — it re-runs on every
│   │   ``htmx:afterSwap`` and re-importing it as a module would
│   │   break the popover-init flow.  ``bootstrap.js`` (132 LOC)
│   │   stays permanent: Alpine's synchronous x-data DOM-walk needs
│   │   the bridge from ESM-namespaced factories to ``window.*``.
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
├── Phase 16.5 — Delta-Branching                          ✅ closed (2026-04-29)
│   │
│   │   Proactive isolation: every agent run gets its own
│   │   zero-copy branch of the target schema, promote-to-main
│   │   goes through an approval, discard is free.  Full design
│   │   in ``project_delta_branching_idea.md``.
│   │
│   │   **Spike verdict (Sprint 16.5.0, 2026-04-29 —
│   │   ADR-0003)**: the zero-copy ideal is NOT viable on cloud
│   │   storage with deltalake-python 1.5.0.  Absolute paths in
│   │   Add actions get re-anchored to the table root by the
│   │   delta-rs reader (file-not-found); ``file://`` URIs hit
│   │   the same path.  A symlink-into-branch-dir + relative
│   │   path fallback works on local FS (5/5 rows, append on
│   │   branch leaves source untouched, zero storage overhead)
│   │   but cannot run on S3/GCS/Azure where symlinks don't
│   │   exist.
│   │
│   │   **Adopted strategy**: hybrid — symlink-clone on local
│   │   FS, deep-copy on cloud storage, controlled by a new
│   │   ``branch.cloud_strategy`` knob in :class:`BranchSettings`
│   │   (``'deep_copy'`` | ``'error'``).  Honest zero-copy
│   │   story for local dev (the primary early-adopter
│   │   deployment), working fallback for cloud deployers.
│   │
│   │   Promotion uses pointer-swap with hard
│   │   ``BranchPromotionConflictError`` if the parent moved
│   │   during branch lifetime.  Diff+replay stays a hypothetical
│   │   future topic.
│   │
│   ├── 16.5.0 — ``_delta_log/`` shallow-clone spike            ✅ done (bd15265)
│   │   └── See ``docs/adr/0003-delta-branching-spike.md`` for
│   │       the three approaches tried and their results.
│   │       Verdict above; reproducer at ``tmp/spike_16_5_0.py``
│   │       (not committed — re-run from ADR if needed).
│   ├── 16.5.1 — soyuz tag schema for branches              ✅ done (64a7d31)
│   │   (``pointlessql.branch.*``).  ``services/branch_tags.py``
│   │   reserves the namespace, ships :class:`BranchTags` typed
│   │   read + apply / set-status / mark-pre-promote-backup
│   │   helpers in both async (UnityCatalogClient, web routes)
│   │   and sync (raw soyuz Client, ``pql/_branch.py``)
│   │   flavours.  No soyuz schema change — the generic ``tags``
│   │   table accepts arbitrary keys.
│   ├── 16.5.2 — ``pql.branch(source_schema, branch_name)``  ✅ done (64a7d31)
│   │   ``pointlessql/pql/_branch.py`` orchestrates the create
│   │   flow: classify storage scheme, pick strategy, create
│   │   UC schema + tables, clone parquets via
│   │   ``DeltaTable.create_write_transaction``, stamp branch
│   │   tags, emit ``pointlessql.branch.created.v1`` CloudEvent.
│   │   Plus :class:`BranchSettings` (cloud_strategy
│   │   default='error', auto_cleanup_*),
│   │   ``MetadataMixin.delete_schema()``, three new event types
│   │   in ``governance_events.py``.
│   ├── 16.5.3 — ``pql.branch_discard(branch_schema)`` with  ✅ done (3b72261)
│   │   safety guards.  Idempotent for already-discarded
│   │   branches.  Refuses promoted branches
│   │   (:class:`BranchInUseError`).  Refuses non-branch
│   │   schemas (:class:`BranchNotFoundError`).
│   │   ``shutil.rmtree`` on the local-FS storage tree
│   │   (unlinks symlinks rather than recursing).  New
│   │   ``branch_audit_log`` table (Alembic ``o5k7m9p2r4t6``)
│   │   captures create / promote / discard / auto_cleanup
│   │   rows so audit trails survive the UC schema's
│   │   deletion.
│   ├── 16.5.4 — ``pql.branch_promote(branch_schema)`` v1    ✅ done (36baac1)
│   │   (pointer-swap only).  Atomic two-step rename: parent →
│   │   ``{parent}_pre_promote_<ts>`` (backup), branch →
│   │   parent.  Per-table conflict detection up front:
│   │   :class:`BranchPromotionConflictError(table, expected,
│   │   actual)` raised BEFORE any UC mutation.  Best-effort
│   │   revert on second-rename failure.
│   │   ``pql.branch_promote_preview()`` is the dry-run for the
│   │   UI — same conflict-detection, no side effects.
│   ├── 16.5.5 — Control-Room UI                            ✅ done (ac9d18a)
│   │   ``pointlessql/api/branches_routes.py`` ships 7 routes
│   │   (3 HTML, 4 JSON).  ``pages/branches.html`` is the
│   │   searchable + status-filtered list.
│   │   ``pages/branch_detail.html`` carries metadata cards,
│   │   parent-version table, audit-log tail, and an admin-only
│   │   Danger-zone with Preview / Promote / Discard buttons.
│   │   Sidebar icon-rail entry (admin-only) under
│   │   ``bi-diagram-3``.
│   ├── 16.5.6 — Auto-cleanup job (opt-in)                  ✅ done (7cf3743)
│   │   ``services/branch_cleanup.py::cleanup_old_branches``
│   │   walks UC schemas, picks ``status='active'`` branches
│   │   past ``branch.auto_cleanup_retention_days``, calls
│   │   ``discard_branch_schema`` on each.  Default-disabled.
│   │   Single-discard failures are logged + counted but
│   │   never abort the loop.  Registered as scheduler kind
│   │   ``"branch_cleanup"`` AND as a background task in the
│   │   FastAPI lifespan; both share the same helper.
│   └── 16.5.7 — End-to-end replay (headful Firefox)        ✅ done
│       ``docs/e2e-walkthroughs/branches.md`` chains: seed
│       parent → branch → write to branch → prove parent
│       untouched → preview-promote → break with competing
│       parent write → discard → re-branch → clean promote.
│       Inspects symlink layout, audit-log, governance_events.
│       Local FS / symlink strategy only — cloud-side discard
│       + promote stay deferred follow-ups.
│
├── Phase 17 — UI Overhaul                                ✅ closed
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
│   ├── Sprint 17.1 — Two-column sidebar (Databricks/Snowsight)  ✅
│   │   └── 60px icon-rail with main nav (Federation, Runs, SQL,
│   │       Workspace, Jobs, Alerts, Volumes, Dashboards, Admin)
│   │       + 240px contextual panel that swaps based on active
│   │       section.  Catalog tree becomes the panel for the
│   │       "Federation" icon.  Cmd+K search trigger stays in the
│   │       topbar; user dropdown lifts out of nav_links into its
│   │       own ``components/user_menu.html`` so the topbar carries
│   │       only brand + search + user.  ``components/nav_links.html``
│   │       is now drawer-only (mobile), and the offcanvas drawer
│   │       carries section panel + nav links + user menu so phones
│   │       have a single navigation surface.
│   ├── Sprint 17.2 — Run-detail consolidation                ✅
│   │   └── Today's 10 tabs (Cells / Operations / Rejects / Tool
│   │       calls / UC mutations / Lineage / Queries / Source /
│   │       Events / Audit log) collapse into 4 top-tabs with
│   │       sub-tabs: Overview (Source + Cells + Events),
│   │       Operations (Operations + Rejects + Queries + UC
│   │       mutations) + admin-only "Danger zone" rollback card
│   │       at the bottom of the Operations top-pane, Lineage
│   │       (single Lineage summary sub-pane today; Sprint 17.3
│   │       will add Row / Column / Value / Graph sub-tabs),
│   │       Audit (Tool calls + Audit log + External writes —
│   │       the unattributed_writes alert from Sprint 13.7.5
│   │       lifted out of the Operations tab into its own
│   │       sub-pane).  URL hash deeplinks (``#tab-lineage``,
│   │       ``#tab-ops``, …) keep working via a small inline
│   │       hash-listener that walks up the DOM and activates
│   │       the parent top-tab in addition to the targeted
│   │       sub-tab.  op_id-filter chip from Sprint 18.1 stays
│   │       above the top-tab strip so cross-axis drilldown
│   │       is unaffected.
│   ├── Sprint 17.3 — Lineage-DAG view                        ✅
│   │   └── New ``GET /api/runs/{run_id}/graph?op_id=...`` JSON
│   │       endpoint backed by a new
│   │       ``services/lineage_graph_builder.py`` that joins
│   │       ``lineage_row_edges`` + ``lineage_column_map`` per
│   │       ``run_id``+``op_id`` into a flat ``{nodes, edges}``
│   │       payload.  New Lineage-Graph sub-tab inside the
│   │       Sprint-17.2 Lineage top-pane embeds a cytoscape.js
│   │       canvas (cytoscape + dagre + cytoscape-dagre via
│   │       jsdelivr, scoped to the run-detail page so default
│   │       pages don't pay the bundle).  One box per touched
│   │       table; arrows labelled with the per-edge
│   │       ``transform_kinds`` aggregate; clicking a node
│   │       highlights its incident edges, clicking an edge opens
│   │       a side-panel listing the column-pairs, and clicking a
│   │       column name highlights every edge that touches it
│   │       (upstream + downstream simultaneously).  Auth gate
│   │       is ``require_supervisor`` (auditor scope OK).  The
│   │       per-row / per-column / per-value trace pages from
│   │       Phase 15 stay for deep-dive on one ``row_id``.
│   ├── Sprint 17.4 — Table-detail entdichten                 ✅
│   │   └── ``pages/table.html`` collapses from a single long
│   │       vertical stack of nine cards into six top-level tabs:
│   │       Overview (Metadata + Properties + PQL Snippet),
│   │       Preview (preview Alpine card with version selector),
│   │       Columns (columns table + Sprint-56 column-statistics
│   │       card + Sprint-15.6 column-lineage badges), Lineage
│   │       (existing ``components/lineage_card.html`` upstream
│   │       + downstream graph), Tags (``tags_editor.html``),
│   │       Permissions (``permissions_card.html`` with the
│   │       Sprint-30 effective-permissions toggle).  Existing
│   │       ≥20-column search box stays in the Columns tab; no
│   │       new client-side filter yet.  Card content + Alpine
│   │       factories preserved verbatim.
│   ├── Sprint 17.5 — Catalog-Browser search/filter           ✅
│   │   └── ``components/sidebar.html`` gains a debounced search
│   │       input above the tree.  Typing case-insensitive
│   │       substrings hides non-matching catalogs / schemas /
│   │       tables and force-expands branches that contain a
│   │       match, so partial hits are visible without manual
│   │       chevron-clicks.  A new "Recent tables" block above
│   │       the tree surfaces the last five
│   │       ``catalog.schema.table`` visits, written into
│   │       ``localStorage['pql.recentTables']`` by a small
│   │       ``base.html`` script (sibling of the Sprint-32
│   │       ``pql.recentCatalogs`` writer).  No server-side
│   │       changes — the existing ``/api/tree`` payload covers
│   │       the filter.
│   │
│   │   Phase-17 follow-ups, queued from the 2026-04-29 closing
│   │   replay (Playwright-MCP against headful Firefox; one
│   │   load-bearing bug surfaced — BUG-17.2-01 ``rollback``
│   │   ``x-data="..."`` collided with ``|tojson`` ``"`` chars,
│   │   fixed in commit ``fc940be``).  None of these block the
│   │   Phase-17 closing — they are polish + nice-to-have:
│   │
│   ├── Sprint 17.3.1 — Lazy-load cytoscape on Graph sub-tab  ✅ done (168960b)
│   │   └── Three ``<script defer>`` tags removed from
│   │       ``run_view.html``.  ``loadCytoscapeOnce()`` in
│   │       ``lineage_dag.js`` injects cytoscape + dagre +
│   │       cytoscape-dagre on demand the first time the
│   │       Graph sub-tab is activated, gated on Bootstrap's
│   │       ``shown.bs.tab`` event.  Promise-cached at module
│   │       level so repeated tab toggles re-use the same
│   │       load.  Fail-soft if the CDN is blocked.  Cache-bust
│   │       bumped to ``?v=sprint17.3.1``.
│   │
│   ├── Sprint 17.5.1 — Server-side tree search + DB recents  ✅ done (eb4d4c4)
│   │   └── New ``recent_tables`` table (Alembic
│   │       ``p6l8n0q3s5u7``) one row per ``(user_id,
│   │       table_full_name)``.  ``services/recents.py`` with
│   │       dialect-aware INSERT-ON-CONFLICT-DO-UPDATE upsert
│   │       + per-user TRIM_THRESHOLD=50.  Auto-write hook in
│   │       the catalog-table HTML detail handler.  Three new
│   │       routes — ``GET /api/tree/search?q=`` (q≥2,
│   │       capped@50, truncated flag), ``GET /api/recents``,
│   │       ``DELETE /api/recents``.  Sidebar keeps
│   │       localStorage as first-paint + no-auth fallback;
│   │       ``fetchRecents`` overrides asynchronously for
│   │       logged-in users.  Search box switches to server-side
│   │       at q.length≥2 with client-side fallback on error.
│   │       7 new pytest cases.
│   │
│   └── Sprint 17.6 — Lineage trace sub-panes                  ⏳ promoted to Phase 41
│       └── The Sprint-15 Row trace, Sprint-15.6 Column trace,
│       │   and Sprint-15.7 Value-changes drill-downs live on
│       │   separate ``/catalogs/.../trace`` pages today.
│       │   Promoted out of Phase 17 into its own ``Phase 41``
│       │   below so it doesn't get lost behind the Phase-39 /
│       │   Phase-40 feature pillars.  Trade-off (more JS in
│       │   the run-detail bundle vs fewer page-flips for the
│       │   audit-reviewer persona) is accepted in the new
│       │   phase entry.  Original defer rationale ("until
│       │   usage data shows the page-flip is the real
│       │   bottleneck") was over-cautious — keeping the
│       │   sub-pane work parked indefinitely behind a usage-
│       │   data signal that nobody is collecting.
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
│   ├── Sprint 18.5 — Anomaly highlighting                    ✅
│   │   └── ``/api/home/summary`` carries an ``anomalies``
│   │       block ({warn, critical}) computed across rejects,
│   │       errored_ops, and external_writes.  Home page renders
│   │       a yellow/red banner when ≥ 1 metric breaches the
│   │       configured σ threshold; ``/runs/{id}`` shows an
│   │       anomaly chip at the top with the worst-offender
│   │       metric + observed-vs-baseline.  Saved-query alert
│   │       thresholds (``alert_threshold_count`` column on
│   │       ``saved_audit_queries``) reuse the existing alerts
│   │       machinery.  Email digest deferred to Phase 19.2
│   │       (Audit-Reviewer-Agent territory).
│   ├── Sprint 18.6 — Anomaly inbox + run-list badge          ✅
│       └── Phase 18.6+ deepening of the closed cockpit.  Two
│           new columns on ``agent_runs``
│           (``anomaly_severity``, ``anomaly_metric``, set by
│           the run-finish hook + a ``backfill_run_anomalies``
│           helper) drive a new badge column on the ``/runs``
│           list.  New ``anomaly_acks`` table (Alembic
│           ``x4t6u8v0w2y4``) carries the cross-run inbox's
│           ack/snooze lifecycle; permanent or still-snoozed
│           acks hide rows from the default inbox view.
│           Three new endpoints: ``GET /api/audit/inbox``
│           aggregates anomalies across the run-anomaly metric
│           pair (rejects + errored_ops by default) and joins
│           ack state; ``POST /api/audit/anomaly-acks`` +
│           ``DELETE /api/audit/anomaly-acks/{id}`` manage the
│           lifecycle.  New HTML page at ``/audit/inbox`` with
│           filter bar + ack/snooze actions.  All new routes
│           are auditor-scope (admin cookie passes, supervisor
│           does not).  Sprints 18.7 (Audit-FTS), 18.8
│           (reverse-index "runs by table"), 18.9 (cell-level
│           run-diff), 18.10 (anomaly-memoization, contingent)
│           queued in the Phase 18.6+ plan.
│   ├── Sprint 18.7 — Full-text search across audit lake     ✅
│       └── New SQLite FTS5 virtual table ``audit_search``
│           (Alembic ``y5u7v9w1x3z5``) populated by triggers
│           on ``agent_runs`` / ``agent_run_operations`` /
│           ``query_history`` / ``agent_run_tool_calls`` /
│           ``audit_log``.  Tokenizer is
│           ``unicode61 separators '._-'`` so UC FQNs match
│           component-wise (a search for ``silver`` matches
│           ``main.silver.orders``).  New auditor-scope
│           endpoint ``GET /api/audit/search?q=…&axis=…``
│           returns ranked snippets; new HTML page
│           ``/audit/search`` calls it via fetch.  Postgres
│           deployments skip the migration and the route
│           returns ``available=false`` with no rows.  Service
│           module exposes ``install_index`` (used by tests) +
│           ``rebuild_index`` (emergency recovery hook).
│           Alembic ``include_object`` filter widens to skip
│           the FTS5 shadow tables so ``alembic check`` stays
│           green.
│   ├── Sprint 18.8 — Runs-by-table reverse index            ✅
│       └── Flips the forward "what did this run touch?"
│           direction.  New auditor-scope endpoint
│           ``GET /api/audit/by-table?fqn=…&kind=…``  with
│           three relationship axes: ``touched`` (declared in
│           ``AgentRun.tables_touched``), ``written`` (op
│           ``target_table`` *or* ``lineage_value_changes``
│           target), ``read`` (referenced via
│           ``query_history_tables``).  No new schema —
│           tables_touched JSON containment uses
│           dialect-portable ``LIKE '%"<fqn>"%'``.  New HTML
│           page ``/audit/by-table/{fqn:path}`` with three
│           tabs that fetch on first activation.  Catalog
│           table-detail page header carries a "Runs that
│           touched this table" cross-link.
│   ├── Sprint 18.9 — Cell-level + column-lineage diff       ✅
│       └── ``GET /api/agent-runs/diff?detail=true`` and the
│           ``/runs/{a}/diff/{b}`` HTML page gain two new
│           payload sections: ``value_changes_diff`` (per
│           ``(target_table, op_id)`` bucket of divergent
│           cells, only-in-a, only-in-b — capped at top_k=50,
│           PII-masked unless admin) and ``column_lineage_diff``
│           (edge identity ``(op_id, source_table,
│           source_column, target_table, target_column)`` →
│           three buckets: only-in-a, changed
│           transform_kind/detail, only-in-b).  Two new
│           sub-tabs on the run-compare page render them; the
│           JSON shape feeds the Hermes ``pql_diff_runs`` tool
│           unchanged.  No new schema — both helpers query
│           existing ``lineage_value_changes`` /
│           ``lineage_column_map``.
│   └── Sprint 18.10 — Anomaly memoization                   🧊 deferred
│       └── Plan-marked contingent on a perf measurement:
│           land only when ``/audit/inbox`` or
│           ``/audit/anomalies`` p95 breaks 2s on a real
│           ≥10⁴-run audit lake.  Today's instances stay well
│           below that threshold (live aggregator returns
│           sub-100ms on the fixture suite), so the cache
│           table + cron rebuild is left as a sketch.  Re-open
│           when a deployment reports the breach.
│
├── Phase 19 — Audit-Reviewer Agent + Grafana             ✅ closed
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
│   ├── Sprint 19.1 — Audit-read tools + new ``auditor`` scope    ✅
│   │   ├── New ``auditor: bool`` column on ``api_keys`` (Alembic
│   │   │   ``k1f2a3b4c5d6``) + matching ``KeyEntry`` field +
│   │   │   middleware ``request.state.api_key_auditor`` +
│   │   │   ``require_auditor`` dependency.  Privilege ladder:
│   │   │   admin > auditor (tenant-wide audit reads) > supervisor
│   │   │   (per-run inspection) > agent.  ``require_supervisor``
│   │   │   now also accepts the auditor scope so a single auditor
│   │   │   key drives both the tenant-wide ``/api/audit/*``
│   │   │   aggregates AND the per-run ``/audit/<axis>`` reads.
│   │   │   PII reveal stays admin-only.
│   │   ├── Five new run-scoped JSON endpoints under
│   │   │   ``/api/agent-runs/{run_id}/audit/<axis>``: ``lineage``
│   │   │   (wraps ``load_lineage_summary_for_run``), ``rejects``
│   │   │   (wraps ``load_rejects_for_run``), ``value-changes``
│   │   │   (always-masked for non-admin auditor calls — cleartext
│   │   │   stays via the existing admin-only PII-reveal route),
│   │   │   ``external-writes`` (wraps
│   │   │   ``load_unattributed_for_run``), ``column-lineage``
│   │   │   (queries ``lineage_column_map`` directly).
│   │   ├── New tenant-wide ``GET /api/audit/history`` route
│   │   │   (paginated ``query_history`` walk).  Default response
│   │   │   excludes ``read_kind='audit_api'`` rows so an agent
│   │   │   can't loop on its own audit-of-audit breadcrumbs;
│   │   │   ``?include_audit_api=true`` or
│   │   │   ``?read_kind=audit_api`` lift the filter on demand.
│   │   ├── Anomaly-baseline bugfix in
│   │   │   :func:`audit_aggregator.anomalies` — when ``since`` is
│   │   │   set, widen the underlying ``timeseries`` query by
│   │   │   ``window_days`` internally and trim the response back
│   │   │   to ``[since, until)`` afterwards.  Without this the
│   │   │   first bin of a ``since``-bounded call had an empty
│   │   │   baseline and false-positived as anomalous.  New
│   │   │   helper ``_bin_floor_compare_string`` does dialect-safe
│   │   │   bin-precision prefix compare for SQLite + Postgres.
│   │   ├── Audit-of-audit logging — every successful
│   │   │   ``/api/audit/*`` and ``/api/agent-runs/.../audit/*``
│   │   │   call records a ``query_history`` row with
│   │   │   ``read_kind='audit_api'`` so the cockpit traffic stays
│   │   │   visible in the same audit lake it queries.
│   │   ├── Plugin-side: ``hermes-plugin-pointlessql`` grows from
│   │   │   20 → 29 tools.  9 new audit-read tools
│   │   │   (``pql_list_recent_runs``, ``pql_audit_summary``,
│   │   │   ``pql_anomaly_check``, ``pql_query_history_audit``,
│   │   │   ``pql_query_row_lineage``, ``pql_query_column_lineage``,
│   │   │   ``pql_query_value_changes``, ``pql_query_rejects``,
│   │   │   ``pql_query_external_writes``) gated on the new
│   │   │   ``POINTLESSQL_AUDITOR_MODE`` opt-in, registered via
│   │   │   ``register_auditor_tools``.  ``pql_get_run`` dropped
│   │   │   from the original sketch — ``pql_run_summary`` already
│   │   │   covers it.
│   │   └── 16 new pytest cases in
│   │       ``tests/test_audit_routes_sprint_19.py`` covering the
│   │       privilege ladder (auditor 200 / supervisor 403 on
│   │       tenant-wide / supervisor 200 on per-run / normal 403
│   │       everywhere), audit-of-audit recursion guard, value-
│   │       change masking default, 404 on stale ``run_id``, and
│   │       the anomaly bugfix's structural shape.
│   ├── Sprint 19.2 — Audit-Reviewer-Agent reference run     ✅ closed (995490b)
│   │   ├── Sprint 19.2.0 — Daily-review Hermes job + auditor   ✅
│   │   │   key bootstrap.  New ``pointlessql admin
│   │   │   issue-auditor-key --name=…`` Typer subcommand on
│   │   │   the existing ``[project.scripts] pointlessql`` entry
│   │   │   point (no-arg invocation still starts uvicorn — the
│   │   │   Typer callback delegates).  Reference manifest at
│   │   │   ``docs/hermes-jobs/audit-reviewer-daily.json``
│   │   │   (cron ``0 6 * * *``, ``enabled_toolsets:
│   │   │   ["pointlessql"]``, deliver ``local`` by default,
│   │   │   prompt pinned to the closed-day window
│   │   │   ``[yesterday-00:00 UTC, today-00:00 UTC)``).  Sister
│   │   │   docs: ``docs/hermes-jobs/README.md`` (auth + install
│   │   │   notes; explains why ``hermes cron create`` cannot
│   │   │   carry the toolset flag yet) and
│   │   │   ``docs/e2e-walkthroughs/audit-reviewer-daily.md``
│   │   │   (operational runbook chaining the CLI key-issue,
│   │   │   ``~/.hermes/.env`` overlay, manual ``jobs.json``
│   │   │   patch, ``hermes cron run/tick``, and an audit-of-audit
│   │   │   verification via ``GET /api/audit/history``).
│   │   ├── Sprint 19.2.1 — Persistence + CloudEvents fan-out    ✅
│   │   │   + cockpit card.  Alembic ``l2g3a4b5c6d7`` adds
│   │   │   ``agent_reviews`` (id, run_id FK nullable, period_*,
│   │   │   severity ok/warn/critical, summary_md ≤ 50 KiB,
│   │   │   payload_json ≤ 1 MiB, delivered_to_json) +
│   │   │   ``review_destinations`` (admin-configured webhooks
│   │   │   with HMAC + per-destination ``min_severity`` gate).
│   │   │   New ``services/review_dispatcher.dispatch_review``
│   │   │   builds a ``pointlessql.agent_review.posted.v1``
│   │   │   CloudEvent, enumerates active destinations whose
│   │   │   severity gate passes, and reuses
│   │   │   ``alert_dispatcher.dispatch_webhook`` for HTTP+HMAC+
│   │   │   retry — saved-query alert plumbing without a single
│   │   │   line of new HTTP code.  Three new auditor-gated
│   │   │   routes (``POST /api/agent-reviews``,
│   │   │   ``GET /api/agent-reviews/latest``,
│   │   │   ``GET /api/agent-reviews/{id}``) plus four admin-gated
│   │   │   ``/api/admin/review-destinations`` routes (list /
│   │   │   create-with-secret-display / patch / delete) mirror
│   │   │   the existing admin-api-keys CRUD shape.  Cockpit:
│   │   │   "Latest review" card on ``/`` (admin-only — best-effort
│   │   │   query mirrors the Sprint-18.5 anomaly banner pattern)
│   │   │   + ``/agent-reviews/{id}`` detail page rendering the
│   │   │   Markdown summary, replay payload, and per-destination
│   │   │   fan-out log with status codes.  Plugin
│   │   │   ``hermes-plugin-pointlessql`` grows from 29 → 31 tools
│   │   │   (``pql_post_audit_review``, ``pql_get_latest_review``).
│   │   └── Sprint 19.2.2 — Wake-gate (skip clean days)         ✅
│   │       New ``scripts/audit-wake-gate.py`` — Hermes pre-run
│   │       script that hits ``GET /api/audit/anomalies`` for
│   │       rejects / errored_ops / external_writes against the
│   │       closed-day window, prints a ``#``-prefixed context
│   │       block (becomes prompt context on wake), and emits the
│   │       wake-gate JSON line as the LAST stdout line.  On
│   │       severity ``ok`` the line is ``{"wakeAgent": false,
│   │       "severity": "ok"}`` and Hermes skips the LLM round-trip
│   │       entirely (see ``hermes-agent/cron/scheduler.py:_parse_wake_gate``).
│   │       On ``warn``/``critical`` the agent wakes with the
│   │       pre-fetched anomaly numbers already in its prompt — no
│   │       redundant ``pql_anomaly_check`` calls.  Cost: ~3 HTTP
│   │       round-trips per clean day instead of an LLM call.
│   │       Reference manifest now carries ``script:
│   │       "scripts/audit-wake-gate.py"``; prompt updated to trust
│   │       the wake-gate's verdicts.  Walkthrough adds a
│   │       step-7 verification path (clean day → no LLM, seeded
│   │       reject row → LLM fires).
│   ├── Sprint 19.3 — Compliance-Bot (ad-hoc Slack/chat)        ✅
│   │   New ``GET /api/audit/principal-summary`` (auditor-gated)
│   │   route — paginated runs list + headline counters scoped to
│   │   one ``AgentRun.principal``, the missing piece between
│   │   Sprint 19.1's per-run audit axes and the "which runs did
│   │   X drive last quarter" persona question.  Plugin grows
│   │   31 → 32 tools (``pql_principal_summary``).  Ships
│   │   ``docs/hermes-jobs/compliance-bot.md`` (full system prompt
│   │   with the four-block answer skeleton + read-only safety
│   │   rules), ``docs/hermes-jobs/compliance-bot.json`` (Hermes
│   │   wake-on-message manifest with ``deliver: "origin"``), and
│   │   ``docs/e2e-walkthroughs/compliance-bot.md`` exercising
│   │   three canonical question shapes plus four safety
│   │   properties (refuses writes, always-masked
│   │   value-changes, no API-key leak in output bytes,
│   │   audit-of-audit history matches the tool surface).
│   └── Sprint 19.4 — Incident-Responder (interactive chat)     ✅
│       Multi-turn Hermes one-shot flow.  Takes a ``run_id`` up
│       front, walks down failing op → reject details → external-
│       write neighbours.  No new server endpoints — prompt-only
│       composition over the existing per-run audit-axis tools
│       from Sprint 19.1.  Ships ``docs/hermes-jobs/incident-
│       responder.{md,json}`` (system prompt with three-block
│       Finding/Evidence/Next skeleton + five constraints
│       including no-write-recommendations, rollback-as-option-
│       not-action, and proactive external-write callout),
│       ``scripts/seed-broken-run.py`` (synthetic broken
│       AgentRun + 3 ops + ~50 LineageRowRejects + 2
│       UnattributedWrite rows), and ``docs/e2e-walkthroughs/
│       incident-responder.md`` covering three drill-down
│       patterns and four safety properties.
│
├── Phase 20 — Forensics + Retention                      ✅ closed (2026-04-29)
│   │
│   │   The orthogonal post-cockpit governance pass.  Audit
│   │   data has been *captured* (15.x), *displayed* (17), and
│   │   *queried* (18, 19) — now it needs lifecycle management,
│   │   compliance-grade external streaming, and the time-axis
│   │   visualization that Delta time-travel enables.  Plan in
│   │   ``.claude/plans/plane-phase-20-vollst-ndig-vast-galaxy.md``.
│   │
│   ├── Sprint 20.0 — Audit-Stream forwarder (3 sink types)    ✅
│   │   ├── Alembic ``m3h4i5j6k7l8`` adds ``audit_sinks``
│   │   │   (id, name, type, config_json, is_active,
│   │   │   event_types_json, created_at) plus
│   │   │   ``governance_events`` (FK-free CloudEvents persistence
│   │   │   for events not tied to a single agent run).
│   │   ├── New ``services/audit_sinks.py`` ships three sink-type
│   │   │   dispatchers: ``webhook`` (reuses
│   │   │   ``alert_dispatcher.dispatch_webhook``), ``s3``
│   │   │   (httpx + ``services/aws_sigv4.py`` for SigV4 PUT,
│   │   │   works against MinIO / Cloudflare R2 via
│   │   │   ``endpoint_url``), and ``aws_cloudtrail`` (CloudTrail
│   │   │   Data Service PutAuditEvents).  ``dispatch_to_sinks``
│   │   │   honours per-sink ``event_types_json`` allow-lists.
│   │   ├── New ``services/governance_events.py`` exports five
│   │   │   constants — ``external_write.detected``,
│   │   │   ``policy.violated``, ``cost_gate.denied``,
│   │   │   ``audit_export.issued``, ``lineage.pruned`` —
│   │   │   plus ``emit_governance_event`` which persists +
│   │   │   fans out.  Off by default; gated by
│   │   │   ``POINTLESSQL_AUDIT_STREAM_ENABLED``.
│   │   ├── Wire-in points: ``external_write_scanner.scan_all``
│   │   │   emits per-row events on every newly-detected
│   │   │   unattributed write; ``/api/sql/explain`` emits when
│   │   │   ``needs_approval`` flips true; ``/admin/audit/export``
│   │   │   emits before stream-return.  ``rollback.executed``
│   │   │   stays on the Phase-16 ``agent_run_events`` path
│   │   │   (already lifecycle-attributed); the audit-stream
│   │   │   pipe gains it via ``mirror_lifecycle_to_sinks``
│   │   │   when admins flip the toggle.
│   │   ├── New ``api/audit_sinks_routes.py`` exposes admin CRUD
│   │   │   (``GET/POST/PATCH/DELETE /api/admin/audit-sinks``)
│   │   │   plus a ``POST /audit-sinks/{id}/test`` synthetic
│   │   │   envelope and a ``GET /audit-sinks/recent-events``
│   │   │   tail of the last 50 governance rows.  Sensitive
│   │   │   keys (HMAC, AWS access keys) are redacted on
│   │   │   readback; cleartext appears only at create time
│   │   │   in the request body.
│   │   ├── ``docs/e2e-walkthroughs/audit-sinks.md`` is the
│   │   │   operational runbook (curl / httpie, no browser).
│   │   │   Admin HTML page deferred to Phase 20.5 (close memo
│   │   │   + bug-hunt sweep) once the API surface settles.
│   │   └── SigV4 signer verified against AWS reference test
│   │       vector for S3 GET test.txt at
│   │       ``examplebucket.s3.amazonaws.com``.  Quality gates
│   │       clean: ruff / pyright (0 errors) / pydoclint /
│   │       alembic check.
│   ├── Sprint 20.1 — PII detection + masking write-hook    ✅
│   │   ├── Alembic ``n4i5j6k7l8m9`` adds ``system_keys``
│   │   │   (name UNIQUE, value TEXT, created_at) for the
│   │   │   lazy-generated PII hash secret.  No schema change to
│   │   │   ``lineage_value_changes`` — the redaction is
│   │   │   write-time inside ``record_value_changes``.
│   │   ├── New ``services/pii_redactor.py`` ships pattern-based
│   │   │   PII detection (regex matches ``email``, ``phone``,
│   │   │   ``ssn``, ``credit_card``, ``iban``, ``passport``,
│   │   │   ``first_name`` / ``last_name``, ``address``,
│   │   │   ``birth``, plus generic ``pii`` substring),
│   │   │   ``hash_value`` (HMAC-SHA256, 16 hex chars),
│   │   │   ``redact_value`` (literal ``<redacted>``), and
│   │   │   ``get_or_create_pii_hash_secret`` (lazy bootstrap).
│   │   ├── ``record_value_changes`` gains ``pii_mode`` +
│   │   │   ``pii_hash_secret`` parameters.  ``store_clear``
│   │   │   keeps pre-20.1 behaviour; ``hash_only`` (default)
│   │   │   rewrites old/new values to a 16-hex HMAC for any
│   │   │   pattern-matched column;
│   │   │   ``redact_with_audit_log`` substitutes the literal
│   │   │   ``<redacted>`` and appends one
│   │   │   ``audit_log`` row per per-op call.
│   │   ├── ``operations._record_value_changes_after_commit``
│   │   │   resolves :class:`Settings` and forwards the mode +
│   │   │   secret automatically — primitives stay agnostic.
│   │   ├── Soyuz tag-driven PII detection stays out of the
│   │   │   sync write path (would dominate per-write cost).
│   │   │   The Phase-18 render-time masking still gates
│   │   │   tagged-but-non-pattern columns at the API surface.
│   │   ├── ``docs/audit/pii-modes.md`` documents the three
│   │   │   modes, secret bootstrap, migration impact, and
│   │   │   the verification recipe.
│   │   └── Existing ``lineage_value_changes`` rows are not
│   │       rewritten — soft transition.  Historical cleartext
│   │       stays readable to admins; new writes hash.  Quality
│   │       gates clean.
│   ├── Sprint 20.2 — Lineage retention TTLs                  ✅
│   │   ├── New ``services/lineage_pruner.py`` exports
│   │   │   ``prune_once`` (sync) + ``prune_once_async`` (async
│   │   │   wrapper that emits one
│   │   │   ``pointlessql.lineage.pruned`` governance CloudEvent
│   │   │   per axis after the DB prune commits).  Each per-axis
│   │   │   prune also appends one ``audit_log`` row so deletion
│   │   │   is itself auditable.
│   │   ├── New ``LineageRetentionSettings`` (env prefix
│   │   │   ``POINTLESSQL_AUDIT_LINEAGE_RETENTION_*``) carries
│   │   │   per-axis ``*_days`` thresholds.  ``None`` /
│   │   │   ``0`` short-circuits the axis (never pruned).
│   │   │   Defaults: row_edges 365, row_rejects 365,
│   │   │   value_changes 730, column_map ``None``.
│   │   ├── Lifespan task ``_lineage_pruner_loop`` ticks every
│   │   │   ``audit.cleanup_interval_seconds`` (default 24h).
│   │   │   Active only when at least one axis has a positive
│   │   │   threshold.  Survives any per-axis exception so a
│   │   │   transient DB hiccup never takes the loop down.
│   │   ├── Sprint 20.0's governance event catalog already
│   │   │   includes ``EVENT_TYPE_LINEAGE_PRUNED``; the pruner
│   │   │   is its first emitter.  Audit-stream sinks see prunes
│   │   │   as part of the same pipe as external-write detections
│   │   │   and cost-gate denials.
│   │   └── Quality gates clean.  Smoke test confirms 400-day-old
│   │       rows are deleted, fresh rows preserved, three
│   │       per-axis audit_log rows appended, and the
│   │       ``column_map`` axis is correctly skipped when its
│   │       threshold is ``None``.
│   ├── Sprint 20.3 — Time-travel value queries in UI       ✅
│   │   ├── New ``pql.table_at_version(fqn, n)`` +
│   │   │   ``pql.table_at_timestamp(fqn, when)`` PQL helpers
│   │   │   wrap :meth:`DeltaTable.load_as_version`.  Always
│   │   │   materialise pandas (engine abstraction targets
│   │   │   current-version reads only).  Each call writes a
│   │   │   ``query_history`` row with ``read_kind=
│   │   │   "pql_table_at_version"``.
│   │   ├── New ``api/time_travel_routes.py`` exposes three
│   │   │   read-only routes: ``/api/tables/{fqn}/versions``
│   │   │   (history list joined against
│   │   │   ``agent_run_operations.delta_version_after`` so each
│   │   │   version names the originating run when known),
│   │   │   ``/api/tables/{fqn}/preview-at-version`` (paged
│   │   │   rows up to 200), ``/api/lineage/row-at-version``
│   │   │   (admin-gated single-row state lookup keyed on
│   │   │   ``_lineage_row_id``).
│   │   ├── Table-detail preview card gains a "View at:" select
│   │   │   populated from ``/api/tables/{fqn}/versions``;
│   │   │   choosing a non-current version reloads the preview
│   │   │   via the new endpoint.
│   │   ├── Row-trace page gains an admin-only "View this row
│   │   │   at a specific Delta version" card with numeric
│   │   │   input + lookup button; renders the two-column
│   │   │   key/value table or a "row was not present" notice.
│   │   ├── ``query_history.read_kind`` enum extends with
│   │   │   ``pql_table_at_version`` so ``/queries`` surfaces
│   │   │   time-travel reads alongside ordinary
│   │   │   ``pql.table()`` calls.
│   │   └── ``docs/e2e-walkthroughs/time-travel.md`` is the
│   │       browser-replay playbook (table picker + row
│   │       admin-only card).  Quality gates clean.
│   └── Sprint 20.4 — Soyuz columnLineage + valueChange ingest  ✅
│       ├── Soyuz side (commit pending push, locally tagged
│       │   ``v0.2.0rc4``): two new ORM models —
│       │   ``LineageColumnEdge`` (composite-uniqueness on
│       │   the source-quad, transformation_type free-text)
│       │   and ``LineageValueChange`` (per-cell before/after,
│       │   no unique constraint).  Alembic ``016`` creates
│       │   both with ``ON DELETE CASCADE`` on ``run_id``.
│       │   ``ingest_event`` walks the per-output
│       │   ``facets.columnLineage`` (OpenLineage 1.x) +
│       │   ``facets.valueChange`` (PointlesSQL extension,
│       │   namespaced under ``_producer``).  Permissive parse
│       │   — malformed entries dropped silently.
│       │   ``LineageIngestResponse`` gains
│       │   ``accepted_column_edges`` /
│       │   ``accepted_value_changes`` (default 0; backwards
│       │   compatible).  Generated client regenerated.
│       │   Existing test suite (545 tests) green after
│       │   additive response-shape update.
│       ├── PointlesSQL side: ``services/soyuz_lineage.py``
│       │   ``emit_event_sync`` accepts optional
│       │   ``column_edges`` + ``value_changes`` lists; builds
│       │   the ``columnLineage`` + ``valueChange`` facet
│       │   bodies into each output dataset's
│       │   ``additional_properties``.
│       │   ``operations._emit_lineage_after_commit`` threads
│       │   the recorder's pending lists through so every
│       │   merge / declarative write that already populates
│       │   ``LineageColumnMap`` + ``LineageValueChange``
│       │   automatically surfaces in soyuz too.
│       ├── PII safety: PointlesSQL emits already-redacted
│       │   values when ``pii_mode != store_clear`` (the
│       │   Sprint 20.1 default ``hash_only`` mode rewrites
│       │   ``old_value`` / ``new_value`` to a 16-hex HMAC),
│       │   so soyuz never sees cleartext PII.  External
│       │   producers may emit the same facet but must
│       │   redact themselves — soyuz doesn't introspect.
│       └── ``v0.2.0rc4`` push + pin-bump from ``v0.2.0rc3``
│           to ``v0.2.0rc4`` are pending — same posture as the
│           Phase-14 rc3 push (the install still works because
│           the response shape extension is additive).
│
├── Phase 21 — ML Registry + Auditable Training           ✅ done 2026-04-30 (21.0/21.1/21.2/21.3/21.4/21.5/21.6/21.7/21.8)
│   │
│   │   The stack today audits *data engineering* end-to-end
│   │   (Phases 14-20) but has a gap when the workload is *model
│   │   training*: hyperparameters, seeds, library versions and
│   │   hardware fingerprints live nowhere structured.  ``model.fit
│   │   (seed=42, lr=0.001)`` is plain Python — captured as cell
│   │   content, not as first-class audit rows.  Phase 21 closes
│   │   that gap on three layers, mirroring how Databricks' Unity
│   │   Catalog absorbed MLflow Registry as a MODEL Securable in
│   │   2023-24.
│   │
│   │   **Three-layer split (analogous to JupyterLab embedding):**
│   │
│   │   ```
│   │   Layer        Owner              Responsibility
│   │   ───────────  ─────────────────  ──────────────────────────
│   │   Tracking     MLflow subprocess  Experiments, runs, params,
│   │                                   metrics, artifacts (REST)
│   │   Registry     soyuz-catalog      MODEL securable: identity,
│   │                                   versions, aliases, grants,
│   │                                   tags — UC-spec parity
│   │   Operations   PointlesSQL UI +   Promote, A/B, shadow-mode,
│   │                Hermes agents      drift alerts, approval-hop,
│   │                                   audit cockpit integration
│   │   ```
│   │
│   │   **Why register in soyuz, not just proxy MLflow Registry:**
│   │   if the catalog doesn't know models as first-class objects,
│   │   every Phase-14-20 win evaporates — uniform grants, lineage
│   │   over training-input → model → inference-output, valueChange
│   │   tracking on inference results, audit-trail across promotion
│   │   steps.  This is exactly the "model is a Catalog object, not
│   │   a sidecar" point UC won over plain-MLflow on.
│   │
│   │   **Honest reproducibility caveat:** seed + hyperparams give
│   │   a strong audit answer to *"how was it configured"* but not
│   │   to *"would it come out bit-identical on rerun"* — CUDA
│   │   non-determinism, parallel dataloaders, atomic-add ordering
│   │   leak even with full state capture.  Document this gap
│   │   explicitly; many EU-AI-Act Art. 12 implementations conflate
│   │   the two.  Phase 21's promise is auditability of intent, not
│   │   bit-replay.
│   │
│   │   Strategic ordering note: Phase 21 lands AFTER Phase 16.5
│   │   (Delta-Branching) so the agent-run isolation story already
│   │   exists when training runs need their own scratch branches.
│   │   Lands BEFORE the Some-day public launch so the ML angle is
│   │   in the launch-day narrative ("auditable agent-driven ML on
│   │   the lakehouse, not just data engineering").
│   │
│   ├── Sprint 21.0 — MLflow Tracking subprocess + UI embed     ✅ done 2026-04-30
│   │   ├── ``services/mlflow.py`` lifecycle manager analogous to
│   │   │   ``services/jupyter.py`` (Phase 1).  Boots ``mlflow
│   │   │   server`` on a configurable port, health-checks, exposes
│   │   │   REST proxy through PointlesSQL's auth layer.
│   │   ├── Storage: experiments + runs in PointlesSQL's own
│   │   │   metadata DB (Alembic migration), artifacts in a UC
│   │   │   Volume so they inherit Phase-12.5 grants.
│   │   ├── ``MLflow`` tab in main nav, embedded iframe initially;
│   │   │   later sprints replace key flows with native UI.
│   │   └── ``pointlessql.mlflow_url`` auto-configured for
│   │       notebook + agent contexts so ``mlflow.log_param`` works
│   │       without env-setup boilerplate.
│   │
│   ├── Sprint 21.1 — soyuz ``MODEL`` Securable (UC-spec parity)  ✅ done 2026-04-30 (soyuz 248f73f, tag v0.3.0rc1 local)
│   │   ├── New endpoints in ``soyuz-catalog`` matching UC spec:
│   │   │   ``POST /models``, ``GET /models/{full_name}``,
│   │   │   ``POST /models/{full_name}/versions``,
│   │   │   ``GET /model-versions/{full_name}/{version}``,
│   │   │   plus aliases (``PUT /models/{full_name}/aliases/{alias}``).
│   │   ├── Same Securable machinery as TABLE/VOLUME: grants,
│   │   │   tags, lineage edges, audit log entries.
│   │   ├── ``soyuz-catalog-client`` regen so PointlesSQL gets
│   │   │   typed access; ``v0.3.0`` minor bump.
│   │   └── Spec-conformance test (Sprint-12 in soyuz) extended
│   │       with the MODEL endpoints from ``all.yaml``.
│   │
│   ├── Sprint 21.2 — Cross-link ``agent_run`` ↔ MLflow ↔ MODEL    ✅ done 2026-04-30
│   │   ├── ``agent_run.mlflow_run_id`` column (Alembic migration);
│   │   │   populated automatically when an op detects an MLflow
│   │   │   call inside the run.
│   │   ├── ``model_version`` carries ``mlflow_run_id`` as a soyuz
│   │   │   tag (UC-compatible, no schema deviation).
│   │   ├── New ``GET /api/runs/{id}/ml-context`` aggregator that
│   │   │   joins agent_run + MLflow Run + soyuz model_version into
│   │   │   one audit response — the "wie wurde das Modell trainiert"
│   │   │   query that plain-MLflow can't answer.
│   │   └── Audit-cockpit (Phase 18) gains an "ML" axis.
│   │
│   ├── Sprint 21.3 — Forced Autolog (training param/metric capture) ✅
│   │   ├── New ``pql.training_context()`` context-manager wraps a
│   │   │   training block, enables ``mlflow.autolog()`` for the
│   │   │   requested framework hint, and at exit copies
│   │   │   ``run.data.params`` + ``run.data.metrics`` into a
│   │   │   JSON blob on ``agent_run_operations.training_params_json``
│   │   │   (Alembic ``t0p2q4r6s8u0``).
│   │   ├── Best-effort: works without the mlflow extra (audit row
│   │   │   still lands), without a live tracking server (snapshot
│   │   │   stays empty), and even when the wrapped training body
│   │   │   raises (partial autolog state captured before re-raise).
│   │   ├── ``train_model`` added to the ``op_name`` enum + CHECK
│   │   │   constraint.
│   │   ├── Run-detail Operations tab gains a collapsed "Training
│   │   │   params + metrics" accordion underneath each
│   │   │   ``train_model`` op row.
│   │   └── Strict fail-loud (``UnauditedTrainingError``) +
│   │       framework/seed interceptors deferred — the best-effort
│   │       path here covers the audit-of-intent goal without
│   │       blocking training when MLflow misbehaves.
│   │
│   ├── Sprint 21.4 — Lib + Hardware Fingerprint                 ✅
│   │   ├── New ``agent_run_operations.env_snapshot`` Text column
│   │   │   (Alembic ``u1q3r5s7t9v1``) carries an advisory JSON
│   │   │   blob with three sub-keys: ``python`` (version + cpu
│   │   │   count + platform), ``packages`` (top 200 distributions
│   │   │   via ``importlib.metadata`` capped at 4 KiB), ``gpu``
│   │   │   (when torch + CUDA are available, per-device name +
│   │   │   total memory).
│   │   ├── Snapshot built once at module-import time and cached
│   │   │   for the whole PointlesSQL process; subsequent
│   │   │   ``record_operation`` calls reuse the cached blob so
│   │   │   the hot path stays cheap.
│   │   ├── Run-detail Operations tab gains a collapsed
│   │   │   "Environment fingerprint" accordion under each op row.
│   │   ├── Best-effort end-to-end: every sub-step is wrapped in
│   │   │   try/except and degrades to ``None`` rather than
│   │   │   blocking the audit row.
│   │   └── ``cudnn.deterministic`` flag + conda/pyproject hashes +
│   │       a dedicated "Repro" sub-tab deferred — the column is
│   │       extension-friendly so future passes can layer them in.
│   │
│   ├── Sprint 21.5 — PointlesSQL Models-Tab                    ✅
│   │   ├── Catalog-tree extended with model nodes (sidebar) +
│   │   │   server-side tree-search supports ``kind="model"``.
│   │   ├── Top-level ``/models`` index with per-catalog filter +
│   │   │   ``bi-box-seam`` icon-rail tab.
│   │   ├── Model-detail page at ``/models/{full_name}`` with five
│   │   │   tabs (Overview, Versions, Lineage, MLflow, Permissions);
│   │   │   Versions tab pulls MLflow params/metrics/tags via
│   │   │   ``MlflowClient.get_run`` per linked run.
│   │   ├── Side-by-side compare-view at ``/models/.../compare``
│   │   │   with metric-direction heuristic
│   │   │   (lower-better/higher-better) and added/removed/changed
│   │   │   diff for params + tags.
│   │   ├── Focused lineage DAG via ``/api/models/.../lineage``:
│   │   │   orange-hexagon model node + green source-table nodes
│   │   │   for every table consumed by any Hermes-run linked to
│   │   │   any version of the model.
│   │   └── Browser-walkthrough playbook in
│   │       ``docs/e2e-walkthroughs/models-tab.md``.
│   │
│   ├── Sprint 21.6 — Champion/Challenger Promotion-Hop          ✅
│   │   ├── ``_pql_promotion`` JSON marker stored in the registered-
│   │   │   model's ``comment`` field (mirrors ``_pql_link``); marker
│   │   │   parser/serializer in
│   │   │   ``pointlessql/services/model_promotion.py``.
│   │   ├── ``POST /api/models/{full_name}/promote`` endpoint gated by
│   │   │   ``require_supervisor``; ``GET /api/models/{full_name}/
│   │   │   promotion`` returns champion + history.
│   │   ├── ``agent_reviews.kind`` discriminator column (Alembic
│   │   │   ``r8n0p2q4s6u8``); promotion review rows coexist with
│   │   │   Phase-19 audit-review rows.
│   │   ├── ``pointlessql.model.promoted`` CloudEvent envelope.
│   │   ├── Promotion-tab on ``/models/{full_name}`` replaces the
│   │   │   Sprint-21.5 Permissions stub: champion card + per-version
│   │   │   promote-button + reason modal + collapsed history list.
│   │   │   Champion-badge on the Versions tab.
│   │   └── First-class soyuz aliases deferred — marker convention
│   │       gives equivalent semantics without a soyuz schema bump.
│   │
│   ├── Sprint 21.7 — Inference-Lineage (model → predictions)    ✅
│   │   ├── New ``source_model_uri`` nullable column on
│   │   │   ``lineage_row_edges`` (Alembic ``s9o1p3r5t7u9``); every
│   │   │   row-edge produced by an inference write carries the
│   │   │   originating ``models:/{full_name}/{version}`` URI.
│   │   ├── ``pql.write_table()`` accepts a new
│   │   │   ``source_model_uri`` kwarg that propagates through the
│   │   │   operation_context recorder and ``record_edges`` into
│   │   │   the column above.
│   │   ├── New ``aggregate_prediction_tables_for_model`` aggregator
│   │   │   feeds ``GET /api/models/{full_name}/predictions`` and
│   │   │   the bidirectional model-lineage graph.
│   │   ├── ``build_model_lineage_graph`` extended to include
│   │   │   prediction nodes (``kind="prediction"``) with dashed
│   │   │   blue ``inferred_to`` edges; cytoscape style + legend
│   │   │   updated.
│   │   ├── New "Prediction tables" card on the model-detail
│   │   │   Lineage tab.
│   │   └── Drift alerts + dedicated ``pql.predict`` helper +
│   │       cost-per-1k-inferences deferred to Phase 22+.
│   │
│   └── Sprint 21.8 — Hermes plugin extension (cross-repo closure) ✅
│       ├── ``POST /api/pql/write_table`` + ``POST /api/pql/merge``
│       │   bodies grow optional ``source_model_uri``; the write
│       │   route auto-derives ``source_table_fqn`` from the SELECT
│       │   when there's exactly one ref so the row-edge grain
│       │   anchors cleanly.
│       ├── ``PQL.merge()`` Python sig grows ``source_model_uri``
│       │   for symmetry with ``PQL.write_table()``; threaded into
│       │   ``recorder.extra_params`` + ``recorder.pending_lineage_edges``.
│       ├── New ``POST /api/pql/training/log`` endpoint persists a
│       │   one-shot ``record_operation(op_name="train_model",
│       │   training_params_json={...})`` row — HTTP-only equivalent
│       │   of ``pql.training_context()`` for the plugin's httpx-only
│       │   transport.
│       ├── Plugin commit ``f01d4e0``: 8 new tools (list_models /
│       │   get_model / get_model_predictions / get_model_lineage /
│       │   get_model_runs / get_promotion_history / log_training_run
│       │   + supervisor-gated promote_model) + 2 extended
│       │   (write_table + merge accept source_model_uri).  Tool
│       │   count 34 → 42.
│       └── Server commit ``5919c63``, plugin commit ``f01d4e0``;
│           closes the "Closure pending (user job)" item from the
│           21.0–21.7 close note.
│
├── Phase 22 — Documentation site (shoreguard-quality)     ✅ done 2026-04-30 (22.0 ✅ 22.1 ✅ 22.2 ✅ 22.3 ✅ 22.4 ✅ 22.5 ✅)
│   │
│   │   Phase 21 closed the audit/ML story end-to-end and the stack
│   │   is feature-complete enough to demo to non-Flo readers — the
│   │   next bottleneck is *visibility*, not *features*.  Phase 22
│   │   brings PointlesSQL to the same docs polish that
│   │   ``shoreguard-fresh`` ships on
│   │   ``flohofstetter.github.io/shoreguard``: mkdocs-material with
│   │   navigation tabs, palette toggle, mkdocstrings auto-generated
│   │   Python API, hand-polished prelude over auto-generated REST
│   │   reference, Mermaid diagrams everywhere, five-minute
│   │   quickstart.
│   │
│   │   **Deploy posture (user pick 2026-04-30)**: local-only
│   │   through Phase 22.  ``mkdocs serve`` for iteration; the
│   │   ``docs.yml`` workflow is staged with ``workflow_dispatch``
│   │   (manual) trigger and a ``mkdocs build`` step (no
│   │   ``gh-deploy``) so PRs catch broken builds without making the
│   │   site URL public.  The launch sprint flips: trigger →
│   │   ``push: main``, repo visibility → public, README badge →
│   │   live URL.  Procedure goes into ``ADR-0004 Public-flip
│   │   checklist`` in Sprint 22.5.
│   │
│   │   **Plan**: ``.claude/plans/dann-plane-diese-vollst-ndig-stateful-music.md``
│   │   is the canonical source for the six sub-sprints.
│   │
│   ├── Sprint 22.0 — Tooling foundation                   ✅ done 2026-04-30
│   │   ├── New ``mkdocs.yml`` (~140 lines) — material theme,
│   │   │   palette toggle, navigation tabs/sections/instant,
│   │   │   mkdocstrings (Google docstring style),
│   │   │   pymdownx.superfences with Mermaid custom-fence,
│   │   │   eight-section ``nav:`` skeleton including all 38 e2e
│   │   │   walkthroughs explicitly listed.
│   │   ├── New ``.github/workflows/docs.yml`` — ``workflow_dispatch``
│   │   │   only (no auto-publish); runs ``mkdocs build`` to prove
│   │   │   the build is green.  ``--strict`` deferred to 22.5 once
│   │   │   the cross-link sweep cleans up the last source-tree
│   │   │   warnings.  Deploy step (``mkdocs gh-deploy --force``)
│   │   │   present but commented out with a TODO marker pointing
│   │   │   at the launch sprint.
│   │   ├── ``docs/`` re-organised into mkdocs-material layout
│   │   │   (8 sections): ``getting-started/``, ``concepts/``,
│   │   │   ``guides/``, ``reference/``, ``integrations/``,
│   │   │   ``development/``, ``decisions/``, ``e2e-walkthroughs/``.
│   │   │   File moves done with ``git mv`` so blame history
│   │   │   survives.  ``docs/install.md`` →
│   │   │   ``docs/getting-started/installation.md``;
│   │   │   ``docs/auth.md`` → ``docs/concepts/auth.md``;
│   │   │   ``docs/data-layers.md`` → ``docs/concepts/data-layers.md``;
│   │   │   ``docs/audit/pii-modes.md`` →
│   │   │   ``docs/concepts/pii-modes.md``;
│   │   │   ``docs/jobs.md`` → ``docs/guides/jobs.md``;
│   │   │   ``docs/design-tokens.md`` →
│   │   │   ``docs/development/design-tokens.md``;
│   │   │   ``docs/adr/*.md`` → ``docs/decisions/*.md``;
│   │   │   ``docs/hermes-jobs/`` → ``docs/integrations/hermes-jobs/``.
│   │   ├── Eight new section landing pages
│   │   │   (``index.md``-each) — one-screen hooks pointing at
│   │   │   what's filled in today and what each later sub-sprint
│   │   │   will add.  Sprint 22.1 rewrites the top-level
│   │   │   ``docs/index.md`` with a real hero.
│   │   ├── 14 stale move-induced cross-links fixed across
│   │   │   ``packaging.md``, ``ux-overhaul.md``, ``installation.md``,
│   │   │   ``audit-reviewer-daily.md``, ``branches.md``,
│   │   │   ``compliance-bot.md``, ``incident-responder.md``,
│   │   │   ``data-layers.md``, ``hermes-jobs/{README,
│   │   │   compliance-bot, incident-responder}.md``.  Remaining
│   │   │   ~117 ``mkdocs build`` warnings are pre-existing
│   │   │   source-tree references (``../../frontend/...``,
│   │   │   ``../../pointlessql/...``) that the walkthroughs make
│   │   │   on purpose — Sprint 22.5 cross-link sweep is when
│   │   │   ``--strict`` gets re-enabled.
│   │   └── ``site/`` added to ``.gitignore``.
│   │
│   ├── Sprint 22.1 — Landing + getting started            ✅ done 2026-04-30
│   │   ├── ``docs/index.md`` rewrite: hero, "What is PointlesSQL?"
│   │   │   narrative, Mermaid ecosystem diagram (agents → plugin →
│   │   │   PointlesSQL → soyuz / Delta), problem framing with
│   │   │   before/after Python snippet, comparison table, feature
│   │   │   highlights with deep-links into the e2e walkthroughs,
│   │   │   "Where to next" link grid.
│   │   ├── ``docs/getting-started/quickstart.md`` (NEW, 7 steps):
│   │   │   docker compose up → first-user register → seed-e2e.py →
│   │   │   browse demo catalog → read demo.sales.orders via PQL →
│   │   │   write demo.sales.orders_high → see audit row + lineage
│   │   │   in the run-detail view.  Tear-down + four common-failure
│   │   │   troubleshooting blocks.
│   │   ├── ``docs/getting-started/concepts.md`` (NEW, ~250 lines):
│   │   │   four-layer stack table, three-part name story, PQL
│   │   │   primitive list, agent-runs as audit container,
│   │   │   four-level lineage chain (with Mermaid), Audit Cockpit,
│   │   │   Family A/B/C supervision tiers, Delta-branching,
│   │   │   champion/challenger marker grammar, "what PointlesSQL
│   │   │   is not" section.
│   │   ├── ``docs/getting-started/index.md``: real section landing.
│   │   ├── ``mkdocs.yml`` nav: Quickstart + Concepts overview added.
│   │   └── ``README.md`` polish: replaced ASCII architecture block
│   │       with Mermaid (renders in GitHub), added Documentation
│   │       pointer above Status section, trimmed Status + Stack
│   │       sections by ~30 % (hand off detail to docs site).
│   │       Stale ``docs/install.md`` / ``docs/jobs.md`` /
│   │       ``docs/adr/`` references in ``README.md`` and
│   │       ``CLAUDE.md`` updated to the post-22.0 layout.
│   │
│   ├── Sprint 22.2 — Architecture + concepts              ✅ done 2026-04-30
│   │   ├── ``docs/concepts/architecture.md`` (NEW, ~250 lines):
│   │   │   four logical layers (routes/services/PQL/storage), the
│   │   │   soyuz-catalog boundary + bug-fix-at-source rule, two
│   │   │   sequence diagrams (agent writes a derived table,
│   │   │   supervisor promotes a model to champion), why
│   │   │   Python-only, full module map.
│   │   ├── ``docs/concepts/audit-trail.md`` (NEW, ~280 lines):
│   │   │   3-level model (cells / operations / queries), the
│   │   │   ``agent_run_operations`` schema (16 columns), the
│   │   │   ``record_operation`` forced-audit pattern, ``params_json``
│   │   │   examples per op-name, Phase-21 audit additions
│   │   │   (mlflow_run_id / training_params_json / env_snapshot /
│   │   │   source_model_uri), the rollback action loop, what's
│   │   │   *not* recorded (LLM prompts → shoreguard's job).
│   │   ├── ``docs/concepts/lineage.md`` (NEW, ~210 lines):
│   │   │   four-level chain (row → column → value → inference)
│   │   │   with cost/opt-in matrix, schema for each table,
│   │   │   sqlglot-driven column provenance, value-level CDF
│   │   │   semantics with PII masking, bidirectional model DAG,
│   │   │   aggregate fan-in (Phase 15.5), rejects.
│   │   ├── ``docs/concepts/agent-supervision.md`` (NEW, ~290 lines):
│   │   │   Family A/B/C tiers + tool counts, asymmetric scope
│   │   │   ladder (auditor passes ``require_supervisor`` but not
│   │   │   vice versa), wake-gate optimisation, ``agent_reviews``
│   │   │   schema with kind discriminator, CloudEvents 1.0 fan-out
│   │   │   shape, the four canonical bot personas (daily Audit-
│   │   │   Reviewer, Compliance-Bot, Incident-Responder,
│   │   │   Promotion-gate), trust-ladder Mermaid.
│   │   ├── ``docs/concepts/index.md``: real section landing,
│   │   │   reading order (architecture → audit-trail → lineage →
│   │   │   agent-supervision), pointers to auth / data-layers /
│   │   │   pii-modes + the ADR index.
│   │   └── ``mkdocs.yml`` nav: four new concept pages wired in
│   │       above the existing reference-style ones.
│   │
│   ├── Sprint 22.3 — Reference manual                     ✅ done 2026-04-30
│   │   ├── ``docs/reference/python/index.md`` — landing page
│   │   │   distinguishing auto-gen (``PQL`` + service modules)
│   │   │   from hand-written (REST top-30 + CLI) reference.
│   │   ├── ``docs/reference/python/pql.md`` — mkdocstrings
│   │   │   directive against ``pointlessql.pql.pql.PQL`` (Google
│   │   │   docstring style, members_order=source, ``filters: !^_``)
│   │   │   plus a usage preface showing all 19 primitives in one
│   │   │   block.
│   │   ├── ``docs/reference/python/services.md`` — mkdocstrings
│   │   │   for five service modules: ``agent_runs.operations``
│   │   │   (record_operation forced-audit), ``agent_runs.training_context``
│   │   │   (Phase 21.3 autolog wrap), ``audit`` (base writer),
│   │   │   ``branch_tags`` (Delta-branching), ``mlflow_subprocess``
│   │   │   (lazy MLflow lifespan).
│   │   ├── ``docs/reference/api.md`` — hand-curated top-30 REST
│   │   │   reference grouped by tag (Auth, Agent runs, PQL writes,
│   │   │   Models, Lineage, Branches, Audit cockpit, Reviews,
│   │   │   Admin API keys, Audit sinks, Health/metrics).  Tier
│   │   │   icons (🍪 🔑 👮 🕵 ⚙) per route + canonical error
│   │   │   envelope shape.  Auto-generated appendix for the
│   │   │   remaining ~180 routes deferred to 22.5.
│   │   ├── ``docs/reference/cli.md`` — ``pointlessql`` Typer
│   │   │   surface (no-arg dev server + ``admin issue-auditor-key``)
│   │   │   with synopsis, options table, output sample, exit
│   │   │   codes, and an explicit "what's *not* in the CLI" list.
│   │   ├── ``docs/reference/configuration.md`` — every
│   │   │   ``POINTLESSQL_*`` env var grouped by ``settings.py``
│   │   │   sub-model (18 sub-models + the four special agent-run
│   │   │   env vars + GHCR_PAT) with rationale per setting.
│   │   ├── ``docs/reference/cloudevents.md`` — all 12 emitted
│   │   │   ``pointlessql.<domain>.<verb>`` types across five
│   │   │   domains (agent_run lifecycle, cost gate, rollback,
│   │   │   lineage retention, external writes, policy violations,
│   │   │   audit export, MLflow link, model promotion) with
│   │   │   payload schemas + examples + HMAC-signing convention.
│   │   ├── ``docs/reference/permissions.md`` — the trust-tier
│   │   │   matrix (Anonymous → Cookie → API key → +supervisor /
│   │   │   +auditor → Admin), asymmetric scope ladder, server-side
│   │   │   FastAPI dependency mapping, plugin-side family gating,
│   │   │   admin-only actions list, "why no per-table ACLs"
│   │   │   rationale.
│   │   ├── ``docs/reference/index.md`` — replaces the placeholder
│   │   │   with a real audience-grouped landing + hand-written-
│   │   │   vs-auto-gen drift-handling table.
│   │   └── ``mkdocs.yml`` nav: full Reference tree (Python API
│   │       sub-section + 5 reference pages) wired in.
│   │
│   ├── Sprint 22.4 — Guides + cookbook                    ✅ done 2026-04-30
│   │   ├── ``docs/guides/index.md`` rewrite — taxonomic landing
│   │   │   with three flavours (high-level recipes, operator
│   │   │   cookbook, e2e walkthroughs) + the 38 walkthroughs
│   │   │   spread across five themed sub-sections (Getting
│   │   │   around / Working with data / Notebooks + jobs /
│   │   │   Audit + lineage / Agents + ML registry).
│   │   ├── ``docs/guides/agent-bring-up.md`` (NEW, 7-step
│   │   │   recipe, ~250 lines): wire a brand-new Hermes agent
│   │   │   end-to-end in ~30 minutes.  Chains four e2e
│   │   │   walkthroughs (auth + agent-ml-registry +
│   │   │   audit-reviewer-daily + admin-audit) into one
│   │   │   narrative; ends with a Mermaid loop showing the
│   │   │   audit-trail-feeds-review-bot pattern.
│   │   ├── ``docs/guides/operator-cookbook.md`` (NEW, 20
│   │   │   recipes): Daily / Weekly / Per-agent / Per-incident /
│   │   │   Per-model / Per-data-issue / Maintenance buckets.
│   │   │   Each recipe is one to three sentences plus a deep-
│   │   │   link to the long-form walkthrough.
│   │   ├── ``docs/guides/troubleshooting.md`` (NEW, ~290 lines):
│   │   │   symptom-first index across Install + first boot,
│   │   │   Auth + sessions, Plugin / Hermes, PQL writes, Audit
│   │   │   cockpit, Notebooks, Storage / Delta, CI / packaging.
│   │   │   References ``BUG-NN-NN`` source-comment markers and
│   │   │   the relevant configuration / permissions docs.
│   │   ├── ``docs/guides/faq.md`` (NEW, ~190 lines): What / Why
│   │   │   this and not… / How / When / Should I sections,
│   │   │   organised by question shape rather than topic.
│   │   └── ``mkdocs.yml`` nav: Guides section reorganised, four
│   │       new high-level pages above ``Jobs``, walkthroughs
│   │       split into five themed sub-sub-sections.
│   │
│   └── Sprint 22.5 — Polish + launch-ready                ✅ done 2026-04-30
│       ├── **Cross-link sweep**: ~117 source-tree warnings
│       │   eliminated via bulk rewrite.  Every walkthrough
│       │   ``../../<path>`` reference rewrites to a canonical
│       │   GitHub URL (``https://github.com/FloHofstetter/PointlesSQL/blob/main/<path>``);
│       │   the four orphan ``../../`` repo-root links in
│       │   ``notebook-editor.md`` resolve to
│       │   ``http://127.0.0.1:8000/notebook/editor``.
│       ├── ``mkdocs build --strict`` now exits 0 with **zero**
│       │   warnings and zero INFO-level link complaints.
│       │   ``mkdocs.yml`` flips ``strict: false`` → ``strict: true``;
│       │   ``.github/workflows/docs.yml`` flips back to
│       │   ``mkdocs build --strict`` (the 22.0 deferral is over).
│       ├── ``docs/integrations/soyuz-catalog.md`` (NEW): boundary
│       │   doc, generated-client pin shape, editable escape-hatch,
│       │   bug-fix-at-source rule, sequence diagram.
│       ├── ``docs/integrations/hermes-plugin.md`` (NEW): install
│       │   procedure, Family A/B/C tool count breakdown (16/4/22),
│       │   conventions, lifecycle hooks, "why httpx not import"
│       │   rationale.
│       ├── ``docs/integrations/mlflow.md`` (NEW): subprocess +
│       │   reverse-proxy architecture (Mermaid), Phase-21 audit
│       │   additions list, configuration reference, lazy-spawn
│       │   semantics, "why subprocess not import" rationale.
│       ├── ``docs/integrations/grafana.md`` (NEW): the 8-panel
│       │   audit dashboard, install via overlay, four known
│       │   gotchas (WAL RW mount, unsigned plugin flag, datasource
│       │   UID, Decimal cast).
│       ├── ``docs/changelog.md`` (NEW): hand-curated What's-new
│       │   digest covering Phases 19/20/21/22 with pointer to
│       │   the full ``CHANGELOG.md`` in the repo root.  Future
│       │   ``gen_whats_new.py`` script (Phase 23 candidate) will
│       │   auto-snip this from ``[Unreleased]`` + last 3 sprints.
│       ├── ``docs/decisions/0004-public-flip-checklist.md`` (NEW):
│       │   the launch-sprint procedure — four-item pre-flight
│       │   (EUIPO trademark / NOTICE / CLA / custom domain) plus
│       │   three-commit flip (workflow / repo visibility / README
│       │   badge).  Codifies the user's "local-only through
│       │   Phase 22" pick.
│       └── ``mkdocs.yml`` nav: 4 integrations pages + ADR-0004 +
│           top-level "What's new" entry wired in.
│
├── Phase 15.8 — Lineage Wiring Audit                     ✅ closed 2026-04-30
│   │
│   │   Surfaced 2026-04-30 by ``scripts/seed-full-stack-demo.py``
│   │   Phase-2-coverage replay; closed same day in one autonomous
│   │   session after the planning pass relocated the bug.  The
│   │   initial 3-axis symptom list (row-edges, value-changes,
│   │   source_model_uri all 0 for ``demo_ml.*``) collapsed to **one
│   │   root cause + one orthogonal latent bug** at line-level
│   │   investigation:
│   │
│   │   - **Root cause** — ``_step_silver``'s explicit-column
│   │     ``SELECT h.house_id, h.size_sqft, …`` projection at
│   │     ``scripts/seed-full-stack-demo.py:490`` drops
│   │     ``_lineage_row_id``.  The downstream
│   │     ``_stamp_lineage_for_write`` short-circuits with no
│   │     ``source_ids``, so ``recorder.pending_lineage_edges``
│   │     stays unset and the post-commit hook records nothing.
│   │     Silver/gold/predictions inherit the gap.
│   │   - **Consequence** — value-changes = 0 isn't a CDF-bootstrap
│   │     bug: CDF IS enabled correctly by ``write_table``'s
│   │     post-create ALTER, the cell-flip merge IS at v3 with CDF
│   │     events.  ``extract_value_changes`` returns ``[]`` because
│   │     the merge frame copies silver_df which has no
│   │     ``_lineage_row_id``.
│   │   - **Consequence** — ``source_model_uri`` plumbing is
│   │     end-to-end intact (``pql.py:255+289 → _write.py:49+144 →
│   │     operations.py:641+660 → lineage_edges.py:254+293``).  The
│   │     missing rows are because ``_write.py:139`` only enters
│   │     the pending-edges block when ``source_ids`` is non-empty
│   │     — no row-id, no edge row, nowhere for the model URI to
│   │     land.
│   │   - **Latent bug (orthogonal)** — ``_merge.py:321`` called
│   │     ``ensure_cdf_enabled`` AFTER ``_do_upsert``, so a merge
│   │     against a non-pql-created Delta target would record its
│   │     commit without CDF.  Fixed by moving
│   │     ``ensure_cdf_enabled`` ahead of ``_do_upsert`` in
│   │     ``merge_table``.
│   │
│   │   Full plan with code-level call-site references at
│   │   ``.claude/plans/phase-15-8-lineage-wiring-audit.md``.
│   │
│   ├── Sprint 15.8.1 — repro fixture                          ✅
│   │   └── ``tests/test_phase158_lineage_wiring.py`` —
│   │       7 contract tests: positive + negative row-edges path,
│   │       source_model_uri stamping, value-change capture across
│   │       fresh-write+remerge, the new INFO-log diagnostic,
│   │       and a regression for merge-against-non-CDF target.
│   ├── Sprint 15.8.2 — ``_lineage_row_id`` propagation         ✅
│   │   └── ``scripts/seed-full-stack-demo.py`` — silver SELECT
│   │       projects ``h._lineage_row_id``, inference projects
│   │       ``_lineage_row_id`` onto the predictions frame.
│   │       ``pointlessql/pql/_sql.py`` — INFO log + new
│   │       ``lineage_row_id_dropped_at_select`` flag on the op's
│   │       ``params_json`` when a SELECT references a
│   │       lineage-bearing source but doesn't project the column.
│   │       ``pointlessql/pql/pql.py`` — ``PQL.sql`` docstring
│   │       documents the propagation contract.
│   ├── Sprint 15.8.3 — ``source_model_uri`` regression-pin     ✅
│   │   └── No code change needed (line-level investigation
│   │       proved the plumbing was already complete).  The
│   │       ``source_model_uri`` regression test in
│   │       ``test_phase158_lineage_wiring.py`` exercises the
│   │       real-Delta round-trip (no ``_FakePQL`` mock) and pins
│   │       the wiring.  Docstring caveats added to
│   │       ``pql.write_table`` flagging the ``_lineage_row_id``
│   │       prerequisite.
│   └── Sprint 15.8.4 — CDF ordering fix + doc                 ✅
│       └── ``pointlessql/pql/_merge.py`` — moved
│           ``ensure_cdf_enabled`` from inside
│           ``_capture_value_changes`` (post-merge) to ahead of
│           ``_do_upsert`` (pre-merge), so the merge commit lands
│           with CDF on regardless of the target's history.
│           Removed the duplicate post-merge call.  ``pql.merge``
│           docstring documents the "first merge after a fresh
│           write_table produces only ``insert`` events; value
│           changes start at the second merge" semantics.
│
│       Acceptance (against ``pointlessql.db`` after
│       ``--fresh --demo-rollback`` replay): all six L5 axes
│       non-zero —  silver=400, gold-train=160, gold-test=40,
│       predictions=80, value_changes=1, pred_with_model_uri=40.
│       Phase 15 is now both **spec-complete** AND
│       **end-to-end-loop-complete**.
│
├── Phase 23 — Contextual help-popovers across the UI       ✅ closed 2026-05-05 (23.0 ✅ 23.1 ✅ 23.2 ✅ 23.3 ✅ 23.4 ✅ 23.5 ✅)
│   │
│   │   The audit/lineage/branching/promotion stack is now
│   │   feature-complete (Phases 13-21) and the docs site is
│   │   launch-ready (Phase 22), but the web UI itself never
│   │   tells a newcomer what an "agent run", "Delta branch",
│   │   "champion version" or "2σ baseline" actually means —
│   │   you have to leave the page and read mkdocs.  Phase 23
│   │   adds small ``bi-info-circle`` icons next to every
│   │   high-value anchor (page headers, key tabs, domain
│   │   badges); a click opens a Bootstrap popover with a 1-3
│   │   sentence "what + why" plus an optional "Learn more →"
│   │   link to the matching mkdocs concept guide.
│   │
│   │   Cross-cutting picks (confirmed via AskUserQuestion at
│   │   plan time): click-popover (mobile-tauglich, focus-trigger
│   │   auto-dismisses, room for multi-sentence body + link);
│   │   typed Python-dict copy registry at ``pointlessql/web/
│   │   help.py`` (pyright-validated, single source of truth);
│   │   staged 5-sub-sprint shape so each PR is reviewable.
│   │
│   ├── Sprint 23.0 — Infra + 5 hero anchors                  ✅ 2026-05-02
│   │   ├── ``pointlessql/web/help.py`` (NEW) — typed
│   │   │   ``HelpEntry`` dataclass + ``HELP`` registry with
│   │   │   the 5 hero slugs (``runs.what-is-a-run``,
│   │   │   ``runs.what-is-an-operation``,
│   │   │   ``models.what-is-promotion``,
│   │   │   ``branches.what-is-a-delta-branch``,
│   │   │   ``lineage.what-is-lineage``).  ``get_help`` raises
│   │   │   ``KeyError`` on unknown slugs so template typos fail
│   │   │   loudly in CI rather than silently render an empty
│   │   │   popover.
│   │   ├── ``frontend/templates/_macros/help_icon.html`` (NEW)
│   │   │   — Jinja macro ``info('<slug>')`` emits a
│   │   │   ``<button data-bs-toggle="popover"
│   │   │   data-bs-trigger="focus">``.  Bootstrap auto-dismisses
│   │   │   on outside-click + Escape, no extra JS listener
│   │   │   needed.  Inner ``<a>`` link uses single-quoted
│   │   │   attributes to avoid colliding with the outer
│   │   │   double-quoted ``data-bs-content``.
│   │   ├── ``frontend/js/help_popovers.js`` (NEW) — idempotent
│   │   │   ``bootstrap.Popover`` initialiser bound to
│   │   │   ``DOMContentLoaded`` + ``htmx:afterSwap`` so
│   │   │   HTMX-boosted swaps re-wire popovers in the new
│   │   │   content.  Loaded immediately after the Bootstrap
│   │   │   bundle in ``base.html``.
│   │   ├── ``pointlessql/api/main.py`` — registers ``get_help``
│   │   │   as the Jinja global ``help`` once on the shared
│   │   │   ``_TEMPLATES.env`` next to the existing
│   │   │   ``epoch_ms`` filter.
│   │   ├── 5 page-template edits: ``runs_list.html`` page
│   │   │   header, ``run_view.html`` Operations top-tab intro
│   │   │   line, ``model.html`` Promotion-tab "Current
│   │   │   champion" card-header, ``branches.html`` page
│   │   │   header, ``table.html`` Lineage-tab intro line.
│   │   ├── ``docs/concepts/contextual-help.md`` (NEW) —
│   │   │   author-facing stub: "How to add a new help slug",
│   │   │   why click-popover won over hover-tooltip, what's
│   │   │   out of scope (i18n, inline tutorials, help-editor
│   │   │   UI).  Wired into ``mkdocs.yml`` Concepts nav.
│   │   └── ``tests/test_help_registry.py`` (NEW, 18 tests) —
│   │       slug naming convention, length caps (title ≤ 60,
│   │       body ≤ 280 chars), ``learn_more`` URL well-
│   │       formedness, ``KeyError`` on missing slugs,
│   │       Sprint-23.0 hero-slug presence pin.
│   ├── Sprint 23.1 — Catalog tree + table-detail            ✅ 2026-05-05
│   │   ├── ``pointlessql/web/help.py`` — appended 8 slugs:
│   │   │   ``catalog.what-is-a-catalog``,
│   │   │   ``schemas.what-is-a-schema``,
│   │   │   ``tables.external-vs-managed``,
│   │   │   ``tables.row-lineage-badge``,
│   │   │   ``tables.column-trace-badge``,
│   │   │   ``tables.time-travel-button``,
│   │   │   ``tables.comments-vs-properties``,
│   │   │   ``tables.column-statistics``.
│   │   ├── ``frontend/templates/components/sidebar.html`` —
│   │   │   info-icon next to the **Catalog** rail heading.
│   │   ├── ``frontend/templates/pages/tables.html`` (schema
│   │   │   detail) — info-icons next to the page header and
│   │   │   the Type column header on the tables list.
│   │   ├── ``frontend/templates/pages/table.html`` — five
│   │   │   anchors across Overview (Type), Properties card,
│   │   │   Preview card + "View at" selector, Columns card,
│   │   │   Column-statistics card.
│   │   └── ``tests/test_help_registry.py`` — slug-pin test
│   │       ``test_sprint_23_1_catalog_and_table_anchors_present``.
│   ├── Sprint 23.2 — Models index + detail                  ✅ 2026-05-05
│   │   ├── ``pointlessql/web/help.py`` — appended 6 slugs:
│   │   │   ``models.what-is-the-registry``,
│   │   │   ``models.versions-table``,
│   │   │   ``models.linked-hermes-runs``,
│   │   │   ``models.inference-lineage``,
│   │   │   ``models.mlflow-vs-pointlessql``,
│   │   │   ``models.compare-versions``.
│   │   ├── ``frontend/templates/pages/models.html`` — info-icon
│   │   │   on the registry page header.
│   │   ├── ``frontend/templates/pages/model.html`` — four
│   │   │   anchors on the detail tabs (Overview "Linked Hermes
│   │   │   runs" card, Versions card-header, Lineage
│   │   │   "Prediction tables" card, MLflow tab intro).
│   │   ├── ``frontend/templates/pages/model_compare.html`` —
│   │   │   info-icon on the v1↔v2 page header.
│   │   └── ``tests/test_help_registry.py`` — slug-pin test
│   │       ``test_sprint_23_2_models_anchors_present``.
│   ├── Sprint 23.3 — Branches + audit + home                ✅ 2026-05-05
│   │   ├── ``pointlessql/web/help.py`` — appended 12 slugs
│   │   │   covering anomalies (``audit.what-is-an-anomaly``,
│   │   │   ``audit.severity-warn-vs-critical``,
│   │   │   ``audit.anomaly-actions``), FTS
│   │   │   (``audit.fts-query-syntax``), principal summary
│   │   │   (``audit.principal-summary``), cross-workspace
│   │   │   lens (``audit.cross-workspace-lens``,
│   │   │   ``audit.read-kind``), branch ops
│   │   │   (``branches.preview-tab``,
│   │   │   ``branches.promote-vs-discard``,
│   │   │   ``branches.cleanup-loop``) and the home cockpit
│   │   │   (``home.what-is-the-cockpit``,
│   │   │   ``home.anomaly-cards``).
│   │   ├── ``frontend/templates/pages/audit_inbox.html``,
│   │   │   ``audit_search.html``, ``audit_by_table.html``,
│   │   │   ``audit_queries.html`` — info-icons next to the
│   │   │   inbox header, severity filter, Ack column, FTS
│   │   │   query input, by-table Principal column, saved
│   │   │   queries page header, ``query_history`` mention.
│   │   ├── ``frontend/templates/pages/branch_detail.html`` —
│   │   │   info-icons on Strategy / Danger-zone / Preview
│   │   │   promote.
│   │   ├── ``frontend/templates/pages/home.html`` — info-icons
│   │   │   on the Welcome heading and the anomaly banner.
│   │   └── ``tests/test_help_registry.py`` — slug-pin test
│   │       ``test_sprint_23_3_audit_branches_home_anchors_present``.
│   ├── Sprint 23.4 — SQL editor + sidebar rail + settings   ✅ 2026-05-05
│   │   ├── ``pointlessql/web/help.py`` — appended 10 slugs:
│   │   │   ``sql.run-modes``, ``sql.saved-queries``,
│   │   │   ``sql.cost-gate``,
│   │   │   ``admin.external-writes-review``,
│   │   │   ``admin.audit-sinks``,
│   │   │   ``admin.workspace-pins``,
│   │   │   ``admin.api-key-scopes``,
│   │   │   ``admin.system-keys``,
│   │   │   ``admin.rate-limit-tiers``,
│   │   │   ``admin.agent-reviews``.
│   │   ├── ``frontend/templates/pages/sql_editor.html`` —
│   │   │   info-icons on the SQL header, Save button and
│   │   │   Explain button.
│   │   ├── ``frontend/templates/pages/admin_external_writes.html``,
│   │   │   ``admin_audit.html``, ``admin_workspaces.html`` —
│   │   │   info-icons on each page header.
│   │   ├── ``frontend/templates/pages/credentials.html`` —
│   │   │   three info-icons (page header, Purpose column,
│   │   │   New Credential button).
│   │   ├── ``frontend/templates/pages/agent_review_detail.html``
│   │   │   — info-icon on the review header.
│   │   └── ``tests/test_help_registry.py`` — slug-pin test
│   │       ``test_sprint_23_4_sql_admin_anchors_present``.
│   └── Sprint 23.5 — Polish + doc-link sweep + e2e replay   ✅ 2026-05-05
│       ├── ``pointlessql/web/help.py`` — re-targeted eight
│       │   stale ``learn_more`` paths (e.g.
│       │   ``/concepts/agent-runs/`` →
│       │   ``/concepts/agent-supervision/``,
│       │   ``/concepts/jobs/`` → ``/guides/jobs/``,
│       │   ``/concepts/notebooks/`` and ``/concepts/alerts/``
│       │   dropped to ``None``) so every "Learn more" link
│       │   resolves to a real mkdocs page.
│       └── ``tests/test_help_registry.py`` — added two sweep
│           tests:
│           ``test_every_template_slug_resolves_in_registry``
│           (catches typos in ``info('<slug>')`` calls) and
│           ``test_every_registry_slug_used_in_some_template``
│           (catches stale registry entries when the UI is
│           refactored away from a popover host).
│
├── Phase 28 — Workspace isolation (soft, Databricks-style)  ✅
│   │
│   │   Closed 2026-05-05 across 9 sub-sprints.  Soft tenant
│   │   boundary over a shared global Unity Catalog.  Catalogs and
│   │   tables stay catalog-scoped (cross-workspace data sharing
│   │   is a feature: dev workspace reads ``prod.silver.orders``
│   │   to bootstrap a sandbox merge); workspaces own audit / jobs
│   │   / dashboards / saved-queries / recents / alerts /
│   │   anomaly-acks.  M:M user↔workspace, cosmetic-only catalog
│   │   pins, switcher hidden when ≤1 workspace exists so single-
│   │   tenant installs see zero behaviour change.
│   │
│   │   ADR: [ADR-0008](docs/decisions/0008-workspace-soft-isolation.md).
│   │   Concept doc: [docs/concepts/workspaces.md](docs/concepts/workspaces.md).
│   │   Admin runbook: [docs/admin/workspace-management.md](docs/admin/workspace-management.md).
│   │
│   ├── Sprint 28.0 — Workspace model + middleware +              ✅
│   │   api_keys pin + scheduler resolver.
│   │   New tables ``workspaces``, ``workspace_members``,
│   │   ``workspace_catalog_pins`` (Alembic ``z6w8a0b2c4d6``).
│   │   FK columns on ``users.default_workspace_id`` (nullable
│   │   in 28.0, NOT NULL in 28.6) and ``api_keys.workspace_id``
│   │   (NOT NULL with backfill to id=1 — carved out of original
│   │   28.5 scope to eliminate cross-sprint hazard).  Bootstrap
│   │   migration seeds workspace ``id=1, slug='default'`` and
│   │   adds every existing user as a member with role mirroring
│   │   ``is_admin``.  Service module ``services/workspaces.py``
│   │   exposes CRUD + non-HTTP ``resolve_workspace_id`` shared
│   │   by middleware, scheduler, CLI, fixtures.  Middleware
│   │   attaches ``request.state.workspace_id`` and 403s
│   │   ``workspace.context_mismatch`` (audit-logged) on
│   │   cross-workspace probes.  ``KeyEntry`` carries
│   │   ``workspace_id``.  New deps ``current_workspace_id``,
│   │   ``current_workspace``, ``require_workspace_admin``.
│   │   28 new pytest cases.
│   ├── Sprint 28.1a — agent_runs + agent_run_* + FTS5 surgery   ✅
│   │   workspace_id NOT NULL + server_default=1 added to all 5
│   │   audit-trail source tables (Alembic ``aa1c3e5g7i9k``);
│   │   compound indexes ``(workspace_id, started_at)`` and
│   │   ``(workspace_id, agent_run_id)``.  Listing routes
│   │   (``/api/agent-runs``, ``/api/agent-runs/operations``)
│   │   add workspace filter; per-run audit-axis routes return
│   │   404 for cross-workspace requests via extended
│   │   ``ensure_run_visible``.  POST /api/agent-runs writes the
│   │   request's resolved workspace; AgentRunOperation /
│   │   AgentRunEvent / AgentRunToolCall write paths denormalise
│   │   from the parent.  FTS5 ``audit_search`` rebuilt with a
│   │   6th ``workspace_id UNINDEXED`` column; triggers populate
│   │   from NEW.workspace_id (runs/ops/tool_calls) or literal 1
│   │   (queries/audit_log — flipped in 28.1b).  10 new pytest
│   │   cases.
│   ├── Sprint 28.1b — lineage + audit_log + governance +        ✅
│   │   query_history get workspace_id (Alembic
│   │   ``bb2d4f6h8j0l``).  10 tables: 4 lineage, 2 query_history,
│   │   audit_log, governance_events, unattributed_writes,
│   │   anomaly_acks.  Two UNIQUE constraints widened to prefix
│   │   workspace_id (``unattributed_writes`` + ``anomaly_acks``).
│   │   ``audit.log_action`` / ``query_history.record_query`` /
│   │   ``governance_events.emit_governance_event`` thread
│   │   workspace_id; lineage write paths derive from parent op.
│   │   ``external_write_scanner`` attributes to ws=1 (28.3 will
│   │   fan out via pins).  FTS5 triggers for query_history /
│   │   audit_log flip from literal ``1`` to ``NEW.workspace_id``.
│   │   8 new pytest cases.
│   ├── Sprint 28.2 — User-owned + scheduler tables              ✅
│   │   (Alembic ``cc3e5g7i9k1m``).  13 tables: 5 scheduler,
│   │   3 catalog/saved-queries, 1 recents (UNIQUE widened to
│   │   prefix workspace_id), 2 alerts, 2 notebook.  Scheduler
│   │   tick propagates Job.workspace_id to JobRun / TaskRun /
│   │   JobLog.  ``recents.record_table_visit`` and
│   │   ``saved_queries.create_saved_query`` thread workspace_id.
│   │   Route-side listing filters land as follow-up.  6 new
│   │   pytest cases.
│   ├── Sprint 28.3 — Workspace catalog pins (cosmetic) +        ✅
│   │   UI default-catalog hint.  Three admin-only routes
│   │   wire the ``workspace_catalog_pins`` table (created but
│   │   unused in 28.0): GET / POST / DELETE
│   │   ``/api/admin/workspaces/{id}/pins``.  ``GET /api/tree``
│   │   accepts ``?primary_only=true`` to filter to pinned
│   │   catalogs.  Promoting a second pin to ``primary`` mode
│   │   auto-demotes the previous primary.  No enforcement —
│   │   cross-workspace catalog access stays free.  Mutations
│   │   audit-log to ``workspace.pin_added`` /
│   │   ``workspace.pin_removed``.  6 new pytest cases.
│   ├── Sprint 28.4 — UI: switcher + base.html plumbing +        ✅
│   │   sidebar awareness + single-workspace hide rule.
│   │   ``POST /auth/switch-workspace`` writes the
│   │   ``pql_workspace`` cookie with membership enforcement;
│   │   middleware reads it as the cookie tier of the resolver.
│   │   ``base.html`` ships three workspace meta tags +
│   │   ``components/workspace_switcher.html`` partial; the
│   │   switcher hides when the user belongs to ≤1 workspace.
│   │   ``pqlApi.fetch`` and the HTMX bridge auto-inject
│   │   ``X-Workspace``.  ``catalog_tree.js`` namespaces its
│   │   sessionStorage cache + recents by workspace slug and
│   │   pre-expands the workspace's primary-pinned catalog.
│   │   New help slug ``workspace.what-is-a-workspace``.
│   │   9 new pytest cases.
│   ├── Sprint 28.5 — Hermes plugin X-Workspace +                ✅
│   │   audit-wake-gate scoping.  Plugin gained
│   │   ``PluginConfig.workspace`` (read from
│   │   ``POINTLESSQL_WORKSPACE``); ``_headers()`` injects
│   │   ``X-Workspace`` on every request.  ``scripts/audit-wake-gate.py``
│   │   honours the same env var.  Server-side test
│   │   ``tests/test_cross_workspace_api_key.py`` round-trips the
│   │   three resolver outcomes (no header → api_key pin;
│   │   mismatched header → 403 + audit row; matching →
│   │   passthrough).  Cross-repo edits in
│   │   ``~/git/hermes-plugin-pointlessql`` (commit ``00eb051``).
│   │   4 server-side + 5 plugin-side pytest cases.
│   ├── Sprint 28.6 — Admin pages: workspace + member CRUD       ✅
│   │   + ``users.default_workspace_id`` flipped to NOT NULL.
│   │   New ``pointlessql/api/admin_workspaces_routes.py`` with
│   │   seven tenant-admin-gated endpoints (list/create/update/
│   │   archive workspaces; list/add/role-change/remove members)
│   │   + the ``/admin/workspaces`` HTML page.  Refuses to
│   │   archive id=1.  Mutations log to ``audit_log`` with
│   │   ``workspace.*`` action prefix.  Alembic ``dd4f6h8j0l2n``
│   │   flips the FK column to NOT NULL after a defensive
│   │   backfill.  12 new pytest cases.
│   ├── Sprint 28.7 — Cross-workspace super-admin lens           ✅
│   │   (``?workspace=all``).  ``audit_aggregator.summary`` /
│   │   ``.timeseries`` / ``.anomalies`` accept a new
│   │   ``workspace_id`` kwarg; ``None`` skips the filter (god-
│   │   eye view).  /api/audit/* routes accept ``?workspace=``
│   │   (slug | "all"); admin-only when not the caller's
│   │   resolved workspace.  New ``audit_api_cross_workspace``
│   │   read_kind in ``VALID_READ_KINDS``; ``_record_self``
│   │   writes that value when the lens lifts the filter so the
│   │   audit-of-audit pipeline can flag tenant-admin escalations.
│   │   Grafana ``$workspace`` variable deferred (queued for the
│   │   public-launch sprint when the dashboard catalog is
│   │   reviewed end-to-end).  6 new pytest cases.
│   └── Sprint 28.8 — Documentation + ADR-0008 + ROADMAP         ✅
│       positioning update.  New ``docs/concepts/workspaces.md``,
│       ``docs/admin/workspace-management.md``,
│       ``docs/decisions/0008-workspace-soft-isolation.md``.
│       ROADMAP entry updated to ✅; CHANGELOG carries a
│       per-sub-sprint entry.
│
├── Phase 29 — Workspace polish pass                         ✅
│   │
│   │   Closed 2026-05-05 across 5 sub-sprints in one autonomous
│   │   run.  Phase 28 shipped soft isolation; Phase 29 fills in
│   │   the cross-cutting tenancy gaps that surfaced once the
│   │   foundation was load-bearing: per-workspace fan-out
│   │   routing for audit sinks + review destinations, OIDC group
│   │   → workspace + scope mapping for federated SSO, and a
│   │   ``$workspace`` template variable on the Grafana dashboard.
│   │   ``system_keys`` deliberately stays install-global so PII
│   │   anomaly aggregation continues to align across tenants.
│   │
│   ├── Sprint 29.1 — Per-workspace audit-sink routing          ✅
│   │   New ``audit_sinks.workspace_filter`` JSON column (alembic
│   │   ``ee5g7i9k1m3o``); ``NULL`` keeps install-global fan-out,
│   │   ``[1, 3]`` restricts the sink to events whose
│   │   ``workspace_id`` is in the list.  ``dispatch_to_sinks``
│   │   gained an optional ``workspace_id`` kwarg that
│   │   ``emit_governance_event`` threads through.  ``POST`` /
│   │   ``PATCH /api/admin/audit-sinks`` validate listed IDs
│   │   against live ``workspaces``; the synthetic test envelope
│   │   endpoint stays bypass-filter so admins can ping a sink
│   │   without picking a tenant.  6 new pytest cases.
│   ├── Sprint 29.2 — Per-workspace review-destination routing  ✅
│   │   Mirror of 29.1 for the agent-review fan-out path.  New
│   │   alembic ``ff6h8j0l2n4p`` adds
│   │   ``agent_reviews.workspace_id`` (FK + ``ix_agent_reviews_workspace_period``)
│   │   plus ``review_destinations.workspace_filter``.
│   │   ``POST /api/agent-reviews`` reads
│   │   ``request.state.workspace_id`` to populate the new column;
│   │   ``dispatch_review`` filters destinations by
│   │   ``review.workspace_id``.  6 new pytest cases.
│   ├── Sprint 29.3 — OIDC group → workspace + scope mapping    ✅
│   │   New alembic ``gg7i9k1m3o5q`` adds
│   │   ``users.is_supervisor`` / ``is_auditor`` (parallel to
│   │   ``ApiKey``-side flags) plus ``users.oidc_groups_json``
│   │   (audit-visibility snapshot).  ``OIDCSettings`` gains
│   │   ``scope`` / ``groups_claim_name`` / ``group_map_raw``;
│   │   the parser fails loud at ``Settings()`` construction on
│   │   malformed input so a typo in the env var never silently
│   │   grants the wrong privileges.
│   │   ``find_or_create_oidc_user`` extracts the groups claim,
│   │   unions scope grants across every matching mapping, picks
│   │   the first matching ``ws=`` for ``default_workspace_id``,
│   │   and re-resolves on every login so IdP group changes
│   │   propagate without a manual refresh.
│   │   ``require_supervisor`` / ``require_auditor`` honour the
│   │   new flags on the session-cookie path while preserving
│   │   the asymmetric privilege ladder pinned in 19.1.  New
│   │   ``docs/admin/oidc-group-map.md`` documents env-var
│   │   format + worked example.  20 new pytest cases.
│   ├── Sprint 29.4 — Grafana ``$workspace`` template variable  ✅
│   │   ``grafana/dashboards/pointlessql_audit.json`` grew a
│   │   multi-select ``workspace`` query variable populated from
│   │   the ``workspaces`` table.  Each panel SQL grew a guard
│   │   ``AND (0 IN ($workspace) OR <table>.workspace_id IN ($workspace))``
│   │   so ``allValue=0`` short-circuits to true (full cross-
│   │   workspace view) while specific picks filter via ``IN``.
│   │   The "Datasource health" smoke-test panel stays global
│   │   on purpose.  ``docs/integrations/grafana.md`` documents
│   │   the filter behaviour, the ``var-workspace=<id>`` URL
│   │   override, and why Grafana queries don't generate audit-
│   │   of-audit trails.  Closes the Sprint 28.7 deferral.
│   └── Sprint 29.5 — Polish + close-out                        ✅
│       ``ruff format`` + ``ruff check`` clean across every
│       Phase-29-touched file; ``alembic check`` confirms zero
│       ORM↔migration drift; ``mkdocs build --strict`` passes
│       with the new admin doc page wired into nav and the
│       Grafana doc updated.  CHANGELOG carries the per-sub-
│       sprint entry; ROADMAP entry flipped to ✅.
│
├── Phase 30 — Postgres production-readiness                ✅
│   │
│   │   Closed 2026-05-05 across 6 sub-sprints in one autonomous
│   │   run.  Postgres has been a *technically supported* metadata
│   │   backend since Phase 4 / Sprint 10, but two cliffs (no PG
│   │   FTS, no Grafana dashboard) and three readiness gaps (no CI
│   │   PG lane, no SQLite→PG migration tool, no production tuning
│   │   surface) stood between "swap a URL and pray" and
│   │   "production default".  Phase 30 closes them.  Decisions
│   │   locked at plan time: single-DB production-readiness (no
│   │   two-DB split), ship the migration CLI, dual-track SQLite +
│   │   PG steady state.  Phase 19.0.1's deferral is closed by
│   │   30.2.
│   │
│   ├── Sprint 30.0 — CI Postgres lane + dialect drift fence     ✅
│   │   ``.github/workflows/test.yml`` grew a parallel ``postgres``
│   │   job spinning up ``postgres:17-alpine`` as a service and
│   │   re-running the pytest suite against PG via
│   │   ``TEST_DATABASE_URL``.  ``alembic env.py`` honours
│   │   ``POINTLESSQL_DB_URL`` for shell-driven runs.  Three
│   │   pre-existing dialect bugs fixed: ``BOOLEAN DEFAULT 0``
│   │   literals replaced with ``DEFAULT false`` / ``true`` (PG
│   │   rejects integer-vs-boolean type mismatch), the Phase-18.7
│   │   FTS5 migration's time-travel import inlined as a
│   │   chronological snapshot, and ``conftest._seed_default_workspace``
│   │   now bumps the PG ``workspaces_id_seq`` past the explicit
│   │   ``id=1`` insert.  Result: ``alembic upgrade head`` clean
│   │   on a fresh DB on both backends.
│   ├── Sprint 30.1 — Postgres FTS via tsvector + GIN            ✅
│   │   New alembic ``hh8j0l2n4p6r`` (PG-only) creates the
│   │   ``audit_search_index`` table with a generated ``tsvector``
│   │   column and a GIN index.  Five PL/pgSQL trigger functions
│   │   keep the index in sync per source axis.
│   │   ``pointlessql/services/audit_fts.py`` becomes a dialect
│   │   router behind unchanged public surface; SQLite path
│   │   stays as-is, PG path uses
│   │   ``WHERE text_search @@ plainto_tsquery('simple', :query)``
│   │   + ``ts_rank`` ordering + ``ts_headline`` snippets.
│   │   ``/api/audit/search`` returns ``available=true`` on PG.
│   ├── Sprint 30.2 — Grafana on Postgres                        ✅
│   │   New ``docker-compose.grafana.postgres.yml`` overlay swaps
│   │   the unsigned ``frser-sqlite-datasource`` plugin for
│   │   Grafana's built-in PostgreSQL datasource.  Provisioning
│   │   split into ``grafana/postgres-provisioning/``; dialect-
│   │   clean dashboard JSON in ``grafana/postgres-dashboards/``
│   │   (Panel 5's reject-rate baseline rewritten with PG
│   │   ``INTERVAL '7 days'`` arithmetic).  Two overlays mutually
│   │   exclusive — operators pick one.  ``docs/integrations/grafana.md``
│   │   gains a "Running with Postgres" section and drops the
│   │   Phase-19.0.1 deferral prose.
│   ├── Sprint 30.3 — ``pointlessql migrate-to-postgres`` CLI    ✅
│   │   New ``pointlessql/cli/migrate_to_postgres.py`` wired into
│   │   the existing Typer surface.  Refuses non-empty targets,
│   │   runs alembic upgrade head, bulk-copies in a hard-coded
│   │   FK-respecting order via SQLAlchemy core, syncs PG
│   │   sequences past the largest copied id, rebuilds the
│   │   30.1 FTS index, and verifies row counts plus a
│   │   1%-sample-hash for tables ≥100 rows.  ``--dry-run``
│   │   prints the plan without touching the target.
│   ├── Sprint 30.4 — Production tuning + ops docs               ✅
│   │   ``DatabaseSettings`` grew four PG-aware fields
│   │   (``pool_size``, ``max_overflow``, ``pool_recycle_seconds``,
│   │   ``statement_timeout_ms``).  ``init_db()`` threads the pool
│   │   knobs into ``create_engine`` for PG and registers a per-
│   │   connection ``SET statement_timeout`` event listener.  New
│   │   ``docs/admin/postgres-deployment.md`` (~3 pages): pool
│   │   sizing formula for a 4-worker fleet, autovacuum hints
│   │   for ``lineage_row_edges`` / ``agent_run_tool_calls`` /
│   │   ``lineage_value_changes``, backup via
│   │   ``pg_dump --format=custom`` + ``pg_restore --jobs=4``,
│   │   monitoring signals, the SQLite→PG migration playbook.
│   │   ``docs/reference/configuration.md`` documents the four
│   │   new env vars.
│   └── Sprint 30.5 — Performance baseline + close-out           ✅
│       New ``scripts/seed_audit_lake.py`` seeds deterministic
│       synthetic load (10 k / 100 k / 1 M scales) against either
│       backend.  ``docs/admin/performance.md`` ships as a
│       measurement template — operators run the seed + their
│       own queries on their hardware and fill in the table.
│       ``mkdocs build --strict`` passes with both new admin
│       pages wired into nav.  CHANGELOG carries per-sub-sprint
│       entries; ROADMAP entry flipped to ✅.
│
├── Phase 31 — Test-suite speed pass                       ✅
│   │
│   │   Closed 2026-05-05 across 6 sub-sprints in one autonomous
│   │   run.  After Phase 30 lit up the PG CI lane, the full PG
│   │   pytest run hit ~3 hours of wall clock and the user
│   │   aborted it — the slowness was structural (autouse
│   │   function-scope fixture rebuilding 45 tables × 1461 tests
│   │   + 4 bcrypt operations per test at rounds=12).  Constraint
│   │   from the user: *"ohne Qualitätsverlust"* — no test
│   │   dropped, no algorithm replaced with a stub, no coverage
│   │   loss.  SQLite went from ~30 min → 68 s (≈27×); PG went
│   │   from ~3 h aborted → ~7 min.
│   │
│   ├── Sprint 31.0 — Baseline measurement scaffold          ✅
│   │   New ``scripts/bench_test_suite.sh`` writes timestamped
│   │   ``--durations=20`` snapshots into ``.bench/<ts>-<backend>.txt``;
│   │   honours ``BACKEND=postgres`` and ``PYTEST_XDIST=auto``.
│   │   Used at 31.5 to record the final wall-clock numbers.
│   │
│   ├── Sprint 31.1 — Lower bcrypt rounds in tests            ✅
│   │   ``tests/conftest.py`` rebinds
│   │   ``pointlessql.services.auth._hasher`` to
│   │   ``BcryptHasher(rounds=4)`` at import time (algorithm,
│   │   salt, cookie format unchanged).  Per-test bcrypt cost
│   │   drops from ~1.0 s to ~64 ms.  Tests that exercise
│   │   bcrypt round-trips still pass with the lower factor.
│   │   Production code is untouched.
│   │
│   ├── Sprint 31.2 — Session-scope schema + per-test wipe   ✅
│   │   Conftest split into a session-scope ``_test_engine``
│   │   (one ``Base.metadata.create_all`` per worker, one
│   │   ``drop_all`` on session exit) and a function-scope
│   │   autouse ``_auth_db`` that wipes rows via PG ``TRUNCATE
│   │   TABLE … RESTART IDENTITY CASCADE`` or SQLite reverse-FK
│   │   ``DELETE FROM …`` + ``sqlite_sequence`` reset, then
│   │   re-seeds the workspace + admin/non-admin users from a
│   │   hash cached at module import.  Audit-FTS artefacts (PG
│   │   ``audit_search_index`` + functions, SQLite ``audit_search``
│   │   vtable + triggers) are dropped at fixture entry so tests
│   │   that opted in don't pollute later tests expecting
│   │   ``available=false``.  Eliminates ~90 DDL statements per
│   │   test — the single biggest cost on PG.
│   │
│   ├── Sprint 31.3 — Lifespan-tax kill                       ✅
│   │   New ``POINTLESSQL_TEST_LIFESPAN_FAST=1`` env var that
│   │   ``pointlessql.api.main._lifespan`` honours: skips
│   │   ``init_db`` (which runs alembic upgrade head against
│   │   the on-disk default URL), the audit / lineage /
│   │   external-writes / branch-cleanup background asyncio
│   │   tasks, the ``bootstrap_from_env`` API-key sync, and the
│   │   teardown-time ``uc_client.aclose`` call when the
│   │   conftest already pre-wired ``app.state``.  Production
│   │   startup is untouched — the env var is only set inside
│   │   the test process.  ``test_anonymous_request_redirects_to_login``
│   │   went from 12.3 s to 0.02 s (≈600×); the suite as a whole
│   │   shed ~12 s of lifespan tax.
│   │
│   ├── Sprint 31.4 — CI xdist + dev docs                    ✅
│   │   ``.github/workflows/test.yml::gate`` flips ``-n auto``
│   │   on for the SQLite lane (xdist already in dev deps,
│   │   per-worker engine in the session fixture means workers
│   │   don't share DB state).  PG lane stays single-worker on
│   │   purpose — workers can't share a live PG database
│   │   without per-worker DB provisioning, deferred to a
│   │   future sub-sprint if PG cycle time becomes the
│   │   bottleneck again.  New
│   │   [`docs/development/test-suite.md`](docs/development/test-suite.md)
│   │   documents the bench script, the env vars, the
│   │   conftest's three load-bearing tricks, and the
│   │   safe-edit rules (don't disable autouse, don't share
│   │   real bcrypt timing tests with the patched hasher,
│   │   etc.).  ``mkdocs build --strict`` clean.
│   │
│   └── Sprint 31.5 — Phase close-out                         ✅
│       Final wall-clock numbers captured into
│       ``.bench/20260505T151801Z-sqlite.txt``.  CHANGELOG
│       Phase-31 entry written; this ROADMAP node flipped to
│       ✅; memory entry filed at
│       ``project_phase31_closed.md``.  ``ruff``,
│       ``ruff format --check``, ``pyright``, and
│       ``mkdocs build --strict`` all clean on Phase-31-touched
│       files (pre-existing repo-wide lint / pyright errors are
│       unchanged).
│
├── Phase 32 — PG test quality cleanup                        ✅
│   │
│   │   Closed 2026-05-05 across 3 sub-sprints in one autonomous
│   │   run.  Once Phase 31 made the PG suite runnable end-to-end
│   │   (~7 min), it surfaced **45 pre-existing PG failures** —
│   │   none caused by Phase 31, but all blocked by it being
│   │   un-runnable.  PG suite goes from **45 failed → 0 failed**
│   │   (1457 / 1457 pass).  No quality loss: no test dropped, no
│   │   ``@skip`` / ``@xfail`` markers, every fix addresses the
│   │   root cause.  PG lane is now a first-class merge gate.
│   │
│   ├── Sprint 32.0 — FK-ordering + read_kind width             ✅
│   │   Inserted ``session.flush()`` between parent ``add()`` and
│   │   child ``add()`` in 11 fixtures across 10 test files
│   │   (``test_anomaly_highlighting``, ``test_inference_lineage``,
│   │   ``test_models_lineage``, ``test_rollback_preview``,
│   │   ``test_rollback_route``, ``test_run_diff_lineage``,
│   │   ``test_runs_op_filter``, ``test_pii_resolver``,
│   │   ``test_cross_workspace_lens``,
│   │   ``test_agent_runs_workspace_isolation``).  SQLAlchemy's
│   │   unit-of-work doesn't reliably topo-sort cross-class inserts
│   │   on PG when no ``relationship()`` is declared between parent
│   │   and child mappers — production code commits parent and
│   │   child in separate transactions so it never hit this.
│   │   ``test_models_lineage._seed_run_with_edges`` also gained an
│   │   actual ``AgentRunOperation`` insert (it was using a hardcoded
│   │   ``op_id=1`` that worked only because SQLite has FKs off).
│   │   Production-side fix: alembic ``ii9k1m3o5q7s`` widens
│   │   ``query_history.read_kind`` from ``VARCHAR(20)`` to
│   │   ``VARCHAR(32)`` (Sprint 28.7's
│   │   ``audit_api_cross_workspace`` literal is 25 chars and was
│   │   silently truncating on PG cross-workspace audit reads).
│   │   ``test_fts_vtable_carries_workspace_id_column`` rewritten
│   │   dialect-aware: PG inspects the ``audit_search_index`` table
│   │   from Sprint 30.1's FTS migration instead of running a
│   │   SQLite-only ``PRAGMA``.
│   │
│   ├── Sprint 32.1 — Dialect-aware saved-audit-queries seed   ✅
│   │   Migration ``j0e1f2a3b4c5`` shipped 5 starter rows with
│   │   ``datetime('now', '-N days')`` SQL strings — SQLite-only
│   │   syntax that PG can't parse.  Back-edited the migration to
│   │   build the rows via a ``starter_rows(dialect_name)`` helper
│   │   that picks ``NOW() - INTERVAL 'N days'`` on PG.
│   │   ``services/saved_audit_queries.py::bootstrap_starter_rows``
│   │   plumbs the session's ``dialect.name`` through (it already
│   │   imports the helper, so test-DBs that bypass migrations
│   │   benefit too).  New alembic migration ``jj0l2n4p6r8u``
│   │   repairs already-deployed PG installs in place via
│   │   ``UPDATE saved_audit_queries SET sql_text = REPLACE(...)``;
│   │   no-op on SQLite.  ``alembic check`` clean on both
│   │   backends.
│   │
│   └── Sprint 32.2 — Phase close-out                          ✅
│       Killer gate green: ``1457 passed`` on PG (was 45 failed),
│       ``1455 passed`` on SQLite (no regression),
│       ``PYTEST_XDIST=auto`` on SQLite still happy, ``pyright``
│       clean on touched files, ``alembic check`` no drift.
│       CHANGELOG Phase-32 entry written; this ROADMAP node
│       flipped to ✅; memory entry filed at
│       ``project_phase32_closed.md``.  Pre-existing repo-wide
│       lint / format errors (102 files) are unchanged — none
│       introduced by Phase 32.
│
├── Phase 33 — Admin Console                                   ✅ closed 2026-05-05
│   │
│   │   Bundle every operator-only screen behind one ``/admin``
│   │   landing.  Pre-Phase-33 the admin surface was three
│   │   isolated routes (``/admin/audit``, ``/admin/external-writes``,
│   │   ``/admin/workspaces``) plus six API-only surfaces with no
│   │   chrome (audit-sinks CRUD, review-destinations CRUD,
│   │   api-keys CRUD, system-keys, PII-mode, OIDC group mapping).
│   │   A single icon-rail pill pointed at the audit log; admins
│   │   reaching audit sinks or review destinations had to curl.
│   │   Phase 33 ships the landing + chrome for the two highest-
│   │   value gaps; the rest stays out of scope per the planning
│   │   trade-off table (system-keys rotation = security-sensitive
│   │   write, PII-mode + OIDC = env-restart-gated, API-keys =
│   │   curl-only acceptable, Playwright = chrome-only).
│   │
│   │   Mini-Sprint 0 retired two stale ROADMAP markers (Sprint
│   │   19.2 and Phase 12.9) that were already complete in code
│   │   but flagged ⏳/🔜.  Sub-sprints 33.1 / 33.2 / 33.3 deliver
│   │   the landing, audit-sinks UI, and review-destinations UI;
│   │   12 new pytest cases gate the templates.
│   │
│   ├── Mini-Sprint 0 — stale-marker cleanup                    ✅ done
│   │   ROADMAP edit only.  Sprint 19.2 ⏳ → ✅ (995490b);
│   │   Phase 12.9 🔜 → ✅ 2026-05-05 (Sprint 76–95: 90d40b8)
│   │   with closing note explaining ``help_popovers.js`` IIFE
│   │   retention + ``bootstrap.js`` permanence.
│   │
│   ├── Sprint 33.1 — Admin Landing + Nav-Chrome                ✅ done
│   │   New ``GET /admin`` route in ``api/admin_routes.py`` with
│   │   five-card grid (audit log, external writes, workspaces,
│   │   audit sinks, review destinations); cards surface
│   │   active-count badges via inexpensive COUNT queries.  New
│   │   template ``frontend/templates/pages/admin_index.html``;
│   │   icon-rail retargeted from ``/admin/audit`` → ``/admin``;
│   │   the three pre-existing admin pages back-link via the
│   │   "Admin" breadcrumb.  Test suite: ``test_admin_index.py``
│   │   (4 cases — anonymous redirect, non-admin 403, all five
│   │   card markers + hrefs assert, rail-retarget assertion).
│   │
│   ├── Sprint 33.2 — Audit Sinks UI                            ✅ done
│   │   New ``GET /admin/audit-sinks`` HTML route; new template
│   │   ``admin_audit_sinks.html`` with full sink table (redacted
│   │   config preview), per-row test/delete/active-toggle
│   │   actions, type-conditional create form (webhook / s3 /
│   │   aws_cloudtrail) with workspace-filter chip selector.
│   │   Reuses the existing ``/api/admin/audit-sinks`` JSON CRUD
│   │   (Phase 19.1 / 29.2) — no new server endpoints.  Test
│   │   suite: ``test_admin_audit_sinks_page.py`` (4 cases) —
│   │   load-bearing assertion is that ``hmac_secret`` and
│   │   ``secret_access_key`` cleartext NEVER reach the page,
│   │   only the literal ``<set>`` marker.
│   │
│   ├── Sprint 33.3 — Review Destinations UI                    ✅ done
│   │   New ``GET /admin/review-destinations`` HTML route; new
│   │   template ``admin_review_destinations.html`` with
│   │   destination table, inline min-severity dropdown,
│   │   HMAC-presence badge (``set`` / ``none``), workspace-filter
│   │   chips, active toggle, delete button, and create form.
│   │   Reuses the existing ``/api/admin/review-destinations``
│   │   JSON CRUD — no new endpoints.  Test suite:
│   │   ``test_admin_review_destinations_page.py`` (4 cases) —
│   │   load-bearing assertion is that the cleartext HMAC secret
│   │   NEVER reaches the page (``has_hmac_secret`` boolean only).
│   │
│   └── Sprint 33.4 — API-Keys UI + System-Info read-only panel ✅ done
│       Closes the two remaining gaps that the first cut deferred.
│       New ``GET /admin/api-keys`` HTML route + template
│       ``admin_api_keys.html``: list (active by default,
│       ``?include_revoked=1`` flips to history view), create
│       form (name / supervisor / auditor / workspace dropdown),
│       plaintext-secret modal after create with
│       ``navigator.clipboard`` copy fallback, soft-revoke via
│       browser ``confirm()``.  ``POST /api/admin/api-keys`` JSON
│       route now also accepts an optional ``workspace_id`` field
│       (defaults to ``1`` for back-compat); the audit-log entry
│       carries the chosen workspace.  New ``GET /admin/system-info``
│       HTML route + template ``admin_system_info.html``: four
│       read-only sections (PII mode + hash-secret presence,
│       API-key counts by scope, OIDC group→workspace+scope
│       mapping with restart-required hint, ``system_keys`` row
│       inventory).  ``admin_index.html`` gets two new cards
│       linking to these pages, with active-key-count badge.  9
│       new pytest cases across ``test_admin_api_keys_page.py``
│       and ``test_admin_system_info_page.py`` — load-bearing
│       assertions: the 64-char ``ApiKey.secret_hash`` and the
│       ``system_keys.value`` cleartext must NEVER reach the
│       rendered HTML; only the ``secret_prefix`` (8 chars) and
│       ``present``-badge surface.  Phase 33 now closes with all
│       four sub-sprints landed.
│
├── Phase 34 — Cross-Workspace Observability                  ✅ closed 2026-05-05
│   │
│   │   Phase 19.0 shipped a 10-panel audit dashboard — Phase 14
│   │   cost-gate, Phase 15.x lineage rejects + value changes,
│   │   Phase 13.11 tool-call latency, Phase 30.2 PG dialect.  But
│   │   six post-19 features stayed unpanelized: rollbacks (16),
│   │   anomaly inbox state (18), audit FTS index health (18.7),
│   │   audit-stream sink delivery (20), retention TTL (20), OIDC
│   │   logins (29).  Operators looking for "is the sink dying?"
│   │   or "how many rollbacks happened today?" had to query the
│   │   metadata DB by hand.  Phase 34 closes the gap by extending
│   │   the existing dashboards in place — same UID, same workspace
│   │   filter — so the Grafana hub stays the canonical operator
│   │   surface, no extra board to maintain.
│   │
│   │   Two sub-sprints planned: 34.1 (operator-pain MVP, 4 panels)
│   │   then 34.2 (governance + compliance, 4 panels).  Both edit
│   │   the SQLite + PG dashboards in lockstep with matched panel
│   │   IDs; SQLite uses ``datetime('now', …)`` / ``date(…)``, PG
│   │   uses ``NOW() - INTERVAL`` / ``::float8`` casts.  New CI
│   │   gate ``scripts/check-grafana-dashboards.sh`` parses both
│   │   JSONs and asserts non-empty panels + structural fields +
│   │   distinct IDs so a malformed edit fails the build instead
│   │   of silently shipping a blank panel-grid.
│   │
│   ├── Sprint 34.1 — Operator-Pain MVP                          ✅ done
│   │   Four new panels in both dashboards (matched IDs 12-15
│   │   plus header panel 11).  (1) ``Sink delivery health
│   │   (last 1h)``: stat over ``governance_events.outcome``,
│   │   red <95% / yellow 95-99% / green ≥99%.  (2) ``Open
│   │   anomaly verdicts (7d)``: stat counting ``agent_runs``
│   │   rows whose cached ``anomaly_severity`` is ``warn`` or
│   │   ``critical`` in the trailing 7 days.  (3) ``Rollbacks
│   │   per day``: vertical bar of ``agent_run_events`` filtered
│   │   to ``event_type='pointlessql.rollback.executed'``.  (4)
│   │   ``Sink errors per day (by event type)``: stacked
│   │   vertical bar of ``governance_events.outcome='delivery_
│   │   failed'`` per day per event_type.  Markdown header
│   │   (panel 11) labels the section as "Phase 28-30 Workspace
│   │   governance".  New CI gate at
│   │   ``scripts/check-grafana-dashboards.sh`` (~70 LOC) — both
│   │   dashboards parse, 15 panels each, distinct IDs.
│   │
│   └── Sprint 34.2 — Governance + Compliance                    ✅ done
│       Four more panels (matched IDs 17-20 + section header 16)
│       in both dashboards.  (1) ``Audit retention horizon
│       (oldest row, days)``: stat over the age of the oldest
│       ``audit_log`` row, threshold-coloured against the default
│       ``POINTLESSQL_AUDIT_RETENTION_DAYS=365`` (yellow ≥300,
│       red ≥365).  SQLite computes via ``julianday('now') -
│       julianday(MIN(...))``; PG via ``EXTRACT(epoch FROM NOW()
│       - MIN(...)) / 86400.0``.  (2) ``FTS index lag (rows
│       behind)``: stat showing ``COUNT(audit_log) -
│       COUNT(audit_search[_index])``; 0 = triggers in sync.
│       Cross-workspace by design.  (3) ``Audit exports issued
│       (selected window)``: stat counting ``governance_events``
│       rows where ``event_type='pointlessql.audit_export.
│       issued'``.  (4) ``Agent reviews per day (by severity)``:
│       full-width stacked bar of ``agent_reviews.created_at``
│       grouped by severity.  Plan originally listed an OIDC-
│       login-volume panel but the audit found logins are not
│       persisted to ``audit_log`` — the slot was redirected to
│       the audit-export trail panel.  Both dashboards: 20 panels,
│       distinct IDs, lint-script green.
│
├── Phase 35 — Targeted modularization + type-hardening     ✅ closed 2026-05-06
│   │
│   │   Code-quality phase opened 2026-05-06 after Phase 34 closed.
│   │   Two streams: (A) split the three big-and-mixed-concerns
│   │   files (``pql/_branch.py`` 1310, ``services/lineage_edges.py``
│   │   1137, ``services/audit_fts.py`` 973) into per-workflow
│   │   subpackages + extract ``run_view.html`` (1467) tab partials,
│   │   (B) drive pyright warnings from 531 toward ≤443 by typing
│   │   ``deltalake.DeltaTable`` returns + the ``cdf_table``
│   │   parameter + the polymorphic ``_frame_to_arrow`` dispatcher.
│   │   Out-of-scope: ``audit_routes`` / ``audit_aggregator`` /
│   │   ``operations.py`` (cohesive by audit), zero-warning push,
│   │   soyuz-client stubs.  Final sub-sprint adds CI gates so the
│   │   gains don't decay.
│   │
│   ├── Sprint 35.1 — Split ``pql/_branch.py``               ✅ closed 2026-05-06
│   │       ``pointlessql/pql/branch/`` package: ``_common.py``
│   │       (soyuz refs + URI/schema/audit/event helpers),
│   │       ``_create.py`` (creation + cloning), ``_discard.py``
│   │       (discard + storage cleanup), ``_promote.py`` (atomic
│   │       rename promote + version-equality conflict gate +
│   │       dry-run preview).  Cross-module helpers dropped leading
│   │       underscore so ``reportPrivateUsage`` stays clean;
│   │       module-internal helpers keep theirs.  ``_branch.py``
│   │       reduced to a 60-LOC re-export shim.  Tests update one
│   │       import-line + 5 patch-target renames; behaviour
│   │       byte-identical, 81 branch tests stay green, full
│   │       1478-test SQLite suite passes.
│   │
│   ├── Sprint 35.2 — Split ``services/lineage_edges.py``    ✅ closed 2026-05-06
│   │       1137 LOC → ``services/lineage/`` subpackage:
│   │       ``_types.py`` (dataclasses + exceptions + caps +
│   │       synth helpers + workspace-id resolver), ``rows.py``
│   │       (record_edges / record_rejects / walk_back / lookups),
│   │       ``columns.py`` (column-level analogs), ``values.py``
│   │       (record_value_changes with PII redaction hook).  Shim
│   │       at ``lineage_edges.py`` re-exports every old symbol;
│   │       12 import sites + 7 test files keep working unchanged.
│   │       58 lineage tests + 1478 SQLite suite green.
│   │
│   ├── Sprint 35.3 — Split ``services/audit_fts.py``        ✅ closed 2026-05-06
│   │       973 LOC → ``services/audit_fts/`` package:
│   │       ``__init__.py`` (public API + dispatcher + sanitiser
│   │       + time-filter), ``_sqlite.py`` (~330 LOC FTS5 DDL +
│   │       triggers + MATCH search + rebuild), ``_postgres.py``
│   │       (~330 LOC tsvector + GIN + PL/pgSQL triggers +
│   │       ts_rank search + ts_headline snippets + rebuild).
│   │       Old ``audit_fts.py`` removed; package's ``__init__.py``
│   │       exposes the same module name so all import sites keep
│   │       working.  25 audit-fts tests + 1478 SQLite suite green.
│   │
│   ├── Sprint 35.4 — Extract ``run_view.html`` partials     ✅ closed 2026-05-06
│   │       1467 LOC → 229-LOC parent + 8 partials in
│   │       ``frontend/templates/partials/_run_*.html``.  Closed
│   │       in Phase 38.1 (``8364faf``); Stream-A had deferred
│   │       this on the browser-playbook gate
│   │       (``feedback_run_playbook_as_gate.md``).  The actual
│   │       gate ended up being a run-detail Playwright replay
│   │       (the original plan had pointed at
│   │       ``audit-reviewer-daily.md``, which is a Hermes-cron
│   │       runbook with no browser surface, so the gate was
│   │       pivoted in-flight).  Verification covered all four
│   │       top-tabs, 13 sub-tabs, the URL-hash deeplink
│   │       activator, and the ``rollbackPanel`` Alpine factory.
│   │
│   ├── Sprint 35.5 — Module-level deltalake imports         ✅ closed 2026-05-06
│   │       Hoisted 13 lazy ``import deltalake`` from function
│   │       bodies to module top in ``_merge.py``, ``_autoload.py``,
│   │       ``engine.py``, ``_cdf.py``.  Plan estimated ≥40 fewer
│   │       pyright warnings — **actual is 0**: deltalake's stubs
│   │       are fine, the warnings are from incomplete pyarrow
│   │       stubs that the hoist can't reach.  Hoist still valuable
│   │       as code-quality cleanup.  Lesson: type annotations
│   │       can't save us from third-party stub gaps.
│   │
│   ├── Sprint 35.6 — ``cdf_table`` parameter typing         ✅ closed 2026-05-06
│   │       Annotated locals (``column_names: set[str]``,
│   │       ``data: dict[str, list[Any]]``, ``diff_columns:
│   │       list[str]``, ``row_id_raw: Any``) in
│   │       ``value_change_capture.py``.  Per-file: 22 → 13
│   │       warnings (-9); global: 531 → 522 (-9).  Plan estimated
│   │       18 — pyarrow ``list[Any]`` indexing stops cascading.
│   │
│   ├── Sprint 35.7 — ``_frame_to_arrow`` ``@overload``      ⏸ skipped
│   │       Investigation found the function already returns a
│   │       typed ``pa.Table``; callers see correct types.  Internal
│   │       "partially unknown" warnings come from
│   │       ``pa.array(...)`` and ``pa.Table.from_pandas(...)``
│   │       returning ``Unknown`` due to pyarrow's incomplete stubs
│   │       — ``@overload`` on the public surface cannot reach that
│   │       cascade.  Real reduction would need custom ``.pyi``
│   │       stubs for pyarrow; out of scope for a single sprint.
│   │       Skipped; warning floor freezes at 522 in 35.8.
│   │
│   └── Sprint 35.8 — File-size + warning budget CI          ✅ closed 2026-05-06
│           ``scripts/check-file-size-budget.sh`` (~75 LOC; 800-LOC
│           cap with allow-list of cohesive big-by-design files)
│           and ``scripts/check-pyright-budget.sh`` (~50 LOC;
│           freezes the post-35.6 522-warning floor + always-zero
│           errors).  Both wired into ``.pre-commit-config.yaml``
│           and the ``test.yml`` lint+type job.  Closes Phase 35.
│
├── Phase 36 — Declarative Pipelines + Expectations          ✅ closed 2026-05-06
│   │
│   │   Integrate dbt-duckdb (de-facto declarative pipeline
│   │   engine) and dbt-tests + dbt-expectations + dbt-utils
│   │   (de-facto data-quality test suite) into the existing
│   │   forced-audit / lineage / anomaly stack.  PointlesSQL
│   │   contributes the *bridge layer*, not the engine: dbt
│   │   manifest + run_results parse → ``agent_run_operations``
│   │   rows + ``lineage_row_edges`` + ``lineage_row_rejects``
│   │   (with a new ``expectation_failed`` reject reason) +
│   │   ``expectation_failure`` axis in the Anomaly Inbox.
│   │   Plan: [.claude/plans/ja-plane-phase-28-tidy-feather.md]
│   │   (../.claude/plans/ja-plane-phase-28-tidy-feather.md).
│   │   Picks: integrate dbt (not reinvent), Subprocess + on-
│   │   demand CLI mode (analog MLflow), dbt-tests +
│   │   dbt-expectations + dbt-utils as Quality stack.
│   │
│   ├── Sprint 36.1 — dbt subprocess + settings + reverse-proxy  ✅
│   │       New ``DBTSettings`` block in settings.py
│   │       (``POINTLESSQL_DBT_*`` env-prefix, default
│   │       ``project_dir=dbt_project/``, ``docs_port=5002``).
│   │       New ``services/dbt_subprocess.py`` mirrors
│   │       ``mlflow_subprocess.py``: async spawn of
│   │       ``dbt docs serve``, HTTP health-poll on the SPA root,
│   │       PID file, SIGTERM-then-SIGKILL shutdown.  Pre-flight
│   │       ``project_ready()`` check skips the spawn (and the
│   │       attendant noise) when no compiled manifest exists yet.
│   │       New ``api/dbt_proxy.py`` reverse-proxy at
│   │       ``/dbt-docs/{path:path}`` with auth gate +
│   │       ``X-DBT-User`` header injection.  New
│   │       ``api/dbt_html_routes.py`` chrome page at ``/dbt`` with
│   │       icon-rail entry (``bi-bezier2``).  Optional extra
│   │       ``[dbt]`` adds ``dbt-duckdb >= 1.9, < 2.0`` (the dbt
│   │       packages ``dbt-expectations`` / ``dbt-utils`` install
│   │       via ``dbt deps`` from ``packages.yml``, not pip).
│   │       14 new unit tests (8 subprocess + 6 proxy).  Bridge
│   │       code lands in 36.2; 36.1 is pure infrastructure.
│   │
│   ├── Sprint 36.2 — dbt run/test on-demand + manifest bridge   ✅
│   │       Three new POST routes (compile / run / test) plus an
│   │       admin-only deps route.  ``services/dbt_executor.py``
│   │       wraps the dbt CLI as an async subprocess with timeout
│   │       and 256 KiB output cap; ``services/dbt_bridge.py``
│   │       parses ``manifest.json`` + ``run_results.json`` and
│   │       emits one ``agent_run_operations`` row per executed
│   │       model + test (new op_names ``dbt_model`` / ``dbt_test``,
│   │       alembic ``kk1m3o5q7s9v`` extends the CHECK).  Routes
│   │       auto-create an ``AgentRun`` (``agent_id="dbt-cli"``)
│   │       when no caller-supplied run id is present.  19 new
│   │       tests; pyright budget 522 → 528 for JSON parse cascade.
│   │
│   ├── Sprint 36.3 — test-failure → rejects + expectation axis  ✅
│   │       ``REJECT_REASONS`` + the SQL CHECK gain
│   │       ``expectation_failed`` (alembic ``ll2n4p6r8t0w``).
│   │       ``services/dbt_bridge.emit_test_failure_rejects`` walks
│   │       (node, op_id) pairs in lockstep and inserts one
│   │       ``lineage_row_rejects`` row per failing dbt test
│   │       (``status='fail'``).  Per-row extraction (one reject per
│   │       failing data row) is deferred — dbt needs ``--store-
│   │       failures`` for that.  Audit aggregator gains an
│   │       ``expectation_failures`` axis: a row-level filter on
│   │       the reject table so the cockpit can show dbt-side data-
│   │       quality failures separately from merge-time rejects.
│   │       ``/api/dbt/run`` summary carries ``rejects_inserted``.
│   │       4 new tests; pre-commit chain green.
│   │
│   ├── Sprint 36.4 — Cockpit /dbt index + run-view sub-tab     ✅
│   │       Landed alongside BUG-37-06 fix: manifest summary
│   │       card-row (model count + test count + coverage
│   │       ratio) above a 3-tab nav (Pipeline docs / Recent
│   │       runs / Test failures).  New ``GET /api/dbt/runs``
│   │       lists the 20 newest ``agent_id='dbt-cli'``
│   │       AgentRun rows; existing
│   │       ``GET /api/dbt/test-failures`` had its
│   │       ``agent_run_id`` query param made optional so the
│   │       cockpit can show recent failures across every run
│   │       (each row links back to ``/runs/{id}``).
│   │
│   ├── Sprint 36.5 — severity enforcement + dbt CloudEvents    ✅
│   │       Three new governance event types
│   │       (``pointlessql.dbt.run.completed`` always,
│   │       ``pointlessql.dbt.test.failed`` per error-severity
│   │       failing test, ``pointlessql.dbt.test.warned`` per
│   │       warn-severity failing test).  ``_classify_severity``
│   │       splits dbt failures by severity; auto-created runs
│   │       finish as ``failed`` only when ``err_failures > 0`` —
│   │       warn-severity failures still let the run land as
│   │       ``succeeded`` and ride out via the anomaly inbox.
│   │       Auto-rollback path (rolling back tested-against models
│   │       on error-severity failure) deferred to a follow-up;
│   │       ``pql.rollback``'s four refusal modes need careful
│   │       gating that exceeds this sprint's scope.  7 new tests.
│   │
│   ├── Sprint 36.6 — plugin tools (hermes-plugin-pointlessql)  ✅
│   │       Three new Hermes tools land in
│   │       ``~/git/hermes-plugin-pointlessql``: ``pql_dbt_compile``
│   │       (read-only), ``pql_dbt_run`` (supervisor scope),
│   │       ``pql_dbt_test`` (supervisor scope).  Each forwards
│   │       ``POINTLESSQL_AGENT_RUN_ID`` via ``X-Agent-Run-Id`` so
│   │       the dbt subprocess's operations attribute under the
│   │       same forced-audit-trail run as the rest of the agent's
│   │       work.  ``PointlessClient`` gains matching ``dbt_compile``
│   │       / ``dbt_run`` / ``dbt_test`` methods.  6 new tool tests +
│   │       updated ``register_all`` expected-set; 113 plugin tests
│   │       green.  The 3 read-only tools sketched in the plan
│   │       (list_models / show_lineage / get_test_failures) need
│   │       new manifest-introspection endpoints on the
│   │       PointlesSQL side and are deferred — picked back up in
│   │       sub-sprint 36.B below.
│   │
│   ├── Sprint 36.A — sample dbt project + integration test    ✅
│   │       (Phase-36 Restabschluss) A 3-model / 5-test demo
│   │       project lands at ``dbt_project/`` (bronze → silver →
│   │       gold pipeline plus ``not_null`` / ``unique`` /
│   │       ``accepted_values`` / ``relationships`` tests against
│   │       a 10-row CSV seed); ``tests/test_dbt_real_subprocess.py``
│   │       (``@pytest.mark.integration``) runs real ``dbt
│   │       compile`` + a full ``dbt seed → run → test`` against
│   │       the project, asserts against the bridge's
│   │       :func:`merge_manifest_and_results` projection, and skips
│   │       cleanly when ``dbt-duckdb`` isn't importable for the
│   │       running interpreter (Python-3.14 + dbt-duckdb-1.9
│   │       currently raises ``mashumaro.UnserializableField``
│   │       during CLI module import).  New
│   │       :meth:`DBTExecutor.seed` lets the test (and future
│   │       agent flows) materialise CSV seeds without reaching
│   │       into ``_run``.
│   │
│   ├── Sprint 36.B — read-only manifest API + plugin tools    ✅
│   │       (Phase-36 Restabschluss) Three new GET routes:
│   │       ``/api/dbt/manifest`` projects ``target/manifest.json``
│   │       to a model summary with attached tests (any
│   │       authenticated user); ``/api/dbt/coverage`` reports the
│   │       test-coverage ratio + untested-model list;
│   │       ``/api/dbt/test-failures`` joins
│   │       ``lineage_row_rejects`` (where
│   │       ``reason='expectation_failed'``) with
│   │       ``agent_run_operations`` (supervisor or auditor scope)
│   │       and returns one row per failing test.  The
│   │       manifest-projection logic moves to
│   │       :mod:`pointlessql.services.dbt_bridge` (``as_dict`` /
│   │       ``as_list`` / ``project_models``) so the plugin's
│   │       ``pql_dbt_show_lineage`` reuses the same projection.
│   │       Three new Hermes tools land plugin-side:
│   │       ``pql_dbt_list_models`` (no-arg manifest summary),
│   │       ``pql_dbt_show_lineage`` (parents/children walk,
│   │       accepts ``unique_id`` or short name), and
│   │       ``pql_dbt_get_test_failures`` (per-run failing tests
│   │       with model relation, severity, and op id).  Closes
│   │       the trigger → inspect loop.
│   │
│   ├── Sprint 36.D — dbt bridge captures Delta versions       ✅
│   │       (Phase-36 Restabschluss) Closes the production-side
│   │       gap surfaced after 36.C landed: every dbt-driven
│   │       rollback was refused with ``RollbackInvalid`` because
│   │       the bridge wrote ``delta_version_before=None``.  New
│   │       :func:`capture_delta_versions` reads each relation's
│   │       soyuz-catalog ``storage_location`` + opens it with
│   │       :class:`deltalake.DeltaTable` to capture the version;
│   │       best-effort, returns ``None`` for non-Delta targets.
│   │       ``/api/dbt/{run,test}`` calls it twice (pre-execution
│   │       + post-execution) and the bridge stamps each
│   │       ``dbt_model`` op's ``delta_version_before`` /
│   │       ``delta_version_after`` columns from the maps.
│   │       Limitation: dbt-duckdb's default ``table``
│   │       materialisation writes DuckDB-native tables, not
│   │       Delta — for those, the version stays ``None`` and
│   │       auto-rollback still refuses (the correct conservative
│   │       path).  Meaningful for projects that opt into the
│   │       Delta materialisation adapter or write through PQL.
│   │
│   ├── Sprint 36.C — auto-rollback on error-severity test     ✅
│   │       (Phase-36 Restabschluss) ``POST /api/dbt/test`` accepts
│   │       a new ``auto_rollback: bool`` body parameter (default
│   │       ``False``).  When set and the run has at least one
│   │       error-severity failing test, the route walks every
│   │       ``dbt_model`` op in the run (newest-first) and invokes
│   │       ``pql.rollback`` for each — collecting per-target
│   │       outcomes (``succeeded`` vs. ``failed``) into the
│   │       response envelope's new ``auto_rollback`` block.
│   │       Per-target refusals (``RollbackStale``,
│   │       ``RollbackInvalid``, …) land in ``failed`` rather than
│   │       aborting the sweep — auto-rollback is best-effort by
│   │       design.  A new
│   │       ``pointlessql.dbt.auto_rollback.executed`` CloudEvent
│   │       fires once per attempted unwind with the aggregate
│   │       counts.  Auto-rollback fires *only* on the test path:
│   │       model writes are reverted because tests failed, never
│   │       as a side-effect of the run itself.
│   │
│   └── Sprint 36.7 — end-to-end walkthrough + close            ✅ closed 2026-05-06
│           Walkthrough replayed end-to-end against the e2e
│           stack: ``dbt compile`` + ``dbt docs generate``
│           land ``manifest.json`` + ``catalog.json``, the
│           lifespan subprocess spawns ``dbt docs serve``,
│           the Phase-36.4 cockpit chrome populates with
│           ``models=3 / tests=6 / coverage=66.7%``, both
│           ``/api/dbt/runs`` + ``/api/dbt/test-failures``
│           lazy-load on tab activation with the documented
│           empty-state messages.  0 console errors on
│           ``/dbt`` after ``dbt docs generate`` lands the
│           catalog file.
│
│           **Mashumaro/Python-3.14 unblock.** Phase 38.2
│           had verified the ``mashumaro 3.14`` upstream
│           blocker against the latest pins; the GitHub-issue
│           dbt-labs/dbt-core#12098 pointed at ``mashumaro
│           3.17`` as the fix.  ``dbt-core 1.11`` declares
│           ``mashumaro<3.15``, but force-installing
│           ``mashumaro==3.17`` runs clean against
│           ``dbt-core 1.11.8`` + ``dbt-adapters 1.22.10``.
│           The override now lives in ``pyproject.toml``
│           ``[tool.uv] override-dependencies`` so
│           ``uv sync --extra dbt`` produces a working
│           environment on Python 3.14 without manual
│           intervention.  Walkthrough Part C carries the
│           ad-hoc ``pip install --no-deps mashumaro==3.17``
│           recipe for the in-place upgrade path.
│
├── Phase 37 — Playwright coverage refresh (post-22/23)     ✅
│   │
│   │   Brings ``docs/e2e-walkthroughs/`` back to complete UI
│   │   coverage after Phase 14, 17, 18.6+, 28, 33, and 36
│   │   landed pages without dedicated playbooks.  Six waves,
│   │   one fix-commit + 6 doc-commits.  6 BUG-37-NN filed; 1
│   │   fixed in same session.
│   │
│   ├── Wave 0a — refresh ``audit-sinks.md``                    ✅
│   │       Rewrote from curl-only operational runbook to UI-
│   │       driven 6-step walkthrough (Phase 33.2 added the
│   │       admin page that the original playbook said didn't
│   │       exist).  Surfaced + fixed BUG-37-01 in ``a744b52``:
│   │       Alpine ``x-data`` attribute escaping on four admin
│   │       row templates (``audit_sinks``, ``review_destinations``,
│   │       ``workspaces``, ``api_keys``) — JSON-encoded string
│   │       inside double-quoted HTML attribute broke the
│   │       parser.  All four page's per-row Alpine bindings
│   │       (toggle / Test / Delete / Revoke) were dead before
│   │       the fix.  Pytest never executed the Alpine layer.
│   │
│   ├── Wave 0b — refresh ``grand-tour.md``                     ✅
│   │       Three surgical updates: workspace-switcher Note in
│   │       Act 1, admin landing flow in Act 10, redaction-
│   │       marker assertion in Act 12.  Acts 4/5/6/13 already
│   │       covered Phase 17 (icon-rail + four-tab run-detail).
│   │
│   ├── Wave 1 — new ``admin-console.md``                       ✅
│   │       Phase-33 admin landing 7-card grid + 5 sub-pages
│   │       (``api-keys``, ``review-destinations``,
│   │       ``system-info``, ``external-writes``).  ~30 steps.
│   │       The api-keys plaintext-secret modal carries the
│   │       strongest redaction property in the whole codebase:
│   │       secret lives in the ``<input>`` ``.value`` DOM
│   │       property only, never serialised into ``outerHTML``
│   │       (Alpine ``:value`` binding does not write through
│   │       to the HTML attribute).  Page-source view literally
│   │       cannot leak a freshly-issued secret.  BUG-37-02 +
│   │       BUG-37-03 filed (admin sidebar incomplete + icon-
│   │       rail duplicate Admin link).
│   │
│   ├── Wave 2 — new ``audit-cockpit-deep.md``                  ✅
│   │       Phase-18.6 → 18.x cockpit: anomaly inbox + FTS
│   │       search + by-table reverse index + saved queries
│   │       workbench.  18 steps split into chrome path
│   │       (``seed-e2e.py``) vs data path (``seed-full-stack-
│   │       demo.py --demo-rollback``).  BUG-37-04 (HTMX null-
│   │       property TypeError on ``/audit/inbox`` page-load) +
│   │       BUG-37-05 (``/audit/by-table`` empty path renders
│   │       ``Error 422`` text in tab loaders) filed.
│   │
│   ├── Wave 3 — new ``run-comparisons.md``                     ✅
│   │       Single playbook for both compare surfaces — audit
│   │       run-diff at ``/runs/{a}/diff/{b}`` (6-tab Chart.js
│   │       structured) + jobs run-compare at
│   │       ``/jobs/{id}/runs/{a}/compare?with={b}`` (side-by-
│   │       side notebook iframes).  Carries the Phase-18
│   │       prior-art Chart.js async-render mitigation (``shown.
│   │       bs.tab`` + ``browser_wait_for``).
│   │
│   ├── Wave 4 — new ``alerts.md``                              ✅
│   │       Alert list + detail + destination CRUD + ``/alerts/
│   │       feed.atom`` + ``/alerts/feed.json`` per-user pull
│   │       feeds.  9 steps.  Generalised BUG-37-04 to a 3-page
│   │       bug class (``/audit/inbox``, ``/audit/search``,
│   │       ``/alerts``).
│   │
│   ├── Wave 5 — new ``dbt-pipeline.md`` (D3b path)             ✅
│   │       Walkthrough for ``/dbt`` covering both states (iframe
│   │       to ``/dbt-docs/`` + warning card when subprocess is
│   │       down).  Plan's preferred D3a (build 36.4 chrome
│   │       first) was de-scoped under session-time constraint;
│   │       D3b path: write playbook against today's iframe-only
│   │       chrome + file BUG-37-06 with explicit fix locations
│   │       for the missing manifest summary card / test-failures
│   │       table / run-view sub-tab.  Phase-36.B read-only API
│   │       surface (``/api/dbt/manifest``, ``/coverage``,
│   │       ``/test-failures``) exercised programmatically as
│   │       documentation of the consumer contract the missing
│   │       chrome would use.  Sprint 36.4 stays ``⏸ Playwright``.
│   │
│   └── Wave 6 — README + CLAUDE.md + ROADMAP wrap-up           ✅
│           ``docs/e2e-walkthroughs/README.md`` index updated
│           with the 5 new entries.  CLAUDE.md playbook count
│           refreshed to 48.  CHANGELOG + this ROADMAP entry
│           record the wave.
│
├── Phase 37.1 — Phase-37 BUG sweep (post-walkthrough fix)    ✅
│   │
│   │   One-shot fix sweep that closed the five open BUG-37-NN
│   │   tickets surfaced during the Phase-37 live replay.
│   │   Verified end-to-end via Playwright MCP: zero console
│   │   errors across ``/audit/inbox``, ``/audit/search``,
│   │   ``/alerts``, ``/audit/by-table``, ``/admin``, and
│   │   ``/dbt`` after the fixes landed.
│   │
│   ├── BUG-37-02 ✅ — admin context-panel completed.
│   │       [components/context_panel.html](frontend/templates/components/context_panel.html)
│   │       admin section now lists all nine entries
│   │       (Overview, Audit log, Audit cockpit, External
│   │       writes, Workspaces, Audit sinks, Review
│   │       destinations, API keys, System info).  Active
│   │       highlighting driven by ``request.url.path`` so
│   │       no backend ``active_page`` plumbing churn.
│   │
│   ├── BUG-37-03 ✅ — duplicate Admin link removed.
│   │       Mobile-only [components/nav_links.html](frontend/templates/components/nav_links.html)
│   │       Admin entry was a Bootstrap dropdown with
│   │       ``href="#"`` shell over a single ``/admin/audit``
│   │       child link.  Replaced with a direct ``/admin``
│   │       link; both desktop icon-rail and mobile drawer
│   │       now point at the same destination.
│   │
│   ├── BUG-37-04 ✅ — htmx 2.0.3 → 2.0.6 CDN bump.
│   │       Root cause was an unguarded ``o.includes("?")``
│   │       in htmx 2.0.3's GET-request constructor; certain
│   │       boost-eligible page-loads synthesised a request
│   │       with a null URL.  htmx 2.0.6 added the
│   │       ``if (o == null || o === "") o = location.href``
│   │       guard before the call.  One-line edit in
│   │       [base.html](frontend/templates/base.html).
│   │
│   ├── BUG-37-05 ✅ — empty-FQN picker for /audit/by-table.
│   │       Added a ``GET /audit/by-table`` (no path
│   │       parameter) handler in
│   │       [api/audit_by_table_routes.py](pointlessql/api/audit_by_table_routes.py)
│   │       that renders ``kinds=[]``; the template now
│   │       serves an FQN input + Open button on the empty
│   │       branch, blocking the three 422-firing tab
│   │       loaders.  ``/audit/by-table/{fqn:path}`` with
│   │       a real FQN keeps the historical tab cockpit.
│   │
│   └── BUG-37-06 ✅ — Phase-36.4 dbt cockpit chrome.
│           [pages/dbt.html](frontend/templates/pages/dbt.html)
│           grew a 3-card summary row + 3-tab nav (Pipeline
│           docs / Recent runs / Test failures) plus the
│           wiring JS.  Backend additions:
│           ``GET /api/dbt/runs`` (new, lists 20 newest
│           ``agent_id='dbt-cli'`` AgentRuns) and
│           ``GET /api/dbt/test-failures`` made
│           ``agent_run_id`` optional (returns 50 most
│           recent failures across all dbt runs when
│           omitted).  Sprint 36.4 flipped from ``⏸ Playwright``
│           to ``✅`` since the chrome the playbook called
│           for is now in main.
│
├── Phase 38 — Sprint-Sweep (35.4 close + 36.7 defer + cockpit) ✅
│   │
│   │   One autonomous session post the "plane die restliche
│   │   aufgaben aus" plan.  Three sub-sprints, three commits
│   │   on top of the Phase-37.1 line.  Closes Phase 35
│   │   completely; Phase 36 stays ``⏳ in progress`` on a
│   │   cleanly-documented upstream blocker.
│   │
│   ├── Sprint 38.1 ✅ — close Sprint 35.4 (run_view.html split).
│   │       1467 LOC → 229 LOC parent + 8 partials in
│   │       ``frontend/templates/partials/_run_*.html``
│   │       (header, metadata, conformance, approval form,
│   │       four tab panes).  Behaviour-equivalent.  Verified
│   │       end-to-end via Playwright MCP against
│   │       ``seed-broken-run.py`` + a partial
│   │       ``seed-full-stack-demo.py`` run: all four top-tabs
│   │       and 13 sub-tabs render with 0 console errors;
│   │       URL-hash deeplink (``#tab-external-writes``)
│   │       activates BOTH parent + leaf via the inline
│   │       activator; ``rollbackPanel`` Alpine factory binds
│   │       cleanly with three pre-picked targets and the
│   │       ``:class="{ 'd-block': modalOpen }"`` modal toggle
│   │       preserved (BUG-67-01-class regression check).
│   │       Phase 35 closes here.
│   │
│   ├── Sprint 38.2 ⏸ — Sprint 36.7 stays deferred (upstream).
│   │       Ran the upfront feasibility check from the plan:
│   │       ``dbt-duckdb 1.10.1`` + ``dbt-core 1.11.8`` +
│   │       ``mashumaro 3.14`` on Python 3.14.4 still raises
│   │       ``UnserializableField: Field "schema" of type
│   │       Optional[str] in JSONObjectSchema`` at import time.
│   │       Root cause is mashumaro's unpacker compiler not
│   │       handling ``Optional[str]`` annotations under
│   │       Python 3.14; no workaround available downstream.
│   │       ``docs/e2e-walkthroughs/dbt-pipeline.md`` Part C
│   │       Caveat updated with the exact pins + trace +
│   │       verification date so the next contributor knows
│   │       whether the upstream picture has changed.
│   │       Sprint 36.7 status flipped from ``⏸ Playwright`` to
│   │       ``⏸ upstream``.  Phase 36 stays ``⏳ in progress``.
│   │
│   └── Sprint 38.3 ✅ — data-path replay of audit-cockpit-deep.
│           Phase-37 Wave 2 had verified the chrome path
│           against ``seed-e2e.py``; this sub-sprint exercises
│           the four cockpit axes against real audit activity.
│           ``/audit/inbox`` shows "2 of 2 breach(es) — metrics
│           rejects, errored_ops, 7d baseline at 2σ" from the
│           seed-broken-run fixture.  ``/api/audit/search?q=silver``
│           returns 1 hit (custom tokenizer matches FQN path
│           segments).  ``/audit/by-table/demo.incidents.broken_orders``
│           heading reads "Runs that touched …", Touched tab
│           counter "2 run(s) touched …".  All 5 starter
│           queries seeded; ``top-mutating-principals-30d``
│           ``POST /run`` returns 200 with 2 rows + columns
│           ``principal, rows_written``.  0 console errors
│           throughout.  ``audit-cockpit-deep.md`` carries a
│           "Verification log" entry stamped 2026-05-06.
│
├── Phase 39 — Agent EXPLAIN-driven self-rewrite loop      ✅ closed 2026-05-06
│   │
│   │   AI-native-lakehouse differentiator landed in one
│   │   autonomous session: agents see DuckDB
│   │   ``EXPLAIN (FORMAT JSON)`` + cost-gate verdict before
│   │   they execute, rewrite SQL when the cost-gate denies,
│   │   and only escalate to human approval after three
│   │   failed attempts.  Each loop resolution is captured in
│   │   the new ``rewrite_attempts`` table for end-to-end
│   │   auditor inspection.  Fits the
│   │   ``project_ai_native_vision.md`` "supervision surface,
│   │   not cheaper Databricks" pitch directly.
│   │
│   │   **Cross-repo drop:** PointlesSQL commits ``e413f42`` /
│   │   ``49aba6c`` / ``305d9e4``; ``hermes-plugin-pointlessql``
│   │   commit ``576c5dc``.  Two new Alembic migrations
│   │   (``mm3o5q7s9u1x`` op_name + ``nn4p6r8t0v2y`` table).
│   │
│   ├── Sprint 39.1 — per-run sql_explain audit row           ✅ done (e413f42)
│   │       ``pql_explain`` tool + ``GET /api/sql/explain``
│   │       endpoint already shipped Phase 14; the Phase-39
│   │       gap was the per-run audit.  Endpoint now writes
│   │       one ``agent_run_operations.op_name='sql_explain'``
│   │       row per call when ``X-Agent-Run-Id`` is set.
│   │       Migration ``mm3o5q7s9u1x`` extends the op_name
│   │       CHECK; malformed UUIDs in the header are silently
│   │       demoted to "no run" so a typo doesn't 500.
│   │
│   ├── Sprint 39.2 — rewrite_attempts table + Rewrites sub-tab  ✅ done (49aba6c)
│   │       New ``rewrite_attempts`` table (Alembic
│   │       ``nn4p6r8t0v2y``) with ``(agent_run_id, attempt_no)``
│   │       UNIQUE + verdict CHECK in
│   │       ``{auto_rewrite_succeeded, auto_rewrite_failed,
│   │       human_approval_required, original_approved}``.
│   │       New ``POST /api/agent-runs/{id}/rewrite-attempt``
│   │       route accepts the plugin envelope, enforces
│   │       workspace match, returns 409-class on duplicate
│   │       attempts.  Run-detail Operations top-tab gets a
│   │       new "Rewrites" sub-pane with verdict badges +
│   │       Δ-cost colour coding.
│   │
│   ├── Sprint 39.3 — explain-first plugin rewrite loop       ✅ done (576c5dc)
│   │       ``hermes-plugin-pointlessql`` ``pql_query`` tool
│   │       now hits ``/api/sql/explain`` before
│   │       ``/api/sql/execute``.  On ``needs_approval=True``
│   │       the tool returns a structured
│   │       ``{ok:false, error:'cost_gate_denied', explain,
│   │       hint, attempt_no}`` envelope so the LLM sees the
│   │       plan + a rewrite hint.  Per-run state on the
│   │       client tracks attempts + the original SQL hash;
│   │       at attempt 4 the envelope flips to
│   │       ``human_approval_required`` and a
│   │       ``rewrite_attempts`` row is POSTed.  A subsequent
│   │       successful rewrite writes a second
│   │       ``auto_rewrite_succeeded`` row.  Audit POSTs are
│   │       fail-soft so an older PointlesSQL server lacking
│   │       the route doesn't crash the agent turn.
│   │
│   └── Sprint 39.4 — walkthrough + Grafana panel 21         ✅ done (305d9e4)
│           ``docs/e2e-walkthroughs/explain-rewrite.md`` is
│           the 49th playbook (Parts A-D: trip, rewrite,
│           UI inspection, three-attempt escalation).
│           Grafana panel id 21 ("Rewrite savings — averted
│           cost-gate denials per week") added to both the
│           SQLite and Postgres audit dashboards with
│           dialect-aware queries against
│           ``rewrite_attempts``.  CLAUDE.md walkthrough
│           count bumped 48 → 49.
│
├── Phase 40 — Lakehouse Federation reads (OpenLineage)        ✅ done
│   │
│   │   PointlesSQL today emits OpenLineage events outbound
│   │   (Phase 15 PQL→soyuz facets) and registers Delta tables
│   │   for federated writes (soyuz Lakehouse Federation).
│   │   This phase closed the loop on the read side: external
│   │   producers POST OpenLineage events to PointlesSQL, edges
│   │   normalise into the existing shadow tables tagged with a
│   │   ``producer``, and the table-detail lineage card surfaces
│   │   the merged graph plus a per-producer freshness widget
│   │   driven by an admin-registered expectation table.
│   │
│   │   **Strategic frame:** User flag — "essentiell für
│   │   federation".  Closes the inbound half of the audit-
│   │   graph story, vs DBX Unity Catalog Lineage which is
│   │   single-source.  Sprint 40.2 (CDF tail of foreign Delta
│   │   tables) was deliberately deferred to Phase 40.5 at plan
│   │   time — push-modell (40.1) is the MVP; pull-modell waits
│   │   for a concrete legacy-ETL producer to ask.
│   │
│   ├── Sprint 40.0 — prep migration + lineage_inbound scope ✅ done (0a23222)
│   │       Alembic ``oo5q7s9u1x3z`` relaxes ``run_id`` /
│   │       ``op_id`` to nullable on ``lineage_row_edges`` /
│   │       ``lineage_column_map`` and adds ``producer`` +
│   │       ``external_event_id`` columns.  ``api_keys.lineage_inbound``
│   │       boolean scope, env-var bootstrap, admin CRUD, and
│   │       admin-page badge column all carry the new flag.
│   │       ``require_lineage_inbound`` guard added.  Knock-on
│   │       type changes: ``PredecessorRef.op_id`` and
│   │       ``ColumnPredecessorRef.op_id`` become ``int | None``
│   │       to match the schema; run-scoped diffs narrow
│   │       defensively.
│   │
│   ├── Sprint 40.1 — OpenLineage inbound endpoint            ✅ done (83b3e37)
│   │       ``POST /api/lineage/openlineage`` accepts an
│   │       OpenLineage 1.x ``RunEvent`` envelope, normalises
│   │       ``inputs`` / ``outputs`` / ``columnLineage`` facets
│   │       into ``lineage_column_map`` rows tagged with
│   │       ``producer = event.job.namespace`` and
│   │       ``external_event_id = event.run.runId``.  Custom
│   │       ``pointlessql.lineage.row`` output facet emits row-
│   │       level edges.  Auth via the new ``lineage_inbound``
│   │       scope; workspace scoping comes from the API key.
│   │       Idempotent on ``(producer, external_event_id, ...)``
│   │       composite keys; a CloudEvents envelope of type
│   │       ``pointlessql.lineage.inbound.received`` fans out via
│   │       ``dispatch_to_sinks`` so Grafana / inbox sinks see
│   │       inbound traffic.  Tolerates OL 2.x facets forward-
│   │       compat (``extra="allow"``).  8 pytest cases.
│   │
│   ├── Sprint 40.2 — soyuz federated-table CDF tail          ✅ closed via Phase 40.5
│   │       Plan-phase trim 2026-05-06 deferred this to Phase 40.5;
│   │       2026-05-07 Phase 40.5 landed the implementation as a
│   │       single sprint.  See Phase 40.5 below for execution
│   │       detail.
│   │
│   ├── Sprint 40.3 — table-detail merged lineage card        ✅ done (28eb537)
│   │       ``catalog_html_routes.table_detail`` joins a new
│   │       ``_external_producers_for_table`` aggregator into
│   │       the template context.  ``components/lineage_card.html``
│   │       grows an "External producers" block below the
│   │       internal up/down-stream sections, rendered with
│   │       amber Bootstrap badges + a dotted ``border-warning``.
│   │       Empty-state widens to also require zero external
│   │       producers.  6 pytest cases.
│   │
│   └── Sprint 40.4 — expected-producer registry + freshness  ✅ done (20400f0)
│           Alembic ``pp6r8t0v2x4z`` adds ``expected_lineage_inbound``
│           with a UNIQUE on
│           ``(workspace_id, target_table_full_name, producer)``.
│           ``services/lineage_freshness.py`` exposes
│           ``compute_freshness`` (per-row verdicts:
│           ``fresh`` / ``stale`` / ``never_seen`` / ``inactive``),
│           ``select_alert_candidates`` (cooldown-aware filter),
│           ``stamp_alerted``, and ``fresh_envelope`` (CloudEvents
│           ``pointlessql.lineage.freshness.stale`` builder).
│           Admin CRUD + freshness JSON live under
│           ``/api/admin/expected-producers``.  13 pytest cases.
│
├── Phase 41 — Sprint 17.6 promote: Lineage sub-panes         ✅ done
│   │
│   │   Three new drill-down sub-pills (Row trace / Column trace /
│   │   Value changes) now sit next to the existing Summary +
│   │   Graph pills inside the Lineage top-tab on
│   │   ``/runs/{id}``.  Pure UX consolidation: each sub-pill
│   │   wraps an existing JSON endpoint
│   │   (``/api/lineage/row-trace``, ``/api/lineage/column-trace``,
│   │   ``/api/lineage/value-changes``); no new SQL surface.  The
│   │   standalone ``/catalogs/.../rows/{id}/trace`` and
│   │   ``/catalogs/.../columns/{name}/trace`` pages stay
│   │   route-mounted for direct-link compatibility.  Deep-link
│   │   plumbing — Summary "Trace target row" button + Graph
│   │   side-panel "Trace this column" button — flips the active
│   │   pill via Bootstrap-Tab JS and stuffs the picker via three
│   │   custom window events (``pql:trace-row`` /
│   │   ``pql:trace-column`` / ``pql:trace-value``).
│   │
│   └── Sprint 41.1 — embed lineage drill-downs as sub-panes  ✅
│           Three new tab-panes inside
│           [`partials/_run_tab_lineage.html`](frontend/templates/partials/_run_tab_lineage.html);
│           three Alpine factories
│           (``rowTracePane`` / ``columnTracePane`` /
│           ``valueChangesPane``) ship in
│           [`components/lineage_panes.js`](frontend/js/components/lineage_panes.js)
│           and register on ``window`` via
│           [`bootstrap.js`](frontend/js/bootstrap.js).  The
│           ``load_lineage_summary_for_run`` loader gained one
│           ``func.min(LineageRowEdge.target_row_id)`` column
│           (``sample_target_row_id``) so the Summary "Trace"
│           button can deep-link concretely; the new key is
│           additive in
│           ``GET /api/agent-runs/{id}/audit/lineage``.  3 new
│           pytest cases (loader extension, sub-pill mount,
│           deep-link button attrs); browser replay against the
│           rebuilt e2e container confirmed zero console errors
│           + end-to-end fetch (Summary → Row trace pane → 2
│           steps loaded from
│           ``/api/lineage/row-trace``).
│
├── Phase 40.5 — Foreign-Delta CDF tail (pull-modell)        ✅ done
│   │
│   │   Closes the deferred Sprint-40.2 sketch as a single
│   │   sprint.  Admins register one
│   │   :class:`CdfTailSubscription` per Delta table whose
│   │   Change Data Feed they want PointlesSQL to tail; the new
│   │   ``_cdf_tail_loop`` worker reads
│   │   ``DeltaTable.load_cdf(starting_version=last+1)`` per
│   │   active subscription and INSERT-OR-IGNOREs every CDF row
│   │   into a new ``cdf_tail_events`` table.  Re-tails are
│   │   idempotent thanks to UNIQUE
│   │   ``(table_full_name, delta_version, row_id, change_type)``.
│   │
│   │   Anti-goal preserved: **no new credential surface**.  The
│   │   worker reuses whatever path/credentials soyuz's
│   │   ``storage_location`` already exposes; tables behind cloud
│   │   credentials we don't have stay un-tail-able and the
│   │   worker stamps a ``last_error`` row rather than failing
│   │   the whole tick.  Disabled by default
│   │   (``POINTLESSQL_CDF_TAIL_INTERVAL_SECONDS=0``); admins
│   │   opt in after registering subscriptions.
│   │
│   └── Sprint 40.5.1 — subscription registry + worker + admin CRUD
│           Alembic ``qq7t9v1x3z5b`` adds
│           ``cdf_tail_subscriptions`` (registry,
│           ``UNIQUE(workspace_id, table_full_name)``) and
│           ``cdf_tail_events`` (capture log, ``UNIQUE`` on the
│           4-tuple above).  ``services/cdf_tail.py`` exposes
│           ``tail_subscription`` (sync, scoped to one row) +
│           ``tail_all`` (async walker that resolves
│           ``storage_location`` via ``uc.get_table`` per tick
│           + stamps ``last_error`` on failure).
│           ``api/admin_cdf_tail_routes.py`` exposes admin CRUD
│           under ``/api/admin/cdf-subscriptions``
│           (GET / POST / toggle / DELETE) plus a manual
│           ``POST /run-now`` so admins can drive a tail without
│           flipping the loop interval.  New
│           :class:`CDFTailSettings` (``interval_seconds`` /
│           ``history_limit``) joins the root settings tree;
│           ``_cdf_tail_loop`` registers in the lifespan next to
│           the external-writes scanner with the same
│           opt-in / cancel-on-shutdown discipline.  9 pytest
│           cases (3 service unit, 3 ``tail_all`` integration,
│           3 admin CRUD).
│
├── Phase 40.6 — CDF Tail UI integration                  ✅ done
│   │
│   │   Phase-40.5 capture surfaced.  Three thin sprints turn
│   │   the CDF-tail backend from "API-only" into a fully
│   │   browsable + agent-readable governance surface.  No new
│   │   tables, no new credential surface — just admin UI,
│   │   table-detail tab, two auditor-scope plugin tools, and
│   │   one new auditor-scope read endpoint.  Anti-goal:
│   │   row-trace fold-in of CDF events stays deferred; CDF
│   │   events are a separate boundary from
│   │   ``lineage_row_edges`` and forcing them into walkback
│   │   semantics is a Phase-40.7 concern with its own scope.
│   │
│   ├── Sprint 40.6.1 — Admin subscriptions HTML page
│   │       New ``GET /admin/cdf-subscriptions`` HTML route on
│   │       ``api/admin_cdf_tail_routes.py``; new
│   │       ``frontend/templates/pages/admin_cdf_tail.html``
│   │       (CRUD + ``Run tail now`` + table-FQN substring
│   │       filter + only-active toggle).  Admin landing
│   │       (``api/admin_routes.py``) extended with two new
│   │       COUNTs (``active_cdf_subscriptions`` +
│   │       ``cdf_subscriptions_with_errors``) so the new
│   │       8th card on ``/admin`` carries badges.  Help-icon
│   │       slug ``admin.cdf-tail`` registered.  4 pytest
│   │       cases.
│   ├── Sprint 40.6.2 — Table-detail "CDF events" tab
│   │       ``api/catalog_html_routes.py`` loader extended with
│   │       two best-effort helpers
│   │       (``_cdf_subscription_for_table`` +
│   │       ``_cdf_recent_events_for_table``, both
│   │       workspace-scoped) and a 7th tab on
│   │       ``frontend/templates/pages/table.html`` that mounts
│   │       ONLY when a subscription exists for the rendered
│   │       table.  Tables without a subscription still show 6
│   │       tabs; no empty-tab visual noise.  2 pytest cases
│   │       (visibility + recent-events render).
│   └── Sprint 40.6.3 — Plugin tools + auditor-scope read endpoints
│           Two new auditor-scope endpoints in
│           ``api/audit_routes.py``:
│           ``GET /api/audit/cdf-subscriptions`` (workspace-scoped
│           list) and ``GET /api/audit/cdf-events`` (per-table
│           events with ``limit`` 1..500).  Two new plugin tools
│           in ``hermes-plugin-pointlessql`` registered in
│           ``register_auditor_tools``:
│           ``pql_list_cdf_subscriptions`` +
│           ``pql_recent_cdf_events_for_table``.  Mutation
│           tools deliberately not registered — admins register
│           via the admin UI, not from agent flows.  3 pytest
│           cases server-side + 6 plugin-side.  New 50th
│           walkthrough at
│           ``docs/e2e-walkthroughs/admin-cdf-tail.md``.
│
├── Phase 44 — Structured logging + traceback preservation ✅ done
│   │
│   │   Code-quality continuation closing four gaps in the logging
│   │   surface: ``JSONFormatter`` ignored ``extra={...}`` (half-
│   │   done structured logs), 36 broad-except sites lost
│   │   tracebacks via ``logger.warning("foo: %s", exc)``, 47
│   │   silent broad-excepts had no opt-out marker, zero
│   │   third-party loggers were quieted.  Six commits in one
│   │   autonomous run; no Alembic, no breaking change.
│   │
│   ├── Sprint 44.1 — ``extra={...}`` propagation in JSONFormatter
│   │       New ``_RESERVED_LOGRECORD_ATTRS`` filter set + new
│   │       ``_harvest_extras()`` helper.  ``JSONFormatter.format``
│   │       projects every non-reserved, non-``_``-prefixed
│   │       ``record.__dict__`` key into the JSON envelope as a
│   │       top-level field.  Base fields always merged AFTER
│   │       extras so the envelope shape stays stable.  8 pytest
│   │       cases; legacy seven-field shape preserved when caller
│   │       passes no ``extra=``.
│   │
│   ├── Sprint 44.2 — Convert lossy broad-except + AST lint test
│   │       28 Bucket-C sites (``logger.warning("...", exc)``)
│   │       converted to ``logger.exception("...")``.  Subset
│   │       changed to ``logger.<level>(..., exc_info=True)`` where
│   │       the original level was ``DEBUG`` or ``INFO`` (so
│   │       traceback lands at the same level, no surprise volume
│   │       jump).  Bucket-D silent sites (``pass`` /
│   │       ``return None``) got ``# bare-broad-ok: <reason>``
│   │       allowlist comments.  New
│   │       ``tests/test_no_lossy_broad_except.py`` AST-walks every
│   │       broad-except in the project and asserts each handler
│   │       (a) preserves the traceback, (b) re-raises, or
│   │       (c) carries the allowlist marker in the body /
│   │       preceding lines.  Lint covers both lossy logs and
│   │       silent-without-marker.
│   │
│   ├── Sprint 44.3 — Retrofit high-value sites to use extra={...}
│   │       Nine sites converted: scheduler runs (``job_id`` /
│   │       ``run_id`` / ``kind``), soyuz-lineage emit (``run_id``
│   │       / ``op_name``), ml-context (``agent_run_id`` /
│   │       ``mlflow_run_id``), training-context (``framework`` /
│   │       ``mlflow_run_id``), notebook render (``run_id``),
│   │       alert dispatcher (``webhook_url`` / ``status_code`` /
│   │       ``attempt``), audit self-track (``endpoint``),
│   │       read-audit (``read_kind`` / ``table_fqn``).  Existing
│   │       159 logger calls migrate opportunistically.  3 pytest
│   │       cases pin the contract.
│   │
│   ├── Sprint 44.4 — Quiet noisy third-party loggers
│   │       New ``_THIRD_PARTY_DEFAULTS`` constant in
│   │       ``logging_config.py`` (httpx / httpcore / urllib3 /
│   │       sqlalchemy.engine → WARNING; mlflow / dbt / papermill →
│   │       INFO).  ``configure_logging`` accepts a
│   │       ``third_party_levels`` override map; when global
│   │       ``POINTLESSQL_LOG_LEVEL=DEBUG`` is set the defaults are
│   │       bypassed entirely.  Settings expose
│   │       ``LoggingSettings.third_party_levels`` (env var
│   │       ``POINTLESSQL_LOG_THIRD_PARTY_LEVELS``).  4 pytest
│   │       cases.
│   │
│   └── Sprint 44.5 — Enable ruff BLE001 + fix missing-noqa sites
│           Added ``"BLE"`` to ``[tool.ruff.lint] select`` so future
│           broad-except regressions are caught at the linter
│           layer (in addition to the AST lint from 44.2).  Two
│           sites surfaced (``api/home_routes.py``,
│           ``pql/branch/_promote.py``) and got
│           ``# noqa: BLE001 — <reason>`` markers.  Note: the AST
│           lint from 44.2 is the real-quality gate; ruff BLE001 is
│           the cosmetic-consistency gate.
│
├── Phase 43 — Error envelope + exception hierarchy unification ✅ done
│   │
│   │   Code-quality overhaul on the API error path.  Three
│   │   asymmetries closed in one autonomous run: (a) zero
│   │   ``StrEnum`` for error codes → central
│   │   ``pointlessql/error_codes.py`` ``ErrorCode`` enum; (b) three
│   │   orphan exception families (``BranchError``,
│   │   ``RollbackError``, subprocess + integrity loners) inheriting
│   │   from raw ``Exception`` → all reparented under
│   │   ``PointlessSQLError`` with their own
│   │   ``status_code``/``error_code`` class attrs (centralised
│   │   handler now auto-renders); (c) 42 bare-string
│   │   ``raise HTTPException`` sites returning generic ``http_NNN``
│   │   codes → 40 converted to domain exceptions, 2 proxy-upstream
│   │   residuals allowlisted via ``# bare-http-ok`` comment.  Plugin
│   │   ``run`` helper extended to parse RFC 9457 ``code`` +
│   │   extension members so the agent sees structured codes.  No new
│   │   Alembic migrations.
│   │
│   ├── Sprint 43.1 — Central ``ErrorCode`` StrEnum
│   │       New ``pointlessql/error_codes.py`` with 35 enum members
│   │       grouped by domain (catalog, auth, validation, engine,
│   │       audit, branch, rollback, model, subprocess).  Every
│   │       ``PointlessSQLError`` subclass references
│   │       ``error_code: ErrorCode = ErrorCode.X`` instead of raw
│   │       string literals.  ``StrEnum`` subclasses ``str`` so legacy
│   │       ``body["code"] == "validation_error"`` assertions stay
│   │       green.  5 new pytest cases.
│   │
│   ├── Sprint 43.2 — Reparent orphan exception families
│   │       ``BranchError`` (×6), ``RollbackError`` (×4), subprocess
│   │       (``DBT*``, ``MLflowStartupError``), ``AuditIntegrityError``,
│   │       ``BranchTagsCorruptError``, ``SQLParseError`` all reparented
│   │       under ``PointlessSQLError``.  Subprocess errors keep
│   │       ``RuntimeError`` via dual-inheritance (mirror of
│   │       ``ValidationError(PointlessSQLError, ValueError)``
│   │       pattern).  New ``extension_members()`` hook on the base
│   │       class replaces the inline ``isinstance(AuthorizationError)``
│   │       branch in the centralised handler — ``BranchPromotionConflictError``,
│   │       ``RollbackAmbiguous``, ``RollbackStale`` surface their
│   │       structured fields as RFC 9457 extension members
│   │       automatically.  ``_refusal_to_http_error`` translation
│   │       helper deleted from ``runs_routes/rollback.py``.
│   │       ``RollbackStale`` flips 422 → 409 (semantic conflict, not
│   │       request-validation), ``test_stale_returns_422`` renamed.
│   │       28 new pytest cases.
│   │
│   ├── Sprint 43.3 — Eliminate bare-string ``raise HTTPException``
│   │       42 → 2 sites (95% conversion).  Three new domain
│   │       exceptions in ``pointlessql/exceptions.py``:
│   │       ``PermissionDeniedError`` (403, no securable context),
│   │       ``ResourceNotFoundError`` (404, non-catalog miss),
│   │       ``ConflictError`` (409, generic state conflict).  Buckets
│   │       converted: 401 auth (×7) → ``AuthenticationError``;
│   │       403 admin (×2) → ``PermissionDeniedError``; 400 missing-
│   │       param (×6) → ``ValidationError``; 404 missing-resource
│   │       (×11) → ``ResourceNotFoundError`` /
│   │       ``CatalogNotFoundError``; 503 dbt-execution (×3) →
│   │       redundant after Sprint 43.2 reparenting, ``except`` blocks
│   │       deleted; misc 5xx → ``EngineError``.  2 proxy-upstream
│   │       502 sites stay as bare ``HTTPException`` with
│   │       ``# bare-http-ok:`` comment (no domain home for
│   │       proxy-failed-to-reach-subprocess).  New
│   │       ``tests/test_no_bare_http_exception.py`` lint test
│   │       enforces the allowlist.  4 pre-existing tests updated for
│   │       400 → 422 status flip on input-validation.
│   │
│   ├── Sprint 43.4 — ``ErrorEnvelope`` Pydantic + selective OpenAPI
│   │       New ``pointlessql/api/error_envelope.py`` with
│   │       ``ErrorEnvelope`` base + four refinements
│   │       (``AuthorizationErrorEnvelope``,
│   │       ``ValidationErrorEnvelope``, ``RollbackStaleEnvelope``,
│   │       ``BranchPromotionConflictEnvelope``).  ``error_responses.py``
│   │       exports ``STANDARD_ERROR_RESPONSES`` for declaration via
│   │       ``@router.get(..., responses=STANDARD_ERROR_RESPONSES)``.
│   │       Applied selectively to 13 plugin-facing routes (audit ×6,
│   │       lineage ×3, pql-write ×4) so the OpenAPI schema exposes
│   │       the envelope contract.  4 new pytest cases assert the
│   │       schema contract.
│   │
│   └── Sprint 43.5 — Plugin envelope-aware error rendering
│           ``hermes-plugin-pointlessql`` ``run()`` helper extended:
│           on ``httpx.HTTPStatusError`` with
│           ``Content-Type: application/problem+json``, parses ``code``
│           and 11 extension members
│           (``required_privilege``, ``securable_type``, ``full_name``,
│           ``table_name``, ``expected_version``, ``actual_version``,
│           ``candidate_ordinals``, ``current_version``,
│           ``intervening_op_count``, ``errors``) into the agent-
│           visible envelope.  Falls back to legacy text-only shape
│           for plain text responses.  5 new pytest cases plugin-side
│           pin the contract.
│
├── Phase 42 — Anomaly-Inbox System-Errors band           ✅ done
│   │
│   │   Phase-40.6's second deferred surface: foreign-Delta CDF
│   │   subscriptions whose last tail tick stamped ``last_error``
│   │   surfaced on the audit-reviewer's inbox.  Operator question
│   │   "are any of my CDF subscriptions currently broken?" is now
│   │   answered without leaving ``/audit/inbox``.  Anti-goal: no
│   │   sigma-anomaly framework intrusion — CDF errors are point-
│   │   in-time state and render server-side as a separate band
│   │   above the time-bin sigma cards.  Single sprint, no new
│   │   Alembic migration, no new credential surface, no mutation
│   │   endpoint (auditor sees, admin clears).
│   │
│   └── Sprint 42.1 — System-errors band on ``/audit/inbox``
│           New ``_load_system_errors`` helper in
│           ``pointlessql/api/audit_inbox_routes.py`` —
│           workspace-scoped query on
│           ``cdf_tail_subscriptions WHERE last_error IS NOT NULL``,
│           ordered ``last_tailed_at DESC NULLS LAST`` so freshest
│           failures bubble.  Threaded into the page-render context
│           as ``system_errors``.  Template
│           ``frontend/templates/pages/audit_inbox.html`` extended
│           with a new ``<section data-inbox-section="system-errors">``
│           above the existing filter form / anomaly table; section
│           is conditional on ``{% if system_errors %}`` so a clean
│           workspace renders zero noise.  Each row carries a
│           paused-badge (when ``is_active=False``), the truncated
│           error message, ``last_tailed_at``, and an "Open admin"
│           cross-link to ``/admin/cdf-subscriptions`` (admin-scope
│           handles retry/clear).  4 pytest cases (renders, hides,
│           workspace-isolation, paused-marker).  Walkthrough-deep
│           extended with a new Part E (3 steps).
│
├── Phase 40.7 — Row-Trace fold-in of CDF events           ✅ done
│   │
│   │   Phase-40.6's deferred surface: foreign-Delta CDF events
│   │   captured by the Phase-40.5 tail folded back into the
│   │   existing row-trace walkback as contextual metadata.  No
│   │   new walkback semantics — events attach per step on
│   │   ``(table, row_id)`` mirror of Phase-15.7's value-changes
│   │   pattern.  Walkback semantics (predecessors out of
│   │   ``lineage_row_edges``) stay unchanged; CDF captures are
│   │   pure context, never new walkback steps.  Single sprint,
│   │   no new Alembic migration, no new credential surface, no
│   │   new plugin tool — existing ``pql_row_trace`` ships the
│   │   new ``cdf_events`` per-step field transparently.
│   │
│   └── Sprint 40.7.1 — Per-step ``cdf_events`` attach
│           New ``fetch_events_for_row`` service helper in
│           ``pointlessql/services/cdf_tail.py`` (workspace-scoped
│           indexed lookup on ``(workspace_id, table_full_name,
│           row_id)``).  New ``_attach_cdf_events`` route-level
│           helper in ``pointlessql/api/lineage_routes.py``
│           parallel to ``_attach_value_changes``; threaded into
│           both row-trace handlers (JSON + HTML).
│           ``_step_to_dict`` extended with always-present
│           ``cdf_events: []``.  New ``<details>`` block on
│           ``frontend/templates/pages/row_trace.html`` mirroring
│           the Value-changes pattern.  Change-type pill
│           extracted into reusable
│           ``frontend/templates/partials/_cdf_change_type_pill.html``;
│           ``table.html`` 7th-tab CDF-events table now includes
│           the partial verbatim.  3 pytest cases (attach,
│           empty-list-default, workspace-isolation).
│
├── Phase 45 — Pyright Hot-Spot Cleanup ✅ done
│   │
│   │   Code-quality cleanup at JSON / soyuz / DuckDB-plan
│   │   deserialisation seams.  Pyright budget 559 → 497 (62
│   │   warnings closed, 11.1% reduction).  Five file-scoped
│   │   sprints in one autonomous run; no production-code
│   │   refactor — pure type-narrowing.  No runtime semantics
│   │   change.  Skipped the three biggest stub-gap files
│   │   (``pql/_merge.py`` 120, ``pql/_autoload.py`` 46,
│   │   ``services/lineage/inbound_parser.py`` 31) per memory
│   │   ``feedback_pyright_thirdparty_stubs.md`` — those need
│   │   custom ``.pyi`` stubs for PyArrow / deltalake /
│   │   OpenLineage and are a Phase-47 candidate at earliest.
│   │
│   ├── Sprint 45.1 — Narrow ``audit_sinks_routes.py`` (12 → 0)
│   │       Two helpers (``_loads_obj`` / ``_loads_list``) absorb
│   │       every ``json.loads(...) -> Any`` boundary; ``cast()``
│   │       narrows the in-place ``decoded = value`` and
│   │       ``body["config"]`` arms that pyright cannot infer
│   │       from ``isinstance`` alone.
│   │
│   ├── Sprint 45.2 — ``cost_estimator.py`` narrowing + parens
│   │       (14 → 0)  Two ``except TypeError, ValueError:`` (PEP
│   │       758 lenient form, valid in Python 3.14) → ``except
│   │       (TypeError, ValueError):``.  Semantic no-op — both
│   │       types are caught either way — but the parenthesised
│   │       form does not bind ``ValueError`` to a name that
│   │       shadows the built-in inside the except block.
│   │       Plus ``cast(dict[str, Any], …)`` after isinstance
│   │       checks so subsequent ``node.get(...)`` calls don't
│   │       cascade Unknown.
│   │
│   ├── Sprint 45.3 — Narrow ``governance_routes.py`` (10 → 0)
│   │       UC ``columns`` payload from ``enforce_table_profile_access``
│   │       gets ``cast(list[dict[str, Any]], …)``;
│   │       ``cast(dict[str, Any], …)`` after the
│   │       ``isinstance(options_raw, dict)`` check on UC
│   │       connection options.
│   │
│   ├── Sprint 45.4 — Narrow ``volumes_routes.py`` (13 → 3)
│   │       Three remaining warnings are PyArrow / deltalake
│   │       stub-gap, anti-goal compliant.  Annotates ``columns:
│   │       list[dict[str, Any]] = []`` so the converted-to-Delta
│   │       payload keeps a known shape downstream; isolates
│   │       ``data = resp.json()`` narrowing to a single
│   │       ``isinstance(data, dict)`` branch with a
│   │       ``cast(list[dict[str, Any]], …)`` on the volumes
│   │       fan-out.
│   │
│   ├── Sprint 45.5 — Narrow ``home_routes.py`` (16 → 0)
│   │       ``cast(datetime, started_at)`` on the ``JobRunModel``
│   │       row tuple unpack so the Spark-history bucket index is
│   │       ``int``, not ``Any``.  ``cast(list[dict[str, Any]],
│   │       cat.get("schemas") or [])`` on the UC ``get_tree()``
│   │       cascade (schemas → tables) so per-node ``score_match``
│   │       / ``.get`` calls keep their narrow types.  Same
│   │       pattern on the notebook-tree ``_walk`` recursion.
│   │
│   └── Sprint 45.6 — Pyright budget 559 → 497
│           ``scripts/check-pyright-budget.sh`` ``BUDGET=`` lowered
│           to 497 with a 5-line comment block documenting the
│           Phase-45 reduction and the policy that the remaining
│           ~497 are rooted in third-party stubs Python annotations
│           cannot fix.
│
├── Phase 46 — Test-Auth-Fixture Centralization ✅ done
│   │
│   │   Replaces ~48 local ``_admin_client()`` /
│   │   ``_non_admin_client()`` / ``_bearer_client()`` /
│   │   ``_client(**kwargs)`` helpers and ~7 local
│   │   ``Iterator[str]``-shaped API-key fixtures across 55 test
│   │   files with six conftest fixtures.  Two-sprint refactor in
│   │   one autonomous run.  Net delta -2027 / +1721 LOC.  1667
│   │   tests pass (1661 baseline + 6 sanity tests).  No
│   │   production-app changes.
│   │
│   ├── Sprint 46.1 — Add admin_client / non_admin_client /
│   │       anonymous_client + ApiKeyFixture fixtures.  Six new
│   │       pytest fixtures in ``tests/conftest.py``:
│   │       ``admin_client``, ``non_admin_client``,
│   │       ``anonymous_client`` yielding pre-configured
│   │       ``httpx.AsyncClient`` instances; ``supervisor_secret``,
│   │       ``auditor_secret``, ``api_key_secret`` yielding the
│   │       new ``ApiKeyFixture(secret, row, headers)`` NamedTuple.
│   │       Purely additive — old local helpers stay valid.  New
│   │       ``tests/test_auth_fixtures.py`` (6 cases) pins the
│   │       fixture contract.
│   │
│   └── Sprint 46.2 — Migrate test files in six route-family
│           batches.  Admin (2), audit (6), branch/rollback/
│           promotion (3), models/ML (4), supervisor/scheduler
│           (4), catch-all (36).  Four files deliberately kept
│           local helpers per the plan's "different test
│           pattern" carve-out: ``test_csrf.py`` (raw JWT
│           injection), ``test_lineage_inbound_routes.py``
│           (custom ``federation_secret`` Bearer scope),
│           ``test_api_key_gate.py`` (interleaved inline
│           AsyncClient blocks reusing one ``transport``
│           variable), ``test_training_log_route.py`` (per-call
│           ``X-Agent-Run-Id`` header injection).
│
├── Phase 47 — NewType ID Hardening ✅ done
│   │
│   │   Wraps the project's primary identifier strings in
│   │   distinct ``typing.NewType`` aliases so pyright catches
│   │   mixups (passing a ``RunId`` where a ``WorkspaceId`` was
│   │   expected) even though every alias erases to ``str`` or
│   │   ``int`` at runtime.  No DB migration, no wire-format
│   │   change, no production behaviour change — purely a
│   │   compile-time contract aid at the function-signature /
│   │   service / route boundary.  Models stay on plain
│   │   ``Mapped[str]`` / ``Mapped[int]`` per anti-goal (ORM
│   │   integration with NewType is unspec'd).  Pyright budget
│   │   unchanged at 497.  1673 tests pass (1667 baseline + 6
│   │   new identifier sanity tests).
│   │
│   ├── Sprint 47.1 — Add ``pointlessql/identifiers.py`` with
│   │       ``RunId`` / ``OpId`` / ``QueryHistoryId`` /
│   │       ``WorkspaceId`` aliases and a 6-case
│   │       ``tests/test_identifiers.py`` pinning the runtime
│   │       erasure contract.  Greenfield: zero existing
│   │       NewType / Annotated usage in the codebase before
│   │       this phase.
│   │
│   └── Sprint 47.2 — Wire the aliases through the
│           public-API entry points: ``services/query_history.py``
│           (``record_query`` takes ``RunId | None``, returns
│           ``QueryHistoryId``; ``get_by_id`` takes
│           ``QueryHistoryId``; ``_sanitise_run_id`` returns
│           ``RunId | None``); ``services/agent_runs/operations.py``
│           (``record_operation`` takes ``RunId``, returns
│           ``OpId``; ``operation_context`` takes ``RunId | None``);
│           ``services/read_audit.py`` (``_resolve_run_id``
│           returns ``RunId | None``).  Wraps land at the FastAPI
│           Path/Query boundary and via
│           ``cast(RunId | None, ...)`` at the
│           ``operation_context`` cascade across 10 PQL
│           primitives.
│
├── Phase 63 — Writeable SQL Editor (AST-dispatch refactor)  ✅ done 2026-05-10
│   │
│   │   The SQL editor was SELECT-only at
│   │   ``pointlessql/pql/sql_parser.py:385-391`` because the
│   │   DuckDB rewriter only made sense for SELECTs (DuckDB
│   │   reserves ``main`` as a catalog name and refuses to bind
│   │   3-part UC refs natively, so the parser has to extract
│   │   + rewrite source tables).  The audit infrastructure
│   │   (Phase 13 ``agent_run_operations``, Phase 14 external-
│   │   write detection, Phase 15.x lineage tables) was
│   │   already ready for write traffic — the only structural
│   │   gap was that interactive editor writes did not populate
│   │   ``query_history.agent_run_id``.  Phase 63 turns the
│   │   editor backend into an AST-classifying dispatcher that
│   │   routes each statement family to its correct typed
│   │   primitive, so editor writes land in the same audit
│   │   trail as Hermes-driven writes.
│   │
│   ├── Sprint 63.1 — Statement-type taxonomy + parser ✅
│   │       ``StmtType`` StrEnum, ``classify(ast)``,
│   │       ``extract_write_target`` / ``extract_source_refs``,
│   │       ``parse_and_classify``, ``parse_batch``.
│   │       ``_parse_root`` no longer rejects non-SELECT;
│   │       ``prepare_sql`` keeps SELECT-only via explicit
│   │       guard.  CREATE/DROP CATALOG parse as ``exp.Command``
│   │       in sqlglot — deliberately rejected (admin UI).
│   │       Bare ``CREATE TABLE`` rejected (use New Table form).
│   │       42 new pytest cases.
│   │
│   ├── Sprint 63.2 — pql.update + pql.delete primitives ✅
│   │       New ``pointlessql/pql/_update_delete.py`` wraps
│   │       ``DeltaTable.update`` / ``.delete`` (delta-rs
│   │       accepts SQL-string predicates).
│   │       ``pql.update(track_value_changes=True)`` reuses
│   │       merge's CDF capture.  HTTP routes
│   │       ``POST /api/pql/{update,delete}``.  Alembic
│   │       ``ee3f6h8j0l2n`` extends the
│   │       ``ck_agent_run_operations_op_name`` CHECK with all
│   │       six new op names (update/delete/drop_table/
│   │       create_schema/drop_schema/alter_table) in one shot.
│   │       ORM CHECK widened in lockstep.  13 new pytest
│   │       cases.
│   │
│   ├── Sprint 63.3 — Soyuz update_table facade  🧊 deferred
│   │       Cross-repo soyuz tag bump + client regen out of
│   │       Phase-63 scope.  Editor's table-detail UI (Phase
│   │       17.4) already handles ALTER TABLE COMMENT /
│   │       properties.  Dispatcher's ``ALTER_TABLE`` branch
│   │       returns a structured "use the table-detail UI"
│   │       error so the parser path stays live for a future
│   │       Phase 63.5 to wire in.
│   │
│   ├── Sprint 63.4 — Backend dispatcher ✅
│   │       New ``pointlessql/api/sql_dispatcher.py`` with one
│   │       ``dispatch(stype, ast, …)`` entry point + per-
│   │       StmtType branches.  SELECT keeps today's path (no
│   │       agent_run created).  Write branches start a one-shot
│   │       ``agent_run`` with ``agent_id='sql-editor'`` BEFORE
│   │       the primitive call; PQL primitives' operation_context
│   │       emits ``agent_run_operations`` against that run id
│   │       automatically.  DDL branches emit op rows directly
│   │       via SQL (soyuz client has no operation_context).
│   │       Per-branch privilege checks reuse ``check_privilege``.
│   │       ``api_sql_execute`` shrinks from 240 LOC to ~140.
│   │       10 new pytest cases.
│   │
│   ├── Sprint 63.5 — MERGE AST → MergeCallSpec translator ✅
│   │       New ``pointlessql/pql/sql_merge_translator.py``.
│   │       Supports the ``WHEN MATCHED THEN UPDATE`` (+
│   │       optional ``WHEN NOT MATCHED THEN INSERT``) upsert
│   │       subset of ``pql.merge``.  Conditional WHEN clauses,
│   │       ``WHEN MATCHED THEN DELETE``, ``WHEN NOT MATCHED BY
│   │       SOURCE``, multiple WHEN MATCHED branches, and
│   │       complex non-EQ ON predicates are all rejected with
│   │       structured ``SQLMergeUnsupportedError`` pointing the
│   │       user at ``POST /api/pql/merge`` for elaborate cases.
│   │       9 new pytest cases.
│   │
│   ├── Sprint 63.6 — Multi-statement / batch route ✅
│   │       ``POST /api/sql/execute_batch`` runs ``;``-separated
│   │       statements through the same dispatcher.
│   │       ``atomic=True`` opens a single batch agent_run and
│   │       calls ``pql.rollback`` (Phase 16) on the prior
│   │       write ops on failure.  ``atomic=False`` (default)
│   │       gives each write its own run.  Frontend toggle
│   │       deferred to a polish Sprint 63.6.1; the server-side
│   │       route is callable today.
│   │
│   ├── Sprint 63.7 — Editor UX ✅
│   │       Statement-type badge above the result widget
│   │       (colour-coded per stmt_type).  Destructive-statement
│   │       confirmation modal (regex heuristic for
│   │       DROP TABLE/SCHEMA + DELETE without WHERE).  New
│   │       ``dml`` / ``ddl`` result-render branch with
│   │       rows-affected + ``View op trace`` deep-link to
│   │       ``/runs/<run_id>``.  Existing SELECT rows-table
│   │       branch unchanged.
│   │
│   ├── Sprint 63.8 — Audit-FK wiring ✅
│   │       ``record_query_async`` accepts ``agent_run_id`` +
│   │       ``read_kind`` kwargs; dispatcher passes both so
│   │       editor writes land in ``query_history`` with
│   │       ``read_kind='sql_dml'`` / ``'sql_ddl'``.
│   │       ``ReadKind`` extended.  ``/runs/<id>`` already
│   │       joins ``query_history`` by ``agent_run_id`` (Phase
│   │       13.10) so editor writes show up in the run's
│   │       queries panel without further work.
│   │
│   └── Sprint 63.9 — Tests + close ✅
│           31 new pytest cases overall; full suite run shows
│           147 passes across the touched paths.  ruff /
│           pyright / pydoclint clean on every new or modified
│           file.  CHANGELOG, ROADMAP, memory updated.
│
├── Phase 59 — Comprehensive UX-tour quality sweep         ✅ done 2026-05-08
│   │
│   │   Post-Phase-58 headed-Playwright tour through 8 thematic
│   │   surface groups produced 65 desktop screenshots and 71
│   │   findings (23 CONTENT / 37 STRUCTURAL / 11 DESIGN), plus
│   │   8 cross-cutting patterns.  Findings doc lives at
│   │   ``docs/internal/phase59_audit_findings.md``; screenshots
│   │   at ``docs/internal/phase59_screenshots/``.  Zero browser-
│   │   console errors and zero 5xx during the tour — UI is
│   │   runtime-clean, all findings are quality-issues not bugs.
│   │
│   │   Phase 59 covers the 60 implementable findings (CONTENT +
│   │   STRUCTURAL); the 11 DESIGN findings defer to Phase 60+.
│   │
│   ├── Sprint 59.1 — Jargon sweep + logic bugs + ANSI strip ✅ c0d93ae
│   │       CONTENT-only sweep + 1 service fix.  "Read kind" →
│   │       "Source", "Status" → "Outcome", "Window" → "Time
│   │       range" on /queries; "tables_touched" / "written" /
│   │       "read" → "Touched" / "Wrote" / "Read" on
│   │       /audit/by-table; drop "Phase 29.3" jargon from
│   │       /admin/system-info; fix "Pull-modell" / "push-modell"
│   │       German typo in admin_index.html; ANSI-strip on
│   │       caught DuckDB exception messages in
│   │       sql_routes.py; hide SHA-256 sentinel on Source-card
│   │       when source bytes ARE captured but SHA is the all-
│   │       zeros hash; filter depth-0 self-nodes from lineage_card
│   │       upstream + downstream so zero-edge tables don't render
│   │       the page subject twice.  Branches default-filter
│   │       finding investigated and dropped (no actual default-
│   │       active chip in code).
│   │
│   ├── Sprint 59.2 — Bootstrap-tab URL-state global helper ✅ 2fc3e36
│   │       New ``frontend/js/tab_sync.js`` self-bootstraps on
│   │       DOMContentLoaded, reads ``?tab=`` and ``?subtab=`` and
│   │       activates the matching ``[data-bs-toggle="tab"]
│   │       [data-pql-tab-key]`` via
│   │       bootstrap.Tab.getOrCreateInstance.  Global delegated
│   │       ``shown.bs.tab`` listener mirrors back via
│   │       history.replaceState.  Eleven templates (table,
│   │       run_view, model, data_product, agent_run_compare,
│   │       dbt, audit_by_table + 4 _run_tab_* sub-pane partials)
│   │       gained ``data-pql-tab-key="<key>"`` attributes.
│   │       Legacy ``#tab-…`` hash IIFE on run_view kept for
│   │       backward-compat.
│   │
│   ├── Sprint 59.3 — Auth/error chromeless layout            ✅ 4be934f
│   │       New ``_layouts/auth_chromeless.html`` — distilled
│   │       layout with logo + content-block + footer; no
│   │       icon-rail, no top-bar Search, no Admin-dropdown.
│   │       Migrated login, register, 403, 404, 500; new
│   │       ``pages/429.html``; wired ``_render_429`` in
│   │       rate_limit_middleware to render the new template via
│   │       ``request.app.state.templates.env`` with bare-HTML
│   │       fallback for early-init.  User-confirmed during
│   │       Phase-58 replay (memory:
│   │       ``feedback_auth_pages_chromeless.md``).
│   │
│   ├── Sprint 59.4 — Filter-row collapsible macro              ✅ 5a68258
│   │       New ``_macros/filter_collapsible.html`` (pure
│   │       Bootstrap, no Alpine).  Wraps a dense filter row in a
│   │       ``.collapse`` block behind a summary pill.  Applied
│   │       default-collapsed to /audit/inbox (6 fields) and
│   │       default-expanded to /queries (3 fields).  /audit/search
│   │       and /runs intentionally skipped — search form IS the
│   │       primary action on /audit/search; /runs uses Alpine
│   │       chips, not a dense form.
│   │
│   ├── Sprint 59.5 — Icon-rail re-mapping                       ✅ 70981b1
│   │       Two new top-level rail items: ``AUDIT`` (bi-shield-
│   │       check) and ``REVIEWS`` (bi-clipboard-check), both
│   │       between ALERTS and PRODUCTS, both visible to all
│   │       auth'd users.  Renamed FEDERATION → CATALOG with
│   │       bi-database icon and href "/" (the actual catalog
│   │       browser landing); section key stays ``federation``
│   │       internally to avoid breaking ~10 references.  Admin
│   │       footer icon swapped bi-shield-check → bi-tools to
│   │       free the icon for AUDIT.  context_panel.html grew
│   │       inline AUDIT (Inbox / Search / By table / By query)
│   │       and REVIEWS (All reviews + cross-link to Admin →
│   │       Review destinations) branches.  Removed the
│   │       duplicative "Audit cockpit" link from the admin
│   │       sidebar.  agent_reviews_routes switched
│   │       active_page from "audit" → "agent_reviews" so it
│   │       highlights REVIEWS, not AUDIT.
│   │
│   ├── Sprint 59.6 — Sub-pane helper-text sweep                 ✅ a7cf5b6
│   │       Replicated the /jobs dual-mode helper across
│   │       /dashboards (added "+ New dashboard" UI path +
│   │       agent ``create_dashboard`` tool) and /alerts
│   │       (existing UI path got a ``create_alert`` agent
│   │       tool reference).  /connections, /volumes, /dbt
│   │       skipped — they share the catalog tree (P-3 root
│   │       cause) and don't render a per-page sidebar helper.
│   │
│   ├── Sprint 59.7 — Empty-state quality sweep                  ✅ d1d90db
│   │       Rewrote below-bar empty-states on /volumes (3-step
│   │       Docker / Python / Hermes), /models (3-step MLflow /
│   │       Hermes / Docs), /branches (dual-mode pql.branch() +
│   │       agent create_branch).  Each empty-state now contains
│   │       a UI path AND an agent path AND (where applicable) a
│   │       docs link.  Replaces references to "soyuz UC-OSS",
│   │       "Hermes plugin", and "UC CLI" jargon-tokens with
│   │       concrete copy-pasteable commands.
│   │
│   ├── Phase 60+ DESIGN-deferred (sketch only)                  🧊
│   │       11 DESIGN findings parked: cytoscape-DAG on table-
│   │       lineage tab (Phase 17.3 reuse), Audit unified
│   │       ``/audit`` page with tab-strip (consolidate 4
│   │       separate sub-pages), Run-Overview sub-tabs flatten
│   │       to sectioned cards, ``/auth/me`` rendered profile
│   │       page (currently raw JSON), ``/admin`` Card-hierarchy
│   │       (action-required-first ordering).  Each is a multi-
│   │       day surface change — bundle as Phase 60 mini-
│   │       redesign trio (analog Phase 58) when scope crystallises.
│   │
│   └── Sprint 59.9 — Phase close                                ✅ this commit
│           ROADMAP.md flipped ⏳ → ✅ with commit hashes,
│           CHANGELOG entry, memory file
│           ``project_phase59_closed.md``, MEMORY.md index
│           updated.  Phase 59 totaled 8 commits including the
│           audit opener + close.  Branch not yet pushed.
│
├── Phase 58 — Phase-57 carve-out trio                       ✅ done 2026-05-08
│   │
│   │   Three small deferred items from Sprint 57.8 land in one
│   │   autonomous pass post the user-prompt "mache die sofort
│   │   follo up und pahse 58 noch ferig".  Single commit.
│   │
│   │   58.1 — admin_workspaces "Create" form → Bootstrap modal.
│   │   Replaces the inline card-form at the top of the workspace
│   │   list with a "+ New workspace" button + modal, matching
│   │   the jobs / dashboards / alerts UX.  Alpine state + POST
│   │   flow unchanged; only the surface moves.  Closes the one
│   │   DESIGN finding from the Phase 57.1 audit.
│   │
│   │   58.2 — admin_audit_sinks empty-state icon swap
│   │   (``bi-broadcast`` → ``bi-broadcast-pin``).  Cosmetic
│   │   refinement noted as the only CONTENT finding in the 57.1
│   │   audit.
│   │
│   │   58.3 — Query-card "View full SQL" drawer trigger.  SQL
│   │   longer than 700 characters surfaces a Phase-56.8
│   │   detail_drawer button that pops the full text out of the
│   │   card's height-capped ``<pre>`` into an Offcanvas panel.
│   │   Short SQL renders without the trigger so the card stays
│   │   clean.  Pre-emptive add — the alternative was to wait for
│   │   user-replay to demand it, but height-capped scrolling on a
│   │   200-line stored procedure is poor enough that proactive
│   │   ship is the better trade.  2 new pytest cases.
│   │
│   │   Drops (deliberately not picked up):
│   │   - Alpine listTable re-add on queries card-grid — no user
│   │     signal that server-side Form-GET reload is too slow.
│   │     Stays parked until replay calls for it.
│   │   - Browser-replay verification — same handling as 54-57.
│   │
│   │   Push gate: standard manual.
│   │
├── Phase 57 — Phase-56 carve-outs + route-test coverage      ✅ done 2026-05-08
│   │
│   │   Closes the three explicit carve-outs from Phase 56 in
│   │   one autonomous session post the user-prompt "plane aus!"
│   │   on (1) queries.html Tables→Cards, (2) DESIGN-tagged
│   │   findings from the 56.1 audit, (3) test-coverage sweep on
│   │   admin_api_keys / federation / jobs / dashboards.  Nine
│   │   sub-sprints; ~85 new pytest cases; one mobile-data-label
│   │   sweep on 7 surfaces.
│   │
│   │   The plan-phase audit again reduced the implementation
│   │   set:  the "DESIGN-tagged findings" carve-out turned out
│   │   to be effectively empty (Section 4 of
│   │   ``phase56_audit_findings.md`` declares ``[DESIGN]`` as a
│   │   tag-category but no individual finding actually carries
│   │   the tag — they were all CONTENT/STRUCTURAL and folded
│   │   into Sprint 56.10).  Sprint 57.1 was repurposed as an
│   │   audit-Ersatz on the ~15 surfaces that the 56.1 audit had
│   │   never covered (admin/* detail views, federation/* detail
│   │   views, jobs+dashboards detail views, branches detail,
│   │   volumes), producing ten STRUCTURAL findings (mobile
│   │   data-label adoption) + one CONTENT finding + one DESIGN
│   │   finding (admin_workspaces "Create" form → modal,
│   │   deferred to Phase 58).  Saved one Sprint-token worth of
│   │   speculative DESIGN work.
│   │
│   │   Sprint 57.1 — Audit-Ersatz: per-surface semantic-content
│   │   review of the ~18 surfaces that the 56.1 audit had not
│   │   covered.  Output ``docs/internal/phase57_audit_findings.md``.
│   │   Read-only.
│   │
│   │   Sprint 57.2 — Server-side offset pagination on
│   │   ``/queries`` (analog Phase 55.1 ``/runs``).  Extends
│   │   ``query_history.list_queries`` with an ``offset`` kwarg
│   │   (backward-compatible default 0); ``count_queries`` grows
│   │   the same filter-arg list ``list_queries`` already takes
│   │   so the pager can compute filter-aware ``remaining``.
│   │   GET /queries dispatches HX-Request → fragment template
│   │   for the Load-More flow.  5 new pytest cases.
│   │
│   │   Sprint 57.3 — ``/queries`` table → card-grid + hljs SQL
│   │   syntax-highlighting.  Replaces the Alpine listTable +
│   │   9-column table with a Bootstrap card-grid (col-12 /
│   │   col-md-6 / col-xxl-4) where each card carries a status
│   │   stripe on the left edge (succeeded / failed / cancelled)
│   │   and the SQL rendered in a height-capped ``<pre>`` block
│   │   coloured by highlight.js.  Filters move from client-side
│   │   chips (mine / failed / last24h) to server-side Form-GET
│   │   selects (read_kind / status / since), same trade-off as
│   │   56.9 on agent_reviews + alerts.  hljs loaded via
│   │   jsdelivr CDN to match the project's existing Bootstrap /
│   │   htmx / alpine / chart.js precedent — no vendor/
│   │   directory.  HTMX after-swap re-highlight.  2 new pytest
│   │   cases.
│   │
│   │   Sprint 57.4 — ``federation_routes.py`` route-level
│   │   smoke-tests (21 endpoints, ~14% → ~80% coverage).  26
│   │   new pytest cases covering 5 connections × 3 resource
│   │   families (15 JSON CRUD) + 6 HTML pages, each with
│   │   admin-success + non-admin-403 + audit-emission asserts +
│   │   one outage-banner case for the connections index.
│   │
│   │   Sprint 57.5 — ``dashboards_routes.py`` smoke-tests (9
│   │   endpoints, ~22% → ~80%).  16 new pytest cases.  Caught
│   │   one spec-mismatch at sprint-start: the create-dashboard
│   │   route maps slug-validation rejections to 422 (not 400)
│   │   because ``ValidationError`` inherits
│   │   ``PointlessSQLError.status_code = 422``.
│   │
│   │   Sprint 57.6 — ``jobs_routes.py`` smoke-tests (13
│   │   endpoints, ~53% → ~80%).  14 new pytest cases targeting
│   │   the 5 endpoints not covered by ``TestJobRoutes`` in
│   │   ``test_scheduler.py`` (DAG tasks list, run-tasks,
│   │   run-logs + task-filter, notebook + download 404 paths,
│   │   compare ``?to=`` papermill-only).
│   │
│   │   Sprint 57.7 — ``admin_api_keys_routes.py`` edge-case
│   │   extension (3 endpoints, ~66% → ~95%).  8 new pytest
│   │   cases on top of the 5 existing happy-path tests:
│   │   create rejects empty / missing / whitespace name (422),
│   │   workspace_id <= 0 (422), duplicate active name (422);
│   │   revoke twice → 404 second time; list ?include_revoked
│   │   surfaces inactive; supervisor + auditor combo; non-admin
│   │   revoke → 403 (require_admin runs first).
│   │
│   │   Sprint 57.8 — Apply CONTENT + STRUCTURAL findings from
│   │   57.1.  Adds ``pql-list-table`` class + ``data-label``
│   │   attributes to 7 surfaces that rendered badly on <640px
│   │   without per-column labels: admin_audit_sinks,
│   │   admin_review_destinations, admin_workspaces (dual
│   │   tables), volumes, volume_detail (Alpine x-for table),
│   │   job_detail (DAG tasks + recent runs), branch_detail
│   │   (audit log).  Same mechanic as Phase 56.4.
│   │
│   │   Sprint 57.9 — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry.
│   │
│   │   Drops (recorded for the implementation log):
│   │   - DESIGN-finding admin_workspaces "Create" → modal.
│   │     Defer Phase 58 — focused mini-redesign.
│   │   - admin_audit_sinks empty-state icon swap (CONTENT,
│   │     cosmetic only).  Defer Phase 58.
│   │   - branches_routes test-coverage extension — already at
│   │     ~85%, diminishing returns.
│   │   - audit_search_routes test-coverage — already 100%.
│   │   - hljs vendoring per the original plan-pick — project
│   │     pattern is CDN for everything (Bootstrap, htmx, alpine,
│   │     chart.js, codemirror) and a single vendored dep would
│   │     be inconsistent.  Sticking to CDN.
│   │   - Alpine listTable on the new card-container for
│   │     ``/queries``.  Server-side filter via Form-GET-Reload
│   │     is sufficient (analog 56.9); user-replay-driven re-add
│   │     Phase 58 if demanded.
│   │   - SQL truncate-with-drawer in queries-card.  Initial
│   │     commit without truncate; observe in user replay.
│   │
│   │   Browser-replay verification:  Wave-3 (57.3 cards + hljs +
│   │   Load-More) needs browser-side verification of hljs-render,
│   │   Load-More click + scroll-trigger, mobile card-stack —
│   │   left for user post-rebuild.  Wave-1 audit + Wave-2 backend
│   │   pagination + Wave-3 test-coverage sweeps + Wave-4 mobile-
│   │   sweep all gate on pytest only (124 tests green across the
│   │   touched test files).
│   │
│   │   Push gate: standard manual.
│   │
├── Phase 56 — UX-polish + bug-hunt + semantic-content review ✅ done 2026-05-08
│   │
│   │   Three-wave audit-first sweep post the user-prompt
│   │   "wir machen bug-hunting + auch hunting von schlechter
│   │   visualisierung … und auch die semantisch richtigen
│   │   Inhalte".  12 sub-sprints in one autonomous session
│   │   (audit-only Wave 1 + 4 mechanical sweeps in Wave 2 + 4
│   │   new-primitive Wave 3 + 3-item Wave 4 polish + close).
│   │
│   │   The plan-phase audit (3 parallel Explore agents +
│   │   verify-pass) collapsed the implementation set
│   │   substantially:  9 of 9 BUG-53-NN markers turned out to
│   │   be already-fixed-but-not-closed (closed in 56.2 with
│   │   per-marker evidence trail in
│   │   ``screenshots/phase53-replay/_notes.md``); the worried-
│   │   about Alpine x-data quoting on 10 templates turned out
│   │   to be already-safe via Jinja's default ``|tojson``
│   │   ``\\uXXXX``-escape behaviour (regression test in
│   │   ``tests/test_alpine_x_data_quoting.py`` pins it); and
│   │   four of the Phase-53 visual-debt patterns (#1 outline-
│   │   button-opacity, #2 errors-no-sidebar, #6 UUID format,
│   │   #8 tab-badges only first sub-tab) were already-fixed-but-
│   │   not-closed by Phases 54.1 / 56.5 / earlier.
│   │
│   │   Sprint 56.1 — Audit consolidation + per-page semantic
│   │   review.  Read-only.  Output:
│   │   ``docs/internal/phase56_audit_findings.md`` with six
│   │   sections (layout-pattern inventory, BUG-status, per-
│   │   page semantic review for 20 surfaces, affected-file
│   │   list per sub-sprint, risk-notes, out-of-scope).  No code
│   │   changes — every finding is acted on (or deferred) in
│   │   later sub-sprints with explicit cross-references.
│   │
│   │   Sprint 56.2 — BUG-53-NN closure + Alpine x-data quoting
│   │   regression test.  Closes all 9 BUG-53-NN markers in one
│   │   sweep of ``_notes.md``.  ``tests/test_alpine_x_data_
│   │   quoting.py`` (12 tests) pins the safe behaviour against
│   │   future regressions.  Net 0 template code-changes.
│   │
│   │   Sprint 56.3 — Empty-state component sweep.  8 templates
│   │   converted from inline ``<p>``/``<div>`` empty-states to
│   │   ``{% include "components/empty.html" %}`` with action-
│   │   oriented messages (e.g. "Add a webhook URL or pull-feed
│   │   receiver below" instead of "No destinations yet").
│   │   Templates: ``alert_detail`` (×2), ``queries``, ``models``,
│   │   ``job_detail``, ``agent_run_compare``, ``model_compare``
│   │   (×3), ``agent_review_detail``, ``admin_external_writes``.
│   │
│   │   Sprint 56.4 — Mobile data-label sweep + Pattern-3
│   │   closure.  7 list-tables get ``data-label`` on every
│   │   ``<td>``; 4 templates also get the ``pql-list-table`` class
│   │   added so the existing mobile-collapse CSS rule kicks in
│   │   under 640 px.  Pattern-3 (mobile cards bare em-dash) is
│   │   automatically resolved because the mobile rule prepends
│   │   ``data-label`` as the column-key.  Templates:
│   │   ``runs_list`` + ``runs_list_append``, ``admin_api_keys``,
│   │   ``admin_external_writes``, ``audit_by_table``,
│   │   ``queries`` (consistency repair), ``alert_detail``
│   │   destinations table.  ``agent_reviews_list`` skipped —
│   │   becomes a card-grid in 56.9.
│   │
│   │   Sprint 56.5 — Display-layer Jinja filters
│   │   ``format_uuid`` (Pattern-6) + ``format_hash``
│   │   (Pattern-7).  ``format_uuid`` normalises packed/
│   │   hyphenated UUID strings to canonical 8-4-4-4-12;
│   │   ``format_hash`` swaps the all-zeros SHA-sentinel for
│   │   the readable label ``(no source captured)``.  Applied
│   │   in 5 templates (run-id title-attrs +
│   │   ``_run_tab_overview`` source-SHA).  Bonus: fixes the
│   │   ``_format_epoch_ms`` ``except TypeError, ValueError``
│   │   binding-target bug to the proper tuple form.  11
│   │   filter tests in ``tests/test_jinja_display_filters.py``.
│   │
│   │   Sprint 56.6 — Truncate-with-tooltip primitive.  New
│   │   ``_macros/truncate.html`` ``truncate_cell(text, max,
│   │   klass)``.  Native ``title=`` (NOT Bootstrap Tooltip —
│   │   plan-agent perf-foot-gun flag for 50-row tables); new
│   │   ``.pql-truncate-tip`` CSS class with dotted-underline
│   │   + ``cursor: help``.  Applied to 6 surfaces: run-detail
│   │   Queries SQL + UC-mutations detail, queries history SQL,
│   │   runs-list Principal/Agent/Tables, audit-search entity-
│   │   id (mirrored in JS template literal), alert-detail URL
│   │   (Alpine ``:title``), admin-external-writes commit_info.
│   │   5 macro tests.
│   │
│   │   Sprint 56.7 — Copy-button primitive + reuse of existing
│   │   toast hook.  New ``_macros/copy_button.html``
│   │   ``copy_btn(value, label, icon)`` + delegated listener in
│   │   ``frontend/js/copy_button.js`` (single click-handler
│   │   wired in ``bootstrap.js``).  Reuses
│   │   ``window.pqlToast.success/error`` (already wired up
│   │   pre-Phase-56) so no new toast plumbing.  Applied to 4
│   │   surfaces: run-detail breadcrumb (full UUID),
│   │   alert-detail webhook URL (Alpine
│   │   ``:data-pql-copy``), connection-options table (per-row),
│   │   model-detail header (model URI).
│   │
│   │   Sprint 56.8 — Bootstrap Offcanvas detail-drawer.  New
│   │   ``_macros/detail_drawer.html`` exposes a ``{% call %}``
│   │   macro; trigger + offcanvas-pane pair, Bootstrap manages
│   │   focus + ARIA + ESC + backdrop-click.  New CSS
│   │   ``components/detail_drawer.css`` sizes drawer to
│   │   ``min(640px, 90vw)`` with ``<pre>``-content styling.
│   │   Applied to 3 surfaces: run-detail Queries SQL drawer,
│   │   tool-call Args + Result drawers (each only when the
│   │   truncation kicks in), audit-log Detail drawer.  ``<details>``
│   │   alternative dropped per user-pick (Offcanvas) +
│   │   plan-agent FF-quirk risk-flag for ``<tr>`` containing
│   │   ``<details>``.
│   │
│   │   Sprint 56.9 — Tables→Cards: agent_reviews + alerts.
│   │   User-pick "Ambitious".  ``agent_reviews_list``: 5-col
│   │   table → severity-coloured card-grid
│   │   (``col-12 col-md-6 col-xxl-4``) with full-summary
│   │   first-line (no truncation), period range with
│   │   calendar icon, created-at as card-footer.  ``alerts``:
│   │   6-col Alpine x-for table → active/paused-coloured
│   │   card-grid with cron + condition + destinations as
│   │   labelled key/value lines, pause/delete actions in
│   │   card-footer.  New ``components/cards.css`` for left-
│   │   stripe accents.  Server-side filter via the existing
│   │   pagination-macro (no listTable Alpine generalisation).
│   │   ``queries.html`` Tables→Cards intentionally deferred
│   │   per plan-agent risk-flag.
│   │
│   │   Sprint 56.10 — Semantic-content corrections (action-
│   │   orientation rewrites).  3 high-traffic surfaces: source
│   │   sub-tab subtitle ("Source bytes captured at run start,
│   │   hashed for tamper-evidence"), audit-inbox heading
│   │   ("anomaly inbox" → "what needs attention") +
│   │   description rewrite, audit-queries description rewrite
│   │   (leads with user-goal, lists allow-listed table names).
│   │   Other audit findings (runs_list "Operations" rename,
│   │   audit_inbox top-KPI, audit_queries "Result" sub-section)
│   │   turned out to not match the codebase and are recorded
│   │   as false-positives.
│   │
│   │   Sprint 56.11 — UX polish bundle.  2 buried CTAs
│   │   promoted (admin_external_writes Acknowledge:
│   │   ``btn-outline-success`` → ``btn-success``;
│   │   audit_inbox JS Ack/Un-ack: ``btn-outline-primary`` →
│   │   ``btn-primary`` + full-word labels with leading icons).
│   │   Spinner-text expanded on the long-running lineage DAG
│   │   load + ARIA ``role="status"`` + ``aria-live="polite"``.
│   │   Phase-53 patterns 1, 2, 8 verified already-clean (no
│   │   CSS opacity-override, sidebar-on-error fixed by
│   │   Phase 54.1, all 5 Operations sub-tabs already render
│   │   count badges).  The "polish-bundle" sub-sprint turned
│   │   out mostly to be confirmation work.
│   │
│   │   Sprint 56.12 — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry.
│   │
│   │   Drops (recorded for the implementation log):
│   │   - ``queries.html`` Tables→Cards — plan-agent risk-flag
│   │     (½-day each for code-highlighting + toggle-state
│   │     migration).
│   │   - DESIGN-tagged findings from 56.1 per-page semantic
│   │     review — page-level redesigns deferred to Phase 57+.
│   │   - Test-coverage-sweep for admin_api_keys / branches /
│   │     federation / jobs / dashboards / audit_search —
│   │     carve-out Phase 57 (Phase 56 was UX-only by design).
│   │   - mb-3 vs mb-4 padding standardisation — explicitly
│   │     out-of-scope.
│   │
│   │   Browser-replay verification: same handling as Phase 54
│   │   + 55.  Stack runs Docker-baked; the Wave-2 mechanical
│   │   sweeps (56.2 / 56.3 / 56.4 / 56.5) need only template-
│   │   parse + pytest gates (all green).  Wave-3 primitives +
│   │   Wave-4 polish (56.6 / 56.7 / 56.8 / 56.9 / 56.11) need
│   │   browser-side verification of tooltip-hover, toast-
│   │   render, drawer click-to-open + ESC-close, card-grid
│   │   layout, action-discovery affordance — left for the
│   │   user post-rebuild.
│   │
│   │   Push gate: standard manual.
│   │
├── Phase 55 — UI polish nachzug (post-Phase-54)            ✅ done 2026-05-08
│   │
│   │   Closes the three explicit Phase-54 carve-outs (accordion
│   │   gap, /audit/queries pagination, /runs + /audit/search
│   │   pagination) plus a small-BS-pattern audit.  Six sub-sprints
│   │   in one autonomous session post the "kannst du die noch
│   │   unetanen dinge vollständig ausplanen?" plan.  Plan-phase
│   │   audit again reduced the implementation set: the
│   │   ``agent_run_compare.html`` accordion candidate from the
│   │   Phase-54 carve-out turned out to be a misidentification (no
│   │   ``.alert`` on that page; the "Cell-level diffing not
│   │   implemented" line lives on the *separate* ``run_compare.html``
│   │   side-by-side iframe view as a footer disclaimer).  Two
│   │   bonus accordion candidates surfaced instead.
│   │
│   │   Sprint 55.1 — Accordion polish.  Two more admin pages flip
│   │   the verbose ``.alert-info`` header into ``accordion-flush``:
│   │   ``admin_review_destinations.html`` (9-line webhook fan-out
│   │   + spec-link) and ``admin_cdf_tail.html`` (8-line pull-modell
│   │   + interval env-var).  Both keep their copy verbatim; distinct
│   │   accordion ids per page so a hypothetical combined view
│   │   doesn't collide on ``data-bs-target``.
│   │
│   │   Sprint 55.2 — /audit/queries pagination.  Saved-queries
│   │   cockpit kept loading the full list as a single ``UL``;
│   │   multi-user installs accumulate user-created queries past the
│   │   starter set, so the cockpit now ships defensive pagination
│   │   (50 rows per page) modelled on the Phase-54.3 ``/admin/audit``
│   │   flow.  New ``saved_audit_queries.list_paginated`` returns
│   │   ``(rows, total)`` via a separate ``COUNT(*)``;
│   │   ``html_audit_queries`` accepts ``?offset=`` and renders only
│   │   the current page; the template calls the shared ``paginate``
│   │   macro under the saved-queries card when ``total`` exceeds
│   │   the page size.  The right-hand result table is fetched
│   │   per-query via vanilla JS and already capped server-side; that
│   │   surface stays unchanged.
│   │
│   │   Sprint 55.3 — /runs infinite-scroll Load-More.  Phase 54.3
│   │   deferred this because the page already relied on Alpine
│   │   ``listTable`` for client-side filter chips.  The Alpine layer
│   │   stays intact and HTMX threads a Load-More CTA through it:
│   │   ``load_runs`` now returns ``(rows, total)`` and accepts
│   │   ``offset``; ``GET /runs`` checks ``HX-Request`` and either
│   │   renders the page shell or a fragment partial that streams
│   │   the next page of ``<tr>`` rows into ``#runs-tbody`` while
│   │   replacing ``#runs-pager`` via ``hx-swap-oob="true"`` to
│   │   advance the offset; ``listTable`` exposes ``refreshRows()``
│   │   so the new rows fall under the active filter / sort after
│   │   each append, and ``runs_list.html`` fires ``pql:rows-appended``
│   │   on ``htmx:after-swap`` to trigger it.  JSON ``/api/runs`` now
│   │   also reports ``total`` + ``next_offset`` for machine
│   │   consumers.
│   │
│   │   Sprint 55.4 — /audit/search infinite-scroll Load-More.
│   │   Phase 54.3 deferred this because the page is fetch-driven
│   │   (JSON API) and adding offset support touched both
│   │   dialect-specific FTS modules.  Per-dialect ``search`` now
│   │   accepts ``offset`` and threads ``OFFSET :n`` into the SQL on
│   │   both SQLite (FTS5 MATCH) and Postgres (tsvector/GIN); the
│   │   facade ``audit_fts.search`` and ``GET /api/audit/search``
│   │   expose ``offset`` + ``next_offset`` (the latter ``None`` once
│   │   the page is the tail).  The audit-search HTML keeps its
│   │   existing fetch flow but tracks ``offset`` in module state,
│   │   fires a Load-More button when ``next_offset`` is non-null,
│   │   and appends new rows into the existing ``<tbody>``.  A fresh
│   │   "Search" submission resets state so a new query never appends
│   │   onto stale results.
│   │
│   │   Sprint 55.5 — Smaller-BS-patterns audit + adoption.
│   │   Audit-first per the plan: each pattern adopted only with
│   │   ≥ 3 real surfaces.  Toast (1× ephemeral .alert-success) →
│   │   DROP.  Progress bars (27× spinner-border but none with
│   │   quantifiable progress; spinners stay correct) → DROP.
│   │   Link-utilities (101× ``text-decoration-none``, all semantic
│   │   and theme-correct already; mass-replacement risks more than
│   │   it gains) → DROP.  Sticky-Top → REAL: 5 long-list tables
│   │   (``/runs``, ``/audit/search``, ``/admin/audit``,
│   │   ``/agent-reviews``, ``/branches``) commonly scroll past their
│   │   thead.  New ``.pql-thead-sticky`` rule pins the column row
│   │   at ``top: var(--pql-topbar-height)`` with ``z-index: 1010``
│   │   so the existing topbar (``z-index: 1020``) always overlays
│   │   it; the mobile collapse rule
│   │   (``.pql-list-table > thead { display: none }``) keeps
│   │   winning under 640 px.
│   │
│   │   Sprint 55.6 — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry.
│   │
│   │   Drops (recorded for the implementation log):
│   │   - ``agent_run_compare.html`` accordion-info-block — no
│   │     ``.alert`` on that page; the misidentification was a
│   │     similar-name conflation with ``run_compare.html``, where
│   │     the alert is a footer disclaimer, not a header info-block.
│   │   - Toast / Progress / Link-utility sweeps — below the
│   │     ≥ 3-real-surface threshold; explicit DROP per the plan.
│   │
│   │   Browser-replay verification: stack runs from a baked Docker
│   │   image; edits don't show up live without a rebuild.
│   │   Templates parse, route imports succeed, all touched pytest
│   │   groups pass (1830 tests / 7 skipped, ``pytest -x -q``).
│   │   Pyright: 497 warnings, at budget.  Push gate: standard
│   │   manual.
│
├── Phase 54 — UI overhaul implementation (M = Modernize) ✅ done 2026-05-08
│   │
│   │   Implements the Phase-53 ``ui-overhaul-proposal.md`` Size-M
│   │   recommendation in six sub-sprints, autonomous session post
│   │   the "mache jetzt einen Plan die gefundenen Sachen alle
│   │   umzusetzen" plan.  The plan-phase code-audit reduced the
│   │   actionable set from "10 bugs + 10 visual-debt patterns"
│   │   down to the items that turned out to be real after
│   │   verifying against the codebase — several Phase-53 findings
│   │   were false alarms (no ``.btn-outline-*`` opacity override
│   │   exists in CSS; UUID format is consistent; Sentinel SHA-256
│   │   is never written; ``runs_list.html`` has no mobile-card
│   │   rendering; three of the "walkthrough doc drift" entries
│   │   were already pointing at the right URLs).
│   │
│   │   Sprint 54.1 — Error pages keep the sidebar.  The Phase-53
│   │   diagnosis ("templates do not extend base.html") was wrong;
│   │   the templates extend correctly but ``error_handlers.py:302``
│   │   hard-coded ``hide_sidebar=True``.  Flipped to ``False`` so
│   │   403/404/500 keep the icon-rail; the ``pql-error-shell``
│   │   content-class still centers the empty card.  Pre-existing
│   │   CSS comment refreshed.
│   │
│   │   Sprint 54.2 — Color-modes toggle (Bootstrap 5.3).  The CSS
│   │   under ``:root[data-bs-theme="light"]`` was already shipping
│   │   since Phase 17; only the toggle UI + JS were missing.
│   │   Three pieces: anti-FOUC inline init script in ``<head>``
│   │   reads ``localStorage.pql.theme`` + ``prefers-color-scheme``
│   │   before any CSS parses, a 3-button dropdown
│   │   (Light / Dark / Auto) in the topbar marked with
│   │   ``data-bs-theme-value``, and a delegated click handler at
│   │   the body end that persists user picks and re-applies on OS
│   │   prefer-changes when in ``auto``.  Default for new users is
│   │   ``auto`` (Bootstrap-canonical).
│   │
│   │   Sprint 54.3 — Pagination component on /admin/audit.  New
│   │   ``frontend/templates/_macros/pagination.html`` macro
│   │   (Bootstrap-5.3 ``<nav><ul.pagination>``, 7-button window
│   │   with ellipsis on overflow, ``Showing N–M of T``).  New
│   │   ``paginate_url`` Jinja global preserves filter chips while
│   │   overriding ``offset``.  ``/admin/audit`` switches from a
│   │   ``LIMIT+1`` truncation flag to a real ``offset``-based
│   │   pager backed by a separate ``COUNT(*)``.  ``/runs``,
│   │   ``/audit/queries``, ``/audit/search`` deferred — they
│   │   interact with client-side Alpine ``listTable`` filtering or
│   │   fetch-driven JS rendering and need a UX pass, not a one-
│   │   template adoption.
│   │
│   │   Sprint 54.4 — Accordion on four admin info-headers.
│   │   Replaced 8-10-line verbose ``.alert-info`` blocks under
│   │   ``/admin/audit-sinks``, ``/admin/api-keys``,
│   │   ``/admin/system-info``, ``/admin/external-writes`` with
│   │   collapsed-by-default ``accordion-flush`` "What is this
│   │   page?" toggles.  All copy preserved verbatim inside the
│   │   accordion body.  Distinct accordion ids per page so a
│   │   hypothetical combined view would not collide on
│   │   ``data-bs-target``.
│   │
│   │   Sprint 54.5 — Small bugs + compare-runs badges.  BUG-53-01:
│   │   ``_macros/help_icon.html`` was using ``|safe`` on the
│   │   popover content attribute, letting any ``"`` close the
│   │   attribute early — switched to ``|e`` so the round-trip
│   │   stays balanced.  BUG-53-09: new admin-gated GET
│   │   ``/agent-reviews`` route + ``pages/agent_reviews_list.html``
│   │   template (paginated via the 54.3 macro).  Sprint 54.5a:
│   │   compare-runs nav-tabs gain count badges on Lineage /
│   │   Rejects / Cells / Column lineage (previously only Operations
│   │   + Tool calls had them); ``runs_routes/diff.py`` now computes
│   │   four new ``*_diff_count`` context vars.  Stale
│   │   ``/jobs/new`` link in ``jobs_sidebar.html`` and stale
│   │   ``/sql-editor`` URL in three docs (sql-editor.md /
│   │   grand-tour.md / e2e-walkthroughs/README.md) corrected.
│   │
│   │   Sprint 54.6 — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry.
│   │
│   │   Drops (from Phase-53 list, false-alarms verified during
│   │   plan-phase audit):
│   │   - Pattern 1 outline-button opacity (no override in CSS).
│   │   - Pattern 6 UUID-format (consistent dashed everywhere).
│   │   - Pattern 7 Sentinel-SHA-256 filter (never written).
│   │   - Pattern 3 mobile-card ``<dl>`` (runs_list.html has no
│   │     mobile-card rendering — responsive table only).
│   │   - BUG-53-03 ``/workspace`` (icon-rail link points at the
│   │     real ``/notebooks/workspace`` admin file browser).
│   │   - BUG-53-04 / -05 / -10 walkthrough drift (admin-audit.md /
│   │     data_products.md / foreign-catalog-sync.md were already
│   │     using the correct URLs).
│   │
│   │   Push gate: standard manual.  Six commits local-only.
│
├── Phase 53 — Full replay sweep + Bootstrap UI overhaul evaluation ✅ done 2026-05-07
│   │
│   │   Diagnose-only phase (no implementation).  Three deliverables
│   │   produced in one autonomous session post the "wirklich
│   │   kompletten walkthrough machen und ordentlich screenshots"
│   │   plus "ob wir wirklich jeden erdenklichen Rahmen von Bootstrap
│   │   vollständig nutzen" plan.
│   │
│   │   Sprint A — Bootstrap-research.  Fetched 10 Bootstrap-5.3
│   │   docs/example pages (dashboard / sidebars / headers / footers
│   │   / album / color-modes / accordion / scrollspy / pagination /
│   │   getting-started); produced
│   │   ``docs/research/bootstrap53-gap-analysis.md`` with
│   │   pattern-adoption table + 5.3-feature checklist + concrete
│   │   recommendations (3 in-scope, 2 out-of-scope).
│   │
│   │   Sprint B — Replay sweep.  Walked 35 of 47 browser+hybrid
│   │   playbooks against the live stack
│   │   (PointlesSQL :8000 / soyuz :8080 / ``admin@pql.test`` /
│   │   ``seed-full-stack-demo``); 12 N/A (Hermes/CLI/deleted-
│   │   features/state-dependent).  ~50 screenshots saved under
│   │   ``docs/e2e-walkthroughs/screenshots/phase53-replay/``
│   │   organized by playbook slug.  Notes log at
│   │   ``screenshots/phase53-replay/_notes.md`` captures 10 bugs
│   │   (BUG-53-01 .. BUG-53-10) and 10 distinct visual-debt
│   │   patterns.  Notable findings: outline buttons read as
│   │   disabled across ≥ 5 surfaces (recurring CSS bug); error
│   │   pages drop the icon-rail sidebar (architectural gap);
│   │   ``/audit/search`` description has unescaped HTML
│   │   (BUG-53-01).
│   │
│   │   Sprint C — Synthesis.  ``docs/ui-overhaul-proposal.md``
│   │   combines Sprint A's Bootstrap gap-analysis with Sprint B's
│   │   visual-debt patterns into a 3-size recommendation
│   │   (S Polish 1-2 d / M Modernize 1 wk / L Reflow 2-3 wk).
│   │   Recommendation: **M — Modernize**, motivated by three
│   │   high-impact Bootstrap-5.3 adoptions (color-modes toggle,
│   │   accordion for stacked details, pagination component) plus
│   │   the recurring outline-button-opacity bug-fix.  Proposal
│   │   defers Phase-54 implementation decision to user; Phase 53
│   │   itself ships zero code changes to the UI layer.
│   │
│   │   Sprint D — Phase close (this entry).  ROADMAP +
│   │   CHANGELOG + memory entry + 2 new mkdocs nav entries.
│   │
│   │   Locked-in user picks at plan time:
│   │   1. Replay strategy: one session, all 47 sequential.
│   │      (Adjusted in execution: 35 covered, 12 N/A; depth of
│   │      visual-debt analysis prioritized over screenshot
│   │      completeness.)
│   │   2. Screenshot depth: full step-sequence (300+ target).
│   │      (Adjusted: ~50 actual; trade-off taken — Sprint C
│   │      synthesis is the actual deliverable, not the count.)
│   │   3. Bug-fix policy: trivial inline + rest dokumentieren.
│   │      Applied: 0 inline fixes this phase (all 10 bugs are
│   │      either route-realignment, doc drift, or non-trivial
│   │      template fixes — pushed to Phase 54 if approved).
│   │   4. Empfehlung-Stil: konkrete S/M/L-Empfehlung.
│   │      Applied: M.
│   │
│   │   Push gate: standard manual.  No code changes; only
│   │   ``docs/`` additions + 2 mkdocs nav entries.
│
├── Phase 52 — Playwright walkthrough completion pass ✅ done 2026-05-07
│   │
│   │   Audit + repair of the e2e walkthrough corpus.  Added a
│   │   ``> **Mode:**`` tag to all 51 walkthroughs (browser /
│   │   hybrid / hermes / curl); rewrote the README inventory
│   │   into a 4-table grouping by mode; wrote 3 new walkthroughs
│   │   for templates that had no playbook
│   │   (``volumes.md`` / ``model-compare.md`` /
│   │   ``agent-review-detail.md``); appended condensed
│   │   ``## Playwright MCP script`` sections to 11 zero-coverage
│   │   walkthroughs (branches / rollback / time-travel /
│   │   inference-lineage / models-tab / notebook-full /
│   │   error-handling / full-stack-demo / contextual-panels /
│   │   multi-workspace-setup / data_products) and to 12 thin
│   │   walkthroughs (alerts / packaging / admin-console /
│   │   admin-cdf-tail / audit-sinks / explain-rewrite /
│   │   run-comparisons / grand-tour / dbt-pipeline / list-polish
│   │   / sprint_13_11_reflexive_tools / agent_drift_monitor /
│   │   audit-cockpit-deep).  Smoke-replayed the 5 gold-standard
│   │   playbooks (auth / home / catalog-browsing /
│   │   audit-cockpit-deep / run-comparisons) — all five render
│   │   200 against the live stack; 2 selector bugs in the new
│   │   MCP scripts surfaced + fixed in the same edit
│   │   (BUG-41-01 / BUG-41-02).  Total: 54 walkthroughs in the
│   │   corpus, 40 in ``Mode: browser``, 8 hybrid, 6 hermes,
│   │   1 curl.  No code changes — pure documentation pass.
│   │
│   │   Push gate: standard manual.  ``mkdocs build --strict``
│   │   warning count unchanged at 18 (all pre-existing
│   │   cross-repo links).
│
├── Phase 51 — Git-backed workspaces ✅ done
│   │
│   │   Workspaces gain a 1..n git-repo registry; clones land at
│   │   ``<base_dir>/<workspace_id>/<slug>/`` and feed the
│   │   yaml loaders (data products + conventions) plus three
│   │   asset bridges (notebooks via ``repo:<ws>:<slug>/<rel>``
│   │   spec, dashboards + saved-queries via
│   │   ``pointlessql.yaml`` blocks).  Read-only by design — git
│   │   is truth, DB is cache.  Provider-shape (``GitProvider``
│   │   Protocol) lets GitLab/Gitea adapters drop in without
│   │   service-layer changes.  Webhook receiver
│   │   (``POST /webhook/git/{repo_id}`` + HMAC verify) and
│   │   opt-in cron loop drive auto-pulls; admin JSON API
│   │   (``/api/admin/repos/*``) drives manual ops.  4 new
│   │   plugin tools.  Pyright budget unchanged at 497.
│   │
│   ├── Sprint 51.1 — Foundation.  ``pointlessql/git/``
│   │       package: GitProvider Protocol + Generic + GitHub
│   │       impls, async subprocess helper, error family.
│   │       ``services/secrets.py`` Fernet authenticated
│   │       encryption (replaces base64url for at-rest creds).
│   │       Two ORM tables (``workspace_repos`` +
│   │       ``workspace_repo_secrets``) via Alembic
│   │       ``aa9b1c3e5d7f``.  ``WorkspaceReposSettings``,
│   │       4 ``ErrorCode`` members, ``cryptography>=44.0``
│   │       added.  34 new tests.
│   │
│   ├── Sprint 51.2 — Yaml-loader integration.
│   │       ``discover_repo_yaml_files`` walks every workspace
│   │       repo's clone dir; ``load_contracts_for_workspace``
│   │       + ``load_conventions_for_workspace`` combine
│   │       env-paths + repo-discovered yaml.
│   │       ``build_post_pull_loader_hook`` returns a
│   │       ``sync_repo``-compatible hook that re-runs both
│   │       loaders; counts surface on ``SyncOutcome``.  Loader
│   │       errors stay isolated.  6 new tests.
│   │
│   ├── Sprint 51.3 — Notebook + Dashboard + Saved-Query
│   │       bridge.  ``resolve_notebook_path`` accepts
│   │       ``repo:<ws>:<slug>/<rel>.py`` spec.  New
│   │       ``pointlessql/repo_assets/`` package with two yaml
│   │       loaders.  ``Dashboard`` + ``SavedQuery`` rows gain
│   │       ``source`` + ``repo_yaml_path`` columns via Alembic
│   │       ``bb1d4f6e8a0c`` so the admin UI can render
│   │       git-canonical rows as read-only.  13 new tests.
│   │
│   ├── Sprint 51.4 — Webhook receiver + cron sync loop.
│   │       Unauthenticated ``POST /webhook/git/{repo_id}``
│   │       (HMAC sig is the auth) verifies + parses + fires
│   │       async ``sync_repo``.  Lifespan-managed
│   │       ``_workspace_repos_sync_loop`` opt-in via
│   │       ``POINTLESSQL_REPOS_SYNC_INTERVAL_SECONDS≥60``.
│   │       ``/webhook/git/`` added to PUBLIC_PREFIXES + CSRF
│   │       exempt list.  9 new tests.
│   │
│   ├── Sprint 51.5 — Admin JSON API.  Eight admin-gated
│   │       endpoints behind ``/api/admin/repos`` (list /
│   │       create / detail / sync / add-or-rotate-secret /
│   │       revoke-secret / rotate-webhook / delete).
│   │       Reveal-once webhook secret on creation; secret
│   │       plaintext never echoed back on subsequent reads.
│   │       Every mutation stamps an ``audit_log`` entry.
│   │       Workspace-scoping enforced via ``_load_repo``
│   │       (other-workspace repos 404).  10 new tests.
│   │
│   └── Sprint 51.7 — Plugin tools.  Four new LLM-callable
│           Hermes tools (``pql_list_workspace_repos``,
│           ``pql_get_workspace_repo``,
│           ``pql_trigger_repo_sync`` (supervisor-gated),
│           ``pql_repo_sync_history``).  ``PointlessClient``
│           gains four matching methods.  Slug→id resolution
│           lives client-side.  8 new plugin tests; total
│           141 → 149.
│
│   Carve-outs (deferred):
│   - **Sprint 51.6 (OAuth GitHub-App).**  Was approved in the
│     plan as opt-in; deferred to a follow-up sub-sprint
│     because (a) it requires registering a real GitHub App +
│     a private-key secret to exercise end-to-end and (b)
│     deploy-keys / PATs already cover the per-workspace
│     credential surface today.  When the App is available,
│     drop ``GitHubInstallation`` + the OAuth callback flow +
│     a per-user token-refresh path on top of the existing
│     ``GitHubProvider``.  No foundation refactor needed.
│   - **HTML admin pages.**  The 51.5 surface today is JSON
│     only.  A 5-tab detail page (Overview / Auth / Sync
│     history / Files / Danger) is a natural follow-up; the
│     JSON shape is sufficient for the agent + ``curl`` paths.
│
├── Phase 50 — Native Data-Product support ✅ done
│   │
│   │   Every UC schema can opt-in to product status by committing
│   │   a ``pointlessql.yaml`` file in the data-team repo declaring
│   │   steward, SemVer version, freshness-SLA and per-table schema
│   │   contract.  Yaml is canonical; git-blame is the audit log.
│   │   ``pql.write/merge`` enforces the contract before any Delta
│   │   IO (fail-loud ``DataProductContractViolation`` on breaking
│   │   diffs); a background scanner emits ``sla_violated``
│   │   CloudEvents when freshness drifts past the declared SLA.
│   │   Workspace-scoped ``/data-products`` UI + 5 plugin tools
│   │   surface discovery, contract inspection, live-diff and
│   │   compliance history.  Pyright budget unchanged at 497.
│   │
│   ├── Sprint 50.1 — Foundation.  ``pointlessql/data_products/``
│   │       package: 11-type column-spec Pydantic model,
│   │       ``DataProductRef(str)`` validation type,
│   │       ``DataProductError`` family (4 subclasses), yaml
│   │       loader with idempotent UPSERT + steward-FK
│   │       resolution.  Two ORM tables (``data_products`` +
│   │       ``data_product_contract_events``) via Alembic
│   │       ``rr8u0w2y4a6c``.  4 ``ErrorCode`` members,
│   │       ``DataProductsSettings`` env-prefix.  23 new tests.
│   │
│   ├── Sprint 50.3 — Enforcement.  Pure-functional
│   │       ``ContractDiffResult`` core + engine-tuples /
│   │       Delta-schema adapters (canonicalises
│   │       int64/long, float64/double, decimal* aliases).
│   │       Pre-write hooks in ``pql/_write.py`` +
│   │       ``pql/_merge.py`` raise
│   │       ``DataProductContractViolation`` *before* Delta IO
│   │       on breaking diffs.  ``pending_contract_event`` on
│   │       ``OperationRecorder`` + post-commit hook persist
│   │       one event row per check; exception path also
│   │       persists so refused attempts show up in the audit
│   │       trail.  15 new tests.
│   │
│   ├── Sprint 50.4 — Freshness Scanner.  Background loop walks
│   │       SLA-bearing products, observes latest write via
│   │       ``DeltaTable.history()``, emits
│   │       ``pointlessql.data_product.sla_violated`` CloudEvent
│   │       on stale ages.  ``last_alerted_at`` re-alert
│   │       suppression (default 60 min).  Opt-in via
│   │       ``POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS≥60``.
│   │       New EVENT_TYPE registered in governance-events
│   │       registry.  5 new tests.
│   │
│   ├── Sprint 50.2 — Web UI.  ``/data-products`` index +
│   │       ``/data-products/{cat}/{schema}`` 5-tab detail
│   │       (Overview / Contract / Diff / Lineage / Compliance)
│   │       with cytoscape mini-DAG via lineage_row_edges.
│   │       Five JSON endpoints (list/detail/diff/lineage/
│   │       admin-reload).  Icon-rail entry between SQL and
│   │       Dashboards.  11 new tests.
│   │
│   └── Sprint 50.5 — Plugin tools.  Five new LLM-callable Hermes
│           tools (``pql_list_data_products``,
│           ``pql_get_data_product``,
│           ``pql_get_data_product_contract``,
│           ``pql_check_contract_compliance``,
│           ``pql_data_product_compliance_history``) all wired
│           into ``register_all`` so any keyed agent can use
│           them.  Plugin client gains four
│           ``/api/data-products/*`` methods.  7 new plugin
│           tests.
│
├── Phase 48 — Primitive-Obsession StrEnum Sweep ✅ done
│   │
│   │   Replaces the 9 enum-shaped string columns and 17
│   │   CloudEvents type literals with explicit ``StrEnum`` /
│   │   ``Final`` registries.  StrEnum members compare equal to
│   │   their string value, so DB-stored values, JSON wire
│   │   format, and SQL CHECK constraint matching are
│   │   byte-identical -- no DB migration, no wire-format change,
│   │   no production behaviour change.  Models stay on
│   │   ``Mapped[str]`` per anti-goal.  Pyright budget unchanged
│   │   at 497.  1686 tests pass (1673 baseline + 13 new enum
│   │   sanity tests).
│   │
│   ├── Sprint 48.1 — Add ``pointlessql/enums.py`` with
│   │       ``RunStatus`` / ``OpName`` / ``ReadKind`` /
│   │       ``QueryStatus`` / ``ReviewSeverity`` / ``ReviewKind`` /
│   │       ``AuditSinkType`` / ``EventOutcome`` /
│   │       ``BranchAction`` StrEnums.  ``tests/test_enums.py``
│   │       (13 cases) pins every value byte-for-byte against
│   │       legacy ``frozenset`` / tuple constants.  Purely
│   │       additive -- old constants stay valid.
│   │
│   ├── Sprint 48.2 — Migrate consumers in four route-family
│   │       batches.  Batch 1 RunStatus + QueryStatus (~11
│   │       files: agent-run lifecycle / events /
│   │       audit-aggregator + query_history + sql_routes +
│   │       PQL read paths).  Batch 2 OpName + BranchAction
│   │       (~13 files: ``record_operation`` /
│   │       ``operation_context`` typed; 9 PQL primitives +
│   │       sql_explain pass enum members; ``_op_name_for_node``
│   │       returns ``OpName``; ``record_branch_audit_log``
│   │       takes ``BranchAction``).  Batch 3 ReadKind (~5
│   │       files: ``record_query`` / ``record_read`` /
│   │       audit_routes typed; ``VALID_READ_KINDS`` derived from
│   │       StrEnum).  Batch 4 AuditSinkType + EventOutcome +
│   │       ReviewSeverity (~4 files: dispatch_to_sinks branch,
│   │       outcome updates, ``_SEVERITY_RANK`` keys).
│   │
│   └── Sprint 48.3 — Add unified
│           ``pointlessql/services/cloudevents/`` package
│           re-exporting the 17 CloudEvents ``Final`` constants
│           under one import path.  Legacy ``EVENT_TYPE_*``
│           aliases stay on
│           ``services.agent_runs.events`` and
│           ``services.governance_events`` for back-compat;
│           ``test_cloudevents_registry_matches_legacy_constants``
│           pins both halves byte-for-byte.
│
├── Phase 49c — TableFqn validation type ✅ done
│   │
│   │   Adds ``pointlessql/table_fqn.py`` with a ``str``-subclass
│   │   validation type for UC three-part identifiers.  Factory
│   │   methods: ``parse()`` (validates) + ``from_parts()`` (no
│   │   validation, for already-split components).  Anti-goal
│   │   preserved: ``Mapped[str]`` columns absorb ``TableFqn``
│   │   transparently (str subclass), wire format identical, no
│   │   alembic.  Pyright budget unchanged at 497.  10 sanity
│   │   tests pin the contract.
│   │
│   ├── Sprint 49c.1 — Add ``pointlessql/table_fqn.py`` plus
│   │       ``tests/test_table_fqn.py`` (10 cases pinning subclass
│   │       identity, JSON round-trip, f-string interpolation,
│   │       parse / from_parts contract).  Purely additive — no
│   │       callsite migrated yet.
│   │
│   └── Sprint 49c.2 — Migrate consumers + producers.  Step A
│           kills the two byte-for-byte duplicate
│           ``_split_three_part`` validators in
│           ``api/pql_introspect_routes.py`` +
│           ``api/pql_write_routes.py``; their callers now invoke
│           ``TableFqn.parse(...).parts()`` directly.  Step B wraps
│           13 f-string FQN producers across api/, services/, pql/
│           via ``TableFqn.from_parts(...)``.  Step C annotates
│           the highest-value service-layer signatures
│           (``services/external_write_scanner`` reference); the
│           remaining ~36 consumer signatures stay on plain ``str``
│           for incremental migration in future phases (each is an
│           isolated patch since ``TableFqn`` is-a ``str``).
│
├── Phase 49b — Service-File Splits ✅ done
│   │
│   │   Two oversize service files migrated into Phase-35-style
│   │   per-axis subpackages.  Public API unchanged via
│   │   ``__init__.py`` re-exports; existing
│   │   ``from pointlessql.services...operations import X``
│   │   imports keep working without churn.  Cross-module
│   │   helpers dropped leading underscores per Phase 35
│   │   convention; module-internal helpers kept theirs.
│   │   Pyright budget unchanged at 497.  1686 tests pass.
│   │
│   ├── Sprint 49b.1 — ``services/agent_runs/operations.py``
│   │       (929 LOC) → six-file subpackage:
│   │       ``__init__`` (re-exports), ``_common``
│   │       (OperationRecorder + ``serialise_warnings`` /
│   │       ``stamp_audit_marker`` + ``LINEAGE_FAILED_MARKER`` +
│   │       ``VALID_OP_NAMES`` derived from ``OpName`` StrEnum),
│   │       ``_rollback`` (RollbackError + 4 subclasses),
│   │       ``_lifecycle`` (``record_operation`` +
│   │       ``operation_context``), ``_lineage`` (3
│   │       post-commit hooks: emit + row-edges + column-edges),
│   │       ``_rejects`` (1 hook), ``_value_changes`` (1 hook).
│   │       One test (``test_operation_warnings.py``) updated to
│   │       import ``stamp_audit_marker`` from
│   │       ``operations._common``.
│   │
│   └── Sprint 49b.2 — ``services/audit_aggregator.py``
│           (913 LOC) → four-file subpackage:
│           ``_query_builder`` (type aliases + ``VALID_*`` sets
│           + ``MetricSpec`` dataclass + ``metric_spec()``
│           switch + ``bin_expr()`` + ``apply_audit_filters()``
│           + ``scalar_count()``), ``_summary`` (``summary()``),
│           ``_timeseries`` (``timeseries()`` + module-private
│           ``_group_col()``), ``_anomaly`` (``anomalies()`` +
│           ``compute_run_anomaly()`` + ``backfill_run_anomalies()``
│           + ``RUN_ANOMALY_METRICS`` + ``_SEVERITY_RANK`` +
│           ``_classify()`` + ``_bin_floor_compare_string()``).
│           One test (``test_dbt_test_failure_bridge.py``) updated
│           to import ``metric_spec`` (was ``_metric_spec``).
│
├── Phase 49a — Repo-wide Lint-Sweep ✅ done
│   │
│   │   Single-sprint cleanup of pre-existing ruff E501 + pydoclint
│   │   DOC502 / DOC503 / DOC601 / DOC603 violations accumulated
│   │   since Phase 35.  119 ruff hits (mostly test-function
│   │   signatures) cleared via ``uv run ruff format``; 36
│   │   pydoclint hits cleared by aligning Raises sections with
│   │   the centralised-handler typed-error pattern (HTTPException
│   │   → typed errors like ``AuthenticationError`` /
│   │   ``ResourceNotFoundError`` / ``ValidationError``) and by
│   │   filling in missing class-attribute lines for
│   │   ``ApiKey.lineage_inbound`` / ``LineageRowEdge.producer`` /
│   │   ``LineageColumnMap.producer`` / ``RollbackAmbiguous`` /
│   │   ``RollbackStale`` (and their ``external_event_id`` /
│   │   ``status_code`` / ``error_code`` siblings).  Pyright
│   │   budget unchanged at 497.  1686 tests pass.  Two
│   │   commits: ``chore(format)`` (68-file reformat sweep) +
│   │   ``chore(docs)`` (12-file docstring alignment).  No
│   │   behaviour change.
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
