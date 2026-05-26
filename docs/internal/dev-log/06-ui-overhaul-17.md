---
title: "Cluster 06 — Phase 17 UI Overhaul (dev-log)"
audience: contributor
cluster_id: "06"
phases: "17"
closed: "2026-04-29"
---

# Cluster 06 — Phase 17 UI Overhaul (dev-log)

> Phase 17 UI Overhaul — icon-rail + context-panel + tab-aware run-detail + 6-tab table-detail. Five sub-sprints + 17.3.1/17.5.1 polish.

These entries were materialised from the pre-W3 ``CHANGELOG.md`` ``[Unreleased]`` block (Doc-Master-Plan W3, 2026-05-26).  They preserve the original phase-keyed narrative for contributors who want richer commit-level context than the auto-generated per-cluster CHANGELOG section provides.

---

> from CHANGELOG.md (bucket: **Closed**)

### Closed — Phase 17 polish: 17.3.1 + 17.5.1 (2026-04-29)

Two queued follow-ups land in one autonomous session.  17.6
(lineage trace sub-panes) stays queued — the ROADMAP-side
"defer until usage data" decision still holds.

* **17.3.1 — Lazy-load cytoscape on the Graph sub-tab.**  The
  three jsdelivr scripts (cytoscape ~280 KB + dagre ~50 KB +
  adapter) no longer ship on every ``/runs/{id}`` cold load.
  ``loadCytoscapeOnce()`` injects them on demand the first
  time the user activates the Graph sub-tab, gated on
  Bootstrap's ``shown.bs.tab``.  Promise-cached at module
  level; fail-soft on CDN block.
* **17.5.1 — Server-side tree search + DB-backed recents.**
  New ``recent_tables`` table (Alembic ``p6l8n0q3s5u7``)
  mirrors the Sprint-17.5 localStorage block in
  PointlesSQL's metadata DB so recents survive across
  devices.  ``GET /api/tree/search?q=`` walks the soyuz tree
  once and filters in-memory (capped@50) — significantly
  cheaper than shipping the full tree to a >1000-table
  browser.  Sidebar keeps localStorage as first-paint +
  no-auth fallback and overrides asynchronously for
  logged-in users.

Tests: 7 new (recents service).  Static gates clean.

> from CHANGELOG.md (bucket: **Closed**)

### Closed — Phase 17: UI Overhaul (2026-04-29)

Five sub-sprints in one autonomous session, closing the
post-Phase-15.7 honest-UX-assessment punch list (top navbar
overloaded, run-detail tabs creaking, lineage UI linear,
table-detail vertical wall, catalog browser scroll-wall).

What's now in place:

- **Two-column sidebar** (Sprint 17.1).  60 px icon-rail with
  one icon per top-level section + 240 px contextual panel
  that swaps based on `active_section`.  Top navbar drops the
  inline nav row (only brand + Cmd+K + user menu remain).
  Mobile drawer keeps `nav_links.html` as fallback.
- **Run-detail tab consolidation** (Sprint 17.2).  10 flat
  tabs → 4 top-tabs (Overview / Operations / Lineage / Audit)
  with nav-pill sub-tabs.  Rollback card moves into a "Danger
  zone" inside Operations; `unattributed_writes` lifts out of
  Operations into an External-writes sub-tab in Audit; an
  inline hash-listener keeps Sprint-18.1 cross-axis deeplinks
  working.
- **Lineage-DAG view** (Sprint 17.3).  New
  `services/lineage_graph_builder.py` + `GET
  /api/runs/{run_id}/graph` join `lineage_row_edges` and
  `lineage_column_map` into a flat `{nodes, edges}` payload.
  New Lineage / Graph sub-tab embeds a cytoscape.js + dagre
  canvas with click-a-column-highlights-upstream-and-
  downstream behaviour.  CDN-loaded, scoped to the run-detail
  page only.
- **Table-detail tab refactor** (Sprint 17.4).  `pages/
  table.html` collapses from a long vertical card stack into
  six tabs (Overview / Preview / Columns / Lineage / Tags /
  Permissions); card content + Alpine factories preserved
  verbatim.
- **Catalog-Browser search + recents** (Sprint 17.5).
  Debounced filter input above the catalog tree + a "Recent
  tables" block surfacing the last five
  `catalog.schema.table` visits via
  `localStorage['pql.recentTables']`.

Numbers:

- 5 sub-sprint commits + this closing commit on PointlesSQL.
- 1 new backend module
  (`services/lineage_graph_builder.py`).
- 1 new public API endpoint
  (`GET /api/runs/{run_id}/graph`).
- 5 new template partials / files (`icon_rail.html`,
  `context_panel.html`, `user_menu.html` + CSS files for
  icon-rail and context-panel +
  `frontend/js/components/lineage_dag.js`).
- 0 new database tables / Alembic migrations — the
  RecentTable persistence lane stays in localStorage; a
  DB-backed sibling is parked as a 17.5.1 follow-up.

What's deferred:

- `/api/tree/search` server-side endpoint for >1000-table
  tenants (Sprint 17.5.1).
- Lazy-load of the cytoscape bundle on Lineage-Graph
  sub-tab click (Sprint 17.3.1) — today the bundle ships
  with every run-detail page, ~280 KB cold-cache.
- Sub-tab content for the Lineage top-pane beyond Summary +
  Graph (Row trace / Column trace / Value changes are
  separate full pages today; making them sub-panes would be
  a Phase-17.6 follow-up if the page-flip overhead becomes
  painful).

### Added — Sprint 17.5: Catalog-Browser search + recents (2026-04-29)

`components/sidebar.html` gains a debounced filter input above
the catalog tree and a "Recent tables" block surfacing the
last five `catalog.schema.table` visits.

Frontend:

- New `query` + `recents` reactive state on the existing
  Alpine `catalogTree()` factory.
- Six new helpers (`tableVisible`, `schemaVisible`,
  `catalogVisible`, `isCatalogExpanded`, `isSchemaExpanded`,
  `filteredEmpty`) drive the filter — case-insensitive
  substring match, partial-match branches force-expand, no
  match shows a friendly empty-state.
- Recent tables come from a localStorage key
  (`pql.recentTables`) written by a small `base.html`
  inline script (sibling of the Sprint-32 recent-catalogs
  writer); the script also dispatches a
  `pql:recent-tables-changed` CustomEvent so an open
  sidebar updates without a hard reload.
- Recents are FQN-deduped, capped at 5, with a "Clear"
  button that wipes the list.

Backend: no changes — the existing `/api/tree` payload
already returns the catalog → schema → table hierarchy the
filter walks.

Deferred to Sprint 17.5.1: server-side
`/api/tree/search?q=` for tenants with >1000 tables, and a
DB-backed `RecentTable(user_id, table_full_name,
last_visited_at)` model for cross-device recents.

### Added — Sprint 17.4: Table-detail tab refactor (2026-04-29)

`pages/table.html` collapses from a single long vertical stack
into six top-level tabs.  No new functionality — this is a pure
layout reorganisation.

| Tab          | Contents                                          |
|--------------|---------------------------------------------------|
| Overview     | Metadata + Properties + PQL Snippet (copy)        |
| Preview      | `tablePreview()` Alpine card with version select  |
| Columns      | Columns table (+existing ≥20-col search) + Sprint-56 stats |
| Lineage      | `components/lineage_card.html` upstream/downstream graph |
| Tags         | `components/tags_editor.html`                     |
| Permissions  | `components/permissions_card.html` (effective-permissions toggle) |

What stayed:

- All Alpine factories (`tablePreview`, `tableStats`) and their
  inline `<script>` blocks — same `init()`, same fetch path,
  same Chart.js sparklines, same Sprint-20.3 version select.
- The Sprint-15.6 column-lineage badges next to each column
  name.
- The Sprint-30 effective-permissions toggle inside the
  Permissions card.
- Header (h1 + breadcrumbs), error alert path, and the
  `{% block extra_js %}` carrying `tableStats` continue to
  render unchanged.

What's deferred to a follow-up:

- Always-on column filter for any column count (today's
  threshold is ≥20).  The plan mentioned 50+ as the trigger;
  the existing 20+ behaviour is more aggressive and works
  fine, so no change for 17.4.
- Row history / sync history sub-tab — not currently surfaced
  on this page; would need a new endpoint to be useful.

### Added — Sprint 17.3: Lineage-DAG view (2026-04-29)

Third landing of Phase 17.  Adds a clickable graph view of the
combined row + column lineage for one run, sitting next to the
Sprint-17.2 Summary table inside the Lineage top-pane.

Backend:

- New `pointlessql/services/lineage_graph_builder.py` joins
  `lineage_row_edges` + `lineage_column_map` per `run_id`
  (and optional `op_id`) into a flat `{nodes, edges}` payload.
  One node per distinct table; one edge per
  `(source_table, target_table, op_id)` triple, with
  `transform_kinds`, `column_pairs`, and `row_edge_count`
  attached.
- New route `GET /api/runs/{run_id}/graph?op_id=...` in
  `runs_routes.py`, gated by `require_supervisor` (auditor or
  admin) — same scope ladder as the Sprint-19.1 audit-axis
  routes.

Frontend:

- New Lineage sub-tabs: Summary (the existing per-op edge
  table) and Graph (cytoscape canvas).  The Summary sub-pane
  keeps `id="tab-lineage"` so existing Sprint-18.1 op-row
  badges that link to `?op_id=N#tab-lineage` continue to land
  on the Summary view.
- New `frontend/js/components/lineage_dag.js` Alpine factory
  registered via `bootstrap.js`.  Loads the graph JSON, hands
  it to cytoscape with the dagre layout, and wires three
  highlight modes: node click (incident edges), edge click
  (side-panel column pairs), column click (every edge that
  touches that column — upstream + downstream simultaneously).
- cytoscape (3.30), dagre (0.8), cytoscape-dagre (2.5) from
  jsdelivr, loaded via a new `extra_js` block in
  `run_view.html` so the ~280 KB bundle hits only the
  run-detail page, not every authenticated route.
- Side-panel column-pair list is scrollable (max-height 280
  px) so wide aggregations stay tidy.

Behaviour:

- Empty-state when the run has no row edges or column-map
  rows: the canvas stays hidden and a friendly alert points
  at the PQL primitives that emit edges.
- `op_id` query parameter is honoured: when the user lands
  via the Sprint-18.1 cross-axis filter chip, the graph
  filters to that single op automatically.
- The `pre`-Sprint-15.6 case of "row edges but no column
  map" keeps surfacing as a node-to-node edge (annotated
  with the row count, no transform_kinds), so old runs are
  still rendered.

### Added — Sprint 17.2: Run-detail tab consolidation (2026-04-29)

`/runs/{id}` collapses from a single nav-tabs strip with 10 tabs
in one row into 4 top-level tabs with 11 nav-pill sub-tabs
distributed across them.  No backend or API changes — pure
template + Alpine surgery.

The new structure:

| Top-tab    | Sub-tabs                                          |
|------------|---------------------------------------------------|
| Overview   | Source · Cells · Events                           |
| Operations | Operations · Rejects · Queries · UC mutations     |
| Lineage    | Lineage summary (Sprint 17.3 will split into Row / Column / Value / Graph) |
| Audit      | Tool calls · Audit log · External writes (NEW)    |

What changed in `frontend/templates/pages/run_view.html`:

- Single `<ul class="nav nav-tabs">` strip + flat tab-content
  → 4-button top-tab strip + 4 top-panes, each carrying its own
  `<ul class="nav nav-pills">` for sub-tabs.
- The `unattributed_writes` alert that Sprint 13.7.5 surfaced
  inside the Operations tab is now its own *External writes*
  sub-pane in the Audit top-tab, with a friendly empty-state
  when no unattributed writes exist (so the sub-tab stays
  coherent when toggled).  The badge on the External-writes
  sub-tab carries the count.
- The Sprint 16.3 admin-only **Rollback** card moves from above
  the tab strip to the bottom of the Operations top-pane as a
  "Danger zone" card.  Same `rollbackPanel()` Alpine factory,
  same modal, same submit → /api/runs/{id}/rollback POST flow;
  only the location moves.
- A small inline hash-listener at the bottom of the template
  walks up the DOM from the targeted sub-pane and activates the
  parent top-tab too, so existing deeplinks like
  `/runs/{id}?op_id=N#tab-lineage` (Sprint 18.1 cross-axis
  drilldowns) keep landing on a visible pane.  Stale hashes
  fall back to the default sub-pane in Overview.
- Sprint 18.1's `op_id`-filter chip + Sprint 18.5's anomaly
  chip + the run-metadata / medallion-conformance / approval
  cards stay above the top-tab strip — outside the tab
  structure on purpose, so they remain visible regardless of
  which top-tab is active.

The 10 sub-pane IDs (`tab-cells`, `tab-ops`, …) and their
existing internal contents are preserved verbatim — only the
wrapping changes.  Sprint 18.1 cross-axis op-row badges that
link to `#tab-lineage` and `#tab-ops` therefore keep working
without edit.

### Added — Sprint 17.1: Two-column sidebar (2026-04-29)

First landing of Phase 17 (UI Overhaul).  The horizontal nav row
that crammed nine items into the topbar is replaced by a 60 px
icon-rail on the left and a 240 px contextual panel next to it.

What changed:

- New `frontend/templates/components/icon_rail.html` —
  vertical 60 px strip with one icon per top-level section
  (Federation / Runs / SQL / Workspace / Jobs / Alerts /
  Volumes / Dashboards + an admin-only Admin entry in the
  footer).  Active item is derived from a new `active_section`
  computed in `base.html` from the existing `active_page`.
- New `frontend/templates/components/context_panel.html` —
  240 px panel that dispatches by `active_section`: Federation
  reuses the existing catalog-tree (`components/sidebar.html`),
  Dashboards reuses the existing dashboards-tree, the seven
  remaining sections render a small static link list with a
  Cmd+K hint where useful.
- New `frontend/templates/components/user_menu.html` — current-
  user dropdown extracted out of `nav_links.html` so it can
  render standalone in the topbar (right side) at >= md.
- `frontend/templates/components/nav_links.html` is now
  drawer-only (< md, 768 px); the topbar drops its inline nav
  block.
- Mobile (< md) keeps the existing offcanvas drawer chrome but
  now carries: section panel + nav-links list + user menu, so
  phones have a single navigation surface (matches the new
  desktop layout in inverse order).
- New CSS `frontend/css/components/icon_rail.css` +
  `frontend/css/components/context_panel.css`; design tokens
  `--pql-icon-rail-width` (60 px) and `--pql-context-panel-width`
  (240 px) in `base.css`; `.pql-shell` grid is now
  `60 px 240 px 1fr` at >= md.

What stayed:

- Cmd+K command palette (Sprint 31/92) is unchanged.
- Notebook iframe page still uses `hide_sidebar=True` and
  fills the viewport — no rail or panel rendered.
- Login / register / error pages also use `hide_sidebar=True`,
  so the new chrome is never shown unauthenticated.
- The catalog-tree `<aside>` continues to ship its own
  `.border-end`; the new column also gets a wrapper border on
  `.pql-sidebar-shell` at >= md so non-tree section panels
  read as a column too.

> from CHANGELOG.md (bucket: **Changed**)

### Changed — Roadmap expansion: Phase 17-20 + Some-day rewrite (2026-04-27)

Strategic conversation post-15.7-close generated a substantial
roadmap extension covering the *non-capture* side of audit
infrastructure: navigation, exploration, governance UX,
forensics, distribution.  Previously the roadmap stopped at
Phase 16 (Rollback) with a vague Some-day block; it now reads
through Phase 20 with concrete sub-sprints.

> from CHANGELOG.md (bucket: **Changed**)

- **Phase 17 — UI Overhaul**: two-column sidebar, run-detail
  tabs consolidation (10→4), lineage-DAG view (cytoscape.js),
  table-detail entdichten, catalog-browser search/filter.
