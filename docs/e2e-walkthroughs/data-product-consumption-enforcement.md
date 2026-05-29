# Data Product Consumption Enforcement — D2 declared-input gate

> **Mode:** `hybrid` · **Surface:** Overview consumption card + Governance selector + `X-PointlesSQL-Authoring-Product` header + `/api/data-products/{c}/{s}/consumption-acknowledgements`

Walks an operator through flipping a product into `strict` consumption
mode and verifies that an undeclared upstream read is blocked.

## Preconditions

* PointlesSQL running.
* Two products loaded: `raw.events` (the upstream) and
  `main.fraud_gold` (the consumer).
* `main.fraud_gold` declares `raw.events` as an input port (see
  `data-products.md` → input ports).
* Logged in as the consumer's steward.

## Browser flow

| Step | Expect |
|---|---|
| Open `/data-products/main/fraud_gold` → Overview | Consumption card renders, badge `advisory (workspace)` |
| Set the Governance-tab selector to `strict` | Card badge flips to `strict (product)`; workspace default unchanged |
| Open a notebook and run `pql.read("undeclared.thing.x")` *with* `X-PointlesSQL-Authoring-Product: main.fraud_gold` | HTTP 403 envelope: `{"code":"consumption.blocked","mode":"strict","source":"undeclared.thing.x", ...}` |
| Same notebook, now read `pql.read("raw.events.orders")` | 200 OK; declared upstream, silent allow |
| Flip back to `advisory` | Same undeclared read now succeeds; an audit row appears in the "Recent Undeclared Consumption" list |
| Steward clicks **Ack** on a row | Audit row marked `consumption.acknowledged`; can be re-listed for audit drift later |

## Agent flow (Hermes)

```python
client.set_consumption_enforcement(
    catalog="main", schema="fraud_gold", mode="strict"
)

# Acknowledge a flagged event:
client.acknowledge_undeclared_consumption(
    catalog="main", schema="fraud_gold", event_id=42
)
```

## curl probes

```bash
# advisory: still 200, but a consumption.undeclared row lands in audit
curl -H "X-PointlesSQL-Authoring-Product: main.fraud_gold" \
     http://localhost:8000/api/catalogs/random/random/tables/x/preview

# inspect the audit feed
curl -s http://localhost:8000/api/data-products/main/fraud_gold/consumption-acknowledgements \
  | jq '.items[:3]'
```

## Common issues

* **No 403 in strict mode** — the request must carry
  `X-PointlesSQL-Authoring-Product` (or hit a notebook bound to a
  product); free-form reads bypass the check by design.
* **Workspace default not changing** — set it from `/admin/governance`,
  per-product overrides win.
