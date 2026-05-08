# Phase 59 — Comprehensive UX Tour Audit Findings (consolidated)

Generated 2026-05-08, post Phase 58 close.

**Method:** Headed Playwright tour through 8 thematic surface groups
(`/tmp/pql_ux_tour/tour.js`), 65 desktop screenshots at 1440×900,
zero console-errors, zero 5xx during tour. Per-theme review with
CONTENT / STRUCTURAL / DESIGN tagging matching Phase 56.1 / 57.1
conventions.

**Scope:** desktop-first (mobile out-of-scope per user pick); empty-
states are valid surfaces and bewertet in-place; deep-links into
surfaces requiring seeded data (jobs, dashboards, models, agent
reviews) reach the empty-state only.

**Output gate:** CONTENT + STRUCTURAL findings fold into Phase 59
sub-sprints (8 cross-cutting patterns identified, see Section 3).
DESIGN findings deferred Phase 60+ unless bundled into a pattern
sprint.

**Screenshots:** `docs/internal/phase59_screenshots/0N_<theme>/*.png`.

---

## Section 1 — Surface Coverage

| Theme | Folder | Screenshots | Findings | Tag mix (C/S/D) |
|---|---|---:|---:|---|
| 1 Auth & Landing | `01_auth_landing/` | 6 | 7 | 2 / 4 / 1 |
| 2 Catalog Browse | `02_catalog_browse/` | 11 | 8 | 2 / 4 / 2 |
| 3 SQL & Queries | `03_sql_queries/` | 7 | 8 | 3 / 4 / 1 |
| 4 Runs & Lineage | `04_runs_lineage/` | 9 | 10 | 3 / 6 / 1 |
| 5 Branches & Rollback | `05_branches_rollback/` | 4 | 8 | 2 / 4 / 2 |
| 6 Agents · Jobs · Models | `06_agents_jobs_models/` | 6 | 9 | 4 / 4 / 1 |
| 7 Audit Cockpit | `07_audit_cockpit/` | 8 | 10 | 3 / 5 / 2 |
| 8 Admin & Federation | `08_admin_federation/` | 14 | 11 | 4 / 6 / 1 |
| **Σ** | — | **65** | **71** | **23 / 37 / 11** |

C = CONTENT (text/label rewrite). S = STRUCTURAL (layout/component
re-arrangement). D = DESIGN (page-level redesign / new component).

---

## Section 2 — Console + 5xx Triage

- **Zero browser-console errors** across 65 navigated surfaces. No
  Alpine quoting bug like BUG-64-01, no HTMX TypeError like
  BUG-37-04.
- **Zero 5xx** in `docker compose logs pointlessql` during the tour.
- 1 expected `[NAV] /admin/audit/export: Download is starting` —
  endpoint is a file download, not HTML (by design).
- Net read: the UI is runtime-clean. All Phase-59 findings are
  UX-quality issues, **not bugs**.

---

## Section 3 — Cross-Cutting Patterns (Phase 59 Sub-Sprint Candidates)

The 71 per-theme findings cluster into 8 patterns. Each pattern is a
candidate sub-sprint with concrete scope. Priority ordering by
impact × effort:

### Pattern P-1 — Bootstrap tabs without URL state (DESIGN/cross)

`?tab=…` URL-param ignored on table-detail, run-detail (and likely
model-detail, agent-review-detail). Bookmarks break, browser-back
broken, audit-cockpit deep-link drilling broken. Affected templates
(observed): `table.html`, `run_view.html`. Likely also affected:
`model.html`, `agent_review_detail.html`, `dashboard_detail.html`,
`job_detail.html`. **Fix:** global Alpine helper that on
`DOMContentLoaded` reads `?tab=` and calls `bsTab.show()`, plus
listens to `shown.bs.tab` to mirror back via
`history.replaceState`. One sprint, one helper, ~6 templates.

### Pattern P-2 — Auth/error pages inherit full app chrome (DESIGN, user-confirmed)

Login, register, 4xx/5xx pages render the icon-rail sidebar +
top-bar Search + Admin-dropdown — all dead affordances pre-auth /
post-error. The 429 rate-limit page renders as bare HTML
(`<h1>429 — Too many attempts</h1>`) without any layout at all.
**Fix:** new `_layouts/auth_chromeless.html`; migrate
`pages/login.html`, `pages/register.html`, `pages/403.html`,
`pages/404.html`, `pages/500.html`; add new `pages/429.html` +
wire the rate-limit middleware to render it. Memory:
[`feedback_auth_pages_chromeless.md`](../../../.claude/projects/-home-flo-git-PointlesSQL/memory/feedback_auth_pages_chromeless.md).

### Pattern P-3 — Icon-rail top-items mis-mapping (STRUCTURAL)

Daily-driver surfaces hide as Admin sub-pages:
- `/audit/*` (Audit-Reviewer-Persona daily) under `ADMIN`.
- `/agent-reviews` (Phase 19 agent-loops) under `ADMIN`.
- `FEDERATION` top-item highlights for `/connections` (federation),
  `/credentials`, `/external-locations`, **and** `/volumes` (UC
  storage), **and** `/dbt` (pipeline tool) — three distinct
  concepts, one icon-rail slot.

**Fix:** new top-level icon-rail items `AUDIT` (with
`bi-shield-check`, sub-tabs Inbox/Search/By-table/By-query/By-run)
and `REVIEWS` (Phase-19 reviews) between `ALERTS` and `PRODUCTS`.
Rename `FEDERATION` → `CATALOG`; add separate `FEDERATE`
icon-rail-item or fold federation under `CATALOG` sub-tab. `DBT`
already has its own slot, leave alone.

### Pattern P-4 — Sidebar sub-pane inconsistency (STRUCTURAL)

Sub-pane between icon-rail and main content is excellent on some
pages, mediocre on others:
- **Best**: `/jobs` "Create one via the + New job button on /jobs
  **or with the agent schedule_job tool**" — dual-mode hint.
- **Mediocre**: `/dashboards` "No dashboards yet." (no agent-tool
  reference).
- **Redundant**: `/alerts` sidebar repeats the empty-state
  helper-text.
- **Off-context**: `/connections`+`/volumes`+`/dbt` share the
  Catalog-tree sub-pane (P-3 root cause).

**Fix:** sweep all sub-pane helper-texts to dual-mode (UI path +
agent-tool path); deduplicate against main empty-state; per-page
context-correct sub-pane.

### Pattern P-5 — Empty-state quality disparity (CONTENT)

**Best-in-class** (replicate verbatim):
- `/audit/search` Tokenizer explanation ("`main.silver.orders`
  matches `silver`").
- `/ml` MLflow setup-instruction (3 numbered install steps).
- `/dbt` dbt-docs setup-instruction (4 numbered steps).
- Run-detail anomaly banner ("CRITICAL — rejects at 50, no
  baseline yet — first observation in window. Drill into
  cockpit").

**Below-bar** (rewrite):
- `/branches` empty-list-with-default-Active-filter shows zero
  visual hint that the Promoted-branch in sidebar is filtered out.
- `/volumes` "Create through the soyuz-catalog API or the UC CLI"
  — refers to two external tools, no in-app path.
- `/models` empty-state mentions "Hermes plugin" / "soyuz UC-OSS"
  — three unknown tokens for newcomer.

**Fix:** sweep empty-states; require each to contain UI path AND
agent-tool path; for OSS-distributed pages add Docker-specific
override hint.

### Pattern P-6 — Filter-row density at desktop width (STRUCTURAL)

`/audit/inbox` (6 fields), `/queries` (3 fields), `/runs` (multiple
fields) — filter rows tight at 1440px, overflow-prone at narrower
widths. **Fix:** introduce a `_macros/filter_collapsible.html` —
collapsed shows summary pill ("Filter: warn or worse · day · since
2026-04-25"), expand button reveals all fields. Reuse across all
filter-bearing list pages.

### Pattern P-7 — Internal DB jargon leaked to UI (CONTENT)

Column names and DB-internal field names visible in user-facing
text:
- `/queries` filter "Read kind" (DB column `read_kind`) → "Source".
- `/audit/by-table` description: "tables_touched" / "written" /
  "read" → "Touched / Wrote / Read".
- `/admin/system-info` reference "Phase 29.3" — internal jargon.
- `/queries` SQL-error body contains raw ANSI escape-codes
  (`\x1b[4m...\x1b[0m`) from DuckDB.

**Fix:** one CONTENT-sweep sprint, all surfaces; plus
`pointlessql/services/sql_execute.py` ANSI-strip regex on
caught DuckDB exceptions.

### Pattern P-8 — Logic inconsistencies / minor bugs (CONTENT/STRUCTURAL)

- Run-Overview Source-card header `SHA-256: (no source captured)`
  *followed by* the actually captured source `print('seed')`
  (`run_view.html`: conditional template logic missing).
- `/branches` default-filter `Active` shows 0 results while sidebar
  shows 1 Promoted branch — inconsistent state.
- `/admin/cdf-subscriptions` description has German typo
  "Pull-modell" / "push-modell" → "model".
- Lineage-tab on table-detail shows `UPSTREAM Depth 0:
  demo.sales.customers` AND `DOWNSTREAM Depth 0:
  demo.sales.customers` (the self-node twice) when no edges exist.

**Fix:** one bug-cleanup sprint, all isolated, each a one-line fix.

---

## Section 4 — Per-Theme Findings

### Theme 1 — Auth & Landing (7 findings)

Screenshots: `01_auth_landing/{01_login_empty,02_login_filled,02b_login_error,03_home_dashboard,04_profile,99_404_with_full_chrome}.png`.

- **[STRUCTURAL → P-2]** `login.html`: Login-Card mittig auf
  Großer Leerfläche; globale Top-Nav (Logo + Search + Theme-Toggle)
  sichtbar — Search ist pre-auth eine tote Affordance.
- **[CONTENT → P-2]** 429-Rate-Limit-Page rendert als bare
  HTML-string ohne Card-Styling. Login-Page zeigt hingegen
  Bootstrap-Alert-Box korrekt.
- **[STRUCTURAL]** Home: Anomaly-Banner "3 metrics above 2σ
  baseline today" + "Welcome, Admin" Heading sind 2 stacked
  alerts; Audit-Banner inline neben Welcome wäre dichter.
- **[STRUCTURAL]** Home "Quick actions" gruppiert Navigation-CTAs
  (Open notebook / View jobs / View dashboards) mit einem
  Write-Action ("Create foreign catalog") in einer Card.
  Inkonsistente Action-Ladung.
- **[CONTENT]** Empty-States ("No job runs in the last 7 days")
  haben Recovery-Hint aber keinen Click-Through-CTA. Sollte
  "Browse jobs →" oder "Create job" inline sein.
- **[DESIGN → P-2]** `/auth/me` zeigt **rohes JSON**
  (`{id:1,email:admin@pql.test,…}`) statt eines gerenderten
  Profile-Pages. Kein `profile.html` Template existiert.
- **[STRUCTURAL]** Home rechte Spalte "Recent catalogs" Card —
  bei ≥1 Catalog redundant zur linken Sidebar-Tree (gleicher
  Inhalt 2× nebeneinander).

### Theme 2 — Catalog Browse (8 findings)

Screenshots: `02_catalog_browse/0{1..10}_*.png` (Home, sidebar
search, catalog detail, schema detail, table 6 tabs).

- **[STRUCTURAL]** Table-Detail Tabs sind 6: Overview / Preview /
  Columns / Lineage / Tags / Permissions — KEIN History / Audit /
  Time-travel Tab wie Phase-17.4-Plan suggest. Diese 3 Surfaces
  als separate Routes (`/audit/by-table/<fqn>`, `?tab=time-travel`)
  fragmentiert. **Fix:** prüfen ob `audit_by_table.html` als 7.
  Tab `Audit` integriert werden kann.
- **[DESIGN]** Lineage-Tab zeigt **keine Cytoscape-DAG** sondern
  ASCII-Liste mit "UPSTREAM Depth 0" / "DOWNSTREAM Depth 0".
  Phase 17.3 lazy-cytoscape gilt nur für `/runs/<id>?tab=graph`.
  **Fix:** Cytoscape-DAG hier auch (Pattern reuse), Toggle "List
  view / Graph view" für Multi-Hop-Lineage.
- **[CONTENT → P-8]** Lineage-Tab Output-Bug: bei 0-edge-Tabellen
  werden UPSTREAM und DOWNSTREAM beide mit dem Self-Node bei
  Depth 0 angezeigt (`demo.sales.customers` 2× rendered). Empty-
  State sollte "No upstream lineage recorded yet" / "No
  downstream consumers yet" sein.
- **[STRUCTURAL]** Sidebar "RECENT" rendert
  `customers · sales.demo` rechts-aligned — `<schema>.<catalog>`
  rückwärts zu `<catalog>.<schema>`. Verwirrend.
- **[CONTENT]** "Runs that touched this table" Button hat
  Clock-Icon (`bi-clock`) statt Run/List-Icon. Clock impliziert
  History/Time, der Button öffnet eine Liste von Runs.
- **[STRUCTURAL]** Catalog-Detail Card-Stack: Metadata → Schemas
  → Tags → Permissions → Properties — 5 Cards gleichgewichtet
  ohne visuelle Hierarchie. "Schemas" sollte prominenter sein
  (Kern-Action).
- **[DESIGN → P-1]** Bootstrap-Tabs auf Table-Detail haben keinen
  URL-State — `?tab=lineage` ignoriert. Bookmarks/Back broken.
- **[CONTENT → P-3]** Sidebar `FEDERATION` Top-Item: Rail-Item
  ist die App-Home (Catalog-Browser), nicht Federation. Rename
  zu `CATALOG`.

### Theme 3 — SQL & Queries (8 findings)

Screenshots: `03_sql_queries/{01_sql_editor_empty, 02_sql_editor_typing, 03_sql_results, 04_sql_error, 05_queries_grid, 06_queries_filtered, 07_queries_no_drawer_present}.png`.

- **[CONTENT → P-7]** SQL-Error-Display zeigt **rohe ANSI-Escape-
  Codes** im Body: `[4m*[0m`. DuckDB output enthält Terminal-
  Farb-Codes die unstripped durchrutschen. **Fix:**
  `pointlessql/services/sql_execute.py` ANSI-Stripping
  (`re.sub(r'\x1b\[[0-9;]*m', '', error_msg)`).
- **[STRUCTURAL]** SQL-Editor Empty-State: leerer schwarzer
  Editor-Block ohne Placeholder. **Fix:** subtile Placeholder
  "-- Type SQL here. Use Cmd+Enter to run." (CM6 placeholder-
  extension); ODER Sample-Snippet-Button-Row.
- **[CONTENT → P-7]** Filter-Dropdown-Labels sind Jargon: "Read
  kind" / "Status" / "Window". **Fix:** "Source" / "Outcome" /
  "Time range".
- **[STRUCTURAL]** `/queries` Cards rendern Comments-only SQL
  (`-- audit_api: …`) als Body-Content; bei 5/6 Cards einzig
  sichtbarer Inhalt. **Fix:** Comment-Zeilen am SQL-Anfang
  dimmen, erste non-comment-Zeile prominent.
- **[STRUCTURAL]** Editor-Sidebar-SubTabs "Editor / History" mit
  Helper-Text "Saved queries appear in the editor's right-hand
  drawer." — Helper-Text gehört zur rechten Saved-Queries-Pane,
  nicht zur History-Tab.
- **[DESIGN]** "Saved queries" rechte Pane bleibt meist leer und
  nimmt 25% Editor-Breite. **Fix:** als Slide-out-Drawer
  (Phase 56.8 detail_drawer pattern), Editor 100% Breite default.
- **[CONTENT]** "Failed in 47ms" rechts-oben gut. Pendant fehlt
  bei Erfolg ("Succeeded in 12ms · 5 rows"). Symmetrisch machen.
- **[STRUCTURAL → P-6]** `/queries` Filter-Bar (3 Dropdowns + Apply
  + Showing-Counter) tight. Empty-Filter-Result-State (0 rows)
  hat keinen prominenten Hint.

### Theme 4 — Runs & Lineage (10 findings)

Screenshots: `04_runs_lineage/{01_runs_list, 02_runs_filter, 03_run_overview, 04_run_operations (= overview, tab-bug), 05_run_graph (= overview, tab-bug), 06_run_audit (= overview, tab-bug), 07_run_diff, 09_column_trace}.png`.

- **[STRUCTURAL → P-1]** Tab-URL-State-Bug: `?tab=operations|graph
  |audit` führt alle zur Overview-View. Replicates table-detail
  bug. Cross-cutting fix needed.
- **[STRUCTURAL]** Run-Overview hat 4 Top-Tabs UND 3 Sub-Tabs in
  Overview (Source/Cells/Events) = 4×3 Navigation-Grid. Cognitive
  overload. **Fix:** Source/Cells/Events als sectioned Cards auf
  Overview-Body inline, keine Sub-Tabs.
- **[CONTENT → P-8]** Source-Card Header `SHA-256: (no source
  captured)` gefolgt von der TATSÄCHLICH erfassten Source
  `print('seed')`. Logik-Inkonsistenz. **Fix:** `run_view.html`
  conditional template.
- **[STRUCTURAL]** Runs-List Columns "Anomaly" + "Cost est." sind
  in alle 6 Test-Rows mit `—` gefüllt = 25% horizontal-real-
  estate verschwendet. **Fix:** Phase-56.4 collapse-empty-column
  pattern, oder Anomaly als Badge in Status-Spalte, Cost est.
  als Tooltip auf ID.
- **[CONTENT]** Run-Detail Heading `nb.py · succeeded`-Badge —
  Run-ID nur im Breadcrumb. **Fix:** Heading prominenter "Run
  #8ebb2e9f · nb.py" + Status-Badge rechts.
- **[CONTENT → P-4]** Sidebar "RECENT" auf `/runs` ist 100%
  redundant zur Haupttabelle (gleiche 6 IDs, gleiche Zeit).
  **Fix:** Sidebar-RECENT nur auf NICHT-/runs-Pages.
- **[STRUCTURAL]** Run-Diff KPI-Cards: 4 Cards selbe visuelle
  Schwere, aber 3 zeigen "no change" und 1 zeigt "+244". **Fix:**
  "no change" Cards opacity 0.5.
- **[STRUCTURAL]** Run-Diff Operations-Liste 6 Sub-Tabs (Operations
  6 / Lineage 4 / Rejects 0 / Tool calls 0 / Cells / Column
  lineage 21) — 2 mit `0` count sind leere Tabs. **Fix:** Tab
  disable/hide wenn count=0.
- **[CONTENT]** Column-Trace Empty-State Yellow-Banner Text
  exzellent formuliert ("Either the column was written without
  declaring an upstream UC source… or the column predates…")
  aber zu klein im body. Banner direkt unter "Walkback depth"
  Card mit höherer visueller Hierarchie.
- **[CONTENT]** Anomaly-Banner über Run-Heading "CRITICAL —
  rejects at 50 (no baseline yet — first observation in window)
  · Drill into cockpit" — best-in-class. Replizieren auf andere
  Surfaces (P-5).

### Theme 5 — Branches & Rollback (8 findings)

Screenshots: `05_branches_rollback/{01_branches_list, 02_branch_detail, 02_branches_empty_state, 05_rollback_card_on_run}.png`.

- **[STRUCTURAL+CONTENT → P-8]** `/branches` Default-Filter-Bug:
  Sidebar zeigt 1 Promoted-Branch, Hauptliste leer (filtert
  default `Active`). Inkonsistent. **Fix:** Default `All` oder
  Sidebar synchron filtern.
- **[DESIGN]** Branch-Liste hat keinen sichtbaren Empty-State
  bei 0 Filter-Treffern. **Fix:** Empty-State Card "No active
  branches. Switch to **Promoted** (1) to see…".
- **[STRUCTURAL]** Filter-Pills "Active / Promoted / Discarded"
  inline mit Search ohne Label. **Fix:** "Filter:" Label oder
  als Tab-Strip.
- **[CONTENT]** Sidebar-Section-Headings "PROMOTED" ohne Count.
  **Fix:** "PROMOTED (1)" / "ACTIVE (0)" / "DISCARDED (0)".
- **[STRUCTURAL]** Branch-Detail (`demo_ml.gold`) hat keinen
  Promote/Discard/Preview-Action-Button bei promoted Branch —
  was passiert wenn User die Aktion ändern will? **Fix:**
  "Actions"-Card im Header.
- **[DESIGN]** Run-Detail Overview hat keinen Rollback-Card —
  Phase 16 promised admin-gated rollback-card auf run-detail.
  Möglicherweise nur im `Audit`-Tab sichtbar (P-1). **Fix:**
  prüfen + ensure visibility.
- **[CONTENT]** Branch-Detail "Created by run" gelinkt; Reverse-
  Link auf Run-Detail "Branches created in this run" fehlt.
- **[STRUCTURAL]** "Audit log · No audit-log entries yet." auf
  promoted Branch widersprüchlich — Promotion IST ein Audit-
  Event und sollte hier erscheinen.

### Theme 6 — Agents · Jobs · Dashboards · Models (9 findings)

Screenshots: `06_agents_jobs_models/{01_agent_reviews, 03_jobs_list, 05_dashboards_list, 07_models_list, 11_mlflow_embed, 12_data_products}.png`.

- **[STRUCTURAL → P-3]** `/agent-reviews` unter "ADMIN" Icon-Rail.
  Phase 19 hat Agent-Reviews als daily-driver eingeführt — gehört
  nicht in Admin. **Fix:** eigener Icon-Rail-Item zwischen ALERTS
  und PRODUCTS.
- **[CONTENT → P-5]** ML-Empty-State exzellent ("Install pip
  install pointlessql[ml]…"), aber Docker-Path fehlt. **Fix:**
  "**Docker:** add `POINTLESSQL_MLFLOW_ENABLED=1` to
  `docker-compose.yml`".
- **[STRUCTURAL]** Models-Filter-Row "Catalog [Dropdown] / Schema
  [Textfield]" inkonsistent. **Fix:** Schema als Dropdown,
  populated dynamisch nach Catalog.
- **[CONTENT]** "PRODUCTS" Icon-Rail Label + `bi-briefcase` Icon
  mehrdeutig. Page-heading sagt "Data Products". **Fix:** Label
  "DATA PRODUCTS"; Icon `bi-box-seam`.
- **[STRUCTURAL → P-4]** Sub-Pane links inkonsistent: Jobs-Helper
  exzellent dual-mode, Dashboards-Helper minimal, Alerts-Helper
  redundant.
- **[CONTENT]** "Registered Models" empty-state mention "Hermes
  plugin oder mlflow.register_model() against the soyuz UC-OSS
  endpoint" — 3 unbekannte Begriffe für Newcomer. **Fix:** Glossar
  oder Docs-Link.
- **[STRUCTURAL]** Detail-Surfaces nicht erreicht (Jobs/
  Dashboards/Models/Reviews alle empty in seed). Coverage-Gap.
  **Recommendation:** Seed-script für Demo-State erweitern.
- **[CONTENT → P-5]** Job-Sidebar-Helper-Text "Create one via the
  + New job button **on /jobs** **or with the agent
  schedule_job tool**" — best-in-class dual-mode-Hinting.
  Replizieren.
- **[DESIGN → P-3]** `/agent-reviews` öffnet innerhalb
  Admin-Sidebar — User kann nicht zu Run-Detail oder Audit-
  Cockpit zurückspringen ohne Icon-Rail-Click. Phase 19 war für
  agent-loops, nicht Admin-Inspection.

### Theme 7 — Audit Cockpit (10 findings)

Screenshots: `07_audit_cockpit/{01_audit_inbox, 02_audit_search, 03_audit_search_results, 04_audit_by_table, 05_audit_queries, 06_audit_anomalies, 07_admin_audit, 09_alerts_list}.png`.

- **[DESIGN → P-3]** **`/audit/*` ist unter ADMIN icon-rail
  einsortiert**. Audit-Cockpit ist Daily-Driver — nicht Admin.
  **Fix:** Top-Level-Icon-Rail-Item `AUDIT`.
- **[STRUCTURAL → P-6]** Audit-Inbox-Filter-Row 6 Inputs
  nebeneinander. **Fix:** Filter als Collapsible.
- **[CONTENT → P-7]** `/audit/by-table` Description verwendet
  DB-interne Begriffe: "tables_touched" / "written" / "read" /
  "query_history".
- **[STRUCTURAL]** `/audit/search` zeigt Result-Table-Header VOR
  Query-Eingabe. **Fix:** Result-Table erst nach erstem Submit.
- **[CONTENT → P-5]** `/audit/search` Intro-Copy best-in-class:
  "Free-text search across runs, ops, queries, tool calls, and
  audit log. Tokenizer keeps . / _ / - as separators…" —
  Goldstandard. Replizieren.
- **[STRUCTURAL]** `/admin/audit` Audit-Log-Tabelle hat 2 Badges
  pro Row (Role + Action), Role-Spalte 12% Breite mit dünner
  Information. **Fix:** Role als Inline-Tag in User-Spalte.
- **[STRUCTURAL → P-4]** `/alerts` Sidebar-Helper redundant zu
  Empty-State. **Fix:** entfernen oder zu Docs-Link.
- **[STRUCTURAL]** `/audit/inbox` Footer "2 of 2 breach(es)" mit
  Metric-Worten ("rejects, errored_ops") nicht klickbar. **Fix:**
  Metric-Worte als Filter-Pills.
- **[CONTENT]** Audit-Cockpit-Inbox Heading "Audit cockpit · what
  needs attention" — STARK formuliert. Behalten.
- **[DESIGN → P-3]** Audit-Cockpit / Audit-Search / Audit-By-
  Table / Audit-Queries als 4 separate Pages. Konsistenter:
  **eine** Page `/audit` mit Tab-Strip. Phase 18.6+ dachte das
  schon halb mit. Vollziehen.

### Theme 8 — Admin & Federation (11 findings)

Screenshots: `08_admin_federation/{01_admin_landing, 02_admin_workspaces, 03_admin_audit_sinks, 04_admin_review_destinations, 05_admin_api_keys, 06_admin_system_info, 07_admin_external_writes, 08_admin_cdf_subs, 09_federation_connections, 09b_connection_detail, 10_federation_credentials, 11_federation_external_locs, 12_volumes, 14_dbt}.png`.

- **[STRUCTURAL → P-3]** Icon-Rail "FEDERATION" Top-Item mehrfach
  belegt: `/connections`/`/credentials`/`/external-locations`
  (federation) UND `/volumes` (UC Storage) UND `/dbt` (Pipeline).
  **Fix:** Top-Item rename `CATALOG`; eigene Icon-Rail-Items für
  Federation (`bi-broadcast-pin`) und DBT existiert schon.
- **[CONTENT → P-8]** `/admin` CDF-subscriptions Beschreibung
  enthält **deutsche Typos**: "Pull-modell" / "push-modell".
  **Fix:** s/modell/model/g in
  `frontend/templates/pages/admin_index.html`.
- **[CONTENT → P-7]** `/admin/system-info` OIDC-Card erwähnt
  "Phase 29.3" — internal-jargon. **Fix:** entfernen.
- **[STRUCTURAL]** Review-destinations Form-Field "Workspace
  filter (optional) [☐ default]" Checkbox-Liste statt Multi-
  Select-Dropdown. Bei 5+ Workspaces hässliches Stacking. **Fix:**
  Multi-Select-Dropdown.
- **[STRUCTURAL → P-5]** "What is this page?" Collapsible auf
  `/admin/review-destinations` best-in-class help-pattern.
  Replikation auf den anderen 7 Admin-Sub-Pages.
- **[CONTENT]** Admin-Landing Tagline "Tenant-wide administrative
  tools. Workspace-local settings live inside each workspace at
  `/workspaces/<slug>`." — exzellent. Behalten.
- **[STRUCTURAL]** `/dbt` 3 tabs (Pipeline docs / Recent runs /
  Test failures) sichtbar bevor dbt überhaupt läuft. **Fix:**
  Tabs disabled-State bis dbt-subprocess läuft.
- **[STRUCTURAL]** Connections-Liste mit 1 Row in Riesentabelle
  wirkt verloren. **Fix:** wenn nur 1 Row, Empty-State-Hero-Card
  mit Connection-Details statt Tabelle.
- **[CONTENT]** `/admin` Workspaces-Card "Slugs are immutable
  once assigned." tucked-away. **Fix:** auf
  `/admin/workspaces` Modal "Create workspace" prominent als
  Inline-Helper.
- **[STRUCTURAL → P-5]** Volumes Empty-State verweist auf 2
  externe Tools, kein In-App-Create. **Fix:** UI-Create-Form
  ODER konkretere "Docker:" / "Python:" Snippets.
- **[DESIGN]** `/admin` Cards = 9 sub-pages alle gleichgewichtet,
  aber "External writes [2]" hat einzige Action-Pending-Badge.
  **Fix:** Card-Hierarchie — Action-Required Cards zuerst,
  Configuration Cards in zweiter Reihe ausgeblasst.

---

## Section 5 — Phase 59 Sub-Sprint Skizzen

Ableitung der 8 Patterns auf konkrete Sub-Sprints (in Priority-
Order; effort ist grobe Schätzung):

| Sprint | Pattern | Scope | Effort | Notes |
|---|---|---|---|---|
| 59.1 | P-7 (Jargon sweep) + P-8 (logic bugs + ANSI strip) | CONTENT-only sweep + 1 service fix | ~½ day | "Read kind" → "Source", `tables_touched` → "Touched", strip ANSI in `sql_execute.py`, fix Lineage-tab self-node duplication, fix branches default-filter, fix CDF "modell" → "model", fix Source-card conditional |
| 59.2 | P-1 (Tab URL state) | global Alpine helper + 6 templates | 1 day | One helper, all tab-bearing pages get bookmarkable URLs |
| 59.3 | P-2 (Auth chromeless layout) | new `_auth.html` layout + 5 template migrations + new 429 template | 1 day | User-confirmed in feedback memory |
| 59.4 | P-6 (Filter collapsible) | new `_macros/filter_collapsible.html` + 3-4 page integrations | ½ day | Audit-inbox / queries / runs / audit-search filter rows |
| 59.5 | P-3 (Icon-rail re-mapping) | new top-level AUDIT + REVIEWS items, FEDERATION rename → CATALOG | 1 day | Cross-cutting; touches `icon_rail.html` + many sub-page sidebars |
| 59.6 | P-4 (Sub-pane sweep) | dual-mode helper-text on all sub-panes; deduplicate redundant ones | ½ day | Replicates Jobs-pattern across the board |
| 59.7 | P-5 (Empty-state quality sweep) | rewrite low-quality empty-states; replicate best-in-class patterns | ½-1 day | Branches / volumes / models / agent-reviews etc. |
| 59.8 | DESIGN-deferred (Phase 60+) | bigger redesigns: cytoscape on table-lineage, Audit unified `/audit` page with tab-strip, Run-Overview sub-tabs flatten | — | Not in Phase 59 scope; defer |
| 59.9 | Phase close + memory | ROADMAP/CHANGELOG, memory entry, push gate | ½ day | Standard close pattern |

**Total Phase 59 effort estimate:** 5-6 working days for 7 sprints
(59.1 → 59.7) plus 59.9 close. DESIGN findings (11 total) parked
for Phase 60.

**Anti-Goals Phase 59:**
- Keine neuen UI-Features bauen — pure quality sweep.
- Keine Phase-17/18-Reopens — Rail+Context-Panel-Layout strukturell
  unangetastet außer Icon-Rail Top-Item-Liste (P-3).
- Keine cytoscape-Integration auf table-detail (DESIGN, deferred).
- Keine Modal/Drawer-Refactors außer Reuse existierender macros.
- Mobile-Audit out-of-scope (Desktop-first per User-Pick).

---

## Appendix A — Reproduzierbarkeit

Tour neu fahren:

```bash
# Container muss laufen
docker compose ps pointlessql

# Login als admin@pql.test / password123
# (Falls 429: ~150s warten oder rate-limit-counter zurücksetzen)

# Tour-Skripte sind in /tmp/pql_ux_tour/{tour,tour2,tour3b,tour4}.js
# (gelöscht nach diesem Phase-Close — re-create from this section
#  if needed for Phase 60+)
cd /tmp/pql_ux_tour
node tour.js          # Wave 1: 8 themes
node tour3b.js        # Supplementary: catalog-detail with correct URL
node tour4.js         # Final: explicit tab-clicks for Bootstrap tabs
```

Tour-Pattern (für Phase 60+):

- Headed Firefox 1440×900 (`{ headless: false }`).
- Login einmal, `context.storageState` persistieren, alle Themen
  über denselben Auth-State.
- Console + pageerror listener → `_console.log`.
- Soft-fail per Surface (`safeGoto` mit try/catch + `errors.push`).
- Bootstrap-Tabs **klicken** statt URL-Param (P-1 nicht gefixt).
- Entity-Discovery via `page.evaluate(fetch(...))` — beachte API-
  shapes:
  - `/api/catalogs` → flaches Array
  - `/api/branches` → `{branches: [{branch_schema_fqn: ...}]}`
  - `/api/agent-reviews` → 405 GET; nutze `/api/agent-reviews/latest`

Rate-Limit-Vorsicht: 4-5 fehlgeschlagene Logins in <2min triggern
ein 149s Backoff auf der Login-Page.

## Appendix B — Verworfene Tour-Iterationen

`tour.js` (Wave 1) hatte 2 Bugs die zu Re-Captures führten:

1. **Wrong table-detail URL**: nutzte `/tables/<fqn>?tab=...`
   statt `/catalogs/<c>/schemas/<s>/tables/<t>?tab=...` →
   alle 6 Table-Tab-Screenshots waren 404-Pages. Eine 404 wurde
   als Evidence in `01_auth_landing/99_404_with_full_chrome.png`
   behalten (ironisch: 404 inherits volles App-Chrome — beweist
   Pattern P-2).
2. **Bootstrap tabs ignored URL `?tab=`**: alle Tab-Screenshots
   zeigten Default-Overview-View. Pattern P-1 — fix in 59.2.

`tour3.js` lief in 429-Rate-Limit nach 3 schnellen Login-
Versuchen. Workaround: Polling-Loop bis `/auth/login` POST 403
(CSRF-only) statt 429 zurückgibt.
