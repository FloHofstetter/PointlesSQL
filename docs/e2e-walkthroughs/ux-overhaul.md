# UX overhaul walkthrough

> **Mode:** `browser` · **Phase:** 17 · **Surface:** Sidebar + theme + density overhaul

's UX-overhaul pass — exercises the keyboard-shortcut registry,
the shared `pqlApi` fetch + toast flow, and the new
`prefers-reduced-motion` + global `:focus-visible` contract. Stack stays
FastAPI + Jinja2 + Bootstrap 5.3 + HTMX + Alpine.js; there is no React
migration.

## Preconditions

- [`auth.md`](auth.md) ran first — `admin@pql.test` is logged in.
- [`catalog-browsing.md`](catalog-browsing.md) seed ran — catalog `demo`
 with schemas `sales` + `hr` is present.
- A non-paused demo job exists for the toast-flow pass. Any job created
 by [`jobs.md`](../guides/jobs.md) works; otherwise create one through the
 `/jobs` modal first.

## Walkthrough

### Pass A — Shortcut registry + chords

1. **Help modal lists every shortcut**.
 - Action: `browser_navigate('http://127.0.0.1:8000/')` then
 `browser_press_key(key='?')`.
 - Assert: the `.pql-cmdk-help` dialog opens; the `<dl>` shows nine
 rows — `⌘K` / `?` / `esc` / `↑ ↓` / `↵` / `g h` / `g j` / `g d` /
 `r`. Each chord row renders its two keys with a space separator
 (`.pql-cmdk-shortcut-sep`).
 - Action: `browser_press_key(key='Escape')`. Assert the help closes.

2. **Cmd+K opens palette from anywhere**.
 - Action: `browser_press_key(key='k', modifiers='Meta')` (Ctrl on
 non-Mac).
 - Assert: palette opens with search input focused. Press Esc to
 close.

3. **Vim-chord navigation**.
 - Action: press `g`, then within 1s press `h`.
 - Assert: navigates to `/`. Repeat with `g j` → `/jobs` and `g d` →
 `/dashboards`. A `g` followed by any other key (or a 1.2s pause)
 cancels the chord without side effects.

4. **`r` refreshes list pages only**.
 - Action: on `/jobs` (a list page, `data-pql-refresh="1"` on
 `<body>`), press `r`.
 - Assert: toast shows "Refreshing." and the page reloads immediately
 (no 400 ms delay since it's a refresh, not a mutation).
 - Action: navigate to `/jobs/<id>` (detail page, no
 `data-pql-refresh`), press `r`.
 - Assert: nothing happens — the shortcut is opt-in per page.

5. **Editable-target guard**.
 - Action: click a tag input on a catalog detail page, type `r`.
 - Assert: the letter `r` is inserted into the input; no reload fires.

### Pass B — Shared fetch + toast flow

1. **Mutation error surfaces as toast**.
 - Action: create a job whose `cron_expr` is intentionally invalid
 (e.g. `"not a cron"`).
 - Assert: the modal's inline `this.error` hint appears **and** a red
 toast pops bottom-right with the soyuz `detail` text. The modal
 stays open; the list is not reloaded.

2. **Mutation success → toast-then-reload**.
 - Action: from `/jobs/<id>` click "Run now".
 - Assert: a success toast "Run started." appears, then 400 ms later
 the page reloads and the new run row is present.
 - Action: on `/dashboards/<slug>` click "Refresh".
 - Assert: blue info toast "Dashboard refreshing." appears, reload
 follows 400 ms later.

3. **Federation flow reuses `pqlApi`**.
 - Action: open `/connections`, click "New connection", submit with a
 blank name.
 - Assert: client-side guard sets `this.error` to "Name is required.";
 no network call, no toast.
 - Action: retry with a valid name + a duplicate of an existing
 connection. Assert: red toast with the soyuz "already exists"
 detail; modal remains.

4. **Silent GETs stay silent**.
 - Action: open a catalog detail page with the Permissions tab.
 - Assert: the background `loadEffective()` call uses
 `pqlApi.fetch(..., { silent: true })` — no toast appears even when
 the endpoint is unreachable (verify by cutting soyuz and reloading;
 the tab shows the fetched `effective` list as empty but no red
 toast fires).

### Pass C — Reduced motion + focus rings

1. **Focus outlines are visible on every interactive element**.
 - Action: from `/catalogs/demo`, press `Tab` repeatedly.
 - Assert: each tab-stop gets the 2 px accent outline with 2 px offset
 (`--pql-color-accent`). Verified via
 `browser_evaluate(function='() => getComputedStyle(document.activeElement).outlineWidth')`
 returning `"2px"`.

2. **Reduced-motion kills animations**.
 - Action: emulate
 `prefers-reduced-motion: reduce` via DevTools / Playwright emulate;
 reload the page; open the palette (Cmd+K).
 - Assert: no fade-in / slide-in — the palette appears instantly. The
 sidebar drawer at `<768 px` also opens without transition. The
 `--pql-duration-*` tokens all read `0ms`
 (`browser_evaluate('() => getComputedStyle(document.documentElement).getPropertyValue("--pql-duration-normal")')`
 returns `"0ms"`).

## Playwright MCP script — skeleton

```text
# Pass A — shortcuts
browser_navigate('http://127.0.0.1:8000/')
browser_press_key(key='?')
browser_wait_for(text='Open command palette')
browser_press_key(key='Escape')
browser_press_key(key='g'); browser_press_key(key='j') # → /jobs
browser_press_key(key='r') # toast + reload

# Pass B — toast flow
browser_navigate('http://127.0.0.1:8000/jobs')
browser_click(element='button with text "New job"')
# … fill in bad cron …
browser_click(element='button with text "Create"')
browser_wait_for(text='invalid') # toast text from soyuz detail

browser_navigate('http://127.0.0.1:8000/jobs/1')
browser_click(element='button with text "Run now"')
browser_wait_for(text='Run started.')

# Pass C — reduced motion
browser_evaluate(function='() => { window.matchMedia = () => ({ matches: true, addEventListener: () => {} }); }')
browser_navigate('http://127.0.0.1:8000/')
browser_press_key(key='k', modifiers='Meta')
browser_evaluate(function='() => getComputedStyle(document.documentElement).getPropertyValue("--pql-duration-normal")') # expect "0ms"
```

## Found bugs

_No app bugs surfaced on the replay (2026-04-18, commit
pending, Playwright MCP against `docker/docker-compose.e2e.yml`). Verified
end-to-end:_

- _**Pass A** — `?` opens the help modal with all nine shortcuts
 rendered from the Alpine `shortcuts` array (`⌘K` / `?` / `esc` /
 `↑↓` / `↵` / `g h` / `g j` / `g d` / `r`). Esc closes it. Chord
 `g` → `j` dispatched as two successive keydown events navigates
 `/` → `/jobs`. `r` on `/jobs` (`data-pql-refresh="1"` on body)
 triggers `pqlApi.reloadWithToast("Refreshing.", {delay: 0})` and
 the page reloads; `r` on `/catalogs/demo` (no flag) is inert._
- _**Pass B** — `pqlApi.fetch('/api/jobs', { method: 'POST', body:
 {invalid} })` returns `{ok: false, status: 422, error: "name and
 cron_expr are required"}` with the `detail` field extracted from
 the FastAPI error envelope; a single `.pql-toast--error` mounts
 under `#pql-toast-root`. The `silent: true` opt-out suppresses
 the toast while still returning the same envelope.
 `pqlApi.reloadWithToast(msg)` emits a `.pql-toast--success`
 before its delayed reload; `{variant: "info"}` selects the
 blue `.pql-toast--info` variant used by the
 `/dashboards/{slug}` Refresh button._
- _**Pass C** — keyboard-focused `.navbar-brand` computes
 `outlineWidth: 2px / outlineStyle: solid / outlineColor:
 rgb(118, 185, 0)` (the `--pql-color-accent` token), confirming
 the new global `:focus-visible` rule. The CSSOM reports the
 `@media (prefers-reduced-motion: reduce)` block resets all three
 duration tokens (`--pql-duration-fast/normal/slow`) to `0ms` and
 applies `animation-duration: 0ms` / `transition-duration: 0ms`
 on `*, *::before, *::after`._

### Harness notes

- **Chord timing vs. MCP round-trip**: pressing `g` then `j` via
 two back-to-back `browser_press_key` calls races the 1 s chord
 window — the MCP tool round-trip plus browser-CDP latency can
 exceed `CHORD_TIMEOUT_MS`, so `_cancelChord()` fires between the
 two presses and the second key sees `_chordPending = false`. Not
 an app bug; same sequence dispatched via `window.dispatchEvent(new
 KeyboardEvent('keydown', …))` inside a single `browser_evaluate`
 navigates correctly. Manual keyboard use on a real browser is
 unaffected (human typing is well under 1 s between keys). Future
 replays should exercise chords via synthetic dispatch, single-
 key shortcuts via native press.
