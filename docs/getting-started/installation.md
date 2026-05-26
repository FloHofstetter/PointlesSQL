# Installing PointlesSQL

Three supported install flavours. Pick the one that matches your
situation. All three require access to the private
[soyuz-catalog][sc] repository, which backs PointlesSQL's catalog.

[sc]: https://github.com/FloHofstetter/soyuz-catalog

| Flavour | Who it is for | What it needs |
|---|---|---|
| [Docker + GHCR images](#docker-ghcr-images-recommended) | End users, quick-start | Docker Engine 24+, a PAT with `read:packages` |
| [pip install from git tag](#pip-install-from-git-tag) | Library consumers, scripting | Python 3.14, `uv`, a PAT with `Contents: Read` on soyuz-catalog |
| [Source checkout](#source-checkout-contributors) | Contributors | Git, Python 3.14, `uv`, an ssh key or PAT |

## Docker + GHCR images (recommended)

Zero-build install. No sibling `../soyuz-catalog` checkout needed.
Pulls both images from GHCR, runs the full stack in ≤2 minutes.

**1. Create a classic PAT** at
<https://github.com/settings/tokens> with scope `read:packages`.
Export it:

```bash
export GHCR_PAT='ghp_...'
```

**2. Log in to GHCR:**

```bash
echo "$GHCR_PAT" | docker login ghcr.io -u <your-github-username> --password-stdin
```

**3. Download the reference `docker/docker-compose.yml`** into a fresh
working directory (do NOT run this inside a PointlesSQL source
clone — compose will pick up the local file with `build:` still
active):

```bash
mkdir ~/pointlessql && cd ~/pointlessql
curl -L -o docker-compose.yml \
 https://raw.githubusercontent.com/FloHofstetter/PointlesSQL/v0.1.0rc3/docker-compose.yml
```

**4. Flip the two services from `build:` → `image:`.** In each
service block, comment out the `build:` block and uncomment the
`image:` line directly above it:

```yaml
soyuz-catalog:
 image: ghcr.io/flohofstetter/soyuz-catalog:v0.2.0rc2 # ← uncomment
 # build: # ← comment
 # context:. # entire
 # dockerfile: docker/Dockerfile.soyuz # block
 # additional_contexts:
 # soyuz-catalog:../soyuz-catalog
 ports:
 - "${SOYUZ_HOST_PORT:-8080}:8080"
...
```

Same edit on the `pointlessql:` service.

**5. Pull and start:**

```bash
docker compose pull
docker compose up -d
```

**Expected state:** `http://127.0.0.1:8000/` renders the PointlesSQL
welcome page. JupyterLab is on `:8888`, soyuz-catalog's UC API on
`:8080`.

**Optional — Grafana audit dashboard.** Append the
`docker/docker-compose.grafana.yml` overlay to spin up Grafana with a
pre-provisioned audit + lineage dashboard at
`http://127.0.0.1:3000`:

```bash
docker compose -f docker/docker-compose.yml -f docker/docker-compose.grafana.yml up -d
```

Reads the same SQLite metadata DB the app uses; no agent code,
no API changes, no extra config. Postgres deployments aren't yet
supported here (see in
[`ROADMAP.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/ROADMAP.md)).

Pin to a digest for reproducibility in production:

```yaml
image: ghcr.io/flohofstetter/pointlessql@sha256:<digest>
```

## pip install from git tag

Install PointlesSQL as a Python package via `uv`. Useful for
scripting / library use where you already have soyuz-catalog
running elsewhere.

**1. Create a classic PAT** at
<https://github.com/settings/tokens> with scope
`Contents: Read` on soyuz-catalog. Export it:

```bash
export GH_PAT='ghp_...'
```

**2. Rewrite HTTPS github clones through the token** (this is how
`uv` resolves the private `[tool.uv.sources]` pin transitively):

```bash
git config --global \
 url."https://x-access-token:${GH_PAT}@github.com/".insteadOf \
 "https://github.com/"
```

**3. Install PointlesSQL:**

```bash
uv pip install "pointlessql @ git+https://github.com/FloHofstetter/PointlesSQL.git@v0.1.0rc3"
```

**4. Start soyuz-catalog** however suits your deployment. If you
have the soyuz-catalog repo checked out, `uv run soyuz-catalog`
listens on `:8080`. Otherwise run the Docker image:

```bash
docker run -p 8080:8080 ghcr.io/flohofstetter/soyuz-catalog:v0.2.0rc2
```

**5. Start PointlesSQL:**

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
git clone git@github.com:FloHofstetter/PointlesSQL.git
cd PointlesSQL
```

**2. Install dependencies.** `uv sync` reuses whatever shell git
credentials your user has already configured (an ssh key against
`git@github.com` is the simplest). The soyuz-catalog-client wheel
is fetched from its pinned tag:

```bash
uv sync
```

**3. Optional — iterate on soyuz-catalog side-by-side.** If you
need regenerated client output to surface without a tag bump,
flip the dependency to an editable sibling checkout:

```bash
git clone git@github.com:FloHofstetter/soyuz-catalog.git../soyuz-catalog
bash scripts/use-editable-soyuz.sh # pyproject.toml dirty on purpose
#...iterate: edit soyuz-catalog, regen client, `uv sync`, test...
bash scripts/use-pinned-soyuz.sh # restore before committing
```

**4. Start both processes.** In terminal 1:

```bash
cd../soyuz-catalog
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

## Troubleshooting

**`docker: pull access denied for ghcr.io/flohofstetter/...`** —
Your GHCR login is missing or expired. Re-run step 2 of the Docker
flavour. Images are private under the repo-owner namespace.

**`docker compose build` hangs on `fetching soyuz-catalog-client`** —
Neither the `ssh` nor the `gh_pat` secret was passed. Either
`docker compose build --ssh default` (requires an ssh-agent
authenticated against `git@github.com`) or `GH_PAT=$(gh auth token)
docker compose build`.

**`--mount=type=secret: unknown flag`** — BuildKit is disabled.
Set `DOCKER_BUILDKIT=1` in your shell or configure
`"features": {"buildkit": true}` in `~/.docker/config.json`.

**`uv sync` fails with `Authentication failed for...soyuz-catalog`** —
The `url.insteadOf` rewrite isn't active in this shell. Confirm
with `git config --global --get url."https://x-access-token:...@github.com/".insteadOf`.
Use a **classic** PAT, not a fine-grained one — fine-grained PATs
need a per-repo grant that the `Contents: Read` classic scope
bypasses.

**`docker compose up` says `soyuz-catalog healthcheck: unhealthy`** —
The soyuz-catalog image failed to start. Check logs with
`docker compose logs soyuz-catalog`. Most common cause: the
`/app/data` volume has a stale SQLite from a previous version;
`docker compose down -v` wipes it.

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
