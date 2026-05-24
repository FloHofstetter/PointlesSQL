# PointlesSQL

**Per-cell auditable lakehouse for agent-driven data engineering, EU-AI-Act-native.**

A web UI and Python bridge over
[soyuz-catalog](https://github.com/FloHofstetter/soyuz-catalog)
(Unity-Catalog REST), Delta Lake, and MLflow — with a forced
audit trail every agent action falls into, at the row, column,
and value level.

📚 **Documentation**: run `uv run mkdocs serve` and open
<http://127.0.0.1:8000>.  The docs site goes public as part of
the public launch; until then, browse the markdown source under
[`docs/`](docs/).

## Why PointlesSQL

The EU AI Act (Article 12), SOC 2, and GDPR all require verifiable
audit trails for data work performed by automated systems. Agents
writing notebooks today leave no per-row, per-column, per-value
lineage — when an auditor or incident-responder asks *"which agent
run produced this value, from which inputs, using which prompt and
model?"*, the answer has to be reconstructed by hand from logs that
were never designed to carry that semantic load.

PointlesSQL closes that gap as part of the runtime, not as an
add-on observability layer:

- **Forced audit trail** at row, column, and value level — every
  PQL write, merge, branch, rollback, and read goes into
  `agent_run_operations` automatically. Opt-out is a deliberate
  config decision, not the default.
- **Branch isolation per agent run** — Delta-Lake-native shallow
  clones let each agent run write to an isolated branch that
  promotes via human review.
- **First-class rollback** — `pql.rollback(run_id)` is a
  supervised action with cryptographic preview, not a manual
  Delta `RESTORE` ritual.
- **Review-bot infrastructure** — the same audit primitives feed
  a daily Audit-Reviewer, a Compliance-Bot, and an Incident-
  Responder agent, so the audit trail becomes actionable rather
  than just stored.

PointlesSQL doesn't replace your query engine, your catalog, or
your agent framework — it composes them under a forced-audit
contract.

## Status

Production stack with the following surfaces shipped:

- **Catalog browser** with inline metadata edit
- **PQL library** — `from pointlessql import PQL` — read / write
  / merge / branch / rollback Delta tables by UC name
- **Audit Cockpit** — `agent_run_operations` with row, column,
  value, and inference-level lineage
- **Native notebook editor** with pyright LSP, per-notebook
  ipykernel, and real-time CRDT-based multi-tab co-edit
- **MLflow registry surface** with champion/challenger promotion
  and forced-autolog training audit
- **Delta branching** — shallow-clone branches per agent run with
  control-room promote/discard/preview UI
- **External SQL API** — DBX-compatible `/api/2.0/sql/statements`
  with per-API-key catalog + IP ACLs and usage aggregation
- **Audit-Reviewer agent infrastructure** — three personas
  (daily reviewer, compliance bot, incident responder) backed by
  the same audit primitives

See [`ROADMAP.md`](ROADMAP.md) for the per-sprint detail and
[`CHANGELOG.md`](CHANGELOG.md) for release notes.  The
[concepts overview](docs/getting-started/concepts.md) is the
ten-minute read that links the pieces together.

## Stack

- **Python 3.14**, managed with [`uv`](https://docs.astral.sh/uv/)
- **FastAPI + Uvicorn**, Jinja2 + Bootstrap 5.3 + HTMX + Alpine
- **`soyuz-catalog-client`** — typed httpx wrapper for UC REST
- **`deltalake` + `pandas` + `polars` + `duckdb`** — PQL bridge
- **`jupyter_client` + `ipykernel` + `pyright` + `jupytext`** —
  notebook editor
- **SQLAlchemy 2.0 + Alembic** — own metadata DB (sessions, UI
  preferences, audit trail); soyuz-catalog owns the lakehouse
  metadata
- **`mlflow`** — registry subprocess
- **pytest + ruff + pyright + pydoclint + pre-commit**

## Architecture

```mermaid
graph TB
    subgraph "PointlesSQL (this repo)"
        UI[Web UI · Audit Cockpit]
        PQL[PQL bridge]
        ML[MLflow subprocess]
    end
    subgraph "soyuz-catalog"
        SC[Unity Catalog REST]
    end
    subgraph "Storage"
        DL[Delta Lake]
    end

    UI -->|httpx| SC
    PQL -->|httpx| SC
    PQL -->|deltalake| DL
    UI -->|deltalake read| DL
    ML -->|register MODEL| SC

    style UI fill:#5C6BC0,color:#fff,stroke:#3F51B5
    style PQL fill:#5C6BC0,color:#fff,stroke:#3F51B5
    style ML fill:#5C6BC0,color:#fff,stroke:#3F51B5
```

PointlesSQL and soyuz-catalog are **separate processes**.
PointlesSQL imports the typed client library and talks to
soyuz-catalog over HTTP — no shared Python state, no shared
database.

## Quick start (Docker + GHCR images)

Zero-build install — both images pull from GHCR. No source
checkout required. Full detail including PAT-creation and
troubleshooting in [`docs/getting-started/installation.md`](docs/getting-started/installation.md).

**1. Log in to GHCR** with a classic PAT that has `read:packages`:

```bash
echo "$GHCR_PAT" | docker login ghcr.io -u <your-github-username> --password-stdin
```

**2. Download the reference compose file into a fresh directory:**

```bash
mkdir ~/pointlessql && cd ~/pointlessql
curl -L -o docker/docker-compose.yml \
  https://raw.githubusercontent.com/FloHofstetter/PointlesSQL/v0.1.0rc3/docker-compose.yml
```

**3. Flip both services from `build:` to `image:`** — in each
service comment out the `build:` block and uncomment the `image:`
line directly above it. See [`docs/getting-started/installation.md`](docs/getting-started/installation.md)
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
``.py`` jupytext Percent-format files; the JupyterLab iframe was
retired in favour of the native editor (see the
[migration note](#migrating-from-the-jupyterlab-iframe)).

## Quick start (local development)

Source-checkout flow for contributors. See
[`docs/getting-started/installation.md`](docs/getting-started/installation.md) for the full three-flavour
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
editor opens at ``notebooks/scratch.py``.  In a new code cell:

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

## Migrating from the JupyterLab iframe

The embedded JupyterLab subprocess that the early prototype set up
has been retired.  The native editor that replaced it supports
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
``docs/decisions/0001-notebook-editor.md`` explains the ``pql_cell_id``
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
[`docs/getting-started/installation.md`](docs/getting-started/installation.md) Troubleshooting for the full
checklist.

## Configuration

PointlesSQL is configured via environment variables.  Every
variable follows the `POINTLESSQL_<SUBMODEL>_<FIELD>` pattern;
see `.env.example` for the full list.

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
[`docs/guides/jobs.md`](docs/guides/jobs.md) for how to author a custom job kind,
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

## Contributing

PRs welcome. See [`CONTRIBUTING.md`](CONTRIBUTING.md) for the
development environment, local gates, and PR conventions. Bugs and
feature requests go through GitHub Issues (pick the right template
from the *New Issue* picker).

## Security

Vulnerabilities should be reported privately. See
[`SECURITY.md`](SECURITY.md) for the responsible-disclosure path.

## License

Apache-2.0. See [`LICENSE`](LICENSE) and [`NOTICE.txt`](NOTICE.txt).
