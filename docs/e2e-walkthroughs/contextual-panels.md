# Contextual side-panels walkthrough

> **Mode:** `browser` · **Surface:** Sidebar context-panel

Exercises the context-panels: the 240-px sidebar to the right of
the primary rail. The rail is now **six hubs** (Home · Watch ·
Build · Data · Community + Admin); each hub opens its **spoke
list** in this panel, followed by the section's contextual content
(catalog tree, runs list, branch list, …). So reaching e.g. Runs
is: click the **Watch** hub, then the **Agent runs** spoke — and
the deep contextual list still renders below, so the user never
has to hop into the main listing page just to find one item.

The goal is to prove that **each hub renders its spoke list, every
contextual panel binds its Alpine factory, fetches data, renders
rows, exposes a help-popover, and does not leak state across
boost-navigation**.

This walkthrough is **driven from a browser** and replayable by
Claude Code via `mcp__playwright__browser_*` against headful
Firefox.

## Preconditions

- PointlesSQL is running locally on `http://127.0.0.1:8000`.
- You're logged in as an admin (so Workspace + Branches +
 Admin rail items are visible).
- Some seed data exists — at minimum a couple of agent runs, a
 Delta-branch, a notebook file, a job, an alert, and a registered
 model. The default `scripts/seed-full-stack-demo.py` gives you
 all six.

## Walkthrough

### 1. Federation panel (catalog tree) — under the Data hub

- Action: navigate to `/connections`. The **Data** hub is active.
- Assertion: the panel shows the **DATA** spoke list on top
 (Catalog · Data products · Domains · Glossary · Mesh · Ingest ·
 Views · Canvas · ML models · MLflow · Delta branches · Lineage),
 then the catalog tree under the "CATALOG" header. At least one
 catalog row visible with a chevron. Tables, volumes
 (`bi-hdd-stack`), and models (`bi-box-seam`) render under their
 schemas when expanded.
- Why it matters: this is the reference contextual partial; the
 hub spokes sit above it without disturbing it.

### 2. Runs panel — three-bucket grouping

- Action: click the **Watch** hub, then the **Agent runs** spoke.
 URL becomes `/runs`.
- Assertion: the panel header reads "Runs" + an `info` icon.
 Below: any of "Needs approval" (warning), "Running" (info), or
 "Recent" (muted) buckets. Each row shows an 8-char short ID,
 a status badge (color-matched to the main page), and a relative
 timestamp ("2 m ago"). The header **R** of "RUNS" is a link to
 `/runs`.
- Action: click the `info` icon next to the header.
- Assertion: a Bootstrap popover opens with title "Runs panel"
 and a body explaining the three buckets, plus a "Learn more →"
 link.
- Action: click any row.
- Assertion: URL changes to `/runs/<full-uuid>`. The row that was
 clicked picks up the green accent border in the panel and
 remains active when the page swaps in.

### 3. Branches panel — admin-gated

- Action: click the **Data** hub, then the **Delta branches**
 spoke (admin-only — renders as a lock stub for non-admins). URL
 becomes `/branches`.
- Assertion: panel header "Branches" + `info` icon. Active /
 Promoted / Discarded sub-headers appear depending on which
 states have rows. Each row shows the branch FQN + a strategy
 tag (`cow` / `symlink`) on Active, or a relative-time on
 Promoted/Discarded. Click the help icon — popover title
 "Branches panel".
- Action: click any branch row.
- Assertion: URL changes to `/branches#<fqn>` and the matching
 card on the main page scrolls into view.

### 4. Workspace panel — flat notebook list

- Action: click the **Build** hub, then the **Notebooks** spoke.
 URL becomes `/notebooks/workspace`.
- Assertion: panel shows alphabetically-sorted `.py` and `.ipynb`
 notebook paths, format-tagged (`py` info / `ipynb` warning).
 Help icon title "Workspace panel". Click any row → URL
 becomes `/notebooks/workspace?path=<path>` and the active row
 picks up the accent border.
- If 30 entries shown: a "Showing 30 most-recent files — browse
 all →" hint footer is visible.

### 5. Jobs panel — active/paused split

- Action: click the **Build** hub, then the **Scheduled jobs**
 spoke. URL becomes `/jobs`.
- Assertion: Active rows have a `bi-clock-history` icon + the
 most-recent run-status badge. Paused rows are muted with a
 `bi-pause-circle` icon and no status badge. Help icon title
 "Jobs panel". Click a row → `/jobs/<id>`.

### 6. Alerts panel — enabled/disabled split

- Action: click the **Watch** hub, then the **Alerts** spoke. URL
 becomes `/alerts`.
- Assertion: Enabled rows have a green `bi-bell`; disabled rows a
 muted `bi-bell-slash` and muted text. Help icon title "Alerts
 panel". Click a row → `/alerts/<slug>`.

### 7. MLflow panel — recent registered models

- Action: click the **Data** hub, then the **MLflow** spoke. URL
 becomes `/ml`. The main area shows the MLflow Tracking iframe (or
 a warning if the subprocess isn't running).
- Assertion: panel header "MLflow" + `info` icon. "Recent
 models" sub-header. Each row shows the model name, a
 `v<latest_version>` badge, and a status badge (READY /
 PENDING_REGISTRATION / FAILED_REGISTRATION). A footer link
 "Open MLflow UI →" points back to `/ml` (so the panel works
 even if you're already on a sub-page).
- Action: click any model row → URL becomes
 `/models/<full_name>` and the row remains active.

### 8. Cross-section round-trip — Alpine survives boost-swap

- Action: from `/connections` (Data hub), click the **Watch** hub
 then its **Agent runs** spoke. Then the **Build** hub → **SQL
 editor** spoke. Then back to the **Data** hub → **Catalog**
 spoke.
- Assertion: each transition swaps the context-panel's contents
 via HTMX OOB (the panel has `id="pql-context-panel"` and
 `hx-swap-oob="true"`). No console errors. The catalog tree
 re-binds with its previous expand/collapse state preserved in
 `sessionStorage`.

### 9. Refresh button per panel

- Action: from any non-Federation rail section, click the
 `bi-arrow-clockwise` button in the panel's top-right corner.
- Assertion: the spinner spins briefly, the
 `sessionStorage` cache clears, and a fresh fetch repopulates
 the rows. No console errors.

### 10. Empty-state copy

- Action (only meaningful with an empty seed): visit a section
 with zero items (e.g. `/branches` on a fresh install).
- Assertion: the panel shows an actionable hint, not just "no
 data" — Branches says ``pql.branch('catalog.schema')``,
 Workspace says "drop a file into the notebooks dir",
 Alerts says "/alerts/new", etc.

## Wider verification ladder

| Level | Gate |
|---|---|
| **L1** | Each panel renders ≥ 1 row OR the matching empty-state copy |
| **L2** | Each panel header carries an `info` icon whose popover title matches "(Section) panel" |
| **L3** | Click on any panel row navigates to the underlying detail page and applies the active-row accent |
| **L4** | Boost-navigation between sections swaps the context-panel via OOB; no `htmx:swapError` events |
| **L5** | Refresh button clears `sessionStorage` and re-fetches |
| **L6** | `uv run pytest tests/test_help_registry.py -q` passes — every slug resolves and obeys the length caps |

## Playwright MCP script

Condensed cross-section replay — each step clicks a rail **hub**
(`.pql-icon-rail__link[data-section='<hub>']`) then a **spoke** in
the context panel (`.pql-context-panel__link:has-text('<label>')`):

1. `browser_navigate('http://127.0.0.1:8000/connections')`
   — Data hub active; assert the panel shows a `DATA` spoke header
   and the catalog tree's `CATALOG` header.
2. `browser_click(".pql-icon-rail__link[data-section='watch']")`
   then `browser_click(".pql-context-panel__link:has-text('Agent runs')")`
   — URL → `/runs`; panel header reads `Runs`; ≥ 1 row visible.
3. `browser_click(".panel-header .info-icon")`
   — `browser_wait_for(".popover")` → title contains
   `Runs panel`; `browser_press_key("Escape")` to dismiss.
4. `browser_click(".pql-icon-rail__link[data-section='data']")`
   then `browser_click(".pql-context-panel__link:has-text('Delta branches')")`
   — URL → `/branches`; admin-only — assert visible.
5. `browser_click(".pql-icon-rail__link[data-section='build']")`
   then `browser_click(".pql-context-panel__link:has-text('Notebooks')")`
   — URL → `/notebooks/workspace`.
6. (still Build hub) `browser_click(".pql-context-panel__link:has-text('Scheduled jobs')")`
   — URL → `/jobs`.
7. `browser_click(".pql-icon-rail__link[data-section='watch']")`
   then `browser_click(".pql-context-panel__link:has-text('Alerts')")`
   — URL → `/alerts`.
8. `browser_click(".pql-icon-rail__link[data-section='data']")`
   then `browser_click(".pql-context-panel__link:has-text('MLflow')")`
   — URL → `/ml`; panel header `MLflow`; ≥ 1 model row.
9. `browser_click(".panel-row:first")` (on any panel)
   — assert the navigated row gets the
   `.panel-row--active` accent border.
10. From the Data hub, `browser_click(".pql-context-panel__link:has-text('Catalog')")`
    then Watch hub → `Agent runs`, then Data hub → `Catalog` again
    — assert no `htmx:swapError` in
    `browser_console_messages()`; the rail hub highlight follows
    `data-active-hub`, and the catalog tree retains its
    expand/collapse state from sessionStorage.
11. `browser_click(".panel-header .bi-arrow-clockwise")`
    — `browser_evaluate('() => sessionStorage.getItem("pql.contextPanel.runs")')`
    is null after the click; new fetch repopulates rows.

## Bugs and fixes

None known on land. Pre-existing bug in
`pointlessql/api/mlflow_html_routes.py` (positional-arg signature
for `templates.TemplateResponse`) was fixed in passing during
24.6 verification — the route now passes `request` first per the
Starlette 0.37+ convention.
