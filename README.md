# PointlesSQL

A web UI for a Python-only Databricks-compatible lakehouse stack --
built on top of [soyuz-catalog](https://github.com/FloHofstetter/soyuz-catalog)
(a Python Unity Catalog REST server), Delta Lake, and optionally
Apache Spark.

## Status

**Phase 1 MVP complete.** PointlesSQL ships three integrated
capabilities:

1. **Catalog browser** -- browse catalogs, schemas, tables, and
   columns in a dark-mode web UI with inline metadata editing
2. **PQL library** -- `from pointlessql import PQL` -- read and write
   Delta tables as pandas DataFrames using Unity Catalog metadata
3. **Embedded notebook** -- a JupyterLab tab with sidebar navigation
   so you can browse catalog metadata while working in a notebook

See [`ROADMAP.md`](ROADMAP.md) for the full sprint history and
upcoming phases.

## Stack

- **Python 3.14**, managed with [`uv`](https://docs.astral.sh/uv/)
- **FastAPI + Uvicorn** for the web UI backend
- **Jinja2 templates** + **Bootstrap 5.3** + **HTMX** + **Alpine.js**
- **`soyuz-catalog-client`** -- typed, generated httpx wrapper for
  the Unity Catalog REST API
- **Delta Lake** (`deltalake>=0.24`) -- storage format for managed
  tables
- **pandas** (`>=2.2`) -- DataFrame engine for PQL
- **JupyterLab** (`>=4.0`) -- embedded notebook server
- **SQLAlchemy 2.0 + Alembic** -- for our own metadata DB (sessions,
  UI preferences); soyuz-catalog owns the lakehouse metadata
- **pytest / ruff / pyright / pydoclint / pre-commit**

## Architecture

```text
+---------------------------------+        +------------------------+
| PointlesSQL                     |        | soyuz-catalog          |
| (FastAPI + Jinja2, :8000)       |        | (FastAPI, :8080)       |
|                                 | HTTP   |                        |
|  Web UI - soyuz_catalog_client -+------->|  Unity Catalog REST    |
|  PQL   - soyuz_catalog_client --+------->|  + over-the-spec       |
|                                 |        |    extensions          |
|  JupyterLab subprocess (:8888)  |        +----------+-------------+
|  - embedded via iframe          |                   |
+---------------------------------+                   v
                                           +------------------------+
                                           | Delta Lake / storage   |
                                           +------------------------+
```

PointlesSQL and soyuz-catalog are **separate processes**.
PointlesSQL imports the typed client library and talks to
soyuz-catalog over HTTP -- no shared Python state, no shared
database.

## Quick start (Docker)

Run the full stack with a single command:

```bash
docker compose up --build
```

This starts:

- **soyuz-catalog** on <http://localhost:8080>
- **PointlesSQL** on <http://localhost:8000>
- **JupyterLab** on <http://localhost:8888>

Delta tables are stored in `./warehouse/` (bind-mounted into both
containers). Notebooks are stored in `./notebooks/`.

**Prerequisites:** Docker Engine 24+ with Compose v2.17+ (for
`additional_contexts`). The `soyuz-catalog` repo must be checked
out at `../soyuz-catalog/` (sibling directory).

> The first build takes a few minutes to install Python 3.14
> dependencies. Subsequent builds use Docker layer caching.

## Quick start (local development)

This assumes you have `~/git/soyuz-catalog` checked out as a
sibling of this repository, since the generated client is
installed as an editable path dependency during development.

**1. Start soyuz-catalog:**

```bash
cd ~/git/soyuz-catalog
uv sync
uv run soyuz-catalog
# listening on http://127.0.0.1:8080
```

**2. Start PointlesSQL:**

```bash
cd ~/git/PointlesSQL
uv sync
uv run pointlessql
# listening on http://127.0.0.1:8000
```

**3. Browse the catalog:**

Open <http://127.0.0.1:8000> in a browser. The sidebar shows all
catalogs, schemas, and tables from soyuz-catalog. Click through
to see metadata, column schemas, and edit comments and properties
inline.

**4. Use PQL in the notebook:**

Click the **Notebook** tab in the navbar. JupyterLab starts
automatically. In a new notebook cell:

```python
from pointlessql import PQL

pql = PQL()

# List what's in the catalog
pql.list_catalogs()

# Read a Delta table as a DataFrame
df = pql.table("my_catalog.my_schema.my_table")

# Write a DataFrame back as a new table
import pandas as pd
df = pd.DataFrame({"id": [1, 2, 3], "value": [10.5, 20.0, 30.7]})
pql.write_table(df, "my_catalog.my_schema.new_table")
```

New tables appear immediately in the sidebar.

## Development

```bash
uv run pytest                # unit tests
uv run pytest -m integration # integration tests (needs live soyuz)
uv run ruff check            # lint
uv run pyright               # type-check
uv run pre-commit run -a     # all hooks
```

If `uv sync` complains about a missing `soyuz-catalog-client`,
it is because the editable path dependency points at
`../soyuz-catalog/soyuz-catalog-client`. Either check out
soyuz-catalog next to this repo or edit `pyproject.toml` /
`uv.lock` to point at a different location.

## Configuration

PointlesSQL is configured via environment variables:

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_SOYUZ_CATALOG_URL` | `http://127.0.0.1:8080` | soyuz-catalog server URL |
| `POINTLESSQL_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` in Docker) |
| `POINTLESSQL_PORT` | `8000` | HTTP port |
| `POINTLESSQL_DATABASE_URL` | `sqlite:///./pointlessql.db` | SQLAlchemy database URL |
| `POINTLESSQL_SECRET_KEY` | `change-me-in-production` | JWT signing key |
| `POINTLESSQL_JUPYTER_ENABLED` | `true` | Enable embedded JupyterLab |
| `POINTLESSQL_JUPYTER_PORT` | `8888` | JupyterLab port |

## Relationship to other repos

- [`soyuz-catalog`](https://github.com/FloHofstetter/soyuz-catalog)
  -- the UC REST server PointlesSQL talks to
- `~/git/delta` -- Delta Lake Python bindings
- `~/git/unitycatalog` -- upstream JVM reference (kept for spec
  contracts only)
- `~/git/spark` -- optional; relevant once PointlesSQL grows into
  query execution

## License

Apache-2.0. See [`LICENSE`](LICENSE).
