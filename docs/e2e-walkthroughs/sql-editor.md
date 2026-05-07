# SQL editor walkthrough

> **Mode:** `browser` · **Phase:** 12 · **Surface:** /sql + saved queries

Exercises the Sprints 49-53 ad-hoc SQL surface: CodeMirror editor
at `/sql`, per-referenced-table `SELECT` enforcement, query
history at `/queries`, saved queries drawer, CSV/Parquet export,
cancel + timeout, EXPLAIN ANALYZE toggle, and catalog-tree
autocomplete. Walks through the golden path as admin, then
repeats the negative case as a non-admin without `SELECT` on the
target table.

## Preconditions

- [`auth.md`](auth.md) and [`catalog-browsing.md`](catalog-browsing.md)
 ran first. `admin@pql.test` is logged in.
- `user@pql.test` exists as a non-admin principal.
- Seed script ran. A Delta table at
 `main.sales.orders` has at least five rows, and `user@pql.test`
 has **no** `SELECT` grant on it yet (the negative-path step
 depends on that).

## Walkthrough

1. **SQL tab appears in the navbar.**
 - Action: from any page, hover the top navbar.
 - Assert: a new "SQL" dropdown sits between the "Notebook"
 and "Jobs" entries (admin-neutral — every logged-in user
 sees it). The dropdown lists "Editor" → `/sql` and
 "History" → `/queries`.

2. **Open the editor from anywhere with `g s`.**
 - Action: press `g` then `s` within one second while focus is
 outside an input.
 - Assert: the browser navigates to `http://127.0.0.1:8000/sql`.
 The command-palette shortcut registry lists "Go to SQL
 editor" at `g s`.

3. **Default query runs and renders rows.**
 - Action: the editor boots with `SELECT 1 AS n`. Press
 `Cmd/Ctrl+Enter`.
 - Assert: the result card shows one row (`n=1`) with a
 duration under 100 ms. No tables render in the "Tables:"
 footer because the query referenced none.

4. **Run a SELECT against a real Delta table.**
 - Action: replace the editor contents with
 `SELECT id, name FROM main.sales.orders ORDER BY id` and
 press `Cmd/Ctrl+Enter`.
 - Assert: the result table renders five rows. The "Tables:"
 footer shows a single `code` tag reading
 `main.sales.orders`. The elapsed-timer returns to zero
 after the response arrives.

5. **Autocomplete suggests fully-qualified table names.**
 - Action: place the cursor after `FROM ` on a fresh line,
 start typing `main.` — the completion popup should appear.
 - Assert: at least one completion reads
 `main.sales.orders`. Accepting it replaces the partial
 token with the full 3-part identifier. The completion
 source reads `/api/tree` once on mount, so the drawer
 reflects your current catalog permissions.

6. **Save the query.**
 - Action: press `Cmd/Ctrl+S`. Fill the modal title
 `Daily orders`, leave the description blank, tick "Share
 with other users", click **Save**.
 - Assert: a success toast reads `Saved as "Daily orders"`.
 The drawer refreshes and shows one row with the shared
 badge. The network panel shows a `POST /api/saved-queries`
 with a 200 JSON body carrying a slug like
 `daily-orders-XXXXXX` and `is_shared: true`.

7. **Load a saved query from the drawer.**
 - Action: clear the editor, then click the saved-query title
 in the drawer.
 - Assert: the editor content is replaced by the saved SQL
 verbatim. An info toast reads `Loaded "Daily orders"`.

8. **Query history records the execution.**
 - Action: navigate to `/queries` (or press `g q`).
 - Assert: the most recent row at the top of the table has
 `status=succeeded`, `duration_ms` > 0, a `row_count`
 matching step 4, a `main.sales.orders` badge in the Tables
 column, and the snippet column shows the truncated SQL.

9. **Re-run from history.**
 - Action: click the re-run arrow on that row.
 - Assert: the browser lands on `/sql` with the SQL
 pre-filled. The URL is clean (`?prefill=` gone — the
 editor called `history.replaceState`). Press Cmd+Enter
 to execute. History now has two `succeeded` rows for the
 same SQL.

10. **CSV export from the history page.**
 - Action: click the re-run arrow to land on `/sql`, note
 the `history_id` from the latest entry (via the `/queries`
 row DOM), and curl:
 ```bash
 curl -b "pql_session=<token>" \
 "http://127.0.0.1:8000/api/sql/execute/<history_id>/download?format=csv"
 ```
 - Assert: response body starts with `id,name\n` and has
 5 data rows. `Content-Disposition` header carries
 `attachment; filename="query-<id>-<timestamp>.csv"`.

11. **Parquet export round-trips via pyarrow.**
 - Action:
 ```bash
 curl -b "pql_session=<token>" \
 -o /tmp/query.parquet \
 "http://127.0.0.1:8000/api/sql/execute/<history_id>/download?format=parquet"
 python -c 'import pyarrow.parquet as pq; print(pq.read_table("/tmp/query.parquet").to_pydict())'
 ```
 - Assert: the Python one-liner prints the same five rows as
 step 4. `Content-Type` is
 `application/octet-stream` and the filename extension is
 `.parquet`.

12. **EXPLAIN toggle.**
 - Action: back on `/sql`, click the **Explain** button next
 to Run (same SQL as step 4).
 - Assert: the result card now shows a "Query plan" monospace
 panel instead of the row table. The text contains
 plan-stage names — at least one of
 `PROJECTION`, `SCAN`, or `HASH_JOIN` depending on the
 seed. Crucially: `/queries` gains **no** new row — EXPLAIN
 runs are diagnostic, not recorded.

13. **Cancel a long-running query (smoke).**
 - Action: swap the editor to something that will take ≥ 2 s
 (e.g. `SELECT count(*) FROM main.sales.orders, main.sales.orders b, main.sales.orders c`
 if the seed is tiny a generate_series works:
 `SELECT count(*) FROM generate_series(1, 100000000)` — adjust
 upwards until the running spinner appears).
 - Action: while the "Running… Ns" badge ticks, click the
 orange **Cancel** button.
 - Assert: an info toast reads `Cancel requested.` The
 execute response eventually fails with
 `Query cancelled by user.` rendered inline. `/queries`
 gains a row with `status=cancelled`. If DuckDB's
 interrupt doesn't abort fast enough, the 60 s timeout
 kicks in — same cancelled status.

14. **Non-admin cannot run SELECT on a table they lack the grant for.**
 - Action: sign out, sign in as `user@pql.test`.
 - Action: visit `/sql`, paste
 `SELECT * FROM main.sales.orders LIMIT 5`, press
 Cmd+Enter.
 - Assert: the response is a 403 `application/problem+json`
 with `code: authorization_error`,
 `required_privilege: SELECT`,
 `full_name: main.sales.orders`. The editor shows the
 "Permission denied" card with the detail verbatim.
 `/queries` for this user has a `failed` row with
 `error_message` mentioning the missing grant.

15. **Non-admin cannot see admin's private saved query.**
 - Pre-arrange: as admin, save a private query (step 6 but
 uncheck the "Share" box). Note its slug.
 - Action: as `user@pql.test`, navigate to
 `http://127.0.0.1:8000/api/saved-queries/<slug>`.
 - Assert: 404 `catalog_not_found`. The drawer on `/sql` does
 not list the private query either.

16. **Mobile stacking.**
 - Action: set the viewport to 375 × 667 px.
 - Assert: editor + saved-queries drawer stack vertically.
 Results table remains horizontally scrollable; nothing
 overflows the viewport. The "Run", "Explain", "Save"
 buttons wrap onto a second row if needed.

## Playwright MCP script

```text
# Auth preamble (reuse auth.md helpers).

# 2. `g s` jumps to the editor.
browser_navigate('http://127.0.0.1:8000/')
browser_press_key('g'); browser_press_key('s')

# 3. Default query runs.
browser_press_key('Control+Enter')
browser_wait_for({ text: 'Ran in' })

# 4. Real table.
browser_evaluate(() => {
 const root = document.getElementById('pql-sql-editor-root');
 const view = root && root.cmView;
 view && view.dispatch({ changes: {
 from: 0, to: view.state.doc.length,
 insert: 'SELECT id, name FROM main.sales.orders ORDER BY id',
 }});
})
browser_press_key('Control+Enter')
browser_wait_for({ text: 'main.sales.orders' })

# 6. Save.
browser_press_key('Control+s')
browser_fill_form({
 '#save-title': 'Daily orders',
 '#save-is-shared': 'check',
})
browser_click({ text: 'Save' })
browser_wait_for({ text: 'Saved as' })

# 8. History page.
browser_navigate('http://127.0.0.1:8000/queries')

# 12. EXPLAIN.
browser_navigate('http://127.0.0.1:8000/sql')
browser_click({ text: 'Explain' })
browser_wait_for({ text: 'Query plan' })

# 14. Negative path (after re-login as user@pql.test).
browser_evaluate(() => {
 const root = document.getElementById('pql-sql-editor-root');
 const view = root && root.cmView;
 view.dispatch({ changes: {
 from: 0, to: view.state.doc.length,
 insert: 'SELECT * FROM main.sales.orders LIMIT 5',
 }});
})
browser_press_key('Control+Enter')
browser_wait_for({ text: 'Permission denied' })
```

## Known-limit notes

- **Multi-worker cancel** is out of scope. The live-
 queries registry lives on `app.state`; a second uvicorn
 worker cannot reach the other worker's DuckDB connections.
- **EXPLAIN ANALYZE never records to `query_history`** by design —
 the surface is diagnostic. If you need EXPLAIN traces for
 audit they need to be emitted separately.
- **Autocomplete is catalog-name-only** (no column awareness) —
 's ontology layer would add the column dimension.
- **Row cap is enforced server-side** at
 `POINTLESSQL_SQL_MAX_ROWS` (default 10 000). A download
 larger than that silently truncates; the UI surfaces the
 `truncated` badge on successful runs but the CSV/Parquet
 download does **not** signal truncation in the file — the
 operator is expected to widen the cap if they need the full
 set.
