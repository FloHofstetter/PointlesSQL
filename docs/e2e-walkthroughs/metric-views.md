# Metric views walkthrough

> **Mode:** `browser` · **Surface:** /metric-views + /api/metric-views

End-to-end exercise of the semantic layer: define a metric view
over a seeded table, query it through the picker panel, verify the
compiled SQL provenance, and confirm governance (an expression that
references a foreign table never bypasses SELECT enforcement).

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first.
- A seeded table with a numeric column exists (the steps call it
  `e2e.demo.orders` with `amount` + `region` columns — substitute
  the real seeded FQN from `scripts/seed-e2e.py`).

## Walkthrough

### Part A — Define (3 steps)

1. **Land on the browser**.
   - Action: `browser_navigate('http://127.0.0.1:8000/metric-views')`.
   - Assert: title `Metric Views · PointlesSQL`, heading "Metric
     Views", catalog/schema pickers; the "New metric view" button is
     disabled until a schema is picked.

2. **Pick the schema**.
   - Action: select the seeded catalog, then its schema.
   - Assert: the table renders with the empty state "No metric
     views in this schema yet."

3. **Create the view**.
   - Action: click "New metric view"; name `revenue`, source table
     `e2e.demo.orders`; dimension `region` / expr `region`; measure
     `total_revenue` / expr `sum(amount)`; filter `amount > 0`.
     Click "Create metric view".
   - Assert: the editor closes and the list shows
     `<catalog>.<schema>.revenue` with 1 dimension and 1 measure.

### Part B — Query (3 steps)

4. **Open the query panel**.
   - Action: click "Query" on the row.
   - Assert: dimension + measure checkboxes render (first of each
     pre-checked), plus filter / order / limit inputs.

5. **Run a grouped query**.
   - Action: keep `region` + `total_revenue` checked, order by
     `total_revenue desc`, limit 10; click "Run".
   - Assert: a result table renders with `region` and
     `total_revenue` columns; the row/duration line shows; clicking
     "compiled SQL" reveals a SELECT carrying
     `SUM(amount) AS "total_revenue"`, the baked-in
     `amount > 0` filter, and `GROUP BY 1`.

6. **Grand total**.
   - Action: uncheck `region`; Run.
   - Assert: exactly one row, no GROUP BY in the compiled SQL.

### Part C — Governance (2 steps)

7. **Reject a malformed measure**.
   - Action: Edit the view; add measure `evil` with expr
     `1; DROP TABLE x`; Save.
   - Assert: the editor's red alert shows the single-expression
     validation message; the definition is unchanged after reload.

8. **Foreign references stay enforced**.
   - Action: (API check) run
     ```js
     async () => {
       const r = await fetch('/api/metric-views/<full_name>/query', {
         method: 'POST', headers: {'Content-Type': 'application/json'},
         body: JSON.stringify({measures: ['total_revenue'],
                               where: "region IN (SELECT region FROM secret.schema.t)"})});
       return r.status;
     }
     ```
   - Assert: the request fails (4xx) — the compiled query's table
     references run through the same SELECT enforcement as the SQL
     editor, so an unknown/ungranted table never executes. Console
     stays clean throughout.
