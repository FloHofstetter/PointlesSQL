# Data Mesh — graph, health, entities, interop, SLOs

> **Mode:** `hybrid` · **Surface:** `/mesh` graph + `/mesh/health` rollup + `/mesh/entities` + `/admin/mesh-entities` + product Interop tab + Overview SLO panel

The mesh is a first-class plane: products connect into an emergent
dependency graph (from declared upstream input ports), share a
polysemic entity vocabulary that powers cross-product join hints,
expose a measured SLO set that rolls up into a health dashboard, and
carry a point-in-time + bitemporal read convention.

## Preconditions

1. `auth.md` — logged in as admin.
2. `scripts/seed-e2e.py` + `scripts/seed-mesh-demo.py` — the seed
   creates two products where `demo.hr` declares `demo.sales` as an
   `upstream_product` input port (one graph edge), per-table statistics,
   and two volume SLOs: a **passing** one on `demo.sales.orders`
   (target 10, observed 50) and a **failing** one on
   `demo.hr.employees` (target 1000, observed 10) — so the health
   rollup shows a mixed red/green band.

   ```bash
   uv run python scripts/seed-e2e.py
   uv run python scripts/seed-mesh-demo.py
   ```

## Walkthrough

1. **Mesh graph.**
   - Action: `browser_navigate('http://127.0.0.1:8000/mesh')`.
   - Assert: a cytoscape canvas (`#mesh-cy`) + the summary
     "2 products, 1 declared edges". `GET /api/mesh/graph` returns nodes
     `[demo.sales, demo.hr]` with edge `demo.sales → demo.hr`.

2. **Mesh health rollup.**
   - Action: `browser_navigate('http://127.0.0.1:8000/mesh/health')`.
   - Assert: a rollup "2 products · 1 green · 1 red · 75% objective pass
     rate" and a per-product table where `demo.hr` = red (1 passed / 1
     failed / 50%) and `demo.sales` = green (2 / 0 / 100%).

3. **Evaluate SLOs → audit log.**
   - Action: click "Evaluate SLOs now".
   - Assert: "Scanned 2 product(s), 1 violation(s)." Then
     `browser_navigate('http://127.0.0.1:8000/admin/audit?action=slo.violation')`
     — a row `slo.violation · data_product:demo.hr` appears.

4. **Entity registry.**
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/mesh-entities')`,
     fill Name `Customer`, click "Create".
   - Assert: a `Customer` (slug `customer`) row with "0" bindings.
   - Action: `browser_navigate('http://127.0.0.1:8000/mesh/entities')`.
   - Assert: the Customer entity renders (bindings list grows as you
     bind columns in step 5).

5. **Interop tab — bind + joinable + point-in-time + bitemporal.**
   - Action: `browser_navigate('http://127.0.0.1:8000/data-products/demo/sales?tab=interop')`.
   - Assert: the pane is **visible** (see BUG-128-01) with four cards:
     **Mesh neighbourhood** (cytoscape canvas), **Shared entities**,
     **Point-in-time read**, **Bitemporal convention**.
   - In **Shared entities** choose entity `Customer`, table `customers`,
     column `customer_id`; click "Bind" (`POST …/entities` → 200).
   - Repeat on `demo.hr` (`?tab=interop`): bind `Customer` to
     `employees` / `employee_id`.
   - On `demo.hr`, in **Shared entities** enter the other product
     `demo.sales` and click "Find join keys".
   - Assert: a hint `Customer  employee_id = customer_id` and a
     generated `SELECT * FROM demo.hr.employees AS l JOIN
     demo.sales.customers AS r ON l.employee_id = r.customer_id`.
   - In **Point-in-time read** set an "As of" timestamp + the products
     `demo.hr, demo.sales`; click "Resolve".
   - Assert: a manifest "As of <utc-instant>" listing each product's
     tables with a resolved Δ version (`v—` when the product has no real
     Delta history, as in the seed).
   - Assert: the **Bitemporal convention** card reads "Processing-time
     injection: off" and names the `_processing_time` / `_event_time`
     columns.

6. **Overview SLO panel.**
   - Action: `browser_navigate('http://127.0.0.1:8000/data-products/demo/sales?tab=overview')`.
   - Assert: a **Service-level objectives** panel showing "pass 100%"
     with a verdict table (freshness `pass`, volume `orders` gte 10
     observed 50 `pass`) and a steward/admin declare form.

## Found bugs

- **BUG-128-01** ✅ Fixed — the product **Interop tab rendered nothing**
  when selected (same root cause as the Governance tab). The
  Contract-tab partial
  [`tab_contract.html`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/_partials/data_product/tab_contract.html)
  was missing its closing `</div>`, nesting the Interop pane inside the
  Contract pane; on `?tab=interop` the parent Contract pane is
  `display:none` so the whole tab was invisible. Fixed by adding the
  missing closing `</div>`.

## Playwright MCP notes

- The Interop tab hosts a live cytoscape neighbourhood canvas that keeps
  the layout perpetually "unstable" for Playwright's auto-wait — a
  direct `browser_click` on the **Resolve** point-in-time button can
  time out on the stability check. Invoke the Alpine handler
  (`runPointInTime()`) via `browser_evaluate`, or click with a short
  explicit timeout, then assert on the rendered manifest.
- `mesh_health.html` passes the admin flag through `|tojson` — a
  **boolean**, so it renders unquoted (`meshHealth(true)`); single-quote
  `x-data` delimiters keep it consistent with the rest of the cluster.

## Anti-goals

- Honest measure/declare split: freshness, volume, completeness,
  statistical-shape drift, and lineage-coverage SLOs are **measured**;
  precision/accuracy, availability, and performance are **declarations**.
- The point-in-time endpoint returns a resolved-version **manifest**
  (a preview); the heavy snapshot read stays a PQL primitive.
- Processing-time injection is **opt-in** (default off) because it
  evolves the Delta schema; event/business-time stays a documented
  producer convention.
