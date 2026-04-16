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

Status legend: ✅ done · 🔜 next · ⏳ planned · 🧊 on ice

## Current state

```text
PointlesSQL
│
├── Phase 0 — Project bootstrap                           ✅ done
│   │
│   ├── M0 — Repo skeleton                               ✅ done
│   │   ├── pyproject.toml (FastAPI, SQLAlchemy, Jinja2)
│   │   ├── hatchling + uv workspace layout
│   │   ├── frontend/{templates,css,js} force-include
│   │   ├── Apache-2.0 LICENSE
│   │   └── shoreguard-fresh style alignment
│   │
│   └── M1 — Catalog browser prototype                    ✅ done
│       ├── Hand-rolled async httpx UC client
│       │   (`pointlessql/services/unitycatalog.py`)
│       ├── 9 FastAPI endpoints: healthz, catalog/schema/table
│       │   list + detail, PATCH for catalog/schema updates,
│       │   full catalog tree JSON API
│       ├── 8 Jinja2 templates: catalog list, catalog detail,
│       │   schema detail, table detail with column list,
│       │   interactive sidebar (Alpine.js), inline editors
│       ├── Bootstrap 5.3 + HTMX + Alpine.js frontend
│       └── Dark-mode CSS baseline
│
├── Phase 1 — MVP: Catalog UI + Notebook + pql            ✅ done
│   │
│   │   Goal: a working "mini-Databricks" where the user can
│   │   browse UC metadata in a web UI, open a notebook tab,
│   │   and read/write Delta tables as Pandas DataFrames via
│   │   a `pql` helper that resolves table names through
│   │   soyuz-catalog.
│   │
│   ├── Sprint 1 — Generated client + settings            ✅ done (3a596e1)
│   │   ├── `uv add --editable ../soyuz-catalog/soyuz-catalog-client`
│   │   │   to pull in the typed generated client as a path
│   │   │   dependency (ADR-0007 in soyuz-catalog)
│   │   ├── New `pointlessql/settings.py` — pydantic-settings,
│   │   │   `soyuz_catalog_url: str = "http://127.0.0.1:8080"`
│   │   │   default, `SOYUZ_CATALOG_URL` env override
│   │   ├── New `pointlessql/services/soyuz_client.py` — thin
│   │   │   factory that returns a configured
│   │   │   `soyuz_catalog_client.Client` instance
│   │   ├── Rewrite `pointlessql/services/unitycatalog.py` to
│   │   │   delegate to the generated client functions instead
│   │   │   of hand-rolled httpx calls. `get_tree()` concurrent-
│   │   │   fetch logic stays. Delete dead httpx scaffolding
│   │   ├── Verify Jinja2 templates work with attrs model
│   │   │   objects (dot-notation access). Adapt any dict-style
│   │   │   access (`.items()`, subscript) if needed
│   │   └── First smoke test: `tests/test_soyuz_client.py` with
│   │       `integration` marker against a live soyuz-catalog
│   │
│   ├── Sprint 2 — pql helper library                     ✅ done (2442dc3)
│   │   ├── New package `pointlessql/pql/` — the central
│   │   │   component that bridges UC metadata and DataFrame
│   │   │   engines. This is what makes PointlesSQL more than
│   │   │   a browser
│   │   ├── `PQL` class wrapping `soyuz_catalog_client.Client`
│   │   │   (sync variant)
│   │   ├── `pql.table("catalog.schema.table")` — calls
│   │   │   `get_table` on soyuz, extracts `storage_location`,
│   │   │   reads Delta via `deltalake.DeltaTable.to_pandas()`,
│   │   │   returns `pd.DataFrame`
│   │   ├── `pql.write_table(df, "catalog.schema.table")` —
│   │   │   writes Delta via `deltalake.write_deltalake()`,
│   │   │   then creates/updates table metadata on soyuz
│   │   │   (columns derived from DataFrame schema)
│   │   ├── Convenience: `pql.list_catalogs()`,
│   │   │   `pql.list_schemas(catalog)`,
│   │   │   `pql.list_tables(catalog, schema)`
│   │   ├── New deps: `deltalake>=0.24`, `pandas>=2.2`
│   │   └── Tests: unit tests with mocked soyuz + one
│   │       integration test (create → write → read → verify)
│   │
│   ├── Sprint 3 — Jupyter notebook tab                   ✅ done (eee7ade)
│   │   ├── New dep: `jupyterlab>=4.0`
│   │   ├── `GET /notebook` route → template with iframe to
│   │   │   `http://localhost:{jupyter_port}/lab`
│   │   ├── Lifespan integration: `main.py` starts Jupyter as
│   │   │   a subprocess on startup, kills it on shutdown.
│   │   │   No auth token (single-user localhost)
│   │   ├── Navbar: "Notebook" tab in `base.html`
│   │   ├── Sidebar remains visible alongside the notebook
│   │   │   iframe so users can browse catalogs while working
│   │   ├── Settings: `jupyter_port: int = 8888`,
│   │   │   `jupyter_enabled: bool = True`
│   │   └── Starter notebook: `notebooks/getting_started.ipynb`
│   │       demonstrating `pql.table("...")` → DataFrame
│   │
│   └── Sprint 4 — Polish, E2E tests, docs               ✅ done (c419f92)
│       ├── E2E smoke tests: soyuz + PointlesSQL up, create
│       │   catalog/schema via PQL, verify it appears in
│       │   browser with correct columns and PQL snippet
│       ├── Error handling: API JSON endpoints return 502
│       │   when soyuz is down; PQL raises ConnectionError
│       │   with user-friendly message
│       ├── UX: copy-paste `pql.table(...)` snippet card on
│       │   table detail page, Alpine.js loading spinner for
│       │   Jupyter startup with retry on failure, improved
│       │   "Jupyter not available" error state
│       ├── README.md: MVP setup docs, quick start, PQL usage
│       ├── CLAUDE.md updates for Phase 1 completion
│       └── Tests: `test_api_errors.py`, `test_e2e.py`,
│           `conftest.py` shared fixtures, PQL ConnectionError
│           tests
│
├── Phase 2 — Catalog UI enhancements                     ✅ done
│   │
│   └── Sprint 5 — Tags, permissions, lineage, federation ✅ done (8354fec)
│       ├── Tags editor card on catalog/schema/table detail
│       │   pages — add/remove tags via PATCH, Alpine.js
│       │   interactive component
│       ├── Permissions card with Assigned + Effective tabs
│       │   on all detail pages — grant/revoke privileges,
│       │   view inherited permissions
│       ├── Lineage card on table detail page — upstream and
│       │   downstream node lists with depth indicators and
│       │   clickable links to related tables
│       ├── Lakehouse Federation: full CRUD pages for
│       │   connections, external locations, and credentials
│       │   with create modals, inline comment editing,
│       │   delete-with-confirmation, navbar dropdown
│       ├── Parallel fetches via asyncio.gather on detail
│       │   pages (tags + permissions + effective + lineage)
│       ├── 21 new facade methods in unitycatalog.py
│       ├── 25 new API routes + 6 HTML page routes
│       └── Tests: test_tags_permissions.py,
│           test_federation.py, extended test_api_errors.py
│           (38 new tests, 75 total pass)
│
├── Phase 3 — Auth & multi-user                           ✅ done
│   │
│   │   Goal: turn PointlesSQL from a single-user localhost
│   │   app into a multi-user system with login, JWT sessions,
│   │   and grant enforcement. soyuz-catalog stores grants
│   │   but never enforces (ADR-0005); PointlesSQL is the
│   │   enforcement layer.
│   │
│   │   DB: SQLAlchemy 2.0 async, SQLite default
│   │   (`aiosqlite`), PostgreSQL via `DATABASE_URL` override.
│   │
│   ├── Sprint 6 — Alembic + local users + JWT auth       ✅ done (5c346cd)
│   │   ├── Initialize Alembic: `env.py`, `alembic.ini`,
│   │   │   first migration
│   │   ├── Settings: `database_url` (default
│   │   │   `sqlite+aiosqlite:///./pointlessql.db`),
│   │   │   `secret_key` for JWT signing
│   │   ├── SQLAlchemy 2.0 async models:
│   │   │   - `User` (id, email, display_name,
│   │   │     password_hash, is_admin, created_at)
│   │   │   - `Session` (id, user_id FK, token_hash,
│   │   │     created_at, expires_at)
│   │   ├── `pointlessql/services/auth.py` — register,
│   │   │   login (bcrypt via pwdlib), verify JWT, logout
│   │   ├── API routes: `POST /auth/register`,
│   │   │   `POST /auth/login`, `POST /auth/logout`,
│   │   │   `GET /auth/me`
│   │   ├── Auth middleware: extract user from JWT cookie
│   │   │   (`pql_session`), attach to `request.state.user`
│   │   ├── Login page (`pages/login.html`), register page
│   │   │   (`pages/register.html`)
│   │   ├── Protect all existing routes: unauthenticated →
│   │   │   redirect to `/login`
│   │   ├── Navbar: show current user email + logout button
│   │   ├── First-run bootstrap: if no users exist, first
│   │   │   registered user becomes admin
│   │   └── Tests: auth service unit tests, login/register
│   │       API tests, middleware tests
│   │
│   ├── Sprint 7 — Principal forwarding + enforcement     ✅ done (9046793)
│   │   ├── Per-request `X-Principal` header forwarding on
│   │   │   all soyuz-catalog client calls (via
│   │   │   `UnityCatalogClient.for_principal()` classmethod
│   │   │   + `make_principal_client()` factory)
│   │   ├── Authorization enforcement: `check_privilege()` and
│   │   │   `check_privilege_from_effective()` in
│   │   │   `services/authorization.py` — checks effective
│   │   │   permissions before each operation
│   │   ├── Privilege mapping: `USE CATALOG`, `USE SCHEMA`,
│   │   │   `SELECT`, `MODIFY`, `MANAGE_GRANTS` per route
│   │   ├── Admin bypass: `is_admin` users skip enforcement
│   │   ├── Federation routes restricted to admin-only
│   │   ├── `403 Forbidden` error page (`pages/403.html`)
│   │   │   with privilege details and "contact admin" hint
│   │   ├── Permissions UI: current user row highlighted with
│   │   │   "you" badge, grant/revoke hidden without
│   │   │   `MANAGE_GRANTS` (`can_manage` flag)
│   │   ├── Audit log: `audit_log` table (Alembic 002),
│   │   │   `services/audit.py` logs write operations
│   │   └── Tests: 39 new tests — `test_authorization.py`
│   │       (15), `test_enforcement.py` (21),
│   │       `test_audit.py` (3), non-admin user fixture
│   │
│   └── Sprint 8 — OIDC / OAuth2 provider                ✅ done (f6551eb)
│       ├── OAuth2 authorization code flow with PKCE
│       ├── Settings: `oidc_discovery_url`, `oidc_client_id`,
│       │   `oidc_client_secret` (optional, for confidential
│       │   clients)
│       ├── Map OIDC claims (sub, email, name) to local User
│       ├── Auto-create user on first OIDC login
│       ├── Login page: "Sign in with SSO" button alongside
│       │   local login form (both remain available)
│       ├── `/auth/callback` route for OAuth2 redirect
│       └── Tests: OIDC flow with mocked provider (33 new,
│           177 total pass)
│
├── Phase 4 — Packaging & deployment                      ✅ done
│   │
│   │   Goal: make PointlesSQL + soyuz-catalog runnable
│   │   with a single `docker compose up` — no manual
│   │   cloning, no editable path deps, no process juggling.
│   │   Swap the soyuz-catalog-client path dependency for
│   │   a pinned wheel so the image builds stand-alone.
│   │
│   ├── Sprint 9 — Dockerfiles + docker-compose           ✅ done (1bf34e8)
│   │   ├── `Dockerfile` for PointlesSQL (3-stage:
│   │   │   soyuz-client-builder → builder → runtime,
│   │   │   python:3.14-slim, uv pip install)
│   │   ├── `Dockerfile.soyuz` for soyuz-catalog (2-stage:
│   │   │   builder → runtime, same base image)
│   │   ├── `docker-compose.yml`: services `soyuz-catalog`
│   │   │   + `pointlessql` (Jupyter embedded as subprocess),
│   │   │   shared `./warehouse` volume for Delta storage,
│   │   │   `additional_contexts` for soyuz-catalog source
│   │   ├── Swap editable `soyuz-catalog-client` path dep
│   │   │   for a built wheel via multi-stage Docker build
│   │   │   (`sed` strips `[tool.uv.sources]` at build time)
│   │   ├── Settings: configurable `host`/`port` via
│   │   │   `POINTLESSQL_HOST`/`POINTLESSQL_PORT`,
│   │   │   SQLite default verified, Postgres via override
│   │   ├── Health checks: python httpx one-liners (no
│   │   │   curl in slim image), `depends_on: service_healthy`
│   │   ├── `.dockerignore` for clean builds
│   │   ├── Jupyter `--allow-root` + `--ip` from settings
│   │   │   for Docker compatibility
│   │   ├── Frontend path fallback for installed wheel
│   │   │   (`pointlessql/_frontend` vs dev `frontend/`)
│   │   └── README: Docker quick-start section
│   │
│   └── Sprint 10 — Postgres option + env polish          ✅ done (8c660d3)
│       ├── `docker-compose.postgres.yml` override adding a
│       │   Postgres service as the metadata DB
│       ├── Alembic migrations verified Postgres-compatible
│       │   (`render_as_batch=True` already set, no changes
│       │   needed)
│       ├── `.env.example` with all POINTLESSQL_* vars
│       │   documented
│       ├── `POINTLESSQL_BASE_URL` setting for OIDC
│       │   redirect_uri in non-localhost deployments
│       ├── `psycopg[binary]>=3.1` promoted to main deps
│       └── Tests: `TEST_DATABASE_URL` env var for Postgres
│           matrix, `drop_all` teardown for clean isolation
│
├── Phase 5 — Pluggable compute engines                   ✅ done
│   │
│   │   Vision: user picks a "kernel profile" (container image
│   │   or local venv) with a specific engine. The pql helper
│   │   abstracts the engine; the notebook just calls
│   │   `pql.table(...)` and gets back the engine's native
│   │   frame type.
│   │
│   ├── Sprint 11 — Engine abstraction + DuckDB           ✅ done (814e992)
│   │   ├── `pointlessql/pql/engine.py` — `Engine` protocol
│   │   │   with `read(storage_location) -> FrameType`,
│   │   │   `write(frame, storage_location, mode)`, and
│   │   │   `columns_info(frame)` methods
│   │   ├── Extract current Pandas logic into `PandasEngine`
│   │   ├── `DuckDBEngine`: `DeltaTable.to_pyarrow_dataset()`
│   │   │   → `conn.from_arrow()`, returns `DuckDBPyRelation`
│   │   ├── Settings: `POINTLESSQL_ENGINE=pandas|duckdb`
│   │   ├── `PQL` auto-selects engine from setting, or
│   │   │   accepts `engine=` kwarg
│   │   ├── New deps: `duckdb>=1.0`, `pyarrow>=17.0`
│   │   └── Tests: engine protocol compliance suite (20 new
│   │       tests, parameterized across both engines,
│   │       201 total pass)
│   │
│   ├── Sprint 12 — Polars engine                         ✅ done (8588ad0)
│   │   ├── `PolarsEngine`: `DeltaTable.to_pyarrow_table()`
│   │   │   → `pl.from_arrow()`, returns `pl.DataFrame`
│   │   ├── New dep: `polars>=1.0`
│   │   ├── `POINTLESSQL_ENGINE=polars` env var in
│   │   │   `docker-compose.yml`
│   │   └── Tests: engine compliance suite parameterized
│   │       across all three engines (9 new tests)
│   │
│   └── Spark engine                                      🧊 on ice
│       └── PySpark kernel with UC connector configured
│           by PointlesSQL at startup (needs JVM — low
│           priority, DuckDB/Polars cover most use cases)
│
├── Phase 5.5 — Quality and observability                  ✅ done
│   │
│   │   Goal: harden the codebase without adding features —
│   │   strict types, domain exception hierarchy, centralized
│   │   error handling, complete docstrings, structured logging.
│   │
│   ├── Sprint 13 — Exception hierarchy + strict pyright   ✅ done (5511871)
│   │   ├── `pointlessql/exceptions.py` — `PointlessSQLError`
│   │   │   base with `status_code`, `error_code`, `detail`;
│   │   │   `CatalogUnavailableError` (502),
│   │   │   `CatalogNotFoundError` (404),
│   │   │   `AuthenticationError` (401),
│   │   │   `AuthorizationError` (403, reparents AccessDenied),
│   │   │   `EngineError` (500), `ValidationError` (422,
│   │   │   inherits ValueError for compat)
│   │   ├── `pointlessql/types.py` — `UserInfo` TypedDict
│   │   │   replacing `dict[str, Any]` user objects
│   │   ├── Pyright strict mode (source only), zero errors
│   │   ├── PQL + engine raise domain exceptions instead of
│   │   │   builtins (ConnectionError → CatalogUnavailableError,
│   │   │   LookupError → CatalogNotFoundError,
│   │   │   ValueError → ValidationError)
│   │   ├── OIDCError reparented under PointlessSQLError
│   │   ├── Broad exception catches narrowed in auth.py
│   │   │   and oidc.py
│   │   └── Tests: 17 new exception tests (230 total pass)
│   │
│   ├── Sprint 14 — Centralized API error handling         ✅ done (d766136)
│   │   ├── `pointlessql/api/error_handlers.py` — centralized
│   │   │   `PointlessSQLError` handler dispatching JSON envelope
│   │   │   for `/api/...` routes and 403.html for HTML routes
│   │   ├── Consistent JSON error envelope: `{"error": {"code",
│   │   │   "message", "request_id"}}` on all API error responses
│   │   ├── UC facade (`unitycatalog.py`) wraps all methods with
│   │   │   `_wrap_catalog_errors` decorator converting
│   │   │   `httpx.HTTPError`/`UnexpectedStatus` →
│   │   │   `CatalogUnavailableError` at the source
│   │   ├── `_require_admin` converted from return-response to
│   │   │   raise-`AuthorizationError`; `_deny_json`,
│   │   │   `_deny_html`, `_require_admin_html` removed
│   │   ├── ~40 duplicated try/except blocks removed from
│   │   │   `main.py` (1164 → 815 lines)
│   │   ├── Request-ID middleware: UUID4 per request (or
│   │   │   forwarded `X-Request-ID`), in error envelope +
│   │   │   response header
│   │   └── Tests: 13 new tests (243 total pass)
│   │
│   ├── Sprint 15 — Docstrings + pydoclint                  ✅ done (33b97ef)
│   │   ├── `[tool.pydoclint]` config in `pyproject.toml`:
│   │   │   Google style, types in signatures only (not
│   │   │   duplicated in docstrings), `__init__` docs merged
│   │   │   into class docstrings
│   │   ├── Ruff `D107` ignored (pydoclint owns `__init__`
│   │   │   docstring policy via `allow-init-docstring`)
│   │   ├── Fixed DOC301 (3): merged `__init__` docstrings
│   │   │   into class docstrings for `PQL`, `DuckDBEngine`,
│   │   │   `UnityCatalogClient`
│   │   ├── Fixed DOC602/603/101/103: restructured exception
│   │   │   hierarchy docstrings (`PointlessSQLError`,
│   │   │   `AuthorizationError`) — constructor params in
│   │   │   Args, class-level annotations in Attributes
│   │   ├── Fixed DOC501/503: accurate Raises sections in
│   │   │   `PQL.table`, `PQL.write_table`,
│   │   │   `find_or_create_oidc_user`
│   │   └── pydoclint: 0 violations, pyright: 0 errors,
│   │       243 tests pass
│   │
│   └── Sprint 16 — Logging and observability              ✅ done (e520c51)
│       ├── `pointlessql/logging_config.py` — `request_id_var`
│       │   contextvar, `RequestIdFilter`, opt-in `JSONFormatter`,
│       │   idempotent `configure_logging(level, fmt)`; installs
│       │   a `setLogRecordFactory` so every record carries
│       │   `request_id` (caplog-compatible without per-handler
│       │   hookup)
│       ├── Settings: `POINTLESSQL_LOG_LEVEL`,
│       │   `POINTLESSQL_LOG_FORMAT=text|json`
│       ├── `request_id_middleware` sets the contextvar (in
│       │   addition to `request.state.request_id`) and resets
│       │   it in `finally` — service-layer logs now carry the
│       │   request ID without receiving the Request object
│       ├── `configure_logging` called at module import time so
│       │   uvicorn `--reload` workers and direct `uvicorn`
│       │   invocations both pick up the format
│       ├── Module-level loggers added to `api/main.py`,
│       │   `api/error_handlers.py`, `services/unitycatalog.py`;
│       │   `_wrap_catalog_errors` now logs the original transport
│       │   exception before re-raising (was silent before)
│       └── 8 new tests — JSONFormatter validity + exc_info,
│           RequestIdFilter, idempotency, text/json switching,
│           end-to-end request-ID propagation via caplog
│           (251 total pass)
│
├── Phase 6 — Infrastructure & orchestration              🔜 next
│   │
│   │   Goal: turn PointlesSQL from a metadata browser + notebook
│   │   into a system that *operates* on data — mirror foreign
│   │   Postgres databases as managed UC catalogs, and run those
│   │   mirror jobs (plus arbitrary user-authored jobs) on a
│   │   schedule. soyuz-catalog already has foreign-catalog
│   │   primitives (Connection + CreateCatalog(connection_name=…),
│   │   soyuz Sprint 28 / ADR-0013), so the work here is UI + sync
│   │   + scheduler, not a new backend concept.
│   │
│   ├── Sprint 17 — Foreign catalog UI                     ✅ done (83a024c)
│   │   ├── "Create foreign catalog" modal on the catalogs page:
│   │   │   pick an existing Connection, set free-form options
│   │   │   (passthrough dict for connector config), submit to
│   │   │   soyuz's `CreateCatalog(connection_name=…)` endpoint
│   │   ├── Catalog detail page: show `connection_name` +
│   │   │   `options` card when present; badge in tree/sidebar
│   │   │   distinguishes foreign from managed catalogs
│   │   ├── Inline edit for `options` (PATCH via generated
│   │   │   client — soyuz already accepts it)
│   │   ├── No backend sync yet — this sprint just wires up the
│   │   │   metadata surface so Sprint 18 has a target
│   │   └── Tests: facade method(s), route tests, HTML snapshot
│   │       of the new card
│   │
│   ├── Sprint 18 — Postgres sync worker                   ⏳ planned
│   │   ├── New service `pointlessql/services/pg_sync.py`:
│   │   │   introspects a live Postgres (via `psycopg`, already
│   │   │   in deps) and emits a diff against the current UC
│   │   │   state under a foreign catalog — adds, drops, column
│   │   │   changes
│   │   ├── Apply diff: create schemas + external tables on
│   │   │   soyuz-catalog with column types mapped from
│   │   │   `information_schema.columns` → UC types
│   │   ├── Manual "Sync now" button on foreign-catalog detail
│   │   │   page; POST to `/api/catalogs/{name}/sync`
│   │   ├── Alembic migration 004: `sync_run` table
│   │   │   (catalog_name, started_at, finished_at, status,
│   │   │   added/changed/dropped counts, error)
│   │   ├── Sync history card on the catalog detail page
│   │   ├── Secrets: connection options with keys matching
│   │   │   `(?i)pass|secret|key|token` are read from the
│   │   │   Credential bound to the Connection, not from
│   │   │   `options` (reusing existing Credential CRUD)
│   │   └── Tests: unit tests with a stub Postgres introspector,
│   │       plus an integration test under `@pytest.mark.integration`
│   │       using a short-lived Postgres container (documented
│   │       but not required in CI)
│   │
│   ├── Sprint 19 — DAG engine: data model + single-task   ⏳ planned
│   │   ├── Alembic migration 005: `jobs`, `job_runs`,
│   │   │   `job_tasks`, `job_logs`. `jobs` has
│   │   │   (id, name, cron_expr, run_as_user_id, kind,
│   │   │   config JSON, is_paused); `job_runs` has
│   │   │   (id, job_id FK, started_at, finished_at, status,
│   │   │   trigger: scheduled|manual)
│   │   ├── Scheduler: in-process asyncio loop started from
│   │   │   `_lifespan`, ticks every 30 s, reads due jobs
│   │   │   (`croniter` — new dep, ~10 KB). No APScheduler —
│   │   │   it's overkill for a single-worker install
│   │   ├── Single-task execution: one Python callable per
│   │   │   job `kind`. Kind `"pg_sync"` calls Sprint 18's
│   │   │   service; kind `"python"` runs a registered
│   │   │   callable from a plugin entry point
│   │   ├── Run-as-user: scheduler resolves `run_as_user_id`,
│   │   │   builds a `UnityCatalogClient.for_principal(...)`
│   │   │   so X-Principal forwards to soyuz and authorization
│   │   │   applies — no new concept, just wiring
│   │   ├── UI: `/jobs` list page, job detail with run history,
│   │   │   "Run now" button, pause toggle
│   │   ├── Settings: `POINTLESSQL_SCHEDULER_ENABLED=true|false`
│   │   │   so tests and single-shot CLI invocations can opt out
│   │   └── Tests: scheduler tick logic with frozen clock,
│   │       job-run state transitions, run-as-user X-Principal
│   │       forwarding, `pg_sync` kind end-to-end
│   │
│   ├── Sprint 20 — DAG engine: multi-task DAGs            ⏳ planned
│   │   ├── `job_tasks` gains `depends_on` (JSON list of task
│   │   │   ids within the same job); scheduler walks the DAG
│   │   │   in topological order, skips downstream tasks when
│   │   │   an upstream fails
│   │   ├── Retry policy per task: `max_retries`,
│   │   │   `retry_backoff_seconds`
│   │   ├── `job_logs` populated per task run; log viewer uses
│   │   │   Sprint 16 structured logging (request-ID-style
│   │   │   `job_run_id` + `task_id` contextvars)
│   │   ├── Concurrency limit: `max_parallel_runs` per job and
│   │   │   a global ceiling from settings
│   │   ├── UI: DAG preview (simple list, not a graph — that's
│   │   │   gold-plating for v1), task-level retry/status
│   │   │   indicators, expandable log panel
│   │   └── Tests: topological order, fail-skip propagation,
│   │       retry with backoff, concurrency limits
│   │
│   └── Sprint 21 — DAG engine: observability + docs       ⏳ planned
│       ├── Prometheus metrics (`prometheus_client` is already a
│       │   dep but unused): `pointlessql_job_runs_total{status}`,
│       │   `pointlessql_job_run_duration_seconds` histogram,
│       │   `pointlessql_scheduler_tick_lag_seconds` gauge
│       ├── `/metrics` endpoint guarded by admin-only check
│       ├── Optional failure webhook: per-job `on_failure_url`
│       │   POSTs a minimal JSON payload (job_id, run_id, status,
│       │   error) — opt-in, no retries on the webhook itself
│       ├── Docs: `docs/jobs.md` — how to author a custom job
│       │   kind, plugin entry-point shape, worked example
│       │   using `pql` inside a task
│       └── Tests: metric emission, webhook invocation with
│           stubbed httpx, admin-only enforcement on `/metrics`
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

This file is read first by every new Claude Code session (see
[`CLAUDE.md`](CLAUDE.md)).
