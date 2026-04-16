# PointlesSQL

A web UI for a Python-only Databricks-compatible lakehouse stack —
built on top of [soyuz-catalog](https://github.com/FloHofstetter/soyuz-catalog)
(a Python Unity Catalog REST server), Delta Lake, and optionally
Apache Spark.

## Status

Early alpha. First milestone: a web UI for soyuz-catalog — browse
catalogs, schemas, tables, columns; inspect tags, permissions, and
lineage; manage Lakehouse Federation connections and foreign
catalogs.

See [`ROADMAP.md`](ROADMAP.md) for what is done, in progress, and
planned.

## Stack

- **Python 3.14**, managed with [`uv`](https://docs.astral.sh/uv/)
- **FastAPI + Uvicorn** for the web UI backend
- **Jinja2 templates**, static assets served from `frontend/`
- **SQLAlchemy 2.0 + Alembic** for our own metadata DB (sessions,
  UI preferences) — soyuz-catalog owns the lakehouse metadata
- **`soyuz-catalog-client`** — the typed, generated httpx wrapper
  shipped by soyuz-catalog (Sprint 20 / ADR-0007). Editable path
  dependency during local development
- **pytest / ruff / pyright / pydoclint / pre-commit**

## Architecture at a glance

```text
┌──────────────────────────┐        ┌────────────────────────┐
│ PointlesSQL              │        │ soyuz-catalog          │
│ (FastAPI + Jinja2, 8000) │ HTTP   │ (FastAPI, 8080)        │
│                          │◄──────►│                        │
│  soyuz_catalog_client    │ REST   │  Unity Catalog REST    │
└──────────────────────────┘        │  + over-the-spec       │
                                    │    extensions          │
                                    └──────────┬─────────────┘
                                               │
                                               │ optional
                                               ▼
                                    ┌────────────────────────┐
                                    │ Postgres / Delta Lake  │
                                    │ (foreign catalogs,     │
                                    │  managed storage)      │
                                    └────────────────────────┘
```

PointlesSQL and soyuz-catalog are **separate processes**.
PointlesSQL imports the typed client library and talks to
soyuz-catalog over HTTP — no shared Python state, no shared
database.

## Running locally

This assumes you have `~/git/soyuz-catalog` checked out as a
sibling of this repository, since the generated client is
installed as an editable path dependency during development.

**Terminal 1** — start soyuz-catalog:

```bash
cd ~/git/soyuz-catalog
uv sync
uv run soyuz-catalog
# listening on http://127.0.0.1:8080
```

**Terminal 2** — start PointlesSQL:

```bash
cd ~/git/PointlesSQL
uv sync
uv run pointlessql
# listening on http://127.0.0.1:8000
```

Open <http://127.0.0.1:8000> in a browser.

If `uv sync` in this repo complains about a missing
`soyuz-catalog-client`, it is because the editable path
dependency points at `../soyuz-catalog/soyuz-catalog-client`.
Either check out soyuz-catalog next to this repo or edit
`pyproject.toml` / `uv.lock` to point at a different location.

## Development

```bash
uv run pytest                # unit tests
uv run ruff check             # lint
uv run pyright                # type-check
uv run pre-commit run -a      # all hooks
```

Integration tests (marked `@pytest.mark.integration`) spin up a
local soyuz-catalog instance and exercise the real wire path.
They are deselected by default — run with
`uv run pytest -m integration` when you need them.

## Relationship to other repos

- [`soyuz-catalog`](https://github.com/FloHofstetter/soyuz-catalog)
  — the UC REST server PointlesSQL talks to. Drives the source of
  truth for every wire shape the UI renders.
- `~/git/delta` — Delta Lake Python bindings, used by soyuz-catalog
  for the `/delta/preview/commits` surface.
- `~/git/unitycatalog` — upstream JVM reference implementation,
  kept only as a source for `all.yaml` / `delta.yaml` (the spec
  contracts soyuz-catalog pins).
- `~/git/spark` — optional; only relevant once PointlesSQL grows
  beyond metadata browsing into actual query execution.

## License

Apache-2.0. See [`LICENSE`](LICENSE).
