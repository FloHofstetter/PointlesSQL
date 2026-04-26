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
├── Phase 11 — Hardening                                 ✅ done
│   │
│   │   Goal: harden the runtime surfaces before layering more
│   │   features on. Phase 10 shipped a working release pipeline,
│   │   but the app itself is still single-user-laptop-grade —
│   │   no CSRF, no rate limiting, no JWT-key rotation story, no
│   │   in-app audit viewer. The public-visibility / external-
│   │   distribution work that was briefly mooted here has moved
│   │   to the unscheduled Some-day Launch block at the bottom
│   │   of this tree. Sequence from here:
│   │   hardening (11) → features (12, 13) →
│   │   audit-completeness (14) → Provenance Log (15) →
│   │   Branching + Rollback (16) → Some-day public launch.
│   │   Phases 14 / 15 / 16 are the "fully autonomous data
│   │   analysis" critical path captured in
│   │   `project_full_autonomous_audit_critical_path.md`.
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
│   ├── Sprint 45 — Nested ``BaseSettings`` refactor  ✅ done (c3cae8c)
│   │   ├── Flat ``Settings`` split into nine sub-models
│   │   │   (Server, Soyuz, Database, Auth, OIDC, Logging, RateLimit,
│   │   │   Jupyter, Scheduler, Delta) each with their own
│   │   │   ``env_prefix``; ``Settings`` composes them via
│   │   │   ``Field(default_factory=…)`` so env reads happen at each
│   │   │   instantiation (matches papermill's CWD-fresh pattern)
│   │   ├── Most ``POINTLESSQL_*`` env vars unchanged; the 9-entry
│   │   │   BREAKING subset (``HOST``→``SERVER_HOST``,
│   │   │   ``DATABASE_URL``→``DB_URL``, ``SECRET_KEY``→``AUTH_SECRET_KEY``,
│   │   │   ``NOTEBOOKS_DIR``→``JUPYTER_NOTEBOOKS_DIR``, etc.) is
│   │   │   documented in CHANGELOG with a full mapping; docker-compose
│   │   │   files updated in-sprint
│   │   ├── Rate-limit and CSRF middleware dynamic-attribute lookups
│   │   │   rewritten to read the ``settings.rate_limit`` /
│   │   │   ``settings.auth`` sub-models instead of flat attributes
│   │   └── Tests that built ``Settings(secret_key="…")`` migrated to
│   │       ``Settings(auth={"secret_key": "…"})``; two fixtures that
│   │       used ``MagicMock(secret_key="…")`` now build real
│   │       ``Settings`` instances so nested access works
│   ├── Rate limiting on `/api/sql/*` — scheduled as a Phase-12
│   │   sprint once the SQL editor lands (the route doesn't exist
│   │   yet)
│   │
│   ├── Sprint 46 — Graceful JWT signing-key rotation  ✅ done (fc2cc99)
│   │
│   └── Sprint 47 — Test-suite regressions  ✅ done (b6381a6)
│       ├── Pin every in-memory SQLite test engine to
│       │   ``StaticPool`` + ``check_same_thread=False`` so the
│       │   schema survives when ``asyncio.to_thread``-backed code
│       │   paths (the home-summary ``_db_block``) hit the engine
│       │   from a worker thread. Covers ``test_catalogs_index``,
│       │   ``test_non_admin_denied_without_grant``,
│       │   ``test_connections_html_denied_for_non_admin``,
│       │   ``test_authenticated_access``, and the two
│       │   ``test_foreign_catalog`` home-modal tests (5 tests)
│       ├── ``test_enforcement`` 403-copy assertions updated from
│       │   ``"Access Denied"`` (pre-Sprint-30 title) to the
│       │   current ``"Access denied"`` that the 403 template
│       │   actually renders (2 tests)
│       └── ``test_list_tables`` updated from
│           ``ListTablesResponse(identifiers=…)`` to ``tables=…``
│           after the soyuz-catalog-client v0.2 rename — the
│           production ``pql.list_tables`` already reads
│           ``response.tables`` (1 test)
│       ├── New optional ``POINTLESSQL_AUTH_SECRET_KEY_PREVIOUS``
│       │   env var on ``AuthSettings``; ``verify_jwt`` tries the
│       │   primary key first and falls back to the previous key
│       │   only if the primary rejects the token. Expired or
│       │   tampered tokens fail under both. New tokens always
│       │   sign with the primary
│       ├── ``get_current_user`` accepts a ``previous_key`` kwarg
│       │   and forwards it into ``verify_jwt`` — auth middleware
│       │   in ``api/main.py`` reads ``settings.auth.secret_key_previous``
│       │   so routes can honour the grace window without per-route
│       │   edits
│       ├── Rotation procedure documented in CHANGELOG with the
│       │   four-step flow (set previous → change primary → wait
│       │   ``jwt_expiry_hours`` → drop previous). ``.env.example``
│       │   updated to surface the new knob
│       └── Six new unit tests in ``tests/test_auth.py``: happy-path
│           previous-key verification, fresh-token behaviour during
│           rotation, third-key rejection, missing-fallback rejection,
│           expiry-preservation, ``get_current_user`` threading
│
├── Phase 12 — SQL editor + query history                 ✅ done (Sprint 53)
│   │
│   │   Goal: close the second first-class-workspace gap after
│   │   notebooks (Phase 8). Dedicated `/sql` page (CodeMirror
│   │   editor + results table), plus `/queries` history that
│   │   answers "which user ran which query on which table when".
│   │   Auditability is free — Phase 3 already enforces SELECT at
│   │   the UC layer; Phase 12 just adds the telemetry plus the UI.
│   │
│   ├── Sprint 48 — Audit-log hardening (shoreguard-port)       ✅ done (14b1249)
│   │   ├── Alembic ``011`` widens ``audit_log.detail`` to ``Text``
│   │   │   and adds ``client_ip`` + ``actor_role`` columns
│   │   ├── ``services/audit.py`` ports the shoreguard-fresh
│   │   │   append-only ORM guards (``before_update`` +
│   │   │   ``before_delete`` event listeners that raise
│   │   │   ``AuditIntegrityError``) plus a
│   │   │   ``_allow_audit_mutation()`` ContextVar bypass that only
│   │   │   the retention sweep opens
│   │   ├── ``log_action`` accepts a JSON-encodable dict for
│   │   │   ``detail``; string callers still work unchanged
│   │   ├── ``AuditSettings`` sub-model (``retention_days``,
│   │   │   ``cleanup_interval_seconds``); a lifespan-owned
│   │   │   background task sweeps expired rows on that cadence
│   │   ├── ``_audit()`` dispatches the INSERT via
│   │   │   ``asyncio.to_thread`` — HTTP requests no longer block
│   │   │   on the audit DB round-trip. All 22 call sites rewritten
│   │   │   to ``await _audit(...)``. Rate-limit-middleware's
│   │   │   ``rate_limit.blocked`` hook uses the same async path
│   │   ├── ``GET /admin/audit/export?fmt=json|csv`` mirrors the
│   │   │   viewer's filter surface (since/action/user/target),
│   │   │   streams a filename-stamped attachment, caps at 10 000
│   │   │   rows per call
│   │   ├── Admin audit-log template gains a Role badge column
│   │   │   (admin/user/system styling) and a compact IP column;
│   │   │   two "Export" buttons build the same query string
│   │   │   operators see in the URL
│   │   ├── ``.env.example`` + ``CHANGELOG.md`` document the new
│   │   │   ``POINTLESSQL_AUDIT_*`` knobs + the 9 shoreguard
│   │   │   patterns ported vs. 3 deliberately skipped (CLI sha256
│   │   │   manifest, syslog/webhook sinks, action-string
│   │   │   renaming) as scope-creep for PointlesSQL's scale
│   │   └── Tests: 5 new unit tests in ``tests/test_audit.py``
│   │       (append-only guards, cleanup round-trip, retention=0
│   │       no-op, broken-factory swallow, dict-detail JSON
│   │       round-trip); 4 new integration tests in
│   │       ``tests/test_admin_audit.py`` (non-admin 403,
│   │       JSON/CSV/filter shape). ``test_admin_audit`` +
│   │       ``test_rate_limit`` also migrated off the ``MagicMock``
│   │       settings fixture that Sprint 47 missed, and both pin
│   │       their engines to ``StaticPool`` so the new async write
│   │       path works under ``asyncio.to_thread``
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
│   │   - **Audit-action naming convention** (Sprint 48 follow-up):
│   │     new events emitted by Phase 12/13 use the
│   │     ``resource.verb`` form (``query.executed``,
│   │     ``query.saved``, ``query.shared``, ``agent.plan.approved``)
│   │     to match shoreguard-fresh's convention and stay
│   │     consistent with the already-landed ``rate_limit.blocked``.
│   │     Existing pre-Sprint-48 strings (``update_catalog``,
│   │     ``create_connection``, …) stay as-is — retroactive
│   │     rename is pure churn.
│   │
│   │   Sprint outline:
│   │
│   ├── Sprint 49 — SQL editor MVP                          ✅ done (b0f705d)
│   │   CodeMirror + `/sql` + `PQL.sql()` + sqlglot-based
│   │   table resolution + SELECT enforcement per referenced
│   │   table. No history, no save, no export yet.
│   ├── Sprint 50 — Query history                           ✅ done (639d7ae)
│   │   Alembic 012 adds `query_history` + `query_history_tables`;
│   │   `/queries` page with filter chips + re-run button;
│   │   non-admin sees only own rows.
│   ├── Sprint 51 — Saved queries                           ✅ done (0f93345)
│   │   Alembic 013 adds `saved_queries`; share model parallel
│   │   to Sprint-28 dashboards; sidebar drawer on the editor.
│   ├── Sprint 52 — Export + limits + cancel                ✅ done (b4bfee5)
│   │   CSV / Parquet download via re-run-from-history; row
│   │   limit + query timeout; cancel via DuckDB `.interrupt()`.
│   └── Sprint 53 — EXPLAIN + autocomplete + close          ✅ done (b718839)
│       EXPLAIN toggle, table-name autocomplete from catalog
│       tree, mobile stacking,
│       `docs/e2e-walkthroughs/sql-editor.md` playbook, phase close.
│
├── Phase 12.5 — Data operations parity add-ons            ✅ done
│   │
│   │   Narrow follow-up between Phase 12 (SQL editor) and Phase 13
│   │   (agents).  Four back-to-back sprints closed the "data-
│   │   operations parity" gaps every Databricks user expects once
│   │   they've got a SQL editor: charts, alerts, column statistics,
│   │   and UC Volumes.  Guiding principle: **no vendor lock-in** —
│   │   every external-facing wire format is an open standard
│   │   (CloudEvents 1.0, Atom 1.0, JSON Feed 1.1, HMAC-SHA256).  No
│   │   SMTP / Slack / Discord / Teams / PagerDuty SDKs — the user
│   │   bridges those via n8n / Zapier / Make and we stay portable.
│   │   Phase-13's EXPLAIN-agent cost-gate will subscribe to the same
│   │   CloudEvents ``data`` shape Sprint 55 emits without a payload-
│   │   shape break.
│   │
│   ├── Sprint 54 — Charts in the SQL editor                 ✅ done (88898d2)
│   │   Bar / Line / Scatter / Pie toolbar below the results table;
│   │   ``c`` toggles table ↔ chart when focus is outside CodeMirror;
│   │   PNG download via ``canvas.toBlob``; chart config persists per
│   │   ``query_history.id`` via Alembic 014 so re-run from history
│   │   replays the same visualisation.  Chart.js 4.x UMD (not ESM)
│   │   vendored via jsDelivr in ``base.html``.
│   ├── Sprint 55 — Query alerts (CloudEvents + feeds)        ✅ done (832087c)
│   │   Alembic 015 adds ``alerts`` / ``alert_destinations`` /
│   │   ``alert_events`` + ``users.feed_token``.  New ``alert_check``
│   │   scheduler job-kind ticks a saved-query condition
│   │   (``row_count op threshold``); when it fires, emits a
│   │   CloudEvents 1.0 JSON envelope to every enabled destination.
│   │   Two destination kinds: webhook (POST with optional
│   │   HMAC-SHA256 signing, 5s/10s timeouts, 2 retries) and pull
│   │   feed (Atom 1.0 + JSON Feed 1.1, per-user opaque token,
│   │   30-day event retention).
│   ├── Sprint 56 — Column statistics / data profiling        ✅ done (1ff3c90)
│   │   "Profile columns" button on every UC table detail page;
│   │   DuckDB pass computes count / null_count / distinct_count /
│   │   min / max / mean / top_5; cached by
│   │   ``(full_name, delta_log_version)`` in ``table_stats``
│   │   (Alembic 016).  Sparklines rendered via the Sprint-54
│   │   Chart.js CDN — zero extra network weight.
│   └── Sprint 57 — UC Volumes (upload + convert-to-Delta)    ✅ done (7662c29)
│       Cross-repo sprint.  soyuz-catalog (f8ef973) adds file
│       upload/download/browse/delete routes + a ``file://`` storage
│       backend behind a ``VolumeFileBackend`` protocol so S3 / ABFSS
│       / GCS can plug in later without route changes.  PointlesSQL
│       adds ``/volumes`` list + ``/volumes/{full_name}`` detail page
│       with an upload form, a browse / delete table, and a
│       "Convert to Delta" action for CSV / Parquet / JSON that
│       reads via DuckDB, writes a managed Delta table inside the
│       volume root, and registers the new table in UC via the
│       existing generated client.  The "I have a CSV, make it go"
│       moment.
│
├── Phase 12.6 — Native Python notebook editor            ✅ done
│   │
│   │   Replace the Sprint-3 JupyterLab iframe with a first-party
│   │   Monaco-based notebook editor. Quality bar = VSCode Python
│   │   Interactive Window: single Monaco instance over a virtual
│   │   document with cell decorations, Pyright LSP, dual-source
│   │   autocomplete (static + kernel), rich outputs persisted in
│   │   SQLite, Variable Explorer, "Insert from catalog".
│   │
│   │   Architecture invariants (locked; see Sprint-58 ADR 0001 at
│   │   ``docs/adr/0001-notebook-editor.md``):
│   │   - On-disk source of truth: ``.py`` in jupytext Percent
│   │     format. ``.ipynb`` lives only where Phase 8 Papermill
│   │     needs it; Sprint 63 adds a convert-step there.
│   │   - Cell parsing via ``jupytext`` (all marker variants
│   │     parsed, ``# %%`` written by default, jupytext per-file
│   │     header honoured).
│   │   - Single Monaco instance + view zones (rejects Monaco-
│   │     per-cell — LSP / undo / cross-cell-nav argument).
│   │   - Kernel via ``jupyter_client`` ZMQ, FastAPI WS proxy
│   │     (no ``jupyter_server``).
│   │   - LSP via ``pyright-langserver --stdio``, FastAPI WS bridge.
│   │   - Outputs persisted in SQLite keyed by
│   │     ``(file_path, cell_id, kernel_session_id)`` — non-
│   │     negotiable: without persistence every reopen of a
│   │     notebook with a slow ``pql.read_table()`` is a 90 s wait.
│   │
│   │   Hard rules:
│   │   - JupyterLab iframe stays live at ``/notebook`` until
│   │     Sprint 63 acceptance — no regress window for current
│   │     users.
│   │   - Phase-8 Papermill pipeline stays functional throughout.
│   │
│   ├── Sprint 58 — Percent parser + Monaco skeleton          ✅ done (513fd68)
│   │   ├── New dep: ``jupytext>=1.16`` for cell parsing /
│   │   │   writing
│   │   ├── ``pointlessql/services/notebook_doc.py`` — load /
│   │   │   save round-trip for ``.py`` percent notebooks;
│   │   │   writes ``# %%`` by default, honours per-file
│   │   │   jupytext header if present; UUID assignment on
│   │   │   first load of a foreign notebook (``dirty`` flag)
│   │   ├── Monaco 0.52.0 vendored under
│   │   │   ``frontend/js/vendor/monaco/`` via
│   │   │   ``scripts/vendor-monaco.sh`` (gitignored ~14 MB
│   │   │   AMD bundle; dev / Docker bootstraps run the script
│   │   │   once per version bump)
│   │   ├── ``GET /notebook/editor?path=<relative>`` Alpine page
│   │   │   with single Monaco, Python syntax, cell background
│   │   │   decorations + top toolbar (Run button stubbed,
│   │   │   tooltip'd "execution lands in Sprint 59"); missing-
│   │   │   file flow scaffolds an empty cell and first save
│   │   │   materialises the file
│   │   ├── ``POST /api/notebook/doc`` save endpoint with the
│   │   │   same traversal guard the executor uses
│   │   ├── Navbar: ``Notebook`` link becomes a dropdown with
│   │   │   ``JupyterLab (classic)`` + ``Editor (preview)``
│   │   │   entries; existing ``/notebook`` iframe route
│   │   │   untouched
│   │   ├── **ADR 0001** committed at
│   │   │   ``docs/adr/0001-notebook-editor.md`` covering:
│   │   │   single- vs multi-Monaco, output-DB schema,
│   │   │   cell-ID strategy
│   │   └── Out of scope: execution, LSP, outputs, workspace-
│   │       tree integration (lives under Sprint 63)
│   │
│   ├── Sprint 59 — Kernel + WS proxy + basic execution       ✅ done (f672564)
│   │   ├── New deps: ``jupyter_client>=8.6`` + ``ipykernel>=6.29``
│   │   │   (both already transitively via papermill; now pinned
│   │   │   explicitly).
│   │   ├── ``pointlessql/services/kernel_session.py`` — one
│   │   │   ipykernel subprocess per ``(user_id, notebook_path)``
│   │   │   (ADR-0001 kernel-identity decision), fan-out pump
│   │   │   from a single ZMQ reader to N browser-tab subscribers
│   │   │   so multiple tabs of one notebook don't starve each
│   │   │   other on iopub. ``POINTLESSQL_PRINCIPAL`` env
│   │   │   forwarding reuses the Sprint-24 pattern but via
│   │   │   ``AsyncKernelManager(env=…)`` instead of the
│   │   │   ``os.environ`` lock (kernels are long-lived; no
│   │   │   concurrent setenv race to dodge).
│   │   ├── ``WS /ws/notebook/kernel?path=<rel>`` FastAPI
│   │   │   endpoint.  WebSocket upgrades bypass the HTTP auth
│   │   │   middleware, so the handler pulls the ``pql_session``
│   │   │   cookie off the request and decodes the JWT manually
│   │   │   via ``auth_service.get_current_user``.  Frame shape:
│   │   │   client → ``{type: "execute"/"interrupt"/"restart"}``;
│   │   │   server → ``{type: "hello"/"ack"/"kernel_msg"/…}``.
│   │   ├── Lifespan integration: ``KernelRegistry`` lives on
│   │   │   ``app.state.kernel_registry``; ``shutdown_all`` runs
│   │   │   alongside the existing scheduler / uc-client cleanup
│   │   │   so a clean app stop also tears down every in-flight
│   │   │   kernel subprocess.
│   │   ├── Frontend: Shift+Enter + Ctrl+Enter run the cell at
│   │   │   the cursor.  Current-cell detection walks upward from
│   │   │   the cursor line for the nearest ``pql_cell_id``
│   │   │   marker.  Output zones are Monaco view zones anchored
│   │   │   below each cell's last line — ephemeral (Sprint-60
│   │   │   persists them) but already following the shape ADR
│   │   │   0001 pinned for the Alembic 017 schema.
│   │   ├── Toolbar: Run / Interrupt / Restart buttons plus a
│   │   │   live ``kernelStatus`` indicator ("Connecting kernel…"
│   │   │   / "Kernel ready" / "Restarting…" / "Kernel
│   │   │   disconnected").
│   │   ├── Kernel round-trip validated: in-process smoke proved
│   │   │   execute / stream / execute_result / interrupt flows
│   │   │   end-to-end; full HTTP-WS E2E deferred to Sprint 64's
│   │   │   Playwright playbook (TestClient blocks on the
│   │   │   JupyterLab subprocess in the shared lifespan).
│   │   └── Out of scope: rich outputs (html / png / svg /
│   │       pandas / matplotlib), output persistence, LSP
│   │
│   ├── Sprint 60 — Output persistence + rich outputs         ✅ done (5a17c0a, 9d03ca0)
│   │   ├── Alembic 017 lands the two tables pinned in ADR 0001:
│   │   │   ``notebook_outputs`` (id + quadruple uniq on
│   │   │   ``(file_path, cell_id, kernel_session_id,
│   │   │   output_index)`` + index on ``(file_path, cell_id)``)
│   │   │   and ``notebook_cell_runs`` (composite PK on the
│   │   │   ``(file_path, cell_id, kernel_session_id)`` triple,
│   │   │   tracks status / execution_count / started_at /
│   │   │   finished_at).
│   │   ├── ``pointlessql/services/notebook_outputs.py`` —
│   │   │   ``append_output`` / ``load_outputs_for_path`` /
│   │   │   ``clear_cell`` / ``clear_session`` / ``upsert_cell_run``.
│   │   │   Only the four content-carrying msg types persist
│   │   │   (``stream`` / ``execute_result`` / ``display_data`` /
│   │   │   ``error``) — ``status`` + ``execute_input`` never
│   │   │   land in the table.
│   │   ├── WS handler wires persistence without the kernel
│   │   │   service knowing about the DB: per-connection
│   │   │   ``output_counters`` drive ``output_index``,
│   │   │   ``execute`` triggers ``clear_cell`` + upsert
│   │   │   ``status=running`` before the ZMQ send, shell-
│   │   │   channel ``execute_reply`` closes the run row with
│   │   │   status / execution_count / finished_at, and a
│   │   │   client-initiated ``clear_cell`` frame purges both
│   │   │   the view zone and the DB row set.
│   │   ├── Editor route payload replay: the ``GET
│   │   │   /notebook/editor`` initial document now carries every
│   │   │   persisted output row so the Alpine mount paints them
│   │   │   into view zones *before* the WS ``hello`` frame
│   │   │   arrives — no more 90-second waits on reopen of a
│   │   │   notebook whose cells ran a slow ``pql.read_table()``.
│   │   ├── Frontend rich-mime renderer picks richest supported
│   │   │   type per bundle: ``text/html`` (pandas-styled tables
│   │   │   themed against the catalog dark mode), ``image/svg+xml``,
│   │   │   ``image/png`` / ``image/jpeg`` (matplotlib inline),
│   │   │   ``application/json`` (pretty-printed), ``text/plain``
│   │   │   fallback.  Errors convert IPython's ANSI traceback to
│   │   │   colour-preserving HTML spans via a dependency-free
│   │   │   SGR walker — no ``xterm.js`` bundle needed.
│   │   ├── Toolbar gains ``Clear cell`` (purges outputs + DB
│   │   │   rows for the cell at the cursor); ``Restart`` now
│   │   │   also wipes every persisted row for the outgoing
│   │   │   kernel session before the subprocess restarts.
│   │   └── ipywidgets explicitly deferred to Phase 12.7 per the
│   │       Sprint-58 decision — MVP ships static mime bundles
│   │       only.
│   │
│   ├── Sprint 61 — Pyright LSP + autocomplete                ✅ done (027ac66)
│   │   ├── ``pyright>=1.1`` moves from dev-only to a runtime
│   │   │   dep so the pypi package's ``pyright-langserver``
│   │   │   binary lands on ``.venv/bin`` for both local dev
│   │   │   and Docker runtimes.  No ``nodeenv`` pin — the
│   │   │   pypi wheel already bundles the needed Node binary.
│   │   ├── ``pointlessql/services/pyright_bridge.py`` — per-
│   │   │   tab subprocess wrapper with asyncio stdio framing
│   │   │   (``Content-Length: N\\r\\n\\r\\n<JSON body>``).  One
│   │   │   pyright subprocess per WS connection; subprocess
│   │   │   lifetime == tab lifetime, no cross-tab routing to
│   │   │   reason about, no registry on ``app.state``.
│   │   ├── ``WS /ws/notebook/lsp?path=<rel>`` FastAPI endpoint.
│   │   │   Mirrors the Sprint-59 kernel WS shape: manual
│   │   │   cookie auth, same traversal guard, transparent
│   │   │   JSON-RPC proxy (server strips/adds LSP framing,
│   │   │   client sends raw LSP objects).  A 4404 close code
│   │   │   fires when ``pyright-langserver`` is missing from
│   │   │   PATH — the toolbar pill just says "Pyright
│   │   │   unavailable" instead of hammering reconnects.
│   │   ├── Frontend: a 40-line ``PyrightClient`` handles
│   │   │   JSON-RPC correlation + notification subscribers.
│   │   │   Monaco provider registrations (completion, hover,
│   │   │   signatureHelp, definition) live once per tab; the
│   │   │   active model lookup goes through a ``WeakMap`` so
│   │   │   multiple editor instances share the registration
│   │   │   without cross-fire.  Diagnostics land via
│   │   │   ``monaco.editor.setModelMarkers``.
│   │   ├── Document lifecycle: ``initialize`` → ``initialized``
│   │   │   → ``textDocument/didOpen`` on mount; full-document
│   │   │   ``didChange`` on every ``onDidChangeContent`` (cheap
│   │   │   enough for notebook-size files, avoids incremental-
│   │   │   sync bookkeeping).  Document URI is
│   │   │   ``file:///notebook/<rel>`` — pyright runs single-
│   │   │   file checking, which is what we want for a
│   │   │   notebook-centric editor anyway.
│   │   ├── Toolbar gains an ``lspStatus`` pill ("Loading
│   │   │   Pyright…" / "Pyright ready" / "Pyright error" /
│   │   │   "Pyright unavailable") next to ``kernelStatus``.
│   │   ├── Scope-killer invoked: kernel ``complete_request``
│   │   │   dual-source merging is explicitly **deferred** to a
│   │   │   Sprint 61 follow-up (or Sprint 62).  LSP-only is
│   │   │   enough to cleanly ship completion / hover /
│   │   │   signatureHelp / definition / diagnostics end-to-end;
│   │   │   the runtime-source second column is a 30-line
│   │   │   provider that can land without backend changes.
│   │   └── Subprocess + LSP smoke test proved initialize +
│   │       didOpen + completion + diagnostics round-trip end-
│   │       to-end against ``json.`` — real completion items
│   │       (``dumps``, ``loads``, …) came back, and the trailing
│   │       ``.`` was flagged by pyright's diagnostics channel.
│   │
│   ├── Sprint 62 — Variable Explorer + catalog insert         ✅ done (95b4a2b)
│   │   ├── Variable Explorer sidebar driven by an
│   │   │   ``__pql_namespace__`` internal introspect — a small
│   │   │   Python snippet the editor injects under the reserved
│   │   │   ``__pql_`` cell-id prefix.  The server's persistence
│   │   │   layer filters every ``__pql_``-prefixed cell_id from
│   │   │   both ``notebook_outputs`` and ``notebook_cell_runs``,
│   │   │   so silent introspects never pollute the DB.  The
│   │   │   sidebar refreshes after every user cell goes idle
│   │   │   (only when the panel is open — idle tabs pay zero
│   │   │   introspect cost).  Each entry renders name / type /
│   │   │   shape + a DataFrame.head() HTML preview for pandas
│   │   │   objects, or a truncated ``repr`` otherwise.
│   │   ├── Insert-from-Catalog modal (Ctrl+Shift+I or toolbar
│   │   │   button) — fetches ``/api/tree``, flattens the
│   │   │   cat→schema→table hierarchy into a searchable list,
│   │   │   inserts ``pql.read_table("cat.schema.tbl")`` at the
│   │   │   cursor on pick.  Modal lives in the page template,
│   │   │   Alpine-driven, Bootstrap-styled.
│   │   ├── Command palette actions (F1 / Ctrl+Shift+P opens
│   │   │   Monaco's palette): Run All, Run Above, Insert Cell
│   │   │   Above / Below, Insert Markdown Cell Below, Clear
│   │   │   Outputs, Restart Kernel, Insert from Catalog,
│   │   │   Toggle Variable Explorer.  Single-letter M/Y/DD
│   │   │   shortcuts deliberately skipped — Phase 12.6 keeps
│   │   │   the editor's always-editing model, command-mode
│   │   │   state machine is Jupyter-classic baggage.
│   │   ├── Plotly / altair / bokeh now render inline:
│   │   │   ``text/html`` output is appended via ``innerHTML``
│   │   │   (which browsers sandbox against script execution),
│   │   │   then the subtree's ``<script>`` tags are cloned
│   │   │   into freshly-parsed nodes so they actually run —
│   │   │   same trick Jupyter's own nbrenderer uses.
│   │   └── **Scope-gate honoured**: ipywidgets stays out of
│   │       Phase 12.6.  Anything that needs ``comm_msg`` round-
│   │       trips lands in Phase 12.7.
│   │
│   ├── Sprint 63 — Papermill bridge + retire JupyterLab       ✅ done (accbeca)
│   │   ├── Phase-8 Papermill: ``_papermill_executor`` in
│   │   │   ``services/scheduler.py`` gains a jupytext-convert
│   │   │   step — ``.py`` inputs are written to a sibling
│   │   │   ``runs/{run_id}.input.ipynb`` via
│   │   │   ``_jupytext_py_to_ipynb`` before papermill sees
│   │   │   them, and the temp ``.ipynb`` is unlinked in a
│   │   │   ``finally`` block.  ``resolve_notebook_path`` now
│   │   │   accepts both suffixes.
│   │   ├── Sprint-26 viewer simplification: the
│   │   │   ``Rendered / JupyterLab`` view-mode toggle is
│   │   │   gone.  ``nbconvert``'s lab template is the sole
│   │   │   renderer; the ``Open in JupyterLab`` anchor became
│   │   │   a ``Download ipynb`` button that hits the existing
│   │   │   download endpoint.  The original plan had the
│   │   │   viewer re-pointing at the Sprint-60 renderer; that
│   │   │   meant converting ``.ipynb`` cells + outputs into the
│   │   │   native-editor shape at render time, which doubled
│   │   │   the sprint's complexity for no user-visible win
│   │   │   over nbconvert's static HTML.  Deliberately scoped
│   │   │   down (smaller-than-sketched OK per the Phase-12.6
│   │   │   memory rule).
│   │   ├── Sprint-27 workspace tree: ``services/
│   │   │   notebook_workspace.py`` now walks both ``.py`` and
│   │   │   ``.ipynb`` and tags each entry with a ``format``
│   │   │   marker.  The Alpine template adds a themed
│   │   │   ``Open`` button for ``.py`` that routes into the
│   │   │   native editor; ``.ipynb`` entries keep the
│   │   │   Schedule action only (upload + execute, no edit
│   │   │   surface).  The upload helper stays ``.ipynb``-only
│   │   │   for papermill compatibility — authoring happens in
│   │   │   the editor.
│   │   ├── Sprint-34 open-in-notebook: the
│   │   │   ``/api/catalogs/.../open-in-notebook`` route now
│   │   │   scaffolds a ``.py`` jupytext notebook (one markdown
│   │   │   header + one code cell, both with UUIDs via
│   │   │   ``notebook_doc.save_document``) and returns
│   │   │   ``{editor_url: …}``.  The legacy ``lab_url`` key
│   │   │   ships on the response as a one-release alias so
│   │   │   in-flight clients don't 500; Sprint 64 drops it.
│   │   ├── Retirement:
│   │   │   - ``pointlessql/services/jupyter.py`` deleted.
│   │   │   - ``"jupyterlab>=4.0"`` dropped from
│   │   │     ``pyproject.toml`` (``uv sync`` cleared ~30
│   │   │     transitive packages).
│   │   │   - ``/notebook`` becomes a 302 to
│   │   │     ``/notebook/editor?path=scratch.py``.
│   │   │   - ``pages/notebook.html`` deleted.
│   │   │   - ``GET /api/jupyter/status`` deleted.
│   │   │   - Navbar dropdown collapsed to a single direct link.
│   │   │   - CSP ``frame-ancestors`` entry lived only in
│   │   │     ``services/jupyter.py`` — gone with the file.
│   │   └── CHANGELOG breaking-change section + README
│   │       migration section.  Grace window is one release:
│   │       the ``/notebook`` redirect + the ``lab_url`` alias
│   │       on ``open-in-notebook`` stay for Sprint 64's close-
│   │       out.
│   │
│   └── Sprint 64 — E2E playbook + phase close                ✅ done (2ab5df1)
│       ├── ``docs/e2e-walkthroughs/notebook-editor.md`` —
│       │   six-part deterministic playbook covering:  first
│       │   open (UUID mint + autosave flush) → execute cell
│       │   (rich-mime output) → reload (outputs persist,
│       │   Sprint-60 replay) → clear / restart (outputs
│       │   wiped) → Pyright LSP (completion / hover /
│       │   diagnostics) → Insert-from-catalog modal (Ctrl+
│       │   Shift+I) → Variable Explorer + scheduled
│       │   refresh → post-retirement surfaces (no ``lab/``
│       │   iframes anywhere, ``/api/jupyter/status`` is
│       │   404, Sprint-26 card is single-view, Sprint-34
│       │   returns ``editor_url``).
│       ├── Grace aliases from Sprint 63 removed:
│       │   ``GET /notebook`` no longer 302-redirects (the
│       │   route is unregistered, giving a 404 — the single
│       │   ``Notebook`` navbar link points directly at the
│       │   editor so no internal caller relies on the
│       │   redirect).  ``open-in-notebook`` response dropped
│       │   the ``lab_url`` alias; the one call-site in
│       │   ``pages/table.html`` now reads ``editor_url``
│       │   directly.
│       ├── Sprint-23 ``notebook.md`` playbook retired —
│       │   obsoleted by the iframe retirement.  The
│       │   ``docs/e2e-walkthroughs/README.md`` index points
│       │   at ``notebook-editor.md`` as slot #7.
│       └── **Phase 12.6 marked ✅** in this roadmap.
│
├── Phase 12.7 — Notebook editor UX overhaul              ✅ done
│   │
│   │   Lift the native editor from Sprint-58–64 mechanics-only to a
│   │   Marimo / VSCode-Jupyter / Hex-grade UI as a series of small
│   │   sprints (1–3 days each), not a big-bang rewrite.  Sprint 65
│   │   first removes the two structural blockers (1571-LoC
│   │   IIFE, BUG-64-02 reactivity landmine) so every later sprint
│   │   touches small modules instead of bloating the single file
│   │   further.
│   │
│   │   Architecture invariants (carried forward from ADR 0001):
│   │   - One Monaco instance per notebook file (per-tab Monaco for
│   │     Sprint 68 multi-tab is fine — each tab is its own page).
│   │   - jupytext Percent on disk, UUIDs in markers.
│   │   - Single ipykernel per ``(user, notebook_path)``.
│   │   - Stack stays Alpine + HTMX + Bootstrap.
│   │   - Monaco / WebWorker / WebSocket-Refs MUST live in closure
│   │     scope, never as ``this.X`` — Sprint 65 enforces with the
│   │     ``createClosureRefs`` helper + a CI grep gate.
│   │
│   │   Trim points: 67, 69-KaTeX, 70, 71, 72 can be dropped without
│   │   breaking the dependency chain.  Hard chain: 65 → all later;
│   │   66 → 71; 67 → 68.  Max-trim = 65 → 66 → 68 → 73 → 74.
│   │
│   ├── Sprint 65 — Editor JS module split + reactivity-boundary gate ✅ done
│   │   ├── Architectural opener; no visible UX change.
│   │   ├── ``frontend/js/notebook_editor.js`` (1571-LoC IIFE) split
│   │   │   into nine ESM modules under
│   │   │   ``frontend/js/notebook/``: ``cell_parser.js`` (markers +
│   │   │   namespace introspect), ``ansi.js`` (SGR → HTML),
│   │   │   ``markdown.js`` (regex preview renderer; Sprint 69 swaps
│   │   │   for markdown-it), ``monaco_loader.js`` (vendored AMD +
│   │   │   defer-until-load wrapper), ``pyright_client.js``
│   │   │   (JSON-RPC client + Monaco provider registration via
│   │   │   WeakMap), ``output_renderer.js`` (mime bundle dispatch +
│   │   │   inline-script rehydration), ``closure_state.js``
│   │   │   (``createClosureRefs`` helper), ``main.js``
│   │   │   (orchestrator), ``bootstrap.js`` (ESM entry that exposes
│   │   │   ``window.notebookEditor``).
│   │   ├── ``frontend/templates/pages/notebook_editor.html`` —
│   │   │   ``<script type="module" src=".../bootstrap.js">``;
│   │   │   the legacy ``notebook_editor.js`` is deleted (no grace
│   │   │   alias — sole consumer was edited in the same commit).
│   │   ├── ``createClosureRefs(['editor', 'model'])`` formalises
│   │   │   the BUG-64-02 lesson (Sprint 64 commit ``0af7984``):
│   │   │   Monaco model + editor refs live in a closure-scoped
│   │   │   sealed bag so the deep-reactive Vue Proxy from Alpine
│   │   │   never reaches Monaco's circular internals.  Other
│   │   │   private state (timers, WS handles, output-zone DOM
│   │   │   maps, accumulator buffers) also moved to closure-scoped
│   │   │   ``let`` vars; the returned reactive object only carries
│   │   │   primitive UI state + bound methods.
│   │   ├── ``scripts/check-frontend-no-reactive-monaco.sh`` greps
│   │   │   for forbidden ``this\._(editor|model|monaco|worker|
│   │   │   wsRaw|lspWsRaw|saveTimer)\s*=`` patterns inside
│   │   │   ``frontend/js/notebook/`` and exits non-zero on a hit.
│   │   │   Wired into ``.github/workflows/test.yml`` as a step
│   │   │   after the ``alembic check``.
│   │   └── Out of scope (lands later in Phase 12.7): cell-type
│   │       registry, file-tree sidebar, multi-tab, markdown-it +
│   │       KaTeX, outline, SQL cell, ipywidgets, run history,
│   │       theme/keymap.  Each gets its own sprint against the
│   │       new module structure.
│   │
│   ├── Sprint 66 — Cell-type registry + per-cell affordances     ✅ done
│   │   Replaced hardcoded ``code | markdown`` with a registry
│   │   ([frontend/js/notebook/cell_types.js](frontend/js/notebook/cell_types.js));
│   │   added per-cell run button, execution-count pill,
│   │   elapsed-time pill, status pill (idle / running / ok /
│   │   error / cancelled), ``+ Code`` / ``+ Markdown`` inserter
│   │   below every cell.  Wire data: existing
│   │   ``execute_input.execution_count`` +
│   │   ``execute_reply.status`` — no backend changes, no Alembic
│   │   migration (columns in ``notebook_cell_runs`` stay unwritten
│   │   until Sprint 73).  New module
│   │   [frontend/js/notebook/cell_affordances.js](frontend/js/notebook/cell_affordances.js)
│   │   owns toolbar + inserter view zones; all DOM/timer state
│   │   closure-scoped (BUG-64-02 invariant preserved).  Registry
│   │   is the seam Sprint 71's SQL cell plugs into — one
│   │   descriptor registration, no parser / runner / decoration
│   │   edits.  Widened ``CELL_MARKER_RE`` to ``(\s+\[\w+\])?`` so
│   │   a future ``[sql]`` tag loaded by a pre-Sprint-71 client
│   │   degrades to ``code`` instead of dropping the cell.
│   │   Reactivity-boundary grep gate widened to also block
│   │   ``this._cellAffordances``, ``this._statusWidgets``,
│   │   ``this._cellWidgets``, ``this._reactiveRoot``.  Playbook
│   │   Part G replayed in Firefox (MCP) as the land gate.
│   │
│   ├── Sprint 67 — File-tree sidebar inside the editor           ✅ done (d41a4eb)
│   │   Mounts the Sprint-27 workspace tree as a 260px left sidebar
│   │   in ``/notebook/editor`` with open / new / rename / delete
│   │   actions.  Three new admin-only endpoints —
│   │   ``POST /api/notebooks/create`` (writes zero-byte ``.py``;
│   │   editor's open handler materialises cell markers on first
│   │   save), ``PATCH /api/notebooks/rename`` (atomic ``os.replace``
│   │   + ``rename_path`` UPDATE on the replay cache so prior
│   │   outputs survive), ``DELETE /api/notebooks?path=…``
│   │   (cascades into ``notebook_outputs`` + ``notebook_cell_runs``
│   │   via the ``clear_path`` stub Sprint 63 had pre-wired).  New
│   │   ESM module [frontend/js/notebook/file_tree.js](frontend/js/notebook/file_tree.js)
│   │   owns the sidebar's reactive slice; its AbortController for
│   │   inflight tree fetches stays closure-scoped, with the
│   │   reactivity-boundary grep gate widened to block
│   │   ``this._treeFetchCtrl`` / ``this._treeAbort``.  Three
│   │   Bootstrap modals (new / rename / delete) reuse the Catalog-
│   │   Insert ``x-show`` + Escape-close pattern.  Trash disabled on
│   │   the currently-open file; renaming the open file triggers a
│   │   hard reload at the new URL so kernel + autosave paths
│   │   resync cleanly.  ``/notebooks/workspace`` stays as the full-
│   │   screen view — the sidebar is a slim mirror (no upload, no
│   │   schedule).  Playbook Part H added; replayed in Firefox (MCP)
│   │   as the land gate per ``feedback_run_playbook_as_gate``.
│   │   **No Alembic migration.**
│   │
│   ├── Sprint 68 — Multi-notebook tab bar                        ✅ done (400670c)
│   │   Tab bar above the editor; each tab is one Monaco instance
│   │   over one file, sharing Sprint-65's modules.  Open-tabs list
│   │   persists in ``localStorage['pql.nbedit.tabs.v1']``; the
│   │   Sprint-67 file-tree click dispatches ``pql:open-tab`` and
│   │   the shell activates / adds the matching tab without a page
│   │   reload.  Kernel registry already keys by ``(user_id, path)``
│   │   so two tabs of the same file share one kernel.  Sprint-65's
│   │   ``createClosureRefs`` factory scales to N instances per
│   │   page verbatim; the grep gate now also blocks
│   │   ``this._tabRefs`` / ``this._tabFactories`` so the shell
│   │   can't aggregate per-tab closure bags onto its reactive
│   │   proxy and reproduce BUG-64-02 at N× scale.  Architecture:
│   │   N Monaco instances rendered into tab panes, lazy-mounted
│   │   via ``x-if="tab.mounted || tab.id === activeTabId"`` — the
│   │   per-tab factory fires ``pql:tab-state-changed {mounted:true}``
│   │   synchronously at ``mount()``'s entry so the shell's
│   │   tab.mounted flag persists across the bootstrap stub → real
│   │   scope swap (fix for the replay's first-tab-blanks-on-second-
│   │   open bug).  Close-tab UX on dirty buffer: Bootstrap-modal
│   │   confirm with Cancel / Discard & close / Save & close,
│   │   reusing the Sprint-67 ``:class="{'d-block': flag}"`` pattern
│   │   (BUG-67-01).  Soft-cap at 10 tabs — no kernel LRU yet so
│   │   uncapped multi-tab would blow up per-user kernel counts;
│   │   the eleventh open produces a toast.  **Roadmap deviation
│   │   note:** the original entry claimed "No backend changes" —
│   │   verified false.  One tiny endpoint landed
│   │   (``GET /api/notebook/doc?path=…``) so non-initial tabs can
│   │   lazy-fetch their content without a full HTML reload.  The
│   │   endpoint reuses the existing Jinja-route helper via a
│   │   factored ``_build_notebook_doc_bundle`` function — ≤30 LoC,
│   │   no new service code.  New module
│   │   [frontend/js/notebook/editor_shell.js](frontend/js/notebook/editor_shell.js)
│   │   owns the tab bar + sidebar mount + close-confirm + event
│   │   bus (``pql:open-tab`` / ``pql:file-renamed`` /
│   │   ``pql:file-deleted`` / ``pql:tab-state-changed`` /
│   │   ``pql:save-tab``).  Sidebar slice's API shifted from a
│   │   static ``currentPath`` to ``getActivePath`` +
│   │   ``isPathOpenInAnyTab`` callbacks so the trash-disable check
│   │   covers any tab (not just the active one) holding the
│   │   path.  Playbook Part I added; replayed in Firefox (MCP) as
│   │   the land gate per ``feedback_run_playbook_as_gate``.
│   │   **No Alembic migration.**
│   │
│   ├── Sprint 69 — Markdown polish + dual-mode + KaTeX            ✅ done (d3c7df7)
│   │   Replaces the Sprint-65 regex preview with ``markdown-it``
│   │   14.1.0 (CommonMark — tables, nested lists, autolinking),
│   │   layered KaTeX 0.16.11 via ``markdown-it-texmath`` 1.0.0
│   │   for ``$…$`` / ``$$…$$`` math; per-cell pencil-pin toggle
│   │   keeps a markdown cell in source view independent of
│   │   cursor position.  All three libs vendored under
│   │   [frontend/js/vendor/](frontend/js/vendor/) via
│   │   [scripts/vendor-markdown-libs.sh](scripts/vendor-markdown-libs.sh)
│   │   (mirrors ``vendor-monaco.sh``).  Pin state lives on
│   │   ``markdownZones[cellId].editModePinned`` (closure-scoped,
│   │   session-only — jupytext marker grammar + ADR 0001
│   │   untouched).  Cell-type registry gains optional
│   │   ``affordances: ['pin']`` field as the seam future
│   │   cell-type-specific buttons plug into.  Reactivity-boundary
│   │   grep gate widened to block ``this._mdSingleton`` /
│   │   ``_mdPinState`` / ``_pinHandlers`` (markdown-it's deep
│   │   rule registries are exactly the BUG-64-02 footgun shape).
│   │   Vendor bundles MUST load before ``monaco/vs/loader.js`` —
│   │   their UMD wrappers detect Monaco's AMD ``window.define``
│   │   and register as anonymous AMD modules, colliding with
│   │   Monaco's "one anonymous define per script" contract
│   │   (BUG-69-01, replay-caught + fixed in same commit).
│   │   Playbook Part J added; replayed in Firefox (MCP) as the
│   │   land gate per ``feedback_run_playbook_as_gate``.
│   │   **No Alembic migration.** KaTeX layer is independently
│   │   droppable: removing the ``.use(window.texmath, …)`` line
│   │   in ``markdown.js`` plus the matching template ``<script>``
│   │   / ``<link>`` tags reverts to plain markdown-it without
│   │   breaking anything else.
│   │
│   ├── Sprint 70 — Outline / TOC panel + cell jump                ✅ done (b6fe0e2)
│   │   Right-side Outline panel peers with the Variable Explorer
│   │   (same 320px slot, mutually exclusive via
│   │   ``toggleOutline`` / ``toggleVariables``).  Lists ATX
│   │   H1/H2/H3 headings from markdown cells (indented per level)
│   │   and each code cell's first non-blank stripped line
│   │   (leading ``# `` stripped, truncated to 60 chars).  Click
│   │   an entry → Monaco jumps to the cell's first content line
│   │   via ``findCellMarkerLine`` + ``revealLineInCenter`` +
│   │   ``focus``.  New ESM module
│   │   [frontend/js/notebook/outline.js](frontend/js/notebook/outline.js)
│   │   is a pure leaf: ``buildOutline(cells)`` returns a flat
│   │   entry list, no imports from the notebook tree.
│   │   **Extraction is regex-based, deliberately NOT markdown-it**
│   │   — dodges the Sprint-69 UMD/AMD loader-order class
│   │   (BUG-69-01), so the outline still renders when the
│   │   markdown vendor bundle fails to load.  Closure-scoped
│   │   ``outlineEntries`` + 150ms debounce timer in
│   │   [main.js](frontend/js/notebook/main.js); the reactive
│   │   ``this.outline`` gets a fresh array via
│   │   ``reactiveRoot.outline = outlineEntries.slice()`` on
│   │   change so Alpine's x-for diffs once per real edit instead
│   │   of on every tick.  Recompute re-splits from the live
│   │   Monaco model (``splitCells(model.getValue())``) to
│   │   sidestep stale closure ``cells`` — BUG-70-01,
│   │   replay-caught and fixed in the same commit.
│   │   Reactivity-boundary grep gate widened to block
│   │   ``this._outlineEntries`` / ``_outlineTimer`` /
│   │   ``_outlineDebounce``.  Playbook Part K added; replayed in
│   │   Firefox (MCP) as the land gate per
│   │   ``feedback_run_playbook_as_gate``.
│   │   **No Alembic migration.** Trim-safe — no downstream
│   │   sprints (71-74) import ``outline.js`` or read
│   │   ``this.outline``; revert is O(1) sprint-local.
│   │
│   ├── Sprint 71 — SQL cell (DuckDB via PQL.sql)                  ✅ done (e0043dc)
│   │   First non-Python cell type, validates Sprint-66's registry.
│   │   Marker grammar: ``# %% [sql] pql_cell_id="<uuid>"``ext, with
│   │   an optional ``result_var="<ident>"`` segment (Databricks-
│   │   style — picked over the originally-sketched auto-generated
│   │   ``_pql_sql_<short>`` name to keep chained-cell readability).
│   │   ``runCellById`` branches on the registry's new ``sql``
│   │   descriptor and emits ``execute_sql`` over the WS instead of
│   │   ``execute``.  The route handler parses + privilege-checks
│   │   the query against soyuz-catalog (mirrors the
│   │   ``/api/sql/execute`` SELECT loop via the new shared
│   │   ``_resolve_sql_approved_tables`` helper) before wrapping the
│   │   SQL into a ``__pql_sql_run(...)`` snippet that runs in the
│   │   kernel.  The kernel-side helper, defined once at start time
│   │   via ``_NOTEBOOK_BOOTSTRAP_CODE`` (silent execute_request
│   │   gated on ``_run_bootstrap`` awaiting its execute_reply
│   │   before the iopub / shell pump tasks start so SQL runs cannot
│   │   race the helper definition), calls ``PQL.sql`` for real,
│   │   materialises the result as a pandas DataFrame, optionally
│   │   binds it to the user-named ``result_var`` in ``globals()``
│   │   for Variable Explorer to surface, and ``display(df)`` for
│   │   the rich-mime path Sprint 60 built to render the table
│   │   inline.  Restart re-queues the bootstrap via the existing
│   │   execute path under reserved cell_id ``__pql_sql_bootstrap__``
│   │   so ``_is_internal_cell`` skips persistence and the kernel
│   │   serialises the bootstrap before any user execute.  ``+ SQL``
│   │   inserter button slots in next to ``+ Code`` / ``+ Markdown``;
│   │   per-cell ``result_var`` text input lives on the SQL toolbar
│   │   with a 300 ms debounce that writes back to the marker line
│   │   via ``editor.executeEdits`` (no parallel JS-side cell
│   │   metadata store — the marker is the source of truth).
│   │   Reactivity-boundary grep gate widened to block
│   │   ``this._resultVarTimers`` / ``this._sqlBootstrap`` — the
│   │   debounce handle stays inside the toolbar's closure record
│   │   (cleared on cell teardown via ``clearResultVarDebounce``).
│   │   Playbook Part L added; replayed in Firefox (MCP) as the
│   │   land gate per ``feedback_run_playbook_as_gate``.
│   │   **No Alembic migration.** Engine-themes (DuckDB tuning,
│   │   Spark routing) stay Phase 13.  Trim-safe — Sprints 72-74 do
│   │   not import the SQL cell.
│   │   **BUG-71-01 (replay-caught + fixed in the same commit):**
│   │   ``__pql_sql_run`` first passed ``SQLResult.columns``
│   │   (``list[dict[str, str]]``) straight to ``pd.DataFrame(...)``;
│   │   the constructor accepted it but ``DataFrame.__repr__`` raised
│   │   ``TypeError`` when ``display(df)`` triggered the text/plain
│   │   fallback — the cell emitted both an ``html`` mime that
│   │   rendered fine and an ``error`` mime that painted the cell
│   │   red, while the status pill stayed ``ok`` because
│   │   ``execute_reply.status`` only watches the top-level result.
│   │   Fix: extract the bare column names via ``[c.get("name") if
│   │   isinstance(c, dict) else c for c in res.columns]`` before
│   │   constructing the DataFrame.
│   │
│   ├── Sprint 72 — ipywidgets (minimal placeholder)               ✅ done (b8ef7dc)
│   │   Scope deliberately trimmed to a placeholder layer; full
│   │   bidirectional ``comm_msg`` round-trip + vendored widget-
│   │   manager bundle deferred to a future sprint per the
│   │   Phase-12.7 master-plan decision.  ``ipywidgets>=8.1`` added
│   │   to ``pyproject.toml`` so ``import ipywidgets as w`` works in
│   │   the kernel without a NameError.  The output renderer gains a
│   │   high-priority MIME branch for ``application/vnd.jupyter
│   │   .widget-view+json`` that paints a styled placeholder card
│   │   showing a truncated ``model_id`` and the disclaimer
│   │   "Interactive widgets will render in a future release.
│   │   Install widgets in the kernel to see live updates here."
│   │   Missing ``model_id`` degrades to "Widget output
│   │   (unrenderable)".  The widget branch must come BEFORE
│   │   ``text/html`` in ``renderMimeBundle`` because every
│   │   ipywidgets ``execute_result`` also carries a ``text/plain``
│   │   repr like "IntSlider(value=42)" that we do NOT want to leak
│   │   through.  ``renderKernelMsg`` silently swallows ``comm_open``
│   │   / ``comm_msg`` / ``comm_close`` (no console log — a single
│   │   ``IntSlider()`` instantiation emits dozens; logging would
│   │   flood DevTools).  No closure state added, so the
│   │   reactivity-boundary grep gate is unchanged.  No Alembic
│   │   migration.  Playbook Part M added; replayed in Firefox via
│   │   Playwright-MCP — the renderer was verified end-to-end via a
│   │   cache-busted ``import()`` of ``output_renderer.js`` because
│   │   of the BUG-72-01 cache issue noted below.
│   │   **BUG-72-01 (replay-caught + workaround in same commit):**
│   │   the editor's [bootstrap.js](frontend/js/notebook/bootstrap.js)
│   │   carries a ``?v=sprintNN`` query param so its own ``<script>``
│   │   invalidates, but the modules it dynamically imports
│   │   (``editor_shell.js`` + ``main.js`` + the eight siblings
│   │   including ``output_renderer.js``) do **not** carry a
│   │   version param, so the browser keeps the previous deploy's
│   │   modules in disk cache.  Workaround for this sprint: bumped
│   │   bootstrap.js to ``?v=sprint72`` and documented the hard-
│   │   reload requirement in Part M.  Permanent fix (build-time
│   │   version stamp threaded into every dynamic import URL) is
│   │   out of scope here and noted as a follow-on.
│   │
│   ├── Sprint 73 — Per-cell run history + diff (Alembic 018)      ✅ done (dc530eb)
│   │   New ``notebook_cell_run_sources`` table — sibling to the
│   │   Sprint-60 ``notebook_cell_runs`` upsert (which keeps
│   │   "current state per session" and would otherwise clobber the
│   │   prior run on every re-execute).  Each row carries the
│   │   source the kernel actually saw + the lifecycle status /
│   │   timestamps + ``execution_count`` ; rows are inserted by the
│   │   WS handler on every ``execute_request`` (via
│   │   ``record_cell_run_start`` returning an autoincrement id),
│   │   stamped on ``execute_reply`` (via ``record_cell_run_finish``
│   │   keyed off the id stashed in ``pending_run_sources``).  No
│   │   FK to ``notebook_cell_runs`` — link is logical via the
│   │   indexed columns; cascade lives in ``notebook_outputs.py``
│   │   (Sprint-67 cascade-via-service pattern) on file delete +
│   │   rename only.  ``clear_cell`` and ``clear_session`` do
│   │   **NOT** touch the history table — the audit trail
│   │   explicitly survives both per-cell clear-outputs and kernel
│   │   restarts.  New admin-gated endpoint
│   │   ``GET /api/notebook/cell-runs?path=…&cell_id=…&limit=…``
│   │   returns newest-first.  Frontend module
│   │   [frontend/js/notebook/run_history.js](frontend/js/notebook/run_history.js)
│   │   owns the singleton popover + jsdiff-based source diff +
│   │   re-run button; clock-icon ``.pql-nbedit-history-btn``
│   │   mounts on every ``canExecute`` cell via
│   │   ``cell_affordances``.  Re-run sends the historical source
│   │   via the existing ``execute`` WS frame (NOT ``execute_sql``,
│   │   since SQL history rows already hold the wrapped
│   │   ``__pql_sql_run(...)`` snippet — re-running executes the
│   │   same SQL the kernel saw without re-walking the route's
│   │   privilege check) and does **NOT** modify the Monaco buffer
│   │   ("what did the old version produce?" UX, not "revert to
│   │   this").  jsdiff 5.2.0 vendored via new
│   │   [scripts/vendor-diff-lib.sh](scripts/vendor-diff-lib.sh)
│   │   mirroring ``vendor-markdown-libs.sh``; cap at 10000 input
│   │   lines so O(N²) cost stays bounded.  Reactivity-boundary
│   │   grep gate widened to block ``this._historyCache`` /
│   │   ``this._historyPopover`` / ``this._historyAbort`` — an
│   │   AbortController on Alpine's proxy would let the reactive
│   │   walk reach into the WHATWG fetch stream's deep registry
│   │   state, the same class as BUG-69-01 / BUG-64-02.  Playbook
│   │   Part N added; replayed in Firefox via Playwright-MCP as
│   │   the land gate.
│   │   **BUG-73-01 (replay-caught + fixed in same commit):**
│   │   ``clear_cell`` cascade was wiping
│   │   ``notebook_cell_run_sources`` on every re-execute (since
│   │   ``_wipe_cell_for_new_execute`` calls ``clear_cell`` to
│   │   reset the previous run's outputs).  Result: only the
│   │   most-recent run ever existed in the history table; popover
│   │   header always read ``Last 1 run``.  Fix: removed the
│   │   ``NotebookCellRunSource`` delete from ``clear_cell`` AND
│   │   ``clear_session``; cascade now lives only in ``clear_path``
│   │   (file delete) and ``rename_path`` (file rename).  Caught
│   │   at the N2 step on the first replay.
│   │
│   └── Sprint 74 — Theme + keymap overlay + phase close           ✅ done (a184ef3)
│       Settings drawer (``vs-dark`` / ``vs`` / ``hc-black`` themes;
│       font-size 10-22; autosave-debounce 200-2000 ms) + keymap
│       overlay listing every editor command + phase-12.7 close.
│       Two new ESM modules
│       [frontend/js/notebook/settings_drawer.js](frontend/js/notebook/settings_drawer.js)
│       and
│       [frontend/js/notebook/keymap_overlay.js](frontend/js/notebook/keymap_overlay.js);
│       both are lazy-mounted singletons attached to ``<body>``.
│       Gear (⚙) and ``?`` toolbar buttons in
│       [notebook_editor.html](frontend/templates/pages/notebook_editor.html)
│       open them; Monaco's ``Ctrl+Alt+/`` keybind is the third
│       entry into the keymap overlay (``Ctrl+/`` left bound to
│       Monaco's default ``toggle-line-comment`` to avoid shadowing
│       the editor convention).  Settings persist to localStorage
│       under ``pql.nbedit.theme.v1`` / ``pql.nbedit.fontSize.v1``
│       / ``pql.nbedit.autosave.debounceMs.v1`` (Sprint-67 / 68
│       ``.v1`` suffix convention); changes broadcast via a
│       ``pql:settings-changed`` ``CustomEvent`` on ``document``
│       so every open tab's editor re-applies via
│       ``monaco.editor.setTheme`` (page-global) +
│       ``editor.updateOptions({fontSize})`` (per-instance) + a
│       lifted ``_autosaveDebounceMs`` closure variable
│       ``scheduleAutosave`` reads at flush-queue time.
│       ``registerPaletteActions`` extended with four new palette
│       commands (``pql.toggleOutline`` / ``pql.openHistory`` /
│       ``pql.openSettings`` / ``pql.openKeymap``).
│       [bootstrap.js](frontend/js/notebook/bootstrap.js) tab-scope
│       stub gained ``outlineVisible`` / ``outline`` plus the four
│       new method names so the pre-mount window no longer raises
│       ``ReferenceError`` on Alpine ``x-show`` / ``@click``
│       expressions (Sprint-72 console-noise tail fixed).  Playbook
│       Part O added; replayed in Firefox via Playwright-MCP as
│       the land gate.
│       **No Alembic migration.** Trim-safe — Sprint 74 is the last
│       sprint of Phase 12.7, no downstream sprints depend on it.
│       **BUG-74-01 (replay-caught + fixed in same commit):**
│       double-backticks inside an HTML template literal in
│       ``buildModal`` (the GitHub-flavoured-markdown-style
│       ``\`\`pql.*\`\``` text in the modal footer) terminated the
│       backtick-quoted string early, raising a ``SyntaxError``
│       inside ``buildModal`` the moment ``mountKeymapOverlay``
│       called it.  Symptom: ``mount()`` caught the error generally
│       at [main.js:317](frontend/js/notebook/main.js#L317);
│       settings drawer mounted (earlier in the flow) but keymap
│       overlay never materialised, and the per-cell affordances
│       (mounted later) never rebuilt.  Fix: replaced the markdown
│       backticks with plain ``pql.*`` text in the modal footer.
│       Caught pre-gate via a cache-busted dynamic ``import()``
│       that surfaced the real
│       ``buildModal@keymap_overlay.js:137:18`` stack trace.
│
│   Phase 12.7 close-out.  Ten sprints (65-74) over the phase
│   transformed the notebook editor from the Sprint-58 single-file
│   monolith into a modular, multi-tab, multi-cell-type, audit-
│   trailed surface.  Sprint hashes in chronological order:
│   - Sprint 65 — module split + closure-refs + reactivity gate.
│   - Sprint 66 — cell-type registry + per-cell affordances.
│   - Sprint 67 — file-tree sidebar + notebook CRUD (d41a4eb).
│   - Sprint 68 — multi-notebook tab bar (400670c).
│   - Sprint 69 — markdown-it + KaTeX + pencil-pin (d3c7df7).
│   - Sprint 70 — outline / TOC panel + cell jump (b6fe0e2).
│   - Sprint 71 — SQL cell (DuckDB via PQL.sql) (e0043dc).
│   - Sprint 72 — ipywidgets minimal placeholder (b8ef7dc).
│   - Sprint 73 — per-cell run history + diff (Alembic 018) (dc530eb).
│   - Sprint 74 — settings drawer + keymap overlay + phase close (a184ef3).
│
│   **Phase 12.7 tail commit:** closing audit-pass replay surfaced
│   BUG-71-02 (server-side notebook_doc.py dropped the ``[sql]``
│   tag + ``result_var`` on round-trip via jupytext) and exposed
│   the Sprint-72 BUG-72-01 "workaround" claim as wrong.  Both
│   fixed in a single follow-up: ``notebook_doc.py`` post-parses
│   the raw .py with a ``_PQL_MARKER_RE`` (mirrors
│   ``cell_parser.js``) to recover ``[sql]`` + ``result_var`` and
│   post-writes via ``_rewrite_sql_markers`` to put them back;
│   the API save validator + load bundle thread the new field
│   through; ``main.js`` normalises ``result_var`` ↔ ``resultVar``
│   at the wire boundary.  BUG-72-01 root fix is a new
│   ``static_module_revalidate_middleware`` that stamps
│   ``Cache-Control: no-cache, must-revalidate`` on every
│   ``/static/js/notebook/*`` response so browsers do conditional
│   GETs (304 when unchanged, fresh bytes on deploy) without
│   needing a hard-reload.  Replay coverage completed for L6 / L7 /
│   L8 / L9 / M1-M5 / N6 / N7 / N8 / O3 / O5 / O6 — documented in
│   the Phase-12.7 tail block of
│   [docs/e2e-walkthroughs/notebook-editor.md](docs/e2e-walkthroughs/notebook-editor.md).
│   Phase 13 (Agent workloads) is next on the roadmap with the
│   EXPLAIN-agent loop sketched as the natural Phase-12 → Phase-13
│   bridge.
│
├── Phase 12.8 — Frontend cleanup                         ✅ done
│   │
│   │   One-shot reorg sprint: the JS layer was carrying a Sprint-22
│   │   shape (everything as window-IIFE Alpine factories) under a
│   │   Sprint-65+ notebook subsystem (already native ESM); five
│   │   small editors copy-pasted the same fetch / error pattern;
│   │   ``pqlApi.fetch`` did not inject the CSRF header (relied on
│   │   the server's form-field fallback alone); ``style.css`` was a
│   │   single 32 KB file; ``notebook/main.js`` had grown to 1547
│   │   LOC.  No new feature — pure code-organisation work to clear
│   │   the surface before Phase 13.  Six commits, six phases, one
│   │   sprint.  Hard constraint: no build step, no bundler, no
│   │   ``package.json`` (CLAUDE.md rule).
│   │
│   └── Sprint 75 — Frontend cleanup (notebook carve-up + ESM-everywhere + CSS-split + CSRF + README)  ✅ done (e0ae139)
│       Six-phase sprint shipped as six commits on main; no Alembic
│       migration; no behaviour change beyond the latent CSRF fix.
│
│       **Phase 1 — notebook/main.js carve-up** (247e271).
│       Split the 1547-LOC orchestrator into the factory shell + five
│       sibling modules: new
│       [output_zone_manager.js](frontend/js/notebook/output_zone_manager.js)
│       (Monaco view-zone lifecycle for outputs + markdown previews +
│       hidden-area updates),
│       [cell_introspector.js](frontend/js/notebook/cell_introspector.js)
│       (stateless cursor/model lookups),
│       [autosave_scheduler.js](frontend/js/notebook/autosave_scheduler.js)
│       (debounce + in-flight queue),
│       [commands.js](frontend/js/notebook/commands.js) (Monaco
│       command-palette registrations); plus a new
│       ``createOutlineRecomputer`` factory in
│       [outline.js](frontend/js/notebook/outline.js) that folds the
│       150 ms recompute-debounce out of main.js.  main.js drops
│       1547 → 1204 LOC and now owns orchestration glue only (mount,
│       kernel WS, LSP WS, cell affordances, save).  Grep gate
│       [check-frontend-no-reactive-monaco.sh](scripts/check-frontend-no-reactive-monaco.sh)
│       extended with autosaveScheduler / autosaveTimer / zoneManager
│       / outputZones / markdownZones / outlineRecomputer so the
│       BUG-64-02 closure-state discipline cannot be undone by a
│       future submodule that parks the new factories' return objects
│       on Alpine's proxy.
│
│       **Phase 2 — ESM bridge entrypoint** (87f03a7).  New
│       [frontend/js/bootstrap.js](frontend/js/bootstrap.js) loaded
│       as ``<script type="module">`` from
│       [base.html](frontend/templates/base.html) before the Alpine
│       CDN script.  ``type="module"`` is defer-by-default and runs
│       in document order, so anything bootstrap.js registers on
│       ``window`` is live before Alpine's x-data walk begins.  New
│       gate
│       [check-frontend-bootstrap-order.sh](scripts/check-frontend-bootstrap-order.sh)
│       wired into CI asserts the script-tag ordering.
│
│       **Phase 3 — editor_base + small editors to ESM** (410f144).
│       New [editor_base.js](frontend/js/editor_base.js) exports
│       ``validateRequired`` (tags / permissions / federation share
│       the trim+null-check) and ``createDictEditor`` (promoted out
│       of properties_editor.js's pre-Sprint-75 private
│       ``_makeDictEditor`` helper).  Migrated to ES modules:
│       [editable.js](frontend/js/editable.js),
│       [permissions_editor.js](frontend/js/permissions_editor.js),
│       [tags_editor.js](frontend/js/tags_editor.js),
│       [properties_editor.js](frontend/js/properties_editor.js)
│       (shrunk 73 → 14 LOC).  Resisted extracting a generic
│       ``runApiAction`` mega-factory — every consumer's onSuccess
│       body is unique and a wrapper would cost more in
│       reader-overhead than the ~3 lines per site it would save.
│
│       **Phase 4 — federation / list_table / sql_editor / helpers
│       to ESM** (2d9e1e2).  Last legacy files migrated:
│       [api.js](frontend/js/api.js) (window.pqlApi),
│       [toast.js](frontend/js/toast.js) (window.pqlToast),
│       [relative_time.js](frontend/js/relative_time.js),
│       [humanize_cron.js](frontend/js/humanize_cron.js),
│       [job_row_actions.js](frontend/js/job_row_actions.js),
│       [federation.js](frontend/js/federation.js) (5 form factories
│       now consume validateRequired),
│       [list_table.js](frontend/js/list_table.js),
│       [sql_editor.js](frontend/js/sql_editor.js) (module-level
│       ``cmView`` and ``catalogCompletions`` moved into the factory
│       closure — ESM makes module-singleton state more dangerous on
│       revisit than the pre-Sprint-75 IIFE shape).  Removed all 11
│       individual ``<script src="/static/js/X.js">`` tags from
│       base.html + sql_editor.html; only bootstrap.js + Alpine +
│       vendor CDN scripts load via raw ``<script>`` now.
│
│       **Phase 5 — CSRF in pqlApi + frontend README** (a5a7a20).
│       ``pqlApi.fetch`` now injects ``X-CSRF-Token`` from
│       ``<meta name="csrf-token">`` for every non-GET/HEAD/OPTIONS
│       request.  Mirrors what ``notebook/main.js`` /
│       ``editor_shell.js`` / ``file_tree.js`` already do by hand
│       and what the ``htmx:configRequest`` hook in base.html does
│       for HTMX mutations.  Form-field fallback stays as
│       belt-and-suspenders.  New
│       [frontend/js/README.md](frontend/js/README.md) documents the
│       post-Sprint-75 conventions: window-naming rules, the
│       editor_base helper surface, the simplify-skill rationale for
│       NOT extracting a generic wrapper, the script-load order, the
│       BUG-64-02 reactivity boundary discipline + how to extend the
│       grep gate, vendor-library handling.
│
│       **Phase 6 — style.css split** (e0ae139).  Carved the
│       1066-line single-file
│       [style.css](frontend/css/style.css) into ten purpose-scoped
│       sheets: base.css, primitives.css, layout.css, responsive.css,
│       and components/{breadcrumbs,empty_state,toast,command_palette,
│       dashboard,list_table}.css.  style.css is now 30 LOC of
│       cascade-ordered ``@import`` statements.  No CSS rule moved
│       between sections — every selector landed in the file matching
│       its pre-Sprint-75 section header; cascade order preserved by
│       the @import order.  Why @import (not concatenation): no build
│       step, no bundler.  CSS @import resolves natively in every
│       supported browser; HTTP/2 multiplexing makes the extra
│       requests harmless on localhost.
│
│       **Out of scope (deferred):** full ESM migration of the
│       ``vendor/`` UMD bundles (Monaco / markdown-it / KaTeX /
│       jsdiff stay as plain ``<script>`` loads); JS unit-test
│       framework (no recurring regression bucket yet); CSS
│       cache-busting via hashed filenames (would require a build
│       step); per-page templates' inline ``<script>`` blocks (a
│       separate audit).  All deferrals documented in
│       [frontend/js/README.md](frontend/js/README.md) so a future
│       sprint picking up the work has the rationale.
│
│       **Static gates (run after every phase):** ``ruff``,
│       ``pyright`` (0 errors, warnings unchanged), ``alembic``,
│       ``node --check`` on every modified JS file, both grep gates
│       (reactive-monaco + bootstrap-order).  No Playwright-MCP
│       replay this sprint — every change is mechanical
│       (file-shape migration, function moves, header-tag injection,
│       file split); a behaviour-touching change in the same
│       neighbourhood would still warrant the playbook gate.
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
├── Phase 12.10 — Notebook format hardening               ✅ done
│   │
│   │   Driven by user feedback after Phase 12.7 closed: the
│   │   jupytext-percent ``.py`` files still embedded a
│   │   PointlesSQL-specific ``pql_cell_id="<uuid>"`` token in
│   │   every cell marker, so the files were not generically
│   │   editable in VSCode / Vim / Codium without risking a
│   │   500 on reload if the user manually removed or reordered
│   │   a UUID.  No other notebook IDE (VSCode Interactive,
│   │   PyCharm, Spyder, Databricks ``.py`` export, JupyterLab
│   │   + jupytext, Marimo) persists cell UUIDs in the ``.py``
│   │   source — the UUID segment was a Phase 12.6 expedient
│   │   that outlived its purpose.  Phase 12.10 rips it out,
│   │   switches the persistence layer to a content-hash
│   │   identity (``FNV-1a-64(normalized_source)``, 16 hex
│   │   chars) that both Python and the browser compute
│   │   byte-for-byte, and then runs a deterministic
│   │   browser-walkthrough to sweep the Monaco output-rendering
│   │   bugs the user reported during the same session.  Plan
│   │   lives at
│   │   [.claude/plans/ich-m-chte-dass-du-luminous-ullman.md](/home/flo/.claude/plans/ich-m-chte-dass-du-luminous-ullman.md).
│   │
│   ├── Sprint 96 — Cell-ID refactor: marker grammar + content-hash identity ✅ done (4c59b85)
│   │       Merged the two sprints the plan originally sketched
│   │       ("A: DB migration" + "B: marker grammar drop") into a
│   │       single coherent commit because the pair is a
│   │       semantically-atomic rename — intermediate landings
│   │       would leave the DB column name mismatched with its
│   │       value format.
│   │
│   │       On-disk grammar cleaned up to the IDE-agnostic shape
│   │       VSCode / Spyder / PyCharm already recognise:
│   │
│   │           # %%                  — code cell
│   │           # %% [markdown]       — markdown cell
│   │           # %% [sql]            — SQL cell without a result variable
│   │           # %% [sql] df         — SQL cell binding its DataFrame to `df`
│   │
│   │       No UUID, no ``pql_cell_id="…"``, no named
│   │       ``result_var="…"`` segment.  Legacy files carrying
│   │       the old grammar still load through a tolerant
│   │       fallback regex; ``load_document`` sets ``dirty=True``
│   │       so the editor prompts a one-time save that rewrites
│   │       the file into the clean shape.  Zero byte churn on
│   │       re-save of an already-clean file (``test_save_load_
│   │       roundtrip_clean_grammar``).
│   │
│   │       Cell identity splits into two separate concepts:
│   │
│   │       * **Transient ordinal label** (``cell-0``, ``cell-1``,
│   │         …) — minted by ``splitCells`` on every parse.  Used
│   │         only as the Alpine ``x-for :key`` / DOM ref key
│   │         inside one editor session.  Never persisted.
│   │       * **Content-hash identity** (``FNV-1a-64`` of the
│   │         whitespace-normalised source, 16 hex chars).  Used
│   │         for every DB lookup + every WS frame that addresses
│   │         a cell.  Stable across reordering + whitespace-only
│   │         edits; naturally splits on meaningful source
│   │         changes — analogous to how git gives a new commit
│   │         a fresh SHA.
│   │
│   │       - **Alembic migration 019** renames ``cell_id`` →
│   │         ``content_hash`` across ``notebook_outputs``,
│   │         ``notebook_cell_runs``, ``notebook_cell_run_sources``.
│   │         Pre-migration rows keep their UUID payload in the
│   │         renamed column — they are orphans now (no new cell
│   │         will compute to a UUID-shaped hash) but the natural
│   │         ``clear_path`` cascade on next notebook-delete /
│   │         rename reaps them.  SQLite + Postgres both round-
│   │         trip cleanly (``alembic downgrade -1 && upgrade head``).
│   │
│   │       - **Python + JS mirror helpers.**  FNV-1a-64 was
│   │         picked over SHA-256 because it has a trivial
│   │         synchronous mirror via ``BigInt`` on the browser
│   │         side — SubtleCrypto would have forced an async
│   │         cascade through every ``splitCells`` caller.  The
│   │         reference vector ``cbf29ce484222325`` (empty source)
│   │         is pinned in ``test_notebook_doc.py`` to catch
│   │         cross-language drift without a Playwright replay.
│   │
│   │       - **Server-side rewrites.**  ``notebook_doc.py``
│   │         marker regex + parser + serialiser; the legacy
│   │         regex stays as a read-only fallback for one-way
│   │         migration.  ``notebook_outputs/outputs.py`` +
│   │         ``cell_runs.py`` + ``kernel_session/session.py`` +
│   │         ``messages.py`` + ``api/notebook_kernel_ws.py`` +
│   │         ``api/notebooks_routes.py`` + ``api/governance_
│   │         routes.py`` all rename ``cell_id`` → ``content_hash``
│   │         in service signatures, WS frame keys, and SQLAlchemy
│   │         queries.  ``KernelMessage`` carries a
│   │         ``content_hash: str | None``.
│   │
│   │       - **Client-side rewrites.**  ``cell_parser.js`` picks
│   │         up ``computeContentHash`` + the new + legacy marker
│   │         regexes; ``cell_introspector.js`` switches from
│   │         UUID-match to positional ordinal-label lookup;
│   │         ``cell_editor.js`` emits clean markers on
│   │         insert / addBelow / addAbove and rewrites SQL
│   │         markers with the positional ``result_var`` shape;
│   │         ``kernel_ws.js`` takes a ``resolveCellId`` closure
│   │         so incoming kernel messages route back to the
│   │         session-local label via the content-hash index
│   │         ``main.js`` maintains alongside ``cellAffordances``;
│   │         ``output_zone_manager.js`` takes the same resolver
│   │         for ``replayPersistedOutputs`` so server-returned
│   │         content-hashes map onto live cells (rows whose
│   │         hash no longer matches any cell — i.e. the user
│   │         edited the source — are silently dropped, matching
│   │         the VSCode / Databricks orphan-output behaviour);
│   │         ``run_history.js`` addresses the history endpoint
│   │         by ``content_hash``.
│   │
│   │       - **Tests.**  New ``tests/test_notebook_doc.py``
│   │         (11 cases) covers the FNV-1a reference vector,
│   │         whitespace-tolerance, clean-grammar round-trip
│   │         byte-stability, positional ``# %% [sql] df`` on
│   │         disk, legacy-file ``dirty`` flag, and the one-way
│   │         legacy → clean migration save.  Node reference
│   │         vector produced identical hashes to Python for
│   │         ``""`` / ``"print(1)"`` / ``"print(1)\n"`` /
│   │         ``"# %%\nprint(1)\n"`` before commit.
│   │
│   │       **Static gates (all green):** ``ruff check`` 0
│   │       errors; ``pyright`` 0 errors / 154 pre-existing
│   │       warnings unchanged; ``pydoclint --style=google`` 0
│   │       violations on every touched file; ``alembic upgrade
│   │       head`` + ``downgrade -1`` + ``upgrade head`` idempotent
│   │       round-trip on a fresh SQLite DB;
│   │       ``pytest tests/test_notebook_doc.py`` 11/11 passing.
│   │
│   ├── Sprint 97 — Parser hardening against manual edits       ✅ done (ac6958e)
│   │       Defensive guards in ``notebook_doc.py`` +
│   │       ``cell_parser.js`` for every shape a user can produce
│   │       by editing a ``.py`` directly in VSCode / Vim.  Both
│   │       sides gained a ``_normalise_file_text`` / inline
│   │       equivalent that strips UTF-8 BOM + collapses CRLF /
│   │       CR to LF before the regex walk; jupytext is now fed
│   │       the normalised string via ``jupytext.reads`` rather
│   │       than the raw file path so a BOM never glues to the
│   │       first cell's source as ``\ufeff`` noise.
│   │
│   │       Scenarios covered, each with a dedicated test in
│   │       ``tests/test_notebook_doc.py`` (now 20 cases total,
│   │       up from Sprint 96's 11):
│   │
│   │       - **Empty file** → single empty ``cell-0``, ``dirty=True``.
│   │       - **Plain .py, no markers at all** → whole file becomes a
│   │         single code cell the user can inspect + add markers
│   │         from the UI; next save materialises a ``# %%`` header.
│   │       - **Unknown tag** (``# %% [foo]``) → falls back to
│   │         ``code``; next save rewrites to plain ``# %%``.
│   │       - **SQL marker without identifier** (``# %% [sql]``) →
│   │         ``cell_type="sql"`` + ``result_var=None``; no crash.
│   │       - **CRLF line endings** → normalised to LF,
│   │         ``dirty=True`` so the next save writes LF-only bytes.
│   │       - **UTF-8 BOM** → stripped, ``dirty=True``; cell source
│   │         no longer starts with ``\ufeff``.
│   │       - **File ending mid-cell without trailing newline** →
│   │         parser passes through; content survives verbatim.
│   │       - **Duplicate cells (identical sources)** → both get the
│   │         same content-hash; tie-breaking lives upstream in the
│   │         WS run-history matcher (cellAffordances keys on the
│   │         transient ``cell-N`` label, so DOM stays distinct).
│   │       - **Cell reorder** → per-cell content-hash is
│   │         reorder-invariant (``test_manual_cell_reorder_
│   │         preserves_content_hash``).
│   │
│   │       Client-side mirror: ``cell_parser.js``'s ``splitCells``
│   │       now strips CRLF + BOM and returns a single synthetic
│   │       ``cell-0`` for markerless text, so the Monaco model
│   │       sees the same shape the server saw on load.
│   │
│   │       **Static gates (all green):** ``ruff`` 0 errors,
│   │       ``pyright`` 0 errors, ``pydoclint --style=google`` 0
│   │       violations, 20/20 tests pass.
│   │
│   └── Sprint 98 — Browser walkthrough + bug sprint            ✅ done (a50df3a)
│           Deterministic Playwright playbook landed at
│           [docs/e2e-walkthroughs/notebook_full_walkthrough.md](docs/e2e-walkthroughs/notebook_full_walkthrough.md)
│           walking 14 output scenarios (stdout, pandas
│           DataFrame, matplotlib, markdown cell, display
│           (Markdown), stderr + stdout, traceback, HTML,
│           save, reload, external edit, markerless file,
│           BOM / CRLF).  Screenshots live under
│           ``docs/e2e-walkthroughs/screenshots/sprint-98/``.
│
│           Two inline fixes landed with this sprint because
│           they surfaced as clear regressions of the
│           Sprint-96 rewrite:
│
│           - **BUG-98-02** — ``display(Markdown("…"))`` showed
│             ``<IPython.core.display.Markdown object>`` because
│             ``output_renderer.js`` lacked a ``text/markdown``
│             mime branch.  Added the branch, re-using the
│             existing ``renderMarkdown`` helper from
│             ``markdown.js``; also added a
│             ``.pql-nbedit-output-markdown`` CSS rule in
│             ``notebook_editor.html`` for heading + code +
│             spacing.  Verified fix in Playwright (screenshot
│             ``12-markdown-display-fixed.png``).
│
│           - **BUG-98-05** — output view-zones keyed by the
│             transient ``cell-N`` label accumulated as ghosts
│             across ``setValue`` calls because
│             ``rebuildCellAffordances`` only pruned the
│             affordance widgets, not the view zones.  Added
│             ``pruneOrphanOutputZones(alive)`` on the
│             output-zone manager + wired it into
│             ``main.js``'s ``rebuildCellAffordances`` pass.
│
│           One deferred follow-up tagged in the playbook tail:
│           **BUG-98-01** — markdown view-zone preview misses
│           its first paint after a synthetic ``setValue``
│           (real users hit the ``+ Markdown`` toolbar button
│           which triggers the rebuild through the normal
│           content-change path, so the bug is only observable
│           in the Playwright replay).  Low priority.
│
│           On-disk invariant verified: a freshly-saved
│           ``sprint98_walkthrough.py`` has zero
│           ``pql_cell_id`` tokens + zero UUID-shaped
│           substrings — Sprint 96's goal reached in the
│           browser, not just in the tests.
│
├── Phase 12.11 — Notebook visual polish                  ✅ closed (scope cut after S99)
│   │
│   │   Phase 12.10 closed the semantic side of the native
│   │   notebook editor (marker grammar, content-hash identity,
│   │   parser robustness).  The visible chrome lagged behind and
│   │   Phase 12.11 was planned as a four-sprint polish run.
│   │   Sprint 99 (toolbar + badges) landed.  Sprints 100-102
│   │   were **cancelled** when the agent-first pivot
│   │   (Phase 12.12) landed: polishing authoring-chrome for a
│   │   surface that was about to be deleted would have been
│   │   throwaway work.  The output-zone ``.card`` idea from
│   │   Sprint 100 was re-homed into the server-side run-detail
│   │   view (``frontend/templates/pages/run_view.html``) during
│   │   Sprint 12.12.1, so the visual design intent lives on.
│   │   Plan stub at
│   │   [.claude/plans/phase-12-11-notebook-unified-anchor.md](/home/flo/.claude/plans/phase-12-11-notebook-unified-anchor.md).
│   │
│   ├── Sprint 99 — Toolbar + status badges               ✅ done (529aa57)
│   │       Editor toolbar moved to Bootstrap-native chrome.
│   │       The audit walked back the original sketch's "9 bare
│   │       buttons" framing — the buttons already carried
│   │       ``btn btn-sm btn-outline-*`` variants and Bootstrap
│   │       icons since earlier sprints.  The real visual debt was
│   │       narrower:
│   │
│   │       - **Status pills.**  The ``saveState`` / ``kernelStatus``
│   │         / ``lspStatus`` spans were bare ``text-success`` /
│   │         ``text-warning`` / ``text-danger`` text living next
│   │         to the toolbar.  Replaced with
│   │         ``.badge .rounded-pill .text-bg-{success,warning,
│   │         danger,secondary}`` mirroring the Jinja2 inline
│   │         pattern from
│   │         ``frontend/templates/components/sync_history_card.html``
│   │         and ``pages/jobs.html``.  Strings stay verbatim so the
│   │         deterministic playbook assertions
│   │         ([notebook-editor.md:43-47](docs/e2e-walkthroughs/notebook-editor.md),
│   │         [notebook_full_walkthrough.md:34](docs/e2e-walkthroughs/notebook_full_walkthrough.md))
│   │         still match.  Five ``saveState`` / five
│   │         ``kernelStatus`` / four ``lspStatus`` values each get
│   │         their own variant — not just the three the sketch
│   │         imagined.
│   │
│   │       - **Semantic ``btn-group``s.**  The eleven toolbar
│   │         buttons were wrapped in four labelled groups
│   │         (``aria-label="Cell ops"`` / ``"Kernel"`` /
│   │         ``"Panels"`` / ``"Help"``) using the
│   │         ``btn-group btn-group-sm role="group"`` pattern from
│   │         ``frontend/templates/pages/sql_editor.html:202-220``.
│   │         The "Run cell" CTA stays standalone with
│   │         ``btn-primary ms-2`` — only primary action on the
│   │         toolbar, matches the Run / Cancel split from
│   │         sql_editor's query toolbar.  Catalog stays as an
│   │         action button (it opens a picker modal, not a
│   │         persistent side panel like Variables / Outline).
│   │
│   │       - **A11y for icon-only buttons.**  Settings (``bi-gear``)
│   │         and Keymap (``bi-question-circle``) gained explicit
│   │         ``aria-label="Editor settings"`` /
│   │         ``"Keymap overlay"``.  ``title`` stays for hover
│   │         tooltips; ``aria-label`` covers screen readers.
│   │
│   │       - **CSS cleanup.**  ``.pql-nbedit-dirty`` (relict from
│   │         pre-Sprint-58 dirty-state flagging) and the unused
│   │         ``.pql-nbedit-status`` class were removed.  The
│   │         existing ``.pql-nbedit-status-pill`` per-cell
│   │         styling was deliberately left untouched — it covers
│   │         the per-cell run-status pill, not the toolbar.
│   │
│   │       Browser replay against Firefox via Playwright-MCP
│   │       confirmed the static evaluations: three pills with the
│   │       expected ``text-bg-*`` classes, four ``btn-group``s with
│   │       3 / 2 / 3 / 2 buttons, ``runBtnIsStandalone=true``,
│   │       both icon-only buttons expose ``aria-label``.
│   │       Screenshots at
│   │       ``docs/e2e-walkthroughs/screenshots/sprint-99/``.  No
│   │       JS, Python, or marker-grammar code touched — Sprint-96
│   │       invariants intact, ``tests/test_notebook_doc.py`` 20/20
│   │       still green.
│   │
│   │       **Static gates:** ``ruff check`` flagged one preexisting
│   │       I001 in ``tests/test_pg_sync.py:18`` (Sprint-82-era
│   │       import-block ordering, untouched by Sprint 99 — out of
│   │       scope per ``feedback_audit_first_narrow_scope``);
│   │       ``pyright`` 0 errors / 155 preexisting warnings;
│   │       ``pydoclint --style=google`` 🎉 no violations;
│   │       ``pytest tests/test_notebook_doc.py`` 20/20 pass;
│   │       ``node --check frontend/js/notebook/main.js`` clean
│   │       (file unmodified).
│   │
│   └── Sprints 100-102 — ❌ cancelled (agent-first pivot).
│           Output-zone ``.card`` polish re-homed into the
│           server-side ``run_view.html`` in Sprint 12.12.1.
│           Per-cell affordance toolbar + DataFrame polish have
│           no surface post-pivot (no browser editor) — the
│           equivalent chrome lives in the supervision
│           run-detail view, slated for Sprint 13.4 polish.
│
├── Phase 12.12 — Agent-first pivot: delete editor, build run-view  ✅ done
│   │
│   │   Decision (2026-04-24): humans no longer author notebooks
│   │   in the browser.  Agents drop ``.py`` jupytext-Percent
│   │   files into ``notebooks/`` (or a UC Volume), the scheduler
│   │   executes them, and the human surface is a supervision
│   │   page at ``/runs`` plus a per-run detail view.  The native
│   │   notebook editor (25 JS modules, Monaco + Pyright LSP +
│   │   kernel WS, ~16 MB vendored libs, 600+ LOC of WS routes)
│   │   was deleted outright.  Server-side Jinja ``run_view.html``
│   │   replaces the browser editor as the read-only surface for
│   │   one notebook + its persisted outputs; ``/runs`` replaces
│   │   the Notebook nav entry.  Plan:
│   │   [.claude/plans/siehst-du-mein-repo-zany-horizon.md](/home/flo/.claude/plans/siehst-du-mein-repo-zany-horizon.md).
│   │
│   ├── Sprint 12.12.1 — JS / CSS / template deletion + server-render skeleton  ✅ done (bc2ad07)
│   │       Deleted all 25 modules under
│   │       ``frontend/js/notebook/``, all five vendored JS libs
│   │       under ``frontend/js/vendor/`` (~16 MB: Monaco, KaTeX,
│   │       markdown-it, markdown-it-texmath, jsdiff), their
│   │       fetcher scripts, the editor-shell + modal templates,
│   │       and the corresponding .gitignore entries.  Added the
│   │       server-side renderer
│   │       ``pointlessql/services/output_rendering.py`` (mime
│   │       priority ``markdown`` → ``html`` → ``svg`` → ``png``
│   │       → ``jpeg`` → ``json`` → ``plain``, ANSI via
│   │       ``ansi2html``, Markdown via ``markdown-it-py``) plus
│   │       four Jinja partials
│   │       (``_output_stream`` / ``_output_error`` /
│   │       ``_output_markdown`` / ``_output_display_data``) and
│   │       the Bootstrap ``.card``-per-cell ``run_view.html``
│   │       skeleton.  Three new runtime deps:
│   │       ``markdown-it-py>=3.0``, ``ansi2html>=1.9``,
│   │       ``Pygments>=2.18``.  Static gates green; route audit
│   │       clean.  Known interim state to be fixed in 12.12.2:
│   │       ``/notebook/editor`` still registered (returns a 500
│   │       ``TemplateNotFound``), the Nav still points at it.
│   │
│   └── Sprint 12.12.2 — Backend routes cleanup + runs stub  ✅ done (ac5207e)
│           Deleted the Notebook-Editor HTTP routes
│           (``GET /notebook/editor``, ``GET`` / ``POST /api/notebook/doc``,
│           ``GET /api/notebook/cell-runs``), the workspace CRUD
│           (``POST /api/notebooks/upload``, ``/create``,
│           ``PATCH /api/notebooks/rename``, ``DELETE /api/notebooks``),
│           both WebSocket routes
│           (``/ws/notebook/kernel`` + ``/ws/notebook/lsp``),
│           the governance ``open-in-notebook`` helper + its
│           table-detail button, the editor-only
│           ``pyright_bridge`` service, the
│           ``static_module_revalidate_middleware`` layer, and
│           the stale ``tests/test_jupyter.py`` (``services/jupyter``
│           was already gone since Sprint 63).  Kept
│           ``services/kernel_session/`` as a library — left in
│           place for a future local-executor fallback, but
│           Phase 13 (revised) treats PointlesSQL as a registry
│           + store, not an executor, so it has no in-repo
│           caller today.  Kept ``services/notebook_outputs/`` +
│           ``services/notebook_doc.py`` — the writer-side and
│           the cell parser both feed the run-detail view.
│           Added ``/runs`` stub route + empty-state template so
│           the nav has a landing page; Nav flipped *Notebook* →
│           *Runs*; Workspace page trimmed to read-only listing
│           + *Schedule…* button (Papermill pre-fill).  End-to-
│           end pivot check: all eight removed routes absent
│           from ``app.routes``, ``/runs`` present, 120 total
│           routes (was 130 before 12.12.1).  Ruff / pyright /
│           pydoclint green against ``pointlessql/``; the lone
│           ``tests/test_pg_sync.py`` I001 is pre-existing from
│           Sprint 82.
│
├── Phase 13 — Agent-run supervision + analytical memory  ✅ done
│   │
│   │   Positioning (2026-04-24 pivot): PointlesSQL is the
│   │   **persistent analytical memory for agents** — not a
│   │   lakehouse competitor, not a query engine, not a runtime.
│   │   Agents already have conversational memory (Hermes alone
│   │   bundles honcho, mem0, supermemory, byterover, hindsight,
│   │   holographic, openviking, retaindb — eight providers).
│   │   None persist Delta tables, UC metadata, column stats,
│   │   lineage graphs, or run history across months.  PointlesSQL
│   │   fills that empty slot.  One-liner: *"Mem0 is what your
│   │   agent remembers you said; PointlesSQL is what your agent
│   │   knows about the data."*
│   │
│   │   Communication chain for roadmap pitches:
│   │
│   │       Data primitives (PointlesSQL + soyuz)
│   │         → Agent runtime (Hermes — first concrete consumer)
│   │           → Work orchestration (Paperclip — upstream)
│   │
│   │   ``shoreguard-fresh`` remains the orthogonal policy gate
│   │   at every edge — approval quora, Z3 verification, OCSF
│   │   audit.  It is not a link in the chain.
│   │
│   │   Scope cut from the original sketch (see
│   │   ``feedback_audit_first_narrow_scope.md`` — scope drift
│   │   is expected and correct):
│   │
│   │   * **PointlesSQL does NOT execute agent runs.**  Hermes
│   │     (or any plug-compatible runtime) spawns the process in
│   │     its own sandbox.  PointlesSQL receives lifecycle POSTs
│   │     + per-cell output writes over HTTP, becoming the
│   │     registry + store + supervision surface.  Eliminates
│   │     the ipykernel-subprocess executor from the original
│   │     Sprint 13.2 scope and removes the runtime competition
│   │     with Hermes's own cron + code-execution tool.
│   │   * **Demo pivot**: Sprint 13.5 Postgres→Bronze spike is
│   │     replaced by a Drift-Monitor agent — exercises three
│   │     shipped primitives (column stats Sprint 54, alerts +
│   │     CloudEvents Sprint 55, Delta-backed history) in a
│   │     single flow, with no new source connector required.
│   │
│   │   First concrete runtime is Hermes (NousResearch/hermes-
│   │   agent, 114k ⭐, Teknium-stabilised plugin surface since
│   │   May 2026, Paperclip adapter already exists upstream so
│   │   every run auto-surfaces in the Paperclip control room
│   │   once CloudEvents emit).  Runtime stays pluggable —
│   │   OpenShell / OpenClaw / Claude Code remain valid — but
│   │   Hermes is the one to name publicly for distribution
│   │   reach.
│   │
│   ├── Sprint 13.1 — EXPLAIN gate + cost estimator         ✅ done (a9e34f4)
│   │       ``GET /api/sql/explain?sql=...`` returns DuckDB's
│   │       ``EXPLAIN (FORMAT JSON)`` with the existing UC-SELECT
│   │       enforcement on referenced tables.  New
│   │       ``services/sql/cost_estimator.py`` parses the plan,
│   │       heuristic ``max_cardinality × (1 + join_depth)``; above
│   │       the ``cost_gate_threshold_rows`` SQLSettings field
│   │       (default 1e6, env ``POINTLESSQL_SQL_COST_GATE_THRESHOLD_ROWS``)
│   │       the endpoint flags ``needs_approval``.  Estimator handles
│   │       both the synthetic ``estimated_cardinality`` shape and
│   │       DuckDB 1.x's nested
│   │       ``extra_info["Estimated Cardinality"]`` (string).  No UI
│   │       yet — consumers are the Hermes plugin (Sprint 13.7) and
│   │       the run-detail view (Sprint 13.4).  Design captured in
│   │       ``project_phase13_explain_agent_loop.md``.
│   │
│   ├── Sprint 13.2 — ``agent_runs`` table + HTTP registry  ✅
│   │       Alembic 020 adds ``agent_runs`` (id UUID string,
│   │       principal, agent_id, notebook_path, source_snapshot_sha,
│   │       status, cost_est NUMERIC, tables_touched JSON, started_at,
│   │       finished_at, exit_code, approved_by, approved_at,
│   │       denied_reason) and nullable FK column ``agent_run_id``
│   │       on ``notebook_cell_runs`` + ``notebook_outputs``.  New
│   │       routes ``POST /api/agent-runs`` (create),
│   │       ``POST /api/agent-runs/{id}/finish`` (terminate),
│   │       ``GET /api/agent-runs`` (JSON list),
│   │       ``POST /api/agent-runs/{id}/approve`` +
│   │       ``/deny`` (admin gates ready for Sprint 13.4 buttons),
│   │       ``GET /runs`` (newest-first table replacing the 12.12.2
│   │       stub), ``GET /runs/{id}`` (detail view joining outputs +
│   │       cell runs via ``agent_run_id``, reusing the per-cell
│   │       Bootstrap ``.card``-s from 12.12.1).  ``X-Principal``
│   │       header respected from day one (prepares Sprint 13.6).
│   │       **No executor code — Hermes or any other runtime POSTs
│   │       runs in.**
│   │
│   ├── Sprint 13.3 — CloudEvents ``agent_run`` envelope    ✅ done (e4b2a01)
│   │       Extends the Sprint-55 CloudEvents envelope with
│   │       ``pointlessql.agent_run.started`` / ``.completed`` /
│   │       ``.failed`` types (``denied`` intentionally silent —
│   │       execution-outcome vocabulary, not approval decisions;
│   │       ``cell_completed`` waits for the per-cell POST route).
│   │       Webhook dispatch reuses the Sprint-55
│   │       ``dispatch_webhook`` helper for HMAC + retry semantics;
│   │       single-URL config via the new ``AgentRunsSettings`` —
│   │       per-destination filter model lands with Sprint 13.4.
│   │       Integration seam for ``hermes-plugin-pointlessql``,
│   │       Paperclip tickets, and any future subscriber.
│   │
│   ├── Sprint 13.4 — Control-room ``/runs`` + detail       ✅ done (9e3a496)
│   │       Filter bar via the existing Alpine ``listTable``
│   │       (search + six status chips + sortable headers,
│   │       client-side because 200 rows is well within client
│   │       cost).  Adds Cost-est and Tables-touched columns to
│   │       the list.  Detail view gains an approval panel
│   │       (Alpine, only when ``status == needs_approval`` AND
│   │       ``current_user.is_admin``) that POSTs to the
│   │       Sprint-13.2 ``/approve`` and ``/deny`` endpoints, an
│   │       audit-log sidebar joining ``AuditLog`` rows by
│   │       ``target = "agent_run:{id}"``, and a tables-touched
│   │       chip-list with catalog-detail links.  Lineage
│   │       sub-graph stays a static list (real graph deferred
│   │       until a concrete consumer asks).
│   │       Browser-replay deferred to Sprint 13.5's
│   │       Drift-Monitor walkthrough — no dedicated /runs
│   │       playbook exists today.
│   │
│   ├── Sprint 13.5 — Drift-Monitor demo agent              ✅ done (0447ec1)
│   │       *(pivoted from Postgres→Bronze; more direct fit with
│   │       shipped primitives.)*  Demo asset: a ``.py`` notebook
│   │       that reads a published bronze table, computes
│   │       freshness + null-rate (value-drift against Sprint-54
│   │       column stats deferred), appends per-check rows to
│   │       ``main.ops.quality_history``, and emits a Sprint-13.3
│   │       ``.failed`` CloudEvent on threshold breach.  Env-
│   │       driven thresholds.  New playbook
│   │       ``docs/e2e-walkthroughs/agent_drift_monitor.md``
│   │       replays the full flow: register → run → terminate
│   │       → ``/runs`` → detail (conformance + audit + tables-
│   │       touched chips), all attributed to ``X-Principal``.
│   │       No new connector code; the notebook + playbook are
│   │       the deliverable.
│   │
│   ├── Sprint 13.6 — ``X-Principal`` forwarding            ✅ done (c1c9d4e)
│   │       New ``dependencies.effective_principal()`` reads
│   │       ``X-Principal`` first, falls back to the cookie email.
│   │       ``get_uc_client`` honours it for SELECT enforcement;
│   │       audit + query-history rows attribute the email to the
│   │       header value.  PQL constructor gains an explicit
│   │       ``principal=`` kwarg (resolution: client > principal
│   │       arg > ``POINTLESSQL_PRINCIPAL`` env > unforwarded) so
│   │       Hermes plugins can pass principal without mutating
│   │       process env.
│   │
│   ├── Sprint 13.7.0.5 — API-key gate (front-loaded)        ✅ done (a0922bf)
│   │       New ``services/api_keys.py`` parses
│   │       ``POINTLESSQL_API_KEYS`` (newline- or comma-separated
│   │       ``name:secret`` pairs) and constant-time matches the
│   │       ``Authorization: Bearer …`` header.  Auth middleware
│   │       extended to attach a synthetic ``UserInfo`` +
│   │       ``request.state.api_key_name`` on match.  Audit
│   │       helper now writes rows for Bearer-only requests
│   │       (``actor_role="system"``, ``user_email="api_key:<n>"``,
│   │       ``detail.api_key`` marker) so the trail survives the
│   │       cookie-less path.  Cookie wins when both are present.
│   │       New ``docs/auth.md`` carries env format + rotation
│   │       flow + the OIDC-vs-Bearer rationale.  Closes the
│   │       Tier-3 multi-tenant gap from
│   │       ``project_phase13_audit_gaps.md`` ahead of Phase 14.
│   │
│   ├── Sprint 13.7 — Companion ``hermes-plugin-pointlessql`` ✅ done (8a18375 + plugin repo)
│   │       Separate repo at ``~/git/hermes-plugin-pointlessql``,
│   │       analogous to ``NousResearch/hermes-paperclip-adapter``.
│   │       Bearer-token client uses ``POINTLESSQL_API_KEY``
│   │       against the Sprint-13.7.0.5 gate.  Lands as five
│   │       sub-sprints, each shipping one verifiable slice:
│   │
│   │       * **13.7.1 skeleton** — ``hermes_plugin_pointlessql/``
│   │         package with ``register(ctx)`` entry, ``plugin.yaml``,
│   │         ``PointlessClient`` (httpx wrapper),
│   │         ``on_session_start`` / ``on_session_end`` hooks
│   │         POSTing strict ``/api/agent-runs`` lifecycle.  Run
│   │         id is set into ``os.environ`` so subprocess spawns
│   │         inherit it (the Sprint-13.8 audit-trail handoff).
│   │       * **13.7.2 ``pql_query``** — first LLM tool, proves
│   │         ``X-Agent-Run-Id`` (Sprint 13.9) + ``X-Principal``
│   │         (Sprint 13.6) header forwarding through a real
│   │         tool dispatch path.  Result rows trim at
│   │         ``max_rows`` for the LLM transcript.
│   │       * **13.7.3 read-tools batch** — ``pql_list_tables``,
│   │         ``pql_get_table``, ``pql_explain``,
│   │         ``pql_conventions``.  PointlesSQL gains
│   │         ``GET /api/conventions`` (yaml + prose contract)
│   │         and ``GET /api/catalogs/{c}/schemas/{s}/tables/{t}``
│   │         (full UC metadata) so the plugin's tools wrap one
│   │         HTTP endpoint each.
│   │       * **13.7.4 ``post_tool_call`` hook** — fires for any
│   │         ``pql_*`` tool, POSTs to the new
│   │         ``POST /api/agent-runs/{run_id}/tool-call`` route
│   │         which persists into ``agent_run_tool_calls``
│   │         (Alembic 024) and emits a Sprint-13.3 CloudEvent
│   │         ``pointlessql.agent_run.tool_call``.  Tool calls
│   │         are a fourth orthogonal level alongside cells /
│   │         operations / queries — distinct table, distinct
│   │         vocabulary.
│   │       * **13.7.5 env-injection proof** — pytest spawns a
│   │         real Python subprocess with ``subprocess.run`` to
│   │         confirm ``POINTLESSQL_AGENT_RUN_ID`` propagates by
│   │         default (no explicit ``env=`` override, matching
│   │         the Hermes ``terminal_tool`` spawn path).
│   │
│   │       Plugin repo gates green: ruff + pyright (strict) +
│   │       pydoclint clean; 35 unit tests pass.  Cross-repo
│   │       permissions wired via the project-local
│   │       ``.claude/settings.local.json`` (Sprint 13.7.0).
│   │
│   ├── Sprint 13.8 — Forced audit trail                     ✅ done (3f19c3d)
│   │       *(Surfaced 2026-04-24 during the live raw→gold demo —
│   │       see ``project_phase13_audit_gaps.md``.)*  Today
│   │       ``agent_runs.notebook_path`` points at a file the agent
│   │       could edit/delete post-run; ``source_snapshot_sha`` is
│   │       declared but unenforced; PQL primitive calls leave no
│   │       per-operation trace; CloudEvents are fire-and-forget
│   │       (no persistence).  Sprint 13.8 closes all four:
│   │
│   │       * **Alembic 022** adds ``agent_run_sources``
│   │         (id, agent_run_id, source_bytes, source_sha,
│   │         captured_at), ``agent_run_operations`` (id,
│   │         agent_run_id, ordinal, op_name, params_json,
│   │         target_table, input_sha, rows_affected,
│   │         delta_version_before, delta_version_after,
│   │         started_at, finished_at), ``agent_run_events``
│   │         (mirror of Sprint-55 ``alert_events``), plus
│   │         ``runtime_versions JSON`` column on ``agent_runs``.
│   │       * ``POST /api/agent-runs`` becomes strict: **422**
│   │         without ``source`` field AND ``runtime_versions``
│   │         field.  Agent code cannot opt out of the trail.
│   │       * Every PQL primitive (``autoload``, ``merge``,
│   │         ``write_table``, ``sql``) auto-emits an
│   │         ``agent_run_operations`` row when
│   │         ``POINTLESSQL_AGENT_RUN_ID`` env is set.  PQL reads
│   │         ``DeltaTable.version()`` before/after every write
│   │         and hashes the input frame (Arrow-canonical) for
│   │         the ``input_sha`` column.
│   │       * Sprint-13.3 emitter writes to ``agent_run_events``
│   │         **before** ``dispatch_webhook``; dispatcher updates
│   │         ``outcome`` on completion / 4xx / retry-exhausted.
│   │       * Run-detail-view (Sprint 13.4) gains an "Operations"
│   │         section between Metadata and Cells; "Source" tab
│   │         shows the captured ``.py`` verbatim with the SHA.
│   │
│   │       This is the EU-AI-Act-Art.-12-aligned trail; pairs
│   │       naturally with the Phase-15+ Shoreguard Provenance
│   │       Log (``project_shoreguard_provenance_log.md``) which
│   │       layers cryptographic signing on top.
│   │
│   ├── Sprint 13.9 — Run-scoped query history               ✅ done (237890d)
│   │       Today ``query_history`` (Sprint 50) captures every
│   │       ``/api/sql/execute`` row with sql_text +
│   │       referenced_tables + duration + Sprint-13.6 principal
│   │       attribution — but the rows are NOT linked to an
│   │       ``agent_run_id``.  Result: on ``/runs/{id}`` you
│   │       can't answer "which queries did this run execute?".
│   │
│   │       * **Alembic 023** adds nullable ``agent_run_id
│   │         VARCHAR(36)`` column to ``query_history`` + index.
│   │       * ``/api/sql/execute`` reads
│   │         ``POINTLESSQL_AGENT_RUN_ID`` env or new
│   │         ``X-Agent-Run-Id`` header, tags the row.
│   │       * Run-detail-view gains a "Queries" tab listing the
│   │         matching rows.  ``/queries`` page accepts an
│   │         optional ``?agent_run_id=`` filter.
│   │
│   │       Smaller follow-up to 13.8; could ship before, but
│   │       the per-op trace is the higher-value half.
│   │
│   ├── Sprint 13.10 — Hermes-Medallion live-replay fixups    ✅ done (47a7018)
│   │       Closed the four findings from the 2026-04-25 manual
│   │       walkthrough replay.  The Sprint-13.5.5 playbook now
│   │       runs end-to-end without manual workarounds.
│   │
│   │       * ``notebooks/hermes_medallion.py`` — committed the
│   │         live patches verbatim (``source_path=``, dict
│   │         result access, ``pql.table`` → pandas → ``pql.write_table``
│   │         for the gold step) plus a ``pql.merge`` first-run
│   │         bootstrap fallback to ``pql.write_table``.  A
│   │         ``pql.merge(create=True)`` flag is the right
│   │         long-term shape but stays out of scope here.
│   │       * **Lazy metadata-DB init** in ``PQL.__init__`` —
│   │         picked option (b) over the explicit notebook-side
│   │         ``init_db()``.  When a run id is resolved and the
│   │         session factory is unbound, the constructor calls
│   │         ``pointlessql.db.init_db(settings.db.url)``
│   │         (idempotent: Alembic head is a no-op).  Cleaner
│   │         contract for any future agent-authored notebook;
│   │         the interactive PQL path stays untouched.
│   │       * **Tool calls** tab landed in
│   │         ``frontend/templates/pages/run_view.html`` between
│   │         Operations and Queries.  Backend (Alembic 024 +
│   │         POST route + CloudEvent type) shipped in 13.7.4;
│   │         this sprint added ``_load_tool_calls_for_run`` in
│   │         ``api/runs_routes.py`` and the template tab body.
│   │       * **soyuz schema PATCH** — picked option (b)
│   │         doc-only.  ``UpdateSchema`` already rejects
│   │         ``storage_root`` via ``extra="forbid"``; soyuz
│   │         ``docs/reference/api.md`` now carries an explicit
│   │         "set-on-create" admonition next to ``PATCH
│   │         /schemas/{full_name}``.  The medallion walkthrough
│   │         precondition 2 is now an explicit ``curl`` loop
│   │         that sets ``storage_root`` on ``POST /schemas``.
│   │
│   ├── Sprint 13.11.1 — pql_describe_primitive + pql_my_run    ✅ done (722eaa0)
│   │       New ``pointlessql/api/pql_introspect_routes.py``
│   │       hosts ``GET /api/pql/primitives`` returning
│   │       ``{primitives: {<name>: {signature, doc}}}`` for the
│   │       five public PQL methods (``table`` / ``sql`` /
│   │       ``write_table`` / ``merge`` / ``autoload``).  Snapshot
│   │       built once via ``inspect.signature`` + ``inspect.getdoc``.
│   │       New aggregator route ``GET /api/agent-runs/{id}/full``
│   │       lives in ``runs_routes.py`` so it can reuse the
│   │       ``_load_*_for_run`` helpers without a circular import
│   │       back into ``agent_runs_routes``.  Hermes plugin lands
│   │       ``pql_describe_primitive`` + ``pql_my_run`` (commit
│   │       ``hermes-plugin-pointlessql 132d108``).
│   │
│   ├── Sprint 13.11.2 — pql_target_state + pql_recent_failures ✅ done (75ea87e)
│   │       Two highest-ROI tools from the bug analysis.
│   │       ``GET /api/pql/target-state?table=…`` fuses the UC
│   │       ``get_table`` lookup with the Sprint-13.8
│   │       ``agent_run_operations`` history (last-5-writes).
│   │       ``CatalogNotFoundError`` from soyuz maps to
│   │       ``exists=False`` — the ``pql.merge``-on-missing-target
│   │       walkthrough bug becomes a one-call check.
│   │       ``GET /api/agent-runs/operations?target=&errored=&since=``
│   │       backs ``pql_recent_failures`` for "did this fail
│   │       elsewhere?" lookups.  Plugin commit
│   │       ``hermes-plugin-pointlessql 4da60ff``.
│   │
│   ├── Sprint 13.11.3 — pql_lineage                           ✅ done (9fd7a4c)
│   │       ``GET /api/pql/lineage?table=…&depth=N`` wraps
│   │       ``LineageMixin.get_lineage`` which already fans out
│   │       to soyuz's upstream + downstream JSON endpoints
│   │       concurrently.  Depth capped at 5 via FastAPI's
│   │       ``Query(le=5)`` so out-of-range values 422 before
│   │       the soyuz call runs.  Memo-original soyuz cross-repo
│   │       work was dropped — the JSON endpoints already
│   │       existed.  Plugin commit
│   │       ``hermes-plugin-pointlessql de417b8``.
│   │
│   ├── Sprint 13.11.4a — DB-backed API keys + Family-B + summary diff ✅ done (c3b1af8)
│   │       Promoted the Sprint-13.7.0.5 env-var API-key parser
│   │       into a real DB-backed store and landed the Family-B
│   │       Sprint-13.11.4 supervisor routes on top.
│   │
│   │       * **Alembic 025** — ``api_keys`` table with
│   │         ``(name unique, secret_hash indexed, secret_prefix,
│   │         supervisor bool, revoked_at, last_used_at)``.
│   │         SHA-256-hex hashing — API keys are high-entropy so
│   │         a fast hash is enough.
│   │       * ``services.api_keys`` rewritten — ``verify_bearer``
│   │         is DB-backed with a 60s in-memory TTL cache;
│   │         ``bootstrap_from_env`` idempotently spills legacy
│   │         ``POINTLESSQL_API_KEYS`` pairs (now with optional
│   │         ``:supervisor`` third token) into the table at
│   │         startup; admin primitives ``create_api_key``,
│   │         ``revoke_api_key``, ``list_api_keys``,
│   │         ``invalidate_cache``, ``is_supervisor``.
│   │       * Admin CRUD at ``GET/POST /api/admin/api-keys`` +
│   │         revoke route.  Plaintext secret returned exactly
│   │         once at creation; ``audit()`` rows on every
│   │         lifecycle event.
│   │       * ``require_supervisor`` dependency in
│   │         ``api/dependencies.py``: passes for cookie-admins
│   │         and Bearer keys with ``supervisor=True``.  Cookie
│   │         admin > supervisor > working agent.
│   │       * Family-B routes in ``agent_runs_routes.py``: filter
│   │         expansion on ``GET /api/agent-runs``
│   │         (``principal``, ``agent_id``, ``status``,
│   │         ``since``); ``GET /api/agent-runs/{id}/summary``
│   │         (rows touched, errored ops count, Delta-version
│   │         range, tables touched — **no cost_gate_threshold**
│   │         per the anti-gaming memo);
│   │         ``GET /api/agent-runs/diff?a=&b=`` with summary
│   │         differences.
│   │       * ``docs/auth.md`` rewritten for the DB-backed
│   │         primary + env-var bootstrap fallback.
│   │
│   │       Plugin commit ``hermes-plugin-pointlessql ff847e5``
│   │       adds ``PluginConfig.supervisor_mode`` + four new
│   │       Family-B tools registered conditionally via
│   │       ``register_supervisor_tools``.
│   │
│   ├── Sprint 13.11.4b — Detailed op-by-op + tool-call diff   ✅ done (90eefaa)
│   │       Layered the memo-original detail-diff onto the
│   │       Sprint-13.11.4a summary route via two new query
│   │       parameters: ``detail=true`` and ``align=ordinal|content``.
│   │
│   │       * **New** ``pointlessql/services/run_diff.py`` —
│   │         pure-Python alignment + per-pair diff service.
│   │         ``"ordinal"`` mode zips by index (deterministic,
│   │         sensitive to insertions); ``"content"`` mode
│   │         greedy-matches on ``(op_name, target_table)`` /
│   │         ``tool_name`` with minimum ordinal-distance tie
│   │         break.  Per-pair output emits ``op_name_diff`` /
│   │         ``target_table_diff`` / ``rows_affected_diff`` /
│   │         ``delta_version_after_diff`` / ``error_diff`` /
│   │         ``params_diff`` only when those fields actually
│   │         differ.  Tool-call diffs walk top-level
│   │         ``args_json`` keys.  500-slot cap with a
│   │         ``truncated`` marker.
│   │       * Diff route accepts ``detail`` + ``align``; bad
│   │         ``align`` values 422 via ``Query(pattern=…)``.
│   │       * Plugin commit ``hermes-plugin-pointlessql 1184fc5``
│   │         adds ``detail`` + ``align`` to ``pql_diff_runs``.
│   │
│   ├── Sprint 13.11.11 — Plugin write tools                    ✅ done (155cdc8)
│   │       Closed the read-only gap on the agent's tool surface.
│   │       Until this sprint the plugin had ``pql_query`` (read SQL)
│   │       plus the Family-A introspection set, but no way to
│   │       drive a Bronze → Silver → Gold pipeline through Hermes
│   │       — every write needed a side-channel script.  The
│   │       2026-04-26 walkthrough surfaced this when ``gpt-5-mini``
│   │       correctly identified that ``pql.autoload`` was
│   │       unreachable from the chat adapter.
│   │
│   │       Added four ``POST /api/pql/*`` endpoints behind the
│   │       principal-aware ``check_privilege`` gate plus the
│   │       Sprint-13.8 forced audit trail:
│   │
│   │       * ``/autoload`` — file-bytes-to-bronze (mirrors PQL.autoload)
│   │       * ``/write_table`` — runs SELECT, materialises pandas, writes
│   │       * ``/merge`` — runs SELECT, upsert/SCD-2 into existing
│   │       * ``/drop_table`` — admin-only soyuz delete passthrough
│   │
│   │       ``write_table`` + ``merge`` reuse the SQL editor's
│   │       ``prepare_sql`` + UC SELECT enforcement so the SELECT
│   │       side stays consistent with ``/api/sql/execute``.
│   │
│   │       Plugin commit ``hermes-plugin-pointlessql fa31742``
│   │       adds the matching four tools (``pql_autoload`` /
│   │       ``pql_write_table`` / ``pql_merge`` / ``pql_drop_table``)
│   │       with arg_error envelopes, Args/Example descriptions,
│   │       and sibling-tool contrast notes.  16 + 4 = 20 plugin
│   │       tools total.
│
│   Phase 13 close-out — Sprint 13.11 closed the read-loop the
│   2026-04-25 walkthrough proved high-leverage.  Three bugs in
│   that demo all shared the same root cause (no tool to *check
│   state* before *acting*); Sprint 13.11.1-13.11.3 ship the
│   five Family-A working-agent tools and 13.11.4a-b the four
│   Family-B supervisor tools that walk cross-run history.  The
│   ``api_keys`` table promotion (25th Alembic migration) was
│   the load-bearing supporting refactor — supervisor scope
│   needed somewhere durable to live.  Phase 13 is the bridge
│   to Phase 15 (signed Provenance Log): the agent now *reads*
│   the same trail it *writes*, and shoreguard policies can
│   reference both halves.
│
│   Risk recorded for Phase 15+: agents could learn to **game
│   supervision** (chunk writes to stay under cost-gate
│   thresholds).  The summary route deliberately omits
│   ``cost_gate_threshold`` to avoid surfacing what the agent
│   could be tuned against.
│
│   Cells-vs-operations design opinion (recorded 2026-04-24):
│   agent-authored runs should be **plain ``.py``**; per-step
│   supervision granularity comes from Sprint-13.8
│   ``agent_run_operations``, **not** from jupytext ``# %%`` cell
│   markers.  Cells stay for human-authored Workspace notebooks
│   only — there they solve the interactive-exploration problem
│   they were designed for.  Sprint-13.5 Drift-Monitor's
│   markdown cells are OK because the playbook is for
│   human-replay.  See
│   ``feedback_cells_vs_operations_for_agents.md``.
│
│   Non-goals for Phase 13 (pushed to later phases):
│
│   - **Own executor / sandbox runtime** — Hermes, OpenShell,
│     and Claude Code already solve this.  PointlesSQL shipping
│     its own would duplicate mature infrastructure and lock
│     agents to a single runtime.
│   - **`paperclip-adapter-pointlessql`** — Paperclip already
│     adapts Hermes upstream, so agent runs land in Paperclip
│     via Hermes once ``hermes-plugin-pointlessql`` is in place.
│     A direct adapter is only worth building once the indirect
│     path is proven insufficient.
│   - **`openclaw-plugin-pointlessql`** — same reasoning; any
│     agent runtime that grows a Hermes-compatible bridge
│     inherits PointlesSQL access for free.
│   - **OIDC vs API-key decision for shoreguard auth** — defers
│     to the day PointlesSQL has a second multi-tenant consumer.
│     For now ``X-Principal`` + session cookies are sufficient.
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
├── Phase 13.5 — Medallion core + DuckDB-first opinion     ✅ done
│   │
│   │   Phase 13 gives PointlesSQL the *supervision* surface for
│   │   agent-authored work; Phase 13.5 gives it the *opinionated
│   │   primitives* that turn a run into a real Medallion lakehouse
│   │   instead of three ad-hoc Delta tables.  Without this phase
│   │   every agent re-invents bronze/silver/gold semantics and the
│   │   "persistent analytical memory" pitch collapses — agents
│   │   remember *where* they wrote, not *what the layer means*.
│   │
│   │   Strong opinions this phase codifies:
│   │
│   │   * **Medallion as default convention**: bronze = raw fidelity
│   │     + audit columns (``_ingested_at``, ``_source_file``,
│   │     ``_source_system``) + append-only; silver = deduped +
│   │     typed + conformed keys; gold = business facts +
│   │     star-schema-ready + aggregated.  UC tags
│   │     ``layer=bronze|silver|gold`` carry the contract to every
│   │     consumer that reads the catalog.
│   │   * **DuckDB-first for compute**: SQL editor, EXPLAIN gate
│   │     (Sprint 13.1), column stats (Sprint 54), the new merge /
│   │     autoload primitives all run on DuckDB.  ``deltalake``
│   │     Python owns writes (schema evolution, protocol upgrades,
│   │     VACUUM); DuckDB owns compute and read.  Storage stays
│   │     Delta-portable, catalog stays UC-portable, runtime stays
│   │     Hermes/OpenShell/Claude-Code-pluggable — the opinion is
│   │     only at the compute layer, where abstraction costs most
│   │     and benefits a second engine least (no second-engine
│   │     user exists today, per
│   │     ``project_catalog_strategy.md``).
│   │   * **Convention is configurable, not hard-coded**: a repo-
│   │     level ``pointlessql.yaml`` can override layer names,
│   │     audit columns, tag schema — defaults are Medallion
│   │     because that matches Delta naturally and the
│   │     HN/walkthrough demo needs a concrete story.
│   │
│   ├── Sprint 13.5.1 — Conventions YAML + ``pql_conventions()``  ✅ done (03726fe)
│   │       New ``pointlessql.yaml`` parser, layer-semantics
│   │       constants module, ``docs/data-layers.md`` as the
│   │       canonical prose contract, and ADR ``0002-duckdb-first``
│   │       documenting the compute-engine decision.  Exposed to
│   │       agents via the Sprint 13.7 Hermes plugin as a
│   │       ``pql_conventions()`` tool that surfaces the YAML +
│   │       docs as system-prompt context.  Small sprint — no
│   │       runtime code.
│   │
│   ├── Sprint 13.5.2 — ``pql.merge()`` primitive                 ✅ done (29dda17)
│   │       Thin facade over ``deltalake.DeltaTable.merge()``.
│   │       Signature: ``pql.merge(source, target, *, on=[...],
│   │       strategy="upsert"|"scd2")``.  Source: pandas DF,
│   │       PyArrow Table, or UC reference (resolved via
│   │       :meth:`PQL.table`).  Target: must already exist — no
│   │       bootstrap (autoload's job in 13.5.3).  Upsert uses
│   │       ``when_matched_update_all`` + ``when_not_matched_insert_all``;
│   │       SCD-2 is two-phase (close current + append new versions
│   │       with ``_valid_from`` / ``_valid_to`` / ``_is_current``).
│   │       MVP caveat: SCD-2 closes + reopens for every source
│   │       key match — pre-filter source for churn-free history.
│   │       Hermes plugin picks it up as ``pql_merge``.
│   │
│   ├── Sprint 13.5.3 — ``pql.autoload()`` primitive              ✅ done (7b974d0)
│   │       Alembic 021 adds ``autoload_checkpoints`` (source_path,
│   │       file_sha, target_table, ingested_at, rows_ingested) with
│   │       a unique constraint on ``(target_table, file_sha)``.
│   │       DuckDB scans local Volume directories via
│   │       ``read_parquet`` / ``read_csv_auto`` / ``read_json_auto``,
│   │       type-infers, injects audit columns from the Sprint-13.5.1
│   │       conventions, filters already-ingested files by SHA-256,
│   │       appends via ``deltalake.write_deltalake(mode="append")``.
│   │       Auto-registers the target in soyuz-catalog on first
│   │       successful append.  MVP scope: file-level exactly-once
│   │       (per-row dedup + schema-drift deferred to Sprint 13.5.3b).
│   │       HTTP-fetched-Volume support deferred — Volumes treated
│   │       as managed-directories on local FS.  Hermes plugin picks
│   │       it up as ``pql_autoload``.
│   │
│   ├── Sprint 13.5.4 — Conformance check in ``/runs/{id}``       ✅ done (7a6b2c9)
│   │       Passive surface — for each ``tables_touched`` entry the
│   │       run-detail view infers the Medallion layer from the
│   │       schema name and applies the layer-specific contract:
│   │       bronze missing audit columns is ``error``, silver
│   │       without SCD-2 / id-key is ``info``, gold > 50 columns
│   │       is ``info``.  No enforcement; catalog hiccups + missing
│   │       tables silently skipped (passive principle).
│   │       Phase 15+ can convert selected checks into shoreguard
│   │       policies if real demand surfaces.  ``layer_tag_key``
│   │       UC-tag override stays a future hook.
│   │
│   └── Sprint 13.5.5 — Hermes-medallion walkthrough              ✅ done (ba54476)
│           ``docs/e2e-walkthroughs/hermes_medallion.md`` — a real
│           Hermes process (with the Sprint-13.7 plugin loaded)
│           reads
│           ``notebooks/hermes_medallion_data/orders.csv``,
│           runs ``pql.autoload`` to build
│           ``main.bronze.orders_raw``, ``pql.merge`` (upsert
│           strategy) to build ``main.silver.orders``, and a
│           ``pql.sql`` aggregation for
│           ``main.gold.orders_summary``.  The run-detail view
│           shows Source + Operations + Tool calls + Queries +
│           Conformance tabs all populated — the first
│           reproducible end-to-end flow where an agent, not a
│           human, authors a Medallion lakehouse.  Depends on
│           13.5.1-13.5.4, Sprint 13.3 (CloudEvents), and
│           Sprint 13.7 (Hermes plugin).  Playwright-MCP replay
│           commands embedded in the playbook per
│           ``feedback_run_playbook_as_gate.md``.
│
│   Critical path to the "Hermes builds Medallion" demo
│   (cross-phase synthesis, 6 sprints minimum):
│
│   1. **Sprint 13.5.1** — Conventions YAML + ADR 0002-duckdb-first
│      + ``pql_conventions()`` tool.  Sets the direction and is
│      cheap — no runtime code.
│   2. **Sprint 13.5.2** — ``pql.merge()`` primitive.  Unblocks
│      bronze → silver transitions.
│   3. **Sprint 13.5.3** — ``pql.autoload()`` primitive.  Unblocks
│      raw → bronze ingestion; the biggest single piece of work
│      in the path.
│   4. **Sprint 13.3** — CloudEvents ``agent_run`` envelope.
│      Without it ``/runs`` sees the lifecycle but no external
│      subscriber (Paperclip, shoreguard, ops dashboard) does.
│   5. **Sprint 13.7** — ``hermes-plugin-pointlessql`` (external
|      repo).  Registers ``pql_conventions`` / ``pql_autoload`` /
│      ``pql_merge`` / ``pql_sql`` / ``pql_emit_cloudevent`` as
│      Hermes tools so an agent can actually reach the primitives.
│   6. **Sprint 13.5.5** — Hermes-medallion walkthrough, the
│      reproducible "done" moment.
│
│   Non-blocking for the demo (nice-to-have, land when convenient):
│   Sprint 13.1 (EXPLAIN gate — agents run without cost gating),
│   Sprint 13.4 (``/runs`` filter bar — list works without
│   filters), Sprint 13.5.4 (conformance check — passive surface,
│   demo works without it), Sprint 13.5 inside Phase 13
│   (Drift-Monitor — a second demo, not the Medallion flow itself),
│   Sprint 13.6 (``X-Principal`` PQL-session forwarding — header
│   hop to the registry already works today).
│
│   Non-goals for Phase 13.5:
│
│   - **Structured streaming ingest** — Hermes cron pulling files
│     is the MVP; real streaming (Kafka, CDC-from-Postgres,
│     Kinesis) is a separate future phase.
│   - **Schema-registry integration** — JSON / Avro / Protobuf
│     registries come with their own governance story; bronze
│     schema is whatever DuckDB infers from the file.
│   - **Cross-engine abstraction** — ``pql.merge`` / ``pql.autoload``
│     are DuckDB-based by contract.  Polars / Daft / Spark
│     back-ends wait for a concrete second-engine user
│     (``project_catalog_strategy.md`` principle applied to
│     compute).
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
├── Phase 15 — Provenance Log (data + LLM signed audit)    ⏳ queued
│   │
│   │   The compliance-driven moat.  Two complementary
│   │   cryptographically-signed logs that together answer
│   │   "AI-Act-Art.-12-grade autonomous data analysis":
│   │
│   │   - **Data-provenance log** — per-row lineage:
│   │     "output row 47 in main.silver.orders came from input
│   │     row 12 in bronze.csv".  See
│   │     ``project_full_autonomous_audit_critical_path.md`` for
│   │     the design space (per-row lineage column vs. shadow
│   │     lineage tables).  Today operation+source lineage is
│   │     captured; row-level is greenfield.
│   │
│   │   - **LLM-provenance log** — full signed token-trail
│   │     (system prompt, conversation, model output incl.
│   │     reasoning, tool-call args+response, sampling params,
│   │     correlation IDs to sandbox / approval / agent_run_id).
│   │     Lives in shoreguard, not PointlesSQL — see
│   │     ``project_shoreguard_provenance_log.md`` for the full
│   │     design + storage tradeoffs.
│   │
│   │   Bundling both under one phase because they answer the
│   │   same compliance question from two angles ("why did the
│   │   agent decide?" vs "which input row produced this row?")
│   │   and a serious enterprise buyer wants both.  Don't ship
│   │   one without the other.
│   │
│   │   Out-of-scope: model-deprecation replay (storage tier
│   │   tradeoff) ships as a Phase-15 follow-up.
│   │
│   ├── Per-row lineage spike (~3 sprints) — pick column-vs-
│   │   shadow-table approach via prototype on `pql.merge`,
│   │   benchmark storage cost on the medallion fixture
│   ├── Shoreguard Provenance Log MVP (~7 sprints, see memory) —
│   │   L7 proxy interception, OCSF + token-trail schema,
│   │   PII-redaction, cross-plane correlation, Merkle-tree
│   │   signing, forensic replay UI, retention tiering
│   └── Cross-plane query: "show me everything that happened
│       around incident X" surfaces both signed logs joined on
│       agent_run_id + sandbox_id + approval_id
│
├── Phase 16 — Delta-Branching + first-class Rollback      ⏳ queued
│   │
│   │   The agent-trust UX.  Two patterns:
│   │
│   │   - **Branching** is proactive: every agent run gets a
│   │     zero-copy branch, promote-to-main is a shoreguard-
│   │     gated approval, discard is free.  Full design in
│   │     ``project_delta_branching_idea.md``.
│   │   - **Rollback** is reactive: a run already hit main and
│   │     a human at 09:00 wants ONE button to undo it.  Today
│   │     Delta time-travel exists but no first-class primitive
│   │     and no UI.
│   │
│   │   Both are needed.  Don't conflate.  Cascade-aware so a
│   │   silver-table rollback warns when downstream gold tables
│   │   were computed from it.
│   │
│   ├── `pql.rollback(target, before_run=run_id)` primitive —
│   │   resolves Delta version via
│   │   ``agent_run_operations.delta_version_before``, emits its
│   │   own `agent_run_operations` row (rollback IS an operation)
│   ├── `/runs/{id}` "Rollback this run" button (admin-gated,
│   │   shoreguard-approval-required) with cascade preview
│   ├── `pql.branch("name")` API — creates UC schema branch via
│   │   Delta `SHALLOW CLONE`, soyuz metadata extension for
│   │   parent + creation time, automatic cleanup of idle
│   │   branches after N days
│   ├── Promote/discard workflow via shoreguard approval flow —
│   │   "promote experiment-X to main" is a shoreguard policy
│   │   target indistinguishable from any other write approval
│   └── Control-Room UI: list active branches, owners, compute
│       cost, promote/discard per branch
│
├── Some-day — Public launch + external distribution      💤 unscheduled
│   │
│   │   Deliberately queued for the end. Phase 10's retrospective
│   │   spelled it out: building release-engineering against a
│   │   private audience of one generates self-inflicted auth
│   │   friction, and release candidates shipped without
│   │   downstream consumers are wasted motion. Hardening
│   │   (Phase 11) and features (Phase 12, 13, 14) come first.
│   │   When this block runs, it is the moment the stack goes
│   │   from "my project" to "something strangers can try". Until
│   │   then this entry exists as an anchor so the future work
│   │   isn't forgotten — not as a scheduled commitment. No
│   │   target date; promote to a numbered phase the day a real
│   │   external consumer asks.
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
│       positioning is at the time. License decision is locked
│       to Apache 2.0 (UC-compatible, no ethical-use clauses
│       worth the drama; revisit only if something has changed)
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

This file is read first by every new Claude Code session (see
[`CLAUDE.md`](CLAUDE.md)).
