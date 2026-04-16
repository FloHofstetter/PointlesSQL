# Catalog-browsing walkthrough

Click-through of the read-only browsing surface: the `/`
welcome screen, the catalog/schema/table detail pages, the
sidebar tree including its `sessionStorage` persistence, and
the PQL snippet card on the table page.

## Preconditions

- [`auth.md`](auth.md) ran first — `admin@pql.test` is the
  currently logged-in admin.
- Seed script ran successfully (`uv run python scripts/seed-e2e.py`) —
  catalog `demo` with schemas `sales`, `hr` and the four demo
  tables exists.

## Walkthrough

1. **Welcome screen** — catalog count + admin-only modal
   trigger.
   - Action: `browser_navigate(url='http://127.0.0.1:8000/')`
   - Assert: the pill "N catalogs available" shows at least 1.
   - Assert: the "Create foreign catalog" button is visible
     (admin-only — gated by `is_admin` in `pages/catalogs.html`).

2. **Sidebar tree — cold load** — the tree fetches from
   `/api/tree` on first render.
   - Action: `browser_evaluate(function='() => JSON.parse(sessionStorage.getItem("pql.tree") || "null")')`
   - Assert: returns a non-null list including an entry whose
     `name === "demo"`.

3. **Expand a catalog node** — click the chevron next to `demo`.
   - Action: click the expand icon (inside the sidebar list
     entry for `demo`).
   - Assert: `sessionStorage["pql.tree.open"]` now contains key
     `c:demo` set to `true` (verify via `browser_evaluate`).

4. **Navigate to catalog detail page**.
   - Action: click the `demo` link in the sidebar.
   - Assert: URL is `/catalogs/demo`. The page shows catalog
     metadata (name, comment, owner). The FOREIGN badge is
     **absent** (managed catalog).
   - Assert: `browser_network_requests` shows GETs to
     `/api/tags/catalog/demo`,
     `/api/permissions/catalog/demo`, and
     `/api/effective-permissions/catalog/demo`.

5. **Drill into a schema**.
   - Action: navigate to
     `http://127.0.0.1:8000/catalogs/demo/schemas/sales` (either
     click through the sidebar or enter the URL directly).
   - Assert: page heading "sales"; the two tables `orders` and
     `customers` are linked in the body.

6. **Drill into a table**.
   - Action: navigate to
     `http://127.0.0.1:8000/catalogs/demo/schemas/sales/tables/orders`.
   - Assert: the columns table lists `order_id`, `customer_id`,
     `amount`, `placed_at` with their types (bigint / double /
     timestamp) rendered.
   - Assert: the "PQL Snippet" card is visible with the snippet
     `pql.table("demo.sales.orders")` (exact quoted three-part
     name) in a `<pre>` block.

7. **Copy-to-clipboard** — snippet card.
   - Action: click the copy button inside the PQL snippet card.
   - Assert: `browser_evaluate` reading the snippet card's
     Alpine `$data.copied` returns `true` right after the click;
     returns `false` again after ~1.5 s.

8. **Sidebar persistence across reload** — the tree must
   remember `c:demo` is open.
   - Action: `browser_navigate(url='http://127.0.0.1:8000/')`
     (hard reload).
   - Assert: the `demo` node in the sidebar is already expanded
     (schemas `sales` and `hr` visible without clicking).
   - Assert: `sessionStorage["pql.tree.open"]` still contains
     the `c:demo: true` entry.

9. **Foreign-catalog detail page is reachable** — even though
   no foreign catalog exists yet in this run, confirm the
   non-foreign branch doesn't render the sync-history card.
   - Assert (already on `demo` detail): no "Sync history"
     heading is present on the page — the card renders only
     when `catalog.connection_name` is truthy.

## Playwright MCP script

```text
browser_navigate('http://127.0.0.1:8000/')
browser_snapshot()

browser_evaluate('() => JSON.parse(sessionStorage.getItem("pql.tree") || "null")')

browser_click(element='sidebar expand chevron for demo')
browser_evaluate('() => JSON.parse(sessionStorage.getItem("pql.tree.open") || "{}")["c:demo"]')

browser_click(element='sidebar link for catalog demo')
browser_network_requests()

browser_navigate('http://127.0.0.1:8000/catalogs/demo/schemas/sales')
browser_snapshot()

browser_navigate('http://127.0.0.1:8000/catalogs/demo/schemas/sales/tables/orders')
browser_snapshot()

browser_click(element='PQL snippet Copy button')
browser_evaluate('() => document.querySelector("[x-data]").__x.$data.copied')
```

## Found bugs

_No PointlesSQL bugs surfaced on this playbook. Live run
confirmed welcome screen, sidebar tree expansion,
`sessionStorage` persistence across reload, table columns
render with correct types (long/double/timestamp), the PQL
snippet matches `pql.table("demo.sales.orders")`, and the
copy-to-clipboard Alpine state flips to `copied: true` on
click._
