# Grafana

PointlesSQL ships an opinionated **Grafana audit dashboard** as
a docker-compose overlay. Eight panels reading
straight from the SQLite metadata DB; no separate Prometheus
scrape, no agent code, no API changes.

## What you see

- **Total runs / day** — bar chart across the
 `POINTLESSQL_AUDIT_ANOMALY_BASELINE_WINDOW_DAYS` rolling
 window
- **Writes vs merges vs aggregates** — stacked area chart of
 `agent_run_operations` by `op_name`
- **Top principals** — bar chart of who's running things
- **Anomalies over time** — σ-tier verdicts (`ok` / `warn` /
 `critical`) per axis
- **External writes** — count per day from
 `unattributed_writes`
- **Rollback executions** — count per day from
 `agent_run_events WHERE event_type='pointlessql.rollback.executed'`
- **Lineage volume** — row / column / value-changes counts
- **Cost gate denials** — count per day

## Install

The overlay file lives at
[`docker-compose.grafana.yml`](https://github.com/FloHofstetter/PointlesSQL/blob/main/docker-compose.grafana.yml)
in the repo root:

```bash
docker compose -f docker-compose.yml -f docker-compose.grafana.yml up -d
```

Browse to <http://127.0.0.1:3000>, login with the default
`admin / admin` (rotate immediately). The audit dashboard is
under **Dashboards → Audit & Lineage** and is provisioned
read-only (the dashboard JSON ships in the same overlay).

Walkthrough: [dashboards.md](../e2e-walkthroughs/dashboards.md).

## Why SQLite, not Prometheus

Prometheus is a metrics store; the audit cockpit needs *event
data* (one row per run / op / promotion / rollback) plus
metric-shaped aggregates over those. Reading SQLite directly
gives the dashboards full row-level detail when an operator
clicks into a panel.

The trade-off: scaling Grafana onto a Postgres backend (Phase
19.0.1 in ROADMAP) requires a `frser-postgres-datasource` swap
and re-pointing the panel queries. The path is sketched in the
roadmap but not implemented.

## Known gotchas

- **WAL mount must be RW.** The Grafana container reads the
 same SQLite file PointlesSQL writes. If the bind mount is
 read-only, the WAL file (`pointlessql.db-wal`) can't be
 checkpointed and Grafana sees stale data. See
 [Troubleshooting](../guides/troubleshooting.md).
- **`GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS` is mandatory.**
 The `frser-sqlite-datasource` plugin isn't signed; the
 overlay sets the flag for you.
- **Datasource UID is hardcoded.** Don't rename it in the
 Grafana UI — the dashboard JSON references it by UID and
 panels go grey if it drifts.
- **`cost_est` Decimal needs `CAST(... AS REAL)`** in custom
 panels; the SQLite-datasource plugin doesn't render
 `Decimal` directly.

## Custom panels

Add panels by exporting them as JSON and dropping into
`pointlessql/_grafana/dashboards/audit.json`. Re-up the
overlay; provisioning re-imports. See
[`docker-compose.grafana.yml`](https://github.com/FloHofstetter/PointlesSQL/blob/main/docker-compose.grafana.yml).

## Where to read next

- [Dashboards walkthrough](../e2e-walkthroughs/dashboards.md)
- [Audit trail → Audit cockpit](../concepts/audit-trail.md)
- [Configuration → Audit](../reference/configuration.md#audit)
