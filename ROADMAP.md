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
├── Phase 6 — Infrastructure & orchestration              ✅ done
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
│   ├── Sprint 18 — Postgres sync worker                   ✅ done (b9a36ae)
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
│   ├── Sprint 19 — DAG engine: data model + single-task   ✅ done (eab27a8)
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
│   ├── Sprint 20 — DAG engine: multi-task DAGs            ✅ done (34bfcc8)
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
│   └── Sprint 21 — DAG engine: observability + docs       ✅ done (e97c105)
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
├── Phase 7 — Live UI walkthrough via Playwright MCP        ✅ done
│   │
│   │   Goal: exercise every HTML route, every interactive Alpine
│   │   component, and every UI-relevant setting once, live, on
│   │   the developer's machine, to surface bugs that unit and
│   │   integration tests cannot reach because no browser has
│   │   ever touched the rendered templates. The fix for the
│   │   job-pause button (commit e09a661 — plain form POST landed
│   │   on a raw JSON page) is the prototype of what this phase
│   │   is meant to catch.
│   │
│   │   Treiber: the Playwright MCP tools Claude has in-session
│   │   (`browser_navigate`, `browser_click`, `browser_snapshot`,
│   │   `browser_fill_form`, `browser_evaluate`,
│   │   `browser_wait_for`, `browser_network_requests`). Deliver-
│   │   able per sprint is a set of Markdown playbooks under
│   │   `docs/e2e-walkthroughs/`: deterministic, step-for-step
│   │   walkthroughs that either Claude (via MCP) or a human can
│   │   replay against a freshly-composed stack. Each playbook
│   │   ends with a Found-Bugs section; fixes land in the same
│   │   sprint where feasible.
│   │
│   │   Explicitly not in scope: pytest-playwright suite,
│   │   GitHub Actions CI (the manual sprint gate of ruff +
│   │   pyright + pydoclint + alembic stands; pytest stays
│   │   skipped per the standing preference), screenshot
│   │   regression diffs, performance/load tests, mobile layout.
│   │
│   ├── Sprint 22 — Harness + data-surface walkthrough      ✅ done (7b837db)
│   │   ├── `docker-compose.e2e.yml` overlay: Postgres sidecar
│   │   │   (postgres:17-alpine) seeded by `scripts/pg-seed.sql`
│   │   │   as foreign-catalog target. No new services in the
│   │   │   base compose file
│   │   ├── `scripts/seed-e2e.py`: idempotent seed via existing
│   │   │   `PQL` helper (1-2 catalogs, a handful of schemas,
│   │   │   real Delta tables under `./warehouse/`). Same
│   │   │   interface as the `e2e_env` fixture in
│   │   │   `tests/conftest.py`
│   │   ├── `docs/e2e-walkthroughs/README.md` — stack start,
│   │   │   test-user credentials, how a future session
│   │   │   (human or Claude-via-MCP) replays a playbook
│   │   ├── 5 playbooks landed: `auth.md` (register first-user
│   │   │   bootstrap + second user + login + logout +
│   │   │   `/auth/me` + redirect-to-login + 403 for non-admin
│   │   │   on `/metrics`), `catalog-browsing.md` (index,
│   │   │   catalog/schema/table detail, sidebar tree with
│   │   │   sessionStorage, PQL snippet card),
│   │   │   `inline-editors.md` (`editable`, `properties_editor`,
│   │   │   `tags_editor`, `permissions_card` grant/revoke +
│   │   │   assigned/effective tabs, `lineage_card` click-
│   │   │   through — all three securable levels),
│   │   │   `federation.md` (connections + external-locations +
│   │   │   credentials: list + detail + create-modal +
│   │   │   deleteConfirm, plus non-admin-negative),
│   │   │   `foreign-catalog-sync.md` (create-modal on `/`,
│   │   │   "Sync now" button, sync-history card, mirrored
│   │   │   schemas/tables visible post-sync)
│   │   └── Bugs surfaced in the run either land as fixes in
│   │       the same sprint commit or are TODO-noted at the
│   │       end of the relevant playbook with a clear next
│   │       action. No "something was weird" entries
│   │
│   └── Sprint 23 — Orchestration, config matrix, operational  ✅ done (72a50bc)
│       ├── Extend `docker-compose.e2e.yml` with mock OIDC
│       │   provider (`ghcr.io/navikt/mock-oauth2-server`) +
│       │   env-var overlays for engine swaps and
│       │   scheduler/jupyter toggles
│       ├── 5 playbooks landed: `jobs-dag.md` (create modal,
│       │   run-now, pause/resume, task log viewer, retry
│       │   + fail-skip propagation, plus a `pg_sync`-kind
│       │   job against Sprint 22's Postgres sidecar as
│       │   cross-feature smoke),
│       │   `notebook.md` (`jupyter_enabled=true` iframe +
│       │   `/api/jupyter/status` polling; separate pass with
│       │   `=false` verifies navbar tab absence + disabled
│       │   state), `oidc.md` (SSO button visibility,
│       │   `/auth/sso` → mock consent → `/auth/callback` →
│       │   auto-user-creation, claim mapping), `operational.md`
│       │   (`/healthz` anon, `/metrics` admin positive +
│       │   negative, `/403` privilege detail, request-id
│       │   header via `browser_network_requests`),
│       │   `config-matrix.md` (one golden path per
│       │   `POINTLESSQL_ENGINE` in {pandas,duckdb,polars},
│       │   per `POINTLESSQL_LOG_FORMAT` in {text,json}, per
│       │   `DATABASE_URL` in {sqlite,postgres via existing
│       │   `docker-compose.postgres.yml`})
│       ├── Scheduler runs with `POINTLESSQL_SCHEDULER_TICK_SECONDS=2`
│       │   during orchestration playbooks so DAG state
│       │   transitions land in a reasonable time
│       ├── `CLAUDE.md`: short section on replaying the
│       │   playbooks (browser + manual OR Claude +
│       │   Playwright MCP)
│       └── Phase-close summary in `ROADMAP.md`: bugs found,
│           bugs fixed, bugs deferred with TODO pointers
│
│   Phase 7 close-out — five data-surface bugs surfaced by live
│   browser replays, all fixed same-commit:
│   - BUG-22-01 (commit 3f1da76): PointlesSQL wrapped soyuz
│     `400 INVALID_ARGUMENT` as `502 catalog_unavailable`. Fixed
│     by status-code-branching in `_wrap_catalog_errors`
│     (404 → `CatalogNotFoundError`, other 4xx → `ValidationError`)
│   - BUG-22-02 (commit 3f1da76): `POST /api/external-locations`
│     without `credential_name` leaked a bare `KeyError` as 500.
│     Same decorator now catches `KeyError` / `TypeError` from
│     generated `Create*.from_dict()` calls
│   - BUG-22-03 (commit 3f1da76): client-side form allowed an
│     empty `credentialName` to reach the server. Inline validation
│     added in `createExternalLocationForm()`
│   - BUG-23-01 (Sprint 23 commit): `oidc_enabled` computed prop
│     treated empty-string env vars as configured. Truthy check
│     added — compose overlay's `${OIDC_*:-}` fallbacks no longer
│     turn the SSO button on
│   - BUG-23-02 (Sprint 23 commit): `POST /api/jobs` committed the
│     job row *before* DAG validation; rejected cycle/unknown-dep
│     payloads left orphan rows in the DB. Refactored to flush
│     only, validate, then commit atomically
│
│   No bugs deferred. What Phase 7 bought: the templates have
│   now been rendered in a real browser at least once, and every
│   interactive path has a Markdown playbook that replays in
│   seconds. The ongoing contract: any future sprint touching
│   HTML/JS should replay the relevant playbook before landing,
│   and the Sprint 22 + 23 commits are the reference for
│   "what clean Found-bugs sections look like".
│
├── Phase 8 — Notebook-as-job (Databricks-style)          🔜 next
│   │
│   │   Goal: close the gap Phase 7 surfaced — the embedded
│   │   JupyterLab and the scheduler are currently two islands.
│   │   Phase 8 lets the user save a `.ipynb` in the workspace,
│   │   schedule it on a cron, run it with typed parameters,
│   │   open the executed output inline in the browser, and pin
│   │   cell outputs as dashboards. Subprocess-per-run (Papermill
│   │   spawns a fresh kernel per `execute_notebook`) is the
│   │   native execution model; no custom kernel pool.
│   │
│   ├── Sprint 24 — Papermill executor + JupyterLab viewer    ✅ done (062bb18)
│   │   ├── `papermill>=2.6` dep; `_papermill_executor` added to
│   │   │   `services/scheduler.py` `build_default_registry()` as
│   │   │   a third built-in kind next to `pg_sync` and `python`
│   │   ├── Config shape `{notebook_path, parameters,
│   │   │   timeout_seconds}`; output written to
│   │   │   `/app/notebooks/runs/{job_run_id}.ipynb`
│   │   ├── Principal forwarded via `POINTLESSQL_PRINCIPAL` env
│   │   │   var into the Papermill kernel subprocess; `PQL()`
│   │   │   constructor honours it
│   │   ├── New setting `notebook_execute_timeout_seconds`;
│   │   │   `asyncio.wait_for` cancellation around
│   │   │   `execute_notebook`
│   │   ├── Create-job modal gains a `kind` select +
│   │   │   papermill-specific fields (`notebook_path`,
│   │   │   `parameters` JSON)
│   │   ├── Recent-runs table on `job_detail.html` gains an
│   │   │   "Open in JupyterLab" link →
│   │   │   `/lab/tree/runs/{run_id}.ipynb`
│   │   └── `docs/e2e-walkthroughs/notebook-jobs.md` playbook
│   │
│   ├── Sprint 25 — Typed parameters UI                       ⏳ planned
│   │   ├── `GET /api/notebooks/inspect` using
│   │   │   `papermill.inspect_notebook` to return
│   │   │   `[{name, default, inferred_type, help}]`
│   │   ├── Create-job modal renders typed inputs per parameter
│   │   │   (text / number / checkbox / textarea) via Alpine
│   │   │   `x-for="p in parameters"`
│   │   ├── DAG support: a task of `kind=papermill` in the
│   │   │   tasks-JSON textarea reuses the same `config.parameters`
│   │   │   shape — no scheduler changes
│   │   ├── Job-detail Configuration card surfaces the resolved
│   │   │   parameters alongside the other config rows
│   │   └── Playbook extension with a parameter-tagged notebook
│   │
│   ├── Sprint 26 — Inline run render + Output artifacts       ⏳ planned
│   │   ├── `nbconvert>=7.0` dep
│   │   ├── `GET /jobs/{id}/runs/{rid}/notebook` renders the
│   │   │   output ipynb via
│   │   │   `HTMLExporter(template_name='lab')`; caches
│   │   │   `runs/{rid}.html` sidecar on first hit
│   │   ├── New "Output artifacts" card on `job_detail.html`,
│   │   │   slotted between the tasks table and the runs
│   │   │   history; click-a-run-row → embed iframe into the card
│   │   ├── View-mode toggle inside the card: **Rendered**
│   │   │   (static HTML, fast) vs **JupyterLab** (interactive
│   │   │   iframe), both pointing at the same ipynb
│   │   ├── `/notebooks/runs/` mounted via `StaticFiles` so the
│   │   │   raw ipynb + cached HTML are downloadable
│   │   └── Playbook extension: click past run → see cells inline
│   │
│   ├── Sprint 27 — Workspace file browser                    ⏳ planned
│   │   ├── `GET /api/notebooks/tree` → dir listing with
│   │   │   `parameters_tagged: bool` flag per notebook
│   │   ├── `GET /notebooks/workspace` page with a sidebar-tree
│   │   │   clone of `components/sidebar.html` `catalogTree()` —
│   │   │   same sessionStorage `pql.notebooks.open` pattern
│   │   ├── Tree-leaf "Schedule…" button pre-fills the
│   │   │   `#createJobModal` with `kind=papermill` +
│   │   │   `notebook_path=<clicked-path>`
│   │   ├── `POST /api/notebooks/upload` multipart endpoint
│   │   │   (admin-only) so the playbook can upload a notebook
│   │   │   from the browser, not via `docker cp`
│   │   ├── Navbar gains a "Workspace" link between Notebook
│   │   │   and Jobs
│   │   └── Playbook extension: upload → click-Schedule →
│   │       Run-now → Output artifacts card expands
│   │
│   └── Sprint 28 — Dashboards + run-compare; close Phase 8   ⏳ planned
│       ├── Alembic migration 008: `dashboards` table (slug
│       │   unique, notebook_path, job_id FK nullable, owner_id FK,
│       │   description, timestamps)
│       ├── `/dashboards` list + `/dashboards/{slug}` detail;
│       │   detail renders the latest run's nbconvert HTML with
│       │   `exclude_input=True` (code cells hidden — that's
│       │   what differentiates a dashboard from a notebook view)
│       ├── Admin CRUD routes + a "Refresh" shortcut that
│       │   triggers the bound job's Run-now
│       ├── Dashboards sidebar tree (another `catalogTree()`
│       │   clone) for navigating the list
│       ├── `GET /jobs/{id}/runs/{rid}/compare?to={other_rid}` —
│       │   two Sprint-26 iframes side-by-side with run metadata
│       │   headers; no cell-level diff highlighting (stub)
│       ├── New playbook `dashboards.md`
│       └── Phase-8 close-out summary in `ROADMAP.md` (bugs
│           surfaced / fixed / deferred), same shape as the
│           Phase-7 summary Sprint 23 added
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
