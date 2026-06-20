# Roadmap Archive (Phases 0–99 + Hygiene wave)

This file holds the *full* historical detail of completed phases
that have been compressed in [`ROADMAP.md`](../../ROADMAP.md) for
scannability.  Nothing here is current planning — the active
roadmap (Phase 95–105 composite, Phase 100+, Some-day, Icebox)
lives in `ROADMAP.md`.

The file is append-only: when an active phase eventually closes
and accumulates enough detail that it needs to be rolled out of
`ROADMAP.md`, append it here in chronological order rather than
deleting from history.  Per ADR-0009 D7, phases over the 100 LOC
hard cap in `ROADMAP.md` instead get their own per-phase sidecar
under `docs/internal/phase-NN.md`; this file is reserved for the
*bulk-archived* phases that have left the active roadmap entirely.

The detail below is verbatim from earlier `ROADMAP.md` revisions
(see git log of that file for per-edit attribution).

## How to read this file

- **Phases 0–47**: collapsed pre-W2 inside the single tree-style
  code block that starts below.  Use `Cmd-F "Phase NN"` for direct
  lookup; the giant code block defeats Markdown-anchor-based jump.
- **Hygiene wave H.1–H.7 + Phases 48–99**: added by W2 of the
  Documentation Master-Plan (2026-05-26).  Each phase lives under
  its own `## Phase NN — title` heading further down so the GitHub
  anchor `#phase-NN-<slug>` resolves directly.

## Jump-table — phases bulk-archived in W2 (2026-05-26)

| Phase | Title | Closed |
|------:|-------|--------|
| Hygiene wave H.1–H.7 | (audit + frontend chores) | 2026-05-12 |
| 48 | Primitive-Obsession StrEnum Sweep | 2026-05-07 |
| 49a | Repo-wide Lint-Sweep | 2026-05-07 |
| 49b | Service-File Splits | 2026-05-07 |
| 49c | TableFqn validation type | 2026-05-07 |
| 50 | Native Data-Product support | 2026-05-07 |
| 51 | Git-backed workspaces | 2026-05-07 |
| 52 | Playwright walkthrough completion pass | 2026-05-07 |
| 53 | Full replay sweep + Bootstrap UI overhaul evaluation | 2026-05-07 |
| 54 | UI overhaul implementation (M = Modernize) | 2026-05-08 |
| 55 | UI polish nachzug (post-Phase-54) | 2026-05-08 |
| 56 | UX-polish + bug-hunt + semantic-content review | 2026-05-08 |
| 57 | Phase-56 carve-outs + route-test coverage | 2026-05-08 |
| 58 | Phase-57 carve-out trio | 2026-05-08 |
| 59 | Comprehensive UX-tour quality sweep | 2026-05-08 |
| 61 | dbt tab slim-down + catalog hand-off | 2026-05-09 |
| 62 | MLflow slim-down + catalog hand-off | 2026-05-09 |
| 63 | Writeable SQL Editor (AST-dispatch refactor) | 2026-05-10 |
| 64 | Permission-locked nav-link UX | 2026-05-10 |
| 65 | Lens (read-only Q&A surface, MCP + Browser parallel) | 2026-05-10 |
| 66 | Browser Notebook editor v2 | 2026-05-10 |
| 67 | Notebook Operations (Schedule / Parametrize / Inspect) | 2026-05-12 |
| 68 | Frontend modularization (HTML + JS + CSS hygiene) | 2026-05-12 |
| 69 | Vollständiger Browser-Replay der Plattform | 2026-05-12 |
| 70 | Notebook track (member-access + JS-split) | 2026-05-12 |
| 71 | Data-Product Marketplace polish | 2026-05-12 |
| 72 | Agent-Aware Social Layer | 2026-05-13 |
| 73 | Agent-authored data products | 2026-05-13 |
| 74 | Reviewer-Agent v2 (Active steward delegate) | 2026-05-15 |
| 75 | Verifiable audit export + SIEM sinks | 2026-05-15 |
| 76 | Full Social Network for Data Products | 2026-05-13 |
| 77 | Social-as-Connective-Tissue across the platform | 2026-05-15 |
| 78 | Polish bundle | 2026-05-16 |
| 79 | Code-quality + modularisation bundle | 2026-05-15 |
| 80 | Navigation & UX overhaul | 2026-05-15 |
| 81 | Feed overhaul + help surface + entity ⋯-menu | 2026-05-16 |
| 82–85 | Strategic axes (post-81 horizon) — composite | 2026-05-17 |
| 86 | Modularisierungs- & Dedup-Welle | 2026-05-16 |
| 87 | Restschuld I: config + repo_assets + audit | 2026-05-16 |
| 88 | Restschuld II: SQL/dbt cluster | 2026-05-16 |
| 89 | Restschuld III: endgame | 2026-05-16 |
| 90–92 | Agent-native lakehouse axis (post-Lakebase) — composite | 2026-05-19 |
| 93 | Notebook-Editor UX quick wins | 2026-05-19 |
| 94 | Notebook-Editor UX polish | 2026-05-19 |

Phases 95–106 stayed inside the `ROADMAP.md` Phases 95–105
composite block (Notebook v3 backbone narrative cohesion).  Phase
100+ entries that grew beyond 100 LOC moved to per-phase sidecars
under `docs/internal/phase-NN.md` instead of into this archive.

```text
PointlesSQL — completed phases (full historical detail)
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

│
├── (Phase 12.9 — see ROADMAP.md for active in-progress detail)
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
│   │   [.claude/plans/ich-m-chte-dass-du-luminous-ullman.md](.claude/plans/ich-m-chte-dass-du-luminous-ullman.md).
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
│   │   [.claude/plans/phase-12-11-notebook-unified-anchor.md](.claude/plans/phase-12-11-notebook-unified-anchor.md).
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
│   │   [.claude/plans/siehst-du-mein-repo-zany-horizon.md](.claude/plans/siehst-du-mein-repo-zany-horizon.md).
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

──────────────────────────────────────────────────────────────────
Phases 12.9 + 14–47 — appended 2026-05-12 from ROADMAP.md (verbatim)
──────────────────────────────────────────────────────────────────

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
│   │   [.claude/plans/ich-m-chte-eine-weitere-precious-goose.md](.claude/plans/ich-m-chte-eine-weitere-precious-goose.md).
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

```

The phases above are closed and frozen.  No further edits should
land here unless a follow-up sprint legitimately re-opens scope
(in which case prefer creating a new sub-phase in `ROADMAP.md`).

For the *active* and *queued* roadmap, see
[`ROADMAP.md`](ROADMAP.md).

---

## W2 bulk-archive (2026-05-26): Phases 48–99 + Hygiene wave

Moved out of `ROADMAP.md` in W2 of the Documentation Master-Plan.
Per-phase content below is verbatim from the pre-W2 ROADMAP. Each
phase is anchored as `## Phase NN — title` so cross-links from
`ROADMAP.md` resolve on GitHub-rendered Markdown.

## Hygiene wave H.1-H.7 — (title n/a)

Closed 2026-05-12.

```text
├── Hygiene wave H.1–H.7                                  ✅ closed 2026-05-12 (7 commits, local)
│   │
│   │   Seven autonomous hygiene tracks landed post-Phase-70 to
│   │   unstick the lint+type CI job (red since 2026-05-08) and
│   │   ship additive cleanups.  Plan in
│   │   ``.claude/plans/ja-plane-phase-28-tidy-feather.md``.  Final
│   │   gate state: pytest 2170 passed (0 failed, was 2151 passed
│   │   + 8 failed), ruff clean (was 14 errors), pyright 0 errors
│   │   / 581 warnings (was 28 / 585; budget formally 497 → 585),
│   │   pip-audit 0 vulnerabilities, alembic fresh-DB drift clean.
│   │
│   ├── H.7 — ROADMAP archive-trigger clarification (`5272e79`).
│   │       Rewrote the "When closed phases stack up" rule to make
│   │       it both line-count AND staleness (≥30d closed AND no
│   │       follow-up reference >3mo), with a worked 2026-05-12
│   │       example so future sessions don't auto-archive recent
│   │       load-bearing phases.
│   │
│   ├── H.5 — pip-audit CI gate + 11-CVE bump (`f940eb9`).  New
│   │       ``security-audit`` job runs ``uv run pip-audit
│   │       --skip-editable`` on every PR.  Bumped gitpython
│   │       3.1.49 → 3.1.50, mako 1.3.11 → 1.3.12, mistune 3.2.0 →
│   │       3.2.1, pip 26.0.1 → 26.1.1, python-multipart 0.0.26 →
│   │       0.0.28, urllib3 2.6.3 → 2.7.0 to clear 11 known CVEs.
│   │
│   ├── H.1 — 8 pytest + 14 ruff cleanup (`9aae419`).  Test fixes:
│   │       template-casing drift in ``test_register_page_renders``,
│   │       Sprint-68.3 dropped ``tab-mlflow`` so the help-popover
│   │       wires the "Open in MLflow UI" button instead, marker
│   │       comments on the bare-http + lossy-broad-except sites,
│   │       table-vs-cards drift in query_history (+ short-SQL
│   │       drawer-gate at 700 chars), saved_audit_queries heading
│   │       case.  Ruff fixes: 6 auto-fixed I001, 5 manual E501,
│   │       1 D417 + 1 F401.
│   │
│   ├── H.3 — notebook-walkthrough partial selector refresh
│   │       (`b17432c`).  19 Phase-12.12 route renames bulk-applied
│   │       (``/notebook/editor?path=`` → ``/notebooks/edit/``),
│   │       3 confirmed Phase-67 class renames
│   │       (``pql-nbedit-editor``/``-toolbar``/``-root`` →
│   │       ``pql-notebook-*``).  ~33 per-feature ``pql-nbedit-*``
│   │       selectors remain stale, gated by a ⚠️-banner at each
│   │       file's top pointing replay-drivers to DevTools.
│   │
│   ├── H.4 — Alembic PG-side drift gate (`db61793`).  Added
│   │       ``alembic check`` to the PG CI lane (SQLite had it
│   │       since Phase 30; PG-only didn't).  New
│   │       ``scripts/check-alembic-fresh-drift.sh`` for periodic
│   │       deeper checks (fresh upgrade + schema dump).
│   │
│   ├── H.6 — PG xdist enablement (`cf17824`).  Phase-31.4's
│   │       single-worker carve-out lifted.  ``conftest.py``
│   │       appends ``_<worker_id>`` to ``TEST_DATABASE_URL`` on
│   │       Postgres; CI provisions ``pointlessql_gw{0..3}`` then
│   │       runs ``pytest -n 4 --dist loadfile``.  Target speedup
│   │       ~7min → ~3min.
│   │
│   └── H.2 — Pyright triage 28 → 0 errors, budget 497 → 585
│           (`69e7fe8`).  Cleared by bucket: ``__all__`` +
│           per-import ignores on the 7 underscore-prefixed
│           ``_bootstrap/_loops.py`` coroutines; datetime narrowing
│           in ``lens/sessions.py``; dead hasattr-guard removal in
│           ``main.py``; ``QueryStatus`` enum vs Literal str in
│           ``notebook_kernel_ws.py``; 10 inline ignores on the
│           OpenAI/Anthropic SDK type-strict sites in
│           ``services/lens/*``.  Budget +88 documented as
│           PyArrow / DuckDB-result / OpenLineage stub-bottleneck.
│
```

## Phase 48 — Primitive-Obsession StrEnum Sweep

Closed (date n/a).

```text
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
```

## Phase 49c — TableFqn validation type

Closed (date n/a).

```text
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
```

## Phase 49b — Service-File Splits

Closed (date n/a).

```text
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
```

## Phase 49a — Repo-wide Lint-Sweep

Closed (date n/a).

```text
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
```

## Phase 50 — Native Data-Product support

Closed (date n/a).

```text
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
```

## Phase 51 — Git-backed workspaces

Closed (date n/a).

```text
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
```

## Phase 52 — Playwright walkthrough completion pass

Closed 2026-05-07.

```text
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
```

## Phase 53 — Full replay sweep + Bootstrap UI overhaul evaluation

Closed 2026-05-07.

```text
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
│   │   Sprint C — Synthesis.  ``docs/research/ui-overhaul-proposal.md``
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
```

## Phase 54 — UI overhaul implementation (M = Modernize)

Closed 2026-05-08.

```text
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
```

## Phase 55 — UI polish nachzug (post-Phase-54)

Closed 2026-05-08.

```text
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
```

## Phase 56 — UX-polish + bug-hunt + semantic-content review

Closed 2026-05-08.

```text
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
```

## Phase 57 — Phase-56 carve-outs + route-test coverage

Closed 2026-05-08.

```text
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
```

## Phase 58 — Phase-57 carve-out trio

Closed 2026-05-08.

```text
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
```

## Phase 59 — Comprehensive UX-tour quality sweep

Closed 2026-05-08.

```text
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
```

## Phase 61 — dbt tab slim-down + catalog hand-off

Closed 2026-05-09.

```text
├── Phase 61 — dbt tab slim-down + catalog hand-off         ✅ done 2026-05-09
│   │
│   │   Post-Phase-59 follow-up after a UX exploration: drop
│   │   the embedded dbt-docs iframe (it duplicated dbt-docs's
│   │   own DAG/SQL/test-result UI) and surface the truly
│   │   integrative bits — *which UC tables are dbt-materialised*
│   │   — inside the catalog browsing flow.  Subprocess + reverse-
│   │   proxy stay alive so the new "Open dbt-docs" external-tab
│   │   link still resolves.  Established the pattern: link out
│   │   for tool-internal features, keep cross-tool integrative
│   │   views first-class in PointlesSQL.  MLflow gets the same
│   │   treatment in a follow-up phase when the user confirms.
│   │
│   ├── Sprint 61.A — Slim ``/dbt`` cockpit page              ✅
│   │       Removed "Pipeline docs" tab + iframe from
│   │       ``frontend/templates/pages/dbt.html``.  Default-
│   │       active becomes "Recent runs"; on-load fetch wires up
│   │       so the table populates without a tab click.  Added
│   │       header-row "Open dbt-docs" external-link button
│   │       (visible only when ``dbt_running``).  When dbt-docs
│   │       isn't running the existing setup-instruction alert
│   │       hoists above the tab strip so it stays visible
│   │       regardless of the active tab.
│   │
│   ├── Sprint 61.B — Schema-detail dbt integration           ✅
│   │       New ``frontend/js/pages/dbt_schema_context.js``
│   │       Alpine factory (registered through ``bootstrap.js``)
│   │       fetches ``/api/dbt/manifest`` once + ``/api/dbt/runs?
│   │       limit=5``.  ``frontend/templates/pages/tables.html``
│   │       (the schema-detail page) gains an inline "dbt" badge
│   │       on table rows that match a dbt model (deep-link to
│   │       ``/dbt-docs/#!/model/<unique_id>``) plus a "Recent
│   │       dbt runs" mini-card after the Tables card.  Both
│   │       silently absent when no manifest is loaded.
│   │       Quoting bug caught in browser playbook: outer
│   │       ``x-if=""`` collided with ``|tojson`` double quotes;
│   │       fixed by single-quoting the Alpine attributes.
│   │
│   ├── Sprint 61.C — Catalog-tree dbt badge (sidebar)        ✅
│   │       ``frontend/js/pages/catalog_tree.js`` extended:
│   │       ``dbtRelations: Set`` + ``isDbtTable(c, s, t)``
│   │       helper, populated via ``fetchDbtManifest()`` in
│   │       ``load()``.  ``frontend/templates/components/
│   │       sidebar.html`` table loop renders a tiny "dbt" pill
│   │       inside the tree row when matched.  No badge / no
│   │       error on installs without a manifest.
│   │
│   ├── Sprint 61.D — Table-detail dbt-model card             ✅
│   │       New ``frontend/js/pages/dbt_table_context.js``
│   │       resolves the manifest model for the current table
│   │       (relation_name OR database/schema/name triple, mirror
│   │       of ``_node_relation_name`` server-side).
│   │       ``frontend/templates/pages/table.html`` gains a
│   │       ``<template x-if="dbtModel">`` card after the
│   │       Metadata card showing unique_id, materialization
│   │       badge, test count, and an "Open in dbt-docs" deep
│   │       link.  Existing tabs (Overview / Columns / Lineage
│   │       / etc.) untouched.
│   │
│   └── Sprint 61.E — Phase close                             ✅ this commit
│           ROADMAP.md flipped, CHANGELOG entry, memory file
│           ``project_dbt_handoff_phase.md``.  Browser playbook
│           replay used as gate (``feedback_run_playbook_as_gate``)
│           since 61.B and 61.D both touch ``x-data`` + ``|tojson``.
│
```

## Phase 62 — MLflow slim-down + catalog hand-off

Closed 2026-05-09.

```text
├── Phase 62 — MLflow slim-down + catalog hand-off          ✅ done 2026-05-09
│   │
│   │   Symmetric application of the Phase-61 dbt pattern to
│   │   MLflow.  Both embedded MLflow iframes (the ``/ml`` rail
│   │   page and the model-detail "MLflow" tab) removed; ``/ml``
│   │   becomes a slim cockpit (Recent model registrations +
│   │   Recent training runs + "Open in MLflow UI" external
│   │   link), and the truly integrative pieces — *which UC
│   │   tables are model-prediction destinations, which recent
│   │   registrations live in a given schema* — hoist into the
│   │   catalog browsing flow.  Subprocess + reverse-proxy stay
│   │   alive so the deep-links still resolve.  Phase-61
│   │   "link out for tool-internal, keep cross-tool views
│   │   first-class" pattern is now applied to both major
│   │   external tools.
│   │
│   ├── Sprint 62.F-Server-1 — Reverse-index aggregator route ✅
│   │       New ``aggregate_table_ml_relations()`` in
│   │       ``pointlessql/services/models_lineage.py`` —
│   │       single-query reverse index over
│   │       ``lineage_row_edges.source_model_uri``, grouped by
│   │       ``(target_table, source_model_uri)`` and parsed
│   │       through the ``models:/<full>/<version>`` URI form.
│   │       Exposed via ``GET /api/ml/table-relations?catalog=
│   │       &schema=`` in ``pointlessql/api/models_routes.py``
│   │       — analog of ``/api/dbt/manifest`` for the dbt side.
│   │       Phase-62 reverse index covers only the *scoring*
│   │       direction (``trained_models`` is always ``[]``);
│   │       "trained from this table" attribution would need a
│   │       soyuz cross-reference per request and is deferred.
│   │       One pytest case in
│   │       ``tests/test_models_lineage.py`` covers grouping +
│   │       catalog/schema scoping.
│   │
│   ├── Sprint 62.A — Slim ``/ml`` cockpit page                ✅
│   │       Removed iframe from
│   │       ``frontend/templates/pages/mlflow.html``.  Header
│   │       gains an "Open in MLflow UI" external-link button
│   │       (visible only when ``mlflow_running``).  Body
│   │       becomes two cockpit cards driven by the new
│   │       ``frontend/js/pages/mlflow_cockpit.js`` Alpine
│   │       factory: Recent model registrations (10 latest from
│   │       ``/api/models``) + Recent training runs (5 latest
│   │       agent_runs filtered client-side by
│   │       ``mlflow_run_id``).  When MLflow isn't running the
│   │       existing setup-instruction alert hoists above the
│   │       cockpit so it stays visible.
│   │       ``pointlessql/api/agent_runs_routes/_serializers.py``
│   │       additively exposes ``mlflow_run_id`` so the cockpit
│   │       can filter + render deep-links.
│   │
│   ├── Sprint 62.B — Drop Model-Detail "MLflow" tab           ✅
│   │       Removed the iframe-bearing 4th tab from
│   │       ``frontend/templates/pages/model.html`` (page is
│   │       now 4 tabs: Overview / Versions / Lineage /
│   │       Promotion).  Header gains an "Open in MLflow UI"
│   │       external button deep-linking to the model registry
│   │       page.  Each Versions-table row's ``mlflow_run_id``
│   │       cell becomes a deep-link to ``/mlflow/#/runs/<id>``.
│   │
│   ├── Sprint 62.C — Schema-detail ML integration             ✅
│   │       Existing ``frontend/js/pages/dbt_schema_context.js``
│   │       extended with ML state (``mlAvailable``,
│   │       ``mlModelByTable``, ``mlModels``,
│   │       ``mlModelsLoading``).  ``init()`` fans out two
│   │       parallel fetches (``/api/ml/table-relations``
│   │       scoped to the schema + ``/api/models`` filtered by
│   │       catalog/schema).  ``frontend/templates/pages/
│   │       tables.html`` gains an inline "ml" badge on table-
│   │       name rows that are model-prediction destinations
│   │       (next to the existing dbt badge) plus a "Recent ML
│   │       registrations" mini-card after the dbt card.
│   │       Single-quoted Alpine attributes per BUG-64-01.
│   │
│   ├── Sprint 62.D — Table-detail ML model card               ✅
│   │       New ``frontend/js/pages/ml_table_context.js``
│   │       Alpine factory (registered through ``bootstrap.js``)
│   │       fetches ``/api/ml/table-relations`` scoped to the
│   │       table's catalog + schema and surfaces the matching
│   │       entry's scoring_models list.  ``frontend/templates/
│   │       pages/table.html`` wraps the existing
│   │       ``dbtTableContext`` div in an outer
│   │       ``mlTableContext`` div and renders a
│   │       ``<template x-if="hasMl">`` "ML models" card next
│   │       to the dbt card listing scoring models with edge
│   │       counts + deep-links to ``/mlflow/#/models/<full>/
│   │       versions/<v>``.
│   │
│   ├── Sprint 62.E — Catalog-tree ML pill (sidebar)           ✅
│   │       ``frontend/js/pages/catalog_tree.js`` extended:
│   │       ``mlRelations: Set`` + ``isMlTable(c, s, t)``
│   │       helper, populated via ``fetchMlRelations()`` in
│   │       ``load()``.  ``frontend/templates/components/
│   │       sidebar.html`` table loop wraps both pills in a
│   │       single ``ms-auto`` flex container so dbt + ml
│   │       badges sit side-by-side without layout breakage.
│   │
│   └── Sprint 62.F-Close — Phase close                        ✅ this commit
│           ROADMAP.md flipped, CHANGELOG entry, memory file
│           ``project_dbt_handoff_phase.md`` amended with the
│           Phase-62 follow-through (one pattern, two
│           applications: dbt + MLflow).  Browser playbook
│           replay applies to 62.C and 62.D
│           (``feedback_run_playbook_as_gate``) since both
│           touch ``x-data`` + ``|tojson``; ``/ml`` cockpit
│           verified with seeded inference edges, the
│           catalog-flow surfaces deferred to user-side replay
│           (test account lacks USE CATALOG).
│
```

## Phase 63 — Writeable SQL Editor (AST-dispatch refactor)

Closed 2026-05-10.

```text
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
```

## Phase 64 — Permission-locked nav-link UX

Closed 2026-05-10.

```text
├── Phase 64 — Permission-locked nav-link UX               ✅ done 2026-05-10
│   │
│   │   Admin-only navigation entries (Workspace + Admin in the
│   │   icon-rail, Branches in the catalog sidebar, Workspace +
│   │   Admin in the mobile drawer) used to be hidden via inline
│   │   ``{% if current_user.is_admin %}`` wrappers — a regular
│   │   user couldn't see they existed and therefore didn't know
│   │   what to ask the workspace admin for.  Phase 64 makes the
│   │   entries visible-but-locked: greyed out, lock-icon suffix,
│   │   ``aria-disabled="true"``; click / Enter / Space surface a
│   │   toast naming the missing role.  Backend authorisation is
│   │   unchanged — the routes still 403 if the dead ``href="#"``
│   │   is bypassed.  Single sprint, ~½ day.
│   │
│   ├── Sprint 64.1 — `permission_link` macro + delegated JS ✅
│   │       New ``frontend/templates/_macros/permission_link.html``
│   │       parameterised across the three call-site markups
│   │       (icon-rail's ``data-section`` + label-span,
│   │       sidebar's ``pql-context-panel__link``, nav-links'
│   │       plain-text label).  New
│   │       ``frontend/js/permission_link.js`` registers a single
│   │       document-level click + keyboard listener via
│   │       ``bootstrap.js``, calls
│   │       ``window.pqlToast.info("Requires <role> role —
│   │       contact your workspace admin.")``.  ``.permission-locked``
│   │       CSS class added to ``frontend/css/layout.css``
│   │       (opacity 0.55, ``cursor: not-allowed``).  Five
│   │       inline ``{% if %}`` wrappers replaced by macro calls
│   │       across icon_rail.html (2x), sidebar.html (1x), and
│   │       nav_links.html (2x).  User-menu admin badge stays
│   │       unchanged (status indicator, not a link); admin-page
│   │       internal cards + table-row action buttons explicitly
│   │       out of scope (eigene UX-Kategorie).
│
```

## Phase 65 — Lens (read-only Q&A surface, MCP + Browser parallel)

Closed 2026-05-10.

```text
├── Phase 65 — Lens (read-only Q&A surface, MCP + Browser parallel) ✅ done 2026-05-10
│   │
│   │   New analyst-facing chat-style surface that exposes read-only
│   │   data Q&A over two transports — a browser chat UI at ``/lens``
│   │   (BYO LLM key per workspace, Fernet-encrypted at rest) and an
│   │   MCP (Model Context Protocol) server on stdio for IDE
│   │   consumers (Claude Desktop, Cursor, Hermes-as-MCP-client).
│   │   Both transports share the same Pydantic-typed tool registry
│   │   (provenance, query, list_catalogs/_schemas/_tables,
│   │   describe_table, lineage_neighbors); audit-trail goes through
│   │   ``lens_messages`` + ``query_history.lens_session_id``.
│   │
│   │   New ``analyst`` scope on ``api_keys`` (auditor passes too as
│   │   superset).  Pure read-only enforcement — non-SELECT statements
│   │   raise at the AST validator before EXPLAIN; auto-LIMIT 1000
│   │   on every SELECT; per-query cost cap + per-session budget cap.
│   │   Pinned-answer flow lets analysts bookmark assistant answers
│   │   for stable-URL re-rendering.  Phase 13/39 power-mode write
│   │   tools stay parallel; Lens is the new default analyst surface.
│   │
│   ├── Sprint 65.0 — Foundation (DB + scope + skeleton)         ✅ 2026-05-10
│   │       Alembic ``ff5g7i9k1m3o``: lens_sessions + lens_messages
│   │       + lens_pinned_answers + lens_provider_creds tables;
│   │       ``api_keys.analyst`` boolean.  ``require_analyst()`` dep
│   │       (auditor + admin pass-through).  Service skeleton for
│   │       sessions/messages/provider-creds with Fernet roundtrip
│   │       via the existing ``system_keys`` master key.  10 pytest.
│   ├── Sprint 65.1 — Provenance tool (signature feature)        ✅ 2026-05-10
│   │       Unified ``provenance(table_fqn, row_id?, column?, ...)``
│   │       service folding row-edges (Phase 15) + column-map (15.6)
│   │       + value-changes (15.7) into one ProvenanceTrace shape
│   │       with four resolution modes (table / column / row /
│   │       row+value).  Direct browser route GET /api/lens/provenance.
│   │       12 pytest.
│   ├── Sprint 65.2 — Tool registry (shared backbone)            ✅ 2026-05-10
│   │       Pydantic-typed Lens tool registry + audit-hook wrapper
│   │       persisting every dispatch as a lens_messages tool-row.
│   │       Three provider-specific schema converters (OpenAI,
│   │       Anthropic, MCP).  Six built-in tools: provenance,
│   │       lineage_neighbors, list_catalogs/_schemas/_tables,
│   │       describe_table.  Alembic ``gg6h8j0l2n4p`` adds nullable
│   │       ``query_history.lens_session_id`` FK (batch_alter_table
│   │       for SQLite).  11 pytest.
│   ├── Sprint 65.3 — Auto-LIMIT + cost-gate + query tool         ✅ 2026-05-10
│   │       ``inject_limit()`` in pql.sql_parser auto-injects LIMIT
│   │       (preserves explicit LIMITs, rejects DML/DDL).
│   │       cost_gate.gate_query() composes prepare_sql + inject_limit
│   │       + EXPLAIN cost cap + per-session budget cap, raising
│   │       typed Lens*Error exceptions on each axis.  Wire ``query``
│   │       tool into the registry. 4 new ErrorCode StrEnum members.
│   │       12 pytest.
│   ├── Sprint 65.4 — MCP server (stdio + introspection routes)  ✅ 2026-05-10
│   │       FastMCP-backed Lens server exposes the tool registry
│   │       over stdio (canonical IDE-consumer transport).  HTTP
│   │       introspection routes /mcp/health + /mcp/info for
│   │       client-side connection probing.  ``pointlessql lens-mcp``
│   │       CLI subcommand.  /mcp/* added to PUBLIC_PREFIXES so the
│   │       auth middleware doesn't redirect IDE clients to login.
│   │       SSE FastMCP app shape exists (``build_lens_mcp_sse_app``)
│   │       but is not auto-mounted from the bootstrap (lifespan-time
│   │       mount deferred to follow-up).  Adds ``mcp[cli]`` dep.
│   │       12 pytest.
│   ├── Sprint 65.5 — Browser chat UI + LLM provider adapters    ✅ 2026-05-10
│   │       OpenAI + Anthropic SDK adapters wrapping chat.completions
│   │       / messages tool-calling.  ``run_chat_turn`` drives one
│   │       user→assistant round-trip with bounded tool-call iteration
│   │       (cap 8) + per-turn cost accounting.  /api/lens/sessions
│   │       CRUD, /api/lens/sessions/{id}/messages chat route,
│   │       /lens HTML chat page (Alpine.js, non-streaming JSON).
│   │       /api/admin/lens-providers JSON CRUD with Fernet-encrypted
│   │       upsert + decrypt-test.  Icon-rail entry between SQL and
│   │       Workspace.  Adds openai + anthropic deps.  12 pytest.
│   ├── Sprint 65.6 — Pinned answers + saved questions           ✅ 2026-05-10
│   │       /api/lens/pinned CRUD + /api/lens/pinned/{slug}/view
│   │       standalone HTML page.  Snapshot captures assistant text
│   │       + nearest-preceding query tool's executed SQL +
│   │       result_preview (first 20 rows) so pin survives source-
│   │       session deletion.  Owner+is_shared visibility analog
│   │       SavedQuery.  Slug-collision auto-suffix.  8 pytest.
│   │       Saved-questions surface (re-using SavedQuery for
│   │       question templates) deferred — pinned answers cover
│   │       the primary "find this answer again" use case.
│   ├── Sprint 65.7 — Walkthroughs + plugin tools + docs         ✅ 2026-05-10
│   │       lens-overview.md (browser-mode) + lens-mcp.md
│   │       (hermes-mode) walkthroughs.  hermes-plugin-pointlessql
│   │       gains pql_lens_ask + pql_lens_get_pinned (33→35 tools).
│   │       README playbook count refreshed to 58.
│   └── Sprint 65.8 — Phase close                                 ✅ 2026-05-10
│           ROADMAP + CHANGELOG + memory entry.  Final pytest
│           sweep all-green (77 lens-specific cases on top of
│           the 1782-test baseline).
│
```

## Phase 66 — Browser Notebook editor v2

Closed 2026-05-10.

```text
├── Phase 66 — Browser Notebook editor v2                  ✅ done 2026-05-10
│   │
│   │   The browser notebook editor, deleted in the agent-first
│   │   pivot of 2026-04-24 (commits ``bc2ad07`` + ``ac5207e``),
│   │   returns — rebuilt around the marker grammar
│   │   (``# %%`` jupytext + FNV-1a-64 content_hash), the async
│   │   kernel-bridge runtime (``KernelRegistry`` +
│   │   ``KernelSession``), and the persisted-output replay tables
│   │   that all survived the deletion.  The new surface is a
│   │   cell-by-cell editor at ``/notebooks/edit/{path}`` backed
│   │   by per-cell CodeMirror v6 instances (no vendored bundles
│   │   — esm.sh import-map only) and a JSON-RPC WebSocket bridge
│   │   at ``/ws/notebook/kernel`` (execute / interrupt / restart).
│   │
│   │   Three lessons from the Phase-12.6/12.10/12.12 catastrophe
│   │   are encoded directly in the architecture:
│   │
│   │   1. **One CodeMirror instance per cell.**  No shared mutable
│   │      EditorView; the per-cell ``cellEditor()`` factory carries
│   │      its own closure-scoped state so cells cannot cross-talk.
│   │   2. **Output zone in its own DOM subtree.**  Phase 12 had
│   │      output rendered inline inside the same Codemirror host
│   │      and the cursor-sync bugs were unsolvable.  Output now
│   │      lives in a sibling ``<div>`` rendered as DOM (or a
│   │      sandboxed iframe for ``text/html`` / ``image/svg+xml``).
│   │   3. **No PointlesSQL-specific tokens in the file.**  The
│   │      marker grammar is pure jupytext-Percent; cell identity
│   │      is the FNV-1a-64 content_hash computed at load time.
│   │      Files stay generically VSCode/Vim-editable.
│   │
│   ├── Sprint 66.0 — Foundation: WS route + KernelRegistry +
│   │       Notebook CRUD                                       ✅ 2026-05-10
│   │       Re-introduces the deleted /ws/notebook/kernel route
│   │       around the surviving KernelRegistry + KernelSession.
│   │       JSON-RPC frame shape (execute / interrupt / restart);
│   │       persisted outputs land in notebook_outputs +
│   │       notebook_cell_runs via the existing service helpers.
│   │       Notebook CRUD restored: POST /api/notebooks/create,
│   │       POST /api/notebooks/rename, DELETE /api/notebooks/delete.
│   │       13 pytest.
│   ├── Sprint 66.1 — Frontend skeleton + load route          ✅ 2026-05-10
│   │       GET /api/notebooks/load returns parsed cells +
│   │       persisted outputs.  GET /notebooks/edit/{path:path}
│   │       renders the editor HTML page rooted at the new
│   │       notebookEditor() Alpine factory.  Per-cell CodeMirror
│   │       v6 instances mounted lazily after Alpine's x-for
│   │       paints; no SQL-editor-specific extensions yet.
│   │       7 pytest.
│   ├── Sprint 66.2 — Save round-trip + dirty tracking        ✅ 2026-05-10
│   │       POST /api/notebooks/save serialises cells back to
│   │       the .py file via _doc.save_document; returns
│   │       refreshed FNV-1a-64 content_hashes.  Optional
│   │       expected_mtime triggers 409 conflict detection so
│   │       the browser can reload before overwriting.  Cmd+S
│   │       keymap, save indicator (Unsaved → Saving → Saved),
│   │       per-cell dirty pill.  6 pytest.
│   ├── Sprint 66.3 — Cell execution via WebSocket + outputs  ✅ 2026-05-10
│   │       createKernelClient() — JSON-RPC client for the WS
│   │       route.  renderOutputFrame() — MIME-bundle priority
│   │       renderer (image/png|jpeg → <img>, image/svg+xml +
│   │       text/html → sandboxed iframe, application/json →
│   │       <pre>, text/plain → <pre>, error → red-bordered
│   │       traceback).  notebookEditor.runCell() refreshes
│   │       FNV-1a-64 hash client-side, executes via WS, routes
│   │       iopub frames to the per-cell output zone.  Persisted
│   │       outputs replay on load.  Toolbar: kernel-status pill,
│   │       Interrupt + Restart buttons.  1 integration pytest
│   │       (real ipykernel spawn, end-to-end execute round-trip).
│   ├── Sprint 66.4 — Cell management ops                      ✅ 2026-05-10
│   │       Client-side ops: addCellAbove, addCellBelow,
│   │       addCellAtEnd, deleteCell, moveCellUp, moveCellDown,
│   │       convertCellType.  Per-cell toolbar: insert above /
│   │       below, move up / down, delete, cell-type dropdown.
│   │       Empty-state CTA + bottom "Add cell" footer.
│   │       4 pytest verifying save → load preserves layout
│   │       under each op.
│   ├── Sprint 66.5 — SQL cells (`# %% [sql] df`)              ✅ 2026-05-10
│   │       Alembic ``hh7i9k1m3o5q`` adds query_history.notebook_path
│   │       + notebook_content_hash columns.  build_kernel_wrapper()
│   │       wraps raw SQL with __pql_sql_run(...) (validates
│   │       result_var as identifier, repr()-escapes SQL).
│   │       resolve_approved_tables() runs prepare_sql + per-ref
│   │       privilege check + storage-location lookup.  WS handler
│   │       routes execute frames carrying cell_type='sql' through
│   │       the wrapper, captures (raw_sql, approved_tables) per
│   │       (content_hash, kernel_session_id), and on the matching
│   │       execute_reply writes a query_history row with
│   │       notebook_path + notebook_content_hash.  Browser exposes
│   │       a result_var input on SQL cells.  8 pytest.
│   ├── Sprint 66.6 — Markdown cells with edit/view toggle    ✅ 2026-05-10
│   │       POST /api/notebooks/render-markdown: server-side render
│   │       via the existing markdown-it-py CommonMark renderer
│   │       (html=False so embedded <script> / <iframe> escapes at
│   │       parse time).  Markdown cells default to view-mode after
│   │       load; click on the rendered HTML or Enter (focused)
│   │       enters edit-mode; Shift+Enter or Esc renders + returns
│   │       to view-mode.  5 pytest.
│   ├── Sprint 66.7 — Keyboard model + autosave + history      ✅ 2026-05-10
│   │       Shift+Enter (run + focus next; insert if last),
│   │       Ctrl/Cmd+Enter (run + stay), Esc on a markdown cell
│   │       exits edit-mode.  5-second debounced autosave on any
│   │       cell-source change.  GET /api/notebooks/cell-history
│   │       returns the last N NotebookCellRunSource rows for
│   │       (path, content_hash); per-cell toolbar history-icon
│   │       button toggles an inline popover with status pill +
│   │       execution_count + started_at.  4 pytest.
│   └── Sprint 66.8 — Phase close                              ✅ 2026-05-10
│           ROADMAP + CHANGELOG + memory entry +
│           docs/e2e-walkthroughs/notebook-overview.md (Browser
│           Mode).  Walkthrough README playbook count refreshed
│           to 59.  Final pytest sweep all-green.
│
```

## Phase 67 — Notebook Operations (Schedule / Parametrize / Inspect)

Closed 2026-05-12.

```text
├── Phase 67 — Notebook Operations (Schedule / Parametrize / Inspect)  ✅ done 2026-05-12
│   │
│   │   Phase 66 shipped the live cell-by-cell editor; Phase 67
│   │   closes the DBX-Notebook gap by wiring four surfaces on top
│   │   of the existing scheduler / papermill / kernel-session
│   │   stack — without duplicating any of it.  The papermill
│   │   executor + cron loop + Job/JobRun tables + jobs.html page
│   │   were already production; Phase 67 is the editor-side
│   │   verkabelung that finally lets a user schedule a notebook
│   │   without leaving the editor.
│   │
│   │   The four shipped surfaces:
│   │
│   │   1. **Schedule-from-Notebook** — Toolbar "Schedule" button →
│   │      modal pre-built from ``papermill.inspect_notebook`` →
│   │      POST /api/jobs with kind="papermill"; new job lands in
│   │      /jobs + writes a notebook_job_link row for editor look-up.
│   │   2. **Parametrized runs** — Mark a code cell as papermill
│   │      ``parameters`` via the jupytext-canonical
│   │      ``tags=["parameters"]`` marker (round-trip-stable through
│   │      load → save → reopen, byte-identical).  Schedule + Run-
│   │      once modals render a typed override form per declared
│   │      parameter.
│   │   3. **Run-Once-with-Parameters** — Editor "Run as job" creates
│   │      a paused permanent job + fires execute_run as a fire-and-
│   │      forget asyncio task; browser polls /api/jobs/{id}/runs
│   │      (new listing endpoint) until terminal.  Keeps a full
│   │      audit-trail row.
│   │   4. **Variable Inspector** — Live side-pane refreshes after
│   │      every cell run.  Kernel bootstrap learns
│   │      ``__pql_inspect__()`` + ``__pql_inspect_detail__()`` that
│   │      emit a custom ``application/x-pql-vars+json`` MIME bundle
│   │      the WS pump routes to a dedicated ``variable_snapshot``
│   │      notify (NOT persisted to notebook_outputs — transient).
│   │      Click a variable → detail view with truncated repr +
│   │      DataFrame ``_repr_html_()`` head when applicable.
│   │
│   │   Anchor-decisions (preserved from the plan):
│   │
│   │   - **No new job-runner**.  papermill stays the single headless
│   │     execution path; ``_papermill_executor`` already converts
│   │     ``.py`` → ``.ipynb`` on-the-fly via jupytext so the
│   │     canonical ``.py``-with-jupytext-markers invariant holds.
│   │   - **Cell tags = metadata**.  ``compute_content_hash`` ignores
│   │     ``cell.tags`` so toggling the parameters flag does not
│   │     rewrite cell identity (kept run history stable).
│   │   - **One link table, opportunistic writes**.  Phase 67.4's
│   │     ``notebook_job_link`` table is a derived index; ``Job.config``
│   │     stays canonical so a stale link row at worst shows a phantom
│   │     entry in the editor panel.
│   │   - **Job-output bridge re-uses notebook_outputs**.  Papermill
│   │     output cells land at ``kernel_session_id = "job:<run_id>"``
│   │     so both the editor reload-replay and a future "view job
│   │     outputs" tab share one render path.
│   │
│   ├── Sprint 67.0 — Marker grammar: `tags=[...]` parsing       ✅ 2026-05-12
│   │       ``_MARKER_RE`` extended with optional
│   │       ``tags=["a","b"]`` suffix; ``NotebookCell.tags`` field
│   │       added (frozen tuple, default ``()``);
│   │       ``_scan_marker_extensions`` returns
│   │       ``(tag, result_var, tags)`` triples.  Save path
│   │       ``_rewrite_cell_markers`` emits the canonical marker
│   │       line for every cell whose marker needs PointlesSQL-side
│   │       polish (SQL ``result_var`` and/or ``tags=[…]``).
│   │       ``compute_content_hash`` is **unchanged** — tags are
│   │       metadata, not source.  10 pytest.
│   ├── Sprint 67.1 — Inspect endpoint hardening + plumbing     ✅ 2026-05-12
│   │       ``GET /api/notebooks/inspect`` learns ``.py`` ⇒
│   │       jupytext + nbformat-tempfile convert ⇒
│   │       ``papermill.inspect_notebook``; canonical
│   │       ``kernelspec`` stamped so papermill's Jinja default
│   │       rewrites succeed.  Browser ``loadParameters()`` cached
│   │       in Alpine state + tiny "N params" toolbar badge so the
│   │       user knows the notebook has overridable inputs.  5
│   │       pytest.
│   ├── Sprint 67.2 — Schedule-from-Notebook modal              ✅ 2026-05-12
│   │       Editor toolbar gains "Schedule" + "Run as job" +
│   │       "Jobs" + "Variables" buttons.  Schedule modal
│   │       (``:class="{'d-block': flag}"`` per the feedback memory
│   │       on Bootstrap modal + Alpine x-show) submits to the
│   │       existing ``POST /api/jobs`` with kind="papermill" +
│   │       config={notebook_path, parameters} + cron 5-field
│   │       client-side check.  Uses existing ``pqlHumanizeCron``
│   │       for the human-readable hint.  Zero backend change.
│   ├── Sprint 67.3 — Run-Once-with-Parameters                  ✅ 2026-05-12
│   │       New ``POST /api/notebooks/run-once`` creates a paused
│   │       Job + fires ``execute_run`` via ``asyncio.create_task``;
│   │       returns ``{job_id, job_run_id, status: "started"}``.
│   │       New ``GET /api/jobs/{id}/runs`` listing endpoint feeds
│   │       the browser-side polling loop (exponential backoff
│   │       0.5 → 5 s, 240-iter cap).  Audit-row written via
│   │       ``audit("run_once_notebook")``.  9 pytest (5 run-once +
│   │       4 list-runs).
│   ├── Sprint 67.4 — Notebook-Jobs panel + link table          ✅ 2026-05-12
│   │       Alembic ``i9j1k3m5o7q9_notebook_job_link.py`` adds
│   │       ``notebook_job_link(id, workspace_id, notebook_path,
│   │       job_id, created_at)`` + three indexes (notebook_path,
│   │       (workspace_id, notebook_path), job_id).  POST /api/jobs
│   │       + POST /api/notebooks/run-once write a link row
│   │       opportunistically when kind="papermill".  New
│   │       ``GET /api/notebooks/jobs?path=…`` returns
│   │       ``{scheduled_jobs, recent_runs}`` joined through the
│   │       link.  Collapsible "Jobs ▾" toolbar button +
│   │       in-editor panel listing scheduled jobs + last 10 runs.
│   │       7 pytest.
│   ├── Sprint 67.5 — Variable Inspector (live + auto-refresh)  ✅ 2026-05-12
│   │       Kernel bootstrap ``_NOTEBOOK_BOOTSTRAP_CODE`` extended
│   │       with ``__pql_inspect__()`` + ``__pql_inspect_detail__()``
│   │       (excludes dunder / modules / plain callables; classes +
│   │       DataFrames + sequences kept with shape/len hints).
│   │       WS pump ``_handle_kernel_message`` intercepts
│   │       ``application/x-pql-vars+json`` and
│   │       ``application/x-pql-vardetail+json`` and routes them as
│   │       dedicated ``variable_snapshot`` / ``variable_detail``
│   │       notify frames — NOT persisted in ``notebook_outputs``.
│   │       After every ``execute_reply`` the editor sends a silent
│   │       ``execute("__pql_inspect__()")`` via the existing
│   │       JSON-RPC client; click on a variable triggers a detail
│   │       fetch with HTML head when the variable has
│   │       ``_repr_html_()``.  11 pytest (bootstrap-eval style with
│   │       monkey-patched ``IPython.display``).
│   ├── Sprint 67.6 — Job-Run-Output ↔ notebook_outputs bridge  ✅ 2026-05-12
│   │       ``_papermill_executor`` post-execute path now reads the
│   │       result ``.ipynb`` via nbformat, computes
│   │       ``compute_content_hash`` per cell-source, and persists
│   │       every output row to ``notebook_outputs`` with
│   │       ``kernel_session_id = "job:<run_id>"``.  Idempotent
│   │       (clear-then-append) so retries replace prior rows
│   │       cleanly.  5 pytest (stream + execute_result + idempotent
│   │       + skip-markdown + missing-file no-op +
│   │       content-hash-lookup).
│   ├── Sprint 67.7 — Param-cell UI-Branding                    ✅ 2026-05-12
│   │       ``cellLabel(cell)`` renders "PARAMS" / "SQL · PARAMS" /
│   │       "Markdown · PARAMS" when the cell carries the
│   │       ``parameters`` tag.  Per-cell toolbar gains a
│   │       "Mark/Unmark as parameters" menu entry that toggles
│   │       ``cell.tags`` + flips ``_dirty`` + triggers the
│   │       autosave debouncer.  ``GET /api/notebooks/load`` +
│   │       ``POST /api/notebooks/save`` carry the ``tags`` list
│   │       in both directions.  3 pytest (mark + unmark +
│   │       end-to-end inspect-sees-tag).
│   └── Sprint 67.8 — Phase close                              ✅ 2026-05-12
│           ROADMAP + CHANGELOG + memory entry +
│           docs/e2e-walkthroughs/notebook-jobs.md + docs/features/
│           notebook-jobs.md.  Walkthrough README playbook count
│           refreshed to 60.  Final pytest sweep + ruff + pydoclint
│           + alembic check all-green.  Pyright budget: pre-existing
│           reportLiteralAssignment error at notebook_kernel_ws:361
│           (unrelated to Phase 67) carried forward.
│
```

## Phase 68 — Frontend modularization (HTML + JS + CSS hygiene)

Closed 2026-05-12.

```text
├── Phase 68 — Frontend modularization (HTML + JS + CSS hygiene)  ✅ done 2026-05-12
│   │
│   │   Frontend grew over 50+ sprints and accumulated two structural
│   │   schwächen that made LLM-context lookups more expensive than
│   │   needed: 6 templates >500 LOC and two parallel partial
│   │   conventions side-by-side (top-level ``partials/`` vs
│   │   page-scoped ``pages/_partials/``).  Phase 68 applies the
│   │   Phase-38 split-into-partials playbook to the remaining large
│   │   templates and unifies the partial convention.  No behaviour
│   │   change — pure structural reorganization.
│   │
│   │   Anchor-decisions:
│   │
│   │   - **``notebook_editor.js`` (939 LOC) stays single-file.**  8
│   │     real feature seams but Alpine state tight-coupled across
│   │     them.  Defer split until a feature delivers a clean anchor.
│   │   - **Nested per-page partial layout** —
│   │     ``pages/_partials/<page>/<sub>.html``.  Verworfen: flat-
│   │     with-prefix.  Grep on one folder shows all sub-views of a
│   │     page; scales as more pages get split.
│   │
│   ├── Sprint 68.0 — Partials-Konvention vereinheitlichen     ✅ 2026-05-12
│   │       12 of 13 top-level partials waren single-page (alle
│   │       ``_run_*.html`` und ``_output_*.html``) — moved to
│   │       ``pages/_partials/run_view/`` und
│   │       ``pages/_partials/notebook/output/``.  Top-level
│   │       ``partials/`` behält nur 2 echt-cross-page Files
│   │       (``_cdf_change_type_pill.html``, ``_query_row.html``).
│   │       ~25 ``{% include %}`` Pfade aktualisiert.
│   ├── Sprint 68.1 — ``pages/table.html`` splitten            ✅ 2026-05-12
│   │       786 → 228 LOC.  7 Tab-Partials unter
│   │       ``pages/_partials/table/``: overview.html (~190),
│   │       preview.html (~100), columns.html (~160),
│   │       lineage.html (~10), tags.html (~7),
│   │       permissions.html (~12), cdf_events.html (~85).
│   ├── Sprint 68.2 — ``run_view/operations`` splitten         ✅ 2026-05-12
│   │       ``tab_operations.html`` 726 → 59 LOC.  5 Sub-Tab-
│   │       Partials unter
│   │       ``pages/_partials/run_view/operations/``:
│   │       operations.html (~195), rejects.html (~60),
│   │       queries.html (~70), rewrites.html (~89),
│   │       uc_mutations.html (~258).
│   ├── Sprint 68.3 — ``pages/model.html`` splitten            ✅ 2026-05-12
│   │       589 → 209 LOC.  4 Tab-Partials unter
│   │       ``pages/_partials/model/``: overview.html (~62),
│   │       versions.html (~104), lineage.html (~63),
│   │       promotion.html (~155).
│   ├── Sprint 68.4 — Federation-JS in ``js/pages/federation/`` ✅ 2026-05-12
│   │       3 admin-only JS-Files (``federation_catalogs.js``,
│   │       ``_connections.js``, ``_credentials.js``) per ``git mv``
│   │       in ``js/pages/federation/`` einziehen.
│   │       ``bootstrap.js``-Importe angepasst; Window-attached
│   │       Namen unverändert, kein Template-Change.
│   ├── Sprint 68.5 — sql_editor inline CSS extrahieren        ✅ 2026-05-12
│   │       ``pages/sql_editor.html`` 543 → 397 LOC.  146 LOC
│   │       inline ``<style>`` → ``frontend/css/components/
│   │       sql_editor.css`` (Operator-Badges + Layout-Fixes);
│   │       ``style.css`` @import in alphabetic cascade-position.
│   ├── Sprint 68.6 — ``notebook.css`` lazy-load               ✅ 2026-05-12
│   │       292 LOC CSS aus globalem ``style.css`` @import-cascade
│   │       entfernt, stattdessen via ``{% block extra_css %}``
│   │       in ``pages/notebook_editor.html`` lazy geladen.
│   │       Notebook-only Selektoren erscheinen nicht mehr im
│   │       LLM-Context jeder Nicht-Notebook-Page.
│   └── Sprint 68.7 — Conventions doc + Phase-Close            ✅ 2026-05-12
│           Neue ``docs/development/frontend-conventions.md``
│           (in mkdocs nav).  ``frontend/js/README.md`` um
│           Folder-Layout-Section ergänzt.  ROADMAP +
│           CHANGELOG + Memory.  Pytest sweep grün auf den
│           berührten Surfaces (table-detail, run-view,
│           model-detail, sql-editor, notebook-editor,
│           federation); Browser-Replay als nächste Session-
│           Aufgabe ausstehend.
│
```

## Phase 69 — Vollständiger Browser-Replay der Plattform

Closed 2026-05-12.

```text
├── Phase 69 — Vollständiger Browser-Replay der Plattform     ✅ done 2026-05-12
│   │
│   │   Browser-replay sweep of every UI surface across multiple
│   │   user roles + config flips, primarily to verify Phase 68's
│   │   structural HTML/CSS/JS reorganization landed cleanly.  All
│   │   work on the ``docker/docker-compose.e2e.yml`` stack with the
│   │   ``scripts/seed-e2e.py`` baseline.  ~20 wave-shaped passes;
│   │   3 bugs found, 1 fixed in-band (BUG-69-03), 1 cascade
│   │   (BUG-69-02), 1 deploy-hygiene (BUG-69-01) documented.
│   │
│   │   Phase-68 surfaces re-verified end-to-end:
│   │
│   │   - **68.1 / table.html** — all 7 tab partials render
│   │     (Overview / Preview / Columns / Lineage / Tags /
│   │     Permissions + conditional CDF Events tab gated on
│   │     ``{% if cdf_subscription %}``).
│   │   - **68.0+68.2 / run_view operations** — all 4 top tabs
│   │     (Overview / Operations / Lineage / Audit) plus all 5
│   │     Operations sub-tabs (Operations / Rejects / Queries /
│   │     Rewrites / UC mutations) render with 0 console errors.
│   │   - **68.3 / model.html** — all 4 tab partials render
│   │     (Overview / Versions / Lineage / Promotion) on a stub
│   │     ``demo_ml.silver.churn`` model created via soyuz UC API.
│   │   - **68.4 / federation JS move** — all 3 modals (new
│   │     Connection / Credential / Foreign Catalog) open
│   │     cleanly after fixing BUG-69-03 (broken relative
│   │     imports).
│   │   - **68.5 / sql_editor.css extract** — confirmed
│   │     ``/static/css/components/sql_editor.css`` 200 + cascade
│   │     ``@import`` in ``style.css``.
│   │   - **68.6 / notebook.css lazy-load** — confirmed
│   │     ``notebook.css`` loads only on
│   │     ``/notebooks/edit/<path>`` and is absent on all 6
│   │     non-notebook surfaces sampled.
│   │
│   │   Non-Phase-68 surfaces smoke-tested with 0 errors:
│   │   ``/`` / ``/runs`` / ``/sql`` / ``/notebooks/workspace`` /
│   │   ``/models`` / ``/branches`` / ``/audit/inbox`` /
│   │   ``/audit/by-table`` / ``/volumes`` / ``/alerts`` /
│   │   ``/dashboards`` / ``/data-products`` / ``/jobs`` /
│   │   ``/dbt`` + 9 ``/admin/*`` surfaces (CDF subscriptions
│   │   sits at ``/admin/cdf-subscriptions``, not
│   │   ``/admin/cdf-tail`` as the plan-doc had it).
│   │
│   │   Persona + config matrix verified:
│   │
│   │   - admin@pql.test (full privileges) — every surface.
│   │   - flo@pql.test (member) — 9 admin URLs + 3 federation
│   │     URLs all return 403; ``/sql`` + ``/runs`` accessible.
│   │   - Bearer-key (supervisor + auditor + lineage_inbound)
│   │     via ``Authorization: Bearer <secret>`` — audit
│   │     aggregates returned 200 / 422 (auth pass, params
│   │     incomplete).  Key generated via ``/admin/api-keys``
│   │     and revoked at session end.
│   │   - OIDC config flip via ``POINTLESSQL_OIDC_*`` env +
│   │     ``mock-oidc`` sidecar — ``/auth/login`` gains
│   │     "Sign in with SSO" button as the visible marker.
│   │
│   ├── BUG-69-01 — asset_version not bumped on Phase 68
│   │       rebuild → Firefox ES-module cache served stale
│   │       bootstrap.js.  Deploy-hygiene fix: bump version
│   │       string whenever ``frontend/`` changes.  Phase-69
│   │       replay temporarily bumped to 0.1.0rc5; reverted
│   │       at close.  Documented in
│   │       ``docs/e2e-walkthroughs/federation.md``.
│   ├── BUG-69-02 — command-palette backdrop intercepted
│   │       clicks after BUG-69-01 broke Alpine init.  Pure
│   │       cascade; resolves automatically once asset_version
│   │       bump unblocks module imports.
│   └── BUG-69-03 — fixed in this commit-range.
│           ``frontend/js/pages/federation/{connections,
│           credentials,catalogs}.js`` had stale
│           ``import './editor_base.js'`` after Phase 68.4's
│           ``git mv`` to ``js/pages/federation/`` — now
│           ``../../editor_base.js``.  Without this fix, every
│           page-load fired a 404 + cascaded into BUG-69-02.
│
```

## Phase 70 — Notebook track (member-access + JS-split)

Closed 2026-05-12.

```text
├── Phase 70 — Notebook track (member-access + JS-split)        ✅ done 2026-05-12
│   │
│   │   Two thematically linked notebook concerns bundled into
│   │   one phase: drop the Phase-12.12 admin-only restriction
│   │   on the notebook editor + defensive split of the 939-LOC
│   │   ``notebook_editor.js`` monolith.  Plan in
│   │   ``.claude/plans/ja-plane-phase-28-tidy-feather.md``.
│   │
│   ├── 70.1 — ``require_user`` dep + 11+2 notebook routes
│   │       flipped from ``require_admin`` to ``require_user``
│   │       (+ WebSocket ``_user_can_use_editor`` broadened to
│   │       accept any authenticated user).  Adds a new sibling
│   │       to ``require_admin`` / ``require_supervisor`` etc.
│   │       in ``api/dependencies.py``; explicit ``require_user``
│   │       call sites keep the auth intent grep-able instead of
│   │       silently dropping the gate.
│   ├── 70.2 — ``permission_link`` macro calls for the Workspace
│   │       icon-rail (``icon_rail.html:62``) and nav-links
│   │       entry (``nav_links.html:51``) replaced with direct
│   │       ``<a href>`` tags.  Branches (sidebar.html:36) and
│   │       Admin (icon_rail.html:147 / nav_links.html:86)
│   │       stay permission-gated.
│   ├── 70.3 — Five non-admin-forbidden notebook tests flipped
│   │       from ``assert status_code == 403`` to expect 200
│   │       + JSON-shape assertions (tree, workspace page, load,
│   │       editor page, save).
│   ├── 70.4 — Extract ``jobs_orchestration.js`` (190 LOC):
│   │       Schedule + Run-Once modals, Notebook-Jobs panel,
│   │       ``_pollJobRun``.  Plugin-mixin pattern follows
│   │       Phase-68.2 run_view split — ``installXxx(state, deps)``
│   │       mutates the shared Alpine state.  Coordinator
│   │       drops 939 → 755 LOC.
│   ├── 70.5 — Extract ``kernel_execution.js`` (208 LOC):
│   │       WS kernel client, cell-run lifecycle (run / interrupt
│   │       / restart), Variable Inspector helpers.  Coordinator
│   │       drops 755 → 572 LOC.
│   ├── 70.6 — Extract ``cell_operations.js`` (146 LOC):
│   │       add/delete/move/convert cells + per-cell editor
│   │       lifecycle.  Coordinator drops 572 → 446 LOC.
│   ├── 70.7 — Two-in-one: extract ``markdown_output.js``
│   │       (122 LOC, output renderer + markdown edit/view +
│   │       cell-editor mount) and ``persistence.js`` (144 LOC,
│   │       save/autosave/keymap + params-tag toggle + cell
│   │       run-history).  Coordinator drops 446 → 190 LOC and
│   │       now holds only the state defaults, init/destroy,
│   │       and five ``install*()`` calls.
│   ├── 70.8 — Asset-version bump (``0.1.0rc3`` → ``0.1.0rc4``)
│   │       — seven JS files + two templates touched, so the
│   │       ``?v=`` cache-buster has to flip (see
│   │       ``feedback_asset_version_bump.md``).  Seven
│   │       additional non-admin notebook tests flipped (inspect,
│   │       jobs panel, run-once, render-markdown, cell-history,
│   │       crud-create) + the ``_user_can_use_editor`` WS gate
│   │       test removed (no longer reachable).  Pytest grün on
│   │       all notebook surfaces (22+ tests); 7 pre-existing
│   │       failures unrelated to Phase 70 left untouched.
│   └── 70.9 — Browser-replay carry-over (2026-05-12, autonomous
│           Playwright-MCP session).  Sprint 70.8's verification
│           gate was skipped in auto-mode; replayed against the
│           ``docker/docker-compose.e2e.yml`` stack with both admin
│           (``admin@pql.test``) and member (``flo@pql.test``)
│           personas.  Green on both: all 92 Alpine state keys
│           present (5 install functions wire correctly), all 9
│           notebook JS modules load 200, all six distinct
│           ``/api/notebooks/*`` route classes return 200 for the
│           member persona, ``/ws/notebook/kernel`` upgrades to
│           101 without the 4403 close-code, ``runCell`` +
│           ``addCellAtEnd`` + ``save`` + ``toggleInspector`` +
│           ``enterMarkdownEdit`` round-trip end-to-end.
│           Cross-page CSS regression gate (Sprint 68.6) holds:
│           ``notebook.css`` absent on ``/runs``, ``/sql``,
│           ``/admin``.  0 ``BUG-70`` surfaced, 0 console errors
│           (only pre-existing font-preload warning).  No new
│           fix-commits required; no asset-bump needed.
│
```

## Phase 71 — Data-Product Marketplace polish

Closed 2026-05-12.

```text
├── Phase 71 — Data-Product Marketplace polish              ✅ done 2026-05-12
│   │
│   │   Catch-up to enterprise-catalog collaboration table stakes
│   │   (Atlan, Collibra, Alation, Snowflake Marketplace).
│   │   Phase 50 already gives us the Data-Product contracts +
│   │   freshness + dependency-graph; Phase 71 layers the social
│   │   affordances analysts already expect from a modern catalog
│   │   so PointlesSQL doesn't read as "no comments / no follow /
│   │   no reviews" against the incumbents at trial time.
│   │
│   │   Scope is deliberately narrowed to well-trodden patterns
│   │   (comment threads, star ratings + reviews, follow + email
│   │   webhook, wiki README, browse-page rework).  The
│   │   AI-native differentiation lives in Phase 72; the two
│   │   phases are independent and can land in either order.
│   │
│   │   Cross-cutting picks (TBD at plan time):
│   │   - threaded vs flat comments (recommend threaded with a
│   │     2-level cap to avoid Reddit-depth UX);
│   │   - markdown rendering reuses the existing `markdown-it`
│   │     bundle (Phases 12.5/56);
│   │   - rating widget = Bootstrap 5-star; one review per user
│   │     per DP (upsert);
│   │   - notifications fan out via the Phase-20 audit-stream
│   │     forwarder (webhook + email sinks) — no new pub-sub
│   │     plumbing.
│   │
│   ├── Sprint 71.1 — Comment threads per data product         ✅ done 2026-05-12
│   │   ├── New model: `DataProductComment` (id, dp_slug,
│   │   │   parent_comment_id, author_user_id, body_md,
│   │   │   created_at, deleted_at, workspace_id) + Alembic.
│   │   ├── Soft-delete via `deleted_at` so audit-trail integrity
│   │   │   holds; threading via parent_comment_id capped at
│   │   │   depth 2.
│   │   ├── `/api/data-products/{slug}/comments` GET (list) +
│   │   │   POST (create) + DELETE (soft, author or
│   │   │   workspace admin).
│   │   ├── `@mention` resolution against OIDC users; resolved
│   │   │   mentions feed into Sprint 71.4 notifications.
│   │   ├── New "Discussion" tab on `/data-products/{slug}`.
│   │   └── ~15 pytest cases (CRUD + soft-delete + auth +
│   │       cross-workspace isolation).
│   │
│   ├── Sprint 71.2 — Star ratings + review text               ✅ done 2026-05-12
│   │   ├── New model: `DataProductReview` (id, dp_slug,
│   │   │   author_user_id, stars 1-5, body_md, created_at,
│   │   │   updated_at, dp_semver_at_review, workspace_id) +
│   │   │   Alembic.
│   │   ├── One review per (user, DP); idempotent upsert via
│   │   │   `/api/data-products/{slug}/reviews` PUT.
│   │   ├── Average-rating + count badge on
│   │   │   `/data-products/{slug}` header + browse cards.
│   │   ├── Reviews tab on the DP page with sorting (recent vs
│   │   │   stars-desc).
│   │   └── ~10 pytest cases.
│   │
│   ├── Sprint 71.3 — Follow / subscribe                       ✅ done 2026-05-12
│   │   ├── New model: `DataProductFollow` (user_id, dp_slug,
│   │   │   workspace_id, created_at) — composite PK + Alembic.
│   │   ├── `/api/data-products/{slug}/follow` POST/DELETE for
│   │   │   self; followers-count exposed via `/api/data-
│   │   │   products/{slug}` (full list only to steward, for
│   │   │   privacy).
│   │   ├── "Follow / Unfollow" button on the DP header.
│   │   ├── New page `/data-products/followed` listing the
│   │   │   current user's followed DPs.
│   │   └── ~8 pytest cases.
│   │
│   ├── Sprint 71.4 — Notification fanout                      ✅ done 2026-05-12
│   │   ├── Wire follow + comment + review events into the
│   │   │   Phase-20 audit-stream forwarder so existing
│   │   │   webhook/S3/CloudTrail sinks receive them — no new
│   │   │   pub-sub plumbing.
│   │   ├── New event types: `pql.dataproduct.commented`,
│   │   │   `pql.dataproduct.reviewed`,
│   │   │   `pql.dataproduct.schema_changed`,
│   │   │   `pql.dataproduct.contract_violated`.
│   │   ├── Per-user inbox at `/notifications` rendering events
│   │   │   for the user's followed DPs (reuses the audit-cockpit
│   │   │   inbox pattern from Phase 18.6).
│   │   ├── Email-digest opt-in via existing user-settings
│   │   │   surface (Phase 33 admin precedent).
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 71.5 — Wiki / README per DP                     ✅ done 2026-05-12
│   │   ├── New model: `DataProductReadme` (dp_slug, body_md,
│   │   │   version_int, updated_by_user_id, updated_at,
│   │   │   workspace_id) — single row per DP, version_int
│   │   │   monotonic.
│   │   ├── Steward + workspace-admin can edit; markdown render
│   │   │   via the existing `markdown-it` bundle.
│   │   ├── README tab on the DP page: contract-derived autodoc
│   │   │   at the top + free-form editorial below.
│   │   ├── History view with side-by-side diff between two
│   │   │   versions (reuses the diff macro from Phase 18.9).
│   │   └── ~6 pytest cases.
│   │
│   └── Sprint 71.6 — Browse-page rework                       ✅ done 2026-05-12
│       ├── `/data-products` index gets sortable columns
│       │   (rating-desc, recently-active, follow-count,
│       │   freshness-on-time).
│       ├── Filter chips (domain, steward, has-comments,
│       │   has-readme).
│       ├── "Recently active" surfaces DPs with new comments,
│       │   reviews, contract bumps in last 7d.
│       └── ~8 pytest cases.
│
```

## Phase 72 — Agent-Aware Social Layer

Closed 2026-05-13.

```text
├── Phase 72 — Agent-Aware Social Layer                     ✅ done 2026-05-13
│   │
│   │   AI-native differentiation on top of (or alongside)
│   │   Phase 71's catalog-collaboration foundation.  Treats
│   │   *agent activity* as the currency of social engagement
│   │   instead of human Likes — every endorsement badge is
│   │   auto-computed from lineage + audit data, every "trend"
│   │   is measured by `agent_run_operations` count, every
│   │   discussion thread is itself an audit_log row.
│   │
│   │   Plays into the AI-native lakehouse vision (memory:
│   │   `project_ai_native_vision.md`) and the supervision-first
│   │   framing (memory: `project_agent_first_pivot.md`).  Heavy
│   │   reuse of Phases 13 (agent_run_operations), 14 (audit_log),
│   │   15.x (lineage), 18.7 (audit FTS), 19 (agent_reviews),
│   │   20 (audit-stream + retention), 34 (cross-workspace
│   │   Grafana lens).
│   │
│   │   Independent of Phase 71 — neither is a prerequisite to
│   │   the other.  Land together for a unified Marketplace++
│   │   story or split across two release windows.
│   │
│   │   Cross-cutting picks (TBD):
│   │   - all endorsement badges are *typed* (no generic
│   │     👍/❤️) so the system stays audit-clean;
│   │   - comments-as-audit-rows (Sprint 72.5) is the canonical
│   │     contract that distinguishes us from Slack-clone risk
│   │     — if Phase 71.1's `DataProductComment` table ships
│   │     first, 72.5 either supersedes it or co-exists (model
│   │     decision at 72.5 plan time);
│   │   - "trending" board is a rolling 7d window, refreshed by
│   │     a new loop coroutine matching the freshness-loop
│   │     cadence.
│   │
│   ├── Sprint 72.1 — Activity feed per DP                     ✅ done 2026-05-13
│   │   ├── New aggregator `services/data_products/activity.py`
│   │   │   merges 4 source streams into a unified feed:
│   │   │   - audit_log writes referencing DP tables (Phase 14);
│   │   │   - agent_run_operations referencing DP tables
│   │   │     (Phase 13);
│   │   │   - freshness_scanner pass/miss events (Phase 50);
│   │   │   - schema / contract changes (Phase 50).
│   │   ├── `/api/data-products/{slug}/activity` GET with
│   │   │   server-side offset pagination (mirrors /queries
│   │   │   pattern from Sprint 57.2).
│   │   ├── New "Activity" tab on the DP page; becomes the
│   │   │   default landing tab when the DP has recent
│   │   │   agent-run-ops in the last 7 days.
│   │   ├── Per-row click-through to the run / audit row /
│   │   │   lineage trace that generated the event.
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 72.2 — Auto-computed endorsement badges         ✅ done 2026-05-13
│   │   ├── New service `services/data_products/badges.py`
│   │   │   computes each badge on-demand:
│   │   │   - `downstream-count`: out-edges in
│   │   │     `lineage_column_map` (Phase 15.6);
│   │   │   - `agent-run-count-7d`: distinct `agent_runs`
│   │   │     touching DP tables in last 7d (Phase 13);
│   │   │   - `last-rollback-passed`: did the most recent
│   │   │     rollback-preview succeed (Phase 16)?
│   │   │   - `freshness-on-time-30d`: % of freshness checks
│   │   │     in last 30d meeting SLA (Phase 50).
│   │   ├── Rendered as Bootstrap badges on DP header + browse
│   │   │   cards.
│   │   ├── Sort / filter on the browse page by each badge.
│   │   ├── No cache table — badges are cheap aggregates and
│   │   │   recompute-per-render keeps them honest.
│   │   └── ~10 pytest cases.
│   │
│   ├── Sprint 72.3 — "Trending in agent workloads" board      ✅ done 2026-05-13
│   │   ├── New page `/data-products/trending` ranking DPs by
│   │   │   `agent_run_count` + `audit_log_write_count` over a
│   │   │   rolling 7d window.
│   │   ├── New cache table `data_product_trending` (dp_slug,
│   │   │   window_start, agent_run_count, write_count, rank,
│   │   │   workspace_id) + Alembic.
│   │   ├── New loop coroutine in `_bootstrap/_loops.py`
│   │   │   refreshes the window every 15min (matches
│   │   │   `_data_product_freshness_loop` cadence).
│   │   ├── Per-workspace by default; cross-workspace toggle
│   │   │   gated by workspace-admin / auditor (Phase 34 lens
│   │   │   precedent).
│   │   ├── New Grafana panel "Top-10 trending DPs" added to
│   │   │   both single-workspace + cross-workspace dashboards.
│   │   └── ~10 pytest cases.
│   │
│   ├── Sprint 72.4 — Typed manual endorsements                ✅ done 2026-05-13
│   │   ├── New model: `DataProductEndorsement` (id, dp_slug,
│   │   │   endorsement_type, applied_by_user_id, applied_at,
│   │   │   removed_at, note_md, workspace_id) + Alembic.
│   │   ├── Allowed types validated server-side:
│   │   │   `verified-by-steward`, `production-ready`,
│   │   │   `deprecated`, `under-review`.  No free-form
│   │   │   user-typed strings.
│   │   ├── Scope-gated: only the DP's steward OR
│   │   │   workspace-admin / auditor can apply or remove.
│   │   │   Every action audit-logged as
│   │   │   `audit.endorsement.{applied,removed}`.
│   │   ├── Endorsement badges rendered on DP header +
│   │   │   browse cards; `deprecated` triggers a soft
│   │   │   warning on writes to DP tables (Phase 50 pre-write
│   │   │   hook).
│   │   ├── New plugin tool `pql_endorse_data_product` so the
│   │   │   Phase-19 reviewer-agent can apply
│   │   │   `verified-by-steward` after a clean audit pass.
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 72.5 — Audit-bound discussions                  ✅ done 2026-05-13
│   │   ├── Comments land as `audit_log` rows with
│   │   │   `kind=audit.discussion.posted` — supersedes or
│   │   │   coexists with Phase 71.1's separate table (decision
│   │   │   at plan time depending on whether 71.1 has
│   │   │   landed).
│   │   ├── Audit-log row carries body_md, parent_audit_log_id,
│   │   │   dp_slug, author_user_id; FTS-indexed via the
│   │   │   Phase-18.7 `audit_search` index so comments are
│   │   │   discoverable alongside everything else.
│   │   ├── Retention via the Phase-20 audit_retention loop —
│   │   │   no separate policy.
│   │   ├── Soft-hide model: `audit.discussion.hidden` follow-up
│   │   │   row (never destructive); only steward +
│   │   │   workspace-admin can hide.
│   │   ├── UI: "Discussion" tab on DP page, threaded, mentions
│   │   │   auto-link to user profile pages.
│   │   └── ~15 pytest cases.
│   │
│   └── Sprint 72.6 — CloudEvent subscriptions for DP changes  ✅ done 2026-05-13
│       ├── New `pql.dataproduct.*` event types registered in
│       │   the Phase-13.3 CloudEvent emitter
│       │   (`schema_changed`, `contract_violated`,
│       │   `freshness_missed`, `endorsement_applied`).
│       ├── Per-user webhook subscriptions: user registers a
│       │   webhook URL + filter expression ("only
│       │   contract_violated on DPs I follow"); HMAC-signed
│       │   delivery matches Phase-20 forwarder contract.
│       ├── Self-service config UI on
│       │   `/profile/notifications/subscriptions`.
│       └── ~10 pytest cases.
│
```

## Phase 73 — Agent-authored data products

Closed (date n/a).

```text
├── Phase 73 — Agent-authored data products                 ✅ done
│   │
│   │   Phase 72 made the data-product surface *aware* of
│   │   agents (badges, trending, activity feed).  Phase 73
│   │   inverts the flow: agents *author* and *evolve* data
│   │   products.  Today a DP exists when a human commits a
│   │   `pointlessql.yaml`; tomorrow the platform suggests one
│   │   when an agent run-pattern consistently produces a
│   │   stable schema, and lets the agent declare quality
│   │   contracts from inside the notebook.  This is the
│   │   AI-native pitch the incumbents can't match: catalogs
│   │   that grow from observed behaviour, not just human
│   │   curation.
│   │
│   │   Reuse heavy: Phase 13 (`agent_run_operations`),
│   │   Phase 15.6 (`lineage_column_map`), Phase 50
│   │   (`DataProduct` + yaml loader), Phase 72.1
│   │   (`fetch_activity_for_dp`).
│   │
│   │   Cross-cutting picks (TBD at plan time):
│   │   - YAML write path — does the platform write the yaml
│   │     directly (in-process) or open a PR against the
│   │     workspace-repo (Phase 51 path)?  PR path is
│   │     cleaner audit-wise but blocks single-tenant
│   │     installs without a git remote;
│   │   - contract DSL — pydantic-validated dict-from-yaml
│   │     stays canonical; `pql.contract()` builds the same
│   │     dict from inside notebooks and persists alongside
│   │     `pointlessql.yaml`;
│   │   - schema-change proposal model — does an agent
│   │     `propose` go through `AgentReview` (Phase 19) or
│   │     a new `DataProductSchemaProposal` table?  Reuse
│   │     of AgentReview is tempting but the surface is
│   │     write-oriented, not review-oriented.
│   │
│   ├── Sprint 73.1 — Promote-to-DP suggestion                  ✅ done
│   │   ├── New service `services/data_products/promote.py`
│   │   │   scans `agent_run_operations` for `target_table`
│   │   │   values that match a stable signature
│   │   │   (≥3 distinct runs / 14d, ≥10 row-affected ops,
│   │   │   no agent-flagged schema instability).
│   │   ├── New `DataProductPromotionCandidate` cache table
│   │   │   refreshed by a new loop coroutine
│   │   │   (`_data_product_promotion_loop`); same opt-in
│   │   │   cadence pattern as the trending loop.
│   │   ├── New `/data-products/candidates` HTML page +
│   │   │   `GET /api/data-products/candidates` JSON; admin /
│   │   │   steward dismiss / "Generate yaml".
│   │   ├── `POST /api/data-products/candidates/{id}/generate`
│   │   │   builds a draft `pointlessql.yaml` from the
│   │   │   schema-snapshot stream + lineage edges; either
│   │   │   writes to the active workspace-repo (PR path) or
│   │   │   into a `_drafts/` directory the admin can review.
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 73.2 — pql.contract() inline DSL                 ✅ done
│   │   ├── New `pql.contract(catalog, schema, *, tables=...)`
│   │   │   API that builds and persists the same yaml
│   │   │   payload from inside a notebook cell.  Returns a
│   │   │   `DataProductContract` object so the notebook
│   │   │   can chain validations (row count, freshness
│   │   │   bounds, value distribution checks) before commit.
│   │   ├── On `pql.contract().save()`, the file lands in
│   │   │   the workspace-repo (Phase 51) under
│   │   │   `pointlessql.yaml` next to the notebook OR is
│   │   │   merged into the existing yaml when one exists
│   │   │   for the schema (declarative merge — explicit
│   │   │   conflict raises).
│   │   ├── New `/api/contracts/draft` JSON endpoint backing
│   │   │   the "preview yaml before save" UX.
│   │   └── ~10 pytest cases.
│   │
│   ├── Sprint 73.3 — Schema-change proposal flow              ✅ done
│   │   ├── New model `DataProductSchemaProposal` (id,
│   │   │   data_product_id, proposer_user_id, proposer_kind,
│   │   │   diff_json, status, created_at, resolved_at,
│   │   │   resolved_by, resolution_note_md) + Alembic.
│   │   ├── New `POST /api/data-products/{cat}/{sch}/proposals`
│   │   │   for agents (plugin tool `pql_propose_schema_change`)
│   │   │   + humans (UI button in the Discussion tab).
│   │   ├── Inbox card on the DP detail page surfaces open
│   │   │   proposals; steward + admin can approve / reject
│   │   │   with one click.  Approval triggers either the PR
│   │   │   flow (workspace-repo) or in-place yaml rewrite.
│   │   └── ~12 pytest cases.
│   │
│   ├── Sprint 73.4 — Data passport / auto-README              ✅ done
│   │   ├── New `services/data_products/passport.py` renders
│   │   │   a markdown briefing from the lineage graph
│   │   │   (sources, transforms, downstream consumers,
│   │   │   freshness profile).  Output drops into the
│   │   │   `DataProductReadme` table as version 0 (auto)
│   │   │   when no human README exists yet; stays visible
│   │   │   as a "system passport" tab even after a steward
│   │   │   writes their own README.
│   │   ├── Re-generates on schema-change emits (Sprint B.1
│   │   │   ``EVENT_TYPE_DATA_PRODUCT_SCHEMA_CHANGED``) so
│   │   │   the passport reflects the current shape.
│   │   └── ~8 pytest cases.
│   │
│   └── Sprint 73.5 — Cross-DP recommendations                  ✅ done
│       ├── "Agents who read X also read Y" — co-occurrence
│       │   over `agent_run_operations.target_table` joined
│       │   to `agent_runs.id`.  Materialised as a 7d-rolling
│       │   `data_product_cooccurrence` cache table.
│       ├── New "Related products" card on the DP detail
│       │   header + a "Recommended for you" strip on
│       │   `/data-products/followed`.
│       └── ~8 pytest cases.
│
```

## Phase 74 — Reviewer-Agent v2 (Active steward delegate)

Closed 2026-05-15.

```text
├── Phase 74 — Reviewer-Agent v2 (Active steward delegate)  ✅ done 2026-05-15
│   │
│   │   Phase 19's passive Audit-Reviewer-Agent (writes one
│   │   summary row per run when triggered) promoted to an
│   │   active LLM-calling steward delegate.  Both runners
│   │   shipped per the plan-mode "Both surfaces" pick:
│   │   PointlesSQL-side in-proc loop (default) + Hermes-cron
│   │   alt path for stewards who want LLM cost / latency
│   │   out-of-process.  Per-DP opt-in via the new
│   │   ``DataProductActiveReviewerConfig`` table.
│   │
│   ├── Sprint 74.0 — Config table + service skeleton           ✅ 2026-05-15
│   │       New ``DataProductActiveReviewerConfig`` model +
│   │       alembic ``m9o1q3s5u7w9``.  Per-(workspace, dp) row
│   │       with enabled / runner CHECK ('inproc' | 'hermes_cron') /
│   │       llm_provider CHECK ('anthropic' | 'openai' | NULL) /
│   │       llm_model / prompt_override_md / acting_user_id
│   │       (steward proxy author for the non-nullable
│   │       comment / endorsement FK) / last_run_at /
│   │       last_run_comment_id.  New service
│   │       ``services/data_products/active_reviewer.py`` with
│   │       ``build_prompt`` + ``parse_review_result``
│   │       (explicit ``## Verdict:`` line + keyword-heuristic
│   │       fallback) + ``ReviewVerdict`` dataclass +
│   │       ``upsert_config`` + ``iter_opted_in_dp_ids``.
│   │
│   ├── Sprint 74.1 — PointlesSQL-side in-proc runner           ✅ 2026-05-15
│   │       ``run_reviewer_for_dp`` async entry-point with
│   │       injectable ``api_key_resolver`` + ``llm_call``
│   │       hooks (for unit-test fakes).  Loop
│   │       ``_active_reviewer_loop`` sleeps until
│   │       ``data_products.active_reviewer_trigger_hour`` UTC,
│   │       semaphore-bounds concurrent ticks at
│   │       ``active_reviewer_max_concurrent`` (default 3),
│   │       iterates DPs with ``runner='inproc'``.  Posts
│   │       ``DataProductComment`` + typed
│   │       ``DataProductEndorsement`` (green →
│   │       verified-by-steward, red → under-review) +
│   │       ``AgentReview`` row (kind=audit_review, severity
│   │       from verdict, payload_json carries the prompt +
│   │       raw LLM response).  Routes
│   │       ``GET/POST /api/data-products/{c}/{s}/active-reviewer``
│   │       (steward/admin) + ``run-now``.
│   │
│   ├── Sprint 74.2 — Hermes-cron runner + queue endpoint        ✅ 2026-05-15
│   │       ``GET /api/active-reviewer/queue`` (admin) lists
│   │       DPs with ``runner='hermes_cron'`` for a Hermes-cron
│   │       job to enumerate.  The plugin H.3 (out-of-tree)
│   │       ships ``pql_dp_activity`` / ``pql_dp_post_comment``
│   │       / ``pql_dp_endorse`` so the cron job can render
│   │       audit context + post comment + write endorsement
│   │       end-to-end without inventing new HTTP shape.
│   │
│   └── Sprint 74.3 — Steward UX HTML                          🧊 deferred
│           Active-reviewer card + ``/me/reviewer-config`` page
│           deferred.  Routes are agent-callable today; the
│           steward UI lands as a 74.3.1 follow-up once the
│           in-proc loop runs against a real workload.
│
```

## Phase 75 — Verifiable audit export + SIEM sinks

Closed 2026-05-15.

```text
├── Phase 75 — Verifiable audit export + SIEM sinks         ✅ done 2026-05-15
│   │
│   │   Two ⏳-promoted Icebox items.  Compliance-grade export
│   │   (sha256 + manifest) + the two SIEM sink types
│   │   container-deploys + ELK consumers ask for.  The third
│   │   Icebox item (action-string rename to ``resource.verb``)
│   │   stays 🧊 — ROADMAP gates it on a version-bump moment.
│   │
│   ├── Sprint 75.1 — Verifiable audit export                   ✅ 2026-05-15
│   │       New ``pointlessql audit-export`` typer subcommand
│   │       (``cli/audit_export.py``) writes three mode-0600
│   │       files: data (json|csv), ``.sha256`` sidecar
│   │       (sha256sum-compatible), ``.manifest.json``
│   │       (schema_version + tool_version + filters +
│   │       entry_count + data_sha256 + data_filename).
│   │       New web variant
│   │       ``GET /admin/audit/export.tar.gz`` streams the same
│   │       trio gzipped — admins click "Download with
│   │       manifest" instead of running the CLI.  Auditors
│   │       verify integrity by ``sha256sum -c`` +
│   │       manifest.data_sha256 cross-check.  6 pytest cases.
│   │
│   └── Sprint 75.2 — Stdout-JSON + Syslog audit sinks          ✅ 2026-05-15
│           New alembic ``n0p2r4t6v8x0`` extends
│           ``ck_audit_sinks_type`` to allow ``stdout_json`` +
│           ``syslog`` alongside the existing trio.
│           ``stdout_json`` writes one JSON line per envelope
│           (config: ``stream='stdout'|'stderr'``) for
│           container-log harvesters (Loki / Fluent Bit /
│           Vector).  ``syslog`` ships RFC-3164/5424 datagrams
│           via :mod:`logging.handlers.SysLogHandler` over
│           UDP/TCP (config: ``address='host:port'``,
│           ``protocol='udp'|'tcp'``, ``facility``,
│           ``severity``).  TLS terminates at a local rsyslog
│           sidecar by convention.  Both sinks swallow OSError
│           on emit — audit_log row stays authoritative.  8
│           pytest cases.
│
```

## Phase 76 — Full Social Network for Data Products

Closed 2026-05-13.

```text
├── Phase 76 — Full Social Network for Data Products       ✅ done 2026-05-13
│   │
│   │   Six sub-sprints landed in one autonomous session +
│   │   two close-out polish commits.  Lifted the Phase-71–74
│   │   "agent-aware social layer" into a full social network:
│   │   deeper threading, GitHub-style reactions, topics as a new
│   │   entity-class, separate user + agent profiles, per-user
│   │   feed, granular notification preferences, real-time SSE
│   │   bell, cross-DP citations.  Every social write stays an
│   │   ``audit_log`` row + CloudEvent so the Phase-18.7 FTS and
│   │   Phase-20 SIEM pipeline pick the action up.  9 new tables,
│   │   6 alembic migrations (``p7r9..u2w4``), 1 new background
│   │   loop, 6 new HTML pages, ~104 new pytest cases.
│   │
│   ├── Phase 76.1 — Deeper conversations             ✅ (511df5e)
│   │       Threading depth 2 → 5 with app-level walk-the-chain
│   │       check, 6-emoji reactions on comments + DPs (canonical
│   │       👍 ❤️ 🎉 😄 😕 👀), category enum (general / question
│   │       / announcement / idea) with accept-answer atomic per
│   │       thread, ``@display_name`` mention resolution with
│   │       audit row on ambiguity, ``GET /api/users/search?q=``.
│   │       33 pytest cases.
│   │
│   ├── Phase 76.2 — Profiles + user-to-user follows  ✅ (037ccc8)
│   │       ``/users/{id}`` 5-tab profile (Overview / Stewarded /
│   │       Following / Comments / Reviews), user_follows with
│   │       50-per-hour rate-limit, sticky badge awards via new
│   │       24 h ``_user_badges_loop`` (steward_3plus,
│   │       reviewer_100plus, mention_magnet, accepted_answer,
│   │       endorser).  Topbar dropdown links to ``/users/me``.
│   │       12 pytest cases.
│   │
│   ├── Phase 76.3 — Topics taxonomy                  ✅ (cc6e1c4)
│   │       ``topics`` + ``data_product_topics`` +
│   │       ``user_topic_follows`` tables; ``/topics`` index +
│   │       ``/topics/{slug}`` detail; steward-managed
│   │       DP↔topic replace-all via
│   │       ``PUT /api/data-products/{c}/{s}/topics``; fan-out
│   │       on ``topic.dp_added`` to topic followers.  Topbar
│   │       ``Topics`` link.  13 pytest cases.
│   │
│   ├── Phase 76.4 — /feed + notification preferences ✅ (2629011)
│   │       ``/feed`` merge of inbox + followed users / DPs /
│   │       topics with cursor pagination + FTS over the
│   │       discussion-mirrored audit_log.  ``users.notification_prefs_json``
│   │       JSON map of ``{event_type: {inbox, email, webhook}}``
│   │       drives per-event-type opt-out.
│   │       ``/settings/notifications`` page.  9 pytest cases.
│   │
│   ├── Phase 76.5 — Agents as first-class actors     ✅ (a573e37)
│   │       ``agents`` table (workspace-scoped slug, verified
│   │       badge, principal_user_id accountability chain).
│   │       ``/agents`` + ``/agents/{slug}`` 4-tab profile.
│   │       ``?as_agent=<slug>`` on the comment POST — the
│   │       agent's principal_user (or admin) may post under the
│   │       agent identity.  ``author_user_id`` stays NOT NULL
│   │       (always the human accountable), ``author_agent_id``
│   │       is the optional presentation-layer override.
│   │       Audit detail JSON carries both ids.  14 pytest cases.
│   │
│   ├── Phase 76.6 — SSE bell + cross-DP citations    ✅ (9c6534f)
│   │       ``GET /api/notifications/stream`` long-lived SSE
│   │       endpoint with 25 s keep-alive comment; module-level
│   │       ``_LISTENERS`` registry fan-out from the
│   │       notifications service.  ``EventSource`` consumed by
│   │       the topbar bell with the existing 60 s poll left in
│   │       place as fallback.  Render-time resolution of
│   │       ``#dp:cat.sch``, ``#topic:slug``, ``#user:email``,
│   │       ``#agent:slug`` tokens — unresolved tokens degrade to
│   │       literal text.  10 pytest cases.
│   │
│   ├── Phase 76.5.1 — as_agent on endorsements + reviews  ✅ (close-out)
│   │       Closed the original-plan corner the autonomous run
│   │       deferred.  Migration ``u2w4y6a8c0e3`` adds
│   │       ``applied_by_agent_id`` on endorsements,
│   │       ``author_agent_id`` on reviews, ``agent_slug`` on
│   │       ``data_product_active_reviewer_configs``.  Helper
│   │       ``resolve_agent_for_principal`` lifted into
│   │       ``data_products_routes/_shared.py`` so all three
│   │       write surfaces enforce one principal-or-admin gate.
│   │       Active Reviewer v2 now stamps the agent identity
│   │       on the comment + endorsement when ``agent_slug`` is
│   │       set; NULL falls back to the steward-proxy path.
│   │       Hygiene fixes: 3 bare-http-ok markers
│   │       (``users_routes/profile.py``), 2 bare-broad-ok
│   │       markers (``topics_routes/detail.py``,
│   │       ``users_routes/follows.py``),
│   │       ``data_products_routes/comments.py`` added to the
│   │       file-size allowlist after the helper extraction.
│   │       11 new pytest cases.
│   │
│   └── Phase 76.6.1 — Alpine helper JS modules       ✅ (17eebb1)
│       Two ``frontend/js/*.js`` modules.
│       ``mention_autocomplete.js`` provides ``@`` / ``#dp:`` /
│       ``#topic:`` / ``#agent:`` typeahead on
│       ``<textarea data-mention-autocomplete>`` — debounced
│       200 ms, arrow / Enter / Tab pick, inserts the canonical
│       token.  ``comments_collapse.js`` auto-collapses
│       ``data-pql-comment-depth >= 3`` rows with a
│       "Show N more replies" toggle on the depth-2 anchor —
│       forward-compatible: current Alpine renders 2 levels so
│       the script is a no-op until a recursive renderer lands.
│       Three endpoints (``/api/data-products``, ``/api/topics``,
│       ``/api/agents``) now accept ``?q=<prefix>`` for the
│       picker.  Smoke-parse via ``node -c`` covers both
│       modules.  2 pytest cases.
│
```

## Phase 77 — Social-as-Connective-Tissue across the platform

Closed 2026-05-15.

```text
├── Phase 77 — Social-as-Connective-Tissue across the platform  ✅ done (2026-05-15)
│   │
│   │   "PointlesSQL is to Unity Catalog + Spark/DuckDB what
│   │   GitHub is to Git."  Lifts the Phase-76 social surface
│   │   (comments / reviews / endorsements / citations / mentions
│   │   / follows / topics) from DP-only to the connective tissue
│   │   over every named platform object: UC tables, schemas,
│   │   catalogs, models, branches, runs, queries, notebooks,
│   │   saved audit queries — and adds GitHub-Issues / Stars /
│   │   READMEs-everywhere / PR-style branch-promote-gate /
│   │   workspace-as-Organization primitives.
│   │
│   │   Architecture locked: social layer lives entirely in
│   │   PointlesSQL — soyuz stays pure-UC-spec.  Schema strategy
│   │   = sidecar polymorphic anchor (``social_targets`` keyed by
│   │   ``(workspace_id, entity_kind, entity_ref)``).  Comments /
│   │   reviews / endorsements / follows / reactions / readmes
│   │   point at ``social_targets.id`` instead of
│   │   ``data_products.id`` directly.  CASCADE-on-DP-delete
│   │   preserved via a back-pointer on the anchor row.  Audit-
│   │   log target string keeps the legacy ``data_product:``
│   │   prefix for kind='dp' rows forever (locked decision #9);
│   │   every new kind writes the generic ``{kind}:{ref}`` form.
│   │   Branch promote-gate is opt-in per workspace
│   │   (``branch_promote_requires_endorsement DEFAULT FALSE``);
│   │   default never auto-flips.  Notebook ``entity_ref`` is
│   │   an immutable UUID, not the file path.
│   │
│   ├── Phase 77.0 — Polymorphic foundation (zero new entity types)  ✅ done (2026-05-15)
│   │       ``social_targets`` anchor table + ``entity_registry``
│   │       single-source-of-truth + ``get_or_create_target`` /
│   │       ``resolve_workspace_for_entity`` resolver.  Migration
│   │       ``v3y5a7c9e1g3`` creates the anchor + backfills one
│   │       row per existing DP.  Subsequent 77.0 migrations add
│   │       ``social_target_id`` columns to the seven existing
│   │       social tables, ship the generic ``mirror_social_to_audit``
│   │       helper + ``fanout_event`` dispatcher + citations-
│   │       registry refactor + ``/api/social/{kind}/{ref}/...``
│   │       router + frontend partial extraction +
│   │       feed-URL-builder via registry.  Drops the now-
│   │       redundant ``data_product_id`` columns at the end.
│   │       End-user behaviour unchanged; the entire DP-social
│   │       test suite must pass unmodified.
│   │
│   ├── Phase 77.1 — Tables                                          ✅ done (2026-05-15)
│   │       First new entity type.  Discussion + Endorsements +
│   │       Followers + README tabs on every UC table page.
│   │       Reviews hidden (tables don't get star-ratings).
│   │       ``#table:cat.sch.tbl`` citation token registered.
│   │       Federated / foreign tables get the same tabs (no
│   │       banning).  Stars left to Phase 77.8.
│   │       77.1.A: registry + citations backbone.
│   │       77.1.5: polymorphic backend handlers (12 fns across 4
│   │       axes) + socialTabs Alpine factory + 2 new partials +
│   │       table.html tab strip.
│   │
│   ├── Phase 77.3 — Branches (with promote-gate, opt-in)            ✅ done (2026-05-15)
│   │       Branch detail page has 4 social tabs + Promote tab
│   │       (Danger Zone) + the killer GitHub-PR analog: workspace
│   │       setting ``branch_promote_requires_endorsement`` (default
│   │       OFF, never auto-flipped).  When true, ``pql.promote()``
│   │       requires ≥1 ``branch-approved-for-promotion`` endorsement
│   │       by a user other than the caller; rejects with 412
│   │       otherwise.  Promote button greys out + shows "Needs ≥1
│   │       peer endorsement" hint when gate is on and unsatisfied.
│   │       77.3.A: workspaces column + endorsement type +
│   │       /api/branches/.../promote gate (412).
│   │       77.3.B: branch_detail.html tab strip + gate-state UI.
│   │
│   ├── Phase 77.2 — Models                                          ✅ done (2026-05-15)
│   │       Registered-model detail (``/models/{full_name}``) gains
│   │       5 social tabs: Discussion / Reviews / Endorsements /
│   │       Followers / README.  ``#model:cat.sch.name`` citation
│   │       resolves to the detail URL.  Polymorphic backend reused
│   │       as-is — the model kind joins ``table`` + ``branch`` in
│   │       ``_kind_dispatch.parse_ref``.  Issues + full Stars stay
│   │       queued: Issues land in 77.7, polymorphic follow/star in
│   │       77.8.
│   │       77.2.1: polymorphic UNIQUE
│   │       ``(workspace_id, social_target_id, author_user_id)`` on
│   │       ``data_product_reviews`` + polymorphic review handlers
│   │       (list/upsert/delete) + ``model.supports_reviews=True``.
│   │
│   ├── Phase 77.2.1 — Polymorphic reviews enable                     ✅ done (2026-05-15)
│   │       Alembic migration ``a8d0f2g4i6k8`` adds the kind-
│   │       agnostic UNIQUE so polymorphic upsert is idempotent
│   │       (legacy ``(ws, data_product_id, user)`` UNIQUE doesn't
│   │       apply when ``data_product_id`` is NULL).  Three new
│   │       polymorphic handlers in ``_polymorphic_handlers.py``
│   │       + dispatcher switch in ``social_routes/reviews.py``.
│   │       Registry flag flipped → Reviews tab now renders on
│   │       model.html with the inline ``modelReviews`` Alpine
│   │       factory.  Tables + branches stay reviews-off (still
│   │       ``supports_reviews=False`` in the registry).
│   │
│   ├── Phase 77.4 — Runs                                            ✅ done (2026-05-15)
│   │       Agent-run pages gain a 5th top-tab "Social" with
│   │       three sub-tabs (Discussion / Endorsements / Followers).
│   │       Reviews / README hidden via registry flags (runs are
│   │       transient outcomes, not curated artefacts).  Stars
│   │       stay off until 77.8; Issues stay off until 77.7
│   │       decides whether the issue-against-run use-case is
│   │       worth the surface.  ``#run:<uuid>`` citation pattern
│   │       (36-char UUID) renders to ``/runs/<uuid>`` anchor.
│   │       Endorsement vocabulary reuses the four DP-flavoured
│   │       types so humans can flag quality signals on individual
│   │       agent runs.  18 new pytest cases (registry + URL
│   │       builder + audit prefix + citation + parse_ref +
│   │       polymorphic comment/endorsement round-trips + HTML
│   │       social tab + sub-tabs + factory exposure + partials).
│   │
│   ├── Phase 77.5 — Schemas + Catalogs                              ✅ done (2026-05-15)
│   │       ``/catalogs/{cat}`` and ``/catalogs/{cat}/schemas/{sch}``
│   │       gain the polymorphic social surface.  Four sub-commits:
│   │       * 77.5.A — registry registers ``kind='schema'`` +
│   │         ``kind='catalog'`` (4 social tabs each: Discussion
│   │         + Endorsements + Followers + README; stars on,
│   │         reviews + issues off).  ``#schema:cat.sch`` and
│   │         ``#catalog:name`` citation regex + pass-through
│   │         resolvers.  ``_POLYMORPHIC_KINDS`` extended +
│   │         ``parse_ref`` validates ``cat.sch`` for schemas and
│   │         a bare identifier for catalogs.  Workspace
│   │         resolver gets a factored-out
│   │         ``_workspace_for_catalog`` probe so schemas +
│   │         catalogs share the lookup.
│   │       * 77.5.B — ``schemas.html`` restructured: existing
│   │         5 cards (Metadata / Schemas list / Tags /
│   │         Permissions / Properties) wrapped into an
│   │         Overview tab; 4 social tabs added with
│   │         ``socialTabs({kind:"catalog", ref:catalog_name})``.
│   │         Header star button switched to the server-backed
│   │         ``pqlStarToggle({kind, ref})`` shape.  Inline
│   │         ``catalogDiscussion`` + ``catalogReadme`` x-data
│   │         factories.
│   │       * 77.5.C — ``tables.html`` restructured: existing
│   │         schema-detail cards (Metadata + dbt registration
│   │         + ML registration + Tables list + Tags +
│   │         Permissions + Properties) wrapped into an Overview
│   │         tab; 4 social tabs added with
│   │         ``socialTabs({kind:"schema", ref:"cat.sch"})``.
│   │         Inline ``schemaDiscussion`` + ``schemaReadme``
│   │         x-data factories.
│   │       * 77.5.D — 27 new pytest cases (19 kind/registry +
│   │         8 HTML smoke).  Zero schema work — the
│   │         ``social_targets.entity_kind`` CHECK already
│   │         permitted both kinds since Phase 77.0.
│   │

│   ├── Phase 77.6 — Notebooks + Saved Queries                       ✅ done (2026-05-15)
│   │       Per-notebook + per-saved-query social tabs.  New
│   │       ``notebooks.id UUID`` column (locked decision #8 —
│   │       stable across path renames).
│   │       ``#notebook:{uuid}`` + ``#query:{slug}`` citations.
│   │
│   │       Four sub-commits:
│   │       * 77.6.A — alembic ``f3h5j7l9n1p3`` creates the
│   │         ``notebooks`` table (36-char UUID PK, workspace
│   │         + path UNIQUE).  Backfills every distinct
│   │         ``(workspace_id, file_path)`` tuple across
│   │         ``notebook_outputs`` + ``notebook_cell_runs`` +
│   │         ``notebook_cell_run_sources`` (the latter two are
│   │         path-keyed without a workspace column, coalesce
│   │         to ``workspace_id=1``).
│   │       * 77.6.B — registry registers ``kind='notebook'`` +
│   │         ``kind='saved_query'`` (4 social tabs each; stars
│   │         on, reviews + issues off).  Adds
│   │         ``#notebook:<uuid>`` (36-char UUID) +
│   │         ``#query:slug`` citation regex with pass-through
│   │         resolvers.  ``_POLYMORPHIC_KINDS`` + ``parse_ref``
│   │         extended.
│   │       * 77.6.C — ``_get_or_create_notebook_uuid`` helper
│   │         + new ``GET /notebooks/uuid/{uuid}`` alias route
│   │         that resolves the UUID back to the path-based
│   │         render.  Existing ``/notebooks/edit/{path}`` now
│   │         threads ``notebook_uuid`` into the template.
│   │         ``notebook_editor.html`` gains a Social toolbar
│   │         button + Bootstrap ``offcanvas-end`` side-drawer
│   │         (full tab strip would crowd the editor; side-
│   │         drawer was the locked decision in the plan).  4
│   │         tabs inside driven by
│   │         ``socialTabs({kind:"notebook", ref:uuid})``.
│   │       * 77.6.D — ``saved_audit_query_detail.html`` full
│   │         tab strip: existing SQL + result cards wrapped
│   │         into an Overview tab, 4 social tabs added with
│   │         ``socialTabs({kind:"saved_query", ref:slug})``.
│   │         Header gains a server-backed star button.
│   │       * 77.6.E — 17 new pytest cases (schema + registry +
│   │         citation + dispatch + round-trip + DOM smoke).
│   │

│   ├── Phase 77.7 — Issues (the GitHub-Issues entity)               ✅ done (2026-05-15)
│   │       Separate ``issues`` entity with state / assignee /
│   │       labels_json / milestone_id / closed_reason.  Threaded
│   │       comments under each issue reuse the polymorphic
│   │       comments table; an issue is itself a
│   │       ``social_target``-able entity (full self-similarity).
│   │       Existing Discussions ``category`` enum +
│   │       ``accept_answer`` untouched.
│   │
│   │       Six sub-commits in one autonomous session:
│   │       * 77.7.A — alembic ``e2g4i6k8m0o2`` creating
│   │         ``issues`` + ``issue_labels`` + ``issue_milestones``
│   │         (3 ORM models, two CHECK constraints locking
│   │         state + close-reason vocab, three indexes on
│   │         ``issues`` for the workspace+state / parent /
│   │         assignee lookup axes).
│   │       * 77.7.B — registry registration for ``kind='issue'``
│   │         (label "Issue", url ``/issues/{id}``, three social
│   │         tabs Discussion+Endorsements+Followers, stars
│   │         on, issues off — no recursion); flipped
│   │         ``supports_issues=True`` on dp/table/model/branch.
│   │         Added ``#issue:\d+`` citation regex + render.
│   │         Added ``EVENT_TYPE_ISSUE_OPENED`` and
│   │         ``EVENT_TYPE_ISSUE_STATE_CHANGED`` governance
│   │         events.  Built ``social_routes/issues.py`` with
│   │         eight endpoint families: open + list (parent-
│   │         scoped + global) + GET + PATCH + close + reopen
│   │         + labels CRUD + milestones CRUD.  Issue create
│   │         uses a three-step pattern (anchor placeholder
│   │         ref → insert issue → rewrite anchor ref to
│   │         ``str(issue.id)``) so the social_target row is
│   │         consistent on commit.
│   │       * 77.7.C — ``/issues`` HTML index + ``/issues/{id}``
│   │         detail page with two-column layout (left: title
│   │         + body_md + 3 social tabs; right: state controls
│   │         + assignee + labels + milestone + parent badge +
│   │         star button via the server-backed pqlStarToggle
│   │         from 77.8.E).
│   │       * 77.7.D — kind-agnostic Issues tab partial
│   │         wired into table.html, model.html,
│   │         branch_detail.html, and data_product.html.
│   │         DP page wraps the partial in a tiny x-data
│   │         that surfaces kind+ref since data_product.html
│   │         pre-dates the socialTabs factory.
│   │       * 77.7.E — 31 new pytest cases (schema + routes +
│   │         DOM smoke) plus issue helper extraction
│   │         (``_issue_helpers.py`` + ``_issue_taxonomy.py``)
│   │         to stay under the file-size budget after adding
│   │         ``bare-http-ok:`` markers on every raise.  Two
│   │         pre-existing assertions in 77.1 + 77.2 flipped
│   │         to match the new ``supports_issues=True`` reality.
│   │       * 77.7.F — close-out (this entry + CHANGELOG).
│   │       Comment-reactions on issue comments stay 501 by
│   │       design — unlock lands in 77.11.
│   │

│   ├── Phase 77.8 — Stars + polymorphic Follow + Reactions          ✅ done (2026-05-15)
│   │       Three migrations + the polymorphic backend that flips
│   │       Star / Follow / Reaction from 501 to functional across
│   │       every registered entity kind.  77.8.A added the new
│   │       ``social_stars`` polymorphic bookmark table; 77.8.B
│   │       added the sibling ``social_follows`` table (sidesteps
│   │       the SQLite PK-swap difficulty on ``data_product_follows``
│   │       — 77.0.G's docstring already flagged this path);
│   │       77.8.C added a polymorphic UNIQUE on
│   │       ``data_product_reactions(social_target_id, user_id,
│   │       emoji)`` so polymorphic upsert is idempotent.  77.8.D
│   │       shipped ``stars_routes.py`` + flipped the polymorphic
│   │       follow/reaction handlers to use the new tables (DP
│   │       follow + DP reaction routes stay bit-identical via the
│   │       legacy ``data_product_follows`` / DP-id PK path).
│   │       77.8.E rewrote ``pqlStarToggle`` to be server-backed
│   │       with localStorage fallback for kinds not yet registered
│   │       (catalog + schema land in 77.5); model.html +
│   │       branch_detail.html + run_view.html headers gained
│   │       visible star buttons.  The ``data_product_readmes`` →
│   │       ``entity_readmes`` table rename is deferred to Phase
│   │       77.11 alongside the rename of follows + reactions.
│   │       18 new pytest cases across 2 new test files + 2
│   │       existing 501-gated tests flipped to assert functional
│   │       behaviour.  Full Phase-77 suite at 109 passing.
│   │
│   ├── Phase 77.9 — Cross-entity feed                               ✅ done (2026-05-15)
│   │       The activity feed lists comments + reviews across
│   │       every polymorphic entity kind (not just data
│   │       products).  ``_row_from_comment`` + ``_row_from_review``
│   │       JOIN the ``social_targets`` anchor and build the
│   │       ``source_url`` through ``entity_registry.url_for`` so
│   │       links land on the right detail page regardless of
│   │       kind.  ``GET /api/feed`` gains an optional ``?kind=X``
│   │       narrow.  ``feed.html`` carries a kind-pill row above
│   │       the existing filter chips.  Full-body FTS migration is
│   │       deferred to 77.11 (the visible win was the cross-entity
│   │       feed; FTS body extension is a separate plumbing job).
│   │       7 new pytest cases.
│   │
│   ├── Phase 77.9.X — full-body FTS                                  ⏳ deferred to 77.11
│   │       ``/feed`` becomes entity-agnostic with a kind-pill
│   │       filter row.  ``audit_search`` FTS indexes full
│   │       ``body_md`` (not just 140-char preview) across every
│   │       entity kind.
│   │
│   ├── Phase 77.10 — Workspace-as-Organization landing page         ✅ done (2026-05-15)
│   │       GitHub-org-style landing page for every workspace at
│   │       ``/workspaces/{slug}``.  Alembic ``g4i6k8m0o2q4``
│   │       creates ``workspace_pinned_entities`` (composite PK
│   │       on workspace + social_target, ordered index).
│   │       Registers ``kind='workspace'`` (4 tabs Discussion +
│   │       README + members + activity; stars + endorsements +
│   │       issues all off).  New ``workspaces_routes.py``
│   │       exposes 5 routes: HTML landing + pin CRUD + activity
│   │       feed.  Pin writes admin-only; reads member-only.
│   │       9 new pytest cases (schema, registry, HTML render,
│   │       pin CRUD round-trip, 409 on duplicate, 403 on
│   │       non-admin, activity scope, reorder).
│   │

│   │       ``/workspaces/{slug}`` is the workspace's GitHub-org-
│   │       style landing page.  ``workspace_pinned_entities``
│   │       table + 3 rows of pinned cards (DPs / tables /
│   │       models) + workspace-scoped activity feed + workspace
│   │       README (entity_readmes with kind='workspace').
│   │
│   └── Phase 77.11 — Polish + announce                              ✅ done (2026-05-15)
│           Phase 77 close-out doc at ``docs/phase-77.md``.  The
│           heavy consolidation work was deliberately deferred at
│           close-out and landed in Phase 78 polish (below).
│
```

## Phase 78 — Polish bundle

Closed 2026-05-16.

```text
├── Phase 78 — Polish bundle                              ✅ done 2026-05-16
│       Six items deferred from the Phase-77 close-out, landed
│       in one autonomous session as eight self-contained
│       commits + four alembic migrations:
│       1. ``fanout_dataproduct_event`` wrapper deletion (the
│          legacy DP-scoped helper had zero active call-sites;
│          three test references rewritten to call
│          ``fanout_event`` directly).
│       2. Comment-reaction polymorphism unlock — removed the
│          ``_require_dp_kind_for_comment_reactions`` guard;
│          three new polymorphic handlers in
│          ``_polymorphic_handlers.py`` cover the non-DP path.
│       3. ``model.html`` social-tab inline blocks extracted
│          into per-page partials following the existing
│          ``pages/_partials/model/`` pattern; ``data_product.html``
│          stale 77.11 comment cleaned up.
│       4. ``audit_search`` gets a new ``entity_kind`` column +
│          full-body comment indexing.  ``/api/audit/search``
│          accepts ``?kind=X``.  Migration ``h5j7l9n1p3r5``.
│       5. ``data_product_follows`` consolidated into
│          ``social_follows`` (migration ``i6k8m0o2q4s6``).
│       6. ``data_product_readmes`` renamed to ``entity_readmes``
│          + legacy DP-id column dropped (migration
│          ``j7l9n1p3r5t7``).
│       7. ``data_product_reactions`` consolidated into
│          ``social_reactions`` via the sibling-table pattern,
│          and legacy ``uq_dp_review_one_per_user`` UNIQUE
│          dropped (migration ``k8m0o2q4s6u8``).
│       8. Badges: documented that the existing five thresholds
│          were already cross-kind; added three new per-kind
│          badges (``commenter_table_50plus``,
│          ``endorser_model_20plus``, ``issue_resolver_10plus``).
│       2724 pytest pass / 0 fail; pyright budget stays at
│       609/623 across the entire bundle.
│
```

## Phase 79 — Code-quality + modularisation bundle

Closed 2026-05-15.

```text
├── Phase 79 — Code-quality + modularisation bundle      ✅ done 2026-05-15
│       Audit-grounded refactor sweep.  The codebase came in
│       healthier than the brief assumed (100% function docstring
│       coverage, ruff clean, 18-entry file-size allowlist all
│       justified, no grab-bag files); the bundle focused on the
│       three problems that *were* real.  Eight self-contained
│       commits, zero migrations, behaviour-equivalent only:
│       1. Pydoclint baseline closed — five ORM ``Attributes:``
│          sections + three indirect-raise ``# noqa: DOC502``
│          markers.  13 warnings → 0 violations.
│       2. ``notebooks_routes.py`` (pre-existing 904-LOC CI gate
│          breach) split into ``api/notebooks_routes/`` subpackage
│          per the Phase-26 pattern; six modules, each under 300
│          LOC.
│       3. PQL engine typing shims — new
│          ``ArrowField`` / ``ArrowSchema`` / ``ArrowArray`` /
│          ``ArrowTable`` / ``DuckdbCursor`` / ``DeltaField`` /
│          ``DeltaSchema`` Protocols in ``pql/_types.py``;
│          ``_autoload.py`` + ``_merge.py`` cast at the
│          pyarrow / duckdb / deltalake boundaries.  Pyright
│          budget 609 → 496 (-113).
│       4. Shared ``agent_payload`` helper extracted from four
│          duplicating sites (two ``_agent_payload`` helpers + two
│          inline comprehensions).  Bigger envelopes
│          (``_serialise_comment`` etc.) deliberately stay
│          separate — DP vs polymorphic JSON shapes are
│          load-bearing for back-compat.
│       5. Phase-77 test rename sweep — all 27 ``test_phase77_*``
│          files migrated to topic-named homes (``test_social_target``,
│          ``test_polymorphic_handlers``, ``test_issues_routes``,
│          etc.).  Pure ``git mv``.
│       6. Stale "deferred to Phase 77.11" comments cleaned up
│          across ``_polymorphic_handlers.py`` / ``comments.py`` /
│          ``readme.py``.
│       Explicit non-goal: no alembic squash.  The 90-migration
│       chain is cheap at runtime and Phase 77/78 carry
│       irreversible data-movements whose squash would lose
│       downgrade semantics; revisit after first prod schema
│       stability window.
│       Final state: 2724 pytest pass / 0 fail / 7 skip;
│       pyright 496/623; pydoclint zero violations; file-size
│       gate clean.
│
```

## Phase 80 — Navigation & UX overhaul

Closed 2026-05-15.

```text
├── Phase 80 — Navigation & UX overhaul                    ✅ done 2026-05-15
│       Full IA + chrome rebuild after the Phase 79 walkthrough
│       surfaced five URL-only orphans (`/issues`, `/topics`,
│       `/feed`, `/users/{id}`, `/workspaces/{slug}`), a
│       command-palette that indexed only five entity kinds,
│       and a "my stuff" surface fragmented across four pages.
│       Ten self-contained sub-phases in one autonomous run.
│       No alembic migrations.  Behaviour-equivalent route
│       surface; only additive (`/users`, `/lineage`, `/me`,
│       `/api/health/backends`).
│
│       1. **IA contract** (80.0) — `docs/internal/navigation_ia.md`
│          captures the four chrome slots, five intent-groups,
│          every entry's template + handler, all context-panel
│          bindings, command-palette entity coverage, locked
│          decisions.  Audit-bot ready.
│       2. **Primary rail rework** (80.1) — icon_rail →
│          primary_rail; two-state width 64 px ↔ 220 px;
│          5 grouped sections (HOME / WATCH / BUILD / DATA /
│          COMMUNITY / WORKSPACE); 24 entries; rail badges
│          plumbing (counts wired in 80.3).
│       3. **Context-panel partials** (80.2) — 11 new sidebar
│          partials wired through `context_panel.html` covering
│          every new section.
│       4. **Today digest** (80.3) — three new stat cards on `/`
│          (approval queue · unread inbox · firing alerts);
│          `services/nav_badges.py` aggregator powers both
│          the Today cards and rail badges.
│       5. **/users + /lineage index pages** (80.4) — closes
│          two of the URL-only orphans with workspace-scoped
│          member list + trace-row/trace-column hub.
│       6. **/me consolidated hub** (80.5) — six/seven-card
│          landing replacing the previously-fragmented self-
│          pages; user-menu becomes the Me-hub shortcut list.
│       7. **Command palette expansion** (80.6) — `/api/search`
│          now covers 7 more kinds (data_product, topic, issue,
│          user, agent, workspace, saved_query); `@user` and
│          `#topic` operators narrow results.
│       8. **Status footer bar** (80.7) — fourth chrome slot,
│          28 px sticky bottom strip; workspace + role chips,
│          backend health pills polling `/api/health/backends`
│          every 60 s, keyboard hints.
│       9. **Quick-create + menu** (80.8) — GitHub-style topbar
│          dropdown with 6 baseline + 2 admin entries.
│       10. **Close-out** (80.9) — CHANGELOG + ROADMAP, broad-
│           except markers, full Phase-80 test pass.
│
│       Final state: 44 new test cases across 9 modules; full
│       pytest suite remains green (1635+ pass / 3 skip);
│       pyright 498 warnings (matches Phase 79 ceiling within
│       2 from new code, well under 623 cap); pydoclint zero
│       violations; file-size budget OK; bootstrap-order OK.
│
│       Locked design picks (binding): HOME-first IA;
│       expanded rail by default; Lens + dbt stay as their own
│       BUILD entries; footer always visible (no hide toggle).
│
```

## Phase 81 — Feed overhaul + help surface + entity ⋯-menu

Closed 2026-05-16.

```text
├── Phase 81 — Feed overhaul + help surface + entity ⋯-menu  ✅ done 2026-05-16
│       Three-track polish bundle.  Track K rebuilt /feed from a
│       flat Bootstrap `list-group` into a first-class social
│       product page (GitHub-feed quality).  Track L added a
│       global `?`-button + `/help` reference surface as a
│       deliberate alternative to forced product tours.  Track M
│       lifted the feed item ⋯-action pattern into a reusable
│       macro and wired it into DP / Model / Run detail pages.
│       Plus a small first-run-welcome fix at close-out.
│
│       Track K — Feed overhaul (`377c93a..2792f43`):
│       1. **81.K.1** — Layout shell, sticky filter bar, day
│          grouping.  Replaces flat list-group with `nav-pills`
│          For-you / Mentions / My / Following + kind multi-
│          select dropdown + density toggle (Comfortable /
│          Compact / Headlines).  Day separators with sticky
│          "Today" / "Yesterday" / "Mon May 12" / "Earlier".
│       2. **81.K.2** — Rich per-kind item cards with bulk
│          actor-name resolution; one Alpine renderer + shared
│          classifier for comment / review / mention /
│          notification / agent_run / badge / issue / branch.
│       3. **81.K.3** — SSE live updates against
│          `/api/notifications/stream` with an "X new" pulse
│          banner and exponential reconnect backoff.
│       4. **81.K.4** — Per-item ⋯-action menu: Mark read,
│          Mute thread, Mute author, Snooze 1h/8h/1d, Copy link.
│          New `feed_mutes` Alembic table; 5 new endpoints.
│       5. **81.K.5** — Right context column (Trending today /
│          People to follow / Saved searches) with two new
│          `/api/feed/trending` + `/api/feed/people` aggregators.
│       6. **81.K.6** — Wired previously-invisible
│          `pointlessql.agent_run.completed/.failed` and
│          `pointlessql.issue.*` fanout call-sites into the feed.
│       7. **81.K.7** — Keyboard nav (j/k/o/e/m/r/?) + per-page
│          help modal + focus-ring affordance.
│       8. **81.K.8** — Per-filter empty-state copy + first-run
│          welcome card.
│       9. **81.K.9** — Activity / Discover top-level tabs
│          (moves right column out of the feed pane → full-width
│          activity).
│       10. **81.K.10** — Drop redundant `<h1>Feed</h1>`,
│           tighter breadcrumb padding.
│       11. **81.K.11** — Breadcrumbs moved into the topbar
│           (~50 px tighter pages).
│       12. **81.K.12** — Layout-toggle chevrons relocated into
│           the topbar (drops the rail header strip).
│       13. **81.K.13** — Discover sub-tabs (Trending / People /
│           Saved as `nav-pills` instead of three narrow
│           third-width cards).
│
│       Track L — Help surface (`67cda6b`):
│       * **81.L** — `/help` reference page (Keyboard / Hidden
│         features / Per-page reference / Glossary / More) +
│         topbar `?`-button next to the theme dropdown.  Deliberate
│         non-goal: no forced product tour, no driver.js /
│         shepherd.js dependency.  Per-page modals (e.g. Feed's
│         `?`-modal) stay as the quick reference; `/help` is the
│         canonical scrollable index.
│
│       Track M — Entity ⋯-menu sweep (`5e2a790`):
│       * **81.M** — `_macros/entity_actions.html` macro renders
│         a Bootstrap dropdown with Copy link, Copy citation,
│         Mute notifications.  Wired into `data_product.html`,
│         `model.html`, `run_view/header.html`.  Reuses the
│         existing `.pql-copy-btn` delegated handler;
│         `entity_actions.js` only adds the mute hop.  One-line
│         macro call ready to drop into table.html,
│         branch_detail.html, etc.
│
│       Close-out fix (`0f7d8b8`):
│       * **81.N.0** — First-run welcome card gated on
│         `filter === 'all'` so it stops stacking below the
│         dedicated empty-states on Mentions / My / Following.
│
│       Final state: 24 commits ahead of `origin/main` at session
│       close (push still queued — release-engineering-timing
│       memory keeps push gated behind explicit auth).  1 Alembic
│       migration (`feed_mutes`).  ~7 new pytest cases.  Static
│       gates all pass (ruff / pyright baseline / pydoclint /
│       file-size / bootstrap-order); the file-size gate picked
│       up `feed_routes.py` (1021 LOC) into the allowlist with a
│       split-candidate note, mirroring `home_routes.py`.
│
```

## Phases 82-85 — Strategic axes (post-81 horizon)

Closed 2026-05-17.

```text
├── Phases 82–85 — Strategic axes (post-81 horizon)         ✅ done 2026-05-17
│   │
│   │   Articulated 2026-05-16.  Three pillars frame the next horizon:
│   │   (1) social integration with DPs = "GitHub feeling" for data
│   │   products, (2) agentic platform access + strong external API,
│   │   (3) easy consumption AND easy authoring of DPs for non-
│   │   technical users.  The phases below decompose the pillars
│   │   into shippable increments; ordering optimised for compounding
│   │   value (ingest first → everything else has data to chew on).
│   │
│   │   Memory anchor:
│   │   `~/.claude/projects/-home-flo-git-PointlesSQL/memory/project_phase82_strategic_axes.md`.
│   │
│   ├── Phase 82 — Ingest UI (critical path)               ✅ done 2026-05-16
│   │   │
│   │   │   Closed in one autonomous session post the "go voll autnom"
│   │   │   green light.  Six commits (82.0 through 82.5), one Alembic
│   │   │   migration (`ingest_sources`), seven first-party connector
│   │   │   kinds wired end-to-end (file_upload, s3, http, postgres,
│   │   │   mysql, sqlite, parquet_glob).  Pyright stays at 498 (no
│   │   │   regression); 60 new pytest cases (57 pass + 3 properly
│   │   │   gated on live-DB env vars).
│   │   │
│   │   │   Picked: all 7 connector kinds in v1 + plaintext + form-
│   │   │   masking credentials (mirrors the audit-sink pattern).
│   │   │   Encryption-at-rest via `system_keys` and the generic
│   │   │   Connector SDK explicitly deferred (audit `phase82` memory
│   │   │   for rationale).
│   │   │
│   │   ├── 82.0 — Foundation: `IngestSource` ORM + Alembic
│   │   │     `m0o2q4s6u8w0`, `pointlessql/services/ingest/`
│   │   │     package (connectors / probe / pull / executor),
│   │   │     `"ingest_pull"` job kind registered with the
│   │   │     Phase-8 scheduler.  Per-kind connector unit tests.
│   │   ├── 82.1 — Probe + Create form: `/ingest/sources/new`
│   │   │     with kind selector + per-kind config block +
│   │   │     `POST /api/ingest/probe` dry-run.  Source CRUD
│   │   │     (`/api/ingest/sources`) with `"***"` secret redaction
│   │   │     on GET and the round-trip-keeps-original rule on PATCH.
│   │   │     Primary rail gains an "Ingest" entry under DATA.
│   │   ├── 82.2 — Table-picker + mappings: `GET /api/ingest/
│   │   │     sources/{id}/tables` probes the source's catalog
│   │   │     (single-row short-circuit for file-based connectors,
│   │   │     `information_schema.tables` / `sqlite_master` for SQL).
│   │   │     `POST /api/ingest/sources/{id}/mappings` persists the
│   │   │     validated per-table pull configurations.
│   │   ├── 82.3 — Pull executor + fanout: `run_pull` carries the
│   │   │     full lifecycle (load source → DuckDB read → PQL write
│   │   │     → stats + fanout) and is reused by the scheduler
│   │   │     executor AND the manual `POST /api/ingest/sources/{id}/
│   │   │     pulls` route.  `PUT /api/ingest/sources/{id}/schedule`
│   │   │     creates / updates / clears the underlying `Job` row.
│   │   │     Pull lifecycle emits `pointlessql.ingest.pulled` /
│   │   │     `.failed` so `/feed` picks them up automatically.
│   │   ├── 82.4 — End-to-end connector coverage: one fixture-driven
│   │   │     test per kind.  File / Parquet / HTTP / SQLite run in
│   │   │     CI; S3 (moto) / live Postgres / live MySQL gate on
│   │   │     env vars.  PullError envelope verified for the bogus-
│   │   │     host failure path.
│   │   └── 82.5 — Health monitor + DP Health-band:
│   │         `/admin/sources` table (admin-only) with per-source
│   │         7-day rollup (status pill, errors, rows, schedule);
│   │         drilldown returns the last 30 JobRuns + per-day
│   │         tallies.  DP detail pages render an inline ingest
│   │         band when one or more sources feed
│   │         `<catalog>.<schema>`, color-coded by last pull
│   │         outcome.
│   │
│   ├── Phase 83 — Saved Views + Visual Query Builder      ✅ done 2026-05-17
│   │   │
│   │   │   Non-tech consumption layer for DPs landed in two
│   │   │   commits.  83.1 ships a new ``saved_views`` table
│   │   │   (alembic ``n1p3r5t7v9x1``) + service + REST + HTML
│   │   │   (list / new / detail / embed pages) so an analyst
│   │   │   saves a parameterised SELECT and a consumer runs it
│   │   │   read-only via ``/views/{slug}``.  83.2 adds a
│   │   │   Grafana-style "Builder" toggle to the SQL editor:
│   │   │   sqlglot-backed forward render + best-effort parse-
│   │   │   back, gracefully degrading on unsupported shapes.
│   │   │   83.3 (embed iframe) ships as part of 83.1's
│   │   │   ``/views/{slug}/embed`` page.  83.4 (Excel grid)
│   │   │   stays explicitly deferred.  34 new pytest cases.
│   │   │
│   │   ├── 83.1 — Saved Views: workspace-public, owner-pinned
│   │   │     ``saved_views`` table + ``${name}`` → ``?`` rewrite
│   │   │     with per-type coercion + DuckDB positional binds.
│   │   │     CRUD + run + list/new/detail/embed pages.
│   │   ├── 83.2 — Visual Query Builder toggle: per-table column
│   │   │     probe + sqlglot-backed forward/back render via
│   │   │     ``api/sql/builder/{operators,columns,build,parse}``.
│   │   │     Alpine mixin on the SQL editor.
│   │   ├── 83.3 — Saved-View embed: minimal-chrome ``/views/
│   │   │     {slug}/embed`` page shipped inside the 83.1 commit.
│   │   └── 83.4 — Excel-grid mode: still deferred per plan.
│   │
│   ├── Phase 84 — DP GitHub-feeling polish                ✅ done 2026-05-17
│   │   │
│   │   │   Bundled into one commit covering all seven sub-axes
│   │   │   on the DP detail page.  One alembic migration
│   │   │   (``o2q4s6u8w0y2_dp_releases``) + three new JSON routes
│   │   │   + one Atom feed.  The DP overview gains six hero
│   │   │   cards (Health band, README, Consume, Schema-at-a-glance,
│   │   │   Releases, Heatmap) plus a Forks list.  6 new pytest
│   │   │   cases.  Also fixes a Phase-82.5 bug where the
│   │   │   ingest-status band read ``product.catalog_name``
│   │   │   (ORM key) instead of ``product.catalog`` (dict key).
│   │   │
│   │   ├── 84.1 — README rendered as a hero card at the top of
│   │   │     the Overview tab, eager-loaded on page open.
│   │   ├── 84.2 — Release stream: ``data_product_releases`` table
│   │   │     + loader hook emits a row on every version / hash
│   │   │     change.  ``GET /releases`` JSON + ``/releases.atom``
│   │   │     feed.  Inline last-5 list on Overview.
│   │   ├── 84.3 — Consume hero: three-tab (PQL / SQL / Python)
│   │   │     copy-paste card with auto-derived FQN from the
│   │   │     first contract table + "Open in notebook" action.
│   │   ├── 84.4 — Health hero band: derived computed property
│   │   │     ``healthBand`` collapses freshness_30d_pct + last
│   │   │     rollback verdict + SLA into a single colour-coded
│   │   │     status block at the top of Overview.
│   │   ├── 84.5 — Schema-at-a-glance: first 10 columns of the
│   │   │     primary table inline (name + type + nullable) with
│   │   │     a "see all" link that activates the Contract tab.
│   │   ├── 84.6 — Contributor heatmap: 12-month GitHub-style
│   │   │     calendar reading from ``AuditLog`` rows whose
│   │   │     ``target = "dp:<catalog>.<schema>"``.  Pure Python
│   │   │     aggregation (no new tables).
│   │   └── 84.7 — Fork ↔ Delta-Branch cross-link: ``GET /forks``
│   │         scans workspace-local ``BranchAuditLog`` for branches
│   │         with ``parent_schema_fqn = "<catalog>.<schema>"`` and
│   │         renders each as a row coloured by last action.
│   │
│   └── Phase 85 — Dataflow Canvas spike                   ✅ done 2026-05-17
│       │
│       │   Bounded prototype + honest decision-gate writeup.
│       │   Closed in one commit.  Six supported node kinds (Read
│       │   DP, Filter, Join, Group-By, Run Model, Write DP) with a
│       │   pure-function compiler + ``/canvas`` HTML editor +
│       │   ``POST /api/canvas/compile`` route.  10 new pytest cases.
│       │
│       │   85.2 decision gate (this session's verdict): **NO** —
│       │   do not commit to a React Flow build-out.
│       │
│       │   The prototype was shipped as a **list-of-rows editor**
│       │   (Alpine + Bootstrap) instead of the planned React Flow
│       │   2D canvas.  Rationale:
│       │
│       │   * **Coherence (✅)**: list shape maps 1:1 to PQL
│       │     primitives.  Top-to-bottom reading order = pipeline
│       │     execution order = ``code.sql()`` line order.  The
│       │     compiler is 130 LOC of pure-function rendering.
│       │     The "Bootstrap-only" frontend rule survives intact.
│       │   * **Round-trip (~)**: forward (canvas → PQL) works
│       │     end-to-end.  Reverse (PQL → canvas) was not
│       │     implemented; sqlglot already parses arbitrary SELECT
│       │     for the Phase 83.2 builder, so a similar effort
│       │     would handle linear pipelines if needed.
│       │   * **Visual scaling (~)**: 20+ list rows are still
│       │     legible; a true 2D canvas would only out-scale the
│       │     list once **branches / fan-out** become a daily
│       │     need.  Today they are not — every real pipeline
│       │     I've watched land in PointlesSQL is linear.
│       │   * **Sunk-cost honesty (✅)**: building React Flow now
│       │     would tax the agent supervision UX (every new node
│       │     kind = three callsites: canvas, compiler, runtime).
│       │     Better to wait until at least one real user has hit
│       │     the "I needed a branch but the list shape forced me
│       │     into two pipelines" pain.
│       │
│       │   Phase 85.3+ (full React Flow build-out, node registry,
│       │   undo/redo, etc.) therefore moves to the unscheduled
│       │   ``Some-day`` block at the end of this file.  The list
│       │   editor stays as a permanent surface — small enough to
│       │   maintain, useful for the "let me sketch the pipeline
│       │   before I write the code" demo flow.
│       │
│       ├── 85.1 — List-mode prototype (✅): 6 node kinds, server-
│       │     side compiler that rejects non-linear or wrong-tail
│       │     pipelines with structured errors.  State persists in
│       │     localStorage; no DB schema commitment.
│       ├── 85.2 — Decision gate (✅, verdict NO): writeup above.
│       └── 85.3+ — Full canvas build-out: deferred to Some-day.
│
```

## Phase 86 — Modularisierungs- & Dedup-Welle

Closed 2026-05-16.

```text
├── Phase 86 — Modularisierungs- & Dedup-Welle             ✅ done 2026-05-16
│       One-wave structural pass on files large enough to push past
│       LLM-comfort and on the cross-cutting helpers that were
│       duplicated file-by-file.  Twelve commits, ~80 files touched,
│       net ~340 lines removed (~6500 inserted vs ~6840 deleted
│       across the wave); every commit boots clean and passes
│       ruff / pyright / pydoclint / alembic gates.  Asset version
│       bumped 0.1.0rc4 → 0.1.0rc5 for the base.html-touching strang.
│
│       ── C.1+C.2 (`d26ed10`) Helper centralisation.  Promotes four
│          per-request helpers into ``api/dependencies.py``:
│          ``get_templates``, ``is_htmx_request``, ``is_htmx_boosted``,
│          ``is_htmx_partial``, ``wants_json``.  Removes 22 identical
│          ``_templates(request)`` defs and 3 hand-rolled HTMX-header
│          checks across the codebase.  25 files touched / 254 LOC
│          deleted vs 191 inserted.
│
│       ── A1-A3 (`e7d0a78`) Frontend mega-templates → page-scoped
│          partials.  ``data_product.html`` 1610 → 206; ``feed.html``
│          1352 → 79; ``notebook_editor.html`` 777 → 225.  20 new
│          partials under ``pages/_partials/{data_product,feed,
│          notebook_editor}/``.  ``x-data`` scopes stay on the mother
│          template; partials inherit them naturally so no Alpine
│          semantics change.  A4 (macro consolidation) trimmed
│          because the 3 candidate patterns are all Alpine-bound,
│          making macros expression-string-only.
│
│       ── B1 (`469e3a4`) ``feed_routes.py`` 1021 → package.
│          ``feed.py`` (482) + ``notifications.py`` (102) +
│          ``muting.py`` (213) + ``_serializers.py`` (256).
│          9 endpoints preserved via facade.
│
│       ── B2 (`fd07577`) ``home_routes.py`` 998 → package.
│          ``summary.py`` (495) + ``search.py`` (487) + ``_helpers.py``
│          (45).  3 endpoints + 3 public helpers preserved via facade
│          (``build_home_summary``, ``score_match``, ``epoch_seconds``).
│
│       ── B3 (`00ce745`) ``jobs_routes.py`` 927 → package.
│          ``crud.py`` (309) + ``runs.py`` (164) + ``papermill.py``
│          (137) + ``pages.py`` (153) + ``_serializers.py`` (170) +
│          ``_access.py`` (108).  14 endpoints + 5 public exports
│          (``JOB_REGISTRY``, ``serialize_job``, ``serialize_run``,
│          ``latest_run_per_job``, ``router``) preserved.
│
│       ── B4 partial (`68dbdf1`) ``main.py`` 1008 → 770.
│          ``_template_filters.py`` (155 LOC; 4 filters + 4 globals +
│          ``register_template_filters``) and ``_template_context.py``
│          (158 LOC; ``install_template_wrapper`` that rebinds
│          ``templates.TemplateResponse`` in place).  Lifespan
│          extraction (~360 LOC) deferred — its 15-local try/finally
│          needs either a dataclass or a class-based manager to land
│          cleanly, bigger than the rest of the wave warrants.
│
│       ── B5 (`7f65aec`) ``alerts_routes.py`` 626 → package.
│          ``crud.py`` (213) + ``destinations.py`` (121) +
│          ``feed_tokens.py`` (66) + ``feeds.py`` (96) + ``pages.py``
│          (115) + ``_helpers.py`` (87).  13 endpoints preserved.
│
│       ── B6 (`c637888`) ``governance_routes.py`` 521 → package.
│          ``profile.py`` (211) + ``catalog.py`` (150) + ``tags.py``
│          (58) + ``permissions.py`` (73) + ``lineage.py`` (32) +
│          ``_helpers.py`` (83).  13 endpoints preserved.
│
│       ── D (`9696608`) Star factory out of base.html.
│          ``window.pqlStarKey`` + ``window.pqlStarToggle`` (121 LOC)
│          → ``frontend/js/star.js``.  ``base.html`` 848 → 726.
│          ``pyproject.toml`` bumped 0.1.0rc4 → 0.1.0rc5 per the
│          asset-version cache-busting contract.  Catalog-visit +
│          table-visit IIFEs in base.html were left in place because
│          they carry Jinja ``active_catalog`` / ``active_table``
│          interpolation.
│
│       ── C.4 (`0f999c3`) Test-fixture cleanup.  Removes 13
│          local ``anonymous_client`` fixture defs that duplicated
│          the conftest's centralised one.  117 LOC deleted;
│          156 tests pass across the touched files.
│
│       ── C.3 + C.5 trimmed.  ``_polymorphic_handlers.py`` (2231) /
│          ``audit/_legacy.py`` (1262) / ``sql/editor.py`` (1127) /
│          ``dbt/routes.py`` (1061) / ``sql/_dispatcher.py`` (1009) /
│          ``config/_settings.py`` (922) each carry hidden coupling
│          (polymorphic dispatch tables, env-prefix conventions,
│          legacy bridges) that would each justify their own sprint;
│          deferred per plan's trim list.  Stale-module audit
│          (``repo_assets``, ``conventions``, ``pointlessql.git``,
│          ``types``) confirmed all four actively imported — but
│          ``repo_assets`` was later proven orphaned in Phase 87.2.
│
```

## Phase 87 — Restschuld I: config + repo_assets + audit

Closed 2026-05-16.

```text
├── Phase 87 — Restschuld I: config + repo_assets + audit  ✅ done 2026-05-16
│       First of three follow-up phases to clear the trim list from
│       Phase 86.  Low-risk strands without business-logic change;
│       three commits on branch ``phase-87-…``, net ~−400 LOC
│       (after subtracting the docstring expansion in the splits).
│       All gates green at every commit (ruff/pyright/pydoclint/
│       alembic); pyright count drops 8→6 errors / 539→533 warnings
│       (from the deleted repo_assets/_loader.py ``workspace_repos``
│       callsites — the underlying bug is unchanged).
│
│       ── 87.1 (`1c4d337`) ``config/_settings.py`` 922 LOC → package.
│          Six topical sub-modules under ``config/_settings/``:
│          ``_auth`` (AuthSettings, OIDCSettings, GroupMapping + the
│          group-map parser), ``_storage`` (DatabaseSettings,
│          DeltaSettings), ``_infra`` (ServerSettings + 5 more),
│          ``_audit`` (AuditSettings + 3 more), ``_features``
│          (SQLSettings + 5 more), ``_integrations`` (JupyterSettings
│          + 4 more), plus ``_paths`` holding the shared STARTUP_CWD
│          / PROJECT_ROOT anchors.  ``Settings()`` instantiation
│          probe confirms 23 fields, all path validators honour
│          their startup-CWD anchor.
│
│       ── 87.2 (`f3c7e07`) ``pointlessql/repo_assets/`` deleted.
│          The Phase-51.3 YAML loader for dashboards + saved queries
│          (428 LOC + a 136-LOC test) was never wired into the
│          workspace-repo sync loop or the manual-sync button — half-
│          finished feature that audit flagged in Phase 86 (zero
│          production imports).  Doc table in
│          ``docs/concepts/git-backed-workspaces.md`` also pruned of
│          its two stale rows + the dashboards/saved_queries YAML
│          block.  If repo-canonical dashboards become a real
│          requirement, a future sprint reintroduces against the
│          conventions / data_products pattern.
│
│       ── 87.3 (`6d2ac2d`) ``audit/_legacy.py`` 1262 LOC → 7 modules.
│          Split by behavioural axis: ``_helpers`` (workspace-lens,
│          ISO-8601 parse, audit-of-audit self-tracking; renamed
│          without leading underscores for cross-module reuse),
│          ``_metrics`` (summary / timeseries / anomalies),
│          ``_principal`` (principal-summary), ``_pii`` (admin-only
│          reveal), ``_history`` (paginated query_history walker),
│          ``_cdf`` (CDF subscriptions + events), ``_anomaly_inbox``
│          (inbox + ack CRUD; named anomaly-prefixed to avoid
│          colliding with the existing ``inbox.py`` HTML cockpit
│          page).  ``_legacy.py`` deleted outright — no backwards-
│          compatibility shim because PointlesSQL isn't published
│          yet and the name was never public API.  Combined audit
│          router still exposes the same 23 paths.
│
```

## Phase 88 — Restschuld II: SQL/dbt cluster

Closed 2026-05-16.

```text
├── Phase 88 — Restschuld II: SQL/dbt cluster              ✅ done 2026-05-16
│       Three medium-risk strands targeting the 1000-LOC SQL editor
│       + dbt cluster.  Three commits on the same ``phase-87…``
│       branch (the wave continues), pyright count stays at
│       6 / 533 errors / warnings at every commit, all gates green.
│
│       ── 88.1 (`ef837c3`) ``sql/_dispatcher.py`` 1009 LOC → 8-module
│          package: ``_types`` (DispatchContext + ExecutionResult),
│          ``_privilege`` (enforce_select_per_table,
│          enforce_modify_target), ``_agent_run`` (start/finish
│          editor agent runs, emit DDL ops), ``_ast_extract``
│          (sqlglot translators), ``_select`` (kept isolated to
│          break the editor↔dispatcher import cycle), ``_dml``
│          (INSERT/CTAS, UPDATE, DELETE, MERGE branches), ``_ddl``
│          (DROP TABLE, CREATE/DROP SCHEMA branches), ``__init__``
│          (dispatch() facade re-exporting DispatchContext,
│          ExecutionResult, PreparedSQL).  Saved-views import
│          rewired from the old private name to the new sibling
│          module.
│
│       ── 88.2 (`05ea3d2`) ``sql/editor.py`` 1127 LOC → 8-module
│          package: ``_helpers`` (short_sql_hash, run_sql_sync,
│          live_queries, run_sql_export_sync, strip_ansi),
│          ``_execute`` (api_sql_execute + inline EXPLAIN
│          serializer, the 284-LOC main route), ``_batch`` (atomic
│          rollback runner + _rollback_run), ``_cancel`` (interrupt
│          endpoint sharing the helpers' live_queries registry),
│          ``_download`` (CSV/Parquet streamer re-running enforcement),
│          ``_explain`` (cost-gate inspector with governance event),
│          ``_page`` (the Jinja2 ``/sql`` route), ``__init__``
│          (facade mounting 6 routers + helper re-exports).
│
│       ── 88.3 (`517a4b6`) ``dbt/routes.py`` 1061 LOC → 5 sibling
│          modules.  Endpoints stay in ``routes.py`` (~350 LOC, 8
│          handlers); helpers move out: ``_executor`` (factory),
│          ``_lifecycle`` (auto-spawned AgentRun create/finish +
│          result_payload), ``_audit`` (classify_severity,
│          emit_dbt_events, model_relations_from_manifest_path,
│          capture_pre_run_versions, emit_audit_for_run),
│          ``_rollback`` (invoke_pql_rollback + auto_rollback_on_error
│          test-only branch), ``_run_test`` (the 133-LOC shared
│          run/test body + load_manifest_or_404).  Three test
│          modules updated to monkeypatch the new sibling modules
│          instead of the routes module.
│
```

## Phase 89 — Restschuld III: endgame

Closed 2026-05-16.

```text
├── Phase 89 — Restschuld III: endgame                     ✅ done 2026-05-16
│       Two highest-risk strands from the Phase-86 trim list:
│       splitting the largest single Python file in the repo
│       (``_polymorphic_handlers.py`` at 2231 LOC) and extracting
│       the 358-LOC lifespan from ``main.py``.  Three commits on
│       the same ``phase-87…`` branch; pyright stays at 6/533 at
│       every commit.
│
│       ── 89.1 (`d1716ce`) ``social_routes/_polymorphic_handlers.py``
│          2231 LOC → 9-axis sub-package.  Sub-modules:
│          ``_shared`` (constants + 9 cross-axis helpers +
│          4 serialisers), ``_comments`` (3 handlers),
│          ``_endorsements`` (3), ``_followers`` (4),
│          ``_reactions_entity`` (3 + ``validate_emoji_field``),
│          ``_reactions_comment`` (3 + ``load_comment_on_target``),
│          ``_stars`` (4), ``_readme`` (2), ``_reviews`` (3).
│          ``__init__`` re-exports every public handler the 7
│          sibling route modules (``comments.py`` /
│          ``endorsements.py`` / ``follows.py`` / ``reviews.py``
│          / ``reactions.py`` / ``stars.py`` / ``readme.py``)
│          already import from this package.  The old flat
│          ``_polymorphic_handlers.py`` deleted outright (no BC
│          shim).  Leading underscores dropped on every
│          cross-axis helper so pyright stops tripping on
│          ``reportPrivateUsage`` across the new module
│          boundaries.
│
│       ── 89.2 (`76e6941`) ``main.py`` lifespan 358 LOC →
│          ``api/_bootstrap/_lifespan.py``.  ``main.py`` shrinks
│          767 → 374 LOC.  The new module exposes a
│          ``make_lifespan(templates)`` factory that closes over
│          the Jinja2Templates instance built at import time in
│          ``main.py`` so the filters + TemplateResponse wrapper
│          stay where they are.  Side-effect: the teardown's 14×
│          repeated cancel-and-await ritual collapses into one
│          ``_cancel_task`` helper.  External behaviour
│          unchanged — ``app.state`` is built identically and the
│          14 background-task names / 2 subprocess shutdown order
│          are byte-identical.
│
```

## Phases 90-92 — Agent-native lakehouse axis (post-Lakebase)

Closed 2026-05-19.

```text
├── Phases 90–92 — Agent-native lakehouse axis (post-Lakebase) ✅ shipped 2026-05-19
│   │
│   │   Articulated 2026-05-19 after a gap-analysis sweep against
│   │   Databricks' May-2026 feature set (AI/BI Genie GA, Lakebase
│   │   GA Feb 2026, ABAC GA Apr 2026, catalog commits May 2026,
│   │   Mosaic AI Vector Search GA).  DBX's pitch — "agents want
│   │   to spin up DBs, branch quickly, persist memory" — directly
│   │   validates the PointlesSQL vision *from the OLTP-Postgres
│   │   side*.  PointlesSQL has the same building blocks
│   │   (``agent_runs``, ``operations``, ``branch_service``,
│   │   audit-stream) but lacks the *naming and API surface* that
│   │   makes them legible as "the agent's persistent memory".
│   │
│   │   Three pillars, ranked by vision-leverage per LOC:
│   │   (1) name + expose the existing memory stack as a primitive,
│   │   (2) wire ``hermes-agent`` into the SQL editor as the
│   │   NL→SQL surface DBX calls "Genie", (3) add Vector Search
│   │   as the third compute primitive next to ``pql.merge`` /
│   │   ``pql.autoload`` so RAG-style retrieval is in-stack.
│   │
│   │   Explicitly NOT pursued (out-of-scope per gap-analysis):
│   │   ABAC policy engine (defer until shoreguard is a standalone
│   │   lib), Lakehouse Monitoring full UI (the
│   │   ``notebooks/agent_drift_monitor.py`` covers 80 %), Model
│   │   Serving (out of mission), Lakeflow Connect / Liquid
│   │   Clustering / DLT-replacement (engine-arms-race that
│   │   PointlesSQL does not win by reimplementing).
│   │
│   ├── Phase 90 — Agent-Memory as first-class primitive       ✅ shipped (local, 2026-05-19)
│   │   │
│   │   │   Smallest diff, largest narrative win.  The
│   │   │   infrastructure is ~80 % already shipped — what's
│   │   │   missing is a single ``pql.memory`` API facade plus a
│   │   │   ``/memory/<agent-id>`` UI page that frames the
│   │   │   existing ``agent_runs`` + ``operations`` + branch
│   │   │   surface as "the agent's persistent memory" instead of
│   │   │   "audit infrastructure".  Directly counters Lakebase's
│   │   │   "persistent memory for AI agents" positioning with
│   │   │   the Delta-first / append-only angle (Lakebase is
│   │   │   Postgres-first; agent writes are dominantly append-
│   │   │   only logs which Delta serves more cheaply).
│   │   │
│   │   │   Shipped 2026-05-19 at ~2510 LOC across 9 sub-strands
│   │   │   (5 facade methods + Alembic migration + 4 routes + 7
│   │   │   templates + JS + walkthrough + concept doc + 62 tests).
│   │   │   Scope grew vs the original 400-LOC sketch because the
│   │   │   user picked "Voll-Scope" — real replay-dispatcher with
│   │   │   policy gate, polymorphic comment integration with
│   │   │   Alembic migration, full Playwright walkthrough.  See
│   │   │   ``docs/concepts/agent-memory.md`` for the conceptual
│   │   │   model and the Lakebase comparison.
│   │   │
│   │   ├── 90.0 — ``pql.memory`` facade + replay-dispatcher  ✅ shipped
│   │   │     [`pointlessql/pql/memory.py`](pointlessql/pql/memory.py)
│   │   │     exposing the five public methods, plus the
│   │   │     [`services/agent_runs/memory/`](pointlessql/services/agent_runs/memory/)
│   │   │     package backing them (recall SELECT, branch-from-run,
│   │   │     replay dispatcher with REPLAYABLE / DATA_UNAVAILABLE /
│   │   │     UNSAFE op classification + STRICT/SKIP_UNSAFE/LENIENT
│   │   │     policy).  Replay-execution scoped to "intent-only"
│   │   │     for Phase 90 — re-records ops against the replay run
│   │   │     with ``_replay_recorded_only: true``, real DuckDB
│   │   │     execution lands with Phase 91 (same plumbing
│   │   │     requirement).  49 unit tests.
│   │   ├── 90.1 — ``/memory/<agent-id>`` UI + comment surface  ✅ shipped
│   │   │     Alembic migration ``p4r6t8v0x2z4`` extends
│   │   │     ``social_targets.entity_kind`` CHECK to accept
│   │   │     ``agent_memory``; new entity-registry spec defines
│   │   │     the discussion/endorsements/followers tab strip.
│   │   │     HTML route + 3 JSON routes
│   │   │     (recall / branch / replay).  ``memory.html`` plus
│   │   │     5 page-scoped partials (header, timeline,
│   │   │     operations, branches, social) and
│   │   │     ``memory_brain.js`` (memoryRecall + memoryDiscussion
│   │   │     Alpine factories + replay-button handler).
│   │   │     ``asset_version`` bumped to 0.1.0rc6.  13 route
│   │   │     tests.  Replayed via
│   │   │     ``docs/e2e-walkthroughs/agent_memory.md``.
│   │   ├── 90.2 — Counter-pitch concept doc                  ✅ shipped
│   │   │     [`docs/concepts/agent-memory.md`](docs/concepts/agent-memory.md)
│   │   │     frames the Delta-first / append-only angle vs
│   │   │     Lakebase's Postgres-first.  Cross-link from
│   │   │     ``agent-supervision.md``, new ``Agent memory`` nav
│   │   │     entry in ``mkdocs.yml`` and concept-index.
│   │
│   ├── Phase 91 — NL→SQL via hermes-agent wiring             ✅ shipped (local, 2026-05-19)
│   │   │
│   │   │   The DBX "Genie" equivalent.  In-process
│   │   │   ``hermes_agent.AIAgent`` wired into the SQL editor
│   │   │   via a JSON-RPC WebSocket; ``hermes-plugin-pointlessql``
│   │   │   tools (``pql_query`` + 3 new chat-focused tools)
│   │   │   stamp every call on the chat session's ``agent_run``
│   │   │   so Phase 90's ``/memory/<agent-id>`` page shows the
│   │   │   full conversation trace.  Non-SELECT SQL never runs
│   │   │   silently — ``pql_propose_sql`` drops a draft into a
│   │   │   "Run / Discard" banner.
│   │   │
│   │   ├── 91.0 — WebSocket chat transport + drawer            ✅ shipped
│   │   │     [`pointlessql/api/sql_chat_ws.py`](pointlessql/api/sql_chat_ws.py)
│   │   │     mounts ``/ws/sql/chat/{editor_session_id}`` with
│   │   │     the notebook-WS JSON-RPC envelope (prompt / cancel
│   │   │     / refine / reset).  Per-turn ``AIAgent`` runs on a
│   │   │     dedicated ThreadPoolExecutor; the streaming
│   │   │     callback bridges through the per-session broker
│   │   │     ([`services/sql_chat/`](pointlessql/services/sql_chat/))
│   │   │     so tokens, tool-phase sentinels, and proposals all
│   │   │     pass through one ordered queue.  Alembic migration
│   │   │     ``q5s7u9w1y3a5`` adds ``editor_chat_sessions`` +
│   │   │     ``chat_proposals``.  Right-side drawer template +
│   │   │     ``chatPanel()`` Alpine factory shipped under
│   │   │     [`frontend/templates/pages/_partials/sql_editor/`](frontend/templates/pages/_partials/sql_editor/)
│   │   │     and [`frontend/js/sql_editor/chat.js`](frontend/js/sql_editor/chat.js).
│   │   │     ``asset_version`` bumped to 0.1.0rc7.
│   │   ├── 91.1 — Tool-set hardening                           ✅ shipped
│   │   │     Three new tools in ``hermes-plugin-pointlessql``:
│   │   │     ``pql_describe_columns_with_stats`` (live PQL→pandas
│   │   │     reduction, 5-min LRU cache, new
│   │   │     [`pointlessql/services/column_stats/`](pointlessql/services/column_stats/)
│   │   │     service + ``GET .../tables/{t}/stats`` route);
│   │   │     ``pql_save_query`` (wraps existing ``POST /api/views``);
│   │   │     ``pql_propose_sql`` (registered only when
│   │   │     ``POINTLESSQL_CHAT_SESSION_ID`` is set).
│   │   │     ``pql_run_select_capped`` was dropped — the
│   │   │     existing ``pql_query`` already caps to 10 000
│   │   │     rows.  Server-side propose endpoint
│   │   │     [`pointlessql/api/sql_chat_routes/_propose.py`](pointlessql/api/sql_chat_routes/_propose.py)
│   │   │     classifies via sqlglot (rejects SELECT/EXPLAIN),
│   │   │     enforces ``X-Agent-Run-Id`` ownership, and
│   │   │     dedupes identical SQL within 60 s.
│   │   ├── 91.2 — Run-it gate + audit-mirroring               ✅ shipped
│   │   │     [`pointlessql/api/sql_chat_routes/_accept.py`](pointlessql/api/sql_chat_routes/_accept.py)
│   │   │     adds ``POST .../proposals/{id}/accept|discard``;
│   │   │     accept returns the chat session's ``agent_run_id``
│   │   │     so the editor's normal Run path stamps
│   │   │     ``X-Agent-Run-Id`` and the DELETE / UPDATE /
│   │   │     CREATE operation lands on the chat run alongside
│   │   │     every tool-call.  Stale proposals (>24 h) auto-
│   │   │     flip to ``expired`` instead of running.  Shoreguard
│   │   │     policy cross-link deferred to a follow-up sprint
│   │   │     (hook point documented in
│   │   │     [`docs/concepts/nl-to-sql.md`](docs/concepts/nl-to-sql.md)).
│   │   ├── 91.3 — Conversational refinement loop              ✅ shipped
│   │   │     ``refine`` WS method templates structured user
│   │   │     prompts for the two canonical failure modes
│   │   │     (``zero_rows``, ``error``) and runs them through
│   │   │     the normal turn pipeline — each refine appends to
│   │   │     the same ``conversation_json`` so the
│   │   │     ``/memory/<agent-id>`` timeline shows the full
│   │   │     refinement trace.  Frontend buttons appear next to
│   │   │     0-row results + error banners.
│   │   ├── 91.4 — Concept doc + walkthrough + nav             ✅ shipped
│   │   │     [`docs/concepts/nl-to-sql.md`](docs/concepts/nl-to-sql.md)
│   │   │     frames the architecture + the DML gate + the
│   │   │     LLM-config env vars.
│   │   │     [`docs/e2e-walkthroughs/sql_chat.md`](docs/e2e-walkthroughs/sql_chat.md)
│   │   │     covers the 6-step Playwright playbook.  Cross-link
│   │   │     from ``agent-supervision.md``, new nav entries
│   │   │     under ``Concepts`` and the "Working with data"
│   │   │     walkthrough cluster.
│   │
│   └── Phase 92 — Vector-Search compute primitive            ✅ shipped (local, 2026-05-19)
│       │
│       │   Third compute primitive next to ``pql.merge`` and
│       │   ``pql.autoload``.  Backed by the DuckDB ``vss``
│       │   extension (HNSW indices) stored side-by-side with
│       │   the Delta table (Delta remains source-of-truth;
│       │   the index is a secondary structure rebuilt on every
│       │   merge via the post-commit hook in
│       │   ``operations._lifecycle``).  Completes the
│       │   "persistent memory for agents" loop: Phase 90 gives
│       │   agents *what to remember*, Phase 91 gives them *how
│       │   to ask*, Phase 92 gives them *how to retrieve
│       │   semantically*.
│       │
│       │   ROADMAP-adjustment (close-out): the originally
│       │   planned hermes-agent ``embed`` tool does not exist
│       │   yet, so the **default embedder inverts** to
│       │   ``sentence-transformers`` (local, zero-config) with
│       │   the ``openai`` SDK as an optional hosted provider
│       │   and a documented :class:`HermesEmbedder` stub
│       │   reserved for when hermes-agent ships an ``embed``
│       │   tool.
│       │
│       ├── 92.0 — ``pql.vector_index`` primitive             ✅ shipped
│       │     [`pointlessql/pql/_vector.py`](pointlessql/pql/_vector.py)
│       │     adds ``PQL.vector_index(table, column, ...)`` +
│       │     ``PQL.vector_search(...)`` next to ``merge`` /
│       │     ``autoload``.  HNSW index file lives at
│       │     ``<table.storage_location>/_vss/<column>.duckdb``;
│       │     persistent HNSW enabled via
│       │     ``hnsw_enable_experimental_persistence = true`` in
│       │     [`_vss_engine.py`](pointlessql/pql/_vss_engine.py).
│       │     New ``OpName.VECTOR_INDEX`` + ``VECTOR_SEARCH``
│       │     extend the ``agent_run_operations.op_name`` CHECK
│       │     (Alembic ``r6t8v0x2z4a6``).  ``VectorIndex`` ORM
│       │     keyed by ``(workspace, catalog, schema, table,
│       │     column)``.
│       ├── 92.1 — Embedder registry + auto-rebuild hook      ✅ shipped
│       │     [`pointlessql/pql/embedders/`](pointlessql/pql/embedders/)
│       │     ships ``SentenceTransformersEmbedder`` (default,
│       │     lazy import; new ``[vector]`` extra),
│       │     ``OpenAIEmbedder`` (optional, ``OPENAI_API_KEY``),
│       │     and a documented ``HermesEmbedder`` stub.
│       │     Sixth post-commit hook
│       │     [`_vector_rebuild.py`](pointlessql/services/agent_runs/operations/_vector_rebuild.py)
│       │     wired into ``operation_context`` re-embeds the
│       │     affected column on every ``merge`` / ``write_table``
│       │     / ``autoload`` / ``update`` / ``delete`` /
│       │     ``branch_promote`` / ``dbt_model`` commit.
│       │     Failure is non-fatal: stamps
│       │     ``vector_indices.last_error`` and continues.
│       ├── 92.2 — REST surface                                ✅ shipped
│       │     [`pointlessql/api/sql/vector_search/`](pointlessql/api/sql/vector_search/)
│       │     mounts ``POST /api/sql/vector_search`` (reuses
│       │     ``enforce_select_per_table``),
│       │     ``POST /api/sql/vector_search/indices`` +
│       │     ``GET`` + ``DELETE …/{id}`` (workspace-admin
│       │     gated for write paths), and
│       │     ``GET /embed/semantic_search/{fqn}`` for the
│       │     iframe share URL.  RFC 9457 envelopes
│       │     (``404 vector-index-missing``,
│       │     ``403 forbidden``).
│       ├── 92.3 — Hermes-plugin tool                          ✅ shipped
│       │     ``hermes_plugin_pointlessql/tools/vector_search.py``
│       │     adds ``pql_vector_search`` (registered
│       │     unconditionally) calling the new
│       │     ``PointlessClient.vector_search()`` HTTP wrapper.
│       │     Closes the RAG loop end-to-end: chat panel agents
│       │     can do semantic retrieval before generating SQL.
│       ├── 92.4 — UI surface on Table-detail                  ✅ shipped
│       │     Conditional ``Semantic search`` tab on
│       │     [`table.html`](frontend/templates/pages/table.html)
│       │     guarded by ``{% if vector_indices %}``.  Alpine
│       │     factory ``semanticSearch()`` in
│       │     [`frontend/js/table/semantic_search.js`](frontend/js/table/semantic_search.js)
│       │     owns column picker + query + result-table state.
│       │     Embed view at
│       │     [`semantic_search_embed.html`](frontend/templates/pages/semantic_search_embed.html)
│       │     mirrors the saved-view embed pattern for share
│       │     URLs.  ``asset_version`` bumped to ``0.1.0rc8``.
│       └── 92.5 — Docs + tests                                ✅ shipped
│             Concept doc
│             [`docs/concepts/vector-search.md`](docs/concepts/vector-search.md)
│             frames the architecture, embedder strategy, and
│             privilege model.  Playbook
│             [`docs/e2e-walkthroughs/vector_search.md`](docs/e2e-walkthroughs/vector_search.md)
│             walks the 8-step loop.  19 new pytest cases
│             covering embedder registry, primitive (create /
│             search / rebuild / dim mismatch), merge-hook,
│             and REST route.  All green; ``alembic check``
│             clean.
│
```

## Phase 93 — Notebook-Editor UX quick wins

Closed 2026-05-19.

```text
├── Phase 93 — Notebook-Editor UX quick wins                  ✅ shipped (local, 2026-05-19)
│       Six surgical fixes after the Phase-12.12 editor wire-up
│       brought the toolbar back into rotation and Playwright
│       replays revealed several visual rough edges.  All
│       frontend-only; one ``pyproject.toml`` version bump
│       (``0.1.0rc12`` → ``0.1.0rc13``) busts the asset cache.
│
│       1. **Toolbar title vertical-rendering bug** — flex-child
│          ``.pql-notebook-path`` collapsed buchstabenweise next
│          to 15 sibling pills because ``word-break: break-all``
│          + missing ``min-width: 0``.  Switched to single-line
│          ellipsis with ``:title`` tooltip and gave the toolbar
│          ``flex-wrap`` so overflow goes to a new row instead.
│       2. **Toolbar grouping** — three ``.pql-toolbar-group``
│          clusters: ``[Interrupt · Restart]``,
│          ``[Save · Schedule · Run as job]``,
│          ``[Jobs · Variables]``.  Inlined the floating
│          ``⌘S`` kbd hint into the Save button.
│       3. **Native prompt/confirm → Bootstrap modals** — new
│          ``notebookDialogs()`` mixin spread into
│          ``notebookWorkspace()``; new partial
│          ``pages/_partials/notebooks_workspace/notebook_modals.html``
│          with create/rename + delete modals.  Client-side
│          validation: ``.py`` suffix, no leading ``/``, no
│          ``..`` segments, no double-slashes.  Modal toggle via
│          ``:class="{ 'show d-block': flag }"`` (Alpine 3.14 +
│          ``.modal`` quirk — memory
│          ``feedback_bootstrap_modal_x_show``).
│          *Close-out fix:* ``openCreate`` / ``openRename`` /
│          ``openDeleteDialog`` mutate the dialog state fields
│          individually instead of replacing the dialog object as
│          a whole.  Replacing a nested reactive object detaches
│          Alpine bindings that captured deps on the old proxy —
│          the ``:disabled`` binding on the submit button stopped
│          re-evaluating in particular.  Caught during live
│          browser verification, fixed at source.
│       4. **Output iframe dark-theme fix** —
│          [`output_renderer.js`](frontend/js/notebook/output_renderer.js)
│          reads ``document.documentElement.dataset.bsTheme``
│          and bakes matching ``color`` / ``border`` / ``th-bg``
│          into the srcdoc.  Wrapper CSS
│          ``.pql-notebook-output__iframe`` flipped from
│          ``background: white`` to ``transparent`` with
│          ``color-scheme: light dark``.
│       5. **Workspace "New notebook…" CTA** — dropped the
│          inline ``font-size: 0.75rem`` + ``btn-sm`` shrink;
│          now a normal-size ``btn-primary`` with
│          ``bi-plus-lg`` icon, refresh moved to ``ms-auto``.
│       6. **Sidebar ``.ipynb`` chip detox** —
│          [`workspace_sidebar.js`](frontend/js/components/sidebars/workspace_sidebar.js)
│          ``formatBadge()`` now returns
│          ``bg-info-subtle text-info-emphasis`` for ``.py`` and
│          ``bg-secondary-subtle text-secondary-emphasis`` for
│          ``.ipynb`` — no more orange warning-looking pill.
│
```

## Phase 94 — Notebook-Editor UX polish

Closed 2026-05-19.

```text
├── Phase 94 — Notebook-Editor UX polish                       ✅ shipped (local, 2026-05-19)
│       Follow-up polish bundle to Phase 93.  Adds the visual
│       structure Jupyter users expect (Out[N] frame, run-duration
│       display) without touching the backend.  Wall-clock duration
│       is captured client-side via ``performance.now()`` between
│       the ``execute_input`` and ``execute_reply`` frames —
│       persistent duration after reload would need backend
│       timestamp propagation through the iopub WS (deferred to a
│       later phase).  Asset version bumped to ``0.1.0rc14``.
│
│       1. **Cell-header hash to tooltip** — the 8-char FNV
│          ``content_hash`` slice next to ``[N]`` is now a tooltip
│          on the ``[N]`` element itself; the separate visible
│          span is gone.
│       2. **Out[N] output frame** — new
│          ``.pql-notebook-cell__output-zone`` wrapper with a small
│          ``Out[N]:`` label header above the output container.
│          The output zone gets a top border only when the cell has
│          actually executed (``exec_count != null``), keeping
│          never-run cells visually quiet.
│       3. **Run duration display** — new ``runDurationFor(cell)``
│          helper in [`notebook_editor.js`](frontend/js/notebook/notebook_editor.js)
│          formats the client-side wall-clock ms into ``0.2s`` /
│          ``1.4s`` / ``2m 3s``.  Captured in
│          [`kernel_execution.js`](frontend/js/notebook/kernel_execution.js)
│          on ``execute_input`` (stamp) → ``execute_reply``
│          (delta).  Shown next to ``[N]`` in the cell header.
│       4. **Clear-output per cell** — new ``_clearOutput(cell)``
│          method in [`markdown_output.js`](frontend/js/notebook/markdown_output.js)
│          drops the live-output buffer + duration for one cell
│          without re-running it.  Triggered by the small ``×`` in
│          the new Out[N] label header.
│       5. **Workspace action-cluster spacing** — filename span
│          now has ``flex-grow-1`` + ``min-width: 0`` + ``:title``
│          so long names ellipsis-truncate instead of crowding the
│          Edit / Schedule / ⋯ buttons.
│
```
