# Data-product contract tests walkthrough

> **Mode:** `agent` · **Surface:** three `pql_*` contract-test tools

End-to-end replay of a Family-A agent declaring contract tests on
a data product, attaching a synthetic Faker fixture, kicking a
synchronous run, and reading the pass / fail / error verdicts —
the agent-flow complement to the browser surface (Contract Tests
tab on the data-product detail page).

Contract tests encode acceptance criteria that consumers care
about (row-count floors, freshness windows, distribution
constraints).  Synthetic fixtures let the same tests run in CI
or before the materialised table exists.  This playbook
exercises the three tools shipped to close the deferred plugin
scope:

* `pql_declare_contract_test` — author or update one test.
* `pql_declare_synthetic_fixture` — register a Faker-driven
  fixture for an output table.
* `pql_run_contract_tests` — kick a synchronous run (synthetic
  or live).

## Prerequisites

- A running PointlesSQL with the API key reaching a steward or
  admin principal for the target product.
- A `hermes-agent` session loaded with the
  `hermes-plugin-pointlessql` plugin (`uv pip install -e
  ~/git/hermes-plugin-pointlessql`).
- A data product registered at `main.silver` with an output port
  declared on the table `orders` (or substitute your own).

## Steps

### 1. Declare a row-count-floor test

Drive `pql_declare_contract_test` with:

```json
{
  "catalog": "main",
  "schema": "silver",
  "name": "orders_row_count_floor",
  "assertion_kind": "row_count_range",
  "assertion_spec": {"min": 1000},
  "severity": "error",
  "enabled": true
}
```

Verify `{ok: true, data: {contract_test: {id, name, ...}}}`.
The id is product-unique by name — repeating the call updates
the spec rather than creating a duplicate.

### 2. Declare a freshness test

Drive `pql_declare_contract_test` again with:

```json
{
  "catalog": "main",
  "schema": "silver",
  "name": "orders_freshness_24h",
  "assertion_kind": "freshness",
  "assertion_spec": {"max_age_hours": 24},
  "severity": "warn"
}
```

Verify a second row appears.  `severity: warn` keeps the
materialise gate open even on fail; `severity: error` is the
hard stop.

### 3. Register a synthetic fixture for `orders`

Drive `pql_declare_synthetic_fixture` with:

```json
{
  "catalog": "main",
  "schema": "silver",
  "table_name": "orders",
  "generator_spec": [
    {"name": "order_id", "kind": "uuid"},
    {"name": "customer_email", "kind": "email"},
    {"name": "amount", "kind": "float", "min": 0, "max": 1000},
    {"name": "created_at", "kind": "iso8601_ts"}
  ],
  "row_count": 250
}
```

Verify `{ok: true, data: {fixture: {id, row_count: 250}}}`.
Available generator kinds: `email`, `name`, `int`, `float`,
`iso8601_ts`, `choice`, `uuid`, `bool` — all seed-reproducible.

### 4. Run the tests in synthetic mode

Drive `pql_run_contract_tests` with:

```json
{ "catalog": "main", "schema": "silver", "mode": "synthetic" }
```

Verify the envelope:

```json
{
  "ok": true,
  "data": {
    "mode": "synthetic",
    "total": 2,
    "passed": 1,
    "failed": 1,
    "errored": 0,
    "results": [ ... ]
  }
}
```

In synthetic mode every test executes against the registered
fixture rows; `orders_row_count_floor` typically passes
(`row_count: 250 ≥ 1000` fails — adjust `row_count` or the
floor to taste).  `orders_freshness_24h` evaluates against the
fixture's synthetic timestamps.

### 5. Run again in live mode

Drive `pql_run_contract_tests` with:

```json
{ "catalog": "main", "schema": "silver", "mode": "live" }
```

If the materialised `main.silver.orders` table exists, the
runner skips the fixture and asserts against the live rows.
If the table is missing the runner returns a `status: error`
for that test rather than crashing the whole batch.

### 6. Inspect a result history

Re-run step 4 a few times, then read individual histories via
the backend GET endpoint
`/api/data-products/main/silver/contract-tests/<id>/results`
(no plugin tool ships for this — the rolling ledger is mostly a
browser concern).  The newest run appears first; each row
carries `status` (pass / fail / error), `observation` (kind-
specific payload), and `run_at`.

### 7. Tear down (optional)

Remove tests and fixtures via the matching browser surface
(`/data-products/main/silver` → Contract Tests tab → delete
button) or the backend `DELETE` endpoints
`/api/data-products/main/silver/contract-tests/{id}` and
`/api/data-products/main/silver/fixtures/{id}`.  The plugin
does not expose deletes by design.

## Found bugs

(none at time of writing — fill in during the first live replay)
