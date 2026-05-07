# List-page polish walkthrough

> **Mode:** `browser` · **Phase:** 17 · **Surface:** List-page polish (sticky headers, density)

Covers the list-page polish: client-side search, sortable
column headers, filter chips, cron humanization, "last run" column
on `/jobs` (status dot + relative time), and hover quick-actions on
job rows (Run now / Pause + Resume). Verifies progressive enhancement
(rows remain usable without JS), the debounce (150 ms) on search,
and the toast-then-reload cadence for row mutations.

## Preconditions

- Stack up via `docker-compose.yml` + `docker-compose.e2e.yml`.
- Run [`auth.md`](auth.md) once so `admin@pql.test` and
 `user@pql.test` exist.
- Run [`jobs-dag.md`](jobs-dag.md) so ≥ 3 jobs exist with mixed
 `kind`, mixed paused/active, and at least one with completed run
 history (required for the last-run column and the sparkline
 regression check).
- Run [`dashboards.md`](dashboards.md) and [`federation.md`](federation.md)
 so `/dashboards`, `/connections`, `/credentials`, and
 `/external-locations` all have ≥ 2 rows.
- Browser: launch with `--browser firefox` per
 [CLAUDE.md](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md).

## Walkthrough

### Part A — `/jobs` list search + sort + chips

1. **Log in as `admin@pql.test` and navigate to `/jobs`.**
 - Assert: the table renders all seeded jobs, sorted by name
 (alphabetical ascending by default per the `initialSort`).
 - Assert: the Name header carries an ascending-arrow indicator
 (`aria-sort="ascending"`), other sortable headers show `aria-sort="none"`.

2. **Debounced client-side search.**
 - Action: type a unique substring of one job's name into the
 search input at the top of the card (e.g. `smoke`).
 - Assert: after ~150 ms, non-matching rows gain `hidden` and only
 the matching row(s) are visible.
 - Assert: typing a nonsense token (e.g. `xxyyzz`) hides every row
 and reveals the `pql-list-empty` fallback with text "No results.".
 - Action: clear the input; after the debounce, every row is
 visible again.

3. **Sortable headers cycle asc → desc → none.**
 - Action: click the Name header.
 - Assert: `aria-sort` flips to `descending`; row order reverses.
 - Action: click Name again.
 - Assert: `aria-sort` returns to `none`; the original DOM order
 is preserved (matters because `initialSort.dir` was `asc` but
 the user has now explicitly opted out).
 - Action: click Kind; assert rows sort by kind; click Last run
 header; assert rows sort by `last_run_at` (ISO-8601 compare);
 click Status header; assert paused rows segregate.

4. **Filter chips AND together.**
 - Assert: two chips are visible in the controls row — `Paused`
 and `Last run failed`.
 - Action: click `Paused`; only rows whose `data-paused="1"` are
 visible (pre-seeded paused job(s) from `jobs-dag.md`).
 - Action: click `Last run failed` while `Paused` is still active.
 Only rows that are both paused and whose last run failed remain
 (likely zero; the empty-state renders).
 - Action: click `Paused` again to deactivate; only rows with a
 failed last run remain.
 - Action: click `Last run failed` again to deactivate; every row
 returns.

### Part B — `/jobs` cron humanization + last-run column

5. **Cron cell renders the friendly form.**
 - Precondition: at least one seeded job has `cron_expr="0 0 * * *"`
 (daily at midnight).
 - Assert: the Cron cell for that row reads `Daily at 00:00` (via
 `pqlHumanizeCron`).
 - Assert: the cell's `title` attribute is the raw expression
 `0 0 * * *` (hover tooltip preserves the source of truth).
 - Action: for a job with an unsupported cron pattern (e.g.
 `2,17 * * * *`), the cell falls back to the raw expression.

6. **Last run column shows status dot + relative time.**
 - Assert: rows for jobs with `last_run_status != null` render a
 `.pql-status-dot.pql-status-dot--{status}` span followed by a
 relative-time string (`pqlRelativeTime(iso)` — e.g. `5 min ago`).
 - Assert: rows with no runs show `—`.

### Part C — Hover quick-actions (admin only)

7. **Hover reveals the actions cell.**
 - Action: `browser_hover` over a row in the table.
 - Assert: the `.pql-row-actions` cell transitions from
 `visibility: hidden` to `visible`; two buttons are tappable
 (Run now icon + Pause/Resume icon).
 - Assert: moving focus into either button via keyboard (Tab) also
 makes the cell visible (`tr:focus-within`).

8. **Run now fires the existing endpoint + reloads.**
 - Action: `browser_network_requests()` → clear.
 - Action: click the Run now icon on a non-paused job.
 - Assert: a single `POST /api/jobs/{id}/run` appears in the log.
 - Assert: a success toast (`.pql-toast--success`) renders briefly
 with the message "Run started.".
 - Assert: ~400 ms later the page reloads and the "Last run"
 column on that row reflects the new run (status dot +
 "just now").

9. **Pause toggles to Resume.**
 - Action: click the Pause icon on an active job.
 - Assert: a `POST /api/jobs/{id}/pause` request; toast reads
 "Job paused."; after reload the row's Status column shows the
 `paused` badge.
 - Action: click the Resume icon on the now-paused row.
 - Assert: a `POST /api/jobs/{id}/unpause` request; toast reads
 "Job resumed.".

10. **Non-admin cannot see the actions column.**
 - Action: log out, log in as `user@pql.test`.
 - Navigate to `/jobs`.
 - Assert: the table has no `.pql-row-actions` cell at all (the
 column is Jinja-gated on `is_admin`).

### Part D — `/dashboards`, `/connections`, `/credentials`, `/external-locations`

11. **Each list supports search + sort.**
 - For each of `/dashboards`, `/connections`, `/credentials`,
 `/external-locations`:
 - Assert: the controls row renders the search input with the
 page-specific placeholder.
 - Action: type a known substring; assert only matching rows
 remain after the debounce.
 - Action: click the Name (or Title) header; assert the order
 flips.

12. **Chips apply where configured.**
 - `/dashboards`: one chip (`Has bound job`) shows only
 dashboards with a non-null `job_id`.
 - `/connections`: one chip per distinct `connection_type` in
 the seed data (e.g. `POSTGRESQL`, `MYSQL`); clicking one
 filters to just those.
 - `/credentials`: one chip per distinct `purpose` (e.g.
 `SERVICE`, `STORAGE`).
 - `/external-locations`: no chips (roadmap nuance — there is no
 natural categorical facet).

### Part E — API contract

13. **`GET /api/jobs` carries the three new fields.**
 - Action: `curl -b <session-cookie>
 http://127.0.0.1:8000/api/jobs | jq '.[0]'`
 - Assert: the shape includes `last_run_status`, `last_run_at`,
 `last_run_duration_s` keys. Values are strings / ISO-8601 /
 float when a run exists, `null` when no runs exist.

### Part F — Regressions on `/`

14. **Home dashboard still renders relative time after the helper
 extraction.**
 - Action: navigate to `/`.
 - Assert: the Latest job runs table still uses
 `pqlRelativeTime` (no blank cells, no `[object Object]`).
 This verifies the extraction of
 `window.pqlRelativeTime` into `/static/js/relative_time.js`
 did not break.
 - Action: `browser_evaluate('typeof window.pqlRelativeTime')`.
 - Assert: returns `"function"`.

## Playwright MCP script

Browser replay for the list-page polish (sticky headers, density
toggle, relative-time formatter):

1. `browser_navigate('http://127.0.0.1:8000/jobs')`
   — assert table renders with the jobs list.
2. `browser_evaluate('() => document.querySelector("table thead").getBoundingClientRect().top')`
   — capture initial top; scroll the table body via
   `browser_press_key("End")`; re-evaluate — assert the
   `<thead>`'s `top` stayed at 0 (sticky header).
3. `browser_click(".density-toggle")`
   — assert the table's `data-density` flips between `comfy`
   and `compact`.
4. `browser_evaluate('() => Array.from(document.querySelectorAll(".relative-time")).map(n => n.innerText)')`
   — assert at least one ends with `ago` (relative-time
   formatter is wired).
5. `browser_evaluate('() => typeof window.pqlRelativeTime')`
   — assert `"function"` (helper is exposed for re-use).
6. `browser_navigate('http://127.0.0.1:8000/runs')`
   — repeat steps 2-4 on the runs list (same convention).
7. `browser_navigate('http://127.0.0.1:8000/alerts')`
   — repeat steps 2-4 on the alerts list.
8. `browser_evaluate('() => document.querySelector("[data-density]").dataset.density === sessionStorage.getItem("pql.density")')`
   — assert density preference persists across navigations.

## Found bugs

- **BUG-33-01** (fixed same-sprint): `x-data="{ c: {{ job.cron_expr|tojson }} }"`
 on the Cron and Last-run cells broke the HTML parser — `tojson`
 emits a double-quoted JSON string, and the outer double-quoted
 attribute terminated after the opening inner quote (`x-data="{ c: "`).
 Alpine logged `expected expression, got '}'` and the cells rendered
 empty. Fixed by switching the outer attribute to single quotes
 (`x-data='{ c: {{ job.cron_expr|tojson }} }'`) on both
 [jobs.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/jobs.html) and
 [job_detail.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/job_detail.html).
 Surfaced by the post-merge Playwright replay.

- **BUG-33-02** (fixed same-sprint): relative-time strings drifted
 by the client's UTC offset — a run fired "just now" showed up as
 "2 hours ago" on a CEST browser. Root cause: `JobRun.started_at`
 is stamped `datetime.now(UTC)` server-side but SQLite strips the
 tzinfo on readback, so `.isoformat()` emits no-tz strings like
 `"2026-04-17T15:15:44.341818"`, which `Date.parse` then parses as
 local. Predates (the same helper fed 's home
 `latest_runs`), but surfaced it on the new jobs
 Last-run column so the fix lands here. Added
 `window.pqlParseServerIso(iso)` in
 [relative_time.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/relative_time.js) — appends
 'Z' only when the string has no tz marker — and routed
 `pqlRelativeTime` + both `toLocaleString` tooltip call sites
 (jobs.html, home.html) through it.
