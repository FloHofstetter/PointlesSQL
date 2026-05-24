# Catalog-browsing walkthrough

> **Mode:** `browser` · **Surface:** /catalogs/* + sidebar tree

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

1. **Home dashboard landing** — catalog counter + admin-only modal
 trigger in Quick actions.
 - Action: `browser_navigate(url='http://127.0.0.1:8000/')`
 - Assert: the Quick actions "Catalogs" counter shows at least 1.
 - Assert: the "Create foreign catalog" button is visible
 (admin-only — gated by `is_admin` in `pages/home.html`).

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

## inline schemas, inline tables, preview, columns, lineage, open-in-notebook

Adds a second pass on top of the existing flow above. Same
seed + auth preconditions apply.

1. **Inline Schemas card on catalog detail**.
 - Action: `browser_navigate('http://127.0.0.1:8000/catalogs/demo')`.
 - Assert: a card titled "Schemas" sits below Metadata. It lists
 `hr` and `sales` as monospace links to
 `/catalogs/demo/schemas/hr` and `/catalogs/demo/schemas/sales`.
 Each row carries a non-empty Updated cell
 (falls back to `—` only if the seed set no `updated_at`).

2. **Inline Tables card on schema detail**.
 - Action: navigate to `/catalogs/demo/schemas/sales`.
 - Assert: a card titled "Tables" lists `customers` and `orders`
 with type + format badges (`MANAGED` / `DELTA`) and a non-zero
 Columns count matching the actual column list (4 for `orders`).

3. **Preview card — happy path**.
 - Action: navigate to
 `/catalogs/demo/schemas/sales/tables/orders`.
 - Assert: a "Preview" card renders below the PQL snippet card;
 once loading finishes, the table shows ≤ 10 rows with the
 column headers `order_id`, `customer_id`, `amount`, `placed_at`.
 - Assert (`browser_network_requests`): the
 `/api/catalogs/demo/schemas/sales/tables/orders/preview`
 response carries a `Cache-Control: no-store` header.

4. **Preview card — server-side cap is not tunable**.
 - Action (`browser_evaluate`): `fetch('/api/catalogs/demo/schemas/sales/tables/orders/preview?limit=1000').then(r => r.json()).then(d => d.rows.length)`.
 - Assert: returns ≤ 10 — the query string is ignored server-side.

5. **Preview card — degrades on broken table**.
 - Prep: in a shell, temporarily move the Delta dir for one demo
 table (`mv warehouse/.../orders/_delta_log warehouse/.../orders/_delta_log.bak`).
 - Action: reload `.../tables/orders`.
 - Assert: the Preview card shows a
 `Preview unavailable: …` inline message instead of a
 page-level 500; the rest of the page (metadata, PQL snippet,
 columns, lineage) still renders.
 - Cleanup: restore the `_delta_log.bak` rename.

6. **Columns search + sort (≥ 20 columns)**.
 - Prep: seed a wide table, e.g. via
 ```python
 from pointlessql import PQL
 import pandas as pd
 pql = PQL()
 pql.write_table(
 pd.DataFrame([[0]*25], columns=[f"c{i}" for i in range(25)]),
 "demo.sales.wide25",
 )
 ```
 - Action: navigate to `.../tables/wide25`.
 - Assert: a search input appears in the Columns card header
 (only when `columns|length >= 20`). Typing `c1` filters the
 list via `listTable()`'s debounced handler.
 - Assert: clicking the `Name` header cycles
 `aria-sort` asc → desc → none.
 - Negative: reload `.../tables/orders` (4 columns) — no search
 input is present (progressive enhancement stays off below the
 threshold).

7. **Lineage — per-depth subheadings**.
 - Prep: if the seed does not already produce lineage, run a
 Python cell that reads `orders` and writes a derived table,
 or add synthetic edges via the soyuz-catalog lineage API.
 - Assert: the Lineage card renders `Depth 1`, `Depth 2`, …
 subheadings; each three-part `full_name` is still a clickable
 link to the target table detail page; the per-node depth
 badge remains.

8. **Open in notebook — admin happy path**.
 - Assert: on `.../tables/orders` as `admin@pql.test` the
 PQL-snippet card header shows an **Open in notebook**
 button next to Copy.
 - Action: click Open in notebook.
 - Assert: the browser navigates to
 `http://<host>:8888/lab/tree/scratch/demo_sales_orders_<hex>.ipynb`.
 The notebook opens inside JupyterLab with a markdown header
 `# Scratch: demo.sales.orders` and a single code cell
 pre-filled with `pql.table("demo.sales.orders")`.
 - Side-assert (server): `notebooks/scratch/` now contains the
 generated file; `/notebooks/workspace` does **not** list
 `scratch/` at the top level (skip-list gate).

9. **Open in notebook — non-admin 403**.
 - Prep: log out and log back in as the non-admin seed user
 (`viewer@pql.test`, per `auth.md`).
 - Assert: the Open in notebook button is **not rendered** on
 `.../tables/orders`.
 - Negative via direct request:
 `fetch('/api/catalogs/demo/schemas/sales/tables/orders/open-in-notebook', {method: 'POST'})`
 returns HTTP 403 with the standard
 `{"error": {"code": "authorization_error",...}}` envelope.

## Playwright MCP script — additions

```text
browser_navigate('http://127.0.0.1:8000/catalogs/demo')
browser_snapshot()

browser_navigate('http://127.0.0.1:8000/catalogs/demo/schemas/sales')
browser_snapshot()

browser_navigate('http://127.0.0.1:8000/catalogs/demo/schemas/sales/tables/orders')
browser_wait_for(text='Preview')
browser_network_requests()

browser_evaluate('() => fetch("/api/catalogs/demo/schemas/sales/tables/orders/preview?limit=1000").then(r => r.json()).then(d => d.rows.length)')

browser_click(element='Open in notebook button inside PQL Snippet card header')
# Browser navigates to http://<host>:8888/lab/tree/scratch/...
```

## Found bugs

_No PointlesSQL bugs surfaced on this playbook replay
(commit f970fce, replayed 2026-04-17 via Playwright MCP against
the `docker/docker-compose.e2e.yml` stack). Verified end-to-end:_

- _Catalog detail `/catalogs/demo` inline Schemas card listed
 `sales` and `hr` with live `updated_at` timestamps and working
 links into schema detail._
- _Schema detail `/catalogs/demo/schemas/sales` inline Tables
 card listed `customers` (3 cols) and `orders` (4 cols) with
 `MANAGED` + `DELTA` badges._
- _Table detail `/.../orders` Preview card fetched 10 rows;
 response headers carried `Cache-Control: no-store`;
 `?limit=1000` passthrough returned 10 rows (server-side cap
 holds); `truncated: true` flag set correctly._
- _Columns search threshold gate works both ways: `orders`
 (4 cols) renders the columns table without a search input;
 a seeded `demo.sales.wide25` (25 cols) renders the search
 input plus `data-sort-key` on position/name/type/nullable,
 and typing `c1` via the Alpine `listTable()` component
 filtered to `c10`..`c19` exactly._
- _Lineage card renders `UPSTREAM` / `DOWNSTREAM` headings and
 per-depth subheadings (`Depth 0` visible on the seeded
 single-node lineage graph); node links remain clickable._
- _Open-in-notebook admin happy path: `POST /api/…/open-in-notebook`
 returned `{"path": "scratch/demo_sales_orders_<hex>.ipynb",
 "lab_url": "http://127.0.0.1:8888/lab/tree/scratch/…"}`; the
 file landed under `/app/notebooks/scratch/` with a markdown
 header cell + a `pql.table("demo.sales.orders")` code cell._
- _Non-admin negative: logging in as `user@pql.test` redirects
 `/catalogs/demo/schemas/sales/tables/orders` to a 403 page
 (no `SELECT`); the direct POST to
 `/api/…/open-in-notebook` returns HTTP 403 with the standard
 `{"error": {"code": "authorization_error", "request_id": …}}`
 envelope; the preview endpoint also returns 403. No route-
 existence leaks to non-admins._

## Found bugs

_No PointlesSQL bugs surfaced on this playbook. Live run
confirmed welcome screen, sidebar tree expansion,
`sessionStorage` persistence across reload, table columns
render with correct types (long/double/timestamp), the PQL
snippet matches `pql.table("demo.sales.orders")`, and the
copy-to-clipboard Alpine state flips to `copied: true` on
click._
