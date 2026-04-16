# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
