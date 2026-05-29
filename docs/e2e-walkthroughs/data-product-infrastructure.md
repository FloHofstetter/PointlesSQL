# Data Product Infrastructure — B8 declarative deployment block

> **Mode:** `playwright-only` · **Surface:** Overview Infrastructure card + `GET/PUT /api/data-products/{c}/{s}/infrastructure`

Walks a steward through documenting a product's deployment shape
(storage class, compute runtime, access methods, region, free-text
notes).  Pure declarative — no enforcement engine.

## Preconditions

* PointlesSQL running.
* Loaded product `main.orders_gold`.
* Logged in as the product's steward.

## Browser flow

| Step | Expect |
|---|---|
| Open `/data-products/main/orders_gold` → Overview | Infrastructure card renders; storage_class / compute_runtime / access_methods / region all `—` |
| Click **Edit** | Form opens with five fields + Save / Cancel |
| Pick `delta` / `pql` / `sql, file` / `eu-west-1` / "Self-serve via Hermes" | Save → form closes, card shows the row |
| Reload page | Values persist |
| Confirm `/api/data-products/main/orders_gold/discovery` `.infrastructure` block reflects the row | yes |

## Agent flow (Hermes)

```python
client.set_data_product_infrastructure(
    catalog="main", schema="orders_gold",
    storage_class="delta",
    compute_runtime="pql",
    access_methods=["sql", "file"],
    region="eu-west-1",
    notes="Self-serve via Hermes",
)
```

## Common issues

* **storage_class rejected** — must be one of
  `delta` / `parquet` / `external`.
* **access_methods not a list** — pass a JSON array; the UI form
  splits a comma-separated string.
