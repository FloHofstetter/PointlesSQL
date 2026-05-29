# Data Product Bitemporal Enforcement — F1/F5 event-time + processing-time gate

> **Mode:** `hybrid` · **Surface:** Overview Bitemporal card + `PUT /api/data-products/{c}/{s}/bitemporal-policy` + `pql.write_table` write-path

Walks a steward through flipping `enforcement=required` on a product
and verifies that a write missing the event-time column is refused.

## Preconditions

* PointlesSQL running.
* Product `main.events_gold` loaded (any table OK).
* Logged in as the product's steward.

## Browser flow

| Step | Expect |
|---|---|
| Open `/data-products/main/events_gold` → Overview | Bitemporal card renders, badge `off` (or workspace default) |
| Flip Governance → Bitemporal to `required` + `require_event_time=true` | Card badge flips to `required`; "Event-time column" row shows `_event_time` (default) |
| In a notebook: `pql.write_table(df_without_event_time, "main.events_gold.t1", mode="append")` | `BitemporalRequirementError`: "event-time column `_event_time` missing from write frame" |
| Same notebook, add `df["_event_time"] = pd.Timestamp.utcnow()`, retry | Write succeeds; `_processing_time` column auto-injected by the write path |
| Inspect the Delta table | Both `_event_time` and `_processing_time` columns present (schema evolved via `mergeSchema=True`) |

## Agent flow (Hermes)

```python
client.set_data_product_bitemporal_policy(
    catalog="main", schema="events_gold",
    enforcement="required", require_event_time=True,
)

# Confirm:
client.get_data_product_bitemporal_policy(
    catalog="main", schema="events_gold"
)
# → {"enforcement":"required", "require_event_time": True, ...}
```

## Common issues

* **Stamp not injected** — check `enforcement` is `required` *or*
  `opt_in` + workspace setting `inject_processing_time=true`.
* **Wrong dtype** — `_event_time` must be a pandas
  `datetime64[*]` / pyarrow `timestamp` column; strings raise.
* **Pre-existing table** — first write after enabling `required`
  evolves the Delta schema; future writes maintain it.
