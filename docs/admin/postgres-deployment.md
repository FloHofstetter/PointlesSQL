# Postgres deployment

Postgres has been a *technically supported* metadata backend for
PointlesSQL since Phase 4 / Sprint 10 (env switch
`POINTLESSQL_DB_URL=postgresql+psycopg://...`).  Sprint 30
closed the operational gaps that stood between "works in dev"
and "production-default": Postgres-native full-text search
(Sprint 30.1), a Grafana dashboard for the PG metadata DB
(30.2), a one-shot SQLite → Postgres migration tool (30.3), and
this page (30.4).

## When to choose Postgres

Pick Postgres when **any** of the following holds.  SQLite is
fine for laptop dev and small single-tenant installs; PG is the
right call once you actually run something:

| Signal | SQLite | Postgres |
|---|---|---|
| Concurrent operators | ≤ 5 | ≥ 5 |
| Audit retention horizon | weeks | months / years |
| Daily lineage edge volume | < 100 k | > 100 k |
| Production Grafana | optional | required |
| HA / backup story | file copy + WAL | `pg_basebackup` + WAL archive |
| Plugin auth keys rotation cadence | rare | continuous |

The Sprint 30.5 performance baseline (when the dedicated
`performance.md` page lands) measures where the SQLite p95
budget for the cockpit starts to bend.  Anecdotally that's
around 10⁵ runs.

## Bring up the stack

The base `docker/docker-compose.yml` defaults to SQLite.  Postgres is a
compose overlay:

```bash
# Postgres metadata DB only.
docker compose \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.postgres.yml up -d

# With Grafana on Postgres (Sprint 30.2).  The Grafana overlay
# is mutually exclusive with docker/docker-compose.grafana.yml.
docker compose \
  -f docker/docker-compose.yml \
  -f docker/docker-compose.postgres.yml \
  -f docker/docker-compose.grafana.postgres.yml up -d
```

The PG service uses `postgres:17-alpine` with
`POSTGRES_USER=POSTGRES_PASSWORD=POSTGRES_DB=pointlessql` defaults
— rotate before exposing the host port outside `127.0.0.1`.

## Pool sizing

`init_db()` reads four new env vars on Sprint 30.4:

| Env var | Default | Effect |
|---|---|---|
| `POINTLESSQL_DB_POOL_SIZE` | `5` | Persistent connections per worker. |
| `POINTLESSQL_DB_MAX_OVERFLOW` | `10` | Burst capacity above `pool_size`. |
| `POINTLESSQL_DB_POOL_RECYCLE_SECONDS` | `1800` | Drop a connection if it's been alive longer than this — sidesteps idle-timeout drops on managed PG. |
| `POINTLESSQL_DB_STATEMENT_TIMEOUT_MS` | `30000` | PG `SET statement_timeout` per connection (ms). |

For a 4-worker uvicorn fleet handling steady cockpit traffic,
the formula `pool_size * worker_count + max_overflow * 1` keeps
PG `max_connections` happy:

- 4 workers × `pool_size=5` = 20 base
- + `max_overflow=10` per worker (rare bursts) = 60 ceiling

PG defaults `max_connections=100`; leave headroom for `psql`
sessions and `pg_dump`.

## Statement timeout

The default 30 000 ms cap covers cockpit reads and the daily
audit-reviewer agent.  Bump it for ad-hoc analytics or for
`migrate-to-postgres` runs over very large lakes (the migration
tool reads in batches but each `COUNT(*)` over a 10 M-row
`lineage_row_edges` can exceed 30 s on slow disks):

```bash
POINTLESSQL_DB_STATEMENT_TIMEOUT_MS=120000 \
  uv run pointlessql migrate-to-postgres ...
```

A timeout of `0` disables the cap entirely (PG default); not
recommended for production.

## Autovacuum hints for high-churn tables

Three audit-axis tables grow fast enough that the global
autovacuum settings under-vacuum them:

| Table | Typical row growth | Recommended override |
|---|---|---|
| `lineage_row_edges` | ~10⁶ rows / day | `autovacuum_vacuum_scale_factor = 0.05` |
| `agent_run_tool_calls` | ~10⁵ rows / day | `autovacuum_vacuum_scale_factor = 0.05` |
| `lineage_value_changes` | ~10⁵ rows / day | `autovacuum_vacuum_scale_factor = 0.05` |

Apply with:

```sql
ALTER TABLE lineage_row_edges
    SET (autovacuum_vacuum_scale_factor = 0.05);
ALTER TABLE agent_run_tool_calls
    SET (autovacuum_vacuum_scale_factor = 0.05);
ALTER TABLE lineage_value_changes
    SET (autovacuum_vacuum_scale_factor = 0.05);
```

These tweaks are not auto-applied by alembic — operators run
them once per install.  A `pointlessql admin tune-pg`
sub-command may follow in a later phase.

## Adding indexes to large tables online

A plain `CREATE INDEX` takes an `ACCESS EXCLUSIVE` lock and blocks
**every write** to the table until the build finishes.  On the large,
append-only tables — `audit_log` (on the request write hot path),
`query_history`, the `lineage_*` family, and the `*_snapshots` tables —
that stalls live traffic for as long as the build runs.

Any migration that adds an index to one of those tables must build it
online instead.  Use the helper rather than a bare `op.create_index`:

```python
from pointlessql.alembic._online_index import create_index_online, drop_index_online

def upgrade() -> None:
    create_index_online(
        "ix_audit_log_workspace_created",
        "audit_log",
        ["workspace_id", sa.text("created_at DESC")],
    )

def downgrade() -> None:
    drop_index_online("ix_audit_log_workspace_created", "audit_log")
```

On Postgres the helper builds the index `CONCURRENTLY` (no write lock)
inside an `autocommit_block` — required, because a concurrent build
cannot run inside the migration's transaction — and adds `IF NOT
EXISTS` so a retry after an interrupted build is idempotent.  On SQLite
it falls back to a plain `op.create_index`, so `alembic check` stays
green on the SQLite lane.  The migration
`64bf0762645a_add_snapshot_lookup_expression_indexes.py` is the
reference example.

> A concurrent build that fails (e.g. a duplicate-value violation on a
> unique index) leaves an `INVALID` index behind.  Drop it
> (`DROP INDEX CONCURRENTLY`) before re-running the migration.

## Backup / restore playbook

### Single-shot dump

```bash
docker exec -t pointlessql_postgres pg_dump \
    --format=custom \
    --compress=9 \
    -U pointlessql pointlessql \
    > pointlessql_$(date +%Y%m%d).dump
```

Restore:

```bash
docker exec -i pointlessql_postgres pg_restore \
    --jobs=4 --clean --if-exists \
    -U pointlessql -d pointlessql \
    < pointlessql_20260505.dump
```

`pg_restore --jobs=N` parallelises across tables; on the
`postgres:17-alpine` image, the ceiling is the host CPU count.

### Streaming PITR

For installs that can't lose more than a few minutes of audit
data, point a `pg_basebackup` continuously running on a
secondary host and configure WAL archiving:

```bash
docker exec pointlessql_postgres psql -U pointlessql \
    -c "ALTER SYSTEM SET archive_mode = 'on';"
docker exec pointlessql_postgres psql -U pointlessql \
    -c "ALTER SYSTEM SET archive_command = 'cp %p /backup/wal/%f';"
docker exec pointlessql_postgres psql -U pointlessql \
    -c "SELECT pg_reload_conf();"
```

Mount `/backup/wal` to durable storage.  Recovery is the standard
`pg_basebackup` + `recovery.signal` dance — out of scope for this
page, see the [PG admin guide](https://www.postgresql.org/docs/current/continuous-archiving.html).

## Migrating from SQLite

`pointlessql migrate-to-postgres` is the operator-facing
one-shot tool (Sprint 30.3).  It runs
`alembic upgrade head` against the target, refuses to overwrite
non-empty rows, bulk-copies tables in a hard-coded FK-respecting
order, syncs PG sequences past the largest copied id, rebuilds
the FTS index, and verifies row counts.

```bash
# Quiesce the source first — stop the SQLite-backed PointlesSQL
# stack so no writes happen mid-copy.
docker compose -f docker/docker-compose.yml down

# Bring up just Postgres for the new target.
docker compose -f docker/docker-compose.yml -f docker/docker-compose.postgres.yml up -d postgres

# Run the migration.
uv run pointlessql migrate-to-postgres \
    --source sqlite:////app/data/pointlessql.db \
    --target postgresql+psycopg://pointlessql:pointlessql@localhost:5432/pointlessql

# Bring the full PG stack up.
docker compose -f docker/docker-compose.yml -f docker/docker-compose.postgres.yml up -d
```

The CLI carries a `--dry-run` flag that prints source row counts
without touching the target — useful for sizing the cutover
window.

## Monitoring

Three signals worth alerting on:

1. **Cockpit search latency** —
   `/api/audit/search?q=...` p95 should stay below 2 s on the
   PG-backed FTS index (Sprint 30.1).  Spikes correlate with
   missed autovacuum on `audit_search_index`.
2. **Anomaly inbox count** —
   `SELECT COUNT(*) FROM anomaly_acks WHERE acknowledged_at IS NULL`
   should stay bounded.  An unbounded growth means the daily
   review-agent isn't running.
3. **Grafana panel render time** —
   the Sprint 30.2 dashboard surfaces 8 panels.  Render time
   over 5 s indicates a missing index — likely the
   workspace-axis compound indexes from Sprint 28.x.

The Grafana dashboard from the Sprint 30.2 overlay surfaces all
three.  See
[Grafana → Running with Postgres](../integrations/grafana.md#running-with-postgres).

## Multi-worker co-edit bus (Phase 109)

The notebook co-edit hub (`/ws/notebook/coedit/{nb}`) holds the
authoritative `pycrdt.Doc` in the uvicorn worker that first claimed
the notebook.  Single-worker deployments work as-is.  To run more
than one uvicorn worker against the same install, enable the
Phase-109 PG LISTEN/NOTIFY bus:

```bash
POINTLESSQL_COEDIT_BUS_ENABLED=1 \
POINTLESSQL_DB_URL=postgresql://... \
uvicorn pointlessql.api.main:app --workers 4 --host 0.0.0.0 --port 8000
```

What the bus does:

* On startup, every worker opens one dedicated psycopg async
  connection and `LISTEN coedit_bus`.
* When a frame arrives over the WebSocket (sync_update, awareness,
  cell_uuid_remap, agent_presence), the worker fans out locally and
  also writes a row to `coedit_bus_messages` + emits a `pg_notify`
  carrying the row id.
* Other workers receive the notify, fetch the row, and replay the
  frame into their local hub.  Frames originating from the same
  PID are skipped (self-loop suppression by `source_pid` column).
* A background task sweeps `coedit_bus_messages` every 30 s,
  deleting rows older than 60 s.

Operator knobs (defaults shown):

| Env var | Default | Notes |
|---------|---------|-------|
| `POINTLESSQL_COEDIT_BUS_ENABLED` | `false` | Master switch.  PG only — SQLite installs ignore. |
| `POINTLESSQL_COEDIT_BUS_MESSAGE_TTL_SECONDS` | `60` | Outbox row lifetime; longer outages re-converge via CRDT sync. |
| `POINTLESSQL_COEDIT_BUS_CLEANUP_INTERVAL_SECONDS` | `30` | Cleanup sweep cadence. |

Diagnostics: `GET /api/admin/coedit-bus/status` returns a JSON
snapshot (`listener_alive`, `listener_ready`, `cleanup_alive`,
`inflight_outbox_rows`) for an authenticated admin.

Out of scope: cross-region (PG NOTIFY is single-cluster), sticky
session routing (the bus makes it unnecessary), bus-level auth
(WS handshake already gates editor access).

## Related

- [Configuration reference](../reference/configuration.md) — env var reference
- [Grafana](../integrations/grafana.md) — operator dashboards
- [Audit cockpit](../concepts/audit-trail.md) — what the FTS surface covers
