# Command palette walkthrough

> **Mode:** `browser` · **Phase:** 17 · **Surface:** Ctrl-K palette overlay

Covers the global command palette: navbar trigger, Cmd+K
keyboard activation, debounced `GET /api/search` aggregation across
catalogs / schemas / tables / federation / jobs / dashboards /
notebooks, ↑↓/Enter/Esc keyboard flow, recent-searches localStorage,
the `?` keyboard-shortcuts help modal, and the admin/non-admin
visibility split on notebook hits.

## Preconditions

- Stack up via `docker-compose.yml` + `docker-compose.e2e.yml`.
- Run [`auth.md`](auth.md) once so `admin@pql.test` and `user@pql.test`
 exist; downstream steps assume admin is logged in.
- Run [`catalog-browsing.md`](catalog-browsing.md) (or
 `scripts/seed-e2e.py`) so soyuz has at least one catalog with
 schemas + tables to find.
- Run [`notebook-jobs.md`](notebook-jobs.md) Part G's upload step so
 there is at least one `.ipynb` under `notebooks/` for the notebook
 source to surface.
- Browser: launch with `--browser firefox` per
 [CLAUDE.md](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md) (the system Chrome channel breaks the
 Playwright MCP harness).

## Walkthrough

1. **Navbar trigger renders with platform-aware modifier hint.**
 - Action: log in as `admin@pql.test`, navigate to `/`.
 - Assert: a ghost button with the search-glass icon, the placeholder
 text `Search…`, and a `<kbd>` block reading either `⌘+K` or
 `Ctrl+K` is visible to the right of the brand at viewport widths
 ≥ 768 px (the wide variant is `.d-none.d-md-inline-flex`).
 - Assert (mobile): at < 768 px the wide trigger is hidden and a
 `bi-search` icon-only button is shown instead.

2. **Cmd+K opens the palette.**
 - Action: send `browser_press_key(key='Meta+k')` (or `Control+k` on
 non-Mac Playwright runs); fall back to clicking the navbar
 trigger when keyboard chords are tricky in the harness.
 - Assert: the dialog `[role=dialog][aria-label="Search PointlesSQL"]`
 appears with focus inside its `<input>`. The backdrop
 (`.pql-cmdk-backdrop`) covers the page.
 - Assert: the empty-state line `Start typing to search.` is visible
 (no recent searches yet on a fresh stack).

3. **Type a known catalog prefix; hits appear.**
 - Action: `browser_type(element='palette input', text='unity')`
 (use whichever catalog name the seed script created).
 - Assert (after the 150 ms debounce): the result list shows a
 `CATALOG` badge row whose label exactly matches the catalog name,
 plus any schemas / tables that prefix-match. Prefix matches sort
 above substring matches.
 - Assert: `browser_network_requests()` shows exactly one
 `/api/search?q=unity&limit=50` GET — the input did not fire a
 request per keystroke.

4. **↑↓ keyboard navigation; ↵ opens the selected hit.**
 - Action: press `ArrowDown` twice, then `Enter`.
 - Assert: navigation lands on the URL of the third item (e.g.
 `/catalogs/<name>` or `/catalogs/<cat>/schemas/<schema>`),
 the dialog closes, and the chosen entry is now the first row of
 `localStorage['pql.recentSearches']` (verify via
 `browser_evaluate('() => JSON.parse(localStorage.getItem("pql.recentSearches"))')`).

5. **Esc closes mid-query without leaking selection state.**
 - Action: open palette via Cmd+K, type `xyz_no_match`, wait for the
 `No matches.` empty state, press `Escape`.
 - Assert: the dialog disappears; subsequent Cmd+K reopens with an
 empty input and the recent-searches list visible (today's seeded
 entry from step 4 must be the top row).

6. **Recent searches cap at 10 and dedupe by URL.**
 - Action: programmatically pre-populate localStorage with 11 entries
 and reload (`browser_evaluate` then `browser_navigate('/')`).
 - Assert: only the most recent 10 are kept after the next palette
 open. Selecting the same entry twice does not duplicate the row.

7. **Federation, job, and dashboard sources surface.**
 - Action: open palette, search for the seeded connection name from
 `federation.md`; then a job name from `jobs-dag.md`; then a
 dashboard slug from `dashboards.md`.
 - Assert each: badge type matches (`CONNECTION`, `JOB`, `DASHBOARD`),
 Enter navigates to `/connections/<name>`, `/jobs/<id>`, and
 `/dashboards/<slug>` respectively.

8. **Admin sees notebook hits; non-admin does not.**
 - Action (admin): search for the notebook filename uploaded in
 `notebook-jobs.md` Part G — assert a `NOTEBOOK` row appears and
 Enter navigates to `/notebooks/workspace?path=<relpath>`.
 - Action: log out, log in as `user@pql.test` / `Passw0rd!`, repeat
 the same search.
 - Assert: zero `NOTEBOOK` rows. Other source types (catalogs,
 schemas, tables, dashboards) still surface as before.

9. **`?` opens the keyboard-shortcuts help modal.**
 - Action: press `?` with focus on the page body (palette closed).
 - Assert: the help dialog `[aria-label="Keyboard shortcuts"]` opens
 listing `⌘/Ctrl + K`, `?`, `Esc`, `↑↓`, `↵` rows.
 - Action: press `Escape`.
 - Assert: the help modal closes.

10. **`?` is suppressed while typing.**
 - Action: open the palette, type a `?` into the search input.
 - Assert: the `?` character lands in the input (the search query
 now contains `?`); the help modal does **not** appear. Same
 check inside any catalog comment editor on the catalog detail
 page — the `editable` component's `<input>` swallows the key.

11. **Soyuz outage degrades gracefully (manual check, optional).**
 - Action: `docker compose stop soyuz-catalog`; reopen palette and
 query for `unity`.
 - Assert: the dialog still renders. Catalog/schema/table/federation
 hits are missing; locally-stored job and dashboard hits remain.
 The frontend shows no toast (silent — soyuz failure is logged
 server-side via `_wrap_catalog_errors`'s warning line). Restart
 soyuz before continuing downstream playbooks.

## Playwright MCP script

```text
browser_navigate('http://127.0.0.1:8000/')

# Step 2 — open palette
browser_press_key(key='Meta+k') # or Control+k off Mac
browser_snapshot()

# Step 3 — query, then assert single network request
browser_type(element='palette input', ref='[role=dialog] input', text='unity')
browser_wait_for(text='CATALOG')
browser_network_requests() # filter by /api/search

# Step 4 — keyboard nav + Enter
browser_press_key(key='ArrowDown')
browser_press_key(key='ArrowDown')
browser_press_key(key='Enter') # navigates + records recent

# Step 5 — Esc closes
browser_navigate('http://127.0.0.1:8000/')
browser_press_key(key='Meta+k')
browser_type(element='palette input', text='xyz_no_match')
browser_wait_for(text='No matches.')
browser_press_key(key='Escape')

# Step 6 — recents cap
browser_evaluate("""
 () => {
 const fake = Array.from({length: 11}, (_, i) => ({
 type: 'catalog', label: 'cat'+i, description: '',
 url: '/catalogs/cat'+i,
 }));
 localStorage.setItem('pql.recentSearches', JSON.stringify(fake));
 }
""")
browser_navigate('http://127.0.0.1:8000/')
browser_press_key(key='Meta+k')
browser_evaluate('() => JSON.parse(localStorage.getItem("pql.recentSearches")).length')

# Step 8 — non-admin
browser_click(element='user dropdown toggle')
browser_click(element='Sign out button')
browser_fill_form(fields=[
 {name:'email', value:'user@pql.test'},
 {name:'password', value:'Passw0rd!'},
])
browser_click(element='Sign in submit button')
browser_press_key(key='Meta+k')
browser_type(element='palette input', text='<your notebook stem>')
browser_snapshot() # assert no NOTEBOOK row

# Step 9 — help modal
browser_press_key(key='Escape')
browser_press_key(key='?')
browser_snapshot()
browser_press_key(key='Escape')
```

## Found bugs

_None at landing time. Add `BUG-31-NN` entries here if a future replay
surfaces issues._
