# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

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
