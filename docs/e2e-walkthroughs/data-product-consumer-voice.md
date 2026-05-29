# Data Product Consumer Voice — C consumer-contributed use cases + ratings

> **Mode:** `playwright-only` · **Surface:** Overview Use-Cases card + Rating widget + `/api/data-products/{c}/{s}/use-cases` + `/rating`

Walks any user through sharing a use case, voting on someone else's,
and giving the product a 1-5 rating.  Producer-side metadata gets a
consumer-side counterweight.

## Preconditions

* PointlesSQL running.
* Loaded product `main.orders_gold`.
* Two test accounts (let them be `alice` and `bob`).

## Browser flow

| Step | Expect |
|---|---|
| As `alice`, open `/data-products/main/orders_gold` → Overview | Use Cases card empty, Rating widget reads "— / 5 · 0 rater(s)" |
| Fill the "Share a use case" form ("ML training inputs", "fraud detection features") → submit | Use case appears with vote count `0` |
| Pick 5★ + "stellar" comment, click Save | Header reads "5.0 / 5 · 1 rater(s)" |
| Logout, login as `bob` | Sees alice's use case |
| Click the upvote button on alice's use case | Vote count `1`; button toggles to "voted" style |
| `bob` picks 3★ + "good but slow" | Header now "4.0 / 5 · 2 rater(s)" |
| `bob` clicks his own upvote button again | Toggles back to `0` |

## Agent flow (Hermes)

```python
client.add_data_product_use_case(
    catalog="main", schema="orders_gold",
    title="ML training inputs",
    body_md="Fraud detection features",
)

client.vote_data_product_use_case(
    catalog="main", schema="orders_gold", use_case_id=7,
)

client.rate_data_product(
    catalog="main", schema="orders_gold", score=5, comment="stellar",
)
```

## Discovery envelope

```bash
curl -s http://localhost:8000/api/data-products/main/orders_gold/discovery \
  | jq '{rating, use_cases: (.use_cases[:3])}'
```

## Common issues

* **Score outside 1..5** — HTTP 400; the UI clamps the buttons but
  the API rejects out-of-range values.
* **Vote idempotency** — toggling the same vote twice cancels it;
  votes count is a cached aggregate, refreshed on each toggle.
