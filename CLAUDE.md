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

## What it is today

The UI is a FastAPI + Jinja2 application that talks to soyuz-catalog
over HTTP through the generated typed client. The Phase 1 MVP — a
"mini-Databricks" to (1) browse UC metadata (catalogs → schemas →
tables → columns) with inline comment/property edits, (2) read and
write Delta tables as pandas DataFrames via the `PQL` library, and
(3) work in a notebook — shipped long ago.

The product has since grown well beyond that into a broad lakehouse
surface: an audit cockpit with per-cell lineage, data products /
data mesh, dbt, an ML registry, agent runs, real-time co-edited
notebooks (CRDT), Lakehouse Federation, governance / policy-as-code,
and an admin console. **`ROADMAP.md` is the single source of truth**
for what is done, in progress, and next — read it before assuming a
feature does or does not exist. `pointlessql/services/` (~80 modules)
and `pointlessql/api/` are the fastest way to see the real surface.

## Stack

- Python 3.14, managed with `uv` + hatchling
- FastAPI + Uvicorn, Jinja2 templates, static assets served from
  `frontend/`
- Bootstrap 5.3 + HTMX + Alpine.js for the frontend
- `deltalake>=0.24` + `pandas>=2.2` — the PQL DataFrame bridge
  (`duckdb` + `polars` + `pyarrow` + `sqlglot` back the SQL paths)
- `jupytext` + `papermill` + `nbconvert` + `jupyter_client` /
  `ipykernel` — the native notebook editor and scheduled execution;
  `pycrdt` drives real-time co-edit (a CRDT whose wire format is
  byte-compatible with Y.js). The Phase 1 embedded-JupyterLab tab is
  gone
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

- `pointlessql/api/` — FastAPI app. `main.py` builds the `app` and
  exposes `cli()` (runs uvicorn with a project-scoped reload watcher);
  the rest is route modules, one package/file per surface (`audit/`,
  `lineage/`, `runs_routes/`, `data_products_routes/`, `mesh_*`,
  `notebook_*`, `*_ws.py` WebSocket handlers, …)
- `pointlessql/services/` — business logic (~80 modules). Entry points:
  - `soyuz_client.py` — factory for a configured
    `soyuz_catalog_client.Client`
  - `unitycatalog/` — async facade package over the generated client.
    **All UC calls route through it** — direct `soyuz_catalog_client.api`
    imports from `api/` are banned by a ruff `flake8-tidy-imports` rule
- `pointlessql/pql/` — the sync `PQL` bridge between UC metadata and
  Delta Lake DataFrames (name parsing, column mapping, SQL/merge
  translation, time-travel, branches, vector search)
- `pointlessql/config/` — pydantic-settings (`Settings` + nested
  per-subsystem `BaseSettings`) and logging; `get_settings()` is the
  cached accessor. (This is the old `settings.py`.)
- `pointlessql/models/` + `pointlessql/db.py` — SQLAlchemy ORM and
  engine/session wiring for *our own* metadata DB
- `pointlessql/alembic/` — migrations for that DB
- Other top-level packages: `cli/` (admin CLIs), `conventions/`,
  `data_products/`, `git/` (provider abstraction), `types/`, `web/`,
  `data/notebook_templates/`
- `frontend/templates|css|js|fonts` — force-included into the wheel
  on build (Jinja templates, Bootstrap/HTMX/Alpine JS, biome-linted)
- `notebooks/` — starter notebooks shipped with the project
- `tests/` — pytest suite (`@pytest.mark.integration` for live-server
  tests). `e2e/` (sibling, not under `tests/`) holds the Playwright
  browser tests; see the markers in `pyproject.toml`

## Commands

`uv` drives everything; there is no Makefile. Setup and running the
app live under ["Wiring soyuz-catalog"](#wiring-soyuz-catalog)
(`uv sync`, then `uv run pointlessql`). The local gates below mirror
CI exactly ([`.github/workflows/test.yml`](.github/workflows/test.yml)) —
run them before opening a PR.

```bash
# Tests — the default run excludes integration/e2e/postgres markers
# (pyproject addopts) and only collects tests/ (not the e2e/ sibling)
uv run pytest                                   # full unit suite
uv run pytest -n auto                           # parallel (pytest-xdist)
uv run pytest tests/test_pql_aggregate.py            # one file
uv run pytest tests/test_pql_aggregate.py::test_name # one test
uv run pytest -k pattern                         # by name substring
uv run pytest -m integration                     # needs a live soyuz-catalog
uv run pytest e2e/ -m e2e                        # Playwright; `playwright install chromium` first

# Lint / format / types / docstrings
uv run ruff check .                              # add --fix to autofix
uv run ruff format .                             # --check in CI
uv run pyright                                   # strict; errors must stay at 0
uv run pydoclint --style=google pointlessql/
biome check frontend/js/                         # --write to fix; config in biome.json

# Drift + budget gates (pure shell, no venv needed)
bash scripts/check-file-size-budget.sh           # 800-LOC/file cap + allowlist
bash scripts/check-pyright-budget.sh             # frozen pyright warning floor
bash scripts/check-no-phase-refs.sh              # phase/sprint/BUG markers in frontend/

# Our own metadata DB (SQLite locally; a Postgres lane runs in CI)
uv run alembic upgrade head
uv run alembic check                             # autogen-drift gate (ORM ↔ migrations)
uv run alembic revision --autogenerate -m "..."

# Docs site (uses the `docs` dependency group only)
uv run --group docs --no-default-groups mkdocs build   # --strict in CI

# Arm the hooks (runs most of the above on each commit)
uv run pre-commit install
uv run pre-commit install --hook-type commit-msg       # Conventional-Commits gate
```

The Postgres dialect lane needs `TEST_DATABASE_URL` (and
`POINTLESSQL_DB_URL`) pointed at a live Postgres; CI runs it as its
own job so SQLite-only DDL drift surfaces before deploy.

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

### Local development — default (clean-machine)

In `~/git/soyuz-catalog` start the server in one terminal:

```bash
uv run soyuz-catalog       # listens on http://127.0.0.1:8080
```

In this repo, `soyuz-catalog-client` is pinned to a **public
GitHub tag** under `[tool.uv.sources]`:

```toml
soyuz-catalog-client = {
  git = "https://github.com/FloHofstetter/soyuz-catalog",
  tag = "v0.3.0rc3",
  subdirectory = "soyuz-catalog-client",
}
```

`uv sync` fetches that wheel over HTTPS with **no credentials** —
soyuz-catalog is a public repository. A sibling `../soyuz-catalog`
checkout is not required; `git clone && uv sync` works on a truly
empty host.

```bash
uv sync
uv run pointlessql         # listens on http://127.0.0.1:8000
```

### Local development — editable escape hatch

When you are iterating on soyuz-catalog itself and want
`scripts/regen_client.sh` regens to surface without a tag bump,
flip `pyproject.toml`'s `[tool.uv.sources]` to an editable path
dep on the sibling checkout. Two helper scripts do the swap in
place:

```bash
bash scripts/use-editable-soyuz.sh   # git-tag pin → editable ../soyuz-catalog path
# …iterate on soyuz-catalog, regen client, uv run pointlessql, etc.
bash scripts/use-pinned-soyuz.sh     # restore pyproject.toml + uv.lock from HEAD
```

The editable swap leaves `pyproject.toml` dirty on purpose — that
is the signal you are in escape-hatch mode. Do not commit the
swapped `pyproject.toml`; run `use-pinned-soyuz.sh` (or
`git restore pyproject.toml uv.lock`) before committing anything
else on main.

An earlier attempt at a gitignored `uv.toml` with a `[sources]`
block is **not** supported by uv — `sources` is only valid inside
a `pyproject.toml`'s `[tool.uv.sources]` table. The swap-in-place
approach above is the working replacement.

### Docker builds

The Dockerfile fetches the soyuz-catalog-client wheel from its
public git tag with no credentials. Contributors who build both
images from a local checkout layer the dev override (which needs a
sibling `../soyuz-catalog` checkout for the soyuz build context):

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up --build
```

### GHCR images (recommended for end users)

Every `v*` tag push fires
[`.github/workflows/docker.yml`](.github/workflows/docker.yml),
which builds and pushes both images to GHCR under the repo-owner
namespace:

- `ghcr.io/flohofstetter/pointlessql:<tag>`
- `ghcr.io/flohofstetter/soyuz-catalog:<pinned-soyuz-tag>`

The packages are public, so `docker/docker-compose.yml` pulls them
with no `docker login`. The default `docker compose up` is a pure
pull-and-run install — no source checkout, no credentials. Pin a
release with `PQL_VERSION` / `SOYUZ_VERSION`.
[`docs/getting-started/installation.md`](docs/getting-started/installation.md)
walks through the flow.

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

Older completed phases are collapsed into a summary table; their
per-sprint detail lives in
[`docs/internal/roadmap_archive.md`](docs/internal/roadmap_archive.md).  Read the archive only
when investigating a specific old decision — `ROADMAP.md` alone
covers all current and recently-closed work.

## Replaying the e2e walkthroughs

`docs/e2e-walkthroughs/` holds 50 deterministic Markdown
playbooks covering every UI surface PointlesSQL ships
(catalog browsing, lineage, run-detail, ML registry,
branches, audit cockpit, federation, admin console, dbt,
etc.). Each one can be replayed by a human with a browser
or by Claude Code through the `mcp__playwright__browser_*`
tool family. The Sprint 23
orchestration + operational playbooks use host env overlays
(`POINTLESSQL_JUPYTER_ENABLED`, `POINTLESSQL_LOG_FORMAT`,
`POINTLESSQL_OIDC_*`, etc.) exposed by
`docker/docker-compose.e2e.yml` via `${…:-default}` — see
[`docs/e2e-walkthroughs/README.md`](docs/e2e-walkthroughs/README.md)
for the full table. When connecting a Playwright MCP server,
pass `--browser firefox` (or the playwright-bundled
`chrome-for-testing`, not the system `chrome` channel) —
Sprint 22 commit `3f1da76` has the backstory. Any future sprint
that touches HTML or JS should replay the relevant playbook
before landing; fixes for bugs surfaced in a replay land in the
same commit if trivial, otherwise as a `BUG-NN-NN` TODO with a
named fix location at the bottom of the playbook.

If Playwright-MCP fails to launch Firefox with `process did exit:
exitCode=0` *immediately* after `<launched>` (juggler-pipe never
completes the handshake), the profile dir has a stale lock. Check
`~/.cache/ms-playwright/mcp-firefox-*/lock` — it is a symlink whose
target encodes the owning PID (`127.0.1.1:+<pid>`). If that PID is
dead (`ps -p <pid>` shows no row), just `rm` the symlink and
retry. Firefox itself runs fine standalone in that state, so the
smoke test is to launch firefox by hand with the bundled binary
before suspecting the install.

If `claude mcp list` reports `playwright ✓ Connected` but
`ToolSearch` finds no `mcp__playwright__*` tools (any query
returns `No matching deferred tools found`), the MCP subprocess
is running but its tool schemas were not registered into the
session's deferred-tool surface at startup. There is no reload
command (`claude mcp` exposes only add/remove/list/get/serve);
the only fix is to exit and restart Claude Code. Confirm by
calling `ToolSearch` with
`select:mcp__playwright__browser_navigate` — empty result means
restart needed. The CLI process being healthy is necessary but
not sufficient for the in-session tool surface.

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
- **Modularize before the hard 800-LOC budget bites.** The
  `check-file-size-budget.sh` gate hard-fails at 800 LOC, but the
  practical seam is earlier: a flat route module past ~450 LOC, or
  an Alpine factory / service module past ~700, should split. The
  project's house style is **package-with-re-export-facade** — turn
  `foo.py` into a `foo/` package whose `__init__.py` re-exports every
  public name (and any symbol other modules import by path), so
  `from … import foo` callers never change. For routes, give each
  sub-module its own `APIRouter` and combine them in `__init__`
  (`api/data_products_routes/` is the template); shared helpers go in
  a `_shared.py` and are made public if imported across sub-modules.
  For Alpine factories, compose `installX(state)` mixin installers
  (`feed.js` / `data_product.js` / `dp_canvas_editor.js`). Keep splits
  behaviour-preserving: move bodies verbatim and, where there are no
  runtime tests (JS), verify with a structural-equivalence harness.
  Do **not** split a cohesive single-surface module just to chase a
  number — a false seam is worse than a long-but-coherent file.
  Caveat: splitting a module that tests monkeypatch **by string**
  moves the patch target — retarget those tests in the same commit.
- **Fix bugs at the source, never work around them.** Both
  PointlesSQL and soyuz-catalog (including `soyuz-catalog-client`)
  are our repos. When a bug surfaces in a dependency we own, fix
  it there instead of adding a workaround here. This keeps both
  codebases clean and avoids stale workaround code that outlives
  the bug
- **Source comments + docstrings MUST NOT reference Phase /
  Sprint / Wave numbers or BUG-NN-NN markers.** That metadata
  belongs in `ROADMAP.md` + `CHANGELOG.md` + git history only.

  Why: phase tags read as cryptic insider language to anyone
  outside the project, and they rot — "Phase 99" means nothing
  once Phase 200 is the current frontier. A comment that needs
  phase context to be understood has the wrong shape; rewrite
  it as a feature description.

  Scope (this rule applies uniformly to every commented source
  format the project carries):
  - Python comments + docstrings (`#`, `"""..."""`)
  - Jinja template comments (`{# ... #}`)
  - HTML comments (`<!-- ... -->`)
  - JavaScript comments (`//`, `/* ... */`)
  - CSS comments (`/* ... */`)
  - **User-facing strings rendered to the UI**: badge text,
    tooltip `title=`, alert / toast bodies, modal labels. These
    are even worse than comments — end users see them and "Phase
    85.1 prototype" reads as untranslated developer chatter.

  Exception (single, narrow): the **docstring bodies** of
  `pointlessql/alembic/versions/*.py` migration files. A migration's
  docstring narrates a schema change that already shipped, so it may
  reference the phase/sprint it landed in — that is the historical
  record, not live project-management noise, and scrubbing the frozen
  migrations would only lose the cross-reference to ROADMAP.md /
  CHANGELOG.md anchors. Migration *filenames* and revision ids carry no
  phase tags: they are sequential `NNNN_slug.py` with a matching
  `revision = "NNNN"` (soyuz-catalog's convention). A new migration
  takes the next number, hand-assigned with
  `alembic revision --rev-id <NNNN> -m "<slug>"`.

  Enforcement: `scripts/check-no-phase-refs.sh` runs as a local
  pre-commit hook scoped to `frontend/` + `pointlessql/`
  (excluding `alembic/versions/`).  Clean baseline; drift
  protection.
