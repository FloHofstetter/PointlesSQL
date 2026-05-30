# Product quota enforcement walkthrough

> **Mode:** `agent` · **Surface:** `pql_set_workspace_quota` + `pql_set_data_product_policy` + cost telemetry

End-to-end replay of a Family-A agent configuring a quota,
triggering a deliberate breach, and observing the 429 envelope
that the `before_read` cost gate emits.  Browser-pendant: the
Workspace Governance form + the per-product policy override on
the data-product detail page.

PointlesSQL carries three quota fields in the workspace
governance row and per-product policy override:

* `max_cost_per_day` — daily ceiling on accumulated cost per
  consumer (numeric).
* `max_queries_per_hour` — hourly ceiling on query count per
  consumer (integer).
* `quota_enforcement` — one of `off` (no checks),
  `warn` (log via observability hook), or `strict` (raise 429
  `QuotaExceededError`).

Inheritance is product ⇐ workspace; an unset product field
falls back to the workspace default.  This playbook exercises
the agent surface for both layers.

## Prerequisites

- A running PointlesSQL with the API key reaching an admin
  principal (for the workspace-default set) and a steward on
  the target product (for the override).
- A `hermes-agent` session loaded with the
  `hermes-plugin-pointlessql` plugin.
- A data product registered at `main.silver` that the agent can
  query via `pql_query` (or `pql_read_table`).

## Steps

### 1. Inspect the current quota state

Drive `pql_get_data_product_policy` for `main.silver`.  The
response carries the 12 POLICY_FIELDS rows; locate the three
quota fields.  On a fresh setup they read
`quota_enforcement: "off"` (workspace default) and the limits
are `null`.

### 2. Set a strict workspace-default quota

Drive `pql_set_workspace_quota` with:

```json
{
  "max_cost_per_day": 50.00,
  "max_queries_per_hour": 100,
  "quota_enforcement": "strict"
}
```

Verify `{ok: true, data: {updated_fields: [...]}}`.  The audit
row `governance.workspace_quota_set` records the field names
written.

### 3. Re-read the product policy

Drive `pql_get_data_product_policy` again.  The three quota
fields now inherit the workspace values.  The product itself
has no override → the workspace value is the effective ceiling.

### 4. Trigger a breach

Drive `pql_query` against `main.silver.orders` more than 100
times (or set `max_queries_per_hour: 1` in step 2 to make this
single-shot).  The 101st (or 2nd) query returns an error
envelope:

```json
{
  "ok": false,
  "error": "http 429",
  "code": "quota_exceeded",
  "detail": "max_queries_per_hour breached on workspace ..."
}
```

The before_read hook raises `QuotaExceededError` (status_code=
429) carrying `metric`, `limit`, `observed`, `consumer_id`, and
`data_product_id` as structured envelope fields.

### 5. Override on the product (steward)

Drive `pql_set_data_product_policy` with:

```json
{
  "catalog": "main",
  "schema": "silver",
  "fields": {
    "quota_enforcement": "off"
  }
}
```

The product override now reads `off`; the workspace default
stays `strict` for other products.  Re-run `pql_query` against
`main.silver` — the call succeeds because the product override
short-circuits the gate.

### 6. Switch to warn mode

Set the product policy `quota_enforcement: "warn"`.  Re-trigger
the breach as in step 4.  The query succeeds (warn mode
allows), but an observability hook fires once per breach with
the same metric / limit / observed payload.  The agent does
not see a difference in the envelope (200 with results).

### 7. Per-consumer telemetry confirms the count

Drive `pql_cost_by_consumer` with no window args.  The newly-
breached consumer's `total_queries` matches what the agent
issued during step 4–6.  Cross-check with
`pql_cost_by_product` for `main.silver` — the two views
agree on `total_queries`.

### 8. Tear down

Reset the product policy to the workspace default by setting
`{quota_enforcement: null}` via `pql_set_data_product_policy`
(or via the browser surface).  Reset the workspace default
via `pql_set_workspace_quota` with `{quota_enforcement: "off"}`.

## Found bugs

(none at time of writing — fill in during the first live replay)
