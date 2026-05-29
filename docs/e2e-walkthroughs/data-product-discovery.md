# Data-Product Discovery — quantum ports, stats, glossary

> **Mode:** `hybrid` · **Surface:** product Overview panels (Discovery / Ports / Semantic / Statistics) + `/admin/glossary` CRUD + `/glossary` browse + Contract-tab term badges

A data product is a self-describing *architecture quantum*: it
publishes a machine-readable discovery contract under a stable URI,
declares its input/output ports, advertises a semantic model + light
statistics, and binds its columns to a shared business glossary. This
playbook exercises the discovery surface and the glossary term →
column badge.

## Preconditions

1. `auth.md` — logged in as admin.
2. `scripts/seed-e2e.py` + `scripts/seed-mesh-demo.py` — the
   `demo.sales` product carries declared columns (`orders.amount`
   among them) and seeded statistics rows.

   ```bash
   uv run python scripts/seed-e2e.py
   uv run python scripts/seed-mesh-demo.py
   ```

## Walkthrough

1. **Overview discovery panels.**
   - Action: `browser_navigate('http://127.0.0.1:8000/data-products/demo/sales?tab=overview')`.
   - Assert: a **Discovery** card showing the stable URI
     `urn:pointlessql:product:default:demo:sales` + a "View contract
     JSON" link; a **Ports** card (Output / Input — "No upstream
     sources declared" for this source-aligned product); a **Semantic
     model** card (Concepts + Sample query); a **Statistics** card
     listing `customers` (20 rows) and `orders` (50 rows) with Δ
     version + age; a **Consume this product** card with PQL / SQL /
     Python snippets.

2. **Glossary admin — create a term.**
   - Action: `browser_navigate('http://127.0.0.1:8000/admin/glossary')`,
     click "New term".
   - Fill Slug `net-revenue`, Term `Net Revenue`, Description
     "Revenue after returns and discounts."; click "Create term".
   - Assert: `POST /api/admin/glossary` → 200; a `net-revenue` row with
     "0" bindings.

3. **Bind the term to a column.**
   - Action: on the row click "Bindings"; fill catalog `demo`, schema
     `sales`, table `orders`, column `amount`; click the primary "Bind".
   - Assert: `POST /api/admin/glossary/{id}/bindings` → 200.

4. **Browse + detail.**
   - Action: `browser_navigate('http://127.0.0.1:8000/glossary')`.
   - Assert: a "Net Revenue" card with "1 column bindings" linking to
     `/glossary/net-revenue`.
   - Action: open `/glossary/net-revenue`.
   - Assert: "Bound columns: demo.sales.orders.amount".

5. **Contract-tab glossary badge.**
   - Action: `browser_navigate('http://127.0.0.1:8000/data-products/demo/sales?tab=contract')`.
   - Assert: the `orders` table renders its column rows; the `amount`
     column carries a `Net Revenue` glossary badge (`bi-book` icon).

## Playwright MCP notes

- Both the glossary "New term" form and the per-row "Bindings" editor
  are collapsed behind a toggle button — click the toggle before
  filling, or Playwright will time out on a hidden input.
- The Contract tab renders columns from the product's contract JSON
  (`detail.tables[].columns`), not from a live catalog scan — a product
  with an empty `columns` list shows table headers with no rows (and so
  no badge). `seed-mesh-demo.py` declares real columns so the badge
  surfaces.

## Anti-goals

- The discovery URI embeds the workspace **slug**, not a numeric id —
  it is stable across restarts but not durable across a workspace
  rename (documented limitation).
- The export port (`GET …/export?table=`) requires a real Delta table;
  it is covered by unit tests rather than this browser playbook.
