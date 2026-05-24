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

### Local development — default (clean-machine)

In `~/git/soyuz-catalog` start the server in one terminal:

```bash
uv run soyuz-catalog       # listens on http://127.0.0.1:8080
```

In this repo, `soyuz-catalog-client` is pinned to a **private
GitHub tag** under `[tool.uv.sources]`:

```toml
soyuz-catalog-client = {
  git = "https://github.com/FloHofstetter/soyuz-catalog",
  tag = "v0.2.0rc2",
  subdirectory = "soyuz-catalog-client",
}
```

`uv sync` fetches that wheel over HTTPS, reusing your shell's git
credentials (SSH key or `GH_TOKEN`). A sibling `../soyuz-catalog`
checkout is **no longer required** — Sprint 38 was the first sprint
where `git clone && uv sync` works on a truly empty host.

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

Sprint 40 made the Dockerfile dual-auth. BuildKit can fetch the
private soyuz-catalog-client wheel via EITHER
`--mount=type=ssh` (ssh-agent, Sprint 38 ergonomics) OR
`--mount=type=secret,id=gh_pat` (token file, CI + clean-machine).
Both mounts are `required=false`; the `RUN` prefers the token if
present, else falls back to SSH. Pick whichever your workstation
already has authenticated:

```bash
docker compose build --ssh default pointlessql           # contributor
GH_PAT=$(gh auth token) docker compose build pointlessql # token path
```

### GHCR images (recommended for end users)

Every `v*` tag push fires
[`.github/workflows/docker.yml`](.github/workflows/docker.yml),
which builds and pushes both images to GHCR under the repo-owner
namespace:

- `ghcr.io/flohofstetter/pointlessql:<tag>`
- `ghcr.io/flohofstetter/soyuz-catalog:<pinned-soyuz-tag>`

Images are private; consumers authenticate with
`docker login ghcr.io` and a classic PAT scoped `read:packages`.
The commented `image:` lines in `docker/docker-compose.yml` turn the
stack into a pure-pull install with no source checkout required —
[`docs/getting-started/installation.md`](docs/getting-started/installation.md) and the
[`docs/e2e-walkthroughs/packaging.md`](docs/e2e-walkthroughs/packaging.md)
playbook walk through this flow.

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

  Exception: `pointlessql/alembic/versions/*.py` migration files
  (the phase tag in the filename + docstring is the schema-change
  identity, not project-management noise).
