# Audit cockpit deepening walkthrough

> **Mode:** `browser` · **Phase:** 18.6+ · **Surface:** /audit/inbox + /audit/search + /audit/by-table + /audit/queries

End-to-end exercise of the Phase 18.6 → 18.x audit cockpit
surfaces that grew on top of the Sprint 19 daily Audit-Reviewer
loop:

- [`audit_inbox.html`](../../frontend/templates/pages/audit_inbox.html)
  — Sprint 18.6 anomaly inbox (cross-run cross-metric σ-breach
  feed)
- [`audit_search.html`](../../frontend/templates/pages/audit_search.html)
  — Sprint 18.7 FTS over runs / ops / queries / tool_calls /
  audit_log
- [`audit_by_table.html`](../../frontend/templates/pages/audit_by_table.html)
  — Sprint 18.8 reverse index (which runs touched / wrote /
  read a given table)
- [`audit_queries.html`](../../frontend/templates/pages/audit_queries.html)
  — Sprint 18.x admin SQL workbench against the audit tables
  (5 seeded starter queries + custom CRUD)

This is the "auditor's morning" companion to
[`audit-reviewer-daily.md`](audit-reviewer-daily.md): that one
drives the LLM-mediated review loop via API + cron;
this one drives the human cockpit via the browser.

## Preconditions

- Stack up via `docker compose -f docker/docker-compose.yml -f
  docker/docker-compose.e2e.yml up -d`.
- Seed: `seed-e2e.py` is enough for the **chrome** of every
  page. To exercise the **data** paths (anomaly rows, FTS hits,
  reverse-index rows), use
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-full-stack-demo.py \
    --fresh --demo-rollback --keep-state
  ```
  which seeds rejects, errored ops, external writes, and ~150
  agent runs across all five FTS axes.
- [`auth.md`](auth.md) ran first — admin session cookie present.
- Playwright MCP Firefox lock-file gotcha: see CLAUDE.md
  line 227-235 — `rm` the stale lock symlink if Firefox launch
  fails immediately after `<launched>`.

## Walkthrough

### Part A — Anomaly inbox (5 steps)

1. **Land on the inbox**.
   - Action: `browser_navigate('http://127.0.0.1:8000/audit/inbox')`.
   - Assert: title `Audit cockpit · anomaly inbox`. Page header
     reads "Audit cockpit · anomaly inbox". Filter bar has 5
     dropdowns (Severity, Metric, Bin, Since, Table FQN) plus
     a "Refresh" button and an "include acked" toggle.

2. **Empty-state placeholder** (clean stack).
   - Assert: counter line reads
     `0 of 0 breach(es) — metrics rejects, errored_ops, 7d
     baseline at 2σ`. The list shows "No active anomalies for
     the chosen filters." This text is load-bearing — Sprint
     18.6's anomaly engine returns an empty list, not 404, when
     no metric breaches σ.

3. **Cycle severity filter**.
   - Action: pick `critical only` from the Severity dropdown.
   - Assert: page re-renders (htmx swap on `inbox-list-target`).
     Empty-state placeholder still shows; counter updates to
     reflect the narrower filter window.

4. **Verify ack/snooze affordance** (when data is present).
   - With `--demo-rollback` seed: each anomaly row has an Ack
     button and a Snooze dropdown (1h / 6h / 24h / 7d).
   - Action: click Ack on any row.
   - Assert (network): `POST /api/audit/anomaly/{id}/ack`
     returns 200; row hides immediately. Toggle "include acked"
     to confirm it reappears, marked acked.

5. **Cross-link from home banner**.
   - Action: navigate to `/`.
   - Assert: when the inbox has at least one breach, the
     home page renders an anomaly chip in the latest-runs
     banner; clicking it lands on `/audit/inbox` with the
     matching severity pre-selected.

### Part B — Audit search (4 steps)

1. **Land on the FTS page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/audit/search')`.
   - Assert: title `Audit cockpit · search`. Filter bar has a
     search box, axis dropdown (`all` / `runs` / `ops` /
     `queries` / `tool_calls` / `audit_log`), Since picker, and
     a Search button. Empty list placeholder reads "Enter a
     query above to search."

2. **Verify FTS availability** (not a precondition the page
   asserts visually — a clean SQLite stack always has FTS5):
   - Action:
     ```js
     async () => (await (await fetch('/api/audit/search?q=test',
       {credentials:'same-origin'})).json()).available
     ```
   - Assert: `true`. SQLite ships with FTS5; if this returns
     `false`, Phase 18.7's `audit_fts.py` rebuild migration
     (`y5u7v9w1x3z5_audit_search_fts`) didn't run.

3. **Submit a query** (data path; needs the full-stack seed).
   - Action: type `customer` into the search box, leave axis =
     `all`, click Search.
   - Assert: result table shows rows projected from each
     matched axis with columns Axis / Run / Entity / Snippet /
     Rank. Snippets carry `<mark>` highlights around the
     matched term.

4. **Tokenizer separator behaviour**.
   - The page header says: "Tokenizer keeps . / _ / - as
     separators, so `main.silver.orders` matches a query for
     `silver`."
   - Action: search for `silver` against the full-stack seed.
   - Assert: hits include `main.silver.orders` (and any other
     three-part FQN containing `silver`). This is Sprint 18.7's
     custom-tokenizer load-bearing assertion — the default FTS5
     tokenizer would only match `silver` against the literal
     bareword, not as a path segment.

### Part C — By-table reverse index (4 steps)

1. **Empty path renders the FQN picker (BUG-37-05 fix)**.
   - Action: `browser_navigate('http://127.0.0.1:8000/audit/by-table')`.
   - Assert: heading reads "Runs by table" (no trailing FQN);
     the page exposes an `<input id="bytable-fqn">` plus an
     "Open" button instead of the touched/written/read tab
     chrome.  No 422 errors fire (`kinds=[]` server-side).
   - Action: enter `main.silver.orders`, click Open.
   - Assert: navigation to `/audit/by-table/main.silver.orders`
     and the chrome populates.

2. **Land on the by-table page with an FQN**.
   - Action: navigate to
     `/audit/by-table/main.silver.orders` (or any FQN seeded by
     `seed-full-stack-demo.py`).
   - Assert: title flips to `Audit · runs by main.silver.orders`.
     Heading reads "Runs that touched main.silver.orders". Three
     tabs (Touched / Written / Read) load asynchronously.

3. **Touched tab — empty stack**.
   - Action: stay on the default Touched tab.
   - Assert: counter line reads `0 run(s) touched
     main.silver.orders` (clean seed-e2e seed has no agent runs)
     OR a list of run rows with ID, Principal, Status, Anomaly,
     Started columns (full-stack seed). Both states are
     legitimate.

4. **Switch tabs** (idempotent loader).
   - Action: click "Written", then "Read".
   - Assert: each tab loads its own data once; subsequent
     re-clicks do not re-fetch (the page's `loaded` Set guards
     against duplicate API calls).

### Part D — Saved audit queries (5 steps)

1. **Land on the queries workbench**.
   - Action: `browser_navigate('http://127.0.0.1:8000/audit/queries')`.
   - Assert: title `Audit cockpit · saved queries`. Header card
     describes the workbench mandate: every run logged in
     `query_history`, every export writes an `audit_log` row.

2. **Verify 5 seeded starter queries are present**.
   - Action:
     ```js
     async () => (await (await fetch('/api/saved-audit-queries',
       {credentials:'same-origin'})).json())
     ```
   - Assert: `saved_audit_queries` array length ≥ 5 with these
     `slug`s present:
     - `top-mutating-principals-30d`
     - `unacknowledged-external-writes`
     - `cost-gate-denials-this-week`
     - `rollbacks-last-quarter`
     - `pii-writes-last-90d`
     Each has `is_starter: true`. The dialect-aware seed (Sprint
     32 — see `feedback_alembic_check_blind_spot.md` memory)
     ensures these land on both SQLite and Postgres.

3. **Run a starter query**.
   - Action: click "Run" on `top-mutating-principals-30d`.
   - Assert (network): `POST /api/saved-audit-queries/{slug}/run`
     returns 200 with `{rows, columns}`. Page renders the result
     table inline. On a clean seed-e2e the rows are typically
     empty (no agent runs yet); seed-full-stack-demo populates
     it.

4. **Export to CSV / JSON**.
   - Action: click the CSV button on the same row.
   - Assert (network): `GET .../export.csv` returns 200 with
     `Content-Type: text/csv` and a `Content-Disposition`
     attachment header. The audit log gets a new row of
     `action=export_audit_query, target=saved_audit_query:<slug>`.

5. **Create a custom saved query** (admin-only).
   - Action: from the "Create new query" form, fill Name = `my
     custom query`, SQL = `SELECT 1 AS one`, click Save.
   - Assert (network): `POST /api/saved-audit-queries` returns
     201 with `{slug, name, ...}`. Slug is generated from the
     name. Run it to verify execution.

### Part E — CDF system errors (3 steps)

Phase 42 adds a server-rendered "System errors" band above the
sigma anomaly cards on `/audit/inbox`. It surfaces foreign-Delta
CDF subscriptions whose last tail tick stamped `last_error`.
Point-in-time state — the next successful tick clears it.

1. **Verify the band is hidden in clean state**.
   - Action: ensure all CDF subscriptions in the workspace have
     `last_error IS NULL` (fresh seed-e2e satisfies this).
   - Action: `browser_navigate('http://127.0.0.1:8000/audit/inbox')`.
   - Assert: no `<section data-inbox-section="system-errors">`
     element in the DOM. The page jumps straight from the
     intro paragraph to the filter form.

2. **Trigger a CDF tail error**.
   - Action: navigate to `/admin/cdf-subscriptions`, register a
     subscription against a non-existent FQN
     (e.g. `demo.does.not_exist`).
   - Action: click "Run tail now". Wait for the page reload —
     the new row's `Last error` column populates with the
     "uc.get_table failed" string (or whatever soyuz returns
     for the missing table).
   - Action: reload `/audit/inbox`.
   - Assert: the System-errors `<section>` is now visible above
     the anomaly table. The badge shows the count, the row
     surfaces the table FQN as `<code>`, the truncated error
     message in red, and `Last attempt` with the ISO timestamp.

3. **Click the action link**.
   - Action: click "Open admin" on the system-errors row.
   - Assert: the browser navigates to
     `/admin/cdf-subscriptions`. Auditor scope was sufficient to
     *see* the error; clearing it (delete the broken sub or
     re-run after fixing the table) is admin-only and lives
     there.

## Playwright MCP script

Browser replay for the four cockpit pages:

1. `browser_navigate('http://127.0.0.1:8000/audit/inbox')`
   — `browser_wait_for("table tbody tr")`; assert ≥ 1 anomaly
   row.
2. `browser_click(".anomaly-row[data-state='open']:first")`
   — assert URL becomes `/audit/inbox?focus=<anomaly_id>`;
   detail panel slides in.
3. `browser_click("Acknowledge")` — assert toast and the row
   flips state from `open` to `acknowledged`.
4. `browser_navigate('http://127.0.0.1:8000/audit/search')`
   — type into the placeholder-bearing input
   `placeholder="e.g. silver.orders OR pql_query OR schema_mismatch"`
   (no `role=searchbox` — see BUG-41-01),
   `browser_press_key("Enter")` — assert ≥ 1 match in the
   results.
5. `browser_evaluate('() => document.querySelectorAll(".audit-result-row").length')`
   — capture the result count for sanity.
6. `browser_navigate('http://127.0.0.1:8000/audit/by-table/main.silver.orders')`
   — assert the reverse-index card lists the latest writes
   to that table.
7. `browser_navigate('http://127.0.0.1:8000/audit/queries')`
   — assert ≥ 1 saved query is visible.
8. `browser_click(".saved-query-row:first .run-button")`
   — `browser_wait_for(".query-result-table")`; assert ≥ 1 row.
9. `browser_click("Save query as…")`,
   `browser_fill_form([{name:"slug", value:"phase41-test-q"}])`,
   `browser_click("Save")` — assert new row appears in the
   workbench list.

## Verification log

- **2026-05-07 — Phase 41 smoke replay.** `/audit/inbox`,
  `/audit/search`, `/audit/queries` all render. Inbox shows
  2 of 2 breaches against `seed-full-stack-demo` data. Search
  page renders an `<input type="text">` (NOT `role="searchbox"`)
  — see BUG-41-01.
- **2026-05-06 — data-path verified end-to-end (Phase 38.3).**
  Replayed against `seed-broken-run.py` + a partial
  `seed-full-stack-demo.py` run (mlflow/sklearn extras absent
  in the e2e venv, so `_step_train` bails — bronze/silver/gold
  steps complete and seed enough activity for the cockpit).
  Verified live in Firefox via Playwright MCP, 0 console errors:
  - Part A — `/audit/inbox` shows "2 of 2 breach(es) — metrics
    rejects, errored_ops, 7d baseline at 2σ"; severity / metric /
    bin filters render; htmx target swaps without TypeError
    (BUG-37-04 fix verified as a side-effect).
  - Part B — `GET /api/audit/search?q=customer` returns
    `available: true`; `q=silver` returns 1 hit (custom tokenizer
    matches inside FQN path segments).
  - Part C — `/audit/by-table/demo.incidents.broken_orders`
    serves the populated cockpit branch (heading flips to "Runs
    that touched …", Touched tab counter reads "2 run(s)
    touched …"); empty-path branch (BUG-37-05 picker route)
    not re-checked but covered by the Phase 37.1 close.
  - Part D — `GET /api/saved-audit-queries` returns all 5
    starter slugs; `POST /api/saved-audit-queries/top-mutating-
    principals-30d/run` returns `{rows: [..], columns:
    ['principal', 'rows_written']}` (status 200, 2 rows).

## Found bugs

- **BUG-41-01** ✅ Fixed in same edit — Sprint-D MCP script
  used `browser_type(role="searchbox", …)` which doesn't match;
  the actual element is `<input type="text"
  placeholder="e.g. silver.orders …">` with no
  `role=searchbox`. Selector should be by placeholder text.
  Surfaced 2026-05-07 during Phase 41 smoke replay.



- **BUG-37-04** ✅ Fixed — root cause was an unguarded
  `o.includes("?")` call in htmx 2.0.3 (`o` was `null` for
  certain page-load synthetic GETs). Fixed by upgrading
  the CDN pin to htmx 2.0.6, which adds the
  `if (o == null || o === "") o = location.href` guard
  before `.includes`. Verified: zero console errors on
  `/audit/inbox`, `/audit/search`, `/alerts`.

- **BUG-37-05** ✅ Fixed — `/audit/by-table` now serves a
  picker form (FQN input + "Open" button) instead of
  rendering the tab chrome. The route handler short-
  circuits on empty `fqn`, returning `kinds=[]` so no
  loaders fire, and the template renders the picker
  branch. The historical `/audit/by-table/{fqn:path}`
  route still serves a populated cockpit when an FQN is
  in the URL.

## Cleanup

```bash
# Delete the custom saved query (uses the same auto-generated slug)
curl -sS -X DELETE \
  http://127.0.0.1:8000/api/saved-audit-queries/my-custom-query \
  -b cookies.txt
```
