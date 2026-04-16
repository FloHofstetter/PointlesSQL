# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

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
