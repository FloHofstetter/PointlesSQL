---
title: ADR-0012 Cost-attribution + quotas + mesh-health dashboard
status: Accepted
date: 2026-05-30
---

# ADR-0012 — Cost-attribution + quotas + mesh-health dashboard

## Status

**Accepted** (2026-05-30).

## Context

Up to phase 145 PointlesSQL tracked query telemetry only in the
free-form audit log and in the lens cost gate's session counter.
The data-mesh book asks for two things on top:

* **Per-product / per-consumer cost attribution** so an owner can
  see who is paying for the queries against their product and a
  team lead can see which products their consumers spend on.
* **Quota enforcement** so a runaway consumer cannot drain a
  shared product budget — the standard HTTP 429 rate-limit story,
  with the same product⇐workspace inheritance every other policy
  field uses.

Combined, these two unlock the **mesh-health dashboard** the book
describes: per-domain SLO rollups, cost trends, top consumers, and
recent deliveries on one surface.

## Decision

Phase 146 ships three intertwined pieces.

### 1. Cost ledger as raw + hourly rollup

Two tables:

* `data_product_query_cost` is the raw per-query meter row.  The
  meter writes one row per executed PQL read; columns carry cost,
  bytes/rows, attribution (consumer user + api-key + authoring
  product + consumer product), and an error class on failure.
* `data_product_cost_buckets_hourly` is the hourly rollup the
  scheduler computes from the raw ledger.  UNIQUE(hour, product,
  consumer) keeps re-runs idempotent — the rollup writes the same
  bucket the second time without duplicating rows.

The split is deliberate: raw rows answer ad-hoc questions ("why is
this query expensive?"); buckets answer aggregate questions ("what
did this product cost yesterday?").  Rotating the raw table after
N days is a forward-cost we accept — phase 146 ships the rollup
job, retention rotation is a follow-up.

### 2. Quota check as a stateless aggregator

`check_quota(consumer_user_id, data_product_id, mode)` reads the
effective policy through the standard `get_effective_policy`
helper, then aggregates the running day + the current hour from the
bucket table.  Three modes:

* `off` — no aggregation, return immediately.
* `warn` — return a :class:`QuotaCheck` with `breached=True`
  when a limit is crossed; never raise.
* `strict` — raise :class:`QuotaExceededError` (status 429) when
  any limit is crossed.

The decision lives in `services/cost/_quota.py` so other call
sites (Cedar policies, agent gates) can consult it without
ploughing through HTTP layers.

### 3. Mesh-health-full as an aggregator on top of mesh-health

`services/cost.mesh_health_full(workspace_id)` calls the existing
`services/mesh.mesh_health` for the green/red bands and layers:

* `per_domain` — products grouped by their `domain` field.
* `cost_trend` — `cost_by_product` over the last 7 days.
* `top_consumers` — `cost_by_consumer` truncated to 10.
* `recent_deliveries` — populated by the existing event-port code
  on demand.

The aggregator is read-only; mesh-health-full does not mutate the
DB.  Cache TTL is intentionally absent in 146 — the surface is
admin-only and the workloads are small.  TTL becomes interesting if
the dashboard moves onto the public landing page; revisit then.

### 4. QuotaExceededError → HTTP 429

`QuotaExceededError(PointlessSQLError)` with `status_code=429`
carries `metric`, `limit`, `observed`, `consumer_id`,
`data_product_id` as extension members so the client envelope
surfaces actionable context.  Added `ErrorCode.QUOTA_EXCEEDED` to
the central enum so the wire format follows the existing pattern.

## Consequences

**Positive.**

- Owners get cost-per-product and cost-per-consumer without a
  separate analytics stack — same database, same auth.
- Quota enforcement integrates with the existing policy
  inheritance (off / warn / strict) so the operational model is
  identical to consumption-enforcement.
- Mesh-health-full unblocks the "single dashboard the book
  describes" without rebuilding the SLO substrate that already
  exists.

**Negative.**

- Cost is **estimated**, not real.  The meter persists the cost-
  gate estimate at execution time; the real DuckDB cost (memory,
  CPU) is not captured.  Acceptable for the budget-control story;
  for billing-grade attribution a future phase needs to wire in
  the engine's post-execution cost.
- The raw ledger grows linearly with traffic; retention rotation
  is a follow-up phase, not 146.
- Per-consumer-per-hour aggregation happens in Python on the
  current-hour subset.  At >100k queries/hour the in-memory sum
  becomes lossy; the SQL-side aggregation is a forward-cost we
  accept for now.
- Quota inheritance follows product⇐workspace⇐off; there is no
  "platform default" today.  Adding a platform tier requires a new
  ADR (mirrors the Cedar / policy-module follow-up).

## Open follow-ups

- **Engine-side cost integration.**  Replace estimated cost with
  real cost where the runtime exposes it (DuckDB query stats).
- **Raw-ledger retention.**  Rotate `data_product_query_cost`
  rows older than the retention window.
- **Cache TTL on mesh-health-full.**  When the surface is no
  longer admin-only.
- **SQL-side hourly aggregation.**  GROUP BY on the buckets when
  Python iteration becomes a bottleneck.
