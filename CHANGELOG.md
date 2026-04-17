# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
