# Time-travel value-query walkthrough

> **Mode:** `browser` · **Surface:** /admin/audit/by-table row-at-version

Exercises the time-travel surface: a table-detail
"view at version N" picker plus a row-trace "at this Delta version,
what did this row look like" admin-only lookup. Builds on the
``agent_run_operations.delta_version_after`` capture from.

## Preconditions

- PointlesSQL is running on `http://127.0.0.1:8000`.
- A Delta table exists with at least three historical versions.
 The Hermes-medallion notebook from
 [`docs/e2e-walkthroughs/hermes_medallion.md`](hermes_medallion.md)
 produces enough versions if no real fixture is on hand:
 - autoload bronze (v0)
 - merge silver (v0 of silver, v1 of bronze if upstream changed)
 - aggregate gold (v0 of gold)
- The metadata DB is on `n4i5j6k7l8m9` or later —
 earlier installs need `alembic upgrade head` first.

## Walkthrough

1. **Open a table-detail page.**

 Browse to
 `http://127.0.0.1:8000/catalogs/{cat}/schemas/{sch}/tables/{tbl}`
 and confirm the Preview card now shows a "View at: current"
 dropdown alongside the row count.

2. **Switch to a historical version.**

 Open the dropdown. Each entry is shaped
 `v3 (2026-04-29) — run abc12345…`; the run-id suffix is
 present only for versions that originated from PointlesSQL
 ( attribution). Pick `v0`. The preview pane
 re-fetches via
 `/api/tables/{full_name}/preview-at-version?version=0&limit=50`
 and renders the same columns + row layout.

3. **Switch back to current.**

 Pick the top "current" option. The preview reverts to the
 live view and the row-count badge updates.

4. **Open a row trace.**

 From the same table-detail preview, click any
 `_lineage_row_id` link to land on
 `/catalogs/{cat}/schemas/{sch}/tables/{tbl}/rows/{row_id}/trace`.

5. **Use the admin-only "view this row at version" card.**

 Logged in as an admin, the row-trace page shows a new card
 labelled "View this row at a specific Delta version" with a
 numeric input. Type a historical version (e.g. `0`) and click
 "Look up". The card renders either:
 - A two-column key/value table of the row's state at that
 version (when the row was present), or
 - A muted "Row was not present at v0" notice (when the row
 was inserted after that version).

 Logged in as a non-admin, the card is not rendered at all
 (the lookup endpoint also gates on `require_admin`).

## Playwright MCP script

Condensed replay. The five prose steps map to:

1. `browser_navigate('http://127.0.0.1:8000/catalogs/main/schemas/silver/tables/orders')`
   — assert the Preview card has a `View at:` dropdown next to
   the row count.
2. `browser_click(".view-at-version-dropdown")`,
   `browser_select_option(role="combobox", value="0")`
   — preview pane re-fetches via
   `/api/tables/main.silver.orders/preview-at-version?version=0&limit=50`.
   `browser_network_requests()` should show that GET returning
   200.
3. `browser_select_option(role="combobox", value="current")`
   — preview reverts to live view.
4. `browser_click(".lineage-row-id-link:first")`
   — URL becomes
   `/catalogs/main/schemas/silver/tables/orders/rows/{row_id}/trace`.
5. **Admin-only:**
   `browser_evaluate('() => document.querySelector(".row-at-version-card") !== null')`
   → `true`;
   `browser_type(role="spinbutton", value="0")`,
   `browser_click("Look up")`
   — assert either a 2-column key/value table OR the muted
   "Row was not present at v0" notice.
6. **Non-admin gate:** repeat step 5 logged in as
   `user@pql.test` — `browser_evaluate('() => document.querySelector(".row-at-version-card")')`
   returns `null` (card is server-side-omitted, not just hidden).

## Notes

- `query_history` gains one row per `preview-at-version` /
 `row-at-version` call with `read_kind = "pql_table_at_version"`,
 so the `/queries` UI surfaces time-travel reads the same way
 the read-audit surfaces ordinary `pql.table()`
 calls.
- The "row at version" lookup masks `_lineage_row_id` mismatch
 (no row found) from a "table did not yet have an
 `_lineage_row_id` column at that version" case (returned with
 an explicit `note`).
- No write paths are added. Time-travel writes belong to the
 rollback flow that already shipped.
