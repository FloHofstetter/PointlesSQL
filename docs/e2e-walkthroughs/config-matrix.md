# Config-matrix walkthrough

Proves the three orthogonal runtime-config axes — engine,
log format, and metadata DB — all still pass a golden-path browser
run. One fully-written primary walk + five delta walks.

## Preconditions

- Stack up with the e2e overlay.
- `admin@pql.test` + the seeded `demo` catalog exist (from
  `auth.md` + `scripts/seed-e2e.py`).
- All axes are flipped via **host env exported before
  `docker compose up --force-recreate pointlessql`** — none of
  them are runtime-togglable (see `api/main.py:49-50` which calls
  `configure_logging` at import time).

## Config axes and defaults

| Env var                          | Default   | Accepted values                    |
| -------------------------------- | --------- | ---------------------------------- |
| `POINTLESSQL_ENGINE`             | `pandas`  | `pandas`, `duckdb`, `polars`       |
| `POINTLESSQL_LOG_FORMAT`         | `text`    | `text`, `json`                     |
| `POINTLESSQL_DATABASE_URL`       | sqlite…   | any SQLAlchemy URL (sqlite/postgres) |

## Primary walk — `engine=pandas`, `log=text`, `db=sqlite`

1. **Start with the defaults**.
   ```bash
   docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
   docker compose exec pointlessql python /app/scripts/seed-e2e.py
   ```

2. **Assert startup log reports the expected values**.
   ```bash
   docker compose logs pointlessql | grep 'PointlesSQL starting' | tail -1
   ```
   Expect the line to contain `engine=pandas, log_format=text`
   (emitted by `api/main.py:102`).

3. **Run the abbreviated golden-path browser walk**:
   - Register `admin@pql.test` (first-user bootstrap).
   - Log in.
   - Navigate `/catalogs/demo/schemas/sales/tables/orders`, assert
     the PQL snippet card renders with
     `pql.table("demo.sales.orders")`.
   - Navigate `/metrics` as admin, assert the response is
     `text/plain` with `pointlessql_job_runs_total`.

Primary walk acceptance: all four asserts pass.

## Delta walks

Each delta reuses the primary walk but flips exactly one env var
(or a combination in the last delta). The only change compared to
the primary walk is the override and the one extra assertion that
confirms the override landed.

### Delta A — `POINTLESSQL_ENGINE=duckdb`

```bash
POINTLESSQL_ENGINE=duckdb docker compose -f docker-compose.yml \
    -f docker-compose.e2e.yml up -d --force-recreate pointlessql
```

Assert startup log shows `engine=duckdb`. Re-run seed (harmless,
idempotent). Browser walk as primary. Since the UI does not expose
the engine, the startup-log grep is the authoritative check.

### Delta B — `POINTLESSQL_ENGINE=polars`

Same pattern; expect `engine=polars`.

### Delta C — `POINTLESSQL_LOG_FORMAT=json`

```bash
POINTLESSQL_LOG_FORMAT=json docker compose -f docker-compose.yml \
    -f docker-compose.e2e.yml up -d --force-recreate pointlessql
```

Assert:
```bash
docker compose logs pointlessql | grep -o '{.*"message":[^}]*}' | head -1 \
    | jq '.log_format // .message'
```
yields valid JSON. Visit `/` from the browser; a second log line
with a non-null `request_id` field should appear.

### Delta D — `DATABASE_URL=postgres`

```bash
docker compose -f docker-compose.yml -f docker-compose.postgres.yml \
    -f docker-compose.e2e.yml up -d --force-recreate pointlessql postgres
```

Note: a fresh `postgres_data` volume has no users. Re-register
`admin@pql.test` (first-user bootstrap applies against the fresh
DB). Re-run seed. Run the browser walk. Verify with:
```bash
docker compose exec postgres psql -U pointlessql -c \
    "SELECT email FROM users;"
```
Expect `admin@pql.test` to appear.

### Delta E — three overlays (duckdb + json + postgres)

Full cartesian-product smoke. Same shape as Delta D but with the
extra env vars set. Golden-path browser walk only; no additional
asserts beyond primary + the per-axis asserts combined.

## Cleanup between deltas

```bash
docker compose -f docker-compose.yml -f docker-compose.e2e.yml down -v
# — reset every env var before re-up —
```

`down -v` wipes the SQLite metadata DB and the Postgres volume.
For deltas D/E, `postgres_data` is also wiped.

## Playwright MCP script

```text
# Primary walk — reuse auth.md + catalog-browsing.md shortened

# Each delta: shell command to restart with env set, then:
browser_navigate('http://127.0.0.1:8000/')
# repeat the login + table-detail + /metrics asserts from primary
```

## Found bugs

_No bugs surfaced. Live spot-check covered the JSON log delta:_

- _`POINTLESSQL_LOG_FORMAT=json` flip + recreate landed; startup
  log lines emitted as single-line JSON with fields
  `timestamp, level, logger, message, request_id, job_run_id,
  task_id`. Request-scoped log lines (triggered by
  `curl -H 'X-Request-ID: matrix-json-test' /`) carried
  `"request_id": "matrix-json-test"` — Sprint 16's contextvar
  propagation still holds under the JSON formatter._
- _Other deltas (engine, database) exercise the same code paths
  already validated by Sprint 22's live walk; the playbook is
  in place for future regressions (e.g. a type-mapping change
  in `DuckDBEngine` would surface as a missing column in the
  `demo.sales.orders` table detail page)._
