# AI/BI dashboards walkthrough

> **Mode:** `browser` · **Surface:** /bi + /bi/{slug} + /bi/{slug}/edit + /bi/public/{token} + /api/bi

End-to-end exercise of the widget-dashboard surface: create a
dashboard, place a markdown tile and a SQL counter on the grid,
drag/resize, parameterise a table widget, publish a public
read-only link, verify it renders without a session, and revoke
it. The JSON surface under `/api/bi` is the one the page
factories script against; widget queries run through the same
SELECT enforcement as notebook SQL cells, so every widget must
reference a real table.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
  (seeds `demo.sales.orders` / `demo.sales.customers` used below)
- [`auth.md`](auth.md) ran first (admin@pql.test exists and is
  signed in).
- Playwright MCP Firefox (`--browser firefox`); see
  [admin-console.md](admin-console.md) for the stale-profile-lock
  recovery note.
- Network access to `esm.sh` (ECharts + gridstack load lazily from
  the importmap). Without it the pages must still render with a
  visible "Chart library unavailable" / "drag and resize are
  disabled" notice — that degradation is itself an assertable
  behaviour, but the steps below assume the CDN is reachable.

## Walkthrough

### Part A — Create + first widgets (4 steps)

1. **Land on the list page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/bi')`.
   - Assert: title `AI/BI Dashboards · PointlesSQL`, heading
     "AI/BI Dashboards" with the bar-chart icon, "New dashboard"
     button, and the empty-state row "No dashboards yet." on a
     fresh stack. The Build hub's context panel highlights the
     "AI/BI Dashboards" spoke.

2. **Create a dashboard**.
   - Action: click "New dashboard"; in the modal type title
     `E2E sales board`, description `Walkthrough dashboard`; click
     "Create dashboard".
   - Assert: the browser lands on `/bi/e2e-sales-board-<hex>/edit`
     with the "editing" badge next to the title and the
     empty-state "No widgets yet" panel.

3. **Add a markdown widget**.
   - Action: click "Add widget"; in the drawer pick kind
     `markdown`, title `Read me`, markdown body
     `## Sales\nNumbers refresh on every view.`; click
     "Save widget".
   - Assert: toast "Widget added.", page reloads, the grid shows
     one card titled "Read me" whose body renders a "Sales"
     heading (no literal `##`).

4. **Add a counter widget**.
   - Action: "Add widget" → kind `counter`, title `Order count`,
     SQL `SELECT COUNT(*) AS orders FROM demo.sales.orders`;
     "Save widget".
   - Assert: after the reload the new card renders the big number
     `50` with the column label `orders` under it.

### Part B — Layout (2 steps)

5. **Drag and resize**.
   - Action: drag the "Order count" card to the right of
     "Read me"; resize it one row taller using the south-east
     handle.
   - Assert: within ~1 s of releasing, the debounced layout
     autosave fires — `browser_network_requests()` shows a
     `PUT /api/bi/dashboards/<slug>/layout` returning 200.

6. **Save layout explicitly + verify persistence**.
   - Action: click "Save layout", then reload the page.
   - Assert: toast "Layout saved."; after the reload both cards
     re-appear in their dragged positions (the `gs-x`/`gs-y`
     attributes on the grid items match the dragged layout).

### Part C — Parameters (3 steps)

7. **Add a string parameter**.
   - Action: in the Parameters card click "Add parameter"; fill
     name `name_like`, label `Customer name`, type `string`,
     default `%Customer 1%`; click "Save parameters".
   - Assert: toast "Parameters saved."

8. **Add a parameterised table widget**.
   - Action: "Add widget" → kind `table`, title `Matching customers`,
     SQL
     `SELECT customer_id, name, email FROM demo.sales.customers WHERE name LIKE {{name_like}}`;
     "Save widget". After the reload, open the widget's pencil
     (edit) button and click "Run".
   - Assert: the drawer shows a green "N rows in M ms." line
     (11 rows for the default pattern: Customer 1 + Customer 10–19).

9. **Apply a param on the view page**.
   - Action: click "View"; on `/bi/<slug>` set the
     "Customer name" input to `%Customer 2%` and click "Apply".
   - Assert: the "Matching customers" table re-renders down to
     2 rows (Customer 2, Customer 20); the counter and markdown
     tiles still render. The params bar shows the default value
     prefilled on first load.

### Part D — Publish + public viewer (4 steps)

10. **Publish**.
    - Action: open the "Share" dropdown → "Publish public link";
      then reopen the dropdown → "Copy public link".
    - Assert: toasts "Dashboard published." then "Public link
      copied."; the dropdown button now reads "Published". Read
      the token from the clipboard or from
      `GET /api/bi/dashboards/<slug>` (`public_token`).

11. **Open the public link in a fresh context**.
    - Action: open a new incognito/fresh browser context (no
      cookies) and navigate to
      `http://127.0.0.1:8000/bi/public/<token>`.
    - Assert: the chromeless public layout renders (brand topbar,
      "Read-only" pill, no nav rail, no Edit/Share buttons); the
      markdown, counter (`50`), and table widgets all render data
      without any login redirect. `browser_network_requests()`
      shows the widget data coming from
      `POST /api/bi/public/<token>/widgets/<id>/data`.

12. **Unpublish**.
    - Action: back in the signed-in context on `/bi/<slug>`,
      "Share" dropdown → "Unpublish".
    - Assert: toast "Dashboard unpublished."; the dropdown
      reverts to "Share".

13. **Revoked token 404s**.
    - Action: reload the public URL in the fresh context.
    - Assert: the branded 404 page renders (no widget data, no
      redirect to login). Console stays free of errors for the
      whole walkthrough except the expected 404 fetch.
