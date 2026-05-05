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

## Filtering by workspace

Phase 29.4 added a `$workspace` template variable at the top of the
audit dashboard. The dropdown is populated from the `workspaces`
table at dashboard load and is **multi-select** + has the **All**
option toggled by default — every panel keeps its global
cross-workspace view until an admin actively scopes down.

How the filter is implemented:

- The variable's `allValue` is the literal string `0` (no real
  workspace ever has id 0). Every panel SQL grows a guard predicate
  shaped like:

  ```sql
  AND (0 IN ($workspace) OR <table>.workspace_id IN ($workspace))
  ```

  When **All** is selected, `$workspace` interpolates to `0` and the
  left disjunct short-circuits the predicate to true — full global
  view. When specific workspaces are picked, the right disjunct
  filters the rows to those IDs.

- The **Datasource health (agent_runs row count)** smoke test stays
  global on purpose — its job is to verify the metadata DB mount
  is attached, not to surface real audit numbers. The workspace
  dropdown does not filter it.

- The audit-of-audit trail for cross-workspace reads (the
  `audit_api_cross_workspace` `read_kind` recorded on the
  `?workspace=all` query-param path) is **not** affected by Grafana
  use, because Grafana queries the metadata DB directly rather
  than going through `/api/audit/...`. Operators who need the
  audit trail must use the in-app cockpit instead.

To default a viewer to a single workspace, edit their personal
dashboard URL with `?var-workspace=<id>`; Grafana will respect it
across page reloads.

## Running with Postgres

PointlesSQL deployments using the Postgres metadata backend
(see [Postgres deployment](../admin/postgres-deployment.md))
plug into a different Grafana wiring. Sprint 30.2 ships a
parallel overlay that swaps the SQLite plugin for Grafana's
built-in PostgreSQL datasource and provisions a dialect-clean
dashboard JSON:

```bash
docker compose \
  -f docker-compose.yml \
  -f docker-compose.postgres.yml \
  -f docker-compose.grafana.postgres.yml up -d
```

Differences from the SQLite overlay:

- **No third-party plugin.** Grafana's built-in
  `postgres` datasource is used; the
  `GF_PLUGINS_ALLOW_LOADING_UNSIGNED_PLUGINS` env var is not
  needed.
- **Dialect-clean SQL.** Panel 5 (the rolling 7-day reject
  baseline) uses PG `INTERVAL '7 days'` arithmetic instead of
  SQLite's `date(d.day, '-7 days')` modifier. Every other
  panel's SQL is portable across both backends.
- **Different datasource UID.** The PG dashboard binds to UID
  `pointlessql-postgres`; the SQLite dashboard binds to UID
  `pointlessql-sqlite`. Mixing the two overlays at once would
  collide on the dashboard slug, so pick exactly one.
- **No SQLite file mount.** The PG overlay drops the SQLite
  bind mount entirely — Grafana reaches Postgres over the
  compose network.

The two overlays are mutually exclusive. Operators picking
Postgres should not also pass `-f docker-compose.grafana.yml`.

## Why SQLite, not Prometheus

Prometheus is a metrics store; the audit cockpit needs *event
data* (one row per run / op / promotion / rollback) plus
metric-shaped aggregates over those. Reading the metadata DB
directly (whichever backend it sits on) gives the dashboards
full row-level detail when an operator clicks into a panel.

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
