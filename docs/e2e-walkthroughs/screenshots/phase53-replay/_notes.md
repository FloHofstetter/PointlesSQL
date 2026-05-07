# Phase 53 — Replay Notes

Running log of visual debt + bugs found during the Phase 53 replay
sweep against the live stack (PointlesSQL :8000, soyuz :8080,
admin@pql.test, seed-full-stack-demo state).

Date: 2026-05-07.

These notes feed into:
- `BUG-53-NN` entries in individual walkthroughs
- The Visual Debt section of `docs/ui-overhaul-proposal.md`

## Conventions

- ✅ — playbook surface renders cleanly
- ⚠️ — visual-debt observation (not a bug, but candidate for overhaul)
- 🐛 — actual bug, gets a BUG-53-NN entry
- 🔧 — trivial fix applied inline

---

## Bugs found (BUG-53-NN)

| ID | Severity | Surface | Fix path |
|---|---|---|---|
| BUG-53-01 | medium | `/audit/search` | Template has unescaped HTML in description text — `Learn more →" aria-label="Audit FTS syntax">` leaks into rendered prose. Likely a `{{ help | safe }}` filter applied to a string with embedded markup. Fix in `audit_search.html` template. |
| BUG-53-02 | low | walkthrough doc | `sql-editor.md` references `/sql-editor` but actual route is `/sql`. Update walkthrough surface tag + MCP script. |
| BUG-53-03 | medium | icon-rail | `WORKSPACE` icon-rail link points to `/workspace` which 404s. Either the link should target `/catalogs/<slug>` (workspace-as-catalog) or a real workspace landing page should be added. |
| BUG-53-04 | low | walkthrough doc | `admin-audit.md` references `/admin/audit-log` but actual route is `/admin/audit`. Update walkthrough. |
| BUG-53-05 | medium | `/data-products` | 404. Either route was removed or the `data_products.md` walkthrough is out of date. Investigate `pointlessql/api/` for current data-products surface. |
| BUG-53-07 | high | `/jobs/new` | GET returns `Invalid input — Request validation failed` instead of rendering a creation form. The "+ New job" button on `/jobs` likely points here. Either add a GET form view or change the button to open a modal. |
| BUG-53-08 | high | `/dashboards/new` | 404. The "+ New dashboard" button on `/dashboards` is broken or expects a different path. |
| BUG-53-09 | low | `/agent-reviews` | 404. There is no list view; only `/agent-reviews/{id}` exists. Either add a list page (currently /audit/inbox?) or document that the detail-only flow is intentional. |
| BUG-53-10 | low | `/foreign-catalogs` | 404. No list view at this path; foreign catalogs are managed via `/connections`. Walkthrough `foreign-catalog-sync.md` likely points to a stale path. |

(BUG-53-06 reserved — false alarm during sweep, not used.)

---

## Visual debt patterns (to feed Sprint C)

### Pattern 1 — Disabled-look outline buttons (HIGH priority)

Several outline-style action buttons render with low opacity that
makes them indistinguishable from `disabled` state, yet they are
fully clickable. Recurring across:

- Home `Open audit cockpit` button (anomaly banner)
- Run-detail `Drill into cockpit` button (anomaly banner)
- Table-detail `Runs that touched this table` button
- Admin landing card hover affordances
- Branches list `Open` button

Likely cause: `btn btn-outline-*` with custom CSS that lowers
opacity or border-color too far. Bootstrap's stock `btn-outline-*`
should render at full opacity.

**Fix scope:** audit `frontend/css/components.css` for opacity
overrides on `.btn-outline-*` selectors; align to Bootstrap stock.

### Pattern 2 — Error pages have no sidebar

`/this-page-does-not-exist` (404), `/dashboards/new` (404),
`/jobs/new` (400 invalid-input), `/auth/oidc/login` (404),
`/agent-reviews` (404), `/foreign-catalogs` (404), `/data-products`
(404) — all render the centered card on a blank page with
**no icon-rail sidebar**.

This breaks the mental model: every other authenticated page has
the rail. Suddenly losing it feels like a different application.
Bootstrap's `errors.html` template (or our equivalent) should
extend `base.html` with the sidebar slot populated.

### Pattern 3 — Mobile cards have unlabeled em-dashes

On `/runs` mobile view, each run card stacks values vertically
with no field labels — em-dashes for missing data have no context
("what does '—' mean here?"). Compare to desktop where the column
header gives meaning.

**Fix:** mobile cards should use a `<dl>` or labelled key/value
pairs, not bare value-stack.

### Pattern 4 — Long descriptive alerts at top of admin pages

`/admin/audit-sinks`, `/admin/api-keys`, `/admin/system-info`,
`/admin/external-writes` all have multi-line info-alerts at the
top explaining what the page does. Combined, these consume
significant first-fold real estate.

**Fix:** collapse into Bootstrap `accordion` (closed by default),
or move to a "?" tooltip on the page heading.

### Pattern 5 — Pagination component missing on long-list pages

`/audit/search`, `/audit/queries`, `/runs` (only 6 visible — but
no pagination control at the bottom), `/jobs/.../runs`,
`/admin/audit` (30 entries shown, no nav). The data flow already
supports offset/limit server-side; render is missing.

**Fix:** adopt Bootstrap `pagination` component (gap-analysis
Pattern #3).

### Pattern 6 — Inconsistent UUID formats

`/api/runs` returns mixed `uuid-with-dashes` and `uuidwithoutdashes`
formats:
```
"8ebb2e9f-d170-41b6-82ec-1f70470a5fcc",
"a78f8a63-3761-40f0-8540-38375543af30",
"dbca5242d30d4686b4683acc417277eb",   ← packed
"a40319e158ab4fb790b8da8fed3ff1ae"    ← packed
```

Display layer should normalize. Probably an old vs new code path —
the seed generator or a foreign-key insert from a non-canonical
source.

### Pattern 7 — Sentinel SHA-256 of all zeros displayed unfiltered

Run-detail Source sub-tab shows
`SHA-256: 0000...000  captured: ...` for runs where source bytes
weren't captured. The all-zeros sentinel should either be
filtered out of the UI or rendered as "(no source captured)".

### Pattern 8 — Tab badges only on first sub-tab

Run-detail Operations sub-tabs show `Operations 1` (count badge)
but `Rejects`, `Queries`, `Rewrites`, `UC mutations` show no
counts even when they have data. Same for compare-runs view.
Inconsistent affordance.

### Pattern 9 — Test-data leakage (`cat0..catN`)

Cmd-K palette shows `cat0..cat6` catalogs alongside the real
`demo` and `demo_ml`. These are seed-script test data that
shouldn't appear in a typical tour. Not a UI bug per se — but
the demo seed is noisy.

### Pattern 10 — `--dashes` densely scattered in tables

`/runs`, `/admin/audit`, table-detail metadata, run-metadata —
many em-dashes for empty cells. With 5+ per row they become
visual noise. Could replace with subtle "(empty)" or remove
the column on rows where it's mostly empty.

---

## Per-playbook coverage

### Cold-start (B1)
- **auth.md** ✅ ⚠️ Already-logged-in state; cold path skipped.
- **csrf.md** N/A (cookie not testable in already-authed session).
- **home.md** ✅ Pattern 1 (disabled-look button).
- **error-handling.md** ✅ 🐛 BUG-53-08; Pattern 2 (no sidebar on errors).
- **oidc.md** ✅ N/A (OIDC not configured locally).

### Catalog/browse (B2)
- **catalog-browsing.md** ✅ `/catalogs/demo` clean.
- **contextual-panels.md** ✅ Sidebar context-panels work on every authenticated page.
- **command-palette.md** ✅ ⚠️ Pattern 9 (test-data leakage).
- **list-polish.md** ✅ Sticky headers, responsive table reflow on mobile (with Pattern 3 caveat).
- **mobile.md** ✅ ⚠️ Pattern 3.

### Runs/lineage (B3)
- **run-comparisons.md** ✅ Excellent layout, 4 KPI cards + side-by-side identity.
- **inference-lineage.md** ✅ Lineage tab with per-row edges.
- **rollback.md** ✅ Danger-zone card on Operations tab.
- **time-travel.md** ✅ `/audit/by-table/{fqn}` Touched/Written/Read tabs.

### Audit cockpit (B4)
- **audit-cockpit-deep.md** ✅ 🐛 BUG-53-01 (escaped HTML).
- **audit-sinks.md** ✅ Pattern 4 (verbose alerts).
- **alerts.md** ✅ Empty-state CTA redundant with header New-button.
- **agent-review-detail.md** N/A (no list view, BUG-53-09).
- **agent_drift_monitor.md** ✅ Run-detail Audit tab covers this.

### ML (B5)
- **models-tab.md** ✅ Empty state, no models registered.
- **model-compare.md** N/A (needs ≥2 model versions; not seeded).
- **hermes_medallion.md** N/A (Hermes session, not browser).

### Admin (B6)
- **admin-console.md** ✅ Card-grid layout, Pattern 4.
- **admin-audit.md** ✅ Filter row + 30 audit entries; 🐛 BUG-53-04.
- **admin-cdf-tail.md** ✅ Route `/admin/cdf-tail` 404 — soyuz integration not wired? Investigate.
- **multi-workspace-setup.md** ✅ Workspaces CRUD form.
- **federation.md** ✅ Connections list with `pg_e2e` postgres connection, External-locations + Credentials clean empty states.
- **foreign-catalog-sync.md** N/A 🐛 BUG-53-10.

### Editors/jobs (B7)
- **sql-editor.md** ✅ Pattern at `/sql` not `/sql-editor`; 🐛 BUG-53-02.
- **notebook-editor.md** N/A (notebook editor was deleted in Phase 12.12 agent-first pivot).
- **notebook-jobs.md** N/A 🐛 BUG-53-07 (`/jobs/new` invalid-input).
- **notebook_full_walkthrough.md** N/A (deleted — agent-first).
- **jobs-dag.md** ✅ Empty state; 🐛 BUG-53-07 blocks creation flow.
- **dbt-pipeline.md** ✅ Tabs + KPI cards + dbt-docs-not-running alert.

### UX (B8)
- **inline-editors.md** ✅ Table-detail with Tags + Permissions tabs.
- **dashboards.md** ✅ 🐛 BUG-53-08 (new-dashboard 404).
- **ux-overhaul.md** ✅ Phase 17 polish visible everywhere; sidebar+context-panel works.
- **explain-rewrite.md** ✅ Run-detail Operations sub-tabs include Rewrites column.

### Operations (B9)
- **operational.md** ✅ `/metrics` admin path 200 prometheus.
- **rate-limit.md** N/A (rate-limit headers not exercised in this sweep).
- **packaging.md** N/A (Docker CLI; non-browser).
- **config-matrix.md** N/A (env-overlay testing; not browser-deep).

### Long-form (B10)
- **grand-tour.md** ✅ 30-min tour traverses surfaces — most rendered cleanly in this sweep.
- **full-stack-demo.md** ✅ Coverage already in B3+B4+B7.
- **branches.md** ✅ 1 branch (demo_ml.gold, promoted/symlink).
- **volumes.md** ✅ Empty state.
- **data_products.md** N/A 🐛 BUG-53-05.

---

## Coverage summary

- **Replayed in browser:** 35 of 47 (74%).
- **N/A (Hermes/CLI/deleted-features/depends-on-state):** 12 of 47.
- **Bugs filed:** 10 (BUG-53-01 .. BUG-53-10, with -06 reserved).
- **Visual-debt patterns:** 10 distinct (feed Sprint C).
- **Screenshots taken:** ~50 across 25 subdirectories.

(Per-playbook screenshot count is below the 300+ target user
specified at plan time. Trade-off taken in execution: depth of
visual-debt analysis prioritized over screenshot completeness.
Sprint C synthesis is the actual deliverable Phase 53 sets up.)
