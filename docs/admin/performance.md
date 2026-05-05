# Performance baseline

The Sprint 30.5 baseline measures **where SQLite WAL stops
serving the cockpit's p95 budget and where Postgres takes over**.
Numbers below are the headline; the underlying playbook lives at
[`scripts/seed_audit_lake.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/seed_audit_lake.py)
so any operator can replay against their hardware.

## How to measure

```bash
# 1. Seed a synthetic lake at the target scale.  Idempotent
#    (deterministic seed) so re-runs produce the same data.
POINTLESSQL_DB_URL=sqlite:///./bench_sqlite.db \
    uv run python scripts/seed_audit_lake.py --runs 100000

POINTLESSQL_DB_URL=postgresql+psycopg://pointlessql:pointlessql@localhost:5432/bench_pg \
    uv run python scripts/seed_audit_lake.py --runs 100000

# 2. Time the queries below against each backend.
#    Five runs each, take the median; ``\timing on`` in psql,
#    ``.timer on`` in sqlite.
```

## Headline numbers (operator-supplied)

The Phase 30 close-out doesn't fix benchmark numbers in the doc
because the meaningful comparison happens on the operator's
hardware (CPU, disk, memory, PG version).  The table below is
the **template** an operator fills in with their own results
before turning on PG production traffic.

| Query | Scale | SQLite WAL p95 | PG default p95 | PG + autovacuum hints p95 |
|---|---|---:|---:|---:|
| `/api/audit/history?since=...&until=...` | 10 k runs | _measure_ | _measure_ | _measure_ |
| `/api/audit/history?since=...&until=...` | 100 k runs | _measure_ | _measure_ | _measure_ |
| `/api/audit/history?since=...&until=...` | 1 M runs | _measure_ | _measure_ | _measure_ |
| `/api/audit/search?q=widget` | 10 k runs | _measure_ | _measure_ | _measure_ |
| `/api/audit/search?q=widget` | 100 k runs | _measure_ | _measure_ | _measure_ |
| `/api/audit/search?q=widget` | 1 M runs | _measure_ | _measure_ | _measure_ |
| `/api/runs/{id}` | 10 k runs | _measure_ | _measure_ | _measure_ |
| `/api/runs/{id}` | 1 M runs | _measure_ | _measure_ | _measure_ |
| `/anomalies` inbox load | 100 k runs | _measure_ | _measure_ | _measure_ |
| Grafana dashboard render (8 panels) | 100 k runs | _measure_ | _measure_ | _measure_ |

## Reading the numbers

Two questions worth answering before flipping production to one
or the other backend:

1. **At what scale does PG start outperforming SQLite WAL?**
   The expected crossover is around 10⁵ runs — beyond that, PG's
   index parallelism + connection pool wins.  Below it, SQLite
   often wins on raw memory locality.
2. **At what scale does SQLite WAL stop meeting the cockpit's p95
   budget?**
   The cockpit's design budget is **p95 < 2 s**; 18.10's deferral
   memory mentioned this gate.  When `audit_search` starts
   exceeding it, that's the time to migrate via
   [`pointlessql migrate-to-postgres`](postgres-deployment.md#migrating-from-sqlite).

## What if the numbers don't match the table?

Three usual suspects:

- **Workspace-axis indexes missing** — the Phase 28.x compound
  indexes on `(workspace_id, started_at)` etc. are required for
  the cockpit's per-workspace filter to be fast.  Verify with
  `\\d+ agent_runs` on PG or `.indexes agent_runs` on SQLite.
- **Autovacuum lagging** — re-read
  [Autovacuum hints](postgres-deployment.md#autovacuum-hints-for-high-churn-tables).
- **Pool sizing too low** — concurrent-cockpit users compete
  for connections; bump
  `POINTLESSQL_DB_POOL_SIZE` and `POINTLESSQL_DB_MAX_OVERFLOW`.

## Related

- [Postgres deployment](postgres-deployment.md)
- [Grafana](../integrations/grafana.md)
- [Audit cockpit](../concepts/audit-trail.md)
