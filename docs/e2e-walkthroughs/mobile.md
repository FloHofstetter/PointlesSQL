# Mobile + responsive walkthrough

's mobile pass — exercised at three viewport sizes
(375 × 812, 768 × 1024, 1280 × 800) to cover the three breakpoint
bands the `--pql-breakpoint-sm/md` tokens cut out. Stack stays
FastAPI + Jinja2 + Bootstrap 5.3 + HTMX + Alpine.js; there is no
React migration.

## Preconditions

- [`auth.md`](auth.md) ran first — `admin@pql.test` is logged in.
- [`catalog-browsing.md`](catalog-browsing.md) seed ran — catalog
 `demo` with schemas `sales` + `hr` and the four demo tables is
 present.
- Seed a ≥ 20-column table for the columns-search branch, same as
 's playbook:
 ```python
 from pointlessql import PQL
 import pandas as pd
 pql = PQL()
 pql.write_table(
 pd.DataFrame([[i]*25 for i in range(3)], columns=[f"c{i:02d}" for i in range(25)]),
 "demo.sales.wide25",
 )
 ```

## Viewports

- **Phone** — 375 × 812 (iPhone 13 mini / 14 Pro baseline).
- **Tablet** — 768 × 1024 (iPad portrait).
- **Desktop** — 1280 × 800 (laptop reference).

## Walkthrough

### Pass A — 375 × 812

1. **Sidebar drawer on narrow viewports**.
 - Action: `browser_resize(375, 812)` + `browser_navigate('/catalogs/demo')`.
 - Assert: top navbar shows only the hamburger + brand + search-
 icon trigger; the inline `<ul class="navbar-nav">` is **not**
 visible (gated by `d-none d-sm-flex` on `.pql-topbar-nav`).
 - Action: click the hamburger.
 - Assert: the sidebar slides in from the left as an offcanvas
 drawer. The bottom of the drawer carries a "Navigation" footer
 section with Federation / Notebook / Workspace / Jobs /
 Dashboards / user dropdown links (visible only via
 `d-sm-none` on `.pql-sidebar-nav-footer`).
 - Action: press `Escape`.
 - Assert: the drawer closes.

2. **Cmd+K mobile trigger**.
 - Assert: the Cmd+K button in the top bar is rendered as a
 search icon only — the desktop label + keycap (`⌘K`) is
 hidden below 768 px.
 - Action: tap the search icon.
 - Assert: command palette opens.

3. **Touch target baseline**.
 - Assert via `browser_evaluate`: every `<button>`, `<a.btn>`,
 `<select>`, `<input[type=search]>` reports
 `offsetHeight >= 44` once the `@media (hover: none)` branch
 kicks in (DevTools emulates touch when the responsive panel
 is open).

4. **List tables → label/value cards**.
 - Action: navigate to `/jobs`.
 - Assert: rows collapse to vertical stacks. Each `<td>` shows
 an uppercase key on the left (from `data-label`) and the
 value on the right. Borders between rows replace the `<th>`
 row. The row-actions cell keeps its buttons inline (no
 `data-label::before` key).
 - Assert: a "Sort by" dropdown appears above the table
 (`.pql-list-sort-mobile`, `d-sm-none`); picking
 `Name ↓` reorders the stacked cards. The dropdown resets
 when picking `—`.
 - Repeat on `/dashboards`, `/external-locations`.
 - Repeat on the Columns card of
 `/catalogs/demo/schemas/sales/tables/wide25` (≥ 20-column
 branch): same stack layout + sort dropdown.

5. **Schemas / Tables / Preview cards (detail pages)**.
 - Action: navigate `/catalogs/demo`.
 - Assert: the Schemas card's rows render as label/value stacks
 (Name / Updated / Comment keys). Links still navigate into
 schema detail.
 - Action: navigate `/catalogs/demo/schemas/sales`.
 - Assert: Tables card rows stack (Name / Type / Format /
 Columns / Updated / Comment).
 - Action: navigate `/catalogs/demo/schemas/sales/tables/orders`.
 - Assert: Preview card rows stack once the fetch resolves; the
 Alpine template sets `data-label` from the `columns[]` array
 so each cell gets its column name as the key.

6. **Jupyter desktop-recommended notice**.
 - Action: navigate `/notebook`.
 - Assert: a blue-tinted `.pql-notebook-mobile-notice` banner
 sits above the iframe with "JupyterLab is optimised for
 desktop…". The iframe itself still loads and works.

### Pass B — 768 × 1024

1. **Shell switches to two-column**.
 - Action: `browser_resize(768, 1024)` + `browser_navigate('/')`.
 - Assert: the sidebar is pinned on the left (sticky
 `.pql-sidebar-shell`), not a drawer. The hamburger is hidden
 (`d-md-none`). The Cmd+K trigger shows the full
 `Search…` + `⌘K` keycap label (`d-none d-md-inline-flex`).
 - Assert: the Jupyter notice is hidden (navigate `/notebook`
 to confirm — the `.d-md-none` gate removes it at ≥ 768 px).

2. **List tables back to row layout**.
 - Action: navigate `/jobs`.
 - Assert: rows render as a normal Bootstrap table again; the
 mobile sort dropdown is hidden (`d-sm-none`). Sortable
 headers cycle asc → desc → none with `aria-sort` updates.

### Pass C — 1280 × 800

1. **No mobile degradation**.
 - Action: `browser_resize(1280, 800)` + spot-check `/catalogs/demo`,
 `/catalogs/demo/schemas/sales/tables/orders`, `/jobs`,
 `/notebook`, `/dashboards`.
 - Assert: every page matches its earlier appearance —
 the mobile-only CSS branches must not leak into desktop.

## Playwright MCP script — per-viewport skeleton

```text
# Pass A — phone
browser_resize(375, 812)
browser_navigate('http://127.0.0.1:8000/catalogs/demo')
browser_snapshot()
browser_click(element='navbar hamburger toggle')
browser_snapshot() # drawer open
browser_press_key(key='Escape')

browser_navigate('http://127.0.0.1:8000/jobs')
browser_evaluate(function='() => getComputedStyle(document.querySelector(".pql-list-table tbody tr td")).display') # expect "flex"

browser_navigate('http://127.0.0.1:8000/notebook')
browser_wait_for(text='JupyterLab is optimised for desktop')

# Pass B — tablet
browser_resize(768, 1024)
browser_navigate('http://127.0.0.1:8000/')
browser_evaluate(function='() => document.querySelector(".pql-sidebar-toggle") && getComputedStyle(document.querySelector(".pql-sidebar-toggle")).display') # expect "none"

# Pass C — desktop
browser_resize(1280, 800)
browser_navigate('http://127.0.0.1:8000/jobs')
browser_evaluate(function='() => !!document.querySelector(".pql-list-sort-mobile[style*=\"display: none\"]") || getComputedStyle(document.querySelector(".pql-list-sort-mobile")).display') # expect "none"
```

## Found bugs

_No bugs surfaced on the replay (2026-04-17, commit
pending, Playwright MCP at 375 × 812 / 768 × 1024 / 1280 × 800
against the `docker-compose.e2e.yml` stack). Verified
end-to-end:_

- _At **375 px**: the top navbar collapses to hamburger + brand +
 search-icon only (`.pql-topbar-nav` computed `display: none`,
 `.pql-cmdk-trigger` hidden, `.pql-sidebar-toggle` visible).
 Clicking the hamburger opens the `offcanvas-md` drawer with a
 CATALOG section on top and a NAVIGATION footer listing
 Federation / Notebook / Workspace / Jobs / Dashboards / Admin.
 Esc closes the drawer. List tables on `/jobs`, `/catalogs/demo`,
 `/catalogs/demo/schemas/sales`, and
 `/catalogs/demo/schemas/sales/tables/orders` collapse into
 label/value stacks (`td` `display: flex`, `::before` resolves
 `attr(data-label)`). The Sort-by dropdown appears
 above the `/jobs` table with every sortable header surfaced as
 two options (asc / desc). The `/notebook` page shows the
 "JupyterLab is optimised for desktop" notice above a still-
 functional iframe._
- _At **768 px**: the hamburger hides, the Cmd+K label + keycap
 is back, the top-nav links reappear, the list-table rows flip
 to `display: table-cell`, the mobile sort dropdown is hidden
 (`d-sm-none`), and the Jupyter mobile notice is gone._
- _At **1280 px**: no mobile CSS leaks — `/jobs` renders with
 the full row layout + sortable headers; the sidebar
 is a sticky two-column shell; the navbar shows the full
 Federation / Notebook / Workspace / Jobs / Dashboards / Admin
 strip._
