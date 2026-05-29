# Data Product Lifecycle — draft → active → deprecated → retired → archived

> **Mode:** `hybrid` · **Surface:** product Overview Lifecycle card + header pill + `/api/data-products/{c}/{s}/lifecycle*`

Walks a steward through the full lifecycle state-machine of a data
product, validates the audit history view, and exercises the
agent-driven `propose` path.

## Preconditions

* PointlesSQL running.
* A loaded data product `main.sales_gold` (see `data-products.md`).
* Logged in as the product's steward (or admin).

## Browser flow

| Step | Expect |
|---|---|
| Open `/data-products/main/sales_gold` → Overview | Lifecycle card renders, badge reads `active` |
| Click **Deprecate** | Confirmation modal; on confirm, badge flips to `deprecated`, history adds a row "active → deprecated by <you>" |
| Click **Retire** in the open form | Optional replacement URN field; submit → badge `retired`, replacement link (if set) renders next to "Changed" timestamp |
| Refresh page | Lifecycle state persists across reloads |
| Click **Archive** | Badge `archived`; only **Restore** target remains |
| Click **Restore** | Badge back to `active`; replacement field cleared |
| Open the **History** dropdown | Every transition above shows newest-first with actor + timestamp |

## Agent flow (Hermes)

```python
from hermes_plugin_pointlessql import PointlessClient

client = PointlessClient(...)

# Direct (steward / admin):
client.set_data_product_lifecycle(
    catalog="main", schema="sales_gold", target_slug="deprecate"
)

# Proposal (any user; needs review):
client.propose_data_product_lifecycle(
    catalog="main", schema="sales_gold", target_slug="retire",
    note="Replaced by main.sales_v2",
)
```

## Discovery envelope

```bash
curl -s http://localhost:8000/api/data-products/main/sales_gold/discovery \
  | jq '.lifecycle'
```

Returns `{"state":"active","changed_at":"...", "replacement_uri":null, "history_url":"..."}`.

## Common issues

* **HTTP 409 on transition** — illegal state-machine move; the
  cock-block shows reachable_targets you actually can transition to.
* **History empty** — only transitions recorded *after* the upgrade
  show up; existing products start `active` with no history.
