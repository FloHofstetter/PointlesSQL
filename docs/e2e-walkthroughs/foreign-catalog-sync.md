# Foreign-catalog sync walkthrough

Cross-feature smoke test: creates a foreign catalog via the
`/` modal pointing at the seeded `pg_e2e` Connection, runs
`Sync now`, verifies the sync-history card records the run,
and confirms the mirrored schemas/tables show up in the
sidebar tree. Non-admin users must **not** see the `Sync now`
button.

## Preconditions

- [`auth.md`](auth.md), [`catalog-browsing.md`](catalog-browsing.md),
  [`inline-editors.md`](inline-editors.md), and
  [`federation.md`](federation.md) ran first.
- Seed script ran — the `pg_e2e` Connection exists and the
  `postgres-e2e` sidecar is populated with the `shop.customers`
  / `shop.products` / `shop.orders` tables (see
  [`../../scripts/pg-seed.sql`](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/pg-seed.sql)).
- Currently logged in as `admin@pql.test`.

## Walkthrough

1. **Open the create-foreign-catalog modal on `/`**.
   - Action: navigate to `http://127.0.0.1:8000/`.
   - Action: click **Create foreign catalog**.
   - Assert: `#createForeignCatalogModal` becomes visible. The
     connection `<select>` dropdown contains an `<option>` for
     `pg_e2e (POSTGRESQL)`.

2. **Submit the modal**.
   - Action: `browser_fill_form` with `name=pg_mirror`.
   - Action: select `pg_e2e` from the connection dropdown.
   - Action: click **Create**.
   - Assert: browser navigates to `/catalogs/pg_mirror` (per
     `createForeignCatalogForm.submit()` in
     [`frontend/js/federation.js`](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/federation.js)).

3. **Foreign-catalog detail renders the foreign card + empty
   sync-history**.
   - Assert: the "FOREIGN" badge is visible next to the catalog
     heading.
   - Assert: the foreign-catalog card (`foreign_catalog_card.html`)
     shows the bound `pg_e2e` connection link.
   - Assert: the "Sync history" card is visible and says
     *"No sync runs yet."* (seeded content from
     `sync_history_card.html` when `sync_runs` is empty).
   - Assert: the **Sync now** button is visible (admin-only).

4. **Run the first sync**.
   - Action: click **Sync now**.
   - Assert: via `browser_network_requests`, a
     `POST /api/catalogs/pg_mirror/sync` returns 200 with a
     JSON body carrying `status: "succeeded"` and
     `added_count >= 3` (three tables in `shop`).
   - Assert: page reloads; the sync-history card now has one
     row with a green "succeeded" badge and `+Added` equal to
     the count returned above.

5. **Mirrored schemas and tables visible in the sidebar**.
   - Action: expand `pg_mirror` in the sidebar.
   - Assert: the `shop` schema node appears; expanding it
     reveals `customers`, `products`, `orders`.
   - Action: click into
     `/catalogs/pg_mirror/schemas/shop/tables/customers`.
   - Assert: the columns table shows `id`, `name`, `email`,
     `created_at` with types derived from
     `information_schema.columns` by
     [`pointlessql/services/pg_sync.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/pg_sync.py).

6. **Second sync is idempotent (no duplicate adds)**.
   - Action: navigate back to `/catalogs/pg_mirror` and click
     **Sync now** again.
   - Assert: the new sync-history row shows
     `added_count == 0`, `changed_count == 0`,
     `dropped_count == 0` (nothing changed in Postgres).

7. **Non-admin negative — `Sync now` absent**.
   - Action: sign out, log in as `user@pql.test` / `Passw0rd!`.
   - Action: navigate to `/catalogs/pg_mirror`.
   - Assert: either the page renders without a
     "Sync now" button (non-admin), **or** the detail page is
     forbidden with `/403` if the user lacks `USE CATALOG`
     (both are acceptable gate points — record which one the
     current build chose).

8. **Restore admin session** — log back in as
   `admin@pql.test`. Done.

## Playwright MCP script

```text
browser_navigate('http://127.0.0.1:8000/')
browser_click(element='Create foreign catalog button')
browser_fill_form(fields=[
    {name:'name', value:'pg_mirror'},
])
browser_select(element='connection dropdown', value='pg_e2e')
browser_click(element='Create button inside modal')

browser_snapshot()                           # assert FOREIGN badge + Sync now
browser_click(element='Sync now button')
browser_network_requests()                   # assert POST /api/catalogs/pg_mirror/sync 200

browser_click(element='sidebar expand chevron for pg_mirror')
browser_click(element='sidebar link for shop schema')
browser_navigate('http://127.0.0.1:8000/catalogs/pg_mirror/schemas/shop/tables/customers')

# Second sync
browser_navigate('http://127.0.0.1:8000/catalogs/pg_mirror')
browser_click(element='Sync now button')

# Non-admin negative
browser_click(element='user dropdown toggle')
browser_click(element='Sign out button')
# log in as user@pql.test and navigate to /catalogs/pg_mirror
```

## Found bugs

_No PointlesSQL bugs surfaced on this playbook. Live run
confirmed:_

- _Create-foreign-catalog modal picks up the seeded `pg_e2e`
  connection from the dropdown (connection options including
  host `postgres-e2e`, database `ecommerce` are returned to the
  modal)._
- _The first sync returns `status: "succeeded"` with
  `added_count: 4` (schema `shop` + tables `customers` /
  `orders` / `products`)._
- _Second sync is idempotent (`added=0, changed=0, dropped=0`)._
- _Mirrored columns on `pg_mirror.shop.customers` are typed
  `int`, `string`, `string`, `timestamp` (Postgres →
  Unity-Catalog type mapping from
  `pointlessql/services/pg_sync.py`)._
- _Non-admin visiting `/catalogs/pg_mirror` gets the
  `403 Access Denied` page — one of the two accepted outcomes
  in step 7 (the other being "Sync now button absent")._
