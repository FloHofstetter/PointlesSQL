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
├── Phase 8 — Notebook-as-job (Databricks-style)          ✅ done
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
│   ├── Sprint 25 — Typed parameters UI                       ✅ done (d15e7ef)
│   │   ├── `GET /api/notebooks/inspect` using
│   │   │   `papermill.inspect_notebook` to return
│   │   │   `[{name, default, inferred_type, help}]`
│   │   ├── Create-job modal renders typed inputs per parameter
│   │   │   (text / number / checkbox / textarea) via Alpine
│   │   │   `x-for="p in parameters"`; `<details>` advanced
│   │   │   fallback keeps the raw JSON textarea for hand-edits
│   │   ├── DAG support: a task of `kind=papermill` in the
│   │   │   tasks-JSON textarea reuses the same `config.parameters`
│   │   │   shape — no scheduler changes; help-text gained a
│   │   │   worked example
│   │   ├── Job-detail Configuration card surfaces the resolved
│   │   │   parameters (Notebook + Parameters rows) instead of
│   │   │   the raw `<pre>{ config }</pre>` for papermill kinds
│   │   ├── Promoted `_resolve_notebook_path` → public
│   │   │   `resolve_notebook_path` so the inspect route reuses
│   │   │   the executor's traversal guard
│   │   └── Playbook extension: Part E in
│   │       `docs/e2e-walkthroughs/notebook-jobs.md` + a second
│   │       seed notebook `smoke_typed_params.ipynb`
│   │       (`count: int = 3`, `enabled: bool = True`,
│   │       `label: str = "hello"`) — one per typed-input branch
│   │
│   ├── Sprint 26 — Inline run render + Output artifacts       ✅ done (6652869)
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
│   │   ├── Downloads served via `/jobs/{id}/runs/{rid}/notebook/
│   │   │   download?format={ipynb,html}` with `_load_job_or_404`
│   │   │   visibility enforcement. Scope change: the original
│   │   │   plan mounted `/notebooks/runs/` via `StaticFiles`, but
│   │   │   that would let any logged-in user exfiltrate another
│   │   │   user's run output by guessing `run_id`s. The
│   │   │   visibility-checked route closes that leak
│   │   └── Playbook extension: click past run → see cells inline
│   │
│   ├── Sprint 27 — Workspace file browser                    ✅ done (72a1438)
│   │   ├── `GET /api/notebooks/tree` (admin-only) → nested
│   │   │   dir listing with `parameters_tagged: bool` per
│   │   │   notebook leaf; the top-level `runs/` executor-output
│   │   │   subdir is skipped
│   │   ├── `GET /notebooks/workspace` page (admin-only) with a
│   │   │   flattened-tree Alpine component — `sessionStorage`
│   │   │   keys `pql.notebooks` + `pql.notebooks.open`, same
│   │   │   shape as the catalog sidebar's `catalogTree()`
│   │   ├── Tree-leaf "Schedule…" button navigates to
│   │   │   `/jobs?prefill_kind=papermill&prefill_notebook_path=<path>`;
│   │   │   the existing `#createJobModal` reads those query
│   │   │   params on mount, pre-fills `kind` + `notebookPath`,
│   │   │   chains `inspect()`, and opens the modal
│   │   ├── `POST /api/notebooks/upload` multipart endpoint
│   │   │   (admin-only); validates `.ipynb` extension, parses
│   │   │   the body as JSON before writing, atomically replaces
│   │   │   via a `.tmp` sidecar, and requires an explicit
│   │   │   `overwrite=true` form field to clobber an existing
│   │   │   file — safer-by-default so a re-upload never silently
│   │   │   loses hand-edits made inside the embedded JupyterLab
│   │   ├── New service module
│   │   │   `pointlessql/services/notebook_workspace.py` holds
│   │   │   `list_workspace_tree` and `resolve_upload_target`
│   │   │   (sibling of Sprint 24's `resolve_notebook_path` that
│   │   │   allows a not-yet-existing file but requires the
│   │   │   parent dir to exist)
│   │   ├── Navbar gains a "Workspace" link (admin-only) between
│   │   │   Notebook and Jobs
│   │   └── Playbook extension: Part G in
│   │       `docs/e2e-walkthroughs/notebook-jobs.md` — upload →
│   │       click-Schedule → Run-now → Output artifacts card
│   │       expands, plus the non-admin 403 pass and the
│   │       `.py` / `..` / existing-without-overwrite negatives
│   │
│   └── Sprint 28 — Dashboards + run-compare; close Phase 8   ✅ done (5f73115)
│       ├── Alembic migration 008: `dashboards` table (slug
│       │   unique, title, description, notebook_path, job_id FK
│       │   nullable with `ON DELETE SET NULL`, owner_id FK,
│       │   timestamps)
│       ├── `Dashboard` ORM model + `_serialize_dashboard`
│       │   helper; `_load_dashboard_or_404` visibility-neutral
│       │   (consumers see everything; admin gate lives on the
│       │   mutating routes + Refresh)
│       ├── Admin CRUD: `POST`, `PATCH /api/dashboards/{slug}`,
│       │   `DELETE /api/dashboards/{slug}`, plus
│       │   `POST /api/dashboards/{slug}/refresh` that reuses
│       │   `scheduler_service.execute_run(..., trigger="manual")`
│       │   — no new execution concept, just a shortcut for the
│       │   dashboard consumer UI
│       ├── `render_run_notebook` in
│       │   `services/notebook_render.py` gains an
│       │   `exclude_input: bool = False` keyword; dashboard-mode
│       │   output is cached to a sibling `{run_id}.dashboard.html`
│       │   sidecar so the two variants coexist
│       ├── `GET /jobs/{id}/runs/{rid}/notebook` gains an optional
│       │   `?exclude_input=true` query param threaded through to
│       │   the render helper (used by the dashboard iframe)
│       ├── `/dashboards` list page + `/dashboards/{slug}` detail;
│       │   detail fetches the latest `status="succeeded"` run for
│       │   the bound job and iframe-sources the code-hidden render
│       ├── Dashboards sidebar component
│       │   (`components/dashboards_sidebar.html`) mirroring the
│       │   Sprint 27 workspace tree — `sessionStorage` key
│       │   `pql.dashboards`, admin-neutral; `base.html` swaps it
│       │   in when `active_page == 'dashboards'`
│       ├── `GET /jobs/{id}/runs/{rid}/compare?to={other_rid}` —
│       │   two Sprint-26 iframes side-by-side with run metadata
│       │   headers; both run ids validated to belong to the same
│       │   job, otherwise 404 (prevents foreign-run leak). No
│       │   cell-level diff highlighting (stub)
│       ├── "Compare runs" card on `pages/job_detail.html` (only
│       │   when ≥ 2 completed runs exist) with two `<select>`s and
│       │   a Compare button that navigates to the compare URL
│       ├── New navbar "Dashboards" link (visible to every
│       │   logged-in user — consumer surface, not admin-only)
│       └── New playbook `docs/e2e-walkthroughs/dashboards.md`
│           covering the create-modal → detail iframe → Refresh →
│           sidebar → non-admin visibility → run-compare flow, plus
│           the foreign-run 404 negative
│
│   Phase 8 close-out — Sprint 28 landed the final piece
│   (dashboards + run-compare). Live Playwright replay of the
│   `dashboards.md` playbook surfaced two bugs, both fixed
│   same-sprint:
│   - BUG-28-01 (commit 23022f5): dashboard detail iframe
│     sourced the Sprint-26 job-run render route, which enforces
│     admin-or-job-owner visibility — non-admin consumers saw a
│     404 inside the iframe instead of the published output.
│     Fixed by adding a sibling `GET /dashboards/{slug}/output`
│     whose visibility boundary is the dashboard itself.
│   - BUG-28-02 (commit 733919d): pre-existing Sprint-24
│     concurrency bug surfaced by the Sprint-28 Refresh button.
│     Papermill's `execute_notebook(cwd=…)` does a process-wide
│     `os.chdir`; concurrent runs race against
│     `Path("notebooks").resolve()` callers and resolve to a
│     non-existent `/app/notebooks/notebooks`. Fixed by
│     capturing `_STARTUP_CWD = Path.cwd()` at settings module
│     import and anchoring relative `notebooks_dir` defaults
│     against it in a field_validator.
│
│   What Phase 8 bought: Papermill-executed notebooks now have
│   a full lifecycle inside PointlesSQL — scheduled execution
│   (Sprint 24) with typed parameters (Sprint 25), inline
│   rendered output (Sprint 26), a workspace file browser for
│   upload + schedule (Sprint 27), and now a publishable
│   dashboard surface that hides code cells + a run-compare
│   view (Sprint 28). The embedded JupyterLab and the
│   scheduler are no longer two islands.
│
├── Phase 9 — UX overhaul & discoverability              ✅ done
│   │
│   │   Goal: turn the *functionally complete* Databricks-style
│   │   UI of Phase 8 into one that actually *feels* like a
│   │   modern alternative. The Phase-7/8 replays proved every
│   │   route works; the Phase-9 survey (Playwright screenshots
│   │   of every major HTML endpoint) exposed a tier of UX gaps
│   │   that a functional audit missed: a raw-JSON 404 with no
│   │   navbar, a left-stuck login card, a near-empty home,
│   │   list pages without search/filter/sort, a table detail
│   │   with no data preview, no global search, no toasts, no
│   │   mobile layout, and ad-hoc `fetch` error handling copy-
│   │   pasted across 5 JS files. The user's explicit must-
│   │   haves are a command palette (Cmd+K), a real home
│   │   dashboard, mobile/tablet responsiveness, and a data
│   │   preview on table detail.
│   │
│   │   Constraint: *"einfach und schnell"* — the stack stays
│   │   (FastAPI + Jinja2 + Bootstrap 5.3 + HTMX + Alpine.js).
│   │   No React/Vue migration. All work is design tokens, new
│   │   components, two new API routes. Every sprint fits in
│   │   one commit and closes with the usual
│   │   ruff+pyright+pydoclint+alembic gate plus a Playwright
│   │   replay of the touched surface.
│   │
│   ├── Sprint 29 — Design-system foundation              ✅ done (75b4dd8)
│   │   ├── CSS variable system: spacing (`--pql-space-1..8`),
│   │   │   typography (`--pql-text-xs..3xl`), radius, elevation,
│   │   │   motion — one token scale per concern, no magic values
│   │   ├── Semantic color tokens (success/warning/danger/info/
│   │   │   neutral) with background + foreground pairs; brand
│   │   │   accent `#76b900` stays; light-mode variant prepared
│   │   │   (opt-in via `data-bs-theme="light"`)
│   │   ├── Inter font self-hosted (~50 kB woff2)
│   │   ├── CSS-only primitives `.pql-stack`, `.pql-cluster`,
│   │   │   `.pql-card`, `.pql-badge` replacing scattered
│   │   │   `d-flex gap-2` + `card mb-4` repetition
│   │   ├── Migrate base.html + login.html + catalogs.html to
│   │   │   the new tokens as proof-of-concept (rest follow in
│   │   │   later sprints)
│   │   └── `docs/design-tokens.md` reference
│   │
│   ├── Sprint 30 — Shell + empty states + error pages    ✅ done (8d939fe)
│   │   ├── New app shell in `base.html` — header + collapsible
│   │   │   sidebar + main, mobile-aware grid (`minmax(0, 1fr)`
│   │   │   on narrow viewports, `auto 1fr` on wide)
│   │   ├── `components/breadcrumbs.html` + `components/empty.html`
│   │   │   replacing one-off `<div class="p-3 text-muted small
│   │   │   fst-italic">No X.</div>` snippets across every list
│   │   │   page
│   │   ├── `pages/404.html` + `pages/500.html` rendered on the
│   │   │   new shell; `error_handlers.py` dispatches on
│   │   │   `Accept: text/html` vs JSON so browser users never
│   │   │   hit the current `<h1>{status}</h1>` raw fallback
│   │   ├── `pages/403.html` refitted on the new shell
│   │   └── Toast system `frontend/js/toast.js` —
│   │       `window.pqlToast.{success,error,info}(msg)` as a
│   │       Bootstrap-toast wrapper mounted once in `base.html`
│   │
│   ├── Sprint 31 — Command palette (Cmd+K)               ✅ done (c9f0198)
│   │   ├── `GET /api/search?q=…&limit=50` aggregates catalogs,
│   │   │   schemas, tables, connections, credentials, external
│   │   │   locations, jobs, dashboards, and (admin-only)
│   │   │   workspace notebooks via `asyncio.gather`; reuses
│   │   │   `unitycatalog.get_tree()` + `list_*()` + the local
│   │   │   `Job`/`Dashboard` queries + `list_workspace_tree`.
│   │   │   Prefix-match scores 2.0, substring 1.0, ties broken
│   │   │   by `updated_at` desc. Per-source soyuz failures
│   │   │   degrade to "those hits missing" instead of 502'ing
│   │   │   the palette. No index — scale doesn't need one
│   │   ├── `components/command_palette.html` mounted once in
│   │   │   `base.html`; Alpine factory `commandPalette()` lives
│   │   │   in the same file (single-file convention, deviates
│   │   │   from the planned two-file split — nothing else
│   │   │   reuses the factory). Cmd+K / Ctrl+K opens, ↑↓
│   │   │   navigates, Enter opens, Esc closes; debounced 150 ms;
│   │   │   stale responses dropped by sequence number
│   │   ├── Recent searches in `localStorage['pql.recentSearches']`
│   │   │   (last 10, deduped by URL), shown when query is empty
│   │   ├── `?` opens keyboard-shortcuts help modal; suppressed
│   │   │   when focus is inside any input/textarea/select or
│   │   │   `[contenteditable]`
│   │   ├── Ghost-button "Search…" with platform-aware `⌘K` /
│   │   │   `Ctrl+K` keycap hint in the navbar; mobile (< 768 px)
│   │   │   collapses to a search-icon button
│   │   └── New playbook `docs/e2e-walkthroughs/command-palette.md`
│   │
│   ├── Sprint 32 — Home dashboard                         ✅ done (7a313fc)
│   │   ├── Rewrite `pages/catalogs.html` (the `/` route) into a
│   │   │   real dashboard (`pages/home.html`): welcome header,
│   │   │   Recent catalogs (last 5 via
│   │   │   `localStorage['pql.recentCatalogs']`), Latest job runs
│   │   │   (10 cross-job with status dot + relative time), Your
│   │   │   dashboards card (owner-scoped), Quick actions
│   │   │   (admin-only "Create foreign catalog" modal preserved
│   │   │   via extracted `components/create_foreign_catalog_modal.html`)
│   │   ├── Inline-SVG sparkline for 7-day job success-rate — 7
│   │   │   bars over 168×40, semantic tint classes
│   │   │   (`.pql-spark--ok/warn/bad/empty`) keyed on a single
│   │   │   `homeSparkline()` Alpine factory. Only terminal
│   │   │   statuses count (succeeded + failed); skipped/running
│   │   │   excluded from both numerator and denominator
│   │   ├── `GET /api/home/summary` — one round-trip for every
│   │   │   server-side card. Soyuz + DB concurrent via
│   │   │   `asyncio.gather` + `asyncio.to_thread`; a
│   │   │   `CatalogUnavailableError` downgrades to
│   │   │   `catalogs.unavailable=true` with a 200 response so the
│   │   │   home page still renders local cards. `_build_home_summary`
│   │   │   helper shared with the HTML handler so first-paint and
│   │   │   refresh see identical shapes. Visibility mirrors
│   │   │   `/api/jobs`: latest_runs + sparkline filter
│   │   │   `Job.run_as_user_id == user.id` for non-admins
│   │   ├── Catalog-visit instrumentation in `base.html` — any
│   │   │   page that threads `active_catalog` writes the name
│   │   │   into `localStorage['pql.recentCatalogs']`, deduped,
│   │   │   capped at 5, mirroring Sprint 31's
│   │   │   `pql.recentSearches` pattern
│   │   ├── 3-step onboarding checklist empty-state when no
│   │   │   catalogs/jobs/dashboards exist; suppressed when soyuz
│   │   │   is unavailable (the red banner is the primary signal
│   │   │   in that case, not "connect a data source")
│   │   └── New playbook `docs/e2e-walkthroughs/home.md` covering
│   │       the sparkline render, latest-runs table, Recent-catalogs
│   │       visit tracking, Your-dashboards card, admin modal,
│   │       fresh-user onboarding, JSON shape, and the soyuz-down
│   │       200-response degradation
│   │
│   ├── Sprint 33 — List-page polish                       ✅ done (c26b9e5)
│   │   ├── Shared `frontend/js/list_table.js` — debounced
│   │   │   (150 ms) client-side search, sortable headers (asc →
│   │   │   desc → none via `aria-sort` + CSS pseudo-arrow), and
│   │   │   optional filter chips on top of any Bootstrap table
│   │   │   whose rows carry `data-search` + `data-sort-<key>`
│   │   │   attributes. Progressive enhancement — the server
│   │   │   renders the full table, JS just hides/reorders rows
│   │   ├── Applied to `/jobs`, `/dashboards`, `/connections`,
│   │   │   `/credentials`, `/external-locations`. Chips per
│   │   │   page: jobs = Paused + Last-run-failed, dashboards =
│   │   │   Has-bound-job, connections = one per distinct
│   │   │   `connection_type`, credentials = one per distinct
│   │   │   `purpose`, external-locations = none.
│   │   │   `/notebooks/workspace` deferred to Sprint 34 — the
│   │   │   tree has its own `sessionStorage` expand/collapse
│   │   │   state and a flat-table helper doesn't fit
│   │   ├── `frontend/js/humanize_cron.js` — `pqlHumanizeCron()`
│   │   │   turns the six `@`-macros + common 5-field shapes
│   │   │   (`* * * * *`, `*/N * * * *`, `M H * * *`, weekly /
│   │   │   monthly / yearly) into friendly strings; falls back
│   │   │   to the raw expression otherwise. Applied on the jobs
│   │   │   list Cron cell + the detail Configuration card, with
│   │   │   `title=<raw>` preserved for tooltip
│   │   ├── `frontend/js/relative_time.js` — the Sprint-32
│   │   │   `window.pqlRelativeTime` helper lifted into its own
│   │   │   file so the jobs list can reuse it; `home.html`'s
│   │   │   inline copy swapped for a one-line pointer
│   │   ├── `GET /api/jobs` gains `last_run_status`,
│   │   │   `last_run_at`, `last_run_duration_s` (`null` when a
│   │   │   job has no runs yet). New `_latest_run_per_job(session,
│   │   │   job_ids)` helper fetches one row per job in a single
│   │   │   round-trip via `group_by(job_id)` + `max(started_at)`
│   │   │   — portable across SQLite + Postgres, rides the
│   │   │   existing `(job_id, started_at)` index on `JobRun`.
│   │   │   `/jobs` rows render the new "Last run" column as a
│   │   │   status dot + `pqlRelativeTime(iso)`; duration field
│   │   │   ships in the API for a later row-level display
│   │   └── Hover quick-actions on `/jobs` rows (admin-only) —
│   │       `.pql-row-actions` cell, `visibility: hidden` until
│   │       `tr:hover` / `tr:focus-within` (always on for touch
│   │       via `@media (hover: none)`). Buttons POST to existing
│   │       `/api/jobs/{id}/run|pause|unpause`; success toast
│   │       through `window.pqlToast` + reload after 400 ms.
│   │       `frontend/js/job_row_actions.js` is the Alpine
│   │       factory behind them
│   │
│   ├── Sprint 34 — Catalog / schema / table experience    ✅ done (f970fce)
│   │   ├── Catalog detail gains an inline Schemas card (name ·
│   │   │   updated · comment) sourced from the existing
│   │   │   `client.list_schemas` via the detail-page
│   │   │   `asyncio.gather`. Planned per-schema table count
│   │   │   dropped to avoid an O(N) fan-out to soyuz-catalog —
│   │   │   `schema.updated_at` alone keeps the card useful
│   │   │   without the extra round-trips
│   │   ├── Schema detail gains an inline Tables card (name ·
│   │   │   type · format · column-count · updated · comment)
│   │   │   sourced from the existing `list_tables` bypass path,
│   │   │   which already returns full `TableInfo` payloads so
│   │   │   the column count is free
│   │   ├── Table detail — new Preview card. `GET /api/catalogs/
│   │   │   {c}/schemas/{s}/tables/{t}/preview` runs
│   │   │   `PQL().table(...)` inside `asyncio.to_thread` under
│   │   │   the caller's `X-Principal`, caps at 10 rows
│   │   │   server-side (no client-tunable `?limit=`), emits
│   │   │   `Cache-Control: no-store`, and degrades to a
│   │   │   single-card error state on any engine/Delta failure
│   │   │   rather than 500-ing the page. Engine-agnostic via a
│   │   │   `_preview_head` helper that keeps DuckDB lazy
│   │   │   (`rel.limit(n).df()`) and coerces polars through
│   │   │   `to_pandas()`
│   │   ├── Columns table gains client-side search + sort via
│   │   │   Sprint-33 `listTable()` when `columns|length >= 20`;
│   │   │   sortable keys are position / name / type / nullable.
│   │   │   Below the threshold the table stays server-rendered
│   │   │   unchanged (progressive enhancement)
│   │   ├── Lineage card replaces its flat `sort(depth)`
│   │   │   indented list with per-depth subheading groups.
│   │   │   Depth badge per node stays — redundant-but-defensive
│   │   │   survives a future collapse/filter. Clickable 3-part
│   │   │   links were already there from an earlier sprint
│   │   └── Admin-only "Open in notebook" button on the PQL
│   │       snippet card. `POST /api/catalogs/…/open-in-notebook`
│   │       sanitises identifiers with `re.sub(r"[^A-Za-z0-9_-]",
│   │       "_", …)`, appends `secrets.token_hex(3)` to defeat
│   │       double-click collisions, writes an `nbformat.v4`
│   │       notebook to `{notebooks_dir}/scratch/…`, re-validates
│   │       with `resolve_upload_target`, and returns a
│   │       `lab_url` the Alpine handler navigates to via
│   │       `window.location.assign`. `scratch/` is added to the
│   │       Sprint-27 workspace-tree skip-list alongside `runs/`
│   │       so generated scratch notebooks never pollute the
│   │       user-authored workspace view
│   │
│   ├── Sprint 35 — Mobile + responsive                    ✅ done (59cf50c)
│   │   ├── Breakpoint tokens `--pql-breakpoint-sm/md/lg/xl`
│   │   │   = 640 / 768 / 1024 / 1280 px. Reference values only
│   │   │   — `@media` rules cannot consume `var()`, so every
│   │   │   query repeats the literal; the token block is the
│   │   │   canonical contract (documented in
│   │   │   `docs/design-tokens.md`)
│   │   ├── Sidebar drawer polish — already wrapped in
│   │   │   Bootstrap `offcanvas-md` from Sprint 30, so focus
│   │   │   trap + Esc-to-close come for free. Verified end-to-
│   │   │   end via Playwright MCP at 375 × 812
│   │   ├── `<640 px` navbar story — scope originally called for
│   │   │   a second hamburger at `<640 px`. Merged instead: at
│   │   │   `<640 px` the inline `<ul class="navbar-nav">` hides
│   │   │   (`d-none d-sm-flex` on a new `.pql-topbar-nav`
│   │   │   wrapper), and a "Navigation" footer section inside
│   │   │   the existing sidebar drawer surfaces all six nav
│   │   │   links (Federation / Notebook / Workspace / Jobs /
│   │   │   Dashboards / user dropdown). One hamburger, not two
│   │   ├── `components/nav_links.html` — new, extracted from
│   │   │   the inline base.html `<ul>` and reused in the drawer
│   │   │   footer with an override `nav_list_class`
│   │   ├── `listTable()` gains a `mobileSort: boolean` flag;
│   │   │   when true it renders a `.pql-list-sort-mobile`
│   │   │   `<select>` (`d-sm-none`) populated from every
│   │   │   sortable `<th data-sort-key>` with asc / desc
│   │   │   options. Picking an option calls a new
│   │   │   `_onMobileSort(raw)` that sets `sortKey` + `sortDir`
│   │   │   in one pick, unlike the tri-state header cycle.
│   │   │   All four `listTable()` callers opt in (jobs,
│   │   │   dashboards, external-locations, Sprint-34 columns
│   │   │   card)
│   │   ├── List tables collapse to 2-column label / value card
│   │   │   rows at `<640 px` via a CSS-only transform on
│   │   │   `.pql-list-table`. Every `<td>` carries a
│   │   │   `data-label="…"` that the `::before` pseudo-element
│   │   │   renders as the key; above the breakpoint the table
│   │   │   stays a normal Bootstrap table. Applied to jobs,
│   │   │   dashboards, external-locations, plus the Sprint-34
│   │   │   Schemas / Tables / Preview / Columns cards
│   │   ├── Touch targets ≥ 44 px under
│   │   │   `@media (hover: none)` for buttons, inputs, selects,
│   │   │   chips, nav-links, sortable headers. Scoped so a
│   │   │   mouse-driven laptop touchscreen with hover support
│   │   │   keeps its compact Sprint-33 spacing
│   │   ├── Jupyter iframe gains a `.pql-notebook-mobile-notice`
│   │   │   banner at `<768 px` ("JupyterLab is optimised for
│   │   │   desktop…") above a still-mounted iframe — heads-up,
│   │   │   not a blocker
│   │   └── New playbook `docs/e2e-walkthroughs/mobile.md`
│   │       exercising phone (375) / tablet (768) / desktop
│   │       (1280) via `browser_resize` + `browser_navigate`.
│   │       Sprint-35 found-bugs section filled in clean — no
│   │       regressions at 1280, all breakpoints flip correctly
│   │
│   └── Sprint 36 — Shared utilities + shortcuts + close   ✅ done (ec3facc)
│       ├── `frontend/js/api.js` exposes `window.pqlApi.fetch(url, init)`
│       │   returning `{ok, status, data, error}` and auto-emitting
│       │   a `pqlToast.error(...)` on non-ok responses (opt out
│       │   with `init.silent = true`). Soyuz `detail` / `message`
│       │   / `error` field extraction, network-failure handling
│       │   (`status: 0`). Also `pqlApi.reloadWithToast(msg, opts)`
│       │   for the toast-then-reload helper (400 ms default)
│       ├── Migrated five Alpine components off ad-hoc `fetch`
│       │   onto `pqlApi.fetch`: `editable`, `properties_editor`,
│       │   `tags_editor`, `permissions_editor` (incl. the
│       │   `silent: true` effective-permissions GET), and all
│       │   four `federation.js` create/delete forms. Inline
│       │   `this.error` hints kept; toast fires on top so
│       │   failures no longer hide in a tiny red span
│       ├── Every mutation-triggered reload now routes through
│       │   `pqlApi.reloadWithToast(...)` —
│       │   `job_row_actions`, `/jobs` create modal,
│       │   `/jobs/{id}` run / pause / resume, the
│       │   `/dashboards/{slug}` Refresh button, the
│       │   `sync_history_card` Sync-now button
│       ├── Keyboard-shortcut registry extends the Sprint-31
│       │   `commandPalette()` Alpine component: `shortcuts`
│       │   array with `{keys, combiner, label}` entries drives
│       │   the help-modal `<dl>`. New bindings `g h` / `g j` /
│       │   `g d` (1 s pending window) + `r` on list pages,
│       │   all behind the existing editable-target / modifier
│       │   guards
│       ├── `list_page: True` threaded through the five list-
│       │   route template contexts; `base.html` renders
│       │   `data-pql-refresh="1"` on `<body>` so `r` opts in
│       │   without touching each page template
│       ├── Global `:focus-visible` in `style.css` + a
│       │   `@media (prefers-reduced-motion: reduce)` block that
│       │   zeroes `--pql-duration-*` and forces
│       │   `animation-duration: 0ms` on `*, *::before, *::after`
│       │   so Bootstrap fades, Alpine x-transitions, and the
│       │   offcanvas slide all respect the preference
│       └── New playbook `docs/e2e-walkthroughs/ux-overhaul.md`
│           covering shortcut chords + toast flow + focus rings
│           + reduced-motion branch
│
│   Phase 9 close-out — the UX overhaul closed the gap between
│   "functionally complete" (Phase 8) and "feels like a modern
│   alternative". Eight sprints shipped the design-token
│   foundation (29), the shell + empty states + error pages
│   (30), a Cmd+K command palette (31), a real home dashboard
│   (32), list polish (33), the catalog/schema/table experience
│   (34), mobile + responsive breakpoints (35), and finally the
│   shared-fetch helper + keyboard-shortcut registry + a11y
│   polish (36). Replays surfaced a handful of small bugs
│   captured in their respective sprint playbooks' found-bugs
│   sections; no Phase-9 bugs deferred.
│
│   What Phase 9 bought: the survey that kicked off the phase
│   found raw-JSON 404s, a left-stuck login card, an empty
│   home, list pages without search/filter/sort, a table detail
│   without data, no global search, no toasts, no mobile
│   layout, and ad-hoc `fetch` error-handling copy-pasted
│   across five JS files. All nine gaps are now closed. The
│   stack never forked (FastAPI + Jinja2 + Bootstrap 5.3 + HTMX
│   + Alpine.js throughout) — every improvement was a token,
│   a component, or a helper. Future sprints picking up
│   Phase-10+ work (docker-compose packaging, DuckDB / Polars
│   engines) inherit a UI that tab-navigates cleanly, respects
│   reduced-motion, ships one toast contract, and surfaces
│   every keyboard shortcut in one help modal.
│
├── Phase 10 — Packaging & private distribution           ✅ done
│   │
│   │   Goal: unblock clean-machine installs. `uv sync`
│   │   currently fails on any host without
│   │   `../soyuz-catalog` checked out, because
│   │   `soyuz-catalog-client` is an editable path dep. Phase
│   │   10 swaps that for a private git-tag pin, gives both
│   │   repos a real release process, and lets docker-compose
│   │   pull images from GHCR instead of building locally.
│   │
│   │   Distribution contract: **private GitHub tags** consumed
│   │   via uv's `[tool.uv.sources]` git-subdirectory shape.
│   │   **No public PyPI** — explicitly deferred. Dual-mode dev
│   │   stays: the editable path to `../soyuz-catalog` is an
│   │   opt-in toggle so client regeneration is still visible
│   │   without a tag bump.
│   │
│   ├── Sprint 37 — soyuz-catalog release engineering     ✅ done (774b419 here, be9c5c6 in soyuz)
│   │   │
│   │   │   Forward-pulled from soyuz-catalog's own Sprint 19.
│   │   │   Lands in the sibling repo; tracked here because
│   │   │   PointlesSQL is what unblocks. The original Sprint
│   │   │   19 scope was narrowed — no public PyPI, no GHCR
│   │   │   image (Sprint 40 owns that instead).
│   │   │
│   │   ├── `soyuz-catalog/cliff.toml` — git-cliff template
│   │   │   keyed to the Conventional Commit scopes on main
│   │   │   (`feat(catalogs)`, `feat(tables)`, `feat(connections)`,
│   │   │   `fix(client)`, `docs(roadmap)`, …). Commit subjects
│   │   │   wrapped in backticks so release-notes output
│   │   │   tolerates `_parse_response`-style tokens under
│   │   │   markdownlint MD037
│   │   ├── `soyuz-catalog/scripts/bump-version.sh` — lockstep
│   │   │   version bump across root + client `pyproject.toml`,
│   │   │   re-locks `uv.lock`, renames `## [Unreleased]` →
│   │   │   `## [X.Y.Z] - <date>` in CHANGELOG.md (anchored
│   │   │   multiline regex, hand-written prose preserved
│   │   │   verbatim), commits `chore(release): vX.Y.Z`, and
│   │   │   creates an annotated tag. Does not push — the user
│   │   │   pushes manually so the action stays reversible.
│   │   │   Errors loudly on dirty tree, non-main branch,
│   │   │   invalid PEP 440, existing tag, or missing
│   │   │   `[Unreleased]` heading
│   │   ├── `soyuz-catalog/.github/workflows/release.yml` —
│   │   │   on-tag `v*`, runs `check_client_drift.sh` first
│   │   │   (reuses the existing gate from `test.yml`; no new
│   │   │   drift logic), `uv build` at root + inside
│   │   │   `soyuz-catalog-client/`, generates short release-
│   │   │   notes via `uvx git-cliff --latest --strip all`, and
│   │   │   `gh release create`s with all four artifacts
│   │   │   attached (server + client, wheel + sdist).
│   │   │   `--prerelease` toggled automatically for PEP 440
│   │   │   `rc*` / `a*` / `b*` / `dev*` shapes
│   │   ├── First tag cut: `v0.2.0rc1`. Both server and client
│   │   │   at `0.2.0rc1` (incremental bump from `0.1.0`; does
│   │   │   not claim 1.0 API stability). Tag was **local-only**
│   │   │   — the push was blocked by three pre-push hooks and
│   │   │   had to be re-cut as `v0.2.0rc2` during Sprint 38.
│   │   │   Soyuz Sprint 19.1 (OpenAPI dedup + CI unblock) was
│   │   │   the follow-on detour; see soyuz' CHANGELOG
│   │   └── Sprint 38 pins
│   │       `soyuz-catalog-client = { git = "…", tag = "v0.2.0rc2",
│   │       subdirectory = "soyuz-catalog-client" }` in
│   │       `[tool.uv.sources]`
│   │
│   ├── Sprint 38 — Swap path-dep to git-tag pin (dual-mode)  ✅ done (41868bc)
│   │   ├── `pyproject.toml [tool.uv.sources]` — replace the
│   │   │   editable path with a `{ git = "…", tag = "v0.2.0rc2",
│   │   │   subdirectory = "soyuz-catalog-client" }` pin.
│   │   │   `v0.2.0rc2` instead of `rc1` because Sprint 19.1 in
│   │   │   soyuz had to land first (OpenAPI schema-name dedup
│   │   │   + CI hook unblock) before the tag would push — the
│   │   │   pushable retag is `rc2`
│   │   ├── Dual-mode toggle: two helper scripts swap
│   │   │   `[tool.uv.sources]` in-place.
│   │   │   `scripts/use-editable-soyuz.sh` rewrites the git-tag
│   │   │   pin to `{ path = "../soyuz-catalog/soyuz-catalog-client",
│   │   │   editable = true }` and re-`uv sync`s;
│   │   │   `scripts/use-pinned-soyuz.sh` restores pyproject.toml
│   │   │   + uv.lock from HEAD. The editable swap leaves the tree
│   │   │   dirty on purpose so the escape-hatch state stays
│   │   │   visible. (A Sprint-38 attempt at a gitignored
│   │   │   `uv.toml` with a `[sources]` block was later found
│   │   │   invalid — `uv` only accepts `sources` inside a
│   │   │   `pyproject.toml`'s `[tool.uv.sources]`; the scripts are
│   │   │   the working replacement)
│   │   ├── `uv.lock` regenerated against the git-tag pin — first
│   │   │   lock that works on a clean clone with no sibling
│   │   │   `../soyuz-catalog` checkout
│   │   ├── `Dockerfile` — collapsed from 3 stages to 2. Stage 1
│   │   │   (`soyuz-client-builder`) and the Stage 2 sed-strip
│   │   │   on `[tool.uv.sources]` are gone. Client wheel fetches
│   │   │   over git/SSH via BuildKit `--mount=type=ssh`;
│   │   │   `docker compose build --ssh default` forwards the
│   │   │   host ssh-agent. Sprint 40 replaces the SSH path with
│   │   │   GHCR image pulls and `--secret`-based token auth
│   │   ├── `docker-compose.yml` — `additional_contexts.soyuz-catalog`
│   │   │   removed (only Stage 1 needed it); replaced with
│   │   │   `build.ssh: [default]` for BuildKit ssh-agent forwarding
│   │   ├── `CLAUDE.md` "Wiring soyuz-catalog" block rewritten
│   │   │   with both dev modes documented (default git-pin +
│   │   │   editable escape hatch via the `use-editable-soyuz.sh`
│   │   │   / `use-pinned-soyuz.sh` script pair)
│   │   └── Smoke test: fresh tmpdir, `git clone`, `uv sync`,
│   │       `uv run pointlessql` — succeeded without
│   │       `../soyuz-catalog`
│   │
│   ├── Sprint 39 — PointlesSQL release engineering         ✅ done (9f73dc3; first GitHub Release at v0.1.0rc2 / 74d6dfa after CI-auth follow-on)
│   │   │
│   │   │   Mirrors Sprint 37's soyuz shape. Adds the first CI
│   │   │   this repo has ever had plus a tag-cutting script that
│   │   │   preserves hand-written `[Unreleased]` prose in
│   │   │   CHANGELOG.md. Pre-work: model-side alembic-drift fix
│   │   │   (fix(alembic) commit) so the new alembic-check CI
│   │   │   step starts green.
│   │   │
│   │   ├── `cliff.toml` — git-cliff template keyed to the
│   │   │   Conventional Commit scopes already in use on main
│   │   │   (`feat(ui)`, `fix(ui)`, `build(packaging)`,
│   │   │   `docs(roadmap)`, …). Drives the release-notes body
│   │   │   in the on-tag release workflow
│   │   ├── `scripts/bump-version.sh` — single-`pyproject.toml`
│   │   │   variant of the soyuz bump-script. PEP 440 sanity-
│   │   │   check, clean-tree + on-main + tag-not-exists guards,
│   │   │   in-place `version = "…"` edit, `uv lock`,
│   │   │   `[Unreleased]` → `[X.Y.Z] - <date>` flip in
│   │   │   CHANGELOG.md with hand-written prose preserved
│   │   │   verbatim, `chore(release): vX.Y.Z` commit, annotated
│   │   │   tag. Does not push — the user pushes manually so the
│   │   │   whole action stays reversible
│   │   ├── `.github/workflows/test.yml` — first CI for this
│   │   │   repo. Jobs: ruff, pyright, pydoclint (Google),
│   │   │   `alembic check`. No pytest (standing sprint-gate
│   │   │   discipline). Private soyuz-catalog dep pulled by
│   │   │   `uv sync` at authentication-time via a single
│   │   │   `git config --global url.insteadOf` rewrite with the
│   │   │   `SOYUZ_READ_TOKEN` classic PAT as
│   │   │   `x-access-token:…` basic auth. Initial shape used a
│   │   │   sibling `git clone` + `uv.toml [sources]` override;
│   │   │   that was torn out as a follow-on fix when `uv`
│   │   │   rejected the `uv.toml` `[sources]` block and when
│   │   │   `actions/checkout@v4`'s fine-grained-PAT handling
│   │   │   failed (the PAT was swapped to a classic one). The 16
│   │   │   `fix(ci)` commits on main trace the investigation
│   │   ├── `.github/workflows/release.yml` — on-tag `v*`. Runs
│   │   │   the gate (ruff/pyright/pydoclint/alembic), builds
│   │   │   wheel + sdist via `uv build`, asserts the wheel
│   │   │   contains `pointlessql/_frontend/` and
│   │   │   `pointlessql/alembic/versions/` (force-includes from
│   │   │   `[tool.hatch.build.targets.wheel.force-include]`),
│   │   │   generates release-notes via
│   │   │   `uvx git-cliff --latest --strip all`, and
│   │   │   `gh release create`s. Prerelease flag auto-toggled
│   │   │   for PEP 440 `rc*` / `a*` / `b*` / `dev*` shapes
│   │   ├── Wheel force-includes verified locally:
│   │   │   `pointlessql-0.1.0-py3-none-any.whl` carries 52
│   │   │   frontend entries at `pointlessql/_frontend/*` and
│   │   │   10 alembic entries at `pointlessql/alembic/**`
│   │   └── First tag: `v0.1.0rc1` (PEP 440 canonical — not
│   │       `v0.1.0-rc1`; same typo-correction as soyuz Sprint 19.1)
│   │
│   └── Sprint 40 — Docker registry + clean-machine install + close  ✅ done (c242464)
│       ├── `.github/workflows/docker.yml` — on-tag, builds
│       │   PointlesSQL + soyuz-catalog images, pushes to GHCR
│       │   under the repo-owner namespace (private; consumers
│       │   `docker login ghcr.io` with a classic PAT scoped
│       │   `read:packages`). Soyuz tag is parsed from
│       │   `pyproject.toml`'s `[tool.uv.sources]` at workflow
│       │   time so the two repos stay in lockstep — no hard-coded
│       │   version. `verify-soyuz-tag-exists` step does a
│       │   `git ls-remote` with `SOYUZ_READ_TOKEN` to fail fast
│       │   on a never-pushed tag (the Sprint 37 `v0.2.0rc1`
│       │   failure mode, guarded against)
│       ├── `Dockerfile` — dual auth. `--mount=type=ssh` (Sprint 38
│       │   ergonomics) AND `--mount=type=secret,id=gh_pat` (CI +
│       │   clean-machine). RUN prefers the token if present,
│       │   falls back to SSH. Plus OCI labels
│       │   (`org.opencontainers.image.source/revision/version/…`)
│       │   with `ARG VCS_REF` / `ARG VERSION` populated by
│       │   `docker.yml`
│       ├── `Dockerfile.soyuz` — OCI labels only. No auth change
│       │   needed (this Dockerfile only `COPY --from=soyuz-catalog`s
│       │   from a build context; no private git fetches inside)
│       ├── `docker-compose.yml` — commented `image:
│       │   ghcr.io/flohofstetter/…:<tag>` line above each
│       │   service's `build:` block, with explainer; `pointlessql`
│       │   build grew `secrets: [gh_pat]` alongside the existing
│       │   `ssh: [default]`; top-level `secrets: gh_pat: {
│       │   environment: GH_PAT }` block so `GH_PAT=$(gh auth token)
│       │   docker compose build` works
│       ├── `docs/install.md` — first formal install guide. Three
│       │   flavours: Docker + GHCR (primary), pip install from
│       │   git tag, source checkout for contributors. Each ends
│       │   with an "expected state" assertion. Final section:
│       │   Troubleshooting for the usual landmines
│       │   (`DOCKER_BUILDKIT=0`, fine-grained vs classic PAT,
│       │   stale `/app/data` volume after a version bump)
│       ├── `docs/e2e-walkthroughs/packaging.md` — eleventh
│       │   playbook. Fresh-`$(mktemp -d)` walkthrough: assert
│       │   anonymous pull **fails** (proves private), `docker
│       │   login ghcr.io`, re-pull succeeds, download compose
│       │   file at the tag, `sed` flips `build:` → `image:`,
│       │   `docker compose pull && up -d`, healthcheck poll,
│       │   Playwright MCP `browser_navigate` home-page assertion,
│       │   OCI-label inspection, teardown. Index in
│       │   `docs/e2e-walkthroughs/README.md` grew a third section
│       │   (`Packaging`)
│       ├── `README.md` — "Quick start (Docker + GHCR images)"
│       │   section replaces the old `docker compose up --build`
│       │   flow as the primary quick-start path; the
│       │   `../soyuz-catalog/` sibling-required prerequisite is
│       │   removed. Source-build demoted under "Quick start (local
│       │   development)". Both sections cross-link to the new
│       │   `docs/install.md`
│       └── `CLAUDE.md` — "Docker builds" + new "GHCR images"
│           subsections documenting dual-auth + on-tag publish;
│           e2e playbook count bumped from ten to eleven
│
│   Phase 10 close-out — four sprints (37, 38, 39, 40) turned two
│   sibling repos into two independently-releasable artifacts with
│   on-tag pipelines that hand-off cleanly. Sprint 37 gave
│   soyuz-catalog its first tag-cutter + on-tag release workflow.
│   Sprint 38 swapped PointlesSQL's editable path dep for a
│   git-tag pin of the soyuz-catalog-client wheel, with the
│   in-place `pyproject.toml` swap scripts preserving the
│   escape-hatch ergonomics. Sprint 39 mirrored Sprint 37's
│   release-engineering on PointlesSQL — first CI for the repo,
│   first tag, first GitHub Release. Sprint 40 closed the loop
│   with on-tag GHCR publishes of both images and a three-flavour
│   install guide.
│
│   What Phase 10 bought: `git clone && uv sync && uv run
│   pointlessql` now works on an empty host; `docker login ghcr.io
│   && docker compose pull && docker compose up` works without
│   any source checkout at all; and every future release cuts a
│   GitHub Release plus two GHCR images automatically. The
│   `../soyuz-catalog/` sibling prerequisite that gated every
│   earlier sprint is gone. A handful of investigation-heavy
│   follow-on fixes landed mid-phase (the sixteen-plus `fix(ci)`
│   commits chasing the `uv.toml [sources]` rejection and
│   `actions/checkout@v4` fine-grained-PAT edge case, plus the
│   alembic-drift and preflight fixes) and all the work they
│   bought is rolled forward.
│
│   Deferred to Phase 11 / beyond: multi-arch (arm64) image
│   builds, public PyPI publish, Helm chart, flipping the GHCR
│   packages from private to public once the project is ready
│   for a broader audience. The `docker.yml` wiring is the
│   substrate that those future efforts bolt onto unchanged.
│
│   Also deferred: the `docs/e2e-walkthroughs/packaging.md`
│   dogfood replay. Attempted at the end of Sprint 40 and
│   abandoned mid-run — the private-GHCR auth dance (the
│   `read:packages` scope is not on the default `gh` CLI token)
│   is self-inflicted friction that disappears the moment the
│   packages flip to public. The playbook's clean-machine
│   assertion is only truly exercised when "clean machine" means
│   "anyone with docker, no PAT dance" — i.e. post-publication.
│   The replay is Phase 11's gate, not Phase 10's.
│
│   Scope retrospective: Phase 10 overreached. Sprint 38
│   (clean-machine `git clone && uv sync`) paid for itself in
│   everyday reduced friction. Sprints 37, 39, 40 built a full
│   release pipeline (wheels, GHCR images, install.md) for an
│   audience of one — the author. Three release candidates
│   (`v0.1.0rc1`–`rc3`) shipped with nobody downstream. The
│   plumbing is not wasted — it activates as-is in Phase 11 —
│   but the lesson is: release-engineering against a private
│   audience generates its own private-auth friction, and that
│   friction is what the eventual public flip dissolves. Next
│   time, build the publish pipeline in the same sprint that
│   flips visibility.
│
├── Phase 11 — Hardening                                 🔜 in progress
│   │
│   │   Goal: harden the runtime surfaces before layering more
│   │   features on. Phase 10 shipped a working release pipeline,
│   │   but the app itself is still single-user-laptop-grade —
│   │   no CSRF, no rate limiting, no JWT-key rotation story, no
│   │   in-app audit viewer. The public-visibility / external-
│   │   distribution work that was briefly mooted here has moved
│   │   to Phase 14 (queued last, on purpose). Sequence from here:
│   │   hardening (11) → features (12, 13) → public launch (14).
│   │
│   ├── Sprint 41 — Admin audit-log viewer                ✅ done (2b25b89)
│   │   ├── `GET /admin/audit` gated by `_require_admin`; reuses
│   │   │   the `/jobs` `listTable` Alpine component + `pql-list-*`
│   │   │   CSS so the page inherits search, sort, chips, and
│   │   │   mobile stacking without new frontend primitives
│   │   ├── Server-side filters: `since=24h|7d|30d|all` (default
│   │   │   `7d`), `action`, `user` substring, `target` substring;
│   │   │   client-side "Mine only" chip layered on top
│   │   ├── Alembic `009` adds `ix_audit_log_created` on
│   │   │   `(created_at)`; the two existing composite indexes cover
│   │   │   user- and target-scoped lookups but the new cross-user
│   │   │   "latest N" ordering query had no supporting index
│   │   ├── New "Admin" dropdown in `components/nav_links.html`,
│   │   │   admin-only, first item is "Audit log". Anchors the
│   │   │   `/admin/*` namespace that the remaining Phase 11 sprints
│   │   │   (and Phase 12 query-history, Phase 13 agent dashboards)
│   │   │   hang off without re-plumbing
│   │   ├── New playbook `docs/e2e-walkthroughs/admin-audit.md`
│   │   │   covering the admin happy path, filters, detail
│   │   │   expand/collapse, and the non-admin 403 lockout
│   │   └── `tests/test_admin_audit.py` — anon redirect, non-admin
│   │       403, newest-first ordering, `since=all` surfaces old
│   │       rows + tolerates non-JSON `detail`, action + target
│   │       filters narrow correctly
│   │
│   ├── Sprint 42 — CSRF protection for HTML form routes     ✅ done (811fb5c)
│   │   ├── New `csrf_middleware` enforces the OWASP double-
│   │   │   submit-cookie pattern on every non-safe request that
│   │   │   does not start with `/api/`, `/static/`, or equal
│   │   │   `/healthz`. Token comparison is timing-safe via
│   │   │   `secrets.compare_digest`
│   │   ├── Cookie `pql_csrf` is `HttpOnly`, `SameSite=Lax`,
│   │   │   `max_age` matches the JWT auth cookie. Middleware
│   │   │   issues a token on every request without one and
│   │   │   rejects any state-changing POST that cookie could not
│   │   │   plausibly have matched yet
│   │   ├── `{{ csrf_input() }}` Jinja macro wired into the three
│   │   │   non-boosted forms (`pages/login.html`,
│   │   │   `pages/register.html`, the logout form in
│   │   │   `components/nav_links.html`)
│   │   ├── HTMX hook in `base.html` injects `X-CSRF-Token` on
│   │   │   every non-safe request from the `<meta name="csrf-token">`
│   │   │   tag — zero per-route edits for the boosted routes
│   │   ├── Token rotates on local-login, OIDC-login, and logout
│   │   │   to prevent fixation; failed login keeps the existing
│   │   │   cookie so retry works without a reload
│   │   ├── New playbook `docs/e2e-walkthroughs/csrf.md` covering
│   │   │   cookie issuance, meta/input agreement, login rotation,
│   │   │   HTMX auto-header, tamper → 403, and the `/api/*`
│   │   │   exemption
│   │   └── `tests/test_csrf.py` — cookie issuance + rendered
│   │       meta/input match, form-field path, `X-CSRF-Token`
│   │       header path, missing/mismatched token → 403,
│   │       login and logout rotation, `/api/*` exemption, body
│   │       re-injection so handlers still see form fields
│   │
│   ├── Sprint 43 — Rate limiting on `/auth/*`                ✅ done (ad4d768)
│   │   ├── New `rate_limit_middleware` sits between
│   │   │   `csrf_middleware` (outer) and `auth_middleware` (inner)
│   │   │   in the Starlette stack so cross-site forged floods still
│   │   │   fail the cheap CSRF check, but CSRF-clean abuse is
│   │   │   caught before the bcrypt/JWT-decode path runs on every
│   │   │   attempt
│   │   ├── Fixed-window counter backed by a new
│   │   │   `rate_limit_events` table; no new runtime dep, no Redis.
│   │   │   Default caps: `POST /auth/login` 10/10min per IP +
│   │   │   5/10min per submitted email, `POST /auth/register`
│   │   │   5/1h per IP, `/auth/sso` + `/auth/callback` share a
│   │   │   20/10min per-IP bucket
│   │   ├── Opportunistic cleanup: every check `DELETE`s rows older
│   │   │   than the window for this bucket before counting, so the
│   │   │   table stays bounded without a background sweeper
│   │   ├── 429 response carries `Retry-After: <seconds>` and a
│   │   │   minimal HTML body matching Sprint 42's CSRF 403 shape —
│   │   │   no templating pipeline, no new frontend primitives
│   │   ├── `rate_limit_trust_x_forwarded_for` setting defaults to
│   │   │   `false`; flip it on only behind a known reverse proxy,
│   │   │   otherwise any client could forge the header and escape
│   │   │   the per-IP bucket. The per-email axis still catches
│   │   │   distributed attacks that probe one account from many IPs
│   │   ├── Alembic `010` creates `rate_limit_events` plus the
│   │   │   composite `(bucket, created_at)` index that serves both
│   │   │   the count query and the cleanup delete
│   │   ├── Every reject emits an `audit_log` row with
│   │   │   `action="rate_limit.blocked"` and the bucket string in
│   │   │   `target`, so the Sprint-41 `/admin/audit` viewer
│   │   │   surfaces the feature without a second dashboard
│   │   ├── New playbook `docs/e2e-walkthroughs/rate-limit.md`
│   │   │   covering login + register + OIDC floods, the `/healthz`
│   │   │   and `/api/*` exemptions, and the admin-audit surface
│   │   └── `tests/test_rate_limit.py` — login IP + per-email caps,
│   │       register cap independence from login, OIDC shared
│   │       bucket across `/sso` + `/callback`, `/healthz` and
│   │       `/api/*` exemptions, `rate_limit_enabled=False` bypass,
│   │       body re-injection, audit-row assertion, and direct
│   │       service-layer unit tests
│   │
│   │
│   ├── Sprint 44 — RFC 9457 error envelope + HTMX toast bridge  ✅ done (f6f327c)
│   │   ├── Port shoreguard-fresh's RFC 9457 ``application/problem+json``
│   │   │   envelope to replace PointlesSQL's nested
│   │   │   ``{"error":{"code","message","request_id"}}`` shape.
│   │   │   Single ``_problem_body()`` helper in
│   │   │   [`error_handlers.py`](pointlessql/api/error_handlers.py)
│   │   │   is the one place the wire format is defined; JSON, toast,
│   │   │   and HTML renderers all source it through ``_dispatch()``
│   │   ├── New ``_wants_htmx_toast`` branch in the dispatch: a
│   │   │   non-boosted ``HX-Request: true`` caller gets an
│   │   │   ``HX-Trigger`` header carrying a ``pqlToast`` event (level,
│   │   │   code, message, request_id) + an empty body. Boosted
│   │   │   navigations keep the existing HTML page render so htmx
│   │   │   can swap ``#main-content`` normally
│   │   ├── Client-side bridge: ``base.html`` listens for the
│   │   │   ``pqlToast`` DOM event (auto-dispatched from ``HX-Trigger``)
│   │   │   and forwards level + message + request_id into the
│   │   │   existing ``window.pqlToast.error`` Bootstrap-toast API —
│   │   │   zero new CSS or JS file, reuses Sprint-30 toast plumbing
│   │   ├── Three new domain exceptions: ``SchedulerError`` (500,
│   │   │   scheduler plumbing failures pre-notebook-run),
│   │   │   ``NotebookRenderError`` (500, nbconvert failures that are
│   │   │   no longer misclassified as ``EngineError``),
│   │   │   ``PQLWriteError`` (subclasses ``EngineError`` so existing
│   │   │   catches keep working, but its own code lets the UI
│   │   │   distinguish write failures from generic engine failures).
│   │   │   ``notebook_render.py`` now raises ``NotebookRenderError``
│   │   │   instead of ``EngineError``
│   │   ├── ``AuthorizationError`` extras (privilege, securable type,
│   │   │   full name) are now RFC 9457 extension members in the JSON
│   │   │   body — no longer template-only context
│   │   ├── All nine ``except Exception`` sites in ``pointlessql/``
│   │   │   surveyed: scheduler (4×) and
│   │   │   ``services/{pg_sync,notebook_workspace}.py`` are legitimate
│   │   │   graceful-degradation paths and keep their ``BLE001`` noqa
│   │   │   plus a sharpened one-line reason comment; only
│   │   │   ``services/notebook_render.py`` changes exception type
│   │   ├── New playbook `docs/e2e-walkthroughs/error-handling.md`
│   │   │   covers problem+json media type on `/api/*`, HTMX-toast
│   │   │   trigger without page swap, boosted-navigation HTML
│   │   │   fallback, and 403 authorization envelope extension members
│   │   └── ``tests/test_problem_json.py`` — media type, extension
│   │       members, HTMX toast branch, boosted fallthrough, envelope
│   │       shape; existing ``test_error_handlers.py`` +
│   │       ``test_api_errors.py`` + ``test_enforcement.py`` +
│   │       ``test_api_notebook_workspace.py`` migrated from the old
│   │       ``body["error"][...]`` shape to the new top-level
│   │       ``body["detail"] / body["code"]`` shape
│   │
│   │   Remaining Phase 11 scope (not yet split into sprints):
│   │
│   ├── Sprint 45 — Nested ``BaseSettings`` refactor (6–8 sub-models,
│   │   per-sub-model ``env_prefix``; most env vars stay identical,
│   │   a small breaking subset is documented in CHANGELOG)  ⏳ planned
│   ├── Rate limiting on `/api/sql/*` — scheduled as a Phase-12
│   │   sprint once the SQL editor lands (the route doesn't exist
│   │   yet)
│   └── Graceful-rotation story for `secret_key` (JWT signing) so
│       mid-flight tokens survive a rotation — target Sprint 46
│
├── Phase 12 — SQL editor + query history                 ⏳ planned
│   │
│   │   Goal: close the second first-class-workspace gap after
│   │   notebooks (Phase 8). Dedicated `/sql` page (CodeMirror
│   │   editor + results table), plus `/queries` history that
│   │   answers "which user ran which query on which table when".
│   │   Auditability is free — Phase 3 already enforces SELECT at
│   │   the UC layer; Phase 12 just adds the telemetry plus the UI.
│   │
│   │   Settled design decisions (before any sprint starts):
│   │
│   │   - Query history lives in PointlesSQL's own Alembic DB,
│   │     not in soyuz-catalog — it is operational telemetry per
│   │     tenant, not lakehouse metadata
│   │   - Referenced tables extracted via `sqlglot` at execute-
│   │     time into a `query_history_tables` relation so
│   │     "who queried table X" is a fast reverse lookup
│   │   - SQL execution hard-wired to DuckDB (Pandas can't,
│   │     Polars only rudimentary); Phase 5's `POINTLESSQL_ENGINE`
│   │     setting stays for `PQL.table()` reads
│   │   - Delta-table export of query history as a `system`
│   │     catalog is deliberately deferred — offered as optional
│   │     Phase 12.5 only if retention requirements appear
│   │
│   │   Sprint outline:
│   │
│   ├── SQL editor MVP — CodeMirror + `/sql` + `PQL.sql()` +
│   │   sqlglot-based table resolution + SELECT enforcement per
│   │   referenced table. No history, no save, no export yet
│   ├── Query history — Alembic migration adds `query_history` +
│   │   `query_history_tables`; `/queries` page with filter
│   │   chips + re-run button; non-admin sees only own rows
│   ├── Saved queries — Alembic migration adds `saved_queries`;
│   │   share model parallel to Sprint-28 dashboards; sidebar
│   │   drawer on the editor
│   ├── Export + limits + cancel — CSV / Parquet download via
│   │   re-run-from-history; row limit + query timeout; cancel
│   │   button via DuckDB `.interrupt()`
│   └── EXPLAIN + autocomplete + close — EXPLAIN toggle,
│       table-name autocomplete from catalog tree, `g s`
│       keyboard shortcut, mobile stacking,
│       `docs/e2e-walkthroughs/sql-editor.md` playbook, phase close
│
├── Phase 13 — Agent workloads                            ⏳ sketch
│   │
│   │   Goal: bring "AI employees on the lakehouse" into
│   │   production — but as an integration with first-party
│   │   tooling, not as a new agent stack inside PointlesSQL.
│   │   The ecosystem already exists around this project:
│   │   shoreguard-fresh (policy / control plane),
│   │   NVIDIA OpenShell (sandbox runtime), and Paperclip
│   │   (org / budget / approval layer above agent frameworks).
│   │   Phase 13 wires those pieces together with PointlesSQL
│   │   staying focused on being the data surface. Three-layer
│   │   governance falls out naturally: UC permissions (what
│   │   data the agent can touch), OpenShell policy (what
│   │   filesystem / network / processes), Paperclip approvals
│   │   (which actions require a human).
│   │
│   │   Scope sketch (many open design questions — only worth
│   │   firming up once Phase 12 is landing):
│   │
│   ├── New companion repo `paperclip-adapter-pointlessql`
│   │   exposing PointlesSQL's REST API + PQL snippets as tools
│   │   Paperclip agents can call; sits next to the existing
│   │   `paperclip-plugin-shoreguard`
│   ├── New job kind `agent_run` in the Sprint-19 DAG engine so
│   │   scheduled agent workloads inherit scheduling, run
│   │   history, and dashboards without reinvention
│   ├── `X-Principal` forwarded into the Paperclip-managed
│   │   sandbox as the agent's UC identity, so Phase-3 SELECT /
│   │   MODIFY enforcement applies to every agent query without
│   │   new plumbing
│   ├── Read-only `/agents` discovery page in PointlesSQL;
│   │   authoring UI stays in Paperclip — PointlesSQL doesn't
│   │   compete with it
│   ├── Open decisions to settle: OIDC federation vs API-key
│   │   for PointlesSQL ↔ shoreguard authentication; ownership
│   │   of the `pql`-preinstalled sandbox image; streaming agent
│   │   logs into PointlesSQL's UI; Paperclip budget metrics
│   │   propagating into the job-run dashboards
│   └── Optional sidequest `openclaw-plugin-pointlessql` —
│       chat interface to catalog / SQL / jobs / dashboards via
│       OpenClaw messaging integrations. Not a sprint inside
│       the phase, just ecosystem work worth doing in the same
│       window
│
│   Exploratory follow-ons (not yet committed phases):
│
│   - **Ontology layer / Foundry-lite**: semantic "object" layer
│     above UC tables (User, Order, Campaign as first-class
│     entities with properties, relationships, derived
│     attributes). Would move the stack toward "governed-
│     operations platform for small teams". 3-6 months of work;
│     only worth picking up if Phase 13 proves the agent-
│     workload thesis carries
│   - **OSINT playbook**: not a phase on its own — Phase 6
│     foreign-catalog primitives + Phase 8 agent-authored
│     dashboards + Phase 13 agents already describe an
│     OSINT-capable substrate. Worth writing up as a pattern
│     playbook once the underlying phases stabilise
│
├── Phase 14 — Public launch + external distribution      ⏳ queued (last)
│   │
│   │   Deliberately queued for the end. Phase 10's retrospective
│   │   spelled it out: building release-engineering against a
│   │   private audience of one generates self-inflicted auth
│   │   friction, and release candidates shipped without
│   │   downstream consumers are wasted motion. Hardening
│   │   (Phase 11) and features (Phase 12, 13) come first. When
│   │   this phase runs, it is the moment the stack goes from
│   │   "my project" to "something strangers can try". Until
│   │   then this entry exists as an anchor so the future work
│   │   isn't forgotten — not as a scheduled commitment.
│   │
│   │   Scope (not yet split into sprints):
│   │
│   ├── GHCR packages flipped private → public for both
│   │   `pointlessql` and `soyuz-catalog` images; the Phase-10-
│   │   deferred `docs/e2e-walkthroughs/packaging.md` dogfood
│   │   replay finally runs end-to-end without the PAT dance
│   ├── Multi-arch (amd64 + arm64) image builds via docker
│   │   buildx — the single-sprint work that Phase 10 couldn't
│   │   justify for an audience of one
│   ├── Public PyPI publish of `soyuz-catalog-client` (first)
│   │   and the `pointlessql` wheel (second); replaces Phase 10's
│   │   private git-tag pin for the general audience while
│   │   keeping the tag-pin option available for consumers who
│   │   prefer reproducible git-based installs
│   ├── Optional: Helm chart for K8s deployments, generalising
│   │   "runs on a €15/month vServer" to "runs on a cluster"
│   └── README / docs pass: swap the "functional Databricks
│       clone" alpha framing for whatever the honest public
│       positioning is at the time. License decision (Apache 2.0
│       is the default-obvious choice — UC-compatible, no
│       ethical-use clauses worth the drama; revisit only if
│       something has changed)
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
