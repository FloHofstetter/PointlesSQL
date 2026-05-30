# Admin mesh-dashboard walkthrough

> **Mode:** `browser` · **Surface:** /admin/mesh-dashboard

End-to-end exercise of the mesh-health-full dashboard: vital-signs
cards, cost-by-product table, top-consumers table.  Tests the
parallel-fetch contract (`/api/mesh/health/full` +
`/api/cost/by-product` + `/api/cost/by-consumer`).

## Preconditions

- E2E stack up + `auth.md` ran first (admin signed in).
- Optional: at least one query executed through Lens so the cost
  meter has populated `data_product_query_cost`.  Without that the
  cost tables show empty-state rows — which the walkthrough still
  asserts cleanly.

## Walkthrough

1. **Land on the mesh dashboard.**
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/mesh-dashboard')`.
   - Assert: page title contains "Mesh dashboard · PointlesSQL".
     Heading reads "Mesh dashboard"; right-aligned hint reads
     "7-day window".

2. **Verify the four vital-signs cards.**
   - Action: read each `.h2.mb-0` element in the top row.
   - Assert: four cards labelled Products / Green / Red / Total
     est. cost (7d).  Each renders a number (or `—` on a fresh
     workspace).  Green is text-success, Red is text-danger.

3. **Cost-by-product table renders.**
   - Action: locate the card titled "Cost by product".
   - Assert: table headers read Product / Queries / Est. cost /
     Bytes scanned.  Either at least one row (when seeded) or the
     empty-state row "No cost data yet."

4. **Top-consumers table renders.**
   - Action: locate the card titled "Top consumers".
   - Assert: table headers read Consumer / Queries / Cost.  Either
     rows or the empty-state row "No consumers yet."

5. **No error card.**
   - Action: read the page for any `text-danger` card body.
   - Assert: the error card is hidden (`x-show="error"` not active);
     the dashboard loads cleanly under standard admin auth.

## Found bugs

(none at time of writing — fill in during the first live replay)
