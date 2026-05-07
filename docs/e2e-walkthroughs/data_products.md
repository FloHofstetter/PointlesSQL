# Data Products — yaml-declared UC schemas

Replays the Phase-50 happy path: a data team commits a
`pointlessql.yaml` declaring their schema as a data product;
PointlesSQL caches it; subsequent `pql.write` calls are
contract-checked, the cockpit shows compliance, and a stale
table fires a freshness CloudEvent.

## Setup

1. Start PointlesSQL with the yaml search path pointing at this
   walkthrough's fixture directory:

   ```bash
   POINTLESSQL_DATA_PRODUCTS_YAML_SEARCH_PATHS=/tmp/walkthrough-products \
   POINTLESSQL_DATA_PRODUCTS_SCAN_INTERVAL_SECONDS=60 \
   uv run pointlessql
   ```

2. Drop a `pointlessql.yaml` at
   `/tmp/walkthrough-products/pointlessql.yaml`:

   ```yaml
   data_product:
     name: Sales Orders
     version: "1.0.0"
     description: Curated orders facts joined with customer dim.
     catalog: main
     schema: sales_gold
     steward_email: alice@example.com
     sla_minutes: 60
     tables:
       - name: orders
         primary_key: [order_id]
         columns:
           - {name: order_id,    type: long,      nullable: false}
           - {name: customer_id, type: long,      nullable: false}
           - {name: order_total, type: double,    nullable: true}
           - {name: ordered_at,  type: timestamp, nullable: false}
   ```

3. Log in as admin and POST to the reload endpoint to materialise
   the yaml into the cache:

   ```bash
   curl -X POST http://localhost:8000/api/data-products/reload \
        -H "Cookie: <admin-session>"
   ```

   Expect `{"loaded": 1, "paths": [...]}`.

## Browser flow (recommended)

| Step | Expect |
|---|---|
| Open `/data-products` | One card "main.sales_gold" with v1.0.0, SLA 60 min, mailto:alice@example.com link |
| Click the card | 5 tabs render; Overview shows the steward + last-loaded ts + UC ref |
| Switch to **Contract** | One table "orders", PK badge `order_id`, four-column table with type badges |
| Switch to **Diff** | Each declared table either ✅ Compliant or ⚠ surface (`table not in UC` / drift fields) |
| Switch to **Lineage** | Cytoscape graph; if no lineage edges yet, the empty-state alert renders |
| Switch to **Compliance** | Empty-state alert; populates after the first `pql.write` against the schema |

## Agent flow (Hermes plugin)

```python
# After registering the plugin and loading at least one yaml
from hermes_plugin_pointlessql import PointlessClient

client = PointlessClient(...)

print(client.list_data_products())
# → {"workspace_id": 1, "data_products": [{"ref": "main.sales_gold", ...}]}

print(client.get_data_product(catalog="main", schema="sales_gold"))
# Full detail incl. tables + recent_events.

print(client.get_data_product_diff(catalog="main", schema="sales_gold"))
# Live yaml↔Delta diff per declared table.
```

The same five tools are exposed through Hermes:
`pql_list_data_products`, `pql_get_data_product`,
`pql_get_data_product_contract`, `pql_check_contract_compliance`,
`pql_data_product_compliance_history`.

## Compliant write

```python
import pandas as pd
from pointlessql import PQL

pql = PQL()
df = pd.DataFrame({
    "order_id":    [1, 2, 3],
    "customer_id": [10, 20, 30],
    "order_total": [9.99, 19.99, 29.99],
    "ordered_at":  pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-03"]),
})
pql.write_table(df, "main.sales_gold.orders", mode="overwrite",
                agent_run_id="<some-run>")
```

Expected: write succeeds; the Compliance tab gains a `compliant`
event row tied to the new `agent_run_operations` row.

## Breaking write (refused)

Drop the contract-required `order_total` column and re-write:

```python
df_breaking = df.drop(columns=["order_total"])
pql.write_table(df_breaking, "main.sales_gold.orders", mode="overwrite",
                agent_run_id="<another-run>")
```

Expected: `DataProductContractViolation` raised; **no Delta IO**
happens (`Engine.write` is never invoked); the audit row's
`error_message` carries the violation; the Compliance tab gains
a `violated` event row with `details.missing_columns =
["order_total"]`.

## Freshness alert

1. Confirm `sla_minutes` is set on the product (the seeded yaml
   uses 60).
2. Wait one scan interval after the latest write is older than
   the SLA (or override `now=` in a unit test).
3. Watch the audit-stream / Grafana for the
   `pointlessql.data_product.sla_violated` CloudEvent; the
   product's `last_alerted_at` is stamped to suppress repeat
   alerts within `re_alert_suppress_minutes` (default 60).

## Anti-goals

- The yaml is canonical; the admin UI does **not** edit it.
  Git-blame is the audit log.
- No DLT-bundle generator — PointlesSQL **is** the platform,
  not an export target.
- No domain-specific RBAC ladder — Workspace + scopes
  (admin/supervisor/auditor) reach everything that needs gating.
