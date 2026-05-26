# Full OpenAPI reference

The complete REST surface auto-generated from the FastAPI app's
OpenAPI schema. ~500 routes across 51 routers; the hand-curated
[top-30 overview](../api.md) is the friendly intro layer that
sits above this auto-reference.

The schema is dumped to `docs/reference/_generated/openapi.json`
by a pre-commit hook (`scripts/dump-openapi.py`) that fires
whenever any file under `pointlessql/api/` changes, so the
rendered reference cannot drift from the actual route surface.

[OAD(../_generated/openapi.json)]
