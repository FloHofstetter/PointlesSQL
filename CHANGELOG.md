# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added

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
