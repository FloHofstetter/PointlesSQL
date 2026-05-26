# Data Products — yaml-declared UC schemas

> **Mode:** `hybrid` · **Surface:** yaml reload (curl) + `/data-products` browse + 5-tab detail

Replays the happy path: a data team commits a
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

## Playwright MCP script

Browser-only verifications after the curl reload completes:

1. `browser_navigate('http://127.0.0.1:8000/data-products')`
   — assert one card with title `main.sales_gold`,
   `v1.0.0` badge, `SLA 60 min`, `mailto:alice@example.com`.
2. `browser_click(".data-product-card a")`
   — URL becomes `/data-products/main/sales_gold`; assert 5
   tabs: Overview / Contract / Tables / Compliance / Activity.
3. `browser_click("Contract")` — assert the `orders` table
   row carries the `PK badge` for `order_id` and a 4-column
   types table.
4. `browser_click("Tables")` — assert one row whose `Status`
   pill reads `OK` (or whatever the freshness state is).
5. `browser_click("Compliance")` — assert the cell
   `track_value_changes` shows the right boolean from the seed.
6. `browser_click("Activity")` — assert the most-recent
   ingestion row carries the agent-run id from the
   `pointlessql.data_product.compliant_write` event.
7. `browser_evaluate('() => fetch("/api/data-products").then(r => r.json())')`
   — assert the JSON keys match what the cards rendered.

## Marketplace polish

> **Surface:** ``/data-products`` browse + the
> per-product detail tabs (Discussion / Reviews / README) + the
> new ``/notifications`` inbox.

Phase 71 layered six social affordances on top of the data-product surface.  Replay these after the curl-reload above
has the cached product visible:

1. **Discussion tab**:
   - `browser_navigate('http://127.0.0.1:8000/data-products/main/sales_gold')`
   - `browser_click('button[data-pql-tab-key="discussion"]')`
   - Type a body in `textarea.pql-comment-new`, click
     `button.pql-comment-submit`; assert the row appears with the
     admin's display name.
   - Reply via the inline "Reply" button + `textarea.pql-comment-reply`
     + "Post reply".  Soft-delete the parent ("Delete" button);
     assert the parent renders `[deleted]` with the reply still
     attached.

2. **Reviews tab**:
   - `browser_click('button[data-pql-tab-key="reviews"]')`
   - Click the 4th star (`i.bi-star[data-star-value="4"]`), fill
     `textarea.pql-review-body`, click `button.pql-review-submit`.
   - Assert the new `div.pql-review-card` carries `★★★★☆`.
   - Reload — the header pill `span.pql-dp-stars-badge` shows
     `★ 4.0 (1)`.

3. **Follow + counter + ``/data-products/followed``**:
   - On the detail page, click `button.pql-dp-follow-btn`; assert
     it flips to "Following" + `pql-dp-follower-count` shows
     "· 1 follower".
   - Navigate to `/data-products/followed`; assert the row
     `tr.pql-followed-row[data-followed-ref="main.sales_gold"]`
     exists.

4. **Notification fan-out + bell**:
   - Log out, log in as `nonadmin@test.com`; follow the same DP.
   - Switch back to admin, post a comment.
   - Re-log as non-admin; the topbar bell
     (`div.pql-notif-bell span.pql-notif-bell-badge`) shows "1".
   - Click `/notifications`; assert the row references the
     comment and clicking it deep-links to the discussion tab.
   - Click "Mark all read"; assert the bell badge disappears.

5. **README tab + diff**:
   - As steward (or install-admin), open the DP detail page,
     click `button[data-pql-tab-key="readme"]`.
   - Click `button.pql-readme-edit-btn`, enter "v1 body",
     click `button.pql-readme-save`.
   - Edit again, save "v2 body".
   - Click `button.pql-readme-history-btn`; tick `from=1`,
     `to=2`, click `button.pql-readme-compare-btn`.  Assert
     `pre.pql-readme-diff` carries `-v1 body` + `+v2 body`.

6. **Browse-page rework**:
   - Navigate to `/data-products`.
   - Assert the table fingerprint (`.pql-dp-table-card .pql-dp-table`)
     ships sortable columns.
   - Click the **Followers** header twice; the rows resort
     descending by `follow_count`.
   - Toggle the chip `[Has README]`; the listing narrows to DPs
     that have a README row.
   - Click the cards-view button (`.pql-dp-view-toggle [data-view="cards"]`);
     reload — `localStorage.pql.dp.view-mode` survives.

## Anti-goals

- The yaml is canonical; the admin UI does **not** edit it.
  Git-blame is the audit log.
- No DLT-bundle generator — PointlesSQL **is** the platform,
  not an export target.
- No domain-specific RBAC ladder — Workspace + scopes
  (admin/supervisor/auditor) reach everything that needs gating.
- Phase 71 does **not** rebuild the user-graph: there are no
  profile pages, no follow-user, no DM.  Social affordances stay
  scoped to data-products.
