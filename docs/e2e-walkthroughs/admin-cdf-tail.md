# Admin CDF subscriptions walkthrough

> **Mode:** `browser` · **Phase:** 40.6 · **Surface:** /admin/cdf-tail + table CDF tab

End-to-end exercise of the Phase 40.6 foreign-Delta CDF tail UI:
admin landing card → `/admin/cdf-subscriptions` registry CRUD →
`Run tail now` trigger → table-detail "CDF events" tab. Mirror
of the push-modell `/admin/external-writes` flow, but for the
pull-modell capture path: PointlesSQL periodically reads
`DeltaTable.load_cdf()` for opted-in foreign Delta tables and
persists every CDF row into `cdf_tail_events`.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml up -d
  docker compose -f docker-compose.yml -f docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in).
- Playwright MCP Firefox: per the lock-file hygiene note in
  [`admin-console.md`](admin-console.md), `rm` any stale
  `~/.cache/ms-playwright/mcp-firefox-*/lock` symlink if launch
  fails immediately after `<launched>`.

## Walkthrough

### Part A — Land on CDF subscriptions admin (3 steps)

1. **Open the admin landing**.
   - Action: `browser_navigate('http://127.0.0.1:8000/admin')`.
   - Assert: 8 cards in the grid (per
     [`admin-console.md`](admin-console.md) Part A step 2).
     The CDF subscriptions card has `data-admin-card="cdf-subscriptions"`
     and `href="/admin/cdf-subscriptions"`.

2. **Click the CDF subscriptions card**.
   - Action: click the card with
     `data-admin-card="cdf-subscriptions"`.
   - Assert: lands on `/admin/cdf-subscriptions`. Heading reads
     "CDF subscriptions". Empty registry shows
     "No subscriptions registered." in the empty-state card.

3. **Verify the explainer alert** is present and quotes
   `POINTLESSQL_CDF_TAIL_INTERVAL_SECONDS` as the loop opt-in.

### Part B — Register one subscription (3 steps)

1. **Fill the "Register new subscription" form**.
   - Action: type `demo.silver.orders` into the
     `Table full name` field.
   - Action: type `id` into the `Row-id column` field.
   - Action: leave producer label empty (defaults to
     `cdf-tail:demo.silver.orders`).

2. **Submit**.
   - Action: click the `+` submit button.
   - Assert: page reloads. The list-table now contains one row
     with `demo.silver.orders` in the Table column, `id` in the
     Row-id col column, `active` pill, `—` in the Last v column
     (no tail tick has run yet).

3. **Confirm the duplicate guard**.
   - Action: re-submit the same form (same table, same row-id).
   - Assert: an alert pops up "Create failed: …already exists" —
     the `(workspace_id, table_full_name)` UNIQUE constraint
     fires server-side and the JSON error envelope flows back to
     the page.

### Part C — Drive a tail tick (3 steps)

1. **Click "Run tail now"**.
   - Action: click the warning-styled "Run tail now" button.
   - Assert: page reloads after the tick. If a real Delta table
     exists at `demo.silver.orders` with CDF turned on, the
     `Last v` column shows the highest CDF version processed and
     `Last tailed` becomes a fresh ISO timestamp. Otherwise (no
     storage backing the table), `Last error` populates with the
     "uc.get_table failed" or "DeltaTable load failed" string and
     the row's `last_error` cell shows the truncated message — the
     loop is fail-safe per subscription.

2. **Toggle the subscription off**.
   - Action: click the "Pause" button on the row.
   - Assert: row class becomes muted; pill flips from `active` to
     `paused`. Re-running "Run tail now" no longer advances the
     pointer for this subscription.

3. **Resume + delete**.
   - Action: click "Resume" then click the trash icon and confirm
     the dialog.
   - Assert: row disappears. All `cdf_tail_events` rows tied to
     the subscription cascade-delete server-side
     (`ON DELETE CASCADE`).

### Part D — Table-detail "CDF events" tab (3 steps)

This part is **conditional on a real Delta table backing the
subscription**. Skip if Part C step 1 stamped an error; the tab
still appears but with no events.

1. **Re-register a subscription that has Delta-CDF behind it**.
   - Action: register one against a UC table whose
     `storage_location` resolves to a CDF-enabled Delta. The
     PQL pipeline-author walkthrough's `silver.orders` is a
     good fit when seeded via `pql.merge(track_value_changes=True)`.
   - Action: click "Run tail now". Wait for the page reload.

2. **Navigate to the table-detail page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/catalogs/<cat>/schemas/<sch>/tables/<tbl>')`
     for the table you just subscribed to.
   - Assert: the tab strip now contains a 7th tab "CDF events"
     with `data-bs-target="#tab-cdf-events"`. (Tables without a
     subscription still only show 6 tabs; the new tab is gated
     on `{% if cdf_subscription %}` server-side.)

3. **Click the CDF events tab**.
   - Action: click the "CDF events" nav button.
   - Assert: the pane mounts. The "Subscription" card surfaces
     the producer label, row-id column, last version, and last
     tailed timestamp. If events were captured, the "Recent
     events" card lists them: one row per event with the
     change-type pill (insert/update_preimage/update_postimage/
     delete colour-coded).

### Part E — Plugin tools (1 step)

1. **Read CDF subscriptions via the auditor-scope plugin tool**.
   - Action: from a Hermes session with the auditor scope wired
     in, run `pql_list_cdf_subscriptions(only_active=true)`.
   - Assert: returns a JSON envelope with `ok: true` and
     `result.subscriptions` listing the same rows visible in
     the admin page.
   - Action: run
     `pql_recent_cdf_events_for_table(table="demo.silver.orders", limit=10)`.
   - Assert: returns the subscription block + up to 10 newest
     events, matching the table-detail pane.

## Playwright MCP script

Browser replay for the admin page + table-detail CDF events tab:

1. `browser_navigate('http://127.0.0.1:8000/admin/cdf-tail')`
   — assert page renders the subscriptions table.
2. `browser_click("Add subscription")`
   — `browser_wait_for(".modal.show")`.
3. `browser_fill_form([{name:"target_table", value:"pg_mirror.public.events"}, {name:"poll_interval_seconds", value:"60"}])`,
   `browser_click("Save")` — assert new row appears.
4. `browser_navigate('http://127.0.0.1:8000/catalogs/pg_mirror/schemas/public/tables/events')`
   — assert the table-detail page exposes a `CDF events` tab.
5. `browser_click("CDF events")`
   — `browser_wait_for(".cdf-event-row")` — assert ≥ 1 row.
6. `browser_evaluate('() => document.querySelectorAll(".cdf-event-row [data-op]")[0].dataset.op')`
   — assert one of `insert`, `update_preimage`,
   `update_postimage`, `delete`.
7. `browser_navigate('http://127.0.0.1:8000/admin/cdf-tail')`,
   `browser_click("Pause")` (on the row from step 3) — assert
   status pill flips to `paused`.
8. `browser_click("Resume")` — assert status flips back to
   `active`.

## Out-of-scope (deliberate)

- Cloud-storage credential surface (S3 / GCS / Azure SAS) —
  unreachable storage stamps `last_error` and the subscription
  is skipped on the next tick. Re-tail of the same range is
  idempotent thanks to the
  `(table_full_name, delta_version, row_id, change_type)`
  UNIQUE.
- Auto-discovery of CDF-enabled tables under the install — opt-in
  per subscription only.
- Row-trace fold-in of CDF events as virtual walkback steps —
  deferred to a future Phase 40.7 sprint; CDF events are already
  joinable to `lineage_row_edges` via row_id when needed.

## See also

- [`admin-console.md`](admin-console.md) — landing-card grid and
  the seven other admin pages.
- [`audit-cockpit-deep.md`](audit-cockpit-deep.md) — auditor
  scope and the cross-cockpit read tools.
