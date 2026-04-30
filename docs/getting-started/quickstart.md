# Quickstart

Get from zero to "I just read a Delta table by name and saw
the audit row pop up" in under five minutes.

This walkthrough assumes Docker Engine 24+ on Linux or macOS.
For the long-form three-flavour install matrix (Docker / `pip` /
source) see [Installation](installation.md).

## Step 1 — Pull the stack

```bash
mkdir ~/pointlessql-quickstart && cd ~/pointlessql-quickstart
curl -L -o docker-compose.yml \
  https://raw.githubusercontent.com/FloHofstetter/PointlesSQL/main/docker-compose.yml
echo "$GHCR_PAT" | docker login ghcr.io -u <your-github-handle> --password-stdin
docker compose pull
```

The two images (`pointlessql` + `soyuz-catalog`) are private on
GHCR for now — `GHCR_PAT` is a classic GitHub PAT with
`read:packages`.  See
[Installation → Docker + GHCR](installation.md#docker-ghcr-images-recommended)
for the PAT-creation flow.

!!! tip "No GHCR access?"
    Use the source-checkout flavour: `git clone` and
    `uv run pointlessql`.  The quickstart works the same way
    once port 8000 is listening.

## Step 2 — Start the stack

```bash
docker compose up -d
docker compose logs -f pointlessql   # watch first-boot migrations
```

Expected: `Uvicorn running on http://0.0.0.0:8000`.  Press
Ctrl-C when you see it — the container stays up.

## Step 3 — Register the first user

Browse to <http://127.0.0.1:8000>.  The login page detects an
empty database and offers a **"Register first admin"** button.
Pick a username and password — this account is the admin.

(`is_first_user()` in
[`pointlessql/services/auth.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/auth.py)
gates the bootstrap flow — the *second* registration drops the
admin flag.)

## Step 4 — Seed the sample catalog

The repo ships an idempotent seed script that lays down a
`demo` catalog with two schemas (`sales`, `hr`) and four tables
(`customers`, `orders`, `employees`, `salaries`).  Every
walkthrough under [Guides → E2E walkthroughs](../guides/index.md)
assumes this shape.

```bash
docker compose exec pointlessql uv run python /app/scripts/seed-e2e.py
```

Expected output: `seeded demo.sales.customers (20 rows) ...
demo.hr.salaries (10 rows)`.  Re-running is safe — every step
is guarded by a "does it exist?" check.

## Step 5 — Browse the catalog

Refresh <http://127.0.0.1:8000>.  The sidebar shows
**demo → sales / hr**, the click-through opens table detail with
schema, properties, and the row preview.  Click
**demo.sales.orders** and look at the **Lineage** tab — it's
empty for now, because nothing has been derived from it yet.

## Step 6 — Read a Delta table from Python

In a fresh terminal:

```bash
docker compose exec pointlessql uv run python -c "
from pointlessql import PQL
pql = PQL()
print(pql.list_catalogs())
df = pql.table('demo.sales.orders')
print(df.head())
print(f'rows: {len(df)}')
"
```

You should see the four-catalog list (`demo` is one of them) and
a `pandas.DataFrame` with 50 sample rows.

## Step 7 — Write a derived table and see the audit row

Still inside the container:

```bash
docker compose exec pointlessql uv run python -c "
from pointlessql import PQL
pql = PQL()
df = pql.table('demo.sales.orders')
high = df[df['amount'] > 100]
pql.write_table(high, 'demo.sales.orders_high', mode='overwrite',
                source_table_fqn='demo.sales.orders')
print(f'wrote demo.sales.orders_high ({len(high)} rows)')
"
```

Now refresh the browser and click **demo.sales.orders** →
**Lineage** tab.  The bidirectional DAG shows
`orders → orders_high` as an `outgoing` edge with the row count.

Click **Run history** in the top nav.  The most recent row is
the operation that just landed: `op_name=write_table`,
`target=demo.sales.orders_high`, `rows_written=N`, with a
"View row-level lineage" link that takes you into the per-row
breakdown.

**You just produced an audit-trail with one Python call.**
Every subsequent agent or operator action lands the same way —
a row in `agent_run_operations`, optional row/column/value
lineage, optional rollback target.

## What's next

- [Concepts overview](concepts.md) — mental model in one read
  (catalogs, agent runs, lineage chain, audit cockpit)
- [Guides](../guides/index.md) — task-oriented walkthroughs
- [Architecture](../concepts/auth.md) (Sprint 22.2 will fill in
  the architecture page; for now the auth page is the deepest
  available concept doc)
- [Reference](../reference/index.md) (Sprint 22.3) — Python +
  REST + CLI + config

## Tear down

```bash
docker compose down -v   # -v wipes the SQLite metadata DB and warehouse/
```

The seed script is idempotent — re-running `up && seed-e2e.py`
restores the same shape.

## Troubleshooting

**`docker compose pull` fails with `pull access denied`** —
GHCR login expired.  Re-run step 1's `docker login`.

**`http://127.0.0.1:8000` returns 404 for everything** —
PointlesSQL booted before its first migration finished.  Wait
~10 s and retry.  `docker compose logs pointlessql` shows
`Alembic: upgraded head` when migrations are done.

**`pql = PQL()` raises `RuntimeError: cannot connect to soyuz`** —
The two services are on the same compose network; the env var
`POINTLESSQL_SOYUZ_CATALOG_URL` should be
`http://soyuz-catalog:8080`.  Check `docker compose config | grep
SOYUZ`.

**Audit row doesn't appear in Run history** — Run-detail page
groups by `agent_run_id`.  A bare Python REPL inherits the
container's session id; if you started the REPL from a different
process tree, set `POINTLESSQL_AGENT_RUN_ID=adhoc` before the
REPL.
