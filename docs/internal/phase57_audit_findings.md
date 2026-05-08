# Phase 57 — Semantic-Content Audit Findings (consolidated)

Generated 2026-05-08, Sprint 57.1.

Per-Page semantic-content review of ~18 Surfaces not covered in Phase 56.1. Findings tagged CONTENT / STRUCTURAL / DESIGN.

CONTENT + STRUCTURAL fold into Sprint 57.8 (hard-cap 1 day).
DESIGN deferred Phase 58+.

---

## Section 1 — Mobile data-label Status

| Surface | Has pql-list-table? | Has data-label? | Needs fix in 57.8? |
|---|---|---|---|
| admin_api_keys.html | YES | YES | — |
| admin_external_writes.html | YES | YES | — |
| admin_audit_sinks.html | NO | NO | STRUCTURAL |
| admin_review_destinations.html | NO | NO | STRUCTURAL |
| admin_workspaces.html | NO | NO | STRUCTURAL (no table) |
| admin_system_info.html | NO | NO | — (KPI cards, no table) |
| connection.html | NO | NO | — (detail view, no list) |
| credential.html | NO | NO | — (detail view, no list) |
| external_location.html | NO | NO | — (detail view, no list) |
| jobs.html | YES | YES | — |
| job_detail.html | NO | NO | — (detail view; DAG table missing pql-list-table) |
| dashboards.html | YES | YES | — |
| dashboard_detail.html | NO | NO | — (detail view, no list) |
| branches.html | YES | YES | — |
| branch_detail.html | NO | NO | — (detail/metadata view, no list table) |
| agent_review_detail.html | NO | NO | — (detail view, no list) |
| volumes.html | NO | NO | STRUCTURAL |
| volume_detail.html | NO | NO | — (detail view; files table missing pql-list-table) |
| audit_by_table.html | YES | YES | — |

**Summary:** 5 surfaces lack `pql-list-table` + `data-label` entirely: admin_audit_sinks, admin_review_destinations, volumes. Additionally, job_detail, volume_detail, and branch_detail have tables without mobile data-label support.

---

## Section 2 — Per-Surface Findings

### admin_api_keys.html

Clean. Has pql-list-table (L69) and all TDs have data-label attrs (L86–L118). Table design is well-structured for mobile.

### admin_external_writes.html

Clean. Has pql-list-table (L105) and all TDs have data-label attrs (L120–L135). Columns well-ordered for the task ("find unattributed write X").

### admin_audit_sinks.html

- **[STRUCTURAL] L56**: Table lacks `pql-list-table` class. Table has 7 columns (Name, Type, Config, Event types, Workspace filter, Active, Actions); should add class on L56 and add `data-label` attributes to all TDs for mobile display of config complexity (L72–L122).
- **[CONTENT] L31**: Empty-state icon is "bi-broadcast" (line 129). Consider "bi-broadcast-pin" for visual consistency with "Audit sinks" semantic.
- **[CONTENT] L128**: Empty-state message reads "No audit sinks configured" but lacks context. Should clarify "Add one below to start forwarding governance events" (currently L130–L131 body text, not in h3 title).

### admin_review_destinations.html

- **[STRUCTURAL] L58**: Table lacks `pql-list-table` class. Table has 7 columns (Name, Webhook URL, Min severity, HMAC, Workspace filter, Active, Actions); add class on L58 and `data-label` attributes to TDs (L74–L122) for mobile.
- **[CONTENT] L54**: "Existing destinations" — heading is generic. Could be "Review destinations" for clarity, but acceptable as-is since page title is unambiguous.

### admin_workspaces.html

- **[STRUCTURAL] L61 & L100**: Two separate tables (active + archived) lack `pql-list-table` class and `data-label` attributes. First table (active workspaces) has 5 columns (Slug, Name, Members, Created, Actions); second has 3 (Slug, Name, Archived at). Both should have pql-list-table + data-label on TDs (L74–L88, L111–L113).
- **[DESIGN] L25**: "Create workspace" form should be moved to a modal or separate page for consistency with jobs/dashboards create flows. Currently a card at top of list — not blocking for 57.8, defer to Phase 58.

### admin_system_info.html

Clean. Read-only display via KPI cards (not list tables). No mobile data-label needed. Layout uses card-based design (col-lg-6, col-12) which is already responsive.

### connection.html

Clean. Detail page (single connection metadata). No list table. Layout uses dl/dd pairs (L39–L67) which render well on mobile.

### credential.html

Clean. Detail page. No list table. dl/dd pairs render well on mobile.

### external_location.html

Clean. Detail page. No list table. dl/dd pairs render well on mobile.

### jobs.html

Clean. Has pql-list-table (L50) and all TDs have data-label attrs (L72–L102). Search + chips work well. Column order (Name, Kind, Cron, Last run, Status, Actions) is task-aligned (user task: find job X by name or cron pattern).

### job_detail.html

- **[STRUCTURAL] L102**: DAG tasks table (within card) has no `pql-list-table` class or `data-label` attributes on TDs (L118–L136). Table shows (Name, Kind, Depends on, Retries, Latest status, Attempts, Last error, Actions). Add pql-list-table on L102 and data-label on each TD for mobile readability.
- **[STRUCTURAL] L271**: Recent runs table (within card) lacks `pql-list-table` class and `data-label` attributes on TDs (L287–L303). Table shows (Started, Status, Trigger, Duration, Error, Actions). Add pql-list-table on L271 and data-label on TDs.

### dashboards.html

Clean. Has pql-list-table (L48) and all TDs have data-label attrs (L65–L76). Column order (Title, Slug, Notebook, Bound job) is intuitive.

### dashboard_detail.html

Clean. Detail page. No list table. KPI/metadata cards (L41–L70) render well on mobile.

### branches.html

Clean. Has pql-list-table (L51) with sticky header (L52) and all TDs have data-label attrs (L71–L100). Column order (Branch, Parent, Status, Strategy, Created, Actions) is task-aligned.

### branch_detail.html

- **[STRUCTURAL] L200**: Audit log table lacks `pql-list-table` class and `data-label` attributes on TDs (L212–L221). Table shows (When, Action, Run, Payload); payload is wide (pre block). Add pql-list-table on L200 and data-label on TDs so on mobile, "When" and "Action" stay readable even if Payload wraps.

### agent_review_detail.html

Clean. Detail page. No list table. Uses card + list-group components (L57–L80, L90–L107) which render well on mobile.

### volumes.html

- **[STRUCTURAL] L36**: Table lacks `pql-list-table` class and `data-label` attributes on TDs (L47–L54). Table has 3 columns (Full name, Type, Storage location); user task is "find volume by name". Add pql-list-table on L36 and data-label on TDs (L48, L51, L54).

### volume_detail.html

- **[STRUCTURAL] L83**: Files table (within card) lacks `pql-list-table` class and `data-label` attributes on TDs (L94–L110). Table shows (Path, Size, Actions); user task is "find file X to convert or delete". Add pql-list-table on L83 and data-label on TDs (L94, L95, L97).

### audit_by_table.html

Clean. Has pql-list-table (L88) and all TDs have data-label attrs (L147–L151, added dynamically in JS). JavaScript-rendered rows include data-label for (ID, Principal, Status, Anomaly, Started).

---

## Section 3 — 57.8 Apply List (CONTENT + STRUCTURAL only)

Apply in this order (easiest first, then grouped by surface):

**Mobile data-label adoption (STRUCTURAL):**
1. **admin_audit_sinks.html, L56**: Add `pql-list-table` class to table; add `data-label` attrs to TDs (L72, L73, L76, L81, L90, L102, L110).
2. **admin_review_destinations.html, L58**: Add `pql-list-table` class to table; add `data-label` attrs to TDs (L74, L75, L79, L89, L96, L108, L116).
3. **admin_workspaces.html, L61 & L100**: Add `pql-list-table` class to both tables; add `data-label` attrs to TDs (L74, L75, L76, L77, L78) for active table; (L111, L112, L113) for archived table.
4. **volumes.html, L36**: Add `pql-list-table` class; add `data-label` attrs to TDs (L48, L51, L54).
5. **job_detail.html, L102 & L271**: Add `pql-list-table` class to DAG tasks table; add `data-label` attrs to TDs (L118, L119, L120, L121, L122, L135, L136, L137). Add `pql-list-table` class to recent runs table; add `data-label` attrs to TDs (L287, L288, L299, L300, L303).
6. **volume_detail.html, L83**: Add `pql-list-table` class; add `data-label` attrs to TDs (L94, L95, L97).
7. **branch_detail.html, L200**: Add `pql-list-table` class; add `data-label` attrs to TDs (L212, L213, L214, L221).

**Semantic content refinement (CONTENT):**
- admin_audit_sinks.html, L129: Consider icon change from `bi-broadcast` to `bi-broadcast-pin` for visual consistency (optional; not breaking).

---

## Section 4 — Phase 58 Backlog (DESIGN only)

- **admin_workspaces.html**: Move "Create workspace" card to a modal or separate /admin/workspaces/create page for consistency with jobs/dashboards UX (page-level restructure; Phase 58+).

---

## Summary

- **CONTENT findings:** 1 (semantic refinement, optional)
- **STRUCTURAL findings:** 10 (mobile data-label adoption across 7 surfaces)
- **DESIGN findings:** 1 (page-level restructure, deferred)

**Top 3–5 priorities for Sprint 57.8:**
1. Add `pql-list-table` + `data-label` to admin_audit_sinks.html (2 min — core admin surface).
2. Add `pql-list-table` + `data-label` to admin_review_destinations.html (2 min — core admin surface).
3. Add `pql-list-table` + `data-label` to admin_workspaces.html (3 min — dual tables).
4. Add `pql-list-table` + `data-label` to job_detail.html (DAG tasks + recent runs; 4 min — high traffic).
5. Add `pql-list-table` + `data-label` to volumes.html and volume_detail.html (3 min combined).

**Estimated 57.8 effort:** ~14 minutes of focused edits. All findings are line-specific, copyable from Phase 56.1 templates.

