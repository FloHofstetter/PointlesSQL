# Installing PointlesSQL

Three supported install flavours. Pick the one that matches your
situation. None of them require GitHub credentials — both
PointlesSQL and the [soyuz-catalog][sc] catalog backend are public.

[sc]: https://github.com/FloHofstetter/soyuz-catalog

| Flavour | Who it is for | What it needs |
|---|---|---|
| [Docker (recommended)](#docker-recommended) | End users, quick-start | Docker Engine 24+ |
| [pip install from git tag](#pip-install-from-git-tag) | Library consumers, scripting | Python 3.14, `uv` |
| [Source checkout](#source-checkout-contributors) | Contributors | Git, Python 3.14, `uv` |

## Docker (recommended)

Zero-build, zero-credential install. Pulls both images from GHCR
and runs the full stack in ≤2 minutes.

**1. Download the reference compose file** into a fresh working
directory (not inside a PointlesSQL source clone):

```bash
mkdir ~/pointlessql && cd ~/pointlessql
curl -fsSL https://raw.githubusercontent.com/FloHofstetter/PointlesSQL/main/docker/docker-compose.yml -o docker-compose.yml
```

**2. Start the stack:**

```bash
docker compose up -d
```

**Expected state:** `http://127.0.0.1:8000/` renders the PointlesSQL
welcome page. JupyterLab is on `:8888`, soyuz-catalog's UC API on
`:8080`.

The compose file defaults to the latest published image tags. Pin a
specific release by exporting `PQL_VERSION` / `SOYUZ_VERSION` before
`docker compose up`:

```bash
PQL_VERSION=v0.1.0rc3 SOYUZ_VERSION=v0.3.0rc3 docker compose up -d
```

Delta tables and notebooks persist in named Docker volumes
(`warehouse_data`, `notebooks_data`, …) that survive
`docker compose down`. Wipe them with `docker compose down -v`.

**Optional — Grafana audit dashboard.** Append the
`docker/docker-compose.grafana.yml` overlay to spin up Grafana with a
pre-provisioned audit + lineage dashboard at
`http://127.0.0.1:3000`:

```bash
docker compose -f docker-compose.yml -f docker-compose.grafana.yml up -d
```

Reads the same SQLite metadata DB the app uses; no agent code,
no API changes, no extra config. Postgres deployments aren't yet
supported here (see
[`ROADMAP.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/ROADMAP.md)).

Pin to a digest for reproducibility in production:

```yaml
image: ghcr.io/flohofstetter/pointlessql@sha256:<digest>
```

## pip install from git tag

Install PointlesSQL as a Python package via `uv`. Useful for
scripting / library use where you already have soyuz-catalog
running elsewhere.

**1. Install PointlesSQL** from a tagged release. The
`soyuz-catalog-client` dependency resolves from its public git tag
with no credentials:

```bash
uv pip install "pointlessql @ git+https://github.com/FloHofstetter/PointlesSQL.git@v0.1.0rc3"
```

**2. Start soyuz-catalog** however suits your deployment. If you
have the soyuz-catalog repo checked out, `uv run soyuz-catalog`
listens on `:8080`. Otherwise run the Docker image:

```bash
docker run -p 8080:8080 ghcr.io/flohofstetter/soyuz-catalog:v0.3.0rc3
```

**3. Start PointlesSQL:**

```bash
POINTLESSQL_SOYUZ_CATALOG_URL=http://127.0.0.1:8080 pointlessql
```

**Expected state:** `http://127.0.0.1:8000/` renders the
welcome page.

## Source checkout (contributors)

Install from the development tree. Matches the loop you'd use if
you were iterating on PointlesSQL itself.

**1. Clone the repo:**

```bash
git clone https://github.com/FloHofstetter/PointlesSQL.git
cd PointlesSQL
```

**2. Install dependencies.** `uv sync` fetches the
`soyuz-catalog-client` wheel from its pinned public git tag — no
credentials required:

```bash
uv sync
```

**3. Optional — iterate on soyuz-catalog side-by-side.** If you
need regenerated client output to surface without a tag bump,
flip the dependency to an editable sibling checkout:

```bash
git clone https://github.com/FloHofstetter/soyuz-catalog.git ../soyuz-catalog
bash scripts/use-editable-soyuz.sh   # pyproject.toml dirty on purpose
# …iterate: edit soyuz-catalog, regen client, `uv sync`, test…
bash scripts/use-pinned-soyuz.sh     # restore before committing
```

**4. Start both processes.** In terminal 1:

```bash
cd ../soyuz-catalog
uv sync
uv run soyuz-catalog
```

In terminal 2:

```bash
cd PointlesSQL
uv run pointlessql
```

**Expected state:** `http://127.0.0.1:8000/` renders the welcome
page. Code reloads with `uvicorn --reload` (see `pointlessql/api/main.py`).

To build the Docker images from your local checkout instead of
pulling from GHCR, layer the contributor override:

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.dev.yml up --build
```

This requires a sibling `../soyuz-catalog` checkout for the soyuz
image build context.

## Troubleshooting

**`docker: pull access denied` / `manifest unknown` for
`ghcr.io/flohofstetter/...`** — The tag you pinned doesn't exist.
Drop `PQL_VERSION` / `SOYUZ_VERSION` to use the defaults, or check
the published tags on the repo's GHCR packages page.

**`docker compose up` says `soyuz-catalog healthcheck: unhealthy`** —
The soyuz-catalog image failed to start. Check logs with
`docker compose logs soyuz-catalog`. Most common cause: the
`/app/data` volume has a stale SQLite from a previous version;
`docker compose down -v` wipes it.

**`docker compose -f … -f docker-compose.dev.yml build` fails on the
soyuz-catalog build context** — The contributor override needs a
sibling `../soyuz-catalog` checkout. Clone it next to PointlesSQL,
or drop the `-f docker-compose.dev.yml` override to pull the
published image instead.

## Default file locations

The SQLite database, MLflow tracking store, and MLflow artifact
root all anchor to the **repository root** rather than the working
directory the server was launched from. Concretely the defaults
resolve to:

| File | Default path | Override env var |
|---|---|---|
| PointlesSQL DB | `<repo>/pointlessql.db` | `POINTLESSQL_DB_URL` |
| MLflow backend | `<repo>/mlflow.db` | `POINTLESSQL_MLFLOW_BACKEND_STORE_URI` |
| MLflow artifacts | `<repo>/mlflow_artifacts/` | `POINTLESSQL_MLFLOW_ARTIFACT_ROOT` |

Pre-fix, those paths were CWD-relative — starting `pointlessql`
from a sibling directory created a *parallel* `pointlessql.db`
there, which the server then read from while the seed-demo wrote
to the in-repo file. Operators who need the legacy CWD-relative
behaviour set the matching env var to `sqlite:///./pointlessql.db`
(or `file://./mlflow_artifacts`) explicitly.
