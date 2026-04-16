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
├── Phase 3 — Auth & multi-user                           🔜 next
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
│   ├── Sprint 7 — Principal forwarding + enforcement     🔜 next
│   │   ├── Forward authenticated principal to soyuz via
│   │   │   `X-Principal` header on all client calls
│   │   ├── Enforcement middleware: before each soyuz
│   │   │   proxy call, check `GET /permissions/...` for
│   │   │   the current user's principal — 403 if missing
│   │   ├── Admin bypass: `is_admin` users skip enforcement
│   │   ├── `403 Forbidden` error page with "request access"
│   │   │   hint
│   │   ├── Permissions UI: show current user's own grants
│   │   │   prominently, grey out actions they can't perform
│   │   ├── Audit log: store who-did-what in a local
│   │   │   `audit_log` table (user_id, action, target,
│   │   │   timestamp)
│   │   └── Tests: enforcement tests (allowed/denied),
│   │       admin bypass, principal header forwarding
│   │
│   └── Sprint 8 — OIDC / OAuth2 provider                ⏳ planned
│       ├── OAuth2 authorization code flow with PKCE
│       ├── Settings: `oidc_discovery_url`, `oidc_client_id`,
│       │   `oidc_client_secret` (optional, for confidential
│       │   clients)
│       ├── Map OIDC claims (sub, email, name) to local User
│       ├── Auto-create user on first OIDC login
│       ├── Login page: "Sign in with SSO" button alongside
│       │   local login form (both remain available)
│       ├── `/auth/callback` route for OAuth2 redirect
│       └── Tests: OIDC flow with mocked provider
│
├── Phase 4 — Pluggable compute engines                   🧊 on ice
│   │
│   │   Vision: user picks a "kernel profile" (container image
│   │   or local venv) with a specific engine. The pql helper
│   │   abstracts the engine; the notebook just calls
│   │   `pql.table(...)` and gets back the engine's native
│   │   frame type.
│   │
│   ├── Polars engine                                     🧊 on ice
│   │   └── `DeltaTable.to_pyarrow()` → `pl.from_arrow()`
│   │
│   ├── Spark engine                                      🧊 on ice
│   │   └── PySpark kernel with UC connector configured
│   │       by PointlesSQL at startup
│   │
│   └── DuckDB engine                                     🧊 on ice
│       └── `DeltaTable` → DuckDB via PyArrow
│
├── Phase 5 — Infrastructure & orchestration              🧊 on ice
│   │
│   ├── docker-compose for the full stack                 🧊 on ice
│   ├── Postgres sync tool (foreign catalog mirror)       🧊 on ice
│   └── Minimal DAG job engine                            🧊 on ice
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
