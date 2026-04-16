# Claude instructions for PointlesSQL

This file is read automatically by Claude Code at the start of every
session in this repository. It captures conventions that are not
enforceable by linters but matter for the long-term readability of
the codebase.

## Vision

PointlesSQL is a **functional Databricks clone built from Python-only
open-source parts**. We do not rebuild the query engine — we wire a
web UI and a thin orchestration layer on top of existing components:

- **[soyuz-catalog](../soyuz-catalog)** — Python reimplementation of
  the Unity Catalog REST API. Spec-compatible with the upstream
  `unitycatalog/unitycatalog` Java server, plus over-the-spec
  extensions (lineage, tags, effective permissions, table
  constraints, foreign catalogs / Lakehouse Federation).
  PointlesSQL is soyuz-catalog's first real-world UI consumer.
- **Delta Lake** (`~/git/delta`) — storage format and Python bindings.
- **Apache Spark** (`~/git/spark`) — optional query runtime; only
  used if/when PointlesSQL grows beyond metadata browsing.

## Phase 1 MVP (complete)

A "mini-Databricks" where the user can:

1. **Browse UC metadata** in a web UI (catalogs → schemas → tables
   → columns), edit comments and properties inline
2. **Read and write Delta tables** as pandas DataFrames via the
   `PQL` helper library, which resolves table names through
   soyuz-catalog
3. **Work in a notebook** via an embedded JupyterLab tab with
   sidebar navigation

The UI is a FastAPI + Jinja2 application that talks to soyuz-catalog
over HTTP using the generated typed client that ships with
soyuz-catalog (Sprint 20 / ADR-0007 in that repo).

## Stack

- Python 3.14, managed with `uv` + hatchling
- FastAPI + Uvicorn, Jinja2 templates, static assets served from
  `frontend/`
- Bootstrap 5.3 + HTMX + Alpine.js for the frontend
- `deltalake>=0.24` + `pandas>=2.2` — the PQL DataFrame bridge
- `jupyterlab>=4.0` — embedded notebook server
- SQLAlchemy 2.0 + Alembic — for *our own* metadata only (user
  sessions, UI preferences, saved queries). soyuz-catalog owns the
  lakehouse metadata; PointlesSQL never writes to it directly
  except through the generated client's HTTP calls
- **`soyuz-catalog-client`** as an editable path dependency during
  local development (see ["Wiring soyuz-catalog"](#wiring-soyuz-catalog)
  below)
- httpx for any UC endpoints not yet exposed by the generated
  client (should be rare — the Sprint 12 conformance test and
  Sprint 21 drift gate in soyuz make sure the client stays complete)
- pytest / ruff / pyright / pre-commit — matching the `shoreguard-fresh`
  project style

## Layout

- `pointlessql/api/main.py` — FastAPI entrypoint, `cli()` runs uvicorn
- `pointlessql/services/` — business logic:
  - `soyuz_client.py` — factory for a configured
    `soyuz_catalog_client.Client`
  - `unitycatalog.py` — async facade over the generated client
  - `jupyter.py` — JupyterLab subprocess lifecycle manager
- `pointlessql/pql/` — sync bridge between UC metadata and Delta
  Lake DataFrames (`PQL` class, column mapping, name parsing)
- `pointlessql/settings.py` — pydantic-settings (soyuz URL, Jupyter
  config)
- `pointlessql/alembic/` — migrations for our own metadata DB
- `frontend/templates|css|js` — force-included into the wheel on build
- `notebooks/` — starter notebooks shipped with the project
- `tests/` — pytest suite (`@pytest.mark.integration` for live-server
  tests)

## Wiring soyuz-catalog

soyuz-catalog runs as a **separate process**. The dependency graph is:

```text
PointlesSQL (FastAPI web UI)
    │
    │ imports (Python)
    ▼
soyuz_catalog_client  (generated, typed httpx wrapper)
    │
    │ HTTP over localhost
    ▼
soyuz-catalog  (FastAPI server, own process)
```

### Local development

In `~/git/soyuz-catalog` start the server in one terminal:

```bash
uv run soyuz-catalog       # listens on http://127.0.0.1:8080
```

In this repo, the generated client is an **editable path
dependency** on the soyuz-catalog workspace:

```bash
uv add --editable ../soyuz-catalog/soyuz-catalog-client
uv run pointlessql         # listens on http://127.0.0.1:8000
```

The editable install means soyuz-catalog's
`scripts/regen_client.sh` regenerations are picked up immediately
on the next Python reload — no `uv sync` round-trip. The trade-off
is that `uv sync` will fail on any machine where
`../soyuz-catalog` is not checked out. That is acceptable for
local development; a future PointlesSQL packaging sprint (tracked
on `ROADMAP.md`) will swap the path dependency for a PyPI pin
once soyuz-catalog cuts a release.

### Don't start the JVM UC server

Earlier drafts of this file pointed at
`~/git/unitycatalog/bin/start-uc-server` (the JVM reference
implementation). That is no longer the target — soyuz-catalog
pins `all.yaml` as its contract, so every UC REST endpoint
PointlesSQL needs is already there, plus the over-the-spec
extensions the JVM server does not have. The JVM checkout is
kept around only as a reference for `all.yaml` and `delta.yaml`.

## Where we are

**Read [`ROADMAP.md`](ROADMAP.md) first.** It is the single source
of truth for what is done, what is in progress, and what is next.
Every sprint update lands there with its commit hash. Do not
invent new milestone or sprint names — extend the existing tree.

## Replaying the e2e walkthroughs

`docs/e2e-walkthroughs/` holds ten deterministic Markdown
playbooks (five data-surface from Sprint 22, five orchestration
+ operational from Sprint 23). Each one can be replayed by a
human with a browser or by Claude Code through the
`mcp__playwright__browser_*` tool family. The Sprint 23
orchestration + operational playbooks use host env overlays
(`POINTLESSQL_JUPYTER_ENABLED`, `POINTLESSQL_LOG_FORMAT`,
`POINTLESSQL_OIDC_*`, etc.) exposed by
`docker-compose.e2e.yml` via `${…:-default}` — see
[`docs/e2e-walkthroughs/README.md`](docs/e2e-walkthroughs/README.md)
for the full table. When connecting a Playwright MCP server,
pass `--browser firefox` (or the playwright-bundled
`chrome-for-testing`, not the system `chrome` channel) —
Sprint 22 commit `3f1da76` has the backstory. Any future sprint
that touches HTML or JS should replay the relevant playbook
before landing; fixes for bugs surfaced in a replay land in the
same commit if trivial, otherwise as a `BUG-NN-NN` TODO with a
named fix location at the bottom of the playbook.

## Conventions

- Apache-2.0 license
- Match shoreguard-fresh code style and project layout — same
  ruff / pyright / pre-commit config
- Google-style docstrings enforced by pydoclint; the docstring
  policy mirrors soyuz-catalog's: summary line + blank line +
  body that explains the *why*, never just restates the signature
- Conventional Commits (`feat(ui): …`, `fix(client): …`,
  `docs(roadmap): …`). Scope is the subsystem touched
  (`ui`, `client`, `auth`, `alembic`, `docs`, …)
- **Never write directly to soyuz-catalog tables**. All lakehouse
  metadata flows through the generated client. Our own Alembic
  schema is for session / preference / audit rows only
- **Update `ROADMAP.md` and `CHANGELOG.md`** for every sprint
  landing — same discipline as soyuz-catalog
- **Fix bugs at the source, never work around them.** Both
  PointlesSQL and soyuz-catalog (including `soyuz-catalog-client`)
  are our repos. When a bug surfaces in a dependency we own, fix
  it there instead of adding a workaround here. This keeps both
  codebases clean and avoids stale workaround code that outlives
  the bug
