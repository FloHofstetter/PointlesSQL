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
3. **Native notebook editor** -- a first-party Monaco-based editor
   (Phase 12.6) with pyright LSP, per-notebook ipykernel, Variable
   Explorer, Insert-from-Catalog command, and autosaved
   ``.py`` jupytext Percent-format files.  Replaced the Sprint-3
   JupyterLab iframe in Sprint 63

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
- **`jupyter_client`** (`>=8.6`) + **`ipykernel`** (`>=6.29`) --
  per-notebook kernel subprocess for the native editor (Sprint 59)
- **`pyright`** (`>=1.1`) -- language server for completion / hover
  / diagnostics in the native editor (Sprint 61)
- **`jupytext`** (`>=1.16`) -- ``.py`` Percent format as the
  native-editor on-disk source of truth (Sprint 58)
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
|  Native editor + pyright LSP +  |        +----------+-------------+
|  per-notebook ipykernel         |                   |
+---------------------------------+                   v
                                           +------------------------+
                                           | Delta Lake / storage   |
                                           +------------------------+
```

PointlesSQL and soyuz-catalog are **separate processes**.
PointlesSQL imports the typed client library and talks to
soyuz-catalog over HTTP -- no shared Python state, no shared
database.

## Quick start (Docker + GHCR images)

Zero-build install — both images pull from GHCR. No source
checkout required. Full detail including PAT-creation and
troubleshooting in [`docs/install.md`](docs/install.md).

**1. Log in to GHCR** with a classic PAT that has `read:packages`:

```bash
echo "$GHCR_PAT" | docker login ghcr.io -u <your-github-username> --password-stdin
```

**2. Download the reference compose file into a fresh directory:**

```bash
mkdir ~/pointlessql && cd ~/pointlessql
curl -L -o docker-compose.yml \
  https://raw.githubusercontent.com/FloHofstetter/PointlesSQL/v0.1.0rc3/docker-compose.yml
```

**3. Flip both services from `build:` to `image:`** — in each
service comment out the `build:` block and uncomment the `image:`
line directly above it. See [`docs/install.md`](docs/install.md)
for the exact two-line edit.

**4. Pull and start:**

```bash
docker compose pull
docker compose up -d
```

- **soyuz-catalog** on <http://localhost:8080>
- **PointlesSQL** on <http://localhost:8000>

Delta tables are stored in `./warehouse/` (bind-mounted into both
containers). Notebooks are stored in `./notebooks/` as
``.py`` jupytext Percent-format files (Sprint 63 retired the
JupyterLab iframe; see the [migration note](#migrating-from-the-jupyterlab-iframe-sprint-63)).

## Quick start (local development)

Source-checkout flow for contributors. See
[`docs/install.md`](docs/install.md) for the full three-flavour
guide.

**1. Start soyuz-catalog:**

```bash
git clone git@github.com:FloHofstetter/soyuz-catalog.git ~/git/soyuz-catalog
cd ~/git/soyuz-catalog
uv sync
uv run soyuz-catalog
# listening on http://127.0.0.1:8080
```

**2. Start PointlesSQL:**

```bash
git clone git@github.com:FloHofstetter/PointlesSQL.git ~/git/PointlesSQL
cd ~/git/PointlesSQL
uv sync
uv run pointlessql
# listening on http://127.0.0.1:8000
```

`uv sync` fetches the private `soyuz-catalog-client` wheel at the
pinned git tag using your shell's existing git credentials — an
ssh key against `git@github.com` is the simplest setup. If you
want edits to `../soyuz-catalog` to surface without a tag bump,
`bash scripts/use-editable-soyuz.sh` swaps the pin to the sibling
checkout.

**3. Browse the catalog:**

Open <http://127.0.0.1:8000> in a browser. The sidebar shows all
catalogs, schemas, and tables from soyuz-catalog. Click through
to see metadata, column schemas, and edit comments and properties
inline.

**4. Use PQL in the notebook:**

Click the **Notebook** tab in the navbar.  The native Monaco-based
editor (Phase 12.6) opens at ``notebooks/scratch.py``.  In a new
code cell:

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

## Migrating from the JupyterLab iframe (Sprint 63)

Phase 12.6 Sprint 63 retired the embedded JupyterLab subprocess
that Sprint 3 set up.  The native editor that replaced it supports
**``.py`` jupytext Percent-format notebooks only** — papermill-
generated ``.ipynb`` files under ``notebooks/runs/`` continue to
work as run artefacts and the workspace browser still lists
``.ipynb`` uploads for scheduling.

If you have hand-authored ``.ipynb`` files you want to keep editing:

```bash
jupytext --to py:percent notebooks/my_notebook.ipynb
```

This produces ``notebooks/my_notebook.py``; the editor picks it up
on open and assigns UUIDs to every cell on first save (ADR 0001 in
``docs/adr/0001-notebook-editor.md`` explains the ``pql_cell_id``
marker format).

The ``jupyterlab`` pypi dep is gone, ``POINTLESSQL_JUPYTER_PORT``
is no longer listened on (the setting stays for backward-compat but
does nothing), the ``/notebook`` URL now 302-redirects to
``/notebook/editor?path=scratch.py``, and the job-detail page's
``Open in JupyterLab`` deep-link became a ``Download ipynb``
button.

## Development

```bash
uv run pre-commit install    # one-time: arm git hook
uv run pytest                # unit tests
uv run pytest -m integration # integration tests (needs live soyuz)
uv run ruff check            # lint
uv run pyright               # type-check
uv run pre-commit run -a     # all hooks
```

If `uv sync` fails to fetch `soyuz-catalog-client`, confirm your
shell has git credentials for the private soyuz-catalog repo (an
ssh key against `github.com`, or a classic PAT wired through
`git config --global url.insteadOf`). See
[`docs/install.md`](docs/install.md) Troubleshooting for the full
checklist.

## Configuration

PointlesSQL is configured via environment variables:

Sprint 45 split the flat `Settings` into nine sub-models with
per-sub-model `env_prefix`. Every variable below follows the
`POINTLESSQL_<SUBMODEL>_<FIELD>` pattern; see `.env.example` for
the full list and `CHANGELOG.md` for the Sprint-45 rename map.

| Variable | Default | Description |
|---|---|---|
| `POINTLESSQL_SOYUZ_CATALOG_URL` | `http://127.0.0.1:8080` | soyuz-catalog server URL |
| `POINTLESSQL_SERVER_HOST` | `127.0.0.1` | Bind address (`0.0.0.0` in Docker) |
| `POINTLESSQL_SERVER_PORT` | `8000` | HTTP port |
| `POINTLESSQL_DB_URL` | `sqlite:///./pointlessql.db` | SQLAlchemy database URL |
| `POINTLESSQL_AUTH_SECRET_KEY` | `change-me-in-production` | JWT signing key |
| `POINTLESSQL_JUPYTER_ENABLED` | `true` | Enable embedded JupyterLab |
| `POINTLESSQL_JUPYTER_PORT` | `8888` | JupyterLab port |

## Jobs

PointlesSQL includes an in-process scheduler that can run multi-task
DAGs on a cron schedule. Two job kinds ship out of the box:
`pg_sync` (the Postgres-to-UC mirror) and `python` (an entry-point
loader for user-authored executors). See
[`docs/jobs.md`](docs/jobs.md) for how to author a custom job kind,
the executor signature, the optional failure webhook, and a worked
example that uses `pql` inside a task.

Prometheus metrics are exposed at `GET /metrics` (admin-only).

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
