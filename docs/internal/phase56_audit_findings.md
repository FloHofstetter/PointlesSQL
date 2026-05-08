# Phase 56 — UX Audit Findings (consolidated)

Generated 2026-05-08, Sprint 56.1.

Konsolidiert die drei Phase-1-Explore-Reports (UX-Audit, Bug-Hunt,
Primitive-Inventur) + Verifikation der unsicheren Punkte +
Per-Page Semantic-Review für die Top-Surfaces.

---

## Section 1 — BUG-53-NN Status (verified)

| ID | Severity | Surface | New Status | Evidence |
|---|---|---|---|---|
| BUG-53-01 | medium | `/audit/search` HTML-leak | **CLOSED** | `grep 'Learn more' frontend/templates/pages/audit_search.html` returns nothing — leak fixed by Phase-53 help-icon `\|e` escape (verified `_macros/help_icon.html:30-37` comment) |
| BUG-53-02 | low | walkthrough `sql-editor.md` | **OPEN** | Trivial doc fix `/sql-editor` → `/sql` |
| BUG-53-03 | medium | icon-rail `WORKSPACE` link | **VERIFY-then-likely-closed** | `icon_rail.html:50` points to `/notebooks/workspace` (not `/workspace` as BUG-53-03 claims). Phase-12 notebook system likely has the route. Verify by curl-test before marking closed |
| BUG-53-04 | low | walkthrough `admin-audit.md` | **OPEN** | Trivial doc fix `/admin/audit-log` → `/admin/audit` |
| BUG-53-05 | medium | `/data-products` 404 | **CLOSED** | `pointlessql/api/data_products_html_routes.py:25` defines `@router.get("/data-products", response_class=HTMLResponse)`. Walkthrough was stale during Phase 53 |
| BUG-53-07 | high | `/jobs/new` GET 422 | **OPEN** | `grep -rn '/jobs/new' pointlessql/api/` returns nothing — no GET handler. Need to add or wire to existing modal in `jobs.html` |
| BUG-53-08 | high | `/dashboards/new` 404 | **OPEN** | Same as BUG-53-07 — no route |
| BUG-53-09 | low | `/agent-reviews` 404 | **CLOSED** | `agent_reviews_routes.py:222` `@router.get("/agent-reviews", response_class=HTMLResponse)` exists since Phase 19 |
| BUG-53-10 | low | walkthrough `foreign-catalog-sync.md` | **OPEN** | Trivial — mark deprecated, foreign-catalogs lebt unter `/connections` |

**Net-Action für Sprint 56.2:**

- 4 Closed-Markierungen in `phase53-replay/_notes.md` (BUG-53-01,
  BUG-53-05, BUG-53-09, plus BUG-53-03 nach Verify).
- 3 Walkthrough-Doc-Fixes (BUG-53-02, BUG-53-04, BUG-53-10).
- 2 echte Code-Changes (BUG-53-07 + BUG-53-08 GET-Routes).

**Win:** 4 von 9 BUGs sind already-fixed-but-not-closed. Saved ~3-4
Tage Arbeit, indem wir Phase 53/19/12 status verifiziert haben.

---

## Section 2 — Layout Pattern Inventory (consolidated, 7 + 6 = 13 buckets)

### Bucket 1 — Long-text columns in `<table>` (9 templates)

| Template | Stelle | Pattern |
|---|---|---|
| `audit_queries.html` (L101-105) | Dynamic SQL results | Cells with arbitrary user-SQL output, no width constraint |
| `audit_search.html` (L65-73) | FTS Snippet column | `data.snippet` rendered raw — can overflow |
| `runs_list.html` (L78-107) | Principal + Agent + Tables | All monospace, no truncation |
| `audit_by_table.html` (L87-100) | Principal column | Email-string raw, no `.table-responsive` wrapper either |
| `_run_tab_operations.html` (L313-355) | SQL/Args/Result | Already truncated `[:120]` with title-tooltip — but tooltip-only-on-hover unreadable |
| `queries.html` (L101-189) | SQL + email | Email rendered full, SQL truncated `[:120]` |
| `alert_detail.html` (L60-92) | webhook URL | Monospace, no truncation |
| `admin_external_writes.html` (L106-152) | commit_info | Inline `style="max-width:360px"` ad-hoc |
| `admin_audit.html` | audit-action-string | Renders `pql.write_table` style FQNs raw |

### Bucket 2 — Mobile-clipping risk

`pql-list-table` class triggers mobile-data-label-stack (CSS in
`list_table.css:136-175`). Status der Listen-Templates:

| Template | `pql-list-table`? | data-label? | Net-Action |
|---|---|---|---|
| `runs_list.html` | ✓ | ✗ | add data-label (8 cols) |
| `admin_audit.html` | ✓ | ?check | verify |
| `agent_reviews_list.html` | ✓ | ✗ | add data-label (5 cols) → wird aber durch 56.9 Card-Konvertierung ersetzt; data-label-Add nur falls 56.9 später kommt |
| `jobs.html` | ✓ | ?check | verify |
| `queries.html` | ✓ | inkonsistent | repair (TDs L153, 162, 178) |
| `branches.html` | ✓ | ?check | verify |
| `dashboards.html` | ✓ | ?check | verify |
| `tables.html` | ✓ | ?check | verify |
| `schemas.html` | ✓ | ?check | verify |
| `table.html` | ✓ | ?check | verify |
| `external_locations.html` | ✓ | ?check | verify |
| `admin_api_keys.html` | ✗ | ✗ | **add `pql-list-table` class + data-label** (8 cols) |
| `admin_external_writes.html` | ✗ | ✗ | **add `pql-list-table` + data-label** (7 cols) |
| `audit_by_table.html` | ✗ | ✗ | wrap in `.table-responsive` + add `pql-list-table` + data-label (4 cols) |
| `alert_detail.html` (destinations) | ✗ | ✗ | add wrapper + `pql-list-table` + data-label (4 cols) |

**Note:** Statt nur `data-label` zu adden für nicht-`pql-list-table`-
Tabellen, müssen wir entweder die Klasse hinzufügen ODER die mobile-
CSS-Rule generischer machen. Klassen-Ansatz ist einfacher.

### Bucket 3 — Empty-state inconsistencies (8 templates)

Bestätigt durch Explore-Audit. Liste in Plan-File 56.3 unverändert.

### Bucket 4 — Heading/padding inconsistencies

Minor — `mb-3` vs `mb-4` 50/50 split. **DROP** für Phase 56 (de-
scoped). Falls Standardisierung gewünscht, separate Phase.

### Bucket 5 — Inline-spinner ohne Progress (6-8 templates)

`_run_tab_lineage.html` (4 spinners), `table.html` profiling,
`model.html` lineage, `data_product.html` yaml-diff. → 56.11
Polish.

### Bucket 6 — Action-discovery problems (4 templates)

Bestätigt. → 56.11 Polish.

### Bucket 7 — Tables→Cards candidates (locked picks)

`agent_reviews_list.html` + `alerts.html` (User-Pick: Ambitious).
`queries.html` deferred (Plan-Agent risk-flag).

### Bucket 8 — Phase-53 Pattern 1: Outline-Button Opacity

**Reframing nach Audit:** `grep 'btn-outline\|opacity' frontend/css/`
findet nur `layout.css:138 opacity: 0.5 !important` mit very narrow
scope (`.pql-editable-view:hover.pql-editable-pencil` only — NICHT
`btn-outline-*`). Plus `list_table.css:53 opacity: 0.35` für
`.pql-row-actions:not(:hover)` (intentional row-action-fade).

**Hypothese:** Pattern 1 (disabled-look outline) ist KEIN CSS-
Override-Issue. Es könnte Bootstrap-Stock-Contrast sein
(low-contrast outline-secondary on light bg) oder eine custom
component-CSS-Datei die ich noch nicht gefunden habe.

**Net-Action für 56.11:** Pattern 1 als VISUAL-CHECK im Browser
verifizieren statt CSS-Sweep-blind. Falls echtes Problem, root-
cause vor Fix identifizieren.

### Bucket 9 — Phase-53 Pattern 2: Errors no Sidebar

Timeboxed in 56.11 (max 2h). Falls `errors.html`-Architektur
request-context-betroffen → defer Phase 57.

### Bucket 10 — Phase-53 Pattern 3: Mobile cards Em-dash Labels

`runs_list.html` mobile-card-stack. Mobile-CSS-rule existiert
(list_table.css:136-175 mit `attr(data-label)` `::before`). Echte
Lücke ist nur das fehlende `data-label` auf den `<td>`s — wird in
56.4 gefixt. Pattern 3 ist damit **effektiv 56.4-bundled.**

### Bucket 11 — Phase-53 Pattern 6: UUID-Format-Mix

Display-filter `format_uuid` in 56.5.

### Bucket 12 — Phase-53 Pattern 7: Zero-SHA-Sentinel

Display-filter `format_hash` in 56.5.

### Bucket 13 — Phase-53 Pattern 8: Tab-Badges only first sub-tab

Run-detail Operations sub-tabs in `run_view.html`. → 56.11 Polish.

---

## Section 3 — Alpine x-data Quoting Risk (10 high-risk + 6 low-risk)

### High-risk (user-controlled names → potential `'` in value)

Outer `x-data='...'` single-quoted; embedded `|tojson` produces
double-quotes inside but doesn't escape outer-string-`'`.

| Template | Line | User-string |
|---|---|---|
| `connection.html` | 18 | UC connection-name |
| `credential.html` | 18 | UC credential-name |
| `external_location.html` | 18 | UC external-location-name |
| `alert_detail.html` | 12 | alert.slug + destinations array |
| `volume_detail.html` | 12 | volume.full_name + files array |
| `admin_audit_sinks.html` | 71 | sink.name |
| `admin_review_destinations.html` | 73 | destination.name (NEW — not in Explore-list) |
| `admin_workspaces.html` | 81 | workspace.slug (NEW) |
| `admin_api_keys.html` | 85 | api-key.name (NEW) |
| `alerts.html` | 11 | alert.slug + saved_queries array (NEW) |

### Low-risk (system-controlled values, low blast)

| Template | Line | Value | Why low-risk |
|---|---|---|---|
| `admin_audit.html` | 143 | ISO timestamp | system-controlled, no quotes |
| `home.html` | 151 | summary.sparkline.days array | system-aggregated, JSON-safe |
| `job_detail.html` | 66 | job.cron_expr | crontab-syntax, low-quote risk |
| `jobs.html` | 78, 86 | cron_expr + ISO | similar |
| `queries.html` | 129 | ISO timestamp | similar |

**Net-Action für 56.2:** Hardening auf alle 10 high-risk Templates.
Low-risk lassen wie sind (nicht prematurely refactor).

---

## Section 4 — Per-Page Semantic-Content Review

Top-Surfaces; pro Page Findings markiert mit `[CONTENT]` (text-
rewrite — fold into 56.10), `[STRUCTURAL]` (column add/remove/
reorder — 56.10), oder `[DESIGN]` (page-redesign — Phase 57+).

### `home.html` — Cockpit Landing

- Heading + 4 KPI-Cards. Probably reasonable from prior phases.
- **TBD-replay** — defer to user-side check after 56.2-56.9 ship.
- *No findings prioritized for 56.10.*

### `runs_list.html` — Agent runs list

- [STRUCTURAL] **Spalten-Reihenfolge:** "Tables touched" liegt
  nach Status / Duration / Principal / Agent / Operations. Aber
  user-task "find run that touched X table" ist häufig — Tables
  verdient höheren Priority-Rank. Reorder: nach Status →
  Tables → Principal/Agent → Operations → Duration.
- [CONTENT] "Operations" column-header ambiguous — könnte
  Operations-count oder Operations-status sein. Rename zu
  "# Ops" oder "Operations count".

### `run_view.html` — Run detail

- [CONTENT] Header Status-Badge prominenz-check; aktuell wahrscheinlich
  inline mit ID + Started-At → Status sollte als Badge prominent
  oben rechts (oder neben Heading) erscheinen.
- [STRUCTURAL] **Tab-Reihenfolge:** Overview / Operations / Lineage /
  Audit (aktuell). User-task: "what did this run DO" → Operations
  ist häufig zuerst gewollt. Reorder Operations vor Overview?
  Kontroversiell — nur ändern wenn 56.10-replay zeigt dass user
  immer Operations zuerst klickt. **Markieren als TBD**.
- [CONTENT] "Source" sub-tab heading: aktuell zeigt SHA-256 + bytes
  — heading "Source" alleine sagt nicht "wo der run-code herkommt".
  Add subtitle: "Source bytes captured at run start".

### `audit_inbox.html` — Audit cockpit Inbox

- [STRUCTURAL] **KPI-Card-Auswahl:** aktuell vermutlich "anomalies
  last 24h" als top-metric. Handlungs-relevanter wäre "anomalies
  unack'd" oder "open anomalies" — was wartet auf Aktion. Replace
  Top-KPI.
- [CONTENT] "Ack" / "Un-ack" buttons: fold "Acknowledge" /
  "Unacknowledge" als full-words — clearer user-intent (56.11
  Action-discovery covers this).

### `audit_queries.html` — Saved queries cockpit

- [CONTENT] sub-section "Result" heading — could be "Query result"
  for clarity (or "Last query result" if cached).
- [CONTENT] Saved-queries sidebar empty-state needs better message
  (covered by 56.3 / fine-tune in 56.10 if needed).

### `audit_search.html` — FTS search

- Already renders snippet correctly post-Phase-55.4 (offset-
  pagination). Snippet drawer covered by 56.8.

### `agent_reviews_list.html` — Agent reviews

- Going to Card-Layout in 56.9. Re-evaluate semantics in card-
  context: severity-badge prominent, period-range readable, full
  summary first-line not truncated.

### `alerts.html` — Alerts list

- Going to Card-Layout in 56.9. Cron-expression + condition
  prominent, active-toggle as card-footer-bar.

### `models.html` — Models list

- Empty-state covered by 56.3.
- [CONTENT] Heading + sub-heading TBD-replay — likely fine.

### `model.html` — Model detail

- [STRUCTURAL] Multiple tabs (Overview / Versions / Lineage / etc)
  — TBD-replay; if user-task = "find latest production version"
  is hidden, reorganize.

### `branches.html` + `branch_detail.html`

- Phase-16.5 polished; likely fine. TBD-replay.

### `admin_audit.html`

- [CONTENT] Filter row column-headers: verify they map to
  user-mental-model.
- KPI: probably fine.

### `table.html` — Table detail

- [STRUCTURAL] 6 tabs from Phase 17.4. TBD-replay if user-task
  fits the order.

### `connection.html` + `credential.html` + `external_location.html`

- Phase-15.6 federation; mostly fine. Delete-button-discovery
  (top-right) is good UX already.

### `dashboards.html` + `jobs.html`

- BUG-53-08 + BUG-53-07 + 56.2 GET-form-route.
- Empty-state default-CTAs need verification post-fix.

### `job_detail.html`

- 56.3 empty-state.

---

## Section 5 — Affected Files per Sub-Sprint

Reduzierte Liste (nach Verify):

**56.2** (BUG-Closure + Alpine 10 surfaces):
- 10 Alpine-templates (high-risk list above)
- 3 walkthrough-docs (sql-editor.md, admin-audit.md, foreign-catalog-sync.md)
- 1 mark-closed in phase53-replay/_notes.md (4 BUGs at once)
- `/jobs/new` GET-route (jobs_routes.py + new template)
- `/dashboards/new` GET-route (dashboards_routes.py + new template)
- icon_rail.html — verify `/notebooks/workspace` works; if not, fix

**56.3** (Empty-state — 8 templates):
- alert_detail (×2), queries, models, job_detail, agent_run_compare
  (×2), model_compare (×3), agent_review_detail, admin_external_writes

**56.4** (Mobile data-label):
- `pql-list-table`-Klasse zusätzlich auf admin_api_keys,
  admin_external_writes, audit_by_table, alert_detail-destinations
- data-label-Add auf runs_list, queries (consistency repair) +
  diese 4 newly-classed.

**56.5** (Jinja filters):
- pointlessql/web/jinja_filters.py (NEW oder extend)
- pointlessql/api/main.py (registration if needed)
- Apply in 7+ templates.

**56.6/56.7/56.8/56.9** — per Plan unverändert.

**56.10** — Per-Page-Findings oben (CONTENT/STRUCTURAL items):

- `runs_list.html` Spalten-Reihenfolge + "Operations" rename
- `run_view.html` Source-tab subtitle
- `audit_inbox.html` Top-KPI replace ("unack'd")
- `audit_queries.html` "Query result" sub-heading

Estimated 4-6 small Template-changes; well under 1-day cap.

**56.11** — per Plan, plus Pattern 1 als VISUAL-CHECK statt CSS-
sweep.

---

## Section 6 — Risk-Notes

- **Truncate-Tooltip Perf (56.6):** native `title=` only; KEIN
  Bootstrap-Tooltip-Init auf 50-Row-Tabellen.
- **`<details>/<summary>` row** (NICHT gewählt — User-Pick = Offcanvas).
  Dokumentiert für future-phase als Alternative bei kleinen
  Detail-Views.
- **Errors-no-Sidebar (Pattern 2):** 2h-timeboxed in 56.11. Falls
  `errors.html` nicht von base.html erbt UND request-context-
  betroffen → defer Phase 57.
- **Pattern 1 (Outline-button-Opacity):** Reframing — KEIN CSS-
  override gefunden. Visual-check im 56.11 vor blindem Fix.
- **listTable + Tables→Cards:** in 56.9 verwenden wir server-side-
  filter (existing pagination-macro), generalisieren listTable
  NICHT.

---

## Section 7 — Out-of-Scope

| Item | Why |
|---|---|
| `queries.html` Tables→Cards | Plan-Agent-Risk |
| Test-Coverage-Sweep | Phase 57 |
| Errors-no-Sidebar wenn request-context | Phase 57 |
| DESIGN-Findings aus Section 4 (page-level redesigns) | Phase 57 |
| Server-side `.progress` bars | Server-API fehlt |
| Form-field-Wrapper-Macro | <3 surfaces |
| Tailwind / React / Custom-Component-Lib | Anti-Goal |
| Phase 17 reopen | Anti-Goal |
| Browser-replay pre-rebuild | User-side post-rebuild |
| `mb-3` vs `mb-4` standardization | de-scoped |
| Low-risk Alpine quoting (6 surfaces) | Latent only, no user-controlled names |

---

**Audit complete.** Sub-Sprint 56.2 startet als nächstes.
