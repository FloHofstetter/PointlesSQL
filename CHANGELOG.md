# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Refactored — Phase 12.9 / Sprint 89a: api/main.py federation routes extract

Tenth decomposition slice for ``api/main.py`` — first cut of Sprint
89's federation+jobs+dashboards triple. All UC federation
administration moves out: connections, external-locations,
credentials (5 routes each + 6 HTML pages = 21 routes total).
main.py drops 2,683 → 2,406 LOC (-277).

- **New module** [federation_routes.py](pointlessql/api/federation_routes.py)
  (322 LOC). All 21 routes are ``require_admin``-gated, mirroring
  the soyuz-catalog rule that federation administration is
  admin-only until a finer-grained CREATE_* privilege ships.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(federation_router)``
  next to the other nine routers.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 25 warnings (-1), ``pydoclint`` 0 violations,
  ``pytest -k 'connection or credential or federation or
  external' --ignore=tests/test_jupyter.py`` 34/34 passed.

### Refactored — Phase 12.9 / Sprint 88b: api/main.py notebook WS endpoints extract

Ninth decomposition slice for ``api/main.py`` — closes out the
notebook surface. The two ``@app.websocket`` handlers
(``/ws/notebook/kernel`` + ``/ws/notebook/lsp``) and their shared
``resolve_sql_approved_tables`` helper move into a dedicated
``notebook_kernel_ws.py``. main.py drops 3,227 → 2,683 LOC (-544).

- **New module** [notebook_kernel_ws.py](pointlessql/api/notebook_kernel_ws.py)
  (601 LOC). Both WS endpoints plus the SQL-approval helper.
  Underscore prefix dropped from helper name
  (``resolve_sql_approved_tables`` is module-public within the
  new package). WS auth model preserved verbatim: cookie + JWT
  decode, traversal guard, 4401/4400/4404/1011 close codes.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(notebook_ws_router)``
  next to the other eight routers. Now-unused ``contextlib``,
  ``WebSocket``, ``WebSocketDisconnect``, ``UnityCatalogClient``,
  ``UserInfo``, ``check_privilege``, ``SELECT``, plus the
  ``services.pyright_bridge`` import all auto-trimmed by ruff
  (the WS routes were the only remaining callers).

- **WS lifecycle preserved.** All five close codes (4401
  unauthenticated, 4400 bad path, 4404 missing pyright, 1011 spawn
  failure, normal close) plus the ZMQ↔WS forward tasks +
  per-cell output counters + per-execute history-row stamping
  moved verbatim.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 26 warnings (-18 from Sprint 88a because the WS code
  carried 18 partial-unknown warnings), ``pydoclint`` 0
  violations. ``pytest tests/test_api_notebook_workspace.py
  tests/test_notebook_workspace.py`` 27/27 passed. WS endpoints
  have no unit tests; their integration coverage runs through
  ``docs/e2e-walkthroughs/notebook_kernel.md`` (Playwright
  playbook).

### Refactored — Phase 12.9 / Sprint 88a: api/main.py notebook HTTP routes extract

Eighth decomposition slice for ``api/main.py``. The HTTP half of the
notebook surface lifts out: editor page, doc bundle (GET + POST),
per-cell run history, the workspace tree + inspect endpoints, the
upload/create/rename/delete CRUD, and the workspace HTML page.
main.py drops 3,751 → 3,227 LOC (-524). The two WebSocket endpoints
(``/ws/notebook/kernel`` + ``/ws/notebook/lsp``) and their shared
``_resolve_sql_approved_tables`` helper stay in main.py for now —
Sprint 88b will move them into a dedicated WS module.

- **New module** [notebooks_routes.py](pointlessql/api/notebooks_routes.py)
  (580 LOC). Owns 11 routes plus the ``build_notebook_doc_bundle``
  helper shared between the HTML editor and the JSON bundle
  endpoint. All existing admin gates preserved.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(notebooks_router)``
  next to the other seven routers. Now-unused ``UploadFile``,
  ``File``, ``Form``, ``uuid4``, top-level ``json`` imports
  auto-trimmed by ruff.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 44 warnings (-10 from Sprint 87c baseline because the
  moved notebook code carried 10 partial-unknown warnings),
  ``pydoclint`` 0 violations, ``pytest -k notebook
  --ignore=tests/test_jupyter.py`` 34/34 passed.

### Refactored — Phase 12.9 / Sprint 87c: api/main.py governance routes extract

Seventh decomposition slice for ``api/main.py``. The full governance
surface lifts out: table column statistics (Sprint 56),
notebook-from-table scratch helper, catalog create/sync/patch +
schema patch, tags + permissions (get/patch + effective), and
lineage. main.py drops 4,242 → 3,751 LOC (-491).

- **New module** [governance_routes.py](pointlessql/api/governance_routes.py)
  (549 LOC). Owns 14 routes plus ``split_full_name`` and
  ``enforce_table_profile_access`` helpers (underscore prefixes
  dropped).

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(governance_router)``
  next to the other six routers. Module-level ``MODIFY`` import
  dropped (only the moved routes used it).

- **Authorization model preserved.** Profile + stats GET still
  require SELECT (admin short-circuits); stats DELETE +
  open-in-notebook + create-catalog + sync-catalog are still
  admin-only; catalog/schema PATCH still need MODIFY; tag PATCH
  MODIFY; permission PATCH MANAGE_GRANTS; lineage GET SELECT.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 54 warnings (-13 from Sprint 87b baseline because the
  moved governance code carried 13 ``Type … partially unknown``
  warnings), ``pydoclint`` 0 violations, ``pytest -k 'stats or
  table_stats or tag or permission or lineage or open_in_notebook'
  --ignore=tests/test_jupyter.py`` 27/27 passed.

### Refactored — Phase 12.9 / Sprint 87b: api/main.py UC volumes routes extract

Sixth decomposition slice for ``api/main.py``. The full UC volumes
surface lifts out: 4 JSON endpoints (browse, upload, delete file +
convert-to-Delta) + 2 HTML pages (volumes list + per-volume detail).
main.py drops 4,717 → 4,242 LOC (-475).

- **New module** [volumes_routes.py](pointlessql/api/volumes_routes.py)
  (527 LOC). Owns 6 routes plus ``soyuz_base_url``,
  ``volume_full_name_split``, ``convert_volume_file_sync``, the
  ``DELTA_PRIMITIVE_TO_UC`` dict + ``delta_field_to_uc``
  field-mapper. Underscore prefixes dropped from helper names;
  the type-mapping pair is re-exported from main.py under its
  legacy ``_DELTA_PRIMITIVE_TO_UC`` / ``_delta_field_to_uc``
  aliases (Invariant 8 of the modularisation plan) so
  ``tests/test_volume_convert_type_mapping.py`` keeps importing
  them from ``pointlessql.api.main``.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(volumes_router)``
  next to the other five routers. Stale ``_soyuz_base_url`` helper
  deleted (the moved volumes routes were the only callers); top-
  level ``httpx`` import dropped for the same reason.

- **Convert-to-Delta admin gate preserved.** The
  ``api_convert_volume_file_to_delta`` route still calls
  ``require_admin(request)`` before any work, mirroring the
  original behaviour.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 67 warnings (unchanged), ``pydoclint`` 0 violations,
  ``pytest -k volume --ignore=tests/test_jupyter.py`` 15/15
  passed; the targeted
  ``tests/test_volume_convert_type_mapping.py`` 9/9 passed
  (re-export gate intact).

### Refactored — Phase 12.9 / Sprint 87: api/main.py alerts + feed routes extract

Fifth decomposition slice for ``api/main.py``. The full alerts
surface lifts out: ``/api/alerts`` CRUD (5 routes), the destinations
sub-resource (2 routes), per-user feed-token (2 routes), the two
unauthenticated pull-feed endpoints (``/alerts/feed.atom`` +
``/alerts/feed.json``), and the two HTML pages (``/alerts`` list +
``/alerts/{slug}`` detail). main.py drops 5,256 → 4,717 LOC (-539).

- **New module** [alerts_routes.py](pointlessql/api/alerts_routes.py)
  (585 LOC). Owns 13 routes plus three module-level helpers
  (``base_url``, ``rotate_or_fetch_feed_token``,
  ``user_for_feed_token``). Underscore prefixes dropped from
  helpers; ``saved_queries_service`` imported at module level for
  the alerts list page (which renders the dropdown of available
  saved-queries to attach an alert to).

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(alerts_router)``
  next to the other four routers. Unused ``saved_queries_service``
  + ``JSONResponse`` imports removed (the alerts routes were the
  only remaining callers).

- **Feed-token auth preserved.** ``PUBLIC_PREFIXES`` in
  ``api/middleware.py`` already exempts ``/alerts/feed.atom`` +
  ``/alerts/feed.json`` from session auth so the route handlers
  can authenticate via the opaque ``?token=…`` query string and
  401 on mismatch.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 67 warnings (unchanged), ``pydoclint`` 0 violations,
  ``pytest -k alert --ignore=tests/test_jupyter.py`` 19/19
  passed.

### Refactored — Phase 12.9 / Sprint 86c: api/main.py queries + saved-queries extract

Fourth decomposition slice for ``api/main.py`` — completes the
original Sprint-86 plan. The query-history read endpoints
(``/api/queries`` list/get/chart-config), the ``/queries`` HTML page,
and the full ``/api/saved-queries`` CRUD all move into a new
``api/queries_routes.py``. main.py drops 5,652 → 5,256 LOC (-396).

- **New module** [queries_routes.py](pointlessql/api/queries_routes.py)
  (444 LOC). Owns three query-history routes + the ``/queries``
  HTML page + five saved-queries routes (list/create + get/patch/
  delete by slug) + the ``parse_since`` window-string helper.
  Underscore prefix dropped from ``parse_since`` since it is now
  module-public within the new package.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(queries_router)``
  next to the other three routers. Module-level imports of
  ``query_history`` + ``saved_queries`` services dropped — the
  alerts route already function-locally re-imports ``saved_queries``
  so nothing else regressed.

- **Visibility model preserved.** Non-admin still sees only their
  own ``query_history`` rows (``user_id`` query param clamped
  server-side); saved queries still 404 on missing OR forbidden so
  private slugs are not discoverable; chart config + delete still
  owner+admin only.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 67 warnings (-7 from Sprint 86b baseline because the
  dropped ``query_history`` + ``saved_queries`` module-level
  imports were the source of seven ``Type … partially unknown``
  warnings), ``pydoclint`` 0 violations, ``pytest -k 'saved_quer
  or query_history or queries' --ignore=tests/test_jupyter.py``
  26/26 passed.

### Refactored — Phase 12.9 / Sprint 86b: api/main.py SQL editor routes extract

Third decomposition slice for ``api/main.py``. The four-route
Phase-12 SQL editor surface (execute / cancel / download + the
``/sql`` page) moved into a new module. Original Sprint-86 plan
bundled SQL with ``/api/queries`` + ``/api/saved-queries``; this
slice carved off the SQL pieces alone for a smaller blast radius.
main.py drops 6,203 → 5,652 LOC (-551).

- **New module** [sql_routes.py](pointlessql/api/sql_routes.py)
  (597 LOC). Owns ``POST /api/sql/execute``,
  ``POST /api/sql/execute/{query_id}/cancel``,
  ``GET  /api/sql/execute/{history_id}/download``, and the
  ``GET /sql`` HTML page, plus the four module-level helpers
  (``short_sql_hash``, ``run_sql_sync``, ``live_queries``,
  ``run_sql_export_sync``). Underscore prefixes dropped since the
  helpers are now module-public within the new package.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(sql_router)``
  alongside the existing auth + catalog routers. Unused
  ``record_query_async`` re-import dropped (the SQL routes were the
  only main.py callers). ``_parse_since`` deliberately stays in
  main.py because ``/api/queries`` (Sprint 86c) still depends on it.

- **Authorization preserved.** Both execute and download still
  re-run ``check_privilege(SELECT)`` per referenced 3-part table —
  a stale ``query_history`` row is not a bypass. The cancel route
  stays idempotent (204 on unknown ids).

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 74 pre-existing warnings, ``pydoclint`` 0 violations,
  ``pytest -k 'sql or query' --ignore=tests/test_jupyter.py`` 48/48
  passed.

### Refactored — Phase 12.9 / Sprint 86: api/main.py catalog tree routes extract

Second decomposition slice for ``api/main.py``. Narrowed from the
sketched ``catalog/sql/queries`` triple-extract down to just the five
catalog tree routes — the lowest-risk surface in the route set, used
to validate the ``APIRouter`` extraction pattern before the much
larger SQL execute + queries-page extracts in the next sprint.
main.py drops 6,347 → 6,203 LOC (-144).

- **New module** [catalog_routes.py](pointlessql/api/catalog_routes.py)
  (186 LOC). Owns the five sidebar/breadcrumb endpoints
  (``/api/tree``, ``/api/catalogs``,
  ``/api/catalogs/{c}/schemas``,
  ``/api/catalogs/{c}/schemas/{s}/tables``,
  ``/api/catalogs/{c}/schemas/{s}/tables/{t}/preview``) plus the two
  preview helpers (``preview_head`` engine-aware row truncation,
  ``run_table_preview`` thread-pool worker) and the
  ``PREVIEW_ROW_LIMIT = 10`` constant. Underscores dropped from the
  helper names since they are now module-public within the new package.

- **Mount point** in
  [main.py](pointlessql/api/main.py): ``app.include_router(catalog_router)``
  added next to the existing ``auth_router`` line. Unused
  ``make_principal_client`` import removed (only the moved preview
  code referenced it).

- **Authorization preserved.** Schemas + tables endpoints still call
  hierarchical ``check_privilege`` (USE_CATALOG / USE_SCHEMA),
  preview still resolves ``effective_permissions`` once and feeds
  ``check_privilege_from_effective(SELECT)``. Preview responses keep
  ``Cache-Control: no-store`` so revoked grants do not leak through
  the browser disk cache.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright`` 0
  errors / 74 pre-existing warnings, ``pydoclint`` 0 violations,
  ``pytest -k 'catalog or tree or preview'
  --ignore=tests/test_jupyter.py`` 44/44 passed (test_jupyter.py has a
  pre-existing import error unrelated to this sprint).

### Refactored — Phase 12.9 / Sprint 85: api/main.py middleware + helpers extract

First decomposition slice for the 6,599-LOC ``api/main.py``. The
lowest-risk pieces — middleware stack + per-request dependencies +
async fire-and-forget audit/query-history writers — moved into three
new modules. main.py drops 6,599 → 6,341 LOC (-258); no route logic
moved this sprint.

- **New modules** under ``pointlessql/api/``:
  [middleware.py](pointlessql/api/middleware.py) (~155 LOC) — five
  middleware functions wired into a single
  ``register_middleware(app)`` entrypoint that preserves the
  LIFO stacking order (``request_id → static_revalidate → csrf →
  rate_limit → auth → handler`` on every incoming request).
  ``PUBLIC_PREFIXES`` lifted out of its underscore-prefixed private
  name since the new module owns it.
  [dependencies.py](pointlessql/api/dependencies.py) (~90 LOC) —
  request-scoped helpers ``get_uc_client`` / ``get_user`` /
  ``require_admin`` / ``client_ip``. main.py re-imports them with
  the legacy ``_get_user`` etc. aliases so the ~hundred call sites
  inside its route handlers keep working unchanged.
  [_audit_helpers.py](pointlessql/api/_audit_helpers.py) (~130 LOC)
  — ``audit`` + ``record_query_async`` async writers, pulled out
  so route-group modules in Sprints 86-90 can import them without
  dragging in the full main module.

- **Middleware order preserved.** ``register_middleware`` calls
  ``app.middleware("http")()`` in the exact same order the decorators
  previously fired in main.py, so the LIFO execution chain on an
  incoming request is byte-identical to the pre-Sprint-85 build.

- **Public surface preserved.** Every existing call into the helpers
  works through the legacy underscore-prefixed re-imports
  (``_get_uc_client``, ``_get_user``, ``_require_admin``,
  ``_record_query_async``, ``_audit``) at the top of main.py, so
  the route handlers below — which still total >5,000 LOC — were
  not touched at all.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 74 pre-existing warnings, ``pytest tests/test_csrf.py
  tests/test_rate_limit.py tests/test_auth.py`` 52/52 passed.

### Refactored — Phase 12.9 / Sprint 84: services/scheduler.py → 5-module package

Eighth backend split — largest service (1,776 LOC). The
``services/scheduler.py`` module became the package
``services/scheduler/`` with five sibling modules carved along the
pipeline boundaries (registry → executors → DAG → runs → loop).

- **Package layout** under ``pointlessql/services/scheduler/``:
  [registry.py](pointlessql/services/scheduler/registry.py) (~95 LOC)
  — ``KindRegistry``, ``JobExecutor`` type alias,
  ``build_default_registry``.
  [executors.py](pointlessql/services/scheduler/executors.py)
  (~555 LOC) — the four built-in executors
  (``_pg_sync_executor``, ``_python_executor``,
  ``_papermill_executor`` + helpers, ``_alert_check_executor``).
  Function-local imports for ``pql.pql`` / ``alerts`` / ``models``
  / ``authorization`` are preserved verbatim — the pre-Sprint-84
  code dodged a circular chain through ``pointlessql.db`` and the
  same pattern continues to work.
  [dag.py](pointlessql/services/scheduler/dag.py) (~135 LOC) —
  pure graph algorithms: ``validate_dag`` (cycle detection),
  ``_topological_order`` (Kahn's algorithm), ``_parse_depends_on``.
  [runs.py](pointlessql/services/scheduler/runs.py) (~825 LOC) —
  DB helpers, ``log_job``, per-task lifecycle (``_run_one_task``,
  ``_run_dag``), run orchestration (``execute_run`` +
  ``_execute_run_core``), telemetry helpers. Owns the test-hook
  globals ``_sleep`` / ``_webhook_client_factory`` /
  ``_WEBHOOK_TIMEOUT_SECONDS``.
  [loop.py](pointlessql/services/scheduler/loop.py) (~250 LOC) —
  ``tick_once``, ``_execute_with_semaphores``, the ``Scheduler``
  driver class.

- **Public surface preserved.** The package
  [__init__.py](pointlessql/services/scheduler/__init__.py)
  re-exports every name the API layer
  ([pointlessql/api/main.py:55](pointlessql/api/main.py#L55)),
  scheduler tests, and external docs reference (``KindRegistry``,
  ``Scheduler``, ``build_default_registry``, ``execute_run``,
  ``tick_once``, ``validate_dag``, ``log_job``,
  ``_alert_check_executor``, ``_papermill_executor``,
  ``resolve_notebook_path``, ``_is_due``,
  ``_execute_with_semaphores``, ``_WEBHOOK_TIMEOUT_SECONDS``,
  ``_sleep``, ``_webhook_client_factory``).

- **Test-hook patch sites moved.** 6 monkeypatch sites across
  ``tests/test_scheduler_dag.py`` (``_sleep``) and
  ``tests/test_metrics.py`` (``_webhook_client_factory``) now patch
  ``scheduler_service.runs._sleep`` /
  ``scheduler_service.runs._webhook_client_factory`` directly. The
  runs.py module reads them via local-name lookup, so monkeypatching
  the package-level re-export does not take effect — the right
  structural fix is to patch the module where the symbol is used.

- **Per-file pyright suppressions.** Added ``# pyright:
  reportPrivateUsage=false`` to ``__init__.py``, ``loop.py``,
  ``registry.py``, and ``runs.py``; and ``# pyright:
  reportUnusedFunction=false`` to ``executors.py``, ``dag.py``,
  and ``runs.py``. Pyright's strict-mode rules treat any
  underscore-prefixed cross-module access as private leakage —
  legitimate within a single package, and the public contract
  (``__all__`` lists, the test patches) is what actually
  constrains the surface.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 15 pre-existing warnings, ``pydoclint`` 0 violations,
  ``pytest tests/test_scheduler.py tests/test_scheduler_dag.py
  tests/test_metrics.py tests/test_alerts.py
  tests/test_scheduler_papermill.py`` 80/80 passed.

### Refactored — Phase 12.9 / Sprint 83: services/unitycatalog.py → mixin package

Seventh backend split — broadest blast radius of the arc (18+ call
sites, 23 tests patch soyuz function names by string). The 783-LOC
``services/unitycatalog.py`` module became the package
``services/unitycatalog/`` with one mixin per securable type plus a
shared ``_api.py`` for the soyuz function bindings + error decorator.
``UnityCatalogClient`` composes the mixins so its single-import
surface (``from pointlessql.services.unitycatalog import
UnityCatalogClient``) is unchanged.

- **Package layout** under ``pointlessql/services/unitycatalog/``:
  [_api.py](pointlessql/services/unitycatalog/_api.py) (~190 LOC) —
  every soyuz typed function imported as ``_get_X`` / ``_create_X``
  / ``_list_X`` / ``_update_X`` / ``_delete_X``, plus the shared
  ``wrap_catalog_errors`` decorator.
  [_catalogs.py](pointlessql/services/unitycatalog/_catalogs.py)
  (~130 LOC) — ``CatalogsMixin`` (catalog CRUD + ``get_tree``
  aggregator that reaches into ``MetadataMixin.list_schemas`` /
  ``list_tables`` via ``self``).
  [_metadata.py](pointlessql/services/unitycatalog/_metadata.py)
  (~210 LOC) — ``MetadataMixin`` (schema + table + tag CRUD).
  [_permissions.py](pointlessql/services/unitycatalog/_permissions.py)
  (~110 LOC) — ``PermissionsMixin`` (direct + effective).
  [_lineage.py](pointlessql/services/unitycatalog/_lineage.py)
  (~50 LOC) — ``LineageMixin``.
  [_federation.py](pointlessql/services/unitycatalog/_federation.py)
  (~180 LOC) — ``FederationMixin`` (connections + external locations
  + credentials).

- **Test patch surface preserved.** The package
  [__init__.py](pointlessql/services/unitycatalog/__init__.py)
  re-exports every soyuz function binding at the legacy
  ``pointlessql.services.unitycatalog._xyz`` path. Tests that do
  ``patch("pointlessql.services.unitycatalog._get_tags.asyncio")``
  hit the same module object the mixin's call resolves to (Python
  module objects are singletons), so 23 patch sites in
  ``test_tags_permissions.py`` + ``test_federation.py`` work
  unchanged.

- **Renamed ``_wrap_catalog_errors`` → ``wrap_catalog_errors``.** Same
  reason the Sprint-77 kernel_session + Sprint-81 alerts + Sprint-82
  pg_sync splits dropped their leading underscores from cross-module
  helpers: pyright's ``reportPrivateUsage`` flags any access from a
  non-owning module, and the decorator is now used by every mixin.

- **MRO verified:** ``UnityCatalogClient → CatalogsMixin →
  MetadataMixin → PermissionsMixin → LineageMixin → FederationMixin
  → object``. ``isinstance(client, UnityCatalogClient)`` still works
  for every existing call site.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 4 warnings (3 pre-existing isinstance/list-typing
  patterns, unchanged), ``pydoclint`` 0 violations, ``pytest
  tests/test_tags_permissions.py tests/test_federation.py`` 23/23 +
  ``pytest tests/test_pg_sync.py tests/test_foreign_catalog.py
  tests/test_e2e.py tests/test_problem_json.py`` 60/60 passed.

### Refactored — Phase 12.9 / Sprint 82: services/pg_sync.py → 5-module package

Sixth backend split. The 778-LOC ``services/pg_sync.py`` module became
the package ``services/pg_sync/`` with five sibling modules carved
along the pipeline boundaries (introspect → diff → apply → record).

- [types.py](pointlessql/services/pg_sync/types.py) (~250 LOC) —
  dataclasses (``PgColumn``, ``PgTable``, ``PostgresSnapshot``,
  ``UcColumn``, ``UcTable``, ``SyncDiff``), the ``PG_TO_UC_TYPE`` map,
  ``map_pg_type_to_uc``, the ``PostgresIntrospector`` Protocol, plus
  the ``EXTERNAL_TABLE_TYPE`` / ``FOREIGN_DATA_SOURCE_FORMAT``
  constants (renamed from underscore-prefixed since they now travel
  cross-module).
- [dsn.py](pointlessql/services/pg_sync/dsn.py) (~80 LOC) —
  ``effective_options`` (renamed from ``_effective_options``) +
  ``build_dsn``.
- [snapshot.py](pointlessql/services/pg_sync/snapshot.py) (~95 LOC) —
  ``PsycopgIntrospector`` (the live-Postgres concrete implementation).
- [diff.py](pointlessql/services/pg_sync/diff.py) (~210 LOC) — pure
  ``diff_snapshots`` + ``collect_uc_tables`` + ``apply_diff`` plus the
  ``_columns_payload`` / ``_storage_location_stub`` helpers (still
  underscored because they remain internal to ``apply_diff``).
- [runs.py](pointlessql/services/pg_sync/runs.py) (~165 LOC) —
  ``run_sync`` end-to-end orchestration + ``list_recent_runs`` +
  ``_start_run`` / ``_finish_run`` bookkeeping.

- **Public surface preserved.** The package
  [__init__.py](pointlessql/services/pg_sync/__init__.py) re-exports
  every name the API layer
  ([pointlessql/api/main.py:51](pointlessql/api/main.py#L51)),
  scheduler
  ([pointlessql/services/scheduler.py:178](pointlessql/services/scheduler.py#L178)),
  and tests
  ([tests/test_pg_sync.py:33](tests/test_pg_sync.py#L33),
  [tests/test_scheduler.py:314](tests/test_scheduler.py#L314)) need.

- **One test rename.** ``_effective_options`` →
  ``effective_options`` in ``tests/test_pg_sync.py`` is the only
  compensation needed for the split — the production code's leading
  underscore is misleading once the symbol is imported across modules
  (same lesson the Sprint-77 kernel_session split made explicit).

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 8 warnings (all pre-existing dict-unpack patterns in
  ``collect_uc_tables``), ``pydoclint`` 0 violations,
  ``pytest tests/test_pg_sync.py`` 46/46 passed (1 deselected: live
  integration test).

### Refactored — Phase 12.9 / Sprint 81: services/alerts.py → 4-module package

Fifth backend split. The 729-LOC ``services/alerts.py`` module became
the package ``services/alerts/`` with four sibling modules + an
``__init__.py`` re-export shim. Pure structural refactor; no
schema, no migration, no behaviour change.

- **Four-bucket split** along the concern boundaries the file already
  implied:
  [crud.py](pointlessql/services/alerts/crud.py) (~340 LOC) — slug /
  serialisation / authorisation helpers, backing-Job lifecycle
  (``_sync_backing_job``), CRUD (``create_alert``, ``list_visible``,
  ``get_by_slug``, ``update_by_slug``, ``delete_by_slug``).
  [destinations.py](pointlessql/services/alerts/destinations.py)
  (~100 LOC) — ``add_destination`` + ``delete_destination``.
  [events.py](pointlessql/services/alerts/events.py) (~165 LOC) —
  ``record_event`` + ``set_event_outcome`` +
  ``list_events_for_alert`` + ``list_events_for_owner`` +
  ``prune_events_older_than``.
  [conditions.py](pointlessql/services/alerts/conditions.py) (~85 LOC)
  — pure ``evaluate_condition`` + ``build_cloudevent``.

- **Cross-module helpers de-underscored.** Renamed ``_serialize`` →
  ``serialize``, ``_serialize_destination`` → ``serialize_destination``,
  ``_can_mutate`` → ``can_mutate``: the leading underscore conveyed
  file-private scope, which is no longer accurate now that
  ``destinations.py`` imports them across modules. Same lesson the
  Sprint-77 kernel_session split made explicit. ``_sync_backing_job``
  stays underscored because it's truly internal to ``crud.py``.

- **Public surface preserved.** Existing ``from pointlessql.services
  import alerts as alerts_service`` callers (API layer line 1693,
  scheduler line 543, tests/test_alerts.py line 19) keep working
  through the package's ``__init__.py`` re-exports.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 0 warnings, ``pydoclint`` 0 violations,
  ``pytest tests/test_alerts.py`` 19/19 passed.

### Refactored — Phase 12.9 / Sprint 80: models.py → 8-module package

Fourth backend split — by far the highest-stakes mechanical refactor
of the arc. The 952-LOC ``models.py`` became the package
``pointlessql/models/`` with one module per domain. Alembic and the
32 known call sites continue to work unchanged via package-level
re-exports. Pure structural refactor; no schema, no migration, no
behaviour change.

- **Package layout.** Module order is load-bearing: SQLAlchemy
  resolves ``ForeignKey("table.col")`` strings at mapper-config time,
  so referenced tables must register before referrers.
  [base.py](pointlessql/models/base.py) (Base);
  [auth.py](pointlessql/models/auth.py) (User);
  [audit.py](pointlessql/models/audit.py) (AuditLog);
  [sync.py](pointlessql/models/sync.py) (SyncRun);
  [scheduler.py](pointlessql/models/scheduler.py) (Job, JobRun,
  JobTask, TaskRun, JobLog);
  [catalog.py](pointlessql/models/catalog.py) (Dashboard,
  QueryHistory, QueryHistoryTable, SavedQuery, TableStats,
  RateLimitEvent);
  [alerts.py](pointlessql/models/alerts.py) (Alert, AlertDestination,
  AlertEvent);
  [notebook.py](pointlessql/models/notebook.py) (NotebookOutput,
  NotebookCellRun, NotebookCellRunSource).

- **Alembic compatibility.**
  [pointlessql/alembic/env.py:6](pointlessql/alembic/env.py#L6) still
  imports ``from pointlessql.models import Base`` and resolves to the
  same metadata. Migration files reference table names (strings) not
  Python classes, so they were untouched. Smoke import confirms all
  20 tables register on ``Base.metadata`` after the split.

- **Public surface preserved.**
  [__init__.py](pointlessql/models/__init__.py) re-exports every
  symbol previously importable from ``pointlessql.models``, so the
  32 known call sites (services, API layer, tests, alembic) work
  unchanged.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 0 warnings, ``pydoclint`` 0 violations, model-touching
  test suites pass.

### Refactored — Phase 12.9 / Sprint 79: services/notebook_outputs.py → 2-module package

Third backend split. The 480-LOC ``services/notebook_outputs.py``
module became the package ``services/notebook_outputs/`` with two
sibling modules + an ``__init__.py`` re-export shim. Pure structural
refactor; no SQL, no schema, no behaviour change.

- **Two-bucket split** along the underlying-table boundary that the
  monolithic file already implied:
  [outputs.py](pointlessql/services/notebook_outputs/outputs.py)
  (~270 LOC) owns the ``NotebookOutput`` table — append-on-iopub,
  replay-on-open, plus the cross-table ``clear_*`` / ``rename_path``
  helpers that scrub output frames and cell-run lifecycle rows
  together on re-execute, restart, delete, or rename.
  [cell_runs.py](pointlessql/services/notebook_outputs/cell_runs.py)
  (~210 LOC) owns the ``NotebookCellRun`` (current state per session)
  and ``NotebookCellRunSource`` (per-execute history) tables —
  ``upsert_cell_run``, ``record_cell_run_start`` / ``_finish``,
  ``list_cell_run_sources``.

- **Public surface preserved.**
  [__init__.py](pointlessql/services/notebook_outputs/__init__.py)
  re-exports every function the API layer uses, so the lone
  external caller
  [pointlessql/api/main.py:48](pointlessql/api/main.py#L48)
  keeps working through ``notebook_outputs_service.X`` access.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 0 warnings, ``pydoclint`` 0 violations, smoke import
  OK.

### Refactored — Phase 12.9 / Sprint 78: pql/pql.py → 5 sibling helpers

Second backend split. The 461-LOC ``PQL`` module is now a 192-LOC
public-class façade plus five per-concern sibling modules.
:class:`PQL`'s methods are thin wrappers that delegate to module-level
helper functions; the orchestration shape (init → method dispatch) is
readable in one file while the per-concern logic — Delta read, DuckDB
SQL execution, Delta write + table-creation, list helpers — lives
next door.

- **New helpers** under ``pointlessql/pql/``:
  [_types.py](pointlessql/pql/_types.py) (44 LOC) carries
  ``SQLResult``;
  [_read.py](pointlessql/pql/_read.py) (64 LOC) is ``read_table()``
  (the body of ``PQL.table``);
  [_sql.py](pointlessql/pql/_sql.py) (124 LOC) is ``run_sql()`` (the
  body of ``PQL.sql`` — DuckDB connect + view registration + execute
  + row cap);
  [_write.py](pointlessql/pql/_write.py) (132 LOC) is
  ``write_table()`` + ``derive_storage_location()`` (the body of
  ``PQL.write_table``);
  [_list.py](pointlessql/pql/_list.py) (80 LOC) is ``list_catalogs``
  / ``list_schemas`` / ``list_tables``.

- **Public surface preserved.** :class:`PQL` keeps every method
  signature it had; ``SQLResult`` is re-exported from
  [pql.py](pointlessql/pql/pql.py) so existing
  ``from pointlessql.pql.pql import SQLResult`` callers (notably
  [tests/test_alerts.py:417](tests/test_alerts.py#L417)) resolve
  unchanged.

- **Tests updated, not the production code.** Added ``_READ`` /
  ``_WRITE`` / ``_LIST`` constants alongside the existing ``_MOD``
  in [tests/test_pql.py](tests/test_pql.py) and re-pointed every
  ``@patch`` to the module that now owns the symbol (e.g.
  ``_get_table`` is monkeypatched on
  ``pointlessql.pql._read`` for read tests and on
  ``pointlessql.pql._write`` for write tests). Internal mocks
  must follow the implementation when the implementation is
  intentionally split — the alternative (re-importing soyuz-client
  internals back into ``pql.py`` purely for the test surface) would
  defeat the split.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 32 warnings (all pre-existing
  ``engine.py`` polars/pyarrow untyped-arg warnings), ``pydoclint``
  0 violations, ``pytest tests/test_pql.py tests/test_alerts.py``
  51/51 passed.

### Refactored — Phase 12.9 / Sprint 77: services/kernel_session.py → package

Pilot of the backend modularization arc (Sprints 77-90). The single
472-LOC ``services/kernel_session.py`` module became the package
``services/kernel_session/`` with three sibling modules + an
``__init__.py`` re-export shim. No behaviour change, no Alembic, no
new dependencies; pure structural refactor.

- **New package layout.**
  [messages.py](pointlessql/services/kernel_session/messages.py)
  (61 LOC) carries ``KernelMessage`` and ``Subscription``
  dataclasses + the ``_SUBSCRIBER_QUEUE_MAXSIZE`` constant.
  [session.py](pointlessql/services/kernel_session/session.py)
  (337 LOC) owns the ``KernelSession`` lifecycle, ZMQ pump
  tasks, bootstrap helper code, and the
  ``_KERNEL_READY_TIMEOUT``/``_SHUTDOWN_TIMEOUT``/``_BOOTSTRAP_TIMEOUT``
  constants.
  [registry.py](pointlessql/services/kernel_session/registry.py)
  (94 LOC) owns ``KernelRegistry`` + the ``drain`` async iterator.

- **Public surface preserved.** The lone external caller
  [pointlessql/api/main.py:45](pointlessql/api/main.py#L45)
  imports the module as ``kernel_session_service`` and accesses
  ``KernelRegistry``, ``KernelMessage``, ``KernelSession``,
  ``drain`` through that namespace. The new
  [__init__.py](pointlessql/services/kernel_session/__init__.py)
  re-exports the full surface so the import resolves unchanged.
  No tests directly import this module.

- **Renamed ``_Subscription`` → ``Subscription``.** The leading
  underscore conveyed file-private scope, which is no longer
  accurate now that ``KernelSession`` imports it across modules.
  Pyright's ``reportPrivateUsage`` rule flagged this immediately
  on the first split attempt.

- **Static gates (all green):** ``ruff`` 0 errors, ``pyright``
  0 errors / 5 warnings (all from ``jupyter_client``'s partially-
  unknown async types — pre-existing), ``pydoclint`` 0 violations,
  smoke import via ``python -c "from pointlessql.services import
  kernel_session"``.

### Refactored — Phase 12.9 / Sprint 76: notebook/main.js → 4 sub-modules + toast helper

Follow-up to Phase 12.8.  Four sibling modules carved out of
notebook/main.js and a cross-cutting toast-guard cleanup across
sql_editor.js, notebook/main.js, and notebook/editor_shell.js.  No
behaviour change, no Alembic, no template-structure change; pure JS
refactor.

- **Notebook main.js split.**
  [main.js](frontend/js/notebook/main.js) drops 1204 → 703 LOC
  (-501).  Four new sibling modules:
  [kernel_ws.js](frontend/js/notebook/kernel_ws.js) (211 LOC) owns
  the ipykernel socket + frame routing;
  [lsp_ws.js](frontend/js/notebook/lsp_ws.js) (133 LOC) owns the
  pyright socket + didOpen + notifyDidChange;
  [cell_scanner.js](frontend/js/notebook/cell_scanner.js) (41 LOC)
  holds pure scanCellRanges + rangesToDecorations;
  [cell_editor.js](frontend/js/notebook/cell_editor.js) (104 LOC)
  holds insertCellAfter + addCellBelow + addCellAbove +
  applyResultVarToMarker.  main.js now owns orchestration glue +
  rebuildCellAffordances + save + catalog-insert only.

- **Toast-guard cleanup (Tranche 7).**
  [api.js](frontend/js/api.js) exports ``toast(variant, msg)`` and
  ``csrfToken()`` as named exports.  14 ``if (window.pqlToast)
  window.pqlToast.X(msg)`` guards in
  [sql_editor.js](frontend/js/sql_editor.js),
  [notebook/main.js](frontend/js/notebook/main.js), and
  [notebook/editor_shell.js](frontend/js/notebook/editor_shell.js)
  replaced with single-line ``toast('error', msg)`` calls.  The
  helper no-ops when the singleton is missing, so call-sites read
  top-down without branch noise.  Duplicate ``csrfToken()`` removed
  from notebook/main.js.

- **Cache-bust bumped** to ``?v=sprint76`` on the
  [notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  bootstrap script tag so browsers pick up the new ESM import graph
  without a hard reload.

- **Deferred to a follow-up sprint:** ``mount_bootstrap.js`` split
  (mount() is tightly coupled to ``this`` + the Alpine factory return
  object; extracting it means refactoring the factory shape, not a
  mechanical move).  Captured in the tranche plan at
  ``~/.claude/plans/wir-haben-in-diesem-warm-dream.md``.

- **Static gates (all green):** ``ruff``, ``pyright`` (0 errors),
  ``pydoclint``,
  [check-frontend-bootstrap-order.sh](scripts/check-frontend-bootstrap-order.sh),
  [check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh),
  ``node --check`` on every modified JS file, import-graph resolution
  check, Jinja template parse.

### Refactored — Phase 12.8 / Sprint 75: Frontend cleanup (notebook carve-up + ESM-everywhere + CSS-split + CSRF + README)

One-shot reorg sprint that clears the JS / CSS organisation debt
before Phase 13 starts.  No new feature; no behaviour change beyond
the latent CSRF fix.  Six commits, one per phase, all on main.

- **Phase 1 — notebook/main.js carve-up** (247e271).
  [main.js](frontend/js/notebook/main.js) drops 1547 → 1204 LOC.
  Five new sibling modules:
  [output_zone_manager.js](frontend/js/notebook/output_zone_manager.js),
  [cell_introspector.js](frontend/js/notebook/cell_introspector.js),
  [autosave_scheduler.js](frontend/js/notebook/autosave_scheduler.js),
  [commands.js](frontend/js/notebook/commands.js); plus
  ``createOutlineRecomputer`` factory in
  [outline.js](frontend/js/notebook/outline.js).  Grep gate
  [check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
  extended with the new closure-state slot names.

- **Phase 2 — ESM bridge entrypoint** (87f03a7).  New
  [frontend/js/bootstrap.js](frontend/js/bootstrap.js) loaded as
  ``<script type="module">`` from
  [base.html](frontend/templates/base.html) before the Alpine CDN
  script.  New CI gate
  [check-frontend-bootstrap-order.sh](scripts/check-frontend-bootstrap-order.sh)
  asserts the script-tag ordering.

- **Phase 3 — editor_base + small editors to ESM** (410f144).  New
  [editor_base.js](frontend/js/editor_base.js) exports
  ``validateRequired`` and ``createDictEditor``; four inline editors
  migrated to native ES modules.

- **Phase 4 — federation / list_table / sql_editor / helpers to ESM**
  (2d9e1e2).  Last legacy files migrated.  Removed all 11 individual
  ``<script src="/static/js/X.js">`` tags from base.html +
  sql_editor.html — only bootstrap.js + Alpine + vendor CDN scripts
  load via raw ``<script>`` now.

- **Phase 5 — CSRF in pqlApi + frontend README** (a5a7a20).
  ``pqlApi.fetch`` now injects ``X-CSRF-Token`` for non-safe verbs.
  New [frontend/js/README.md](frontend/js/README.md) documents the
  post-Sprint-75 conventions.

- **Phase 6 — style.css split** (e0ae139).  1066-line single file
  carved into ten purpose-scoped sheets that the master
  [style.css](frontend/css/style.css) ``@import``s in cascade order:
  base / primitives / layout / responsive plus six under
  components/.

Hard constraints honoured: no build step, no bundler, no
``package.json``.  Static gates green: ruff, pyright, alembic,
``node --check`` on every modified file, both frontend grep gates.

### Fixed — Phase 12.7 tail: BUG-71-02 + BUG-72-01 root fix + replay completion

Closing audit pass on the Phase-12.7 sprints surfaced two bugs
the in-sprint replays missed; both fixed in a single follow-up
commit.

**BUG-71-02 — server-side notebook_doc dropped the [sql] tag +
result_var on round-trip.**  Sprint 71's frontend correctly
emitted ``# %% [sql] pql_cell_id="…" result_var="…"`` markers,
but the server-side
[notebook_doc.py](pointlessql/services/notebook_doc.py) used
jupytext for both load and save; jupytext only recognises
``[markdown]`` as a cell-type tag — anything else (``[sql]``,
``[raw]``, …) is silently dropped from the marker line, and the
cell is parsed as a plain code cell.  The ``result_var`` segment
was equally invisible.  Saving was rejected outright by the
server validator (``cell_type='sql'`` not in the allow-list).
Result: editor showed SQL cells as code cells on reload, autosave
silently failed for SQL cells.  Fix:

- Extended ``NotebookCell`` with ``result_var: str | None``.
- Added module-level ``_PQL_MARKER_RE`` mirroring the
  client-side ``CELL_MARKER_RE`` in
  [cell_parser.js](frontend/js/notebook/cell_parser.js).
- ``load_document`` post-parses the raw .py file with the regex
  to recover ``[sql]`` tags + ``result_var`` segments and
  overrides the cell type jupytext returned.
- ``save_document`` post-writes via a new ``_rewrite_sql_markers``
  helper that rewrites code-cell markers for SQL cells back to
  ``# %% [sql] pql_cell_id="…" result_var="…"``.
- ``api_save_notebook_doc`` accepts ``cell_type='sql'`` + reads
  optional ``result_var``.
- ``api_load_notebook_doc`` includes ``result_var`` in the
  bundle for every cell.
- [main.js](frontend/js/notebook/main.js) normalises
  ``result_var`` ↔ ``resultVar`` at the wire boundary on both
  load and save so the rest of the JS-side cell shape stays in
  one consistent form.

**BUG-72-01 root fix.**  The Sprint-72 commit's "workaround"
claim — that bumping bootstrap.js's ``?v=`` query busts the
inner ESM imports — was wrong; that param only invalidates
bootstrap.js itself, not the dynamically-imported siblings.  Real
fix: a new HTTP middleware
[``static_module_revalidate_middleware``](pointlessql/api/main.py)
stamps ``Cache-Control: no-cache, must-revalidate`` on every
``/static/js/notebook/*`` response, so the browser must issue a
conditional ``If-Modified-Since`` request next time.  Starlette's
StaticFiles answers 304 when unchanged (cheap); a sprint-fresh
module is delivered immediately on the next page load — no
hard-reload needed.  Sprint 72's "What the replay caught"
section in
[docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
is also corrected to reflect the real fix.

**Replay completion** for the Sprint-71 / -72 / -73 / -74
playbook steps that the in-sprint walkthroughs had skipped (L6,
L7, L8, L9, M1-M5, N6, N7, N8, O3, O5, O6).  Documented in the
new "Phase 12.7 tail" block at the end of
[notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md).

### Added (Sprint 74) — Phase 12.7: Settings drawer + keymap overlay + phase close

Tenth and final Phase 12.7 sprint.  Settings drawer (theme,
font-size, autosave-debounce knob), ``Ctrl+Alt+/`` keymap overlay
listing every editor command, four new ``pql.*`` palette actions,
and the Phase-12.7 ROADMAP node flips ``⏳ open`` → ``✅ done``.

- [frontend/js/notebook/settings_drawer.js](frontend/js/notebook/settings_drawer.js)
  — new module.  Bootstrap offcanvas with ``Theme`` (``vs-dark`` /
  ``vs`` / ``hc-black``), ``Font size`` (10-22 px), ``Autosave
  debounce`` (200-2000 ms).  Persists to localStorage under
  ``pql.nbedit.theme.v1`` / ``pql.nbedit.fontSize.v1`` /
  ``pql.nbedit.autosave.debounceMs.v1``; broadcasts a
  ``pql:settings-changed`` ``CustomEvent`` on ``document`` so
  every open tab's editor re-applies via
  ``monaco.editor.setTheme`` (page-global) +
  ``editor.updateOptions({fontSize})`` (per-instance) + a
  ``_autosaveDebounceMs`` closure mutation.
- [frontend/js/notebook/keymap_overlay.js](frontend/js/notebook/keymap_overlay.js)
  — new module.  Static 15-row commands array (Sprint 62 +
  70 + 73 + 74 additions), Bootstrap modal renderer reachable via
  the ``?`` toolbar button, the ``Ctrl+Alt+/`` keybind, and the
  ``pql.openKeymap`` palette action.  ``Ctrl+/`` left bound to
  Monaco's default ``toggle-line-comment`` to avoid shadowing the
  editor convention.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — applies ``loadSettings()`` on Monaco create; lifts
  ``_autosaveDebounceMs`` out of module scope so
  ``scheduleAutosave`` reads it at flush-queue time;
  ``registerPaletteActions`` extended with
  ``pql.toggleOutline`` / ``pql.openHistory`` /
  ``pql.openSettings`` / ``pql.openKeymap`` (last is also bound to
  ``Ctrl+Alt+/``); new Alpine methods ``openSettings`` /
  ``openKeymap`` / ``openHistoryForCurrentCell``.
- [frontend/js/notebook/bootstrap.js](frontend/js/notebook/bootstrap.js)
  — extended the tab-scope stub with ``outlineVisible`` /
  ``outline`` and the four new method names so the pre-mount
  window no longer raises ``ReferenceError`` on Alpine
  ``x-show`` / ``@click`` expressions.  Cleaned up the
  Sprint-72-era console-noise tail.
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — gear (⚙) + ``?`` toolbar buttons; bootstrap.js script tag
  bumped to ``?v=sprint74``.

**BUG-74-01 (replay-caught + fixed in same commit):** double-
backticks inside an HTML template literal in
``buildModal`` (the GitHub-flavoured-markdown-style ``\`\`pql.*\`\```
text in the modal footer) terminated the backtick-quoted string
early, raising a ``SyntaxError`` inside ``buildModal`` the moment
``mountKeymapOverlay`` called it.  Symptom: ``mount()`` caught the
error generally; settings drawer mounted (earlier in the flow)
but keymap overlay never materialised, and the per-cell
affordances never rebuilt.  Fix: replaced the markdown backticks
with plain ``pql.*`` text.  Caught pre-gate via a cache-busted
dynamic ``import()`` that surfaced the real
``buildModal@keymap_overlay.js:137:18`` stack trace.

**Phase 12.7 closed.**  Ten sprints (65-74) transformed the
notebook editor from the Sprint-58 single-file monolith into a
modular, multi-tab, multi-cell-type, audit-trailed surface.
Phase 13 (Agent workloads) is next on the roadmap with the
EXPLAIN-agent loop sketched as the natural Phase-12 → Phase-13
bridge.

No Alembic migration.  Trim-safe.

### Added (Sprint 73) — Phase 12.7: Per-cell run history + diff (Alembic 018)

Ninth Phase 12.7 sprint.  Adds an audit trail of every cell
execute_request — source snapshot + lifecycle status + timestamps
+ ``execution_count`` — and a per-cell history popover with
``view diff`` against current Monaco source and a ``re-run``
button that replays the historical source through the kernel
without modifying the Monaco buffer ("what did the old version
produce?" UX, not "revert to this").

**Schema (Alembic 018).** New ``notebook_cell_run_sources`` table
with autoincrement id PK; sibling to the Sprint-60
``notebook_cell_runs`` upsert (which keeps "current state per
session" and would otherwise clobber the prior run on every
re-execute).  No FK to ``notebook_cell_runs`` — link is logical
via the indexed columns; cascade lives in
``notebook_outputs.py`` service (Sprint-67 cascade-via-service
pattern) on file delete + rename only.  ``clear_cell`` and
``clear_session`` deliberately do NOT touch the history table —
the audit trail explicitly survives both per-cell clear-outputs
and kernel restarts.

- [pointlessql/alembic/versions/018_notebook_cell_run_sources.py](pointlessql/alembic/versions/018_notebook_cell_run_sources.py)
  — new migration; ``ix_notebook_cell_run_sources_path_cell`` on
  ``(file_path, cell_id, started_at)``.
- [pointlessql/models.py](pointlessql/models.py) — new
  ``NotebookCellRunSource`` ORM model.
- [pointlessql/services/notebook_outputs.py](pointlessql/services/notebook_outputs.py)
  — ``record_cell_run_start`` (insert + return id),
  ``record_cell_run_finish`` (stamp by id),
  ``list_cell_run_sources`` (newest-first JSON-ready dicts).
- [pointlessql/api/main.py](pointlessql/api/main.py)
  — ``pending_run_sources`` map keyed by ``(cell_id,
  kernel_session_id)``; ``_wipe_cell_for_new_execute`` calls
  ``record_cell_run_start`` and stashes the returned id;
  ``_handle_shell_lifecycle`` pops the id on ``execute_reply`` and
  calls ``record_cell_run_finish``.  New admin-gated
  ``GET /api/notebook/cell-runs?path=…&cell_id=…&limit=…``.
- [frontend/js/notebook/run_history.js](frontend/js/notebook/run_history.js)
  — new module.  Closure-scoped popover + cache + AbortController.
  Re-run sends the historical source via the existing ``execute``
  WS frame (NOT ``execute_sql``, since SQL history rows already
  hold the wrapped ``__pql_sql_run(...)`` snippet — re-running
  executes the same SQL without re-walking the route's privilege
  check).  Does NOT touch Monaco.
- [frontend/js/notebook/cell_affordances.js](frontend/js/notebook/cell_affordances.js)
  — clock-icon ``.pql-nbedit-history-btn`` mounted on every
  ``canExecute`` cell; ``handlers.onShowHistory(cellId, anchorEl)``
  threaded through ``mountAffordances``.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — ``openHistoryPopover(cellId, anchorEl)`` reads current source
  via ``cellSourceById`` for diffing.
- [scripts/vendor-diff-lib.sh](scripts/vendor-diff-lib.sh)
  — new vendoring script for jsdiff 5.2.0 (npm ``diff``, MIT,
  ~10 KB UMD ``window.Diff``).
- [.gitignore](.gitignore) — added
  ``frontend/js/vendor/jsdiff/``.
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — ``<script src="/static/js/vendor/jsdiff/diff.min.js?v=sprint73">``
  tag; bootstrap.js bumped to ``?v=sprint73``;
  ``.pql-nbedit-history-btn`` / ``.pql-nbedit-history-popover`` /
  ``.pql-nbedit-diff`` styles.
- [scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
  — widened forbidden pattern to cover ``this._historyCache`` /
  ``this._historyPopover`` / ``this._historyAbort``.
- [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  — Playbook **Part N** added; replayed in Firefox via
  Playwright-MCP as the land gate.

**BUG-73-01 (replay-caught + fixed in same commit):** the first
version of the service threaded ``NotebookCellRunSource`` deletes
through the ``clear_cell`` cascade alongside ``NotebookOutput``
and ``NotebookCellRun``.  But ``clear_cell`` is called from
``_wipe_cell_for_new_execute`` at the top of every execute_request,
so the cascade meant every re-run deleted the prior run's row
before ``record_cell_run_start`` inserted its own — only the
most-recent run ever existed in the history table.  Fix: removed
the ``NotebookCellRunSource`` delete from ``clear_cell`` AND
``clear_session``; cascade now lives only in ``clear_path`` (file
delete) and ``rename_path`` (file rename).  Caught at the N2 step
on the first replay (DB query showed exactly one row even after
three runs).

Trim-safe — Sprint 74 (theme + keymap + phase close) does not
import the run-history module; revert is sprint-local.

### Added (Sprint 72) — Phase 12.7: ipywidgets minimal placeholder

Eighth Phase 12.7 sprint.  Scope deliberately trimmed to a
placeholder layer; full bidirectional ``comm_msg`` round-trip +
vendored widget-manager bundle deferred to a future sprint per the
Phase-12.7 master-plan decision.  ``import ipywidgets as w`` now
works in the kernel, and the output renderer paints a styled
placeholder card whenever a ``display_data`` /
``execute_result`` carries
``application/vnd.jupyter.widget-view+json`` — the user sees
where the slider / dropdown WOULD live once a future sprint wires
the widget-manager.

- [pyproject.toml](pyproject.toml) — added ``ipywidgets>=8.1`` to
  the dependency list; ``uv lock`` resolved
  ``ipywidgets-8.1.8`` + ``jupyterlab-widgets-3.0.16`` +
  ``widgetsnbextension-4.0.15``.
- [frontend/js/notebook/output_renderer.js](frontend/js/notebook/output_renderer.js)
  — new high-priority MIME branch in ``renderMimeBundle``.  Must
  come BEFORE ``text/html`` so the widget bundle wins over the
  fallback ``text/plain`` repr (every ipywidgets ``execute_result``
  carries both).  Renders a ``.pql-nbedit-output-widget-placeholder``
  card with truncated ``model_id`` + disclaimer.  Missing
  ``model_id`` falls back to ``Widget output (unrenderable)``.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — ``renderKernelMsg`` silently swallows ``comm_open`` /
  ``comm_msg`` / ``comm_close``.  No console log: a single
  ``IntSlider()`` instantiation emits dozens of comm frames and
  logging would flood DevTools.
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — ``.pql-nbedit-output-widget-placeholder`` +
  ``.pql-nbedit-widget-model-id`` + ``.pql-nbedit-widget-note``
  styles; bootstrap.js script tag bumped to ``?v=sprint72``.
- [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  — Playbook **Part M** added with synthetic + real-widget +
  comm-swallow + missing-``model_id`` + persist/replay steps.
  Renderer verified end-to-end via a cache-busted
  ``import('/static/js/notebook/output_renderer.js?_t=' + Date.now())``
  because of BUG-72-01 below.

**BUG-72-01 — ES module disk cache hides new mime branches.**  The
notebook editor's [bootstrap.js](frontend/js/notebook/bootstrap.js)
carries a ``?v=sprintNN`` query param so its own ``<script>``
invalidates, but the modules it dynamically imports
(``editor_shell.js`` + ``main.js`` + the eight siblings,
including ``output_renderer.js``) do not carry a version param, so
the browser keeps the previous deploy's modules in disk cache.
Workaround for this sprint: bumped bootstrap.js to ``?v=sprint72``
and documented the hard-reload requirement (``Ctrl+Shift+R``) in
Part M.  Permanent fix is a follow-on sprint that threads a build-
time version stamp into every dynamic import URL — out of scope
here.

No Alembic migration.  Trim-safe — the placeholder branch is the
upgrade seam a future sprint will replace with a real widget-
manager.  No closure state added, so the reactivity-boundary grep
gate is unchanged.

### Added (Sprint 71) — Phase 12.7: SQL cell (DuckDB via PQL.sql)

Seventh Phase 12.7 sprint.  Adds the first non-Python cell type and
validates Sprint 66's cell-type registry as the right seam for new
languages.  Marker grammar widens to
``# %% [sql] pql_cell_id="<uuid>" result_var="<ident>"``; the
``result_var`` segment is optional (Databricks-style — picked over
the originally-sketched ``_pql_sql_<short-uuid>`` auto-generator
to keep chained-cell readability).  ``runCellById`` branches on the
new ``sql`` descriptor and emits an ``execute_sql`` WS frame; the
route handler parses + privilege-checks every 3-part reference
against soyuz-catalog (mirrors ``/api/sql/execute``'s SELECT loop
via the new shared ``_resolve_sql_approved_tables`` helper) before
wrapping the source into a ``__pql_sql_run(...)`` snippet that runs
in the kernel.  The kernel-side helper, defined once at start time
via ``_NOTEBOOK_BOOTSTRAP_CODE`` (silent execute_request awaited
before the iopub / shell pump tasks start so SQL runs cannot race
the helper definition), calls ``PQL.sql`` for real, materialises
the result as a pandas DataFrame, optionally binds it to the user-
named ``result_var`` in ``globals()`` for Variable Explorer to
surface, and ``display(df)`` so the Sprint-60 rich-mime path
renders the table inline.  Restart re-queues the bootstrap via the
existing execute path under reserved cell_id
``__pql_sql_bootstrap__`` so ``_is_internal_cell`` skips
persistence.

- [frontend/js/notebook/cell_types.js](frontend/js/notebook/cell_types.js)
  — registered ``sql`` descriptor (``markerTag: ' [sql]'``,
  ``canExecute: true``, ``bandClass: 'pql-nbedit-cell-band-sql'``,
  ``affordances: ['result_var']``).
- [frontend/js/notebook/cell_parser.js](frontend/js/notebook/cell_parser.js)
  — widened ``CELL_MARKER_RE`` to capture optional
  ``result_var="<ident>"`` (group 3); ``splitCells`` /
  ``joinCells`` round-trip the field; ``RESULT_VAR_RE`` exported
  for the affordance validator.
- [frontend/js/notebook/cell_affordances.js](frontend/js/notebook/cell_affordances.js)
  — per-cell ``result_var`` text input (300 ms debounce write-back,
  CSS error class on invalid identifiers); ``+ SQL`` inserter
  button alongside ``+ Code`` / ``+ Markdown``;
  ``removeAffordances`` clears the debounce on cell teardown.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — ``runCellById`` branches on ``typeId === 'sql'`` and emits
  ``execute_sql``; ``runAllCells`` / ``runCellsAbove`` share the
  new ``sendCellFrame`` helper; ``cellResultVarById`` reads the
  marker; ``applyResultVarToMarker`` writes back via
  ``editor.executeEdits`` so on-disk text stays the source of
  truth.
- [pointlessql/api/main.py](pointlessql/api/main.py)
  — new ``execute_sql`` WS branch; shared
  ``_resolve_sql_approved_tables`` helper that returns either
  ``(approved, None)`` or ``({}, error_dict)`` so the WS handler
  can ship a synthetic kernel_msg straight to the cell's output
  zone on parse / catalog / privilege failures; refactored
  ``_wipe_cell_for_new_execute`` to share the persistence prelude
  with the existing ``execute`` branch.
- [pointlessql/services/kernel_session.py](pointlessql/services/kernel_session.py)
  — ``_NOTEBOOK_BOOTSTRAP_CODE`` defines ``__pql_sql_run`` in the
  kernel; ``_run_bootstrap`` runs it silently with a
  ``_BOOTSTRAP_TIMEOUT`` safety net; ``restart`` re-queues the
  bootstrap via the regular execute path under reserved cell_id
  ``__pql_sql_bootstrap__``.
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — ``.pql-nbedit-cell-band-sql`` band hue + ``.pql-nbedit-result-var``
  input styling.
- [scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
  — widened forbidden pattern to cover ``this._resultVarTimers``
  / ``this._sqlBootstrap``.
- [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  — Playbook **Part L** added; replayed in Firefox via
  Playwright-MCP as the land gate per
  ``feedback_run_playbook_as_gate``.  Replay caught BUG-71-01:
  pandas's ``DataFrame.__repr__`` raised ``TypeError`` because
  ``SQLResult.columns`` is ``list[dict[str, str]]``, not bare
  names; fix in the same commit extracts the names with
  ``[c.get("name") if isinstance(c, dict) else c for c in
  res.columns]`` before constructing the DataFrame.

No Alembic migration.  Trim-safe — Sprints 72-74 do not import the
SQL cell.

### Added (Sprint 70) — Phase 12.7: Outline / TOC panel + cell jump

Sixth Phase 12.7 sprint.  Adds a right-side Outline panel that peers
with the Variable Explorer (mutually exclusive, same 320px slot,
same chrome).  Lists markdown H1/H2/H3 ATX headings (indented per
level) and each code cell's first non-blank stripped line
(truncated to ~60 chars).  Clicking a row jumps Monaco to the
cell's first content line and scrolls it to the viewport centre
via ``editor.revealLineInCenter`` + ``editor.focus``.

- **New module** [frontend/js/notebook/outline.js](frontend/js/notebook/outline.js)
  — pure ``buildOutline(cells)`` regex helper + ``stripCodeLabel``.
  No markdown-it dependency (dodges the Sprint-69 UMD/AMD
  loader-order class, BUG-69-01).  No closure state — re-entrant,
  idempotent.
- [frontend/js/notebook/main.js](frontend/js/notebook/main.js)
  — closure-scoped ``outlineEntries`` + 150ms debounce timer;
  mirrored into reactive ``this.outline`` as a fresh array on
  every change so Alpine's x-for diffs once per real edit.
  ``toggleOutline()`` mutually excludes with ``toggleVariables()``.
  ``jumpToCell(cellId)`` reuses ``findCellMarkerLine`` verbatim
  and adds ``revealLineInCenter`` + ``focus``.  Recompute
  re-splits from the live Monaco model
  (``splitCells(model.getValue())``) rather than reading the
  closure-scoped ``cells`` array — ``cells`` is only refreshed on
  save / ``rescanDecorations``, so free-form typing inside a cell
  would have left the outline stale (BUG-70-01, replay-caught).
- [frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)
  — ``Outline`` toolbar button between Variables and Run cell;
  right-side ``<aside class="pql-nbedit-outline">`` mirroring the
  Variables aside; inline CSS for per-level indent classes
  (``.pql-outline-l1`` / ``-l2`` / ``-l3`` / ``-code``).
- [scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
  — widened forbidden list to cover ``this._outlineEntries``,
  ``this._outlineTimer``, ``this._outlineDebounce`` so a future
  change cannot regress by parking the 150ms debounce handle on
  Alpine's proxy (its captured closure holds the live ``cells``
  array; Alpine's reactive walk would recurse — exactly the
  BUG-64-02 shape).
- [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  — Part K replay added with 7 numbered steps + known-quirks
  section + bug-catch write-ups for BUG-70-01 (stale closure
  ``cells``) and BUG-70-02 (over-stripping jupytext prefix
  double-shifted heading levels).

**No Alembic migration.**  Pure frontend, no backend change, no
persisted state (open/closed panel is session-only).  Trim-safe
per the Phase 12.7 roadmap — nothing downstream depends on
``outline.js`` or ``this.outline``; revert is O(1) sprint-local.

### Added (Sprint 69) — Phase 12.7: markdown-it + KaTeX + pencil pin

Fifth Phase 12.7 sprint.  Replaces the Sprint-65 regex markdown
preview renderer with ``markdown-it`` (CommonMark-conformant —
tables, nested lists, task lists, autolinking), layers KaTeX for
``$…$`` / ``$$…$$`` math via ``markdown-it-texmath``, and adds a
per-cell pencil button that pins a markdown cell into source view
independently of cursor position.

- **Vendored bundles** ([scripts/vendor-markdown-libs.sh](scripts/vendor-markdown-libs.sh)
  — new).  Fetches markdown-it 14.1.0, markdown-it-texmath 1.0.0,
  and KaTeX 0.16.11 from the npm registry into gitignored dirs
  under ``frontend/js/vendor/``.  Mirrors the Monaco vendoring
  pattern from ADR 0001.  Appends a ``window.texmath = texmath``
  line to the vendored ``texmath.js`` because the package ships
  CommonJS-only.
- **Renderer swap** ([frontend/js/notebook/markdown.js](frontend/js/notebook/markdown.js)).
  Exported signature unchanged — ``renderMarkdown(src) → string`` —
  so the single call site in ``main.js`` stays untouched.  Cached
  markdown-it instance lives in a module-scoped ``let`` (closure,
  not Alpine proxy); KaTeX registration is a single ``.use(...)``
  line, layer-droppable without touching the rest of the module.
- **Pencil-pin affordance** ([frontend/js/notebook/cell_affordances.js](frontend/js/notebook/cell_affordances.js),
  [frontend/js/notebook/cell_types.js](frontend/js/notebook/cell_types.js),
  [frontend/js/notebook/main.js](frontend/js/notebook/main.js)).
  Markdown descriptor gains ``affordances: ['pin']``; the toolbar
  renders a ``bi-pencil`` button right of the cell-type label on
  cells whose descriptor opts in.  Click toggles
  ``markdownZones[cellId].editModePinned`` (closure-scoped,
  session-only — no marker grammar changes, no ADR 0001 churn);
  pinned cells stay unhidden by ``updateHiddenAreas`` regardless
  of cursor position.  A rebuild re-syncs the pencil state so a
  content edit does not desync the icon.
- **Template wiring** ([frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)).
  KaTeX CSS link added; three UMD script tags (markdown-it,
  katex, texmath) load **before** ``monaco/vs/loader.js`` so
  their UMD wrappers fall through to the plain-script branch
  (BUG-69-01 replay-caught).  New CSS rules for the pencil
  button + markdown-it tables / nested lists / blockquotes /
  KaTeX blocks.  ``bootstrap.js`` cache bust bumped to
  ``?v=sprint69``.
- **Reactivity-boundary gate widened** ([scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh))
  to block ``this._mdSingleton`` / ``this._mdPinState`` /
  ``this._pinHandlers``.  markdown-it's rule registries are
  exactly the kind of deep-circular object that Alpine's
  reactive walk would wrap and traverse on every re-render —
  same BUG-64-02 class of bug, pre-empted.
- **Playbook Part J** ([docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md))
  — ten-step walkthrough (CommonMark table, nested lists, inline
  KaTeX, block KaTeX, pin keeps source visible, unpin collapses,
  session-only reset, code cells have no pencil, KaTeX drop-
  sanity, earlier-sprint regression pass).

### Fixed (Sprint 69 replay catch)

- **BUG-69-01 — UMD vs AMD loader-order collision.**  The first
  Part-J replay loaded ``markdown-it.min.js`` and ``katex.min.js``
  after ``monaco/vs/loader.js``.  Both scripts ship UMD wrappers
  that detect Monaco's ``window.define`` and register as anonymous
  AMD modules, colliding with Monaco's "one anonymous define per
  script file" contract.  Fixed by loading the three markdown
  vendor scripts **before** Monaco's loader, so ``window.define``
  does not yet exist when their UMD wrappers execute and they
  bind to ``window.markdownit`` / ``window.katex`` as globals.
  The template now documents the ordering rationale inline.

### Added (Sprint 68) — Phase 12.7: multi-notebook tab bar

Fourth Phase 12.7 sprint.  Adds a tab bar above the editor so the
user can keep several notebooks open in one page and switch
between them without a reload.  Each tab hosts its own Monaco
editor + kernel WS + LSP WS; the Sprint-65 closure-ref factory is
already N-instance-safe and the Sprint-66 affordance machinery is
editor-scoped, so tab switches are a CSS ``display`` flip rather
than a Monaco teardown.

- **Tab bar** ([frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html)).
  New ``.pql-nbedit-tabbar`` above the layout; each tab shows the
  file basename, a dirty dot (``•``) when the buffer is unsaved,
  and a close button.  Horizontal-scroll overflow; no dropdown
  overflow menu.  Soft-cap at 10 tabs — the eleventh open toasts
  ``Tab limit reached``.  The Files-sidebar toggle moved from the
  per-tab toolbar to the tab-bar's right side (the sidebar is
  shell-scoped, not tab-scoped).
- **Editor shell factory** ([frontend/js/notebook/editor_shell.js](frontend/js/notebook/editor_shell.js)
  — new module).  Alpine factory ``createNotebookEditorShell``
  owns tabs + activeTabId + the close-confirm modal + the file-
  tree sidebar slice + localStorage persistence (``pql.nbedit.
  tabs.v1``).  Listens on ``document`` for ``pql:open-tab`` /
  ``pql:file-renamed`` / ``pql:file-deleted`` /
  ``pql:tab-state-changed`` — the sidebar and the per-tab scopes
  talk to the shell through this bus rather than via cross-scope
  reference walking.
- **Per-tab factory split** ([frontend/js/notebook/main.js](frontend/js/notebook/main.js)).
  Renamed ``createNotebookEditor`` → ``createNotebookTabEditor``;
  added optional ``tabId`` / ``initial`` / ``bundleLoader`` args.
  Cell + output initialisation moved inside ``mount()`` so lazy
  tabs defer network + Monaco work until first activation.  The
  factory dispatches ``pql:tab-state-changed`` for ``mounted`` /
  ``dirty`` / ``saveState`` transitions so the tab chrome stays
  in sync without reaching into the child proxy.
- **GET /api/notebook/doc** ([pointlessql/api/main.py](pointlessql/api/main.py)).
  The only backend change — a small read-only endpoint returning
  the same ``{cells, dirty, outputs}`` bundle the HTML editor
  route embeds.  Shared helper ``_build_notebook_doc_bundle``
  wraps ``notebook_doc_service.load_document`` +
  ``notebook_outputs_service.load_outputs_for_path``; the HTML
  route and the new JSON route call it identically, so first-
  paint and lazy-load can never drift.  (Roadmap line originally
  said "No backend changes"; amended with this deviation note.)
- **Sidebar API reshape** ([frontend/js/notebook/file_tree.js](frontend/js/notebook/file_tree.js)).
  ``createFileTreeSlice`` now takes ``getActivePath`` +
  ``isPathOpenInAnyTab`` callbacks instead of a static
  ``currentPath``.  Row-click / create / rename / delete dispatch
  CustomEvents on ``document`` instead of calling
  ``window.location.assign`` — the shell orchestrates tab state.
  Trash-disable now covers *any* open tab, not just the active
  one.
- **Reactivity-boundary gate widened** ([scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh))
  to block ``this._tabRefs`` and ``this._tabFactories``.  A
  shell that aggregates per-tab closure bags onto its Alpine-
  reactive ``this._`` would reproduce BUG-64-02 at N× scale.
- **Close-tab-with-unsaved-changes modal**.  Bootstrap dialog
  with Cancel / Discard & close / Save & close; reuses the
  Sprint-67 ``:class="{'d-block': flag}"`` pattern (BUG-67-01).
  Save & close dispatches ``pql:save-tab`` and waits for the
  child factory's next ``saveState`` emission before closing;
  if the save errors, the modal stays open and surfaces via the
  per-tab save toast.
- **Playbook Part I** ([docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md))
  — eleven-step multi-tab walkthrough (first open, row-click
  opens second tab lazily, cross-tab state preservation, dirty
  dot, close-clean / close-dirty / confirm-modal, reload
  persistence + lazy hydration, kernel sharing, rename updates
  chrome in place, delete closes tab silently, ten-tab cap
  toast).

### Fixed (Sprint 68 replay catch)

- **Tab-mounted flag lost during stub→real scope swap.**  The
  bootstrap stub seeded ``tabs = [seedTab]`` synchronously with
  ``mounted: false``; the template's ``x-init="tab.mounted = true;
  mount()"`` set the flag on the seed, but the async import of
  ``editor_shell.js`` + ``_hydrateTabs()`` replaced the tabs array
  wholesale — the flag was dropped on the floor.  Alpine's
  ``:key="tab.id"`` diff reused the DOM element so x-init did not
  re-fire, leaving ``tab.mounted: false`` on the live tab.  Net
  effect: opening a second tab made the first tab's ``x-if``
  (``tab.mounted || active``) evaluate false, Alpine unmounted
  the pane, Monaco + kernel were torn down mid-session.  Fixed
  by having the per-tab factory fire
  ``pql:tab-state-changed { mounted: true }`` **synchronously**
  at the top of ``mount()``, before any async Monaco / kernel /
  LSP work; the shell's listener updates ``tab.mounted`` in the
  tabs array so the x-if lazy-mount wrapper stays true through
  subsequent tab switches.

### Added (Sprint 67) — Phase 12.7: file-tree sidebar inside the editor

Third Phase 12.7 sprint.  Mounts the Sprint-27 workspace tree as a
slim left sidebar in ``/notebook/editor`` and closes the long-
deferred notebook create / rename / delete actions from Sprint 27.
The full-screen ``/notebooks/workspace`` page stays as-is.

- **File-tree sidebar** ([frontend/templates/pages/notebook_editor.html](frontend/templates/pages/notebook_editor.html),
  [frontend/js/notebook/file_tree.js](frontend/js/notebook/file_tree.js)).
  260px left panel listing directories + ``.py`` + ``.ipynb`` leaves
  from ``/api/notebooks/tree``.  Hover pencil / trash; click names
  to navigate.  Currently-open row is highlighted and its trash is
  disabled to keep the editor out of a dangling state after delete.
  Toggle state persists in ``localStorage['pql.nbedit.filesVisible']``;
  sidebar defaults visible on first load.
- **Three CRUD endpoints** ([pointlessql/api/main.py](pointlessql/api/main.py)):
  ``POST /api/notebooks/create`` writes a zero-byte ``.py`` file
  (the editor's open handler already materialises cell markers on
  first save), ``PATCH /api/notebooks/rename`` atomically moves a
  file and re-keys its replay cache, ``DELETE /api/notebooks?path=…``
  removes the file and cascades into ``notebook_outputs`` +
  ``notebook_cell_runs``.  All admin-only, all audit-logged.
- **Shared resolver** ([pointlessql/services/notebook_workspace.py](pointlessql/services/notebook_workspace.py)):
  new ``resolve_notebook_target`` owns the traversal + parent-
  directory guard for every mutation helper; the pre-existing
  ``resolve_upload_target`` now delegates to it.  Added
  ``create_empty_notebook`` / ``rename_notebook`` /
  ``delete_notebook`` helpers.
- **Replay cache re-keying** ([pointlessql/services/notebook_outputs.py](pointlessql/services/notebook_outputs.py)):
  new ``rename_path`` ``UPDATE``s ``file_path`` on ``NotebookOutput``
  + ``NotebookCellRun`` so rename preserves per-cell outputs + run
  history.  Paired with the existing ``clear_path`` which is now
  wired from the delete endpoint.
- **Three Bootstrap modals** on the editor page — new / rename /
  delete — reusing the Catalog-Insert modal's ``x-show`` +
  ``@keydown.escape.window`` pattern.
- **Reactivity-boundary gate widened** ([scripts/check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh))
  to block ``this._treeFetchCtrl`` and ``this._treeAbort`` —
  sidebar's AbortController for inflight tree fetches stays in
  closure scope.
- **Playbook Part H** ([docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md))
  covers the six sidebar flows: render, toggle, open, new,
  rename-open-file (hard-reload), delete-other-file (tree refresh).

### Fixed (Sprint 67 replay catch)

- **BUG-67-01** — Alpine 3.14.1's ``x-show`` sets inline
  ``display = ''`` on ``false → true``, letting Bootstrap 5's
  ``.modal { display: none }`` CSS rule win: every editor modal
  stayed invisible on its first open even though Alpine thought
  it was visible.  The pre-existing Catalog-Insert modal (Sprint
  62-ish) had the same latent bug.  Fixed by replacing ``x-show``
  with ``:class="{ 'd-block': flag }"`` on all four editor modals
  (Catalog, New, Rename, Delete) — Bootstrap's ``.d-block``
  utility is ``display: block !important`` which beats both the
  cascade and Alpine's inline manipulation.  Caught by replaying
  Part H of the editor playbook in Firefox per
  ``feedback_run_playbook_as_gate``.

**No Alembic migration** — rename is a plain ``UPDATE``, delete
reuses the ``clear_path`` stub Sprint 63 had already wired in
anticipation of this sprint.

### Added (Sprint 66) — Phase 12.7: cell-type registry + per-cell affordances

Second Phase 12.7 sprint.  Converts the hardcoded ``code | markdown``
fork spread across ``cell_parser.js`` + ``main.js`` into a single
descriptor registry, and surfaces per-cell affordances (run button,
execution-count pill, elapsed-time pill, status pill, ``+`` inserter)
that the wire protocol already carried but the Sprint-58 UI ignored.
No backend changes, no Alembic migration — the ``notebook_cell_runs``
columns reserved by Sprint 60's Alembic 017 stay unwritten until
Sprint 73 actually persists per-cell history.

- **Cell-type registry** at [frontend/js/notebook/cell_types.js](frontend/js/notebook/cell_types.js).
  One descriptor per type with ``id``, ``label``, ``markerTag``,
  ``canExecute``, ``bandClass``.  ``getCellType(id)`` is the single
  lookup point; unknown tags fall back to ``code`` so a Sprint-71
  ``[sql]`` marker loaded by a pre-Sprint-71 client renders as plain
  Python instead of dropping the cell.  ``CELL_MARKER_RE`` widened
  from ``(\s+\[markdown\])?`` to ``(\s+\[\w+\])?``.
- **Per-cell affordances** at [frontend/js/notebook/cell_affordances.js](frontend/js/notebook/cell_affordances.js).
  Two view zones per cell — a 26px toolbar above the marker (run
  button + ``[n]`` exec count + status pill + elapsed + type label)
  and a 22px hover-revealed inserter below the cell body with
  ``+ Code`` / ``+ Markdown`` buttons.  All DOM nodes, Monaco view-
  zone handles, and ``setInterval`` timers live in a closure-scoped
  ``cellAffordances`` map on the orchestrator — BUG-64-02
  reactivity-boundary invariant preserved.
- **WS wiring.**  ``renderKernelMsg`` in ``main.js`` now intercepts
  ``execute_input`` (pulls ``execution_count`` into the pill) and
  ``execute_reply`` (maps ``ok`` / ``error`` / ``aborted`` →
  ``ok`` / ``error`` / ``cancelled``) before dispatching to the
  existing ``appendOutputFrame`` path, so empty output zones no
  longer leak from shell-channel replies.
- **Status pills.**  Five states — ``idle``, ``running`` (yellow,
  pulsing), ``ok`` (green), ``error`` (red), ``cancelled``
  (muted).  Elapsed timer ticks every 100 ms during a run and
  freezes on ``execute_reply``.  Kernel ``restart`` resets all
  count pills to ``[ ]``, status pills to ``idle``, and clears
  elapsed.
- **Single execution seam.**  ``runCellById(cellId)`` is the one
  method that fires an execute frame; ``runCurrentCell`` /
  ``runAllCells`` / ``runCellsAbove`` / per-cell ``▶`` button all
  route through it.  Registry's ``canExecute`` gate is checked once
  at the seam instead of being duplicated per-call-site.
- **``+`` inserter**.  Inserts a fresh cell (with UUID from
  ``crypto.randomUUID``) one line below the anchor cell's body,
  using ``getCellType(typeId).markerTag`` so the inserter does not
  know about the specific tag strings.  ``rebuildCellAffordances``
  is idempotent — it re-runs on every ``onDidChangeContent`` and
  moves zones via ``removeZone`` + ``addZone`` to re-anchor after
  boundary shifts.
- **Reactivity-boundary gate widened.**  ``scripts/check-frontend-no-reactive-monaco.sh``
  now also blocks ``this._cellAffordances``, ``this._statusWidgets``,
  ``this._cellWidgets``, and ``this._reactiveRoot`` so the
  Sprint-66 state surface cannot be smuggled back onto ``this._X``
  under a different field name.
- **Playbook Part G** added to [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md)
  covering the seven check-boxes: toolbar visible per cell, per-cell
  run button, error status, interrupt → cancelled, ``+`` inserter
  (code + markdown), kernel-restart reset, page-reload BUG-64-02
  regression gate.  Replayed in Firefox via Playwright-MCP as the
  land gate per ``feedback_run_playbook_as_gate``.
- **Alpine-vs-ESM race fix** (caught by the replay).  Sprint-65's
  ``<script type="module" src="bootstrap.js">`` + the two extra
  Sprint-66 modules pushed the ESM graph resolution past Alpine's
  deferred boot, leaving the reactive scope empty on first load.
  Fixed by converting [bootstrap.js](frontend/js/notebook/bootstrap.js)
  from a module to a classic IIFE that registers
  ``window.notebookEditor`` synchronously during HTML parse and
  dynamic-imports [main.js](frontend/js/notebook/main.js) inside
  the factory's ``mount()``.  Same mitigation pattern as the
  Sprint-41 SQL-editor fix (commit ``b830300``).  Script tag
  carries ``?v=sprint66`` to bust Firefox's module cache for
  consumers upgrading in-place.
- **KeyboardInterrupt → ``cancelled``** (caught by the replay).
  Jupyter surfaces a user-interrupted cell as
  ``execute_reply.status='error'`` with ``ename='KeyboardInterrupt'``,
  not ``status='aborted'``.  The reply handler in
  [main.js](frontend/js/notebook/main.js) now maps both
  ``aborted`` and ``error + ename='KeyboardInterrupt'`` to the
  ``cancelled`` pill so the red error state is reserved for
  genuine runtime errors.

### Added (Sprint 65) — Phase 12.7 opener: editor JS modularisation

Phase 12.7 ("Notebook editor UX overhaul") opens with a structural
sprint that prepares the notebook editor codebase for the eight UX-
heavy follow-on sprints (cell-type registry, file-tree sidebar,
multi-tab, markdown-it + KaTeX, outline, SQL cell, ipywidgets,
history + diff, theme + keymap).  No visible UX change — the
existing 22-step playbook still passes unchanged; visible-UX sprints
starting with Sprint 66 will replay the playbook before commit.

- **JS module split.**  ``frontend/js/notebook_editor.js`` (1571-LoC
  IIFE) is replaced by nine ESM modules under
  ``frontend/js/notebook/``: ``cell_parser.js`` (markers + namespace
  introspect snippet), ``ansi.js`` (SGR → HTML traceback rendering),
  ``markdown.js`` (regex preview renderer; Sprint 69 will swap for
  ``markdown-it``), ``monaco_loader.js`` (vendored AMD + the Sprint-
  64 defer-until-load wrapper), ``pyright_client.js`` (JSON-RPC
  client + Monaco completion / hover / signature / definition
  provider registration via ``WeakMap``), ``output_renderer.js``
  (mime-bundle dispatch + Sprint-62 inline-script rehydration),
  ``closure_state.js`` (``createClosureRefs`` helper — see below),
  ``main.js`` (Alpine-factory orchestrator), and ``bootstrap.js``
  (ESM entry that exposes ``window.notebookEditor`` so Alpine's
  ``x-data="notebookEditor(...)"`` keeps resolving).
- **``createClosureRefs`` helper.**  Promotes the Sprint-64
  BUG-64-02 fix from inline-comment mahnung to a documented sealed
  bag of mutable refs that never leaves the factory closure.  Monaco
  model + editor refs live in ``refs`` (named slots; typo throws);
  other private state (timers, WebSocket handles, output-zone DOM
  maps, accumulator buffers, parsed-cell cache) moved to closure-
  scoped ``let`` vars.  The reactive object Alpine sees now carries
  primitive UI state + bound methods only.
- **CI grep gate.**  ``scripts/check-frontend-no-reactive-monaco.sh``
  greps ``frontend/js/notebook/`` for the forbidden assignment
  pattern ``this\._(editor|model|monaco|worker|wsRaw|lspWsRaw|
  saveTimer)\s*=`` and exits non-zero on a hit.  Wired into
  ``.github/workflows/test.yml`` after the ``alembic check`` step
  — pure shell, no Python venv needed.  Belt-and-suspenders against
  Sprint-66+ accidentally re-introducing the BUG-64-02 class of
  bug under a different field name.
- **Template** (``frontend/templates/pages/notebook_editor.html``)
  now loads ``<script type="module"
  src=".../notebook/bootstrap.js">``; the legacy
  ``notebook_editor.js`` is **deleted** (no grace alias — the sole
  consumer was edited in the same commit).  Two ``x-show``
  expressions that referenced the now-closure-scoped
  ``_catalogTables`` switched to the new ``catalogTablesLoaded``
  flag and ``catalogTablesEmpty`` getter on the reactive object.
- **ROADMAP.md** opens Phase 12.7 with the ten-sprint tree (65–74)
  and five trim-points marked.  Hard dependency chain: 65 unblocks
  all later sprints, 66 unblocks 71, 67 → 68.  Max-trim path is
  ``65 → 66 → 68 → 73 → 74``.

All gates green: ruff, pyright, pydoclint, alembic upgrade head +
check, plus the new ``check-frontend-no-reactive-monaco.sh``.

### Added (Sprint 64) — Phase 12.6 close: editor E2E playbook

Phase 12.6 closes with its e2e playbook and the one-release
grace aliases from Sprint 63 removed.

- **``docs/e2e-walkthroughs/notebook-editor.md``** — six-part
  deterministic playbook (First open / Execute+persistence /
  Pyright LSP / Insert-from-catalog / Variable Explorer /
  Post-retirement surfaces) replacing the Sprint-23 JupyterLab
  iframe playbook.  Same step-by-step shape the other
  playbooks follow so a human with a browser or an MCP-driven
  Claude Code session can replay it deterministically.
- **Grace aliases removed.**  ``GET /notebook`` no longer
  302-redirects (the route is unregistered; the navbar link
  goes straight to the editor so no internal caller relied on
  the redirect).  ``open-in-notebook`` response dropped the
  ``lab_url`` alias; ``pages/table.html`` reads
  ``editor_url`` directly.
- **Sprint-23 ``notebook.md`` playbook retired** — obsoleted
  by the iframe retirement.  The walkthroughs README index
  points at ``notebook-editor.md`` as slot #7.

**Phase 12.6 → ✅**.  The native notebook editor started as a
Sprint-58 skeleton (Monaco + jupytext round-trip), layered
execution (59) + persisted rich outputs (60) + Pyright LSP (61)
+ Variable Explorer / catalog insert (62) + papermill ``.py``
bridge + iframe retirement (63), and closed with the playbook
here in Sprint 64.  The quality bar ("as good as VSCode Python
Interactive Window") landed unchanged from the plan.

### Changed — Breaking (Sprint 63) — JupyterLab iframe retired

Phase 12.6 Sprint 63 retires the Sprint-3 embedded JupyterLab
iframe.  The native Monaco editor that Sprints 58–62 built ships
every notebook-facing use case end-to-end; the iframe came out in
this commit.

Breaking changes to a running deployment:

- **``jupyterlab`` is no longer a runtime dep.**  ``pyproject.toml``
  drops ``jupyterlab>=4.0``.  ``uv sync`` removes ~30 transitive
  packages from the venv.  Docker images shrink accordingly.
- **No more JupyterLab subprocess.**  ``services/jupyter.py`` is
  gone.  The FastAPI lifespan no longer starts a kernel server
  on port 8888.  ``POINTLESSQL_JUPYTER_PORT`` stays on the
  settings class for backward-compat but does nothing.
- **``GET /notebook`` now 302-redirects** to
  ``/notebook/editor?path=scratch.py``.  The Sprint-3 iframe page
  template (``pages/notebook.html``) is deleted.
- **``GET /api/jupyter/status`` is removed.**  The endpoint was
  only used by the Sprint-3 loader polling the JupyterLab
  subprocess — the native editor has no equivalent gate.
- **User-authored ``.ipynb`` editing is unsupported.**  The
  editor reads / writes ``.py`` only.  Papermill-generated
  ``.ipynb`` under ``notebooks/runs/`` still works (execute-only
  artefact) and the Sprint-27 workspace browser still lists
  ``.ipynb`` uploads for scheduling.  Migration: run
  ``jupytext --to py:percent file.ipynb`` manually.  README
  gained a migration section.
- **Navbar simplified.**  The Sprint-58 dropdown
  (JupyterLab-classic + Editor-preview) collapsed into one
  ``Notebook`` link that goes straight to the editor.
- **Sprint-26 job-detail output card** dropped the
  ``Rendered / JupyterLab`` view-mode toggle.  The rendered
  HTML (nbconvert's lab template) is now the only mode.  The
  ``Open in JupyterLab`` anchor became a ``Download ipynb``
  button that hits the existing download endpoint.
- **``Sprint-34 open-in-notebook``** now scaffolds a ``.py``
  jupytext notebook and returns ``{editor_url: …}`` instead of
  ``{lab_url: …}``.  The ``lab_url`` alias still ships on the
  response as a one-release grace for clients that have not
  been reloaded; Sprint 64 drops it.

Positive changes enabled by the retirement:

- **Papermill can schedule ``.py`` notebooks.**  The scheduler's
  ``_papermill_executor`` gains a jupytext-convert step —
  ``.py`` inputs are converted to a sibling ``.ipynb`` in
  ``runs/``, papermill executes, and the temp ``.ipynb`` is
  unlinked in a ``finally`` block.  ``resolve_notebook_path``
  accepts both suffixes.
- **Workspace tree shows ``.py`` notebooks** with a themed icon
  and an ``Open`` button that routes into the native editor.
  ``.ipynb`` entries keep the Schedule action only.
- **CSP cleanup.**  The Sprint-3 ``frame-ancestors 'self'
  http://localhost:8000 http://127.0.0.1:8000`` header was
  scoped to the JupyterLab subprocess and went away with it.
  No separate main.py CSP entry to unwind.

All gates green: ruff, pyright (0 errors, ~87 third-party
warnings, no regressions), pydoclint.

### Added (Sprint 62) — Variable Explorer + catalog insert + rich script exec

Phase 12.6 Sprint 62 rounds out the native editor's read-side
ergonomics: a live Variable Explorer reflects the kernel's user
namespace, an ``Insert from catalog`` modal drops
``pql.read_table(...)`` snippets at the cursor, Monaco's
command palette surfaces the run / clear / restart / insert
actions, and the ``text/html`` output path now executes inline
scripts so plotly / altair / bokeh render for real.

- **``__pql_`` internal cell-id namespace.**  The WS handler's
  persistence hooks skip any cell_id starting with ``__pql_``
  on both ``notebook_outputs`` inserts and
  ``notebook_cell_runs`` upserts.  This lets the editor run
  silent introspects (Variable Explorer, future autocomplete
  helpers) under reserved cell ids without polluting the DB —
  a non-breaking-change hook Sprint 63's workspace-tree
  integration can also lean on.
- **Variable Explorer sidebar.**  Toggleable right-side panel
  that lists every user-defined variable by name + type + shape
  + a 5-row ``DataFrame`` preview (pandas-styled HTML) or a
  truncated ``repr()`` fallback.  The introspect snippet runs
  under ``__pql_namespace__`` and re-fires after every user
  cell goes idle, but only when the panel is open so inactive
  tabs pay zero introspect cost.  Smoke-tested end-to-end
  against a real ipykernel: a 2×2 pandas DataFrame round-trips
  as ``{type: "DataFrame", shape: [2, 2], repr: "…"}``.
- **Insert from catalog** modal.  Fetches ``/api/tree``,
  flattens the catalog → schema → table hierarchy into a
  searchable list, inserts ``pql.read_table("cat.schema.tbl")``
  at the cursor on pick.  Binding: Ctrl+Shift+I or toolbar
  ``Catalog`` button or the command-palette entry.
- **Command palette actions.**  Every notebook-editor command
  is registered via ``editor.addAction`` so F1 / Ctrl+Shift+P
  lists them:  ``Run all``, ``Run all cells above cursor``,
  ``Insert cell above / below``, ``Insert markdown cell below``,
  ``Clear outputs``, ``Restart kernel``, ``Insert from
  catalog…``, ``Toggle variable explorer``.  Single-letter
  ``M`` / ``Y`` / ``DD`` shortcuts deliberately skipped — the
  editor stays always-in-edit-mode, Jupyter-classic's
  command-mode state machine is not worth the bookkeeping.
- **Plotly / altair / bokeh render inline.**  ``text/html``
  output is painted via ``innerHTML`` (which sandboxes
  ``<script>``) and then every ``<script>`` in the rendered
  subtree is cloned into a freshly-parsed node so the browser
  actually executes it.  Same trick Jupyter's nbrenderer
  uses; no additional vendoring.
- **Scope-gate honoured**.  ipywidgets + any ``comm_msg`` /
  ``display_data`` updating stays out of Phase 12.6 per the
  memory decision.  If a future cell emits a widget bundle
  the renderer will simply show the fallback ``text/plain``
  rep; widgets land in Phase 12.7.

### Added (Sprint 61) — Pyright LSP (completion / hover / diagnostics)

Phase 12.6 Sprint 61 wires ``pyright-langserver`` into the native
editor over a dedicated WebSocket.  Monaco's CompletionItem,
Hover, SignatureHelp, and Definition providers now route through
pyright; diagnostics populate the gutter via
``monaco.editor.setModelMarkers``.  Kernel-backed dual-source
completion is explicitly deferred to a follow-up per the plan's
scope-killer escape hatch — LSP-only ships a clean sprint.

- **Deps.** ``pyright>=1.1`` moves from dev-only to a runtime
  dep so the ``pyright-langserver`` binary ships on
  ``.venv/bin`` for both local dev and Docker.
- **Service layer** (``pointlessql/services/pyright_bridge.py``).
  ``PyrightSession`` spawns ``pyright-langserver --stdio`` and
  handles the LSP ``Content-Length`` framing in both directions
  via asyncio stdio.  Inbound messages dispatch to an async
  callback (subscriber errors are caught + logged so a broken
  consumer doesn't tear the reader loop down); outbound
  messages add the header before writing.  ``shutdown`` sends
  SIGTERM with a 2 s timeout, then SIGKILL.
- **WS route.** ``/ws/notebook/lsp?path=<rel>`` mirrors the
  Sprint-59 kernel WS: manual ``pql_session`` cookie auth,
  same traversal guard via ``resolve_py_notebook_path``, one
  pyright subprocess per connection so subprocess lifetime
  equals tab lifetime.  A 4404 close code fires when
  ``pyright-langserver`` is missing from ``PATH`` so the UI
  can say "Pyright unavailable" instead of reconnect-looping.
- **Frontend.** A ~40-line ``PyrightClient`` handles JSON-RPC
  request/response correlation + notification subscribers.
  Monaco provider registration is gated with a module-level
  flag + a ``WeakMap`` so the same global language id can
  serve multiple editor instances without cross-fire.
  ``initialize`` → ``initialized`` → ``textDocument/didOpen``
  on mount; full-document ``didChange`` on every
  ``onDidChangeContent`` (notebook-sized buffers, incremental
  sync is not worth the bookkeeping).
  ``textDocument/publishDiagnostics`` notifications repaint
  markers via ``monaco.editor.setModelMarkers``.
- **Toolbar**. New ``lspStatus`` pill reads "Loading Pyright…"
  / "Pyright ready" / "Pyright error" / "Pyright unavailable"
  next to the ``kernelStatus`` pill.
- **Out of scope (deferred).** Kernel ``complete_request``
  merged into Monaco's completion list as a second source —
  explicit scope-killer invocation, lands as a Sprint-61
  follow-up (or Sprint 62) as a ~30-line provider with no
  backend changes required.
- **Validation.** Pyright subprocess smoke proved initialize →
  didOpen → completion + diagnostics round-trip against a
  seeded ``json.`` buffer: real module members came back in
  the completion list, the trailing ``.`` was flagged by the
  diagnostics channel.  All gates green.

### Added (Sprint 60) — Output persistence + rich outputs

Phase 12.6 Sprint 60 closes the "reopen doesn't cost 90 seconds"
loop locked in ADR 0001 (kernel + output-schema decisions), and
upgrades the Sprint-59 text-only renderer to the full mime-bundle
matrix Jupyter clients ship with.

- **Alembic 017.** ``notebook_outputs`` +
  ``notebook_cell_runs`` with the exact DDL ADR 0001 pinned.
  No surprise column additions, no silent PK changes.
- **ORM models** (``pointlessql/models.py``). ``NotebookOutput``
  and ``NotebookCellRun`` follow the Sprint-56 ``TableStats``
  pattern — composite index keyed on ``(file_path, cell_id)`` for
  the hot read path, quadruple unique on the output-index triple
  for write safety.
- **Service layer** (``pointlessql/services/notebook_outputs.py``).
  Deliberately thin: ``append_output`` / ``load_outputs_for_path``
  / ``clear_cell`` / ``clear_session`` / ``clear_path`` /
  ``upsert_cell_run``.  Only four content-carrying msg types
  persist (``stream`` / ``execute_result`` / ``display_data`` /
  ``error``); status + execute_input stay ephemeral.
- **WS handler persistence hooks**.  Per-connection
  ``output_counters`` drive monotonic ``output_index`` values
  across a single session.  ``execute`` triggers
  ``clear_cell`` + upsert ``status=running`` before the ZMQ
  send.  Shell-channel ``execute_reply`` closes the run row
  with mapped status (ok/error/aborted) and the kernel's
  ``execution_count``.  A new client-initiated ``clear_cell``
  frame purges both the view zone and the DB row set.
  Restart now ``clear_session``'s the outgoing kernel session
  *before* the subprocess restart bumps the session id.
- **Editor route replay**. ``GET /notebook/editor`` threads every
  persisted output through the initial Alpine payload so the
  mount paints them into view zones synchronously — the WS hello
  frame arrives ``after`` the user sees their previous outputs,
  eliminating the reopen-wait.
- **Rich mime renderer** (``frontend/js/notebook_editor.js``).
  Priority list: ``text/html`` > ``image/svg+xml`` >
  ``image/png`` > ``image/jpeg`` > ``application/json`` >
  ``text/plain`` fallback.  Pandas-styled HTML tables inherit the
  catalog dark theme via scoped CSS.  Inline matplotlib (PNG),
  altair / plotly (HTML), and standard Jupyter display_data
  flows all land on this path.
- **ANSI tracebacks**.  A dependency-free SGR walker converts
  IPython's ``ultratb`` output into coloured ``<span>``s — no
  ``xterm.js`` bundle, no vendor-script work.  Covers the
  standard 30-37 / 90-97 foreground palette + bold + reset.
- **Toolbar** gained a ``Clear cell`` button.  Sprint 59's
  ``Restart`` button now wipes the outgoing kernel session's
  persisted rows in the same click so "restart + clear" stays
  one user action.
- **ipywidgets** remain out of scope per the Phase-12.6 decision
  memory — interactive widgets are deferred to Phase 12.7 if they
  prove load-bearing.

### Added (Sprint 59) — Kernel + WebSocket proxy + basic execution

Phase 12.6 Sprint 59 adds the second layer of the native notebook
story: one long-lived ``ipykernel`` subprocess per
``(user_id, notebook_path)`` pair, a FastAPI WebSocket endpoint
that proxies ZMQ shell / iopub messages as JSON frames, and the
client half that turns Shift+Enter into a round-trip execute
with text / stream / error outputs rendered under the cell via
Monaco view zones.  Output persistence and rich mime rendering
land in Sprint 60; LSP in Sprint 61.

- **Deps.** ``jupyter_client>=8.6`` + ``ipykernel>=6.29`` now
  pinned explicitly in ``pyproject.toml`` (both already arrived
  via papermill's transitive closure).
- **Service layer** (``pointlessql/services/kernel_session.py``).
  ``KernelSession`` wraps ``AsyncKernelManager`` + a single ZMQ
  reader pump per channel that fans out to N subscriber queues
  — two browser tabs of the same notebook can watch the same
  kernel without starving each other on ``get_iopub_msg``.
  ``KernelRegistry`` owns the dict keyed by ``(user_id, path)``
  and lives on ``app.state.kernel_registry``; the FastAPI
  lifespan's existing cleanup block calls ``shutdown_all`` so a
  clean app stop tears down every in-flight subprocess
  gracefully (SIGTERM + 5 s timeout, then force-kill — mirrors
  the Sprint-3 ``jupyter._shutdown`` pattern).
  ``POINTLESSQL_PRINCIPAL`` forwards via the kernel manager's
  ``env=`` kwarg rather than the Sprint-24 ``os.environ`` lock —
  kernels are long-lived, no concurrent ``setenv`` race to
  dodge.
- **WebSocket route.** ``/ws/notebook/kernel?path=<rel>``.
  WebSocket upgrades bypass the HTTP auth middleware, so the
  handler pulls the ``pql_session`` cookie directly and decodes
  the JWT via ``auth_service.get_current_user`` — same call
  chain the HTTP middleware uses, just from a WS context.
  Traversal guard reuses ``notebook_doc_service.
  resolve_py_notebook_path``.  Client frames: ``{type: "execute"
  | "interrupt" | "restart"}``; server frames: ``{type: "hello"
  | "ack" | "kernel_msg" | "interrupted" | "restarted" |
  "error"}``.
- **Frontend.** Shift+Enter / Ctrl+Enter run the cell at the
  cursor (Monaco ``addCommand`` bindings fire only when the
  editor has focus so the toolbar and Alpine inputs keep normal
  Enter semantics).  Current-cell detection walks upward from
  the cursor line for the nearest ``pql_cell_id`` marker.
  Output zones are Monaco view zones anchored below each cell's
  last line — ``pql-nbedit-output`` styling colour-codes
  stream/stdout, stderr, ``execute_result``, and ``error``;
  tracebacks strip ANSI codes until Sprint 60 lands ANSI-to-HTML.
  Toolbar gained Interrupt (sends SIGINT) and Restart (bumps
  ``kernel_session_id``, clears outputs) buttons plus a live
  ``kernelStatus`` indicator.
- **Out of scope (Sprint 60).** Rich mimes (``text/html``,
  ``image/png``, ``image/svg+xml``, pandas-HTML, matplotlib
  inline), persisted outputs, ANSI-to-HTML traceback rendering.
  The kernel message shape already matches what the Alembic-017
  ``notebook_outputs`` table will capture — Sprint 60 swaps the
  ephemeral DOM writes for queries against the persistence
  layer without touching the WS protocol.

### Added (Sprint 58) — Native notebook editor skeleton

Phase 12.6 opens with the skeleton of a first-party Monaco-based
notebook editor that will eventually replace the Sprint-3
JupyterLab iframe. Scope for Sprint 58 is deliberately narrow:
load, render, save. Execution, LSP, and persisted outputs land in
Sprints 59–60.

- **ADR 0001** — ``docs/adr/0001-notebook-editor.md`` locks in
  the three decisions every subsequent Phase-12.6 sprint builds
  on: single Monaco over a virtual document (not one editor per
  cell), output-persistence schema keyed by
  ``(file_path, cell_id, kernel_session_id)``, cell identity
  via UUIDs written into jupytext cell-marker metadata under the
  custom ``pql_cell_id`` key (marker form
  ``# %% pql_cell_id="<uuid>"``; the filter
  ``cell_metadata_filter: pql_cell_id,-all`` pins it into the
  notebook frontmatter so jupytext preserves the key on
  round-trip).
- **Service layer.** ``pointlessql/services/notebook_doc.py``
  wraps jupytext for ``.py`` Percent-format load / save with a
  ``resolve_py_notebook_path`` traversal guard that mirrors the
  Sprint-27 upload helper.  First load of a foreign notebook
  mints UUIDs for any cell without one and flags the document
  ``dirty`` so the editor can prompt a save.
- **Routes.** ``GET /notebook/editor?path=<relative>`` renders
  the editor with the initial document as a JSON blob the
  Alpine component consumes synchronously on mount.  Missing
  files scaffold an empty cell and are materialised on first
  save.  ``POST /api/notebook/doc`` persists the client's cell
  list back to disk; the CSRF middleware gates it via the
  ``X-CSRF-Token`` header.  Both routes reject paths that
  escape the notebooks directory or lack a ``.py`` suffix.
- **Frontend.** ``frontend/templates/pages/notebook_editor.html``
  hosts a single Monaco instance; cell boundaries render as
  background colour bands via ``deltaDecorations``.  Add-cell
  inserts a ``# %% pql_cell_id="<uuid>"`` marker through
  ``editor.executeEdits`` — no DOM mount / unmount.  The
  client-side cell parser accepts only the canonical UUID
  marker form the server writes; foreign marker variants stay
  a jupytext-on-the-server concern.
- **Monaco vendoring.** ``scripts/vendor-monaco.sh`` pins
  monaco-editor 0.52.0, fetches the tarball from
  ``registry.npmjs.org`` and extracts ``min/vs`` into
  ``frontend/js/vendor/monaco/vs/``.  Contents are gitignored
  (~14 MB); run the script once after ``git clone`` and
  whenever ``MONACO_VERSION`` bumps.
- **Navbar.** "Notebook" becomes a dropdown — ``JupyterLab
  (classic)`` still points at the Sprint-3 iframe,
  ``Editor (preview)`` opens the new route at
  ``?path=scratch.py``.  Hard rule: the iframe stays live
  until Sprint 63.

### Added (Sprint 57) — UC Volumes (upload + convert-to-Delta)

Phase 12.5 closes with the "I have a CSV, make it go" moment.
Cross-repo work: soyuz-catalog gained file IO routes under
``{prefix}/volumes/{full_name}/files`` plus a ``file://`` storage
backend behind a ``VolumeFileBackend`` protocol
(soyuz commit f8ef973).

- **Service layer** (``pointlessql/services/volumes.py``).  Async
  httpx helpers — ``upload_file``, ``browse_files``,
  ``download_file`` (streaming), ``delete_file``, ``volume_url``,
  ``build_headers`` — that talk directly to the new soyuz
  endpoints, forwarding the caller's email as ``X-Principal`` so UC
  enforcement applies.  The generated client stubs have not been
  regenerated for these routes; the raw httpx layer unblocks Phase
  12.5 without a client-regen round-trip and will be swapped in
  after the soyuz tag bumps.
- **Routes.** ``GET /volumes`` list + ``GET /volumes/{full_name}``
  detail pages; ``GET|POST /api/volumes/{full_name}/files``
  (multipart upload + browse);
  ``DELETE /api/volumes/{full_name}/files/{path:path}``; and
  ``POST /api/volumes/{full_name}/convert-to-delta`` (admin-only).
- **Convert-to-Delta.**  Streams the source file out of soyuz into
  a temp path, reads it with DuckDB's ``read_csv_auto`` /
  ``read_parquet`` / ``read_json_auto``, writes a managed Delta
  directory inside the volume's ``file://`` root at
  ``_delta_<table>/``, inspects the Delta schema via ``deltalake``,
  and calls UC's ``create_table`` to register an ``EXTERNAL``
  table with the correct columns.  Only ``file://`` volumes are
  supported this sprint — cloud backends are a soyuz follow-up.
- **Audit.** ``volume.file_uploaded``, ``volume.file_deleted``,
  ``volume.converted_to_delta``.
- **Frontend.** ``pages/volumes.html`` (list) +
  ``pages/volume_detail.html`` (detail).  Upload form uses raw
  ``fetch(..., {body: FormData})`` with the CSRF header read from
  the ``<meta name="csrf-token">`` tag.  A per-file "Convert to
  Delta" button is rendered only for supported extensions
  (``.csv`` / ``.parquet`` / ``.json``).  Component scripts are
  non-module IIFEs that publish ``window.volumeDetail``
  synchronously before Alpine walks (Phase-12 trap #1 preempted).
- **Nav.**  "Volumes" entry in ``nav_links.html``.
- Tests: 6 new cases in ``tests/test_volumes.py`` — URL + header
  helpers + four httpx ``MockTransport`` round-trips covering
  upload (multipart body + X-Principal), browse (JSON list),
  delete (boolean), and download (streamed chunks).

### Added (Sprint 56) — Column statistics / data profiling

- **Alembic 016** — new ``table_stats`` table keyed by
  ``(full_name, delta_log_version, column_name)`` with a composite
  unique constraint + ``ix_table_stats_lookup`` for the read path.
- **Model.** ``TableStats`` under ``pointlessql/models.py``.
- **Service layer** (``pointlessql/services/table_stats.py``).
  ``read_delta_log_version`` wraps ``DeltaTable.version()``.
  ``compute_stats`` opens a DuckDB conn, registers the Delta view
  via the Sprint-49 ``register_delta_view`` helper, and issues one
  aggregate SQL per column plus a second ``GROUP BY`` when
  cardinality permits.  ``write_cached`` is idempotent,
  ``read_cached`` returns parsed dicts, ``delete_cached`` evicts
  every version.  Non-numeric columns never carry a ``mean``;
  ``top_5`` is skipped when ``distinct_count`` exceeds
  ``TOP_K_DISTINCT_CEILING`` (10 000 default).
- **Routes.**
  ``POST /api/tables/{full_name:path}/profile`` — SELECT-gated,
  checks the cache first, falls back to compute + write, emits one
  ``table.profiled`` or ``table.profile_cache_hit`` audit row.
  ``GET /api/tables/{full_name:path}/stats?version=<opt>`` —
  SELECT-gated read path.
  ``DELETE /api/tables/{full_name:path}/stats`` — admin-only
  eviction with a ``table.stats_cleared`` audit row.
- **Frontend.** New "Column statistics" card on the table detail
  page with Profile + admin-only Clear cache buttons; ``top_5`` bars
  render via Chart.js (reusing Sprint-54's CDN — zero extra network
  weight).  Non-module IIFE publishes ``window.tableStats``.
- Tests: 9 new cases in ``tests/test_table_stats.py`` — pure
  helpers (end-to-end compute against a Delta fixture, top_5 ceiling,
  cache round-trip, eviction, fresh-Delta version read) + HTTP
  surface (profile → cache-hit → stats round-trip, DELETE
  admin-only, profile enforces SELECT, 404 on unknown table).

### Added (Sprint 55) — Query alerts (CloudEvents webhook + Atom/JSON Feed)

- **Alembic 015** — ``alerts`` / ``alert_destinations`` /
  ``alert_events`` + ``users.feed_token``.  ``CHECK`` constraints on
  ``condition_op`` (``gt``/``lt``/``eq``/``ne``), ``kind``
  (``webhook``/``feed``), ``outcome`` (``fired``/``suppressed``/
  ``delivery_failed``).  Per-owner unique index on the nullable
  ``feed_token``.
- **Models.** ``Alert``, ``AlertDestination``, ``AlertEvent`` under
  ``pointlessql/models.py``; each alert holds a ``backing_job_id``
  FK so the existing scheduler drives firing via the new
  ``alert_check`` job-kind.
- **Service layer** (``pointlessql/services/alerts.py``).  Slug
  generation mirrors Sprint-51's saved-queries shape; CRUD with
  ``(user_id, is_admin)`` enforcement at the boundary; destination
  add/remove; event record/list/prune.  Pure helpers
  ``evaluate_condition`` + ``build_cloudevent`` are covered by
  dedicated tests.
- **Dispatcher** (``pointlessql/services/alert_dispatcher.py``).
  ``dispatch_webhook`` canonicalises the envelope with
  ``json.dumps(sort_keys=True, separators=(",",":"))`` so receivers
  can reserialise after decoding to verify HMAC-SHA256.  Timeouts
  ``connect=5s`` + ``read=10s``; retry ladder 2 extra attempts at
  1s / 2s backoff on 5xx / transport errors; 4xx is a permanent
  failure.
- **Feeds** (``pointlessql/services/alert_feeds.py``).  Atom 1.0
  via ``xml.etree.ElementTree`` with XML prolog; JSON Feed 1.1
  per ``jsonfeed.org/version/1.1``.  Both cap to last 30 days.
- **Scheduler wiring.** New ``_alert_check_executor`` registered
  under ``alert_check`` in ``build_default_registry``.  Reuses the
  existing ``KindRegistry`` + cron-tick infrastructure: the alert's
  hidden backing ``Job`` carries the user's cron expression, the
  executor parses + enforces + runs the saved query, evaluates the
  condition, inserts one ``AlertEvent``, and fans out dispatch.
  Delivery failure flips the event's ``outcome`` to
  ``delivery_failed`` via a second UPDATE.
- **CloudEvents envelope** ``data``: ``alert_slug`` +
  ``saved_query_slug`` + ``condition`` (``{op, threshold}``) +
  ``row_count`` + ``duration_ms`` + ``referenced_tables`` +
  ``fired_at``.  ``duration_ms`` + ``referenced_tables`` carried
  explicitly so Phase-13's EXPLAIN-agent cost-gate can consume the
  same webhook sink without a later payload-shape break.
- **Routes.** ``GET|POST /api/alerts``, ``GET|PATCH|DELETE
  /api/alerts/{slug}``, ``POST /api/alerts/{slug}/destinations``,
  ``DELETE /api/alerts/{slug}/destinations/{id}``,
  ``GET|POST /api/me/feed-token{,/rotate}``,
  ``GET /alerts/feed.atom?token=<opaque>`` returning
  ``application/atom+xml``, ``GET /alerts/feed.json?token=<opaque>``
  returning ``application/feed+json``, HTML pages ``/alerts`` (list)
  + ``/alerts/{slug}`` (detail with destinations + last 50 events).
  Every per-slug endpoint collapses missing + forbidden to 404.
- **Audit actions.** ``alert.created``, ``alert.updated``,
  ``alert.deleted``, ``alert.destination_added``,
  ``alert.destination_removed``, ``alert.feed_token_rotated`` —
  all through ``log_action`` wrapped in ``asyncio.to_thread``.
- **Frontend.** ``/alerts`` list with create-alert modal;
  ``/alerts/{slug}`` detail with destination manager;
  feed URLs panel with copy + rotate actions.  Non-module IIFEs
  publish ``window.alertsPage`` / ``window.alertDetail``
  synchronously (Phase-12 trap #1 preempted).
- **Nav.** New "Alerts" entry in ``nav_links.html``.
- Tests: 19 new cases in ``tests/test_alerts.py`` — condition
  evaluator, CloudEvents envelope shape, dispatcher HMAC +
  retry ladder, Atom + JSON feed parseability, service-level CRUD
  + owner gating, HTTP round-trip (create/list/delete/stranger 404/
  feed-token auth), scheduler executor (fires + records event +
  envelope parses).

### Added (Sprint 54) — Chart toolbar + chart_config persistence

- **Alembic 014** — ``ALTER TABLE query_history ADD COLUMN
  chart_config TEXT NULL``.  JSON-as-text carrying the user's chart
  selection ``{type, x, y}``; ``NULL`` means table view, which is
  correct for every pre-Sprint-54 row.
- **New routes.** ``GET /api/queries/{history_id}`` fetches a single
  row as JSON so the editor can seed its chart config when the page
  is deep-linked from ``/queries``.  ``PATCH /api/queries/{history_id}/
  chart-config`` persists the user's selection; payload is either
  ``{type, x, y}`` (server canonicalises via
  ``json.dumps(sort_keys=True)``) or ``null`` to clear.  Owner + admin
  only; 404 collapses missing + forbidden the same way the Sprint-51
  saved-queries surface does.  Audit action:
  ``query.chart_config_updated``.
- **`POST /api/sql/execute`** success payload now echoes
  ``history_id`` so the frontend's debounced PATCH knows which row
  to update without a second round-trip.
- **Service layer.** ``query_history.get_by_id`` + ``update_chart_config``
  alongside the existing record / list helpers; every mutation takes
  ``(user_id, is_admin)`` up-front so enforcement lives at the
  service boundary, not the route.
- **Chart.js 4.4.1 UMD** via jsDelivr in ``base.html``.  Non-module —
  the Phase-12 replay (commit b830300) burned us once on Alpine/ESM
  races; rule is "factories register on ``window.<lib>`` synchronously".
- **Frontend.** New ``viewMode`` / ``chartConfig`` / ``_chartInstance``
  state on the editor component, plus ``toggleView`` /
  ``renderChart`` / ``destroyChart`` / ``downloadChartPng`` /
  ``seedFromHistory`` methods.  Global ``c`` key toggles table ↔
  chart when focus is outside CodeMirror + form controls.  Results
  card now gates table vs. chart via ``<template x-if>`` branches
  with a Bootstrap btn-group view switch.  PNG download uses
  ``canvas.toBlob`` + an ephemeral ``<a download>``.
- **`/queries` re-run link** now carries ``&history_id=<id>`` so the
  editor's ``seedFromHistory`` fetch can seed the chart config.
- Tests: 7 new cases in ``tests/test_query_history_chart_config.py`` —
  service-level (write + clear + non-owner refusal) + HTTP (owner
  round-trip, null-clears, 422 on invalid payload, 404 for strangers
  on both GET and PATCH).

### Added (Sprint 53) — EXPLAIN + autocomplete + polish + Phase 12 close-out

- **EXPLAIN ANALYZE toggle.** Second button next to Run sends
  ``{explain: true}`` to ``/api/sql/execute``.  Server-side flow:
  parse + enforce as usual, then prepend ``EXPLAIN ANALYZE`` to
  the rewritten SQL and execute.  The multi-row plan output is
  flattened into a single ``explain_text`` string (tab-joined
  cells, newline-joined rows) that the editor drops into a
  ``<pre class="pql-sql-explain-panel">`` block.  EXPLAIN runs
  deliberately skip ``query_history`` and audit — they are
  diagnostic, not operational activity.
- **Catalog-tree autocomplete.** CodeMirror's ``autocompletion``
  extension wired to a custom completion source.  On mount, the
  editor fetches ``/api/tree`` once, flattens to
  ``catalog.schema.table`` strings, and serves them as
  completions whenever the caret touches a word.  Non-admin
  callers see only catalogs they have ``USE`` on — correct
  scope because you should not autocomplete something you can't
  query.  ``@codemirror/autocomplete@6.18.4`` is now in the
  import-map.
- **Mobile stacking.** New ``@media (max-width: 767.98px)`` block
  raises the editor's ``min-height`` so it dominates the
  viewport on phones; the Bootstrap grid already collapses the
  drawer under the editor at ``<lg`` breakpoints.  Results
  table stays horizontally scrollable so wide schemas don't
  overflow.
- **`g s` keyboard shortcut** for "Go to SQL editor" landed in
  Sprint 49 — documented here for the phase index.
- **Playbook.**
  [docs/e2e-walkthroughs/sql-editor.md](docs/e2e-walkthroughs/sql-editor.md) —
  16-step walkthrough covering the golden path (editor → run →
  save → history → re-run → CSV + Parquet export → EXPLAIN →
  cancel) and the two negative paths (non-admin without
  ``SELECT`` gets 403, non-admin can't see admin's private
  saved query gets 404).  Includes a Playwright-MCP script
  and a "Known-limit notes" block that calls out the
  single-worker cancel scope, the no-column autocomplete,
  and the silent row-cap on export.
- **Phase 12 closes.** ROADMAP flips the phase to ✅ done; every
  sprint 49-53 landed with its feat + ``docs(roadmap)`` pair.
- Tests: 1 new EXPLAIN route test in ``tests/test_sql_execute.py``
  (explain=true returns ``is_explain=True`` + non-empty
  ``explain_text``; history row count does not grow).

### Added (Sprint 52) — Export + timeout + cancel

- **`GET /api/sql/execute/{history_id}/download?format=csv|parquet`.**
  Re-runs a previously recorded query (reads ``sql_text`` from the
  :class:`QueryHistory` row, re-parses, re-fetches
  ``storage_location`` for every referenced table, re-enforces
  ``SELECT`` via ``check_privilege``) and streams the result out
  as either CSV (``StreamingResponse``, row-by-row generator) or
  Parquet (``pyarrow.parquet.write_table`` into a ``BytesIO`` +
  single ``Response``).  Filename pattern is
  ``query-{history_id}-{YYYYmmdd-HHMMSS}.{ext}``.  Non-owner
  non-admin callers receive 404 — history IDs are not a bypass.
  Row-cap applies so a huge download cannot be coerced by
  editing ``?format=``.  Emits a ``query.exported`` audit row
  with ``format`` + ``row_count`` in ``detail``.
- **Query timeout (``POINTLESSQL_SQL_QUERY_TIMEOUT_SECONDS``,
  default 60).** The execute route now dispatches the DuckDB
  call via :func:`asyncio.wait_for` and fires ``conn.interrupt()``
  on the pre-captured connection when the window elapses.  A
  timeout is recorded as ``status="cancelled"`` (not ``"failed"``)
  in ``query_history`` — the query may have been valid, just
  slow.
- **Cancel button.** New ``POST /api/sql/execute/{query_id}/cancel``
  endpoint looks up the client-supplied ``query_id`` in a
  per-app :class:`dict` of live :class:`duckdb.DuckDBPyConnection`
  handles (``app.state._live_queries``), calls ``.interrupt()``,
  and returns 204.  Unknown / already-completed IDs are 204 too —
  the client races the execute response and we want idempotence.
  Exceptions raised by ``.interrupt()`` are logged but swallowed
  so a flaky backend can't 500 the cancel request.  The
  ``/sql`` page shows an orange "Cancel" button + elapsed-seconds
  counter while a query is in flight; the Alpine component
  generates a ``crypto.randomUUID`` per run so each execute call
  carries a unique ``query_id`` and the Cancel button targets the
  right connection even if the user fires another query in rapid
  succession.  Execute responses now echo ``query_id`` so clients
  never have to reconstruct it.  Single-worker-correct only;
  multi-worker cancel is Phase 14.
- **`PQL.sql()` + `_run_sql_sync` + `_run_sql_export_sync` accept
  an optional pre-created ``conn``.** The route owns the
  connection lifecycle so it can register the handle in the
  cancel registry *before* the worker thread starts running —
  a race-free design.  The notebook-style entry point (``conn=None``)
  still creates + closes its own connection for callers that
  don't need cancel.
- **Audit actions.** ``query.exported``, ``query.cancelled`` join
  the Sprint-48 ``resource.verb`` Phase-12 vocabulary.
- Tests: 4 export cases in ``tests/test_sql_export_cancel.py``
  (CSV + Parquet round-trip against a small Delta table,
  missing-history 404, re-enforcement 404 for non-owner);
  3 cancel cases (interrupt invoked on registered conn, unknown
  qid → 204, backend raise swallowed → 204); 1 execute-shape
  case (the JSON response now carries ``query_id``).  The
  cancel tests are **fully mocked** — they never run a real
  long-running DuckDB query that would need actually aborting,
  so no risk of the test harness hanging on a regressed
  interrupt path.

### Added (Sprint 51) — Saved queries

- **Alembic 013** creates ``saved_queries`` (id, unique slug,
  title, optional description, ``sql_text`` TEXT, ``owner_id`` FK
  users, ``is_shared`` BOOL default FALSE, created_at, updated_at)
  plus a ``(owner_id, updated_at)`` index so the drawer's
  "most-recently-touched first" ordering is a single index scan.
- **Visibility model.** Owner + admin always see the row; every
  other logged-in user sees it only when ``is_shared = True``.
  Mutation (PATCH / DELETE / re-share) is restricted to owner +
  admin.  The ``/api/saved-queries/{slug}`` endpoints collapse
  "not found" and "forbidden" into a single 404 so unguessable
  slugs double as a mild privacy guard for private rows.
- **`services/saved_queries.py`** — pure helpers independent of
  FastAPI.  ``make_slug(title)`` derives a URL-safe identifier
  with a 6-char hex suffix (two users saving "Daily orders"
  don't collide).  ``create_saved_query``,
  ``list_visible``, ``get_by_slug``, ``update_by_slug``,
  ``delete_by_slug`` cover the full CRUD surface; every mutation
  takes the ``(user_id, is_admin)`` pair up-front so the
  enforcement is at the service boundary, not the route.
  ``ValidationError`` on empty title / empty SQL.
- **API.**
  - ``GET /api/saved-queries`` — list visible rows, admin or
    owner view, ordered by ``updated_at DESC`` (limit 200).
  - ``POST /api/saved-queries`` — create; audit tag
    ``query.saved`` (private) or ``query.shared`` (on creation
    with ``is_shared: true``).
  - ``GET /api/saved-queries/{slug}`` — single lookup, 404 on
    miss or privacy.
  - ``PATCH /api/saved-queries/{slug}`` — partial update; audit
    tag ``query.updated`` unless the sharing flag flipped, in
    which case ``query.shared`` / ``query.unshared``.
  - ``DELETE /api/saved-queries/{slug}`` → 204; audit tag
    ``query.deleted``.
- **Editor sidebar drawer.** New ``components/saved_queries_drawer.html``
  included on ``/sql`` as a 3-col right-hand column on desktop
  (Sprint-53 will add the mobile stack).  Shows title +
  description + owner email + "shared" badge; click the title
  to load into the editor, click the red ``x`` to delete with a
  confirm dialog.
- **Save current query modal + Cmd+S.** ``<div id="pqlSaveQueryModal">``
  renders a Bootstrap modal with title / description / shared
  checkbox.  CodeMirror's ``Mod-s`` keybind and a new "Save"
  button next to "Run" both open the modal; on submit
  ``pqlApi.fetch('POST /api/saved-queries')`` creates the row
  and refreshes the drawer.
- **Audit actions.** ``query.saved``, ``query.shared``,
  ``query.unshared``, ``query.updated``, ``query.deleted`` —
  every new audit string follows the Sprint-48 ``resource.verb``
  convention settled for Phase 12.
- Tests: 11 new cases in ``tests/test_saved_queries.py`` —
  slug generation + sanitising, empty title/SQL validation,
  private peer query hidden from non-owner, shared query visible
  to non-owner, PATCH/DELETE by non-owner returns None/False,
  owner toggles ``is_shared``, full API round-trip (create →
  list → get → private-is-404-for-other-user → PATCH-by-non-
  owner-404 → DELETE-204).

### Added (Sprint 50) — Query history

- **Alembic 012** creates two new tables. ``query_history``
  (``id``, ``user_id``, ``user_email``, ``sql_text`` TEXT,
  ``started_at`` + ``finished_at``, ``status`` CHECK IN
  ``succeeded|failed|cancelled``, nullable ``row_count`` /
  ``duration_ms`` / ``error_message``, ``request_id`` for
  Sprint-16 log correlation) with composite indexes on
  ``(user_id, started_at)`` and a forward index on
  ``started_at``.  ``query_history_tables`` (``id``,
  ``query_history_id`` FK, ``full_name``, ``access_type``
  defaulting to ``"read"``) with a reverse-lookup index on
  ``(full_name, query_history_id)`` so the "who queried table X"
  pattern is a single index seek.
- **`POST /api/sql/execute` now persists history on both paths.**
  Success and failure each write a ``query_history`` row via the
  new :func:`_record_query_async` helper, which dispatches the
  INSERT through :func:`asyncio.to_thread` (same pattern as
  Sprint-48's ``_audit``).  Parse failures log an empty
  ``referenced_tables`` array; enforcement failures carry the
  refs that were extracted before ``check_privilege`` raised.
  ``error_message`` is the exception detail verbatim so the
  ``/queries`` detail panel can surface DuckDB's "column not
  found" without a second fetch.
- **`GET /queries` page** — Jinja template ``pages/queries.html``
  driven by the Sprint-33 ``listTable`` Alpine component.  Filter
  chips: *Mine only*, *Failed*, *Last 24h*.  Each row renders a
  status badge, SQL snippet (truncated at 120 chars with an
  expand-to-show-error toggle for failed rows), referenced-table
  chips, a duration, and a re-run button that links to
  ``/sql?prefill=<urlencoded sql>``.  Non-admin callers see only
  their own rows — enforcement lives in
  :func:`api_list_queries` and mirrors Sprint-33's ``/api/jobs``
  scoping.  The page opts into the Sprint-36 ``r``-refresh via
  ``list_page: True`` in its template context.
- **`GET /api/queries?user_id=&status=&since=&limit=`** — JSON
  endpoint the page preloads from.  ``since`` accepts ``24h`` /
  ``7d`` / ``30d`` / ``all`` (anything else → no filter, never a
  400).  Admin-only scoping: a non-admin's ``user_id`` is
  clamped to their own ID.  Hard cap at 1000 rows even if the
  caller asks for more.
- **Editor prefill.** ``sql_editor.js`` now reads
  ``?prefill=<urlencoded sql>`` on mount and seeds the CodeMirror
  doc with it.  URL cleanup via ``history.replaceState`` so a
  page reload isn't a second re-run.  Pattern lifted verbatim
  from Sprint-27's ``prefill_notebook_path`` in ``pages/jobs.html``.
- **Navbar collapses Notebook/SQL.** The new "SQL" nav entry
  becomes a dropdown with *Editor* → ``/sql`` and *History* →
  ``/queries``.  ``g s`` still jumps to the editor;
  Sprint 50 adds ``g q`` chord for the history.
- Tests: 5 new service cases in ``tests/test_query_history.py``
  (happy record, failure-with-error-message, user+status
  filtering, reverse table lookup, count) plus 4 new route cases
  (execute writes succeeded history, parse-fail writes failed
  history, non-admin sees only own rows on ``/api/queries``,
  ``/queries`` page renders).

### Added (Sprint 49) — SQL editor MVP

- **`POST /api/sql/execute` + `GET /sql` page.** First Phase 12 sprint.
  A dedicated ad-hoc SQL surface next to the Notebook tab: the user
  types ``SELECT … FROM catalog.schema.table`` in a CodeMirror-6
  editor, presses :kbd:`Cmd+Enter`, and sees the result table
  inline.  No history, no save, no export, no EXPLAIN, no cancel
  yet — those land in Sprints 50-53.
- **`PQL.sql()` + DuckDB-only engine for SQL.** Phase-5's
  ``POINTLESSQL_DELTA_ENGINE`` still drives :meth:`PQL.table` reads,
  but ad-hoc SQL is hard-wired to DuckDB (``duckdb`` was already a
  dep).  The new :meth:`pointlessql.pql.pql.PQL.sql` is a
  :func:`staticmethod` that opens a fresh DuckDB connection per
  request, registers every referenced Delta table as a view, runs
  the query, caps the result at ``POINTLESSQL_SQL_MAX_ROWS`` (default
  10 000), and returns a JSON-friendly ``SQLResult`` dataclass.
- **sqlglot-based 3-part-reference parser + rewriter.** New
  ``pointlessql/pql/sql_parser.py`` parses the user's SQL once with
  ``sqlglot.parse(dialect="duckdb")`` and returns a ``PreparedSQL``
  carrying (a) the distinct ``catalog.schema.table`` references in
  first-appearance order and (b) a rewritten form where each 3-part
  reference is collapsed to a single quoted identifier.  DuckDB
  reserves ``main`` as a catalog name and refuses to bind 3-part UC
  references natively; the route registers each Delta view at
  exactly that quoted identifier so the rewrite binds.  CTE
  aliases, subquery aliases, and 2-part / 1-part references are
  handled correctly (skipped or rejected).
- **Per-table SELECT enforcement.** The route fetches
  ``storage_location`` + effective permissions from soyuz-catalog
  for every referenced table and calls :func:`check_privilege` with
  ``SELECT``.  Admin short-circuits per the Phase 7 behaviour.  A
  missing grant raises :class:`AuthorizationError`, which the
  Sprint-44 RFC 9457 handler renders as
  ``application/problem+json`` with ``required_privilege=SELECT`` +
  ``full_name`` extension members.
- **Audit on execute.** Every successful call writes a
  ``query.executed`` audit row (per ROADMAP's Sprint-48 follow-up:
  Phase 12 audit actions use the ``resource.verb`` convention).
  The ``target`` is a truncated-SHA256 hash of the SQL so identical
  queries from different users collapse into one reverse-lookup key
  without blowing out the audit row width; ``detail`` carries a
  dict with ``row_count``, ``duration_ms``, referenced ``tables``,
  and the ``truncated`` flag.
- **CodeMirror 6 via CDN import-map.** The new ``pages/sql_editor.html``
  loads ``@codemirror/state``, ``@codemirror/view``,
  ``@codemirror/lang-sql`` and ``@codemirror/theme-one-dark``
  straight from ``cdn.jsdelivr.net`` through a ``<script type=
  "importmap">`` — matches the existing Bootstrap/Alpine/htmx CDN
  strategy.  Vendoring is deferred until a CSP or offline-install
  requirement makes it necessary.
- **Navbar + shortcut.** New "SQL" entry in
  ``components/nav_links.html`` (between Notebook and Jobs; shown
  to every logged-in user, not admin-gated — everyone is allowed
  to query what they have ``SELECT`` on).  ``g s`` added to the
  command-palette chord registry (``components/command_palette.html``)
  so ``g s`` from any page jumps to ``/sql``.
- **Settings.** New :class:`pointlessql.settings.SQLSettings`
  sub-model.  ``POINTLESSQL_SQL_ENABLED`` (default ``True``),
  ``POINTLESSQL_SQL_MAX_ROWS`` (default 10 000), and
  ``POINTLESSQL_SQL_QUERY_TIMEOUT_SECONDS`` (default 60 — the
  timeout knob is declared now; wiring lands in Sprint 52).  Set
  ``POINTLESSQL_SQL_ENABLED=false`` and the ``/sql`` page renders
  a disabled placeholder while ``/api/sql/execute`` returns a
  400 ``sql_execution_error``.
- **New exception ``SQLExecutionError``.** ``status_code=400``,
  ``error_code="sql_execution_error"``.  Covers both parse-time
  rejections (multi-statement, non-SELECT, 2-part refs) and
  DuckDB's own runtime errors (unknown column, type mismatch, …).
  Both surface the message verbatim so the user can fix their
  query without guessing.
- **Deps.** Added ``sqlglot>=26.0`` (resolved to 30.4.3 at lock
  time).  CodeMirror is CDN-loaded; no Python-side dep needed.
- Tests: 13 new unit tests in ``tests/test_sql_parser.py`` covering
  single refs, joins, CTE aliases, subqueries, deduplication,
  no-table queries, bad-format rejection, and the DuckDB rewrite
  output shape.  8 new route tests in ``tests/test_sql_execute.py``
  covering admin happy path, non-admin-without-SELECT 403,
  non-admin-with-SELECT happy path, malformed SQL 400, 2-part
  rejection 400, row-cap truncation, zero-table SELECT 1, and
  ``/sql`` page render.

### Added (Sprint 48) — audit-log hardening

- **Append-only ORM guards.** :class:`AuditLog` ``before_update``
  and ``before_delete`` SQLAlchemy event listeners raise a new
  :class:`AuditIntegrityError`; every existing audit row is
  effectively immutable at the ORM layer. The retention cleanup
  path opens a :class:`~contextvars.ContextVar` (the
  ``_allow_audit_mutation`` scope) to bypass the delete guard —
  that's the only way to remove a row through the ORM. Raw SQL
  can still bypass; deployments that need true WORM should layer
  PostgreSQL ``REVOKE DELETE`` on top. Pattern ported verbatim
  from ``shoreguard-fresh/shoreguard/services/audit.py:46–115``.
- **Async audit writes.** :func:`api.main._audit` now dispatches
  the INSERT via :func:`asyncio.to_thread`, so request handlers
  never block on the audit DB round-trip. The rate-limit
  middleware's ``rate_limit.blocked`` hook uses the same async
  path. All 22 call sites in ``api/main.py`` were rewritten to
  ``await _audit(…)``.
- **Structured ``detail`` and richer columns.** Alembic ``011``
  widens ``audit_log.detail`` from ``String(2000)`` to ``Text``
  and adds ``client_ip`` (IPv4/IPv6, nullable) + ``actor_role``
  (``admin``/``user``/``system``, defaults to ``user``). The
  :func:`log_action` helper accepts a JSON-encodable dict for
  ``detail`` and JSON-encodes it; plain-string callers still
  work for backwards compatibility.
- **Retention policy.** New :class:`AuditSettings` sub-model
  exposes ``POINTLESSQL_AUDIT_RETENTION_DAYS`` (default 365) and
  ``POINTLESSQL_AUDIT_CLEANUP_INTERVAL_SECONDS`` (default 86 400).
  A lifespan-owned background task calls
  :func:`cleanup_old_entries` on that cadence; failures are
  logged and swallowed. Setting ``retention_days=0`` disables
  the sweep entirely (pre-Sprint-48 behaviour).
- **JSON + CSV export.** New ``GET /admin/audit/export?fmt=json|csv``
  endpoint mirrors the viewer's filter surface (``since`` / ``action`` /
  ``user`` / ``target``) and streams a filename-stamped attachment,
  capped at 10 000 rows per call. Two new "Export" buttons in the
  Sprint-41 viewer build the same query string so operators get
  "what you see is what you download".
- **Viewer surfaces new columns.** The admin-audit template gains a
  Role badge column (admin/user/system styling) and a compact IP
  column. Existing search/sort/chip behaviour ported over the new
  ``data-sort-*`` attributes.

### Fixed (Sprint 48, tests)

- ``tests/test_admin_audit.py`` + ``tests/test_rate_limit.py``
  migrated from ``MagicMock(secret_key=…)`` fixtures to real
  :class:`Settings` instances (Sprint 47 missed these two files),
  and both now pin their engines to ``StaticPool +
  check_same_thread=False`` so the Sprint-48 async audit writes
  can hand the factory to ``asyncio.to_thread`` without the
  worker seeing an empty in-memory DB.

### Fixed (Sprint 47) — test-suite regressions

- **In-memory SQLite test schemas survive the worker thread.**
  ``asyncio.to_thread``-backed code paths (``_build_home_summary``'s
  ``_db_block``) hit the engine from a separate thread, and the
  default ``QueuePool`` + ``sqlite:///:memory:`` combination gives
  each worker its own empty database — tests that touched ``/`` or
  ``/catalogs/…`` reported "no such table: jobs" even though the
  root-conftest ran ``Base.metadata.create_all``. Fix: pin every
  in-memory engine to ``StaticPool`` + ``check_same_thread=False``
  in ``tests/conftest.py`` and ``tests/test_auth_routes.py``. No
  production code changes.
- **403 enforcement tests match the rendered title case.**
  ``test_enforcement.py`` still asserted the pre-Sprint-30
  ``"Access Denied"`` title; the current 403 template renders
  ``"Access denied"`` (lowercase ``d``) via ``_STATUS_TITLES`` and
  hardcoded copy. Two assertions updated.
- **``test_list_tables`` matches the current soyuz-catalog-client
  wire format.** ``ListTablesResponse(identifiers=…)`` → ``tables=…``
  after the v0.2 rename (the production ``pql.list_tables`` already
  reads ``response.tables``).

### Added (Sprint 46)

- **Graceful JWT signing-key rotation.** Final Phase 11 hardening
  sprint. A new optional ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS``
  env var lets operators rotate the primary signing key without
  invalidating every outstanding session. New tokens are always
  signed with the primary key; ``verify_jwt`` tries the primary
  first and falls back to the previous key only if the primary
  rejects the token. Expired, tampered, or third-key tokens still
  fail under both. Rotation procedure:

  1. Set ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS`` to the *current*
     (old) key value.
  2. Change ``POINTLESSQL_AUTH_SECRET_KEY`` to the new value.
     Restart / recreate the container so both settings are picked
     up at the same time.
  3. Wait for ``jwt_expiry_hours`` (default 168 h = 7 d) so every
     live session has either re-logged-in or naturally timed out.
     During this window, fresh logins emit tokens signed with the
     new key while existing cookies continue to verify under the
     old.
  4. Drop ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS``. Any cookie
     still signed with the old key now fails verification and the
     user is bounced to ``/auth/login``.

  When ``secret_key_previous`` is unset (the default) the fallback
  path is disabled and a key change invalidates every live session
  immediately. Six new unit tests in ``tests/test_auth.py`` cover
  the happy path, fresh tokens during rotation, unknown keys,
  missing-fallback rejection, expiry preservation, and
  ``get_current_user``'s ``previous_key`` threading.

### Changed (Sprint 45) — BREAKING: nested Settings + renamed env vars

- **Flat `Settings` split into nine `BaseSettings` sub-models.** Fifth
  Phase 11 hardening sprint, porting the shoreguard-fresh nested-
  settings pattern 1:1.  Each sub-model owns its own ``env_prefix``:
  ``ServerSettings``, ``SoyuzSettings``, ``DatabaseSettings``,
  ``AuthSettings``, ``OIDCSettings``, ``LoggingSettings``,
  ``RateLimitSettings``, ``JupyterSettings``, ``SchedulerSettings``,
  ``DeltaSettings``.  Access moves from ``settings.secret_key`` to
  ``settings.auth.secret_key``, from ``settings.notebooks_dir`` to
  ``settings.jupyter.notebooks_dir``, etc.  Most environment
  variables are unchanged because the old flat prefix already
  overlapped — ``POINTLESSQL_RATE_LIMIT_*``,
  ``POINTLESSQL_SCHEDULER_*``, ``POINTLESSQL_OIDC_*``,
  ``POINTLESSQL_JUPYTER_*``, ``POINTLESSQL_SOYUZ_CATALOG_URL``,
  ``POINTLESSQL_LOG_LEVEL``, ``POINTLESSQL_LOG_FORMAT`` all still
  read the same value.  The breaking subset:

  | Old                                          | New                                              |
  | -------------------------------------------- | ------------------------------------------------ |
  | ``POINTLESSQL_HOST``                         | ``POINTLESSQL_SERVER_HOST``                      |
  | ``POINTLESSQL_PORT``                         | ``POINTLESSQL_SERVER_PORT``                      |
  | ``POINTLESSQL_BASE_URL``                     | ``POINTLESSQL_SERVER_BASE_URL``                  |
  | ``POINTLESSQL_DATABASE_URL``                 | ``POINTLESSQL_DB_URL``                           |
  | ``POINTLESSQL_SECRET_KEY``                   | ``POINTLESSQL_AUTH_SECRET_KEY``                  |
  | ``POINTLESSQL_JWT_EXPIRY_HOURS``             | ``POINTLESSQL_AUTH_JWT_EXPIRY_HOURS``            |
  | ``POINTLESSQL_ENGINE``                       | ``POINTLESSQL_DELTA_ENGINE``                     |
  | ``POINTLESSQL_NOTEBOOKS_DIR``                | ``POINTLESSQL_JUPYTER_NOTEBOOKS_DIR``            |
  | ``POINTLESSQL_NOTEBOOK_EXECUTE_TIMEOUT_SECONDS`` | ``POINTLESSQL_JUPYTER_EXECUTE_TIMEOUT_SECONDS`` |

  The ``docker-compose.yml`` and ``docker-compose.postgres.yml``
  default env blocks were updated in this sprint; the
  ``docker-compose.e2e.yml`` overlay accepts both the old and new
  ``BASE_URL`` name for a one-release transition.  Tests that built
  ``Settings`` with flat kwargs (``Settings(secret_key="…")``) must
  switch to nested dict kwargs (``Settings(auth={"secret_key":
  "…"})``).  The validator that anchors ``notebooks_dir`` to the
  startup CWD (BUG-28-02) and the ``oidc.enabled`` computed field
  both carried over unchanged — see ``pointlessql/settings.py`` for
  the new shape.

### Changed (Sprint 44) — BREAKING: error envelope shape

- **Error responses migrated to RFC 9457 `application/problem+json`.**
  Fourth Phase 11 hardening sprint. The previous nested envelope
  `{"error": {"code": "...", "message": "...", "request_id": "..."}}`
  is replaced by a flat top-level body `{"type": "about:blank",
  "title": "<status title>", "status": <code>, "detail": "<message>",
  "code": "<identifier>", "request_id": "..."}` served with
  `Content-Type: application/problem+json`. Domain `AuthorizationError`
  surfaces its `required_privilege`, `securable_type`, and `full_name`
  as RFC 9457 extension members; FastAPI's `RequestValidationError`
  flows through the same envelope with an `errors` array extension.
  API clients that read the old nested `.error.code` / `.error.message`
  fields must switch to top-level `.code` / `.detail`. The only known
  clients — PointlesSQL's own frontend via `frontend/js/api.js` and
  two Alpine templates — were updated in the same sprint.

### Added (Sprint 44)

- **HTMX toast bridge for inline errors.** Non-boosted HTMX fragment
  requests (`HX-Request: true` without `HX-Boosted: true`) that raise
  a domain error now receive an empty body at the real error status
  plus an `HX-Trigger` header carrying a `pqlToast` event. A
  `base.html` listener forwards level + message + request_id into the
  existing Sprint-30 `window.pqlToast.error` API so the user sees an
  inline Bootstrap toast without losing the current page. Boosted
  navigations keep the branded HTML error page so htmx can still swap
  `#main-content`. The primary consumer is the upcoming Phase-12 SQL
  editor: a failed query can now surface as a toast without the
  editor losing focus.
- **Three new domain exceptions.** `SchedulerError` (scheduler
  plumbing failures pre-notebook-run), `NotebookRenderError`
  (nbconvert failures, previously misclassified as generic
  `EngineError`), and `PQLWriteError` (subclasses `EngineError` so
  existing catches keep working, but its own code lets the UI
  distinguish write failures from read/compute failures).
  `services/notebook_render.py` now raises `NotebookRenderError`
  instead of `EngineError`; `tests/test_notebook_render.py` updated.
- **Playbook `docs/e2e-walkthroughs/error-handling.md`** covers
  problem+json media type on `/api/*`, HTMX toast trigger without
  page swap, boosted-navigation HTML fallback, and 403 extension
  members.

### Added (Sprint 43)

- **Rate limiting on `/auth/*`.** Third Phase 11 hardening sprint. A
  new `rate_limit_middleware` enforces per-IP and per-email fixed-
  window caps on the auth surface: 10/10min per IP + 5/10min per
  submitted email on `POST /auth/login`, 5/1h per IP on
  `POST /auth/register`, and a shared 20/10min per-IP bucket across
  `GET /auth/sso` + `GET /auth/callback`. Buckets live in a new
  `rate_limit_events` table (Alembic migration `010`) so the limiter
  ships with zero new runtime dependencies — no Redis, no slowapi,
  no background sweeper. Opportunistic cleanup inside every check
  `DELETE`s rows older than the window, and the composite
  `(bucket, created_at)` index covers both the count and the
  delete. The middleware sits between CSRF (outer) and auth (inner)
  so cross-site forged floods still fail the cheap CSRF check
  before they can burn a slot, while CSRF-clean abuse is caught
  before bcrypt + JWT-decode run on every attempt. Rejections
  return 429 with a `Retry-After` header and emit an
  `audit_log` row with `action="rate_limit.blocked"` so the
  Sprint-41 `/admin/audit` viewer surfaces the feature without a
  second dashboard. The `rate_limit_trust_x_forwarded_for` setting
  defaults OFF and must be flipped on explicitly behind a known
  reverse proxy — otherwise any client could forge the header and
  escape the per-IP bucket; the per-email axis still catches
  distributed attacks that probe one account from many IPs. New
  playbook `docs/e2e-walkthroughs/rate-limit.md` and
  `tests/test_rate_limit.py` cover login + register + OIDC floors,
  window expiry, the `/healthz` and `/api/*` exemptions, body
  re-injection, and the audit hook.

### Added (Sprint 42)

- **CSRF protection for HTML form routes.** Second Phase 11 hardening
  sprint. A new `csrf_middleware` implements the OWASP
  double-submit-cookie pattern: every request without a `pql_csrf`
  cookie gets one (`HttpOnly`, `SameSite=Lax`, matches the JWT
  cookie's `max_age`), and every non-safe method outside `/api/`,
  `/static/`, or `/healthz` must echo that cookie back via either a
  `csrf_token` form field or an `X-CSRF-Token` header. The
  `base.html` HTMX hook auto-attaches the header for every
  boosted request from the `<meta name="csrf-token">` tag, so
  existing HTMX flows pick up protection with zero per-route edits.
  A new `{{ csrf_input() }}` Jinja macro wires the three non-boosted
  forms (login, register, logout). Token rotates on local-login,
  OIDC-login, and logout to prevent fixation; failed login keeps the
  existing cookie so retry works without a page reload. New playbook
  `docs/e2e-walkthroughs/csrf.md` and `tests/test_csrf.py` cover
  cookie issuance, both submission paths, rotation, the `/api/*`
  exemption, and body re-injection so downstream handlers still see
  posted fields.

### Added (Sprint 41)

- **Admin audit-log viewer at `/admin/audit`.** First sprint of
  Phase 11 (Hardening). The Sprint-7 `audit_log` table has been
  write-only since it landed; Sprint 41 adds the read side. Admins
  get a filterable, newest-first list view that reuses the `/jobs`
  `listTable` Alpine component, the `pql-list-*` CSS, and the
  existing `_require_admin` gate — no new frontend primitives. The
  route supports four server-side filters (`since=24h|7d|30d|all`,
  `action=`, `user=` substring, `target=` substring) plus a client-
  side "Mine only" chip. A new Alembic migration `009` adds
  `ix_audit_log_created` so the cross-user "latest N" ordering
  query has a supporting index. New "Admin" dropdown in the top
  navbar (admin-only, gated in `components/nav_links.html`)
  anchors the `/admin/*` namespace that Phase 11's remaining
  sprints will extend. New playbook
  `docs/e2e-walkthroughs/admin-audit.md` replays the flow.

### Changed

- **`ROADMAP.md`.** Opened ⏳ entries for four forward-looking
  phases with a deliberate sequence: hardening first, features
  second, public launch last. **Phase 11 (Hardening)** — CSRF
  on HTML forms, rate limiting on `/auth/*` and future
  `/api/sql/*`, graceful `secret_key` rotation, admin audit-log
  viewer reusing the `/jobs` list-table machinery.
  **Phase 12 (SQL editor + query history)** — CodeMirror `/sql`
  page, DuckDB-only `PQL.sql()` with sqlglot-based table
  resolution, `query_history` + `query_history_tables` Alembic
  migration, saved queries, export, EXPLAIN, `g s` shortcut.
  **Phase 13 (Agent workloads — sketch)** —
  `paperclip-adapter-pointlessql` companion repo, new
  `agent_run` job kind, `X-Principal`-into-sandbox for UC
  enforcement on agent queries, read-only `/agents` discovery
  page; plus two uncommitted follow-ons (ontology / Foundry-
  lite; OSINT pattern playbook). **Phase 14 (Public launch +
  external distribution — queued last)** — GHCR private→public
  flip + Phase-10-deferred packaging replay, multi-arch builds,
  public PyPI publish, optional Helm chart, positioning /
  license decisions. Phase 14 is deliberately queued for the
  end per the Phase 10 retrospective ("release engineering
  against a private audience generates self-inflicted
  friction"). No code touched — these entries anchor scope
  discussed in-session so later sessions pick up where this
  one left off.

## [0.1.0rc3] - 2026-04-18

### Added (Sprint 40)

- **`.github/workflows/docker.yml`.** On-tag image publish to
  GHCR. Builds both the PointlesSQL image (from `Dockerfile`) and
  the soyuz-catalog image (from `Dockerfile.soyuz` with a
  `build-contexts: soyuz-catalog=soyuz-catalog` overlay pointing at
  a just-cloned soyuz-catalog checkout). Pushes to
  `ghcr.io/flohofstetter/pointlessql:<tag>` and
  `ghcr.io/flohofstetter/soyuz-catalog:<pinned-soyuz-tag>`. The
  soyuz tag is parsed from `pyproject.toml`'s `[tool.uv.sources]`
  at workflow time so no hard-coded version lives in CI. A
  `verify-soyuz-tag-exists` step does `git ls-remote` with
  `SOYUZ_READ_TOKEN` before building — fails fast on a
  never-pushed tag, guarding against the Sprint 37 `v0.2.0rc1`
  failure mode. Prerelease tags (`rc*`, `a[0-9]*`, `b[0-9]*`,
  `dev[0-9]*`) do not get the `:latest` alias, matching the
  `release.yml` regex.
- **GHCR image labels.** Both `Dockerfile` and `Dockerfile.soyuz`
  grew `ARG VCS_REF` / `ARG VERSION` + `LABEL
  org.opencontainers.image.{source,revision,version,title,
  description,licenses}` on the runtime stage. `docker.yml`
  passes `--build-arg VCS_REF=${github.sha} --build-arg
  VERSION=${github.ref_name}`. The `source` label is what GHCR
  uses to link the package to the repo sidebar.
- **`docs/install.md`.** First formal install guide. Three
  flavours: Docker + GHCR images (recommended primary), pip
  install from git tag, source checkout for contributors. Each
  ends with an "expected state" assertion and a troubleshooting
  section calls out the usual landmines — `DOCKER_BUILDKIT=0`
  silently dropping `--mount=type=secret`, fine-grained PAT
  requiring per-repo grants vs. classic-PAT scopes just working,
  stale `/app/data` SQLite after a version bump.
- **`docs/e2e-walkthroughs/packaging.md`.** Eleventh playbook —
  the clean-machine flow. Preconditions assert the Sprint 40 tag
  has shipped and images exist on GHCR. Steps: `cd
  "$(mktemp -d)"`, assert anonymous `docker pull` fails
  (proves the images are private), `docker login ghcr.io`, re-pull
  succeeds, `curl` the compose file at the tag, `sed` flips
  `build:` → `image:`, `docker compose pull && up -d`, healthcheck
  poll, Playwright MCP `browser_navigate` asserts the home-page
  Welcome `<h1>`, `docker image inspect` confirms
  `org.opencontainers.image.source` labels, teardown. Found-bugs
  section left with the `(none at time of writing — fill in
  during the first live replay)` placeholder that matches
  Phase 7/8/9 convention. Index in
  `docs/e2e-walkthroughs/README.md` grew a third section
  (`Packaging`).

### Changed (Sprint 40)

- **`Dockerfile` dual auth.** The single `--mount=type=ssh` RUN
  grew a second mount: `--mount=type=secret,id=gh_pat`, both
  `required=false`. Inline shell branch prefers the token if
  `/run/secrets/gh_pat` is non-empty, else falls back to the
  ssh-agent path. Sprint 38's `docker compose build --ssh default`
  contributor flow still works; the new `GH_PAT=$(gh auth token)
  docker compose build` path is what CI + clean-machine users hit.
- **`docker-compose.yml`.** The `pointlessql` service's `build:`
  block grew `secrets: - gh_pat` alongside the existing `ssh:
  [default]`; a top-level `secrets: gh_pat: { environment:
  GH_PAT }` block wires the env var to the BuildKit secret file.
  Each service also grew a commented `# image: ghcr.io/…:<tag>`
  line above its `build:` block with a two-line explainer so
  clean-machine users can flip to the pull path with a
  comment-out-and-uncomment edit.
- **`README.md` quickstart.** "Quick start (Docker + GHCR
  images)" is now the primary top-level install path — `docker
  login ghcr.io` → `curl docker-compose.yml` → flip two lines →
  `docker compose pull && up`. The `../soyuz-catalog` sibling
  prerequisite is gone from this section. Source-build demoted to
  "Quick start (local development)" below it; both sections
  cross-link to `docs/install.md`.
- **`CLAUDE.md`.** "Docker builds" subsection rewritten for
  dual-auth; new "GHCR images" subsection documents the on-tag
  publish pipeline + the PAT-based pull flow. "Replaying the e2e
  walkthroughs" bumped playbook count ten → eleven.

### Docs (Sprint 40)

- **`ROADMAP.md`.** Sprint 40 flipped to ✅. Phase 10 flipped to
  ✅ done. Phase 10 close-out block added following the
  Phase 7/8/9 shape: what the phase bought (clean `git clone &&
  uv sync` for source, clean `docker login && compose pull && up`
  for users, every future release cuts a GH Release plus two
  GHCR images automatically), plus Deferred-to-Phase-11 list
  (multi-arch arm64, PyPI publish, Helm chart, public-GHCR flip).

## [0.1.0rc2] - 2026-04-18

### Fixed (Sprint 38 follow-on)

- **Dual-mode dev toggle.** The documented escape hatch — dropping
  a gitignored `uv.toml` with a `[sources]` block to flip
  `soyuz-catalog-client` to the sibling `../soyuz-catalog`
  checkout — was rejected by `uv` with `error: Failed to parse:
  uv.toml. The sources field is not allowed in a uv.toml file.
  sources is only applicable in the context of a project`. The
  mechanism never actually worked; Sprint 38's smoke test only
  covered the default-pinned path. Replaced with two helper
  scripts, `scripts/use-editable-soyuz.sh` and
  `scripts/use-pinned-soyuz.sh`, that swap `[tool.uv.sources]` in
  `pyproject.toml` in-place. The swap intentionally leaves the
  tree dirty so the escape-hatch state stays visible. `.gitignore`
  loses its `uv.toml` stanza (the mechanism is gone); `CLAUDE.md`
  "Wiring soyuz-catalog" rewrites the editable-hatch section.

### Changed (Sprint 39 follow-on — CI)

- **`.github/workflows/test.yml` + `release.yml`.** Torn out the
  broken sibling-checkout + `uv.toml`-drop construction. Both
  workflows now consume the private `soyuz-catalog` dep the same
  way a local checkout does: `uv sync` resolves the pinned
  `[tool.uv.sources]` git-tag source, authenticated by a single
  `git config --global url."https://x-access-token:${SOYUZ_READ_TOKEN}@github.com/".insteadOf "https://github.com/"`
  step before `uv sync`. Removed: the debug curl-probes step, the
  raw `git clone --branch v0.2.0rc2 …` sibling-checkout step, the
  `cat > uv.toml <<EOF [sources] …` override step, and every
  `working-directory: PointlesSQL` (the main checkout lives at
  the default path again).
- **`SOYUZ_READ_TOKEN` preflight.** Added a 2-check gate step
  before `uv sync`: length ≥ 30 bytes (catches empty/truncated
  paste) and `GET https://api.github.com/user` returning 200
  (catches a revoked, expired, or typo'd PAT). Fails with a
  `::error::` annotation whose prose tells the maintainer exactly
  where to re-paste. No token material is echoed. Cost is one
  HTTPS request per run; saves a minute of dep resolution on
  every bad-secret state.
- **Alembic gate needs a migrated target.** `alembic check` on a
  fresh runner produced `FAILED: Target database is not up to
  date.` — the runner has no `pointlessql.db`, so `check` has
  nothing to compare the ORM models against. Workflows now run
  `alembic upgrade head` before `alembic check` so the sqlite
  file exists at the latest revision. Locally unchanged — the
  developer's working DB is already at head.

### Notes on external fix (SOYUZ_READ_TOKEN)

The previous org-secret values were all rejected by GitHub
(the first at `3ceaf45` was 1 byte; the later re-pastes were
40-byte strings that GitHub returned HTTP 401 for on
`/user`). The 16-commit `fix(ci)` investigation on main was
this plus the `uv.toml` bug tangled up. Resolved by pasting a
freshly-generated fine-grained PAT with `Contents: Read` on
`FloHofstetter/soyuz-catalog` into the repo secret. File
content unchanged.



### Added (Sprint 39)

- **`cliff.toml`.** git-cliff template keyed to PointlesSQL's
  Conventional Commit scopes (`feat(ui)`, `fix(ui)`,
  `build(packaging)`, `docs(roadmap)`, `fix(alembic)`, …). Drives
  the release-notes body in `release.yml`.
- **`scripts/bump-version.sh`.** Single-`pyproject.toml` variant
  of soyuz-catalog's Sprint 19 bump-script. Guards: PEP 440
  syntax, clean tracked-file tree, on-main, tag-not-exists. In-
  place version bump, `uv lock`, anchored `[Unreleased]` →
  `[X.Y.Z] - <date>` flip in CHANGELOG.md (hand-written prose
  preserved verbatim), `chore(release): vX.Y.Z` commit, annotated
  tag. Does not push.
- **`.github/workflows/test.yml`.** First CI this repo has had.
  Jobs: ruff, pyright, pydoclint (Google), `alembic check`.
  Pytest stays out per the standing sprint-gate discipline.
  Private soyuz-catalog git-dep pulled via a `SOYUZ_READ_TOKEN`
  org-secret URL rewrite.
- **`.github/workflows/release.yml`.** On-tag `v*`. Runs the
  gate, `uv build`s the wheel + sdist, asserts the wheel carries
  `pointlessql/_frontend/` (force-included) and
  `pointlessql/alembic/versions/`, generates release-notes via
  `uvx git-cliff --latest --strip all`, and `gh release create`s
  with `--prerelease` auto-toggled on PEP 440 `rc*` / `a*` / `b*`
  / `dev*` shapes.

### Fixed (pre-Sprint-39 cleanup)

- **Alembic autogen drift.** `uv run alembic check` had been
  flagging six `remove_index` operations + one `add_constraint`
  on every run — the indexes were declared in migrations
  001/002/003/004/006 but never mirrored into the ORM models, so
  autogen wanted to drop them on every comparison. Declared each
  index in the owning model's `__table_args__`, including the
  partial unique `ix_users_oidc_identity`
  (`WHERE oidc_provider IS NOT NULL`) via dialect-specific
  `sqlite_where=` / `postgresql_where=` kwargs. No migration
  written — this is a model-side fix for latent drift; nothing
  in the database changes. Gate now green, so the new alembic-
  check CI step lands on solid ground.

### Changed (Sprint 38)

- **`pyproject.toml`.** `[tool.uv.sources]` swapped from an
  editable path dep (`../soyuz-catalog/soyuz-catalog-client`) to a
  private-repo git-tag pin
  (`git = "https://github.com/FloHofstetter/soyuz-catalog", tag = "v0.2.0rc2", subdirectory = "soyuz-catalog-client"`).
  First sprint where `git clone && uv sync` works on a clean
  host without a sibling `../soyuz-catalog` checkout.
- **`uv.lock`.** Regenerated against the git pin; the client is
  resolved from
  `source = { git = "…?subdirectory=soyuz-catalog-client&tag=v0.2.0rc2#<sha>" }`.
- **`Dockerfile`.** Collapsed from 3 stages to 2. The
  `soyuz-client-builder` stage and the sed-strip on
  `[tool.uv.sources]` are gone. The remaining builder stage
  fetches the client wheel over git via BuildKit
  `--mount=type=ssh`, reusing the contributor's ssh-agent. Sprint
  40 will replace this with GHCR image pulls and
  `--secret`-based `GH_TOKEN` auth.
- **`docker-compose.yml`.** `additional_contexts.soyuz-catalog`
  (only fed the now-removed Stage 1) replaced with
  `build.ssh: [default]` so `docker compose build` forwards
  ssh-agent to BuildKit. Invoke with
  `docker compose build --ssh default pointlessql`.
- **`CLAUDE.md`.** "Wiring soyuz-catalog" section rewritten.
  Default clean-machine flow documented first; the editable
  escape hatch (drop a gitignored `uv.toml` at repo root with
  `[sources] soyuz-catalog-client = { path = …, editable = true }`)
  documented second. Docker `--ssh default` requirement called
  out with a Sprint 40 forward-reference.
- **`.gitignore`.** `uv.toml` added so contributors' editable
  overrides never land in commits.

### Added (Sprint 37)

- Phase 10 (Packaging & private distribution) opened in
  [`ROADMAP.md`](ROADMAP.md). Distribution contract locked in as
  private GitHub tags over `[tool.uv.sources]` git-subdirectory
  pins; no public PyPI.
- Sprint 37 — forward-pulled soyuz-catalog Sprint 19 release
  engineering. Lands in the sibling repo `../soyuz-catalog/` at
  commit `be9c5c6`: `cliff.toml`, `scripts/bump-version.sh`
  (lockstep version bump + CHANGELOG `[Unreleased]` flip +
  annotated tag, does not push), and
  `.github/workflows/release.yml` (on-tag; runs the existing
  `check_client_drift.sh` gate, builds server + client wheels +
  sdists, attaches all four to the GitHub Release with git-cliff
  release notes).
- First tag cut in soyuz-catalog: `v0.2.0-rc1`. Sprint 38 will
  pin PointlesSQL's `soyuz-catalog-client` source against it,
  retiring the editable path-dep that currently blocks
  clean-machine `uv sync`.

### Added (Sprint 36)

- New `frontend/js/api.js` exposes `window.pqlApi.fetch(url, init)`
  returning `{ok, status, data, error}` and auto-emitting a
  `window.pqlToast.error(...)` on non-ok responses (opt out with
  `init.silent = true`). Soyuz error bodies have their `detail` /
  `message` / `error` field extracted; network failures report
  `status: 0`. Also exposes `pqlApi.reloadWithToast(message, opts)`
  for the toast-then-reload pattern (400 ms default delay).
- Migrated five Alpine components off their hand-rolled
  `fetch` + try/catch/error-string blocks onto `pqlApi.fetch`:
  `editable`, `properties_editor`, `tags_editor`, `permissions_editor`
  (including the `silent: true` effective-permissions background
  GET), and the four `federation.js` create/delete forms. The
  inline `this.error` hints stay; the toast fires on top so
  mutations fail loudly instead of burying the error in a tiny
  red span.
- Replaced every silent `window.location.reload()` after a
  mutation with `pqlApi.reloadWithToast(...)` — `job_row_actions`,
  `/jobs` create modal, `/jobs/{id}` run/pause/resume, the
  `/dashboards/{slug}` Refresh button, and the `sync_history_card`
  Sync-now button each surface a success/info toast before the
  400 ms reload.
- Expanded the Sprint-31 command-palette Alpine component into a
  keyboard-shortcut registry. The hard-coded help-modal `<dl>` now
  iterates a `shortcuts` array with `{keys, combiner, label}`
  entries. New bindings: `g h` / `g j` / `g d` Vim-style chords
  (go home / jobs / dashboards) with a 1 s pending window; `r`
  reloads the current list page when `<body data-pql-refresh="1">`
  is set. Editable-target and modifier guards match the existing
  `?` handler.
- Plumbed `list_page: True` through the five list-route template
  contexts (`/jobs`, `/dashboards`, `/connections`,
  `/external-locations`, `/credentials`); `base.html` renders
  `data-pql-refresh="1"` on the `<body>` when the flag is set, so
  `r`-to-refresh opts in without touching each page template.
- Global `:focus-visible` rule in `style.css` gives every
  focusable element the same 2 px accent outline. The Sprint-33
  `.pql-sortable:focus-visible` rule is kept for its tighter
  offset. A new `@media (prefers-reduced-motion: reduce)` block
  zeroes the `--pql-duration-*` tokens and forces
  `animation-duration: 0ms` + `transition-duration: 0ms` on
  every element so Bootstrap fades, Alpine x-transitions, and
  the offcanvas slide all respect the user preference.
- New playbook `docs/e2e-walkthroughs/ux-overhaul.md` covering
  shortcut chords, the toast flow (error → red toast, success →
  toast-then-reload), focus rings, and the reduced-motion branch.

### Added (Sprint 35)

- Breakpoint tokens `--pql-breakpoint-sm/md/lg/xl` (640 / 768 /
  1024 / 1280 px) added to the Sprint-29 token block. Reference
  values only — CSS `@media` rules cannot consume `var()`, so
  every media query in `style.css` repeats the literal; the token
  block is the canonical contract, documented in
  `docs/design-tokens.md`.
- `components/nav_links.html` extracts the inline base.html
  `<ul class="navbar-nav">` so the same link set renders in the
  top navbar at `>=640 px` and again as a "Navigation" footer
  inside the existing `offcanvas-md` sidebar drawer at `<640 px`.
  One hamburger, not two — the scope's separate `<640 px`
  hamburger was merged into the existing sidebar toggle.
- `listTable()` gains a `mobileSort: boolean` config flag. When
  true, mount renders a `.pql-list-sort-mobile <select>`
  (hidden at `>=sm`) populated from every sortable `<th
  data-sort-key>` with asc / desc options. A new
  `_onMobileSort(raw)` method sets `sortKey` + `sortDir` in one
  pick, complementing the tri-state desktop header cycle. Wired
  up on jobs, dashboards, external-locations, and the Sprint-34
  Columns card.
- CSS-only card transform at `<640 px`: `.pql-list-table` rows
  collapse into 2-column label / value stacks, with each `<td>`'s
  `data-label="…"` rendered as an uppercase key via
  `::before`. Applied to the four `listTable()` pages plus the
  Sprint-34 Schemas / Tables / Preview / Columns cards. Row-
  action cells opt out of the key rendering (no `::before`) and
  stay right-aligned.
- `.pql-notebook-mobile-notice` banner above the Jupyter iframe
  at `<768 px` — "JupyterLab is optimised for desktop…". The
  iframe itself stays mounted; the notice is a heads-up, not a
  blocker.
- Touch-target baseline `min-height: 44px` under
  `@media (hover: none)` for buttons, links, inputs, selects,
  chips, sortable headers. Scoped to touch-only devices so
  hover-capable laptops keep the compact Sprint-33 spacing.
- New playbook `docs/e2e-walkthroughs/mobile.md` exercising
  phone (375 × 812) / tablet (768 × 1024) / desktop (1280 × 800)
  viewports via `browser_resize` + `browser_navigate`; found-
  bugs section filled in clean.

### Added (Sprint 34)

- Catalog detail page (`/catalogs/{c}`) gains an inline Schemas card.
  Populated by `client.list_schemas` folded into the existing
  `asyncio.gather`; shows name (linked to schema detail), updated,
  and comment. Per-schema table counts were dropped from the original
  scope to avoid O(N) fan-out to soyuz-catalog — `schema.updated_at`
  alone keeps the card useful without the extra round-trips.
- Schema detail page (`/catalogs/{c}/schemas/{s}`) gains an inline
  Tables card with name (linked to table detail), type, format, column
  count, updated, and comment — sourced from the existing
  `list_tables` bypass path that already returns full `TableInfo`
  payloads.
- Table detail page (`/catalogs/{c}/schemas/{s}/tables/{t}`) gains a
  Preview card. New `GET /api/catalogs/{c}/schemas/{s}/tables/{t}/preview`
  runs `PQL().table(...)` inside `asyncio.to_thread` under the
  caller's `X-Principal`, caps at 10 rows server-side (no
  client-tunable `?limit=`), emits `Cache-Control: no-store` so row
  data does not persist in the browser disk cache after a permission
  revocation, and degrades to a single-card error banner on any
  engine/Delta failure instead of 500-ing the page. Engine-agnostic
  via a `_preview_head` helper that keeps DuckDB lazy
  (`rel.limit(n).df()`) and coerces polars through `to_pandas()`.
  Values flow through `fastapi.encoders.jsonable_encoder` so Decimal,
  datetime, bytes, and numpy scalars serialise cleanly.
- Columns table on the table detail page gains client-side search +
  sort via Sprint-33 `listTable()` when `columns|length >= 20`.
  Sortable keys: position, name, type, nullable. Below the threshold
  the table stays server-rendered unchanged (progressive enhancement).
- Lineage card (`components/lineage_card.html`) now groups upstream
  and downstream nodes by depth under per-depth subheadings
  ("Depth 1", "Depth 2", …) instead of a flat `sort(depth)` list
  with padding-left indent. The per-node depth badge stays —
  redundant-but-defensive survives a future collapse/filter. Node
  links (3-part `catalog.schema.table` names → table detail) were
  already present from an earlier sprint and are unchanged.
- "Open in notebook" button on the PQL snippet card (admin-only).
  New `POST /api/catalogs/{c}/schemas/{s}/tables/{t}/open-in-notebook`
  sanitises identifiers with `re.sub(r"[^A-Za-z0-9_-]", "_", …)`,
  appends `secrets.token_hex(3)` to defeat double-click filename
  collisions, writes an `nbformat.v4` notebook (markdown header +
  a `pql.table(...)`-pre-filled code cell) to
  `{notebooks_dir}/scratch/…`, re-validates the path via
  `resolve_upload_target` to block traversal escapes, and returns a
  `lab_url` the Alpine handler navigates to with
  `window.location.assign`. Writes an `open_in_notebook` audit entry.
- `notebook_workspace` skip-list extended: `scratch/` joins `runs/`
  as a top-level directory excluded from `list_workspace_tree` so
  machine-generated scratch notebooks never pollute the
  user-authored workspace view. Skip logic rewritten to match by
  name against a `_SKIP_TOP_LEVEL_DIRS` frozenset scoped to the
  notebooks root — same behaviour as before for `runs/`, adds
  `scratch/` without duplicating the absolute-path equality check.

### Added (Sprint 33)

- Shared `frontend/js/list_table.js` — `window.listTable(config)`
  Alpine factory that adds debounced (150 ms) client-side search,
  sortable column headers (asc → desc → none, driven by `aria-sort`
  + a CSS pseudo-element arrow so no className juggling is required),
  and optional filter chips on top of any Bootstrap `<table>` whose
  rows carry `data-search` + `data-sort-<key>` attributes.
  Progressive enhancement — rows stay rendered server-side and the
  page is still usable if JS never runs.
- Applied `listTable` to `/jobs`, `/dashboards`, `/connections`,
  `/credentials`, `/external-locations`. Chips configured per page:
  `Paused` + `Last run failed` on jobs, `Has bound job` on
  dashboards, one chip per distinct `connection_type` on
  connections, one chip per distinct `purpose` on credentials,
  none on external-locations.
- `frontend/js/humanize_cron.js` — `window.pqlHumanizeCron(expr)`
  turns the common 5-field cron shapes + the six `@`-macros into
  human-readable strings ("Daily at 00:00", "Weekly on Monday at
  08:30"), falls back to the raw expression for anything the helper
  doesn't recognise. Applied on the `/jobs` list Cron cell and the
  `/jobs/{id}` detail Configuration card; the cell's `title`
  attribute still shows the raw expression for hover tooltips.
- `frontend/js/relative_time.js` — extracted the Sprint 32 inline
  `window.pqlRelativeTime` helper into its own file so the
  `/jobs` "last run" column can reuse it without duplicating code.
  `home.html`'s local copy is now a one-line pointer comment; the
  helper's behaviour is unchanged.
- `GET /api/jobs` now emits `last_run_status`, `last_run_at` and
  `last_run_duration_s` per job. Populated by a new
  `_latest_run_per_job(session, job_ids)` helper that fetches the
  latest run per job in one round-trip via a `group_by(job_id)` +
  `max(started_at)` subquery, portable across SQLite and Postgres
  and riding the existing `(job_id, started_at)` index on
  `JobRun`. The same map also feeds the server-rendered `/jobs`
  row rendering.
- `/jobs` rows gain a "Last run" column — a
  `.pql-status-dot--{status}` + `pqlRelativeTime(iso)` pair
  mirroring the home dashboard's latest-runs table. Rows with no
  runs yet show `—`.
- Hover quick-actions on `/jobs` rows (admin-only) — a trailing
  `<td class="pql-row-actions">` whose buttons are revealed on
  `tr:hover` and `tr:focus-within` (always visible on touch
  devices via `@media (hover: none)`). "Run now" POSTs to the
  existing `/api/jobs/{id}/run`; "Pause" / "Resume" POSTs to
  `/pause` or `/unpause`. Both fire through `window.pqlToast` for
  the success/error banner and reload 400 ms later, matching the
  Sprint-36-direction already established by Sprint 32.
- `frontend/js/job_row_actions.js` — `window.jobRowActions({jobId,
  paused})` Alpine factory backing the new row-action buttons.
- CSS additions in `frontend/css/style.css`: `.pql-list-controls`,
  `.pql-chip` + `.pql-chip--active`, `.pql-sortable` with arrow
  pseudo-element, `.pql-row-actions` with hover/focus-within
  reveal.
- `docs/e2e-walkthroughs/list-polish.md` — Playwright MCP playbook
  covering search debounce, sortable cycle, chip AND-ing, cron
  humanization + raw-title tooltip, last-run column rendering,
  hover-reveal + toast-then-reload on Run-now / Pause, the
  non-admin column gating, the four other flat list pages, the
  `/api/jobs` JSON shape, and a Sprint-32 relative-time
  regression check.

### Added (Sprint 32)

- Home dashboard — the `/` route (formerly the welcome hero in
  `pages/catalogs.html`) is now a real dashboard. Welcome header,
  7-day success-rate sparkline (inline SVG, no Chart.js),
  10 most-recent job runs with status dots, a Recent catalogs card
  driven by `localStorage['pql.recentCatalogs']`, Your-dashboards
  card (owner-scoped), and a Quick actions cluster that keeps the
  admin-only "Create foreign catalog" modal reachable.
- 3-step onboarding checklist empty-state — shown only when the
  current user has no visible catalogs, no jobs, and no dashboards;
  suppressed when soyuz is unavailable so users whose data is fine
  are not told to "connect a data source". Admin gets the inline
  Create-foreign-catalog button; non-admin sees an
  "ask an admin" hint.
- `GET /api/home/summary` — one round-trip for every server-side
  card. Returns `{user, catalogs, jobs, dashboards, latest_runs,
  sparkline, onboarding}`. Soyuz `list_catalogs()` runs in parallel
  with the local DB work via `asyncio.gather` + `asyncio.to_thread`;
  a `CatalogUnavailableError` downgrades to `catalogs.unavailable =
  true` with a 200 response so the page still renders every local
  card. Visibility mirrors `/api/jobs` (latest_runs + sparkline
  filter `Job.run_as_user_id == user.id` for non-admins).
- Catalog-visit instrumentation in `base.html` — any page that
  threads `active_catalog` (catalog/schema/table detail) writes
  `{name, ts}` into `localStorage['pql.recentCatalogs']`, deduped
  by name, capped at 5. Pattern mirrors the Sprint-31 palette's
  `pql.recentSearches` writer.
- Sparkline CSS in `frontend/css/style.css` uses three semantic
  tints (`--pql-color-success-fg` / `--pql-color-warning-fg` /
  `--pql-color-danger-fg`) plus a neutral empty-day style, so the
  prepared light-mode variant comes for free. Bars have a 2 px
  floor and a nested `<title>` tooltip for native hover.
- `.pql-status-dot--{succeeded,failed,running,pending,skipped}` —
  compact status indicators reused by the latest-runs table.
- `pages/home.html` + `components/create_foreign_catalog_modal.html`
  (extracted from the old welcome page; the modal markup itself is
  unchanged). `pages/catalogs.html` deleted — `/` was its only
  caller. The Sprint-22 `catalog-browsing.md` playbook's step 1 was
  updated to assert the new Quick actions counter instead of the
  old `N catalogs available` pill.
- `docs/e2e-walkthroughs/home.md` — Playwright MCP playbook
  covering the twelve home-page assertions including the soyuz-down
  degradation (verified 200 + `catalogs.unavailable=true` + banner +
  local cards still render), the visit-tracking instrumentation,
  and the system-empty onboarding trigger.

### Fixed (Sprint 32, same-commit from playbook replay)

- **BUG-32-01**: the sparkline SVG didn't render because Alpine's
  `<template x-for>` inside `<svg>` fails — `<template>.content`
  is an HTML-namespaced DocumentFragment, so inner `<rect>` elements
  were parsed as unknown HTML and never bound. Surfaced as
  `ReferenceError: d is not defined` / `Document.importNode:
  Argument 1 is not an object.` in the browser console on first
  load. Fixed by computing `bar_height`, `bar_class`, and
  `bar_title` server-side in `_build_home_summary` and rendering
  the seven `<rect>`s via a plain Jinja `{% for %}` loop. The
  `homeSparkline()` Alpine factory survives only for the meta
  counters.
- **BUG-32-02**: the home-page two-column CSS Grid used
  `align-items: stretch` (the Grid default), which dehned the Job
  activity card and the Quick actions card to match whichever
  neighbour was tallest. Combined with `grid-row: 2 / span 2` on
  the Latest runs card, the Sparkline card acquired a dead lower
  half. Fixed by switching to two flex columns
  (`.pql-home-col--primary` / `--secondary`) — each card now hugs
  its natural height. Also added `justify-content: space-between`
  to `.pql-home-sparkline` so the SVG and its meta counters sit at
  opposite ends of the card header rather than clustering on the
  left.

### Added (Sprint 31)

- Global command palette — `Cmd+K` / `Ctrl+K` opens a centred dialog
  that searches catalogs, schemas, tables, connections, credentials,
  external locations, jobs, dashboards, and (admin-only) workspace
  notebooks in one shot. Prefix matches outrank substring matches;
  ties resolve by `updated_at` descending. Empty query renders
  `localStorage['pql.recentSearches']` (last 10, deduped by URL).
  `?` opens a keyboard-shortcuts help modal.
- `GET /api/search?q=&limit=` aggregates the seven sources via
  `asyncio.gather` (reusing `unitycatalog.get_tree()`,
  `list_connections/credentials/external_locations`, the local
  `Job` / `Dashboard` ORM queries, and
  `notebook_workspace.list_workspace_tree`). Per-source soyuz
  failures degrade gracefully: a `PointlessSQLError` from one
  fetcher logs at WARNING and the remaining sources still answer,
  so a soyuz blip never 502's the palette.
- `frontend/templates/components/command_palette.html` mounted once
  in `base.html` so the shortcut is global. Alpine factory
  `commandPalette()` owns palette + help-modal state, debounces
  search to 150 ms, drops stale responses by sequence number, and
  guards `?` against firing while focus is in an input or the
  palette itself.
- Navbar gains a ghost-button trigger (`.pql-cmdk-trigger`) with a
  platform-aware `⌘K` / `Ctrl+K` keycap hint and a mobile-only
  search-icon button below 768 px. Removed the `ms-auto` from the
  navbar `<ul>` and put it on the trigger so the button anchors the
  right-hand cluster.
- Design-token-native CSS for the palette, hit list, type badges
  (one accent per source family), help modal, and `<kbd>` keycaps;
  reuses `--pql-color-*`, `--pql-elev-3`, and `--pql-radius-md`
  from Sprint 29 so light mode works for free.
- `docs/e2e-walkthroughs/command-palette.md` — Playwright MCP
  playbook covering navbar trigger, Cmd+K, keyboard nav, recent
  searches, admin/non-admin notebook visibility split, the `?`
  help modal, and the soyuz-degraded fallback.

### Added (Sprint 30)

- New app-shell layer in `base.html`: mobile-aware responsive grid
  (`minmax(0, 1fr)` below `md`, `var(--pql-sidebar-width) minmax(0, 1fr)` ≥ md),
  sidebar wrapped in Bootstrap 5.3 `offcanvas-md` with a hamburger
  trigger visible only on narrow viewports. No new JS module — Bootstrap's
  built-in offcanvas handles open/close, backdrop, and Esc-to-close.
  Sprint 35 hardens touch targets and focus-trap.
- `frontend/templates/components/breadcrumbs.html` — declarative
  component that renders from a `breadcrumbs=[{label, href?}]` list;
  the final item (or any item without `href`) becomes the active
  terminal crumb. Migrated 8 pages: `jobs`, `dashboards`, `connections`,
  `external_locations`, `credentials`, `notebooks_workspace`,
  `schemas`, `tables`.
- `frontend/templates/components/empty.html` — reusable empty-state
  panel with optional `icon`, `title`, `message`, `action_href` /
  `action_label`, and a `flush` variant for use inside an existing
  card. Migrated the 6 list-page empty states (jobs, dashboards,
  connections, external_locations, credentials, notebooks_workspace)
  — in-card snippets (permissions, tags, lineage, properties,
  sync_history) remain opportunistic follow-up.
- New branded error pages: `pages/404.html` (bi-compass), `pages/500.html`
  (bi-exclamation-octagon, renders `request_id` for bug reports),
  both on the new app shell. `pages/403.html` refitted onto the same
  `components/empty.html` primitive — preserving the existing
  `required_privilege`/`securable_type`/`full_name` context.
- `pointlessql/api/error_handlers.py` — Accept-aware dispatch:
  `/api/` paths still always emit the JSON envelope; non-`/api/` paths
  honour an explicit `Accept: application/json` without `text/html`,
  otherwise render the HTML shell. Registered a `StarletteHTTPException`
  handler so unmapped 404s render the branded page (not FastAPI's
  default JSON), and an `Exception` catch-all that logs `exc_info` and
  returns the 500 shell or JSON envelope.
- `frontend/js/toast.js` — `window.pqlToast.{success, error, info}(msg, {timeout}?)`
  mounted once in `base.html`. Each call builds a Bootstrap toast in
  `#pql-toast-root`, applies a Sprint-29 semantic variant
  (`.pql-toast--{success|error|info}`), and removes the node on
  `hidden.bs.toast`. API only this sprint; Sprint 36 wires the five
  existing components onto an `apiFetch` helper that emits toasts
  on error.
- CSS additions in `frontend/css/style.css`: responsive `.pql-shell`
  grid, `.pql-sidebar-shell` offcanvas reset, `.pql-sidebar-toggle`,
  `.pql-breadcrumbs`, `.pql-empty` (+ `.pql-empty--{variant}` tints,
  `__icon` / `__title` / `__message` / `__meta` / `__action`),
  `.pql-error-shell` centered wrapper, and `.pql-toast` (+ variants).
  All colour pairs reuse Sprint-29 semantic tokens so light-mode
  inherits for free.

### Added (Sprint 29)

- Design-token system in `frontend/css/style.css`: spacing
  (`--pql-space-1..8`, 4-px scale), typography
  (`--pql-text-xs..3xl`, ~1.125 modular ratio), radius
  (`--pql-radius-sm|md|lg|pill`), elevation (`--pql-elev-0..3`,
  dark-mode-tuned), motion (`--pql-duration-fast|normal|slow` +
  `--pql-ease`), and semantic colour pairs (success / warning /
  danger / info / neutral — each with a `bg` + `fg` variable so
  chip text meets AA contrast against its own background). Brand
  accent `#76b900` preserved as `--pql-color-accent`
- Light-mode variant **prepared** via a
  `:root[data-bs-theme="light"]` override block — tokens flip
  automatically when the attribute changes. No toggle is wired
  yet; switching in DevTools is enough to verify downstream
  primitives adapt
- Inter font self-hosted (OFL-1.1, Latin subset) at
  `frontend/fonts/inter-regular.woff2` (23.7 kB) and
  `inter-semibold.woff2` (24.3 kB) — combined 48 kB, under the
  50 kB per-page budget. Two `@font-face` blocks with
  `font-display: swap`; `body { font-family: var(--pql-font-sans); }`
  picks it up globally. Regular is `<link rel="preload">`-ed in
  `base.html`; SemiBold is lazy-loaded on first use
- CSS-only primitives: `.pql-stack` (vertical flex with token
  gap; `--tight`/`--loose` modifiers), `.pql-cluster`
  (horizontal wrapping cluster), `.pql-card` (panel surface
  replacing the 18-site `card mb-4 p-4` pattern; sibling
  `.pql-card + .pql-card` auto-margins; `.pql-card--flush`
  strips padding for iframe wrappers), `.pql-badge` (pill-shaped
  status chip, semantic-palette modifiers `--success|warning|danger|info`)
- Proof-of-concept template migrations: `base.html` (font
  preload + Inter via body rule), `pages/login.html` (card ↦
  `.pql-card` + nested `.pql-stack` form layout), and
  `pages/catalogs.html` (welcome hero wrapped in `.pql-card` +
  `.pql-stack --loose`; catalog-count chip becomes
  `.pql-badge --info`). The remaining 27 templates stay on
  Bootstrap utilities and will migrate in Sprints 30 / 33 / 34
  as those sprints touch each surface
- `docs/design-tokens.md` reference — token tables with
  "when to use" notes, primitive snippets, light-mode override
  pattern, and contribution conventions (new tokens land
  alongside a doc update in the same commit)

### Added (Sprint 28)

- Alembic migration `008_dashboards.py` creating the
  `dashboards` table (slug unique, title, description,
  notebook_path, job_id FK nullable with `ON DELETE SET NULL`,
  owner_id FK, timestamps)
- New `Dashboard` ORM model in `pointlessql/models.py`
- `render_run_notebook` in `pointlessql/services/notebook_render.py`
  gains an `exclude_input: bool = False` keyword; when true,
  renders with `HTMLExporter(..., exclude_input=True)` and caches
  to a sibling `{run_id}.dashboard.html` sidecar so the
  code-visible and code-hidden variants coexist without clobbering
  each other
- `GET /jobs/{id}/runs/{rid}/notebook` gains an optional
  `?exclude_input=true` query param threaded through to the
  render helper
- Dashboard CRUD routes: `GET /api/dashboards` (list, any
  logged-in user), `GET /api/dashboards/tree` (sidebar shape),
  `POST /api/dashboards` (admin-only, validates slug against
  `^[a-z0-9][a-z0-9-]{0,199}$`), `PATCH /api/dashboards/{slug}`
  (admin-only; editable fields: title, description,
  notebook_path, job_id), `DELETE /api/dashboards/{slug}`
  (admin-only), `POST /api/dashboards/{slug}/refresh`
  (admin-only; triggers the bound job's `execute_run(...,
  trigger="manual")` via the same helper that powers the
  job-detail Run-now button)
- `GET /dashboards` list page + `GET /dashboards/{slug}` detail
  page rendering the latest succeeded run through an iframe
  pointed at `/jobs/.../notebook?exclude_input=true`; empty
  state when no job is bound or no successful run exists
- `GET /jobs/{id}/runs/{rid}/compare?to={other_rid}` — two
  Sprint-26 iframes side-by-side with run metadata headers; both
  run ids are validated to belong to the same job before render
  (no foreign-run leak). No cell-level diff highlighting (stub)
- "Compare runs" card on `pages/job_detail.html` (visible only
  when ≥ 2 completed runs exist) with two `<select>`s and a
  Compare button that navigates to the compare URL
- New templates: `pages/dashboards.html`,
  `pages/dashboard_detail.html`, `pages/run_compare.html`, and
  `components/dashboards_sidebar.html` (mirrors the Sprint 27
  workspace-tree component; `sessionStorage` key
  `pql.dashboards`)
- Navbar gains a **Dashboards** link (visible to every logged-in
  user — consumer surface, not admin-only); `base.html` swaps in
  the dashboards sidebar when `active_page == 'dashboards'`
- New playbook `docs/e2e-walkthroughs/dashboards.md` covering
  create-modal → detail with code-hidden iframe → Refresh →
  sidebar tree → non-admin visibility → run-compare from the
  job-detail card, plus the foreign-run 404 negative

### Added (Sprint 27)

- New `pointlessql/services/notebook_workspace.py` with
  `list_workspace_tree(notebooks_dir)` (nested listing with per-
  notebook `parameters_tagged: bool`; skips the executor `runs/`
  subdir) and `resolve_upload_target(notebooks_dir, relative_path)`
  (mirrors `resolve_notebook_path` but allows a not-yet-existing
  target and requires the parent directory to exist)
- `GET /api/notebooks/tree` — admin-only directory listing for
  the workspace browser
- `POST /api/notebooks/upload` — admin-only multipart upload of
  `.ipynb` files into the notebooks workspace; validates
  `.ipynb` extension, parses the body as JSON before writing,
  atomically replaces via a `.tmp` sidecar, and requires an
  explicit `overwrite=true` form field to clobber an existing
  file
- `GET /notebooks/workspace` — new admin-only HTML page with a
  flattened-tree component keyed on `sessionStorage`
  `pql.notebooks` / `pql.notebooks.open`, plus a per-leaf
  **Schedule…** button that navigates to
  `/jobs?prefill_kind=papermill&prefill_notebook_path=<path>`
- Create-job modal (`pages/jobs.html`) reads those query params
  on mount, pre-fills `kind=papermill` + `notebookPath`, chains
  `inspect()` for the typed-parameters form, opens the modal,
  and strips the query string via `history.replaceState`
- Navbar gains a **Workspace** link (admin-only) between
  Notebook and Jobs
- Playbook extension: Part G in
  `docs/e2e-walkthroughs/notebook-jobs.md` covers upload →
  schedule → run-now → Output artifacts card, plus non-admin
  403 and the overwrite / traversal / non-`.ipynb` negative paths

### Added (Sprint 26)

- `nbconvert>=7.0` dep and new `pointlessql/services/notebook_render.py`
  with `render_run_notebook(runs_dir, run_id)` — first call runs
  `HTMLExporter(template_name="lab")` on
  `runs/{run_id}.ipynb`, writes an atomic `.html` sidecar next to
  it, and returns the HTML; subsequent calls serve the sidecar
- `GET /jobs/{id}/runs/{rid}/notebook` — inline-renders a
  papermill run's output notebook for iframe embedding on the
  job-detail page
- `GET /jobs/{id}/runs/{rid}/notebook/download?format={ipynb,html}`
  — visibility-checked downloads of the raw notebook or its
  rendered sidecar. Replaces the originally planned
  `/notebooks/runs/` StaticFiles mount so non-owner logged-in
  users can't exfiltrate other users' run outputs by guessing
  `run_id`s. Both routes share `_load_papermill_run_output_path`
  which validates job ownership, papermill kind, and run
  ownership before touching disk
- New "Output artifacts" card on `job_detail.html` (between
  the DAG tasks and Recent runs cards, guarded by
  `job.kind == "papermill"`): auto-selects the most recent
  succeeded/failed run on page load, Rendered/JupyterLab view
  toggle wired to the two iframe sources, download links for
  `.ipynb` and `.html`
- Recent runs rows are now clickable on papermill jobs;
  `$dispatch("run-selected", { runId })` swaps the card's
  iframe to the clicked run's output. The Sprint 24 "Open in
  JupyterLab" anchor retains `@click.stop` so row-click and
  popout-click don't collide
- `docs/e2e-walkthroughs/notebook-jobs.md` Part F walks the
  card's auto-select, view-toggle, row-click swap, downloads,
  and the three 404 negatives

### Added (Sprint 25)

- `GET /api/notebooks/inspect?path=…` admin-only route wrapping
  `papermill.inspect_notebook` — returns
  `[{name, default, inferred_type, help}]` so the create-job modal
  can render one typed input per declared parameter instead of a
  free-form JSON textarea
- Create-job modal gains a "Load parameters" button, a typed form
  (`number` / `checkbox` / `text` / `textarea`) rendered via Alpine
  `x-for`, and a collapsed `<details>` "Advanced" fallback that
  keeps the raw JSON textarea for power users. Advanced mode wins
  over the typed form when the `useAdvanced` checkbox is ticked
- Job-detail Configuration card renders dedicated **Notebook** and
  **Parameters** rows for papermill jobs (nested `<dl>` for the
  parameters) instead of the catch-all `<pre>{{ config|tojson }}</pre>`
- Promoted `_resolve_notebook_path` → public `resolve_notebook_path`
  in `services/scheduler.py` so the inspect route reuses the same
  traversal-safe path resolver the executor uses
- Seed script writes `notebooks/smoke_typed_params.ipynb`
  (`count: int = 3`, `enabled: bool = True`, `label: str = "hello"`)
  for the new Part E playbook — one parameter per typed-input branch
- `docs/e2e-walkthroughs/notebook-jobs.md` Part E walks the
  inspect endpoint, the typed-form rendering + override, the
  Advanced raw-JSON fallback, and two negative inspect cases
  (missing file, traversal). Live-run findings appended to the
  Found-bugs section — no bugs surfaced

### Added (Sprint 24)

- Papermill job kind: `_papermill_executor` registered next to
  `pg_sync` and `python` in `scheduler_service.build_default_registry()`.
  Config shape `{notebook_path, parameters, timeout_seconds}`;
  output lands at `{notebooks_dir}/runs/{job_run_id}.ipynb` so the
  embedded JupyterLab serves it at `/lab/tree/runs/{run_id}.ipynb`
- `POINTLESSQL_PRINCIPAL` env var honoured by the `PQL` constructor
  (via `make_principal_client`) so notebook code running under the
  Papermill executor inherits the job's run-as user without extra
  wiring — the scheduler exports the env var into the kernel
  subprocess
- New settings `POINTLESSQL_NOTEBOOKS_DIR` (default `notebooks`) and
  `POINTLESSQL_NOTEBOOK_EXECUTE_TIMEOUT_SECONDS` (default `300`).
  `services/jupyter.py` now resolves its `--notebook-dir` through
  the setting so the executor and the embedded JupyterLab share a
  single source of truth
- Create-job modal (`frontend/templates/pages/jobs.html`) gains a
  `kind` select with `DAG (multi-task)` and `Papermill (single
  notebook)` options; Papermill-specific `notebook_path` +
  `parameters` inputs render conditionally
- Job detail page (`frontend/templates/pages/job_detail.html`)
  recent-runs table gains a trailing "Open in JupyterLab" column
  on rows of `kind=papermill` jobs whose run status is `succeeded`
  or `failed`
- `docs/e2e-walkthroughs/notebook-jobs.md` — Phase-8 playbook
  covering create via modal, Run-now, output-artifact verification,
  the JupyterLab deep-link, and four negative paths
  (missing path, traversal, missing file, failing cell)

### Added (Sprint 23)

- `docker-compose.e2e.yml` gains a `mock-oidc` service
  (`ghcr.io/navikt/mock-oauth2-server:latest`, host port 9090)
  and `${…:-default}` env passthroughs on the `pointlessql`
  service for `POINTLESSQL_SCHEDULER_TICK_SECONDS`
  (default `2` so DAG state transitions land in seconds during
  live walks), `POINTLESSQL_JUPYTER_ENABLED`,
  `POINTLESSQL_LOG_FORMAT`, and the four `POINTLESSQL_OIDC_*`
  / `POINTLESSQL_BASE_URL` knobs. All default to empty so the
  Sprint 22 data-surface playbooks keep working unchanged
- Five orchestration + operational playbooks under
  `docs/e2e-walkthroughs/`:
  - `jobs-dag.md` — single-task + DAG job creation, Run-now,
    retry + fail-skip propagation, Pause/Resume click, per-task
    log panel expand, and a `pg_sync`-kind cross-feature smoke
    driving Sprint 18's `run_sync()` against the Sprint 22
    `pg_mirror` foreign catalog
  - `notebook.md` — `/notebook` + `/api/jupyter/status` in
    `jupyter_enabled=true` (iframe src `http://localhost:8888/lab`,
    Alpine `jupyterLoader().ready` flips to true) and `=false`
    (template short-circuits to "Notebook Disabled" card) passes
  - `oidc.md` — SSO button absent with no OIDC env, then with
    the mock issuer a full authorize-code + PKCE round-trip that
    auto-creates a user with `oidc_provider` / `oidc_subject`
    bound; repeated sign-in reuses the existing row
  - `operational.md` — anonymous `/healthz`, admin `/metrics`
    `text/plain` with all three metric families, non-admin
    `/metrics` renders 403, JSON API errors carry a UUID
    `request_id`, `X-Request-ID` round-trips client-supplied
    values
  - `config-matrix.md` — primary walk (`engine=pandas,
    log=text, db=sqlite`) plus five delta walks for every
    non-default value of `POINTLESSQL_ENGINE`,
    `POINTLESSQL_LOG_FORMAT`, `POINTLESSQL_DATABASE_URL`, and
    their cartesian-product smoke
- `docs/e2e-walkthroughs/README.md` updated: cross-links to the
  ten playbooks, the host-env overlay table with the
  recreate-pointlessql workflow, and a Sprint-23 section on the
  `mock-oidc` + bridge-IP workaround for Docker DNS asymmetry
- `CLAUDE.md` "Replaying the e2e walkthroughs" section pinning
  the ten-playbook tree, the `--browser firefox` /
  `chrome-for-testing` MCP config requirement (Sprint 22 commit
  `3f1da76` backstory), and the "replay before landing HTML/JS"
  contract for future sprints
- Phase 7 close-out summary appended to `ROADMAP.md`: all five
  surfaced bugs fixed same-commit, none deferred

### Fixed (Sprint 23)

- **BUG-23-01**: `oidc_enabled` computed property in
  `pointlessql/settings.py` used `is not None`, treating the
  empty strings produced by the compose overlay's
  `${POINTLESSQL_OIDC_DISCOVERY_URL:-}` fallback as
  *configured*. The SSO button on `/auth/login` rendered and
  clicking it hit a `401 Failed to fetch OIDC discovery
  document`. Truthy check replaces the `is not None` so both
  `None` and `""` count as "not configured"
- **BUG-23-02**: `POST /api/jobs` in `pointlessql/api/main.py`
  committed the `Job` row before running
  `scheduler_service.validate_dag` over the task list, so a
  cycle / unknown-dep payload returned 422 but left the job row
  visible on `/jobs` forever. Refactored to `session.flush()`
  during the two-pass task insert and a single final
  `session.commit()` only after `validate_dag` succeeds —
  rejected payloads roll back cleanly when the session context
  exits

### Added (Sprint 22)

- `docker-compose.e2e.yml` overlay — `postgres-e2e` sidecar
  (postgres:17-alpine, port 5433) seeded from
  `scripts/pg-seed.sql` as the foreign-catalog target for the
  sync playbook; mounts `./scripts:/app/scripts:ro` on the
  `pointlessql` service so the seed script can run server-side
  with consistent `file:///app/warehouse/...` storage URIs
- `scripts/pg-seed.sql` — defensively idempotent Postgres
  `shop` schema (customers, products, orders) with a few seeded
  rows so the first foreign-catalog sync returns `added_count`
  equal to `schema + 3 tables`
- `scripts/seed-e2e.py` — idempotent driver that runs inside
  the PointlesSQL container: creates managed catalog `demo`,
  schemas `demo.sales` / `demo.hr` with `file://` storage
  roots, writes four Delta tables via `PQL.write_table` (50
  orders, 20 customers, 10 employees, 10 salaries), and
  registers a soyuz `Connection pg_e2e` pre-bound to the
  seeded Postgres so the foreign-catalog create modal picks it
  up without further setup
- `docs/e2e-walkthroughs/README.md` — operator doc: stack
  start/teardown, test-user credentials shared across playbooks,
  how Claude replays a playbook via the Playwright MCP tool set,
  selector conventions for a codebase without `data-test`
  attributes, rebuild note for stale cached container images
- Five Markdown playbooks under `docs/e2e-walkthroughs/`:
  `auth.md` (first-user admin bootstrap + non-admin + `/auth/me`
  + `/metrics` 403), `catalog-browsing.md` (welcome screen +
  sidebar-tree sessionStorage persistence + PQL-snippet copy
  button), `inline-editors.md` (`editable` +
  `properties_editor` + `tags_editor` + `permissions_card`
  grant/revoke across catalog/schema/table, driven via
  `Alpine.$data(card)` rather than DOM mutation so Alpine's
  reactive bindings don't swallow typed values), `federation.md`
  (admin CRUD of connections / credentials / external locations
  with `deleteConfirm`, non-admin 403 negative), and
  `foreign-catalog-sync.md` (create-foreign-catalog modal → Sync
  now → sync-history card → mirrored `pg_mirror.shop.*`
  tables in the sidebar)
- All five playbooks exercised live via Playwright MCP in
  Firefox against a freshly-composed stack. Playbooks record
  what each step's `browser_evaluate` returned so the next
  replay has a concrete expectation. Three bugs surfaced
  during the live run and were fixed in the same sprint:
  - **BUG-22-01 fixed**: `_wrap_catalog_errors` in
    `pointlessql/services/unitycatalog.py` now branches on
    `UnexpectedStatus.status_code` — 404 → `CatalogNotFoundError`,
    other 4xx → `ValidationError`, only 5xx / transport →
    `CatalogUnavailableError`. PATCH permissions with an
    invalid privilege (e.g. `SELECT` at catalog level) now
    returns `422 validation_error` passing the soyuz message
    through; PATCH on a non-existent catalog now returns
    `404 catalog_not_found`
  - **BUG-22-02 fixed**: the same decorator now catches
    `KeyError` / `TypeError` raised by a generated
    `Create*.from_dict()` (missing required request-body field)
    and re-raises `ValidationError`. `POST
    /api/external-locations` without `credential_name` now
    returns `422 validation_error: "Invalid request body:
    'credential_name'"` instead of a 500 leaking the KeyError
  - **BUG-22-03 fixed**:
    `createExternalLocationForm.submit()` in
    `frontend/js/federation.js` now rejects an empty
    `credentialName` with an inline error before issuing the
    request, matching the UC spec requirement surfaced by
    BUG-22-02

### Added (Sprint 21)

- `pointlessql/services/metrics.py` — Prometheus surface on its
  own `CollectorRegistry` so tests don't contaminate the global
  default. `Counter pointlessql_job_runs_total{status,job_name}`,
  `Histogram pointlessql_job_run_duration_seconds{job_name}`
  (buckets 0.05 s .. 3600 s, log-spaced, includes the Prom
  default 10 s), `Gauge pointlessql_scheduler_tick_lag_seconds`;
  `render_metrics()` / `record_run()` / `observe_tick_lag()`
  helpers
- `GET /metrics` admin-only (raises `AuthorizationError` via
  `_require_admin`); returns `generate_latest()` bytes with
  `text/plain; version=0.0.4`
- Optional per-job failure webhook: `jobs.on_failure_url`
  (Alembic migration 007, nullable `String(1000)`). Scheduler
  POSTs `{job_id, job_name, run_id, status, error, started_at,
  finished_at}` (ISO-8601) on a failed run via
  `_post_failure_webhook`. 5 s timeout, no retries, one-shot
  `httpx.AsyncClient.post`; `httpx.HTTPError` logged at WARN
  and swallowed so a broken receiver never affects run state.
  `_webhook_client_factory` exposed for test stubbing
- `docs/jobs.md` — authoring guide: executor signature
  (`job_run_id, user_info, config, uc_client`), publishing a
  custom kind via the `pointlessql.jobs` entry-point group, the
  scheduling JSON + `on_failure_url` payload shape, a worked
  `pql`-in-a-task summary-table example, notes on logging /
  retries / concurrency, observability, and when to add a
  built-in kind instead
- README.md gains a "Jobs" section linking to `docs/jobs.md`
- `tests/test_metrics.py` — 9 new tests (emission on success +
  failure, `/metrics` admin-only enforcement, webhook URL +
  payload keys + timeout, no-webhook path, broken-receiver
  does not abort the run). Sprint 19+20 scheduler tests still
  green (36 passed). Full suite not run in this sprint

### Changed (Sprint 21)

- `scheduler.py`: `execute_run` wraps a new `_execute_run_core`
  and emits telemetry around every run; `tick_once` emits
  telemetry for synthetic `skipped` rows too; `Scheduler._run`
  samples tick lag each iteration

### Added (Sprint 20)

- Alembic migration 006: `jobs.max_parallel_runs`; `job_tasks`
  gains `kind`, `depends_on` (JSON list of task ids),
  `max_retries`, `retry_backoff_seconds`; new `task_runs`
  (id, job_run_id FK, task_id FK, status, started_at,
  finished_at, attempts, error); `job_logs.task_id` nullable
  FK (batch-alter safe on SQLite)
- Topological DAG walk in `scheduler.py`: iterative three-color
  DFS validates the graph at create-time and raises
  `ValidationError("cycle detected in task graph: [...]")`
  with the offending path; unknown `depends_on` ids caught
  in the pre-pass; upstream-fail → downstream tasks marked
  `skipped` (not `failed`)
- Retry policy per task: linear backoff (delay between
  attempts `i` and `i+1` is `i * retry_backoff_seconds`);
  `_sleep` is a module-level hook so tests patch it;
  attempts counted on `TaskRun`
- Concurrency caps: layered `asyncio.Semaphore`. Global
  semaphore sized from
  `POINTLESSQL_SCHEDULER_MAX_CONCURRENT_RUNS` (default 4)
  allocated on `Scheduler.start()`; per-job semaphores are
  lazy, keyed by `job_id`, sized from
  `Job.max_parallel_runs` (default 1). Global acquired
  before per-job (consistent lock order). DB `running`-count
  query stays as the authoritative `skipped` writer so
  process restarts don't lose state
- `logging_config.py`: new `job_run_id_var` and `task_id_var`
  alongside Sprint 16's `request_id_var`. `JSONFormatter`,
  `RequestIdFilter`, and the `LogRecord` factory carry all
  three. Scheduler sets them per-task and resets in
  `finally`. Sprint 19's `request_id_var = f"job-{job_run_id}"`
  is kept for continuity
- `log_job(job_run_id, task_id, level, message)` writes every
  status transition and retry to `job_logs`, synchronously
  relative to the task call
- `POST /api/jobs` accepts a DAG create form: `tasks` array
  with `{name, kind, config, depends_on, max_retries}`;
  validates cycles/unknown deps before insert
- New routes: `GET /api/jobs/{id}/tasks`,
  `GET /api/jobs/{id}/runs/{run_id}/tasks`,
  `GET /api/jobs/{id}/runs/{run_id}/logs?task_id=...`
- UI: "New DAG job" modal on `jobs.html` (JSON textarea — no
  builder yet). Per-task table on `job_detail.html` with
  status, retry count, last error; expandable Alpine log
  panel fetches lines on demand
- Settings: `POINTLESSQL_SCHEDULER_MAX_CONCURRENT_RUNS`
  (default `4`)
- `tests/test_scheduler_dag.py` — 13 new tests (topology,
  fail-skip, retry success, retry exhaustion, cycle
  detection, self-loop, unknown dep, per-job cap, global
  semaphore serialization, contextvars set/reset via
  caplog, `log_job` writer, route-level cycle 422). Sprint
  19's 23 scheduler tests and Sprint 16's 8 logging tests
  still green. Full suite not run in this sprint

### Added (Sprint 19)

- Alembic migration 005: `jobs` (name unique, cron_expr,
  run_as_user_id FK, kind, config JSON, is_paused, timestamps),
  `job_runs` with `(job_id, started_at DESC)` index, plus
  `job_tasks` and `job_logs` pre-created for Sprint 20
- `pointlessql/services/scheduler.py` — in-process asyncio
  scheduler started from `_lifespan`; `croniter`-driven due
  detection; per-tick running-run query prevents overlap;
  paused jobs skipped; failed `run_as_user_id` resolution
  surfaces as a `failed` run with a clear error
- Kind registry: `pg_sync` wraps Sprint 18 `run_sync` with
  `config["catalog_name"]`; `python` resolves an entry point
  from the `pointlessql.jobs` group (tests register a fake)
- Run-as-user builds `UnityCatalogClient.for_principal(user.email)`
  so soyuz's X-Principal applies automatically — reuses Sprint 7
- Scheduler sets `request_id_var` to `f"job-{job_run_id}"`
  inside each per-run span so structured logs correlate
  without a new contextvar (Sprint 20 adds
  `job_run_id_var` + `task_id_var`)
- Settings: `POINTLESSQL_SCHEDULER_ENABLED` (default `True`)
  and `POINTLESSQL_SCHEDULER_TICK_SECONDS` (default `30`)
- Routes: `GET /jobs` (list, ownership-filtered for non-admin),
  `GET /jobs/{id}`, `POST /api/jobs` (admin-only),
  `POST /api/jobs/{id}/run`, `POST /api/jobs/{id}/pause`,
  `POST /api/jobs/{id}/unpause` — all audited
- `frontend/templates/pages/jobs.html`,
  `frontend/templates/pages/job_detail.html` with "Run now" /
  "Pause/Resume" buttons visible to admin or the owner
- Navbar "Jobs" entry between "Notebook" and existing
  dropdowns
- `tests/test_scheduler.py` covering tick logic with a
  patched clock, state transitions, overlap prevention,
  paused skip, run-as-user principal forwarding, `pg_sync`
  end-to-end, route admin-gating and ownership filter

New dep: `croniter`.

### Changed (Sprint 19)

- `tests/conftest.py` sets
  `POINTLESSQL_SCHEDULER_ENABLED=false` before app import
  so the loop never ticks in ordinary test runs; the
  scheduler suite re-enables it per-test via monkeypatch
- `.gitignore`: `*.db-shm`, `*.db-wal` (SQLite WAL
  artifacts now produced by the scheduler's DB writes)

### Added (Sprint 18)

- `pointlessql/services/pg_sync.py`: pure-function Postgres → UC sync
  worker. `PG_TO_UC_TYPE` map, `map_pg_type_to_uc` with DECIMAL
  precision passthrough and STRING fallback on unknown types,
  `diff_snapshots(pg, uc_tables) -> SyncDiff` (schemas/tables/
  columns added/changed/dropped), `apply_diff` driving the facade,
  `PostgresIntrospector` protocol + `PsycopgIntrospector` default
  backed by `information_schema.columns` via `psycopg.sql.SQL`,
  `run_sync` glue that persists a `SyncRun` row per execution
- `unitycatalog.py` facade: `create_schema`, `create_table`,
  `delete_table` for driving the sync — all wrapped in
  `_wrap_catalog_errors`
- `POST /api/catalogs/{name}/sync` (admin-only, audited) resolves
  the catalog's bound Connection + optional Credential, builds a
  libpq DSN, runs the sync, and returns the `SyncRun` snapshot
- Alembic migration 004: `sync_run` table (`catalog_name`,
  `started_at`, `finished_at`, `status`, `added_count`,
  `changed_count`, `dropped_count`, `error`) with
  `(catalog_name, started_at DESC)` index
- `SyncRun` ORM model
- `components/sync_history_card.html`: last-20 sync runs + admin
  "Sync now" button on the foreign-catalog detail page
- Secret handling: connection options with keys matching
  `(?i)pass|secret|key|token` are overridden from a bound
  Credential's `additional_properties` (see `_effective_options`);
  missing Credential falls back to `options`
- 46 new tests (309 total) covering type mapping (16 parametrized),
  diff logic, secret merging, DSN builder, `apply_diff` with mock
  UC, `run_sync` end-to-end with stub introspector, the
  admin-only sync route, audit log emission, the history card
  render, and an `@pytest.mark.integration` test against a
  real Postgres container (documented, skipped by default)

### Added (Sprint 17)

- `unitycatalog.py` facade: `create_catalog(data)` and
  `delete_catalog(name, force)` wrapping the generated client's
  `_create_catalog` / `_delete_catalog`; both go through
  `_wrap_catalog_errors` so transport failures surface as
  `CatalogUnavailableError`
- `POST /api/catalogs` route (admin-only, audited) accepting the
  full `CreateCatalogRequest` shape — `name`, optional `comment`,
  `properties`, `type=FOREIGN`, `connection_name`, and free-form
  `options` passthrough — for wiring up foreign catalogs
- "Create foreign catalog" button + modal on the catalogs page
  (`pages/catalogs.html`): admin-only, pre-populated connection
  dropdown, key/value options row editor, posts through a new
  `createForeignCatalogForm(...)` Alpine factory in `federation.js`
- `components/foreign_catalog_card.html`: bound-connection link +
  inline options editor on the catalog detail page, rendered when
  `catalog.connection_name` is set
- FOREIGN badge on the catalog detail heading
  (`pages/schemas.html`) and in the sidebar tree
  (`components/sidebar.html`, `bi-plug` icon) so foreign catalogs
  are visually distinct from managed ones
- `optionsEditor(...)` in `properties_editor.js` — PATCHes
  `{ options: {...} }` to the catalog; shares a new
  `_makeDictEditor(field, ...)` helper with the existing
  `propertiesEditor`
- `tests/test_foreign_catalog.py` — 8 tests covering POST happy
  path + non-admin 403, PATCH options forwards dict verbatim,
  foreign-card/FOREIGN-badge/connection-link rendering, modal
  visibility for admin vs non-admin users
- `tests/test_federation.py`: new `TestCatalogsCreate` (4 tests)
  exercising the facade's managed + foreign-catalog create and
  delete paths (263 total pass)

### Changed (Sprint 17)

- `properties_editor.js`: `propertiesEditor` refactored to a
  shared `_makeDictEditor` helper; behavior preserved (the
  "cannot clear all properties at once" quirk stays scoped to
  `field === 'properties'`)
- `/` home handler fetches connections for the create modal only
  when the current user is admin (empty list otherwise, no
  `list_connections` call)

### Added (Sprint 16)

- `pointlessql/logging_config.py` — centralized logging: a
  `request_id_var` contextvar, `RequestIdFilter`, opt-in
  `JSONFormatter`, idempotent `configure_logging(level, fmt)`.
  Also installs a `logging.setLogRecordFactory` so every record
  is stamped with the current `request_id` (works with pytest's
  `caplog` without per-handler hookup)
- Settings: `log_level` (default `"INFO"`) and `log_format`
  (`"text"` | `"json"`, default `"text"`); env overrides
  `POINTLESSQL_LOG_LEVEL`, `POINTLESSQL_LOG_FORMAT`
- Module-level loggers in `api/main.py`, `api/error_handlers.py`,
  and `services/unitycatalog.py`
- Startup log line from `_lifespan` (host, port, engine,
  log_format)
- `error_handlers.py` warns on every handled `PointlessSQLError`
  except `AuthorizationError` (authz denials are expected
  traffic, not anomalies)
- `services/unitycatalog.py` `_wrap_catalog_errors` logs the
  original transport exception before re-raising as
  `CatalogUnavailableError` — fixes prior silent-swallow
- `tests/test_logging_config.py` — 8 new tests covering
  formatter, filter, idempotency, and end-to-end request-ID
  propagation through a captured warning log (251 total pass)

### Changed (Sprint 16)

- `request_id_middleware` sets the `request_id_var` contextvar
  (in addition to `request.state.request_id`) and resets it in
  `finally`, so every log record emitted during the request
  carries the ID — service-layer code no longer has to receive
  the `Request` object to log it
- `api/main.py` calls `configure_logging(...)` at module import
  time so uvicorn `--reload` workers and direct `uvicorn` invocations
  both pick up the configured format; idempotent, coexists with
  pytest's `caplog`

### Changed (Sprint 15)

- `[tool.pydoclint]` configuration in `pyproject.toml`: Google
  style, types in signatures only, `__init__` docs merged into
  class docstrings
- Ruff `D107` ignored — pydoclint owns `__init__` docstring
  policy via `allow-init-docstring = false`
- Merged `__init__` docstrings into class docstrings for `PQL`,
  `DuckDBEngine`, `UnityCatalogClient` (DOC301)
- Restructured exception docstrings: constructor params in Args,
  class-level annotations in Attributes (DOC602/603/101/103)
- Accurate Raises sections in `PQL.table`, `PQL.write_table`,
  `find_or_create_oidc_user` (DOC501/503)
- pydoclint: 0 violations across all 27 source files

### Added (Sprint 14)

- `pointlessql/api/error_handlers.py` — centralized FastAPI
  exception handler for `PointlessSQLError` family; dispatches
  JSON error envelope for `/api/...` routes and 403.html for
  HTML authorization errors
- Consistent JSON error envelope on all API error responses:
  `{"error": {"code": "...", "message": "...", "request_id": "..."}}`
- Request-ID middleware: generates UUID4 per request (or
  forwards client `X-Request-ID`), attaches to error envelope
  and `X-Request-ID` response header
- `tests/test_error_handlers.py` — 13 new tests covering JSON
  envelope for each exception type, HTML 403 rendering,
  request-ID generation and forwarding, admin enforcement via
  centralized handler (243 total pass)

### Changed (Sprint 14)

- UC facade (`unitycatalog.py`): all public async methods
  wrapped with `_wrap_catalog_errors` decorator converting
  `httpx.HTTPError` / `UnexpectedStatus` →
  `CatalogUnavailableError` at the source — routes never see
  raw transport exceptions
- `_require_admin` raises `AuthorizationError` instead of
  returning a `JSONResponse`; `_deny_json`, `_deny_html`, and
  `_require_admin_html` removed
- ~40 duplicated try/except blocks removed from `main.py`
  (1164 → 815 lines); JSON API routes are now simple
  pass-through calls with exceptions propagating to the
  centralized handler
- HTML graceful-degradation routes (catalog/schema/table
  detail, federation pages) catch `CatalogUnavailableError`
  (domain exception) instead of raw `httpx.HTTPError`
- `httpx` and `UnexpectedStatus` no longer imported in
  `main.py`

### Added (Sprint 13)

- `pointlessql/exceptions.py` — domain exception hierarchy with
  `PointlessSQLError` base carrying `.status_code`, `.error_code`,
  `.detail`; six concrete types: `CatalogUnavailableError` (502),
  `CatalogNotFoundError` (404), `AuthenticationError` (401),
  `AuthorizationError` (403), `EngineError` (500),
  `ValidationError` (422, also inherits `ValueError`)
- `pointlessql/types.py` — `UserInfo` TypedDict replacing
  `dict[str, Any]` for authenticated user objects
- `tests/test_exceptions.py` — 17 new tests covering hierarchy,
  attributes, catchability, and backward compatibility
  (230 total pass)

### Changed (Sprint 13)

- Pyright: `typeCheckingMode` upgraded from `"standard"` to
  `"strict"` on source code; zero errors, 32 warnings (from
  incomplete third-party stubs)
- `AccessDenied` reparented as an alias for `AuthorizationError`
  in `services/authorization.py` (backward compatible)
- `OIDCError` reparented under `PointlessSQLError`
- PQL raises `CatalogUnavailableError` instead of `ConnectionError`,
  `CatalogNotFoundError` instead of `LookupError`,
  `ValidationError` instead of `ValueError`
- `make_engine()` raises `ValidationError` instead of `ValueError`
- `parse_full_name()` raises `ValidationError` instead of
  `ValueError`
- Broad exception catches narrowed: `except Exception` in
  `auth.py` → `except (ValueError, TypeError, PwdlibError)`,
  `except (JSONDecodeError, Exception)` in `oidc.py` →
  `except (JSONDecodeError, ValueError, UnicodeDecodeError)`
- `_STATE_COOKIE_NAME` in `oidc.py` renamed to `STATE_COOKIE_NAME`
  (was flagged by strict pyright as cross-module private access)
- `_get_user()` in `api/main.py` returns `UserInfo` instead of
  `dict[str, Any]`; `auth_middleware` and
  `_template_response_with_user` have explicit return type
  annotations

### Added (Sprint 12)

- `PolarsEngine` in `pointlessql/pql/engine.py` — reads Delta tables
  via PyArrow → `pl.from_arrow()`, returns `pl.DataFrame`; writes via
  `frame.to_arrow()` → `deltalake.write_deltalake()`
- `_POLARS_TYPE_MAP` + `_polars_type_to_uc()` for Polars dtype → UC
  type mapping
- `PolarsEngine` registered in engine factory and exported from
  `pql/__init__.py`
- Settings: `POINTLESSQL_ENGINE` now also accepts `"polars"`
- `POINTLESSQL_ENGINE` env var forwarded in `docker-compose.yml`
  (defaults to `"pandas"`)
- New dependency: `polars>=1.0`
- Engine compliance suite parameterized across all three engines;
  `TestPolarsEngineSpecific` with 3 Polars-specific tests; 2 new
  PQL constructor tests (9 new tests, 213 total pass)

### Added (Sprint 11)

- `pointlessql/pql/engine.py` — `Engine` protocol with `read()`,
  `write()`, and `columns_info()` methods; `PandasEngine` (default,
  preserving backward compatibility) and `DuckDBEngine` (reads Delta
  via PyArrow → DuckDB, returns `DuckDBPyRelation`)
- `make_engine()` factory to instantiate engines by name
- `columns_from_tuples()` in `_columns.py` — engine-agnostic column
  metadata builder for UC table registration
- Settings: `POINTLESSQL_ENGINE` (default `"pandas"`, also accepts
  `"duckdb"`) for engine selection via environment variable
- `PQL.__init__()` accepts `engine=` kwarg (string name or `Engine`
  instance); auto-selects from settings when omitted
- New dependencies: `duckdb>=1.0`, `pyarrow>=17.0`
- `tests/test_engine.py` — 20 new tests: parameterized engine
  protocol compliance suite (read, write, round-trip, column
  metadata) plus engine-specific tests for Pandas and DuckDB

### Changed (Sprint 11)

- `PQL.table()` and `PQL.write_table()` delegate all data I/O to
  the active engine instead of calling `deltalake` directly
- `PQL.__init__()` resolves `Settings` once and reuses it for both
  client creation and engine selection
- `columns_from_dataframe()` refactored to delegate to
  `columns_from_tuples()` internally (no behavior change)
- `pql/__init__.py` exports `Engine`, `PandasEngine`, `DuckDBEngine`,
  and `make_engine`

### Added (Sprint 10)

- `docker-compose.postgres.yml` — compose override that adds a
  Postgres service as PointlesSQL's metadata DB; usage:
  `docker compose -f docker-compose.yml -f docker-compose.postgres.yml up`
- `.env.example` — documents all `POINTLESSQL_*` env vars with
  defaults and descriptions
- Settings: `POINTLESSQL_BASE_URL` for OIDC callback URIs behind
  reverse proxies or inside Docker (falls back to request-derived
  URI when unset)
- `psycopg[binary]>=3.1` promoted from dev to main dependencies
  so Postgres URLs work at runtime
- Test fixture: `TEST_DATABASE_URL` env var to run the test suite
  against Postgres (or any SQLAlchemy-supported backend)

### Changed (Sprint 10)

- OIDC redirect_uri construction uses `POINTLESSQL_BASE_URL` when
  set, fixing SSO flows behind reverse proxies and in Docker
- Test `_auth_db` fixture drops all tables on teardown for clean
  isolation on persistent backends (Postgres)

### Added (Sprint 9)

- `Dockerfile` — 3-stage multi-stage build (soyuz-client-builder →
  builder → runtime) using `python:3.14-slim` and `uv pip install`
- `Dockerfile.soyuz` — 2-stage build for soyuz-catalog
- `docker-compose.yml` — full-stack orchestration with health checks,
  shared `./warehouse` volume for Delta storage, `depends_on` with
  `service_healthy` condition, configurable host ports via env vars
- `.dockerignore` for clean Docker builds
- Settings: `POINTLESSQL_HOST` (default `127.0.0.1`) and
  `POINTLESSQL_PORT` (default `8000`) for configurable bind address
- Frontend path fallback: installed wheel resolves
  `pointlessql/_frontend` when dev `frontend/` directory is absent
- README: Docker quick-start section with `docker compose up --build`

### Changed (Sprint 9)

- `cli()` reads host and port from `Settings` instead of hardcoding
- Jupyter subprocess uses `--allow-root` and binds to `settings.host`
  for Docker compatibility

### Added (Sprint 8)

- OIDC / OAuth2 authorization-code flow with PKCE — opt-in via
  `POINTLESSQL_OIDC_DISCOVERY_URL` and `POINTLESSQL_OIDC_CLIENT_ID`
  env vars; supports both public and confidential clients
- `pointlessql/services/oidc.py` — PKCE generation, HMAC-signed
  state cookie, discovery document caching, token exchange, userinfo
  fetch, find-or-create user provisioning with same-email linking
- `GET /auth/sso` route initiates the OIDC flow; `GET /auth/callback`
  handles the provider redirect and auto-provisions local users
- Login page shows conditional "Sign in with SSO" button alongside
  the existing email/password form
- Alembic migration 003: `password_hash` nullable for OIDC-only
  users, `oidc_provider` + `oidc_subject` columns with partial
  unique index
- `tests/test_oidc.py` — 33 new tests (177 total pass)

### Changed (Sprint 8)

- `User.password_hash` is now nullable to support OIDC-only accounts
- `auth.login()` handles `password_hash=None` gracefully (OIDC-only
  users cannot log in via email/password, preserving constant-time
  comparison)

### Added (Sprint 7)

- Authorization enforcement layer: PointlesSQL now checks effective
  permissions from soyuz-catalog before each operation. Non-admin
  users need `USE CATALOG`, `USE SCHEMA`, `SELECT`, `MODIFY`, or
  `MANAGE_GRANTS` depending on the operation
- Per-request `X-Principal` header forwarding: every soyuz-catalog
  HTTP call includes the authenticated user's email as the
  `X-Principal` header (via per-request client factory)
- Admin bypass: users with `is_admin=True` skip all permission checks
- Federation routes (connections, external locations, credentials)
  restricted to admin users only
- 403 Forbidden error page with privilege details and "contact an
  administrator" hint (`pages/403.html`)
- Audit log: `audit_log` table (Alembic migration 002) records
  who-did-what for all write operations — updates, tag changes,
  permission grants/revokes, federation CRUD
- `pointlessql/services/authorization.py` — `check_privilege`,
  `check_privilege_from_effective`, `has_privilege`, `AccessDenied`
- `pointlessql/services/audit.py` — `log_action` for append-only
  audit entries
- Permissions UI enhancements: current user's row highlighted with
  "you" badge in both Assigned and Effective tabs; grant/revoke
  controls hidden when user lacks `MANAGE_GRANTS`
- Non-admin test user fixture (`non_admin_cookies`) in conftest
- `tests/test_authorization.py` — 15 unit tests for authorization
  service (admin bypass, privilege matching, dict privilege format)
- `tests/test_enforcement.py` — 21 route-level enforcement tests
  (allowed/denied/admin bypass for catalogs, schemas, tables,
  updates, permissions, federation admin-only)
- `tests/test_audit.py` — 3 audit log service tests

### Changed (Sprint 7)

- All API routes use per-request `UnityCatalogClient` via
  `_get_uc_client(request)` instead of the shared singleton
- Detail pages enforce access using already-fetched effective
  permissions (no duplicate HTTP call)
- `permissions_card.html` and `permissions_editor.js` accept
  `canManage` and `currentUserEmail` parameters
- `test_api_errors.py` updated for per-request client pattern
  (monkeypatches `UnityCatalogClient.for_principal`)

### Added (Sprint 6)

- Alembic + SQLAlchemy 2.0 for PointlesSQL's own metadata DB
- Local user registration and login with bcrypt password hashing
- JWT cookie-based auth (`pql_session`, HttpOnly, HS256)
- Login and register pages
- Auth middleware protecting all routes
- First-user admin bootstrap
- Navbar shows current user and logout button

### Added (Sprint 5)

- Tags editor card on catalog, schema, and table detail pages — add
  and remove tags via PATCH to soyuz-catalog's tags endpoint, with
  Alpine.js interactive component (`tags_editor.html`, `tags_editor.js`)
- Permissions card with two Bootstrap nav-tabs (Assigned / Effective)
  on all detail pages — grant privileges via principal + privilege
  selector, revoke by clicking badge; effective permissions loaded
  on-demand (`permissions_card.html`, `permissions_editor.js`)
- Lineage card on table detail page showing upstream and downstream
  dependencies as depth-indented node lists with clickable links to
  related tables (`lineage_card.html`)
- Lakehouse Federation: full CRUD pages for connections, external
  locations, and credentials — list pages with create modals, detail
  pages with inline comment editing and delete-with-confirmation
  (`connections.html`, `connection.html`, `external_locations.html`,
  `external_location.html`, `credentials.html`, `credential.html`,
  `federation.js`)
- Federation dropdown in navbar (Connections, External Locations,
  Credentials)
- 21 new async facade methods in `unitycatalog.py` (tags, permissions,
  effective permissions, lineage, connections CRUD, external locations
  CRUD, credentials CRUD)
- 25 new JSON API routes + 6 HTML page routes in `main.py`
- `tests/test_tags_permissions.py` — unit tests for tags, permissions,
  effective permissions, and lineage facade methods
- `tests/test_federation.py` — unit tests for connections, external
  locations, and credentials facade CRUD
- Extended `tests/test_api_errors.py` with 11 new error-handling tests
  for all new JSON API endpoints

### Changed (Sprint 5)

- Detail page route handlers (`catalog_detail`, `schema_detail`,
  `table_detail`) now fetch tags, permissions, and effective permissions
  in parallel via `asyncio.gather`; `table_detail` additionally fetches
  lineage. Failure in any single fetch does not break the page
- `base.html` loads three new JS files: `tags_editor.js`,
  `permissions_editor.js`, `federation.js`

### Added (Sprint 4)

- E2E smoke test (`tests/test_e2e.py`): full roundtrip — create
  catalog/schema, write table via PQL, verify in web UI with correct
  columns and PQL snippet card
- `tests/conftest.py` with shared integration fixtures (`soyuz_client`,
  `e2e_env`)
- `tests/test_api_errors.py` — unit tests for API error handling
  (all JSON endpoints return 502 when soyuz-catalog is unreachable)
- PQL snippet card with copy-to-clipboard button on table detail page
- Jupyter loading spinner on notebook page: polls `/api/jupyter/status`
  until ready, shows error state with retry button after 30 s timeout

### Changed (Sprint 4)

- API JSON endpoints (`/api/tree`, `/api/catalogs`, `/api/schemas`,
  `/api/tables`, PATCH endpoints) return HTTP 502 with JSON error body
  when soyuz-catalog is unreachable (previously returned 500)
- `PQL.table()` and `PQL.write_table()` raise `ConnectionError` with
  a user-friendly message when soyuz-catalog is unreachable (previously
  raised raw `httpx.ConnectError`)
- Notebook page uses Alpine.js polling to wait for Jupyter readiness
  before loading the iframe; shows "Jupyter Not Available" error state
  if startup fails
- README.md rewritten with MVP setup docs, quick start, PQL usage
  examples, configuration table
- CLAUDE.md updated with Phase 1 completion, PQL/Jupyter/Alpine.js
  in stack, expanded layout section

### Previously added (Sprint 3)

- `pointlessql/services/jupyter.py` — async context manager that
  starts JupyterLab as a managed subprocess (SIGTERM/SIGKILL
  lifecycle, health-check polling, configurable port)
- `GET /notebook` route with embedded JupyterLab iframe; sidebar
  remains visible alongside the notebook for catalog browsing
- `GET /api/jupyter/status` JSON endpoint for subprocess status
- "Notebook" tab in the navbar (`base.html`)
- `{% block content_class %}` in `base.html` for per-page layout
  overrides (used by notebook page to remove content padding)
- Settings: `jupyter_enabled: bool = True`,
  `jupyter_port: int = 8888` (env overrides:
  `POINTLESSQL_JUPYTER_ENABLED`, `POINTLESSQL_JUPYTER_PORT`)
- `notebooks/getting_started.ipynb` — starter notebook demonstrating
  `PQL` read/write/list workflows
- New dependency: `jupyterlab>=4.0`
- `tests/test_jupyter.py` — 11 unit tests covering subprocess
  manager, route handlers, status API, and settings defaults

### Previously added (Sprint 2)

- `pointlessql/pql/` package — sync bridge between UC metadata and
  Delta Lake DataFrames, designed for notebooks and scripts
- `PQL` class with `table()` (read Delta as DataFrame),
  `write_table()` (write DataFrame + register metadata), and
  `list_catalogs()` / `list_schemas()` / `list_tables()` convenience
  methods
- New dependencies: `deltalake>=0.24`, `pandas>=2.2`
- `tests/test_pql.py` — unit tests with mocked soyuz client
- `tests/test_pql_integration.py` — integration round-trip test
  (create → write → read → verify)
- `PQL` re-exported from `pointlessql` package root

### Previously added (Sprint 1)

- `pointlessql/settings.py` — pydantic-settings module with
  `soyuz_catalog_url` setting (env override: `POINTLESSQL_SOYUZ_CATALOG_URL`)
- `pointlessql/services/soyuz_client.py` — factory for a configured
  `soyuz_catalog_client.Client` instance
- `tests/test_soyuz_client.py` — integration smoke tests against a
  live soyuz-catalog server (`@pytest.mark.integration`)
- `soyuz-catalog-client` as editable path dependency

### Changed

- `pointlessql/services/unitycatalog.py` — rewritten to delegate to
  the generated soyuz-catalog client instead of hand-rolled httpx
  calls. All methods convert attrs response objects to plain dicts
  via `.to_dict()` so templates stay unchanged
- `pointlessql/api/main.py` — lifespan uses `make_soyuz_client()`
  factory; error handling catches `UnexpectedStatus` alongside
  `httpx.HTTPError`

### Fixed

- Fixed code-gen bug in soyuz-catalog-client: `list_tables`
  `_parse_response` now handles the 200 status and returns
  `ListTablesResponse` instead of treating success as an unexpected
  status
