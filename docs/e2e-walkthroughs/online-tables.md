# Online tables walkthrough

> **Mode:** `browser` · **Surface:** /online-tables + /api/online-tables

End-to-end exercise of the synced-tables surface: create an online
table over a seeded Delta table, run a full sync into a SQLite
serving target, point-read it through the lookup tester, verify the
status/error lifecycle on a broken target, and clean up. The JSON
surface under `/api/online-tables` is the same one schedulers and
scripts drive; the page is thin chrome over it.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in).
- A seeded Delta table exists (the seed script's
  `shop.gold.orders`-style fixture; any 3-part table with a
  storage location works — note its name and an integer-ish
  primary-key column below).
- Playwright MCP Firefox (`--browser firefox`); see
  [admin-console.md](admin-console.md) for the stale-profile-lock
  recovery note.

## Walkthrough

### Part A — Create (3 steps)

1. **Land on the page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/online-tables')`.
   - Assert: title `Online Tables · PointlesSQL`, heading "Online
     Tables" with the `bi-database-fill-gear` icon, breadcrumb
     Home → Online Tables, the empty state "No online tables yet.",
     and the intro paragraph shows the literal
     `{{secrets/<scope>/<key>}}` reference syntax.

2. **Create an online table**.
   - Action: click "New online table"; fill name `e2e-orders`,
     source table `shop.gold.orders` (or the seeded table you
     picked), target URL `sqlite:////tmp/e2e-online.db`, target
     table `orders_online`, primary keys `order_id`, mode `full`;
     click "Create online table".
   - Assert: the create card closes; the list shows `e2e-orders`
     with mode badge `full`, status badge `idle`, rows synced `0`,
     version `—`.

3. **Reject a malformed create**.
   - Action: open the create card again, fill name `has space` and
     the same other fields, click "Create online table".
   - Assert: the card's red alert shows the `1-128 chars from
     [A-Za-z0-9_-]` validation message; close the card — the list
     still shows exactly one row.

### Part B — Sync + lookup (4 steps)

4. **Run a sync**.
   - Action: click "Sync now" on the `e2e-orders` row.
   - Assert: the button shows "Syncing…" then the row refreshes
     with status badge `ok` (green), rows synced equal to the
     source table's row count, and a numeric version.

5. **Verify the audit trail**.
   - Action: open `/admin/audit`.
   - Assert: the newest rows include `synced_table.created` and
     `synced_table.synced` on target `synced_table:e2e-orders`,
     the latter's detail carrying the row count.

6. **Point-read through the lookup tester**.
   - Action: back on `/online-tables`, click "Lookup" on the row;
     the panel's key-column select offers exactly the configured
     primary keys (`order_id`); type an existing key value, click
     "Look up".
   - Assert: the result table shows the matching row(s) with all
     target columns; the row-count line matches.

7. **Verify the lookup is PK-only** (load-bearing — the
   predictable-index invariant).
   - Action:
     ```js
     async () => {
       const r = await fetch(
         '/api/online-tables/e2e-orders/lookup?key_column=status&key=x',
         {headers: {'Accept': 'application/json'}});
       return r.status + ' ' + await r.text();
     }
     ```
   - Assert: status `422` and the body names the allowed primary
     keys; no result rows.

### Part C — Failure path + cleanup (3 steps)

8. **Surface a sync failure**.
   - Action: create a second online table `e2e-broken` with the
     same source but target URL
     `sqlite:////nonexistent-dir/broken.db`; click "Sync now".
   - Assert: the page's red alert shows the engine error, the row's
     status badge turns `failed` (red), and hovering the badge
     shows the error text (tooltip = `last_error`).

9. **Delete the broken table**.
   - Action: click "Delete" on `e2e-broken`, accept the confirm
     dialog.
   - Assert: the row disappears; `/admin/audit` gains
     `synced_table.deleted`.

10. **Clean up**.
    - Action: delete `e2e-orders` the same way.
    - Assert: the empty state returns. Console stays free of
      errors for the whole walkthrough.
