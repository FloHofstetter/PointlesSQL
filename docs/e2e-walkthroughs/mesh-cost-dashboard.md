# Mesh cost dashboard walkthrough

> **Mode:** `agent` · **Surface:** three `pql_*` cost-telemetry tools

End-to-end replay of a Family-A agent reading the data-mesh
cost-attribution surface: per-product rollup, per-consumer
rollup, and the full mesh-health dashboard payload.  Browser-
pendant: the `/admin/mesh-dashboard` page (Chart.js trend lines,
per-domain stacked bar, freshness heatmap, top-consumers table).

PointlesSQL meters every query through the lens engine and
attributes the cost to the authoring data product (engine
runtime cost) and the consumer principal (query-count cost).
A nightly rollup turns the raw meter into hourly buckets the
dashboard reads.  This playbook exercises the three tools that
expose the read surface:

* `pql_mesh_health_full` — comprehensive dashboard payload.
* `pql_cost_by_product` — per-product rollup over a window.
* `pql_cost_by_consumer` — per-consumer rollup over a window
  (admin-only, identifies users).

## Prerequisites

- A running PointlesSQL with the API key reaching a steward
  (for `cost_by_product` and `mesh_health_full`) or admin (for
  `cost_by_consumer`) principal.
- A `hermes-agent` session loaded with the
  `hermes-plugin-pointlessql` plugin.
- At least a few minutes of query activity in the workspace so
  the hourly rollup has buckets to surface.  In a fresh setup
  trigger queries by driving `pql_query` a few times.

## Steps

### 1. Fetch the full dashboard payload

Drive `pql_mesh_health_full` with no args.  Verify the envelope:

```json
{
  "ok": true,
  "data": {
    "per_domain": [...],
    "cost_trend": [...],
    "top_consumers": [...],
    "recent_deliveries": [...],
    "freshness_heatmap": [...]
  }
}
```

`cost_trend` is a 7-day rolling series of `{hour, total_cost,
total_queries}`.  `top_consumers` is capped at 10 entries by
consumer cost descending.  `per_domain` includes SLO bands for
each domain (`slo_band: red | yellow | green`).

### 2. Per-product window query (steward)

Drive `pql_cost_by_product` with:

```json
{
  "since": "2026-05-23T00:00:00Z",
  "until": "2026-05-30T00:00:00Z"
}
```

Verify the response is `{rows: [{data_product_id, total_cost,
total_queries, total_bytes, ...}]}` sorted by
`total_cost` descending.  Omit both args to default to the
last seven days.

### 3. Per-consumer window query (admin)

Drive `pql_cost_by_consumer` with the same window args.  Verify
the rows carry `consumer_user_id` — identifying info that the
backend gates behind admin scope.  A non-admin principal gets
a 403 envelope here even though `cost_by_product` works.

### 4. Cross-check the rollup horizon

Run `pql_cost_by_product` with a window narrower than one hour.
The rows may be empty because the rollup runs hourly; the raw
`data_product_query_cost` table carries finer-grained data but
the agent surface only exposes the rollup.  Widen the window to
a few hours to see populated rows.

### 5. Identify the top consumer

Take the first entry from step 1's `top_consumers`.  Combine
its `consumer_user_id` with the rows from step 3 to confirm the
two views agree on totals.  If they diverge, the rollup is
mid-flush; re-run after a minute.

### 6. Drill into freshness heatmap (optional)

The `freshness_heatmap` in step 1 returns one row per (domain,
day) cell with `freshness_violations` count.  No plugin tool
ships for hour-level granularity — the browser surface shows
that via tooltips.  Agents that need finer detail can compose
the raw query through `pql_query` against
`data_product_query_cost` directly.

### 7. Tear down

No tear-down is needed; this walkthrough only reads.  The
rollup table is append-only; the hourly scheduler runs by
default at 5 minutes past the hour.

## Found bugs

(none at time of writing — fill in during the first live replay)
