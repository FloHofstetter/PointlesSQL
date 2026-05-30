# Data-Product-Cluster UX-Audit — 2026-05-30

> **Mode:** Headful Firefox (Playwright-MCP, bundled binary, 1440×900) ·
> **Surfaces:** 14 (2 discovery + 8 detail tabs + 4 admin) plus 3
> deep-dive end-to-end flows · **Seed:** `seed-mesh-demo.py` overlay on
> existing UC catalog (no fresh `seed-e2e.py` due to hardcoded `/app`
> warehouse-path; was acceptable, demo catalogs already present) ·
> **Session:** Admin (first-account auto-admin via `/auth/register`).

## TL;DR

- **Three live bugs surface within 2 seconds of opening any data-product
  detail page**: the social drawer fires two `"no DataProduct at
  undefined.undefined in workspace 1"` error toasts, the new
  Schema-Versioning drawer renders inline as a giant card instead of as
  an overlay, and every Alpine factory's `init()` runs twice — every
  API call on the page actually happens 2–6 times.
- **The freshly-shipped tabs work in their backend layer** (Contract
  Tests CRUD + Run-All round-trips clean; Cost-&-quota strict-mode
  saves and the "Active quota mode" badge flips to `strict`), but
  the **UI surface is rough** — form-field/save-button placement is
  inconsistent across the three new cards, and the Schema-Versioning
  drawer is effectively unusable.
- **Admin surfaces load** but `/admin/policy-modules` throws an Alpine
  expression error on first paint (`testResult is null`); the 4 cards
  on `/admin` are clean but the surfaces behind them only render an
  empty-state — the substrate works (we tested the API directly),
  but the pages can't yet drive a useful workflow without a
  pre-seeded module / pending candidate / draft spec.

**Verdict for the cluster as a whole**: substrate is solid, surfaces
need a focused polish pass before this is shippable to anyone but
us. The bug list is short (7 entries) and mostly local; none are
backend-design problems.

---

## Setup notes

- soyuz-catalog (port 8080) + PointlesSQL (port 8000) both already
  running locally. PointlesSQL restarted once to pick up `rc194`
  assets (browser had been pinned at `rc192`).
- Seed: `seed-mesh-demo.py` created `demo.sales` + `demo.hr` with
  one upstream-port edge, 4 stats rows, 2 SLOs (1 pass / 1 fail).
  `seed-e2e.py` failed with `PermissionError: /app` (warehouse-path
  hardcoded for docker); not blocking — the existing UC state was
  enough.
- Auth: registered `admin@pql.test` via `/auth/register` (first
  account → auto-admin per the form's notice).
- Screenshots: `docs/internal/ui-audits/2026-05-30-data-product-cluster/screenshots/`,
  numbered `NN_w<N>_<surface>_<action>.png`.

---

## Wave 1 — Discovery surfaces

### S01 — /data-products listing

[Loaded](2026-05-30-data-product-cluster/screenshots/01_w1_list_loaded.png) ·
[Filtered "sales"](2026-05-30-data-product-cluster/screenshots/02_w1_list_filtered.png)

**Was funktioniert**
- Listing renders both seeded products cleanly; columns (Product,
  Version, Steward, Followers, Comments 7d, Downstream, Agents 7d,
  Last loaded) are usefully chosen and width-balanced.
- Filter is live (no submit step) — typing `sales` immediately
  narrows to one row.
- Per-row `on_time` badge in "Last loaded" is a tight at-a-glance
  freshness signal.

**Was reibt**
- The four filter chips (`All / Has comments / Has README / Stale`)
  are styled as buttons, not as a toggle group — unclear whether
  they're radio (one-of) or multi-select. After clicking I see no
  visible "active" state on any of them.
- "Steward" column shows `No steward` for both rows — that's
  expected for the seed, but the empty-state cell makes the column
  feel half-broken at first glance. A `—` would read calmer.
- No per-row CTA — the only way to act on a product is to click the
  name. A right-side actions cluster (open / star / unfollow) would
  cut a click for power users.

**Verdict**: **polish**.

### S02 — /data-products/demo/sales detail shell

[Loaded](2026-05-30-data-product-cluster/screenshots/03_w1_detail_overview_with_BUG_toasts.png)

**Was funktioniert**
- Header packs product ref, version, on-time-30d badge, Follow,
  Social, action menu in ≈ 480px — efficient use of top space.
- All 9 tabs fit at 1440×900 with no wrap. Tab keys read clean
  (Overview / Contract / Diff / Lineage / Compliance / Governance /
  Contract tests / Interop / Activity).

**Was reibt**
- **The two `"no DataProduct at undefined.undefined in workspace 1"`
  toasts appear within 2 seconds of every detail-page load** — see
  the linked screenshot. Pure noise from a wiring bug
  (see BUG-30-02 + BUG-30-03 below).
- Every API call fires **two times** at minimum (`/governance`,
  `/contract-tests`, `/fixtures`); shared endpoints fire 4–8 times
  (`/discovery` × 8, `/output-ports` × 6) — see BUG-30-01.

**Verdict**: **polish** — the page is functional under the noise,
but the noise is itself the headline impression of opening any
detail page.

---

## Wave 2 — Detail tabs

### S03 — Overview tab

[Full](2026-05-30-data-product-cluster/screenshots/09_w2_overview_full.png)

**Was funktioniert**
- 9 cards (Healthy band, SLO table, Domain, Discovery, Ports,
  Semantic, Statistics, README, Consume) plus a right-rail of 8
  smaller cards (Steward, Lifecycle, Bitemporal, Consumption,
  Event stream, Infrastructure, Use cases, Rating). Lots of
  signal density without becoming illegible.
- SLO table's verdict pill (`pass` / `fail`) sits in a column with
  the target threshold + observed value — that's the right shape
  for the SLO table.
- "Consume this product" with tabs `PQL / SQL / Python` and a
  one-click copy button is the strongest microsurface on the page.

**Was reibt**
- The page is **really long** — ≈ 13 cards stacked + an 8-card
  right rail. Scrolling is the dominant interaction. A 2-column or
  group-collapse pass would help density without losing signal.
- Empty-state phrasing is inconsistent across cards: "No transformation
  bound yet." vs "No concepts declared." vs "No output ports
  declared. SQL access is always available." — different verb
  tenses + different presence of a fallback hint. Tightening to one
  pattern reads cleaner.
- Form-row layouts inside cards differ: Domain card uses
  `select → button` left-to-right; Output ports uses
  `text → select → text → button`; Concepts uses
  `text → text → text → button`. None broken, but the inconsistency
  registers as visual noise.

**Verdict**: **polish**.

### S04 — Contract tab

[Snapshot](2026-05-30-data-product-cluster/screenshots/12_w2_contract_tab.png) — render-check only.

**Was funktioniert**: Tab loads, contract content visible.

**Was reibt**: Nothing called out beyond the global double-fetch
issue.

**Verdict**: **ship**.

### S05 — Diff tab

[Snapshot](2026-05-30-data-product-cluster/screenshots/13_w2_diff_tab.png)

**Was funktioniert**: Loads, empty-state clean.

**Was fehlt**: Without prior contract versions to diff against, the
tab shows just an empty state — the seeded product only has one
version. Not blocking.

**Verdict**: **ship**.

### S06 — Lineage tab

[Snapshot](2026-05-30-data-product-cluster/screenshots/14_w2_lineage_tab.png)

**Was funktioniert**: Cytoscape renders the seed-mesh-demo edge
(`demo.sales → demo.hr`).

**Was reibt**: 9 console warnings appear after the Cytoscape
render — they're vendor-side and don't affect the graph, but they
clutter the dev console.

**Verdict**: **ship**.

### S07 — Compliance tab

[Snapshot](2026-05-30-data-product-cluster/screenshots/15_w2_compliance_tab.png)

**Was funktioniert**: Empty-state ("No open compliance violations")
clean.

**Verdict**: **ship**.

### S08 — Governance tab

[Loaded](2026-05-30-data-product-cluster/screenshots/07_w2_governance_loaded.png) ·
[After save quota = strict](2026-05-30-data-product-cluster/screenshots/08_w4_governance_after_save_quota.png)

**Was funktioniert**
- Policy table renders the 5-field effective-policy state with a
  clear `unset` source badge on every row. Inheritance story is
  legible without reading the docstring.
- **Cost & quota card** renders the 7-day cost summary cleanly
  (`Estimated cost (last 7 days): 0.00` + `Active quota mode: off`)
  and the inline editor (quota mode select + max-cost-per-day +
  max-queries-per-hour) round-trips: after save, the badge flips
  to `strict` and the numbers stick across reload — see linked
  "after save quota" screenshot.
- The explanatory paragraph under the editor ("Strict mode raises
  HTTP 429 on the next read once a limit is breached. Warn mode
  records a decision row and lets the read through.") is the right
  shape for an admin surface — it tells the user the behavioural
  consequence, not the data shape.

**Was reibt**
- The **Cost & quota card has no Save button of its own** — the
  user has to scroll back up to the Policy card's "Save policy"
  button, which saves *everything* including the quota fields.
  Until you discover that, the Cost & quota card looks read-only.
  This is the single biggest UX miss on the Governance tab.
- Three forms on this tab; only one has a save button. Surface
  expectation breaks.

**Verdict**: **polish** — the substrate works, the discovery
flow doesn't.

### S09 — Contract tests tab

[Empty](2026-05-30-data-product-cluster/screenshots/04_w2_contract_tests_empty.png) ·
[After declare](2026-05-30-data-product-cluster/screenshots/05_w4_contract_tests_after_declare.png) ·
[After run-all](2026-05-30-data-product-cluster/screenshots/06_w4_contract_tests_after_runall.png)

**Was funktioniert**
- The tab card has a tight header layout: title + mode-select
  (`synthetic`/`live`) + Run-all button.
- Declare → list-refresh → run-all round-trip is clean. POST to
  `/contract-tests` returns 200, GET refresh renders the new row,
  POST to `/contract-tests/run?mode=synthetic` returns 200.
- Synthetic Fixtures sub-card has the right empty-state message
  ("Synthetic-mode runs need at least one fixture per table the
  tests reference.") — explains the dependency.

**Was reibt**
- **Form-field order on the Declare form is wrong**: the row reads
  `Name → Assertion kind → Severity → [Declare button] → Assertion
  spec (JSON)`. The JSON spec is required-ish (the form is
  meaningless without it for most assertion kinds), but it lives
  *after* the submit button. A user is asked to click Declare
  before reading the most important field.
- "Severity" defaults to `warn`. That's a sensible default but the
  visual hierarchy gives it equal weight to assertion-kind — could
  collapse into a secondary "Advanced" row.
- After Run-all the verdict card doesn't visibly appear in the
  fold-of-the-page (need to scroll); subjectively unclear whether
  the run succeeded until you hunt for the result.

**Verdict**: **polish**.

### S10 — Interop tab

[Snapshot](2026-05-30-data-product-cluster/screenshots/16_w2_interop_tab.png)

**Verdict**: **ship** (render-check; not deeply exercised).

### S11 — Activity tab

[Snapshot](2026-05-30-data-product-cluster/screenshots/17_w2_activity_tab.png)

**Verdict**: **ship** (render-check; no audit rows yet on fresh seed).

---

## Wave 3 — Admin surfaces

### S12 — /admin/policy-modules

[Loaded](2026-05-30-data-product-cluster/screenshots/18_w3_policy_modules.png)

**Was funktioniert**: Page renders, "New module" modal opens,
list-table is in place with the right columns (Name, Version,
Enabled, Updated, Actions).

**Was reibt**
- **Alpine throws a JS error on first paint**: `can't access
  property "error_class", testResult is null`. The Test-modal's
  conditional rendering of an error-class label doesn't null-check
  `testResult` (see BUG-30-07). Page is still usable but the error
  is logged.
- Empty-state for the list is just "No modules yet" — could
  promote the "New module" affordance more aggressively
  (e.g. tip about Cedar syntax + a stub policy as starting point).
- The decisions-log modal needs an existing module to be
  meaningful; without seeding the page is mostly inert.

**Verdict**: **polish**.

### S13 — /admin/mesh-dashboard

[Loaded](2026-05-30-data-product-cluster/screenshots/19_w3_mesh_dashboard.png)

**Was funktioniert**: 4 vital-signs cards (Green / Red / Unknown /
Pass-rate) render with seed values. Cost-by-product + top-consumers
tables are present.

**Was reibt**
- Vital-signs cards are color-coded (green/red/grey) but the
  numbers are tiny relative to the card. Inverting the type-scale
  would make the at-a-glance read instant instead of squinting.
- No date-range selector — the user can't ask "last 24h" vs "last
  7d", they get whatever the rollup default is.
- No drill-down on a domain row — `per_domain.pass_rate=0.5` for
  `(unknown)` is exposed as a number but you can't click to filter
  the cost table.

**Verdict**: **polish**.

### S14 — /admin/entity-discovery

[Loaded](2026-05-30-data-product-cluster/screenshots/20_w3_entity_discovery.png)

**Was funktioniert**: Page loads, pending-queue table + "Run now"
button visible.

**Was reibt**
- Empty-state shows no candidates because the discovery job hasn't
  been run yet — but there's no inline link to actually trigger it
  from this page. The "Run now" button IS there but its position
  in the toolbar is ambiguous (does it run discovery, or fetch the
  list? read the help text and find out).

**Verdict**: **ship** — the surface is honest about the empty
state.

### S15 — /admin/data-product-apply

[Loaded](2026-05-30-data-product-cluster/screenshots/21_w3_data_product_apply.png)

**Was funktioniert**: YAML textarea + Plan + Apply buttons in
place; output area below ready to receive diff/outcome.

**Was reibt**
- Textarea is a plain `<textarea>` — no syntax highlighting, no
  validation hint, no template / "load existing product" affordance.
  For an admin "apply YAML" surface the expectation is at least an
  example.
- Without a stub spec the user has no anchor to start from. A
  "Load demo.sales as starting YAML" button would lift the surface
  out of cold-start hell.

**Verdict**: **polish**.

### Admin index (context)

[Loaded](2026-05-30-data-product-cluster/screenshots/22_admin_index_cards.png) — for completeness; cards 1-4 link to S12-S15.

---

## Wave 4 — Deep-dive workflows

### S04 — Cost & quota deep-dive (Governance tab)

Verified the strict-mode round-trip end-to-end:
1. Load Governance tab — Active quota mode badge: `off`.
2. Quota-enforcement select → `strict`; Max cost / day → `10`;
   Max queries / hour → `100`.
3. Click "Save policy" (the shared button at the bottom of the
   Policy card — see BUG-30-08 in the bug log; the lack of a
   per-card save button is the deep-dive's main finding).
4. PUT `/api/data-products/demo/sales/policy` → 200 OK.
5. Discovery envelope reload returns `policies.quota_enforcement
   = strict`, `policies.max_cost_per_day = 10`, `policies.max_queries_per_hour = 100`.
6. Active quota mode badge after reload: `strict`. ✓

**Verdict for the deep dive**: substrate ships; surface polish
needed for the "save button lives in another card" trap.

### S05 — Contract Tests deep-dive

Verified the declare → run round-trip end-to-end:
1. Mode select → `synthetic`.
2. Declare:
   - Name: `row_count_smoke`.
   - Assertion kind: `row_count_range`.
   - Severity: `warn`.
   - Spec JSON: `{"min": 0, "max": 10000}`.
3. Submit → POST `/api/data-products/demo/sales/contract-tests` →
   200 OK; row appears in the table; Run-all button becomes
   enabled.
4. Run-all → POST `/api/data-products/demo/sales/contract-tests/run?mode=synthetic` →
   200 OK. No visible verdict card in-fold (see Reibung-Punkt
   above).

**Verdict**: substrate ships; surface polish needed for the
form-field ordering + run-result visibility.

### S03 — Schema-Versioning deep-dive (Output Ports panel)

**Blocked** — see BUG-30-04 + BUG-30-06 in the bug log. The
Versions button on a freshly-created output port fires the
versions-list fetch (GET `/output-ports/1/versions` → 200), but
the drawer modal renders inline as a giant card instead of as an
overlay. The form is inaccessible because clicking anything inside
the inlined modal scrolls the page weirdly and the "Propose bump"
form fields aren't reachable via test-runner without programmatic
intervention.

[Inline-modal screenshot](2026-05-30-data-product-cluster/screenshots/11_w4_schema_drawer_BUG_renders_inline.png)

**Verdict**: blocked until BUG-30-04 + BUG-30-06 are fixed.

---

## Cross-cutting findings

- **`init()` double-fire is the largest single performance + UX
  defect**: every Alpine factory on the data-product page fires
  `init()` twice because the templates use both
  `x-init="init()"` and an `async init()` method (Alpine 3 calls
  the method automatically). Result: every API call on the page
  fires 2-8 times. Half the network traffic on every load is
  wasted, and the duplicate toasts ("no DataProduct at
  undefined…") are a direct downstream symptom.
- **Modal pattern inconsistency**: the new Schema-Versioning
  modal uses `x-show + d-block`; existing in-tree modals use
  `:class="{ 'show d-block': flag }"` (the documented pattern in
  the memory rule). Fixing the new one to match makes it work.
- **Save-button discoverability**: in three different cards on the
  Governance tab the editor lives in one card and the save button
  lives in another. Either move the save next to the editor in
  each card, or be explicit ("Save all policy + quota changes").
- **Form-row layout drift**: the new Contract-Tests Declare form
  has the JSON spec field after the submit button; older forms
  have a roughly consistent left-to-right `input → input → button`
  shape. A one-row layout audit would tidy this.
- **Spurious toasts are noise users learn to ignore** — once we
  silence the "undefined.undefined" trap, the bar for *legitimate*
  toasts (Save successful / Run failed) goes up, not down. Worth
  doing.

---

## Bug Log

| Marker | Severity | Surface | Reproduce | Suspected fix |
|---|---|---|---|---|
| **BUG-30-01** | medium | every detail-page factory | Open any `/data-products/<c>/<s>`, watch network tab — every endpoint fires 2× minimum | Remove `x-init="init()"` from every partial in `frontend/templates/pages/_partials/data_product/`. Alpine 3 calls a method named `init` automatically. ~14 partials to edit. |
| **BUG-30-02** | trivial (inline-fix) | social_drawer.html → issuesPane | Open any detail page, see two `"no DataProduct at undefined.undefined in workspace 1"` toasts | [social_drawer.html:62](../../../frontend/templates/pages/_partials/data_product/social_drawer.html#L62) uses `product.catalog_name + "." + product.schema_name`; the keys on `product` are `catalog` + `schema` (see [data_product.js:141](../../../frontend/js/pages/data_product.js#L141)). 2-char fix. |
| **BUG-30-03** | trivial (inline-fix) | issuesPane factory | Same as BUG-30-02 — root cause raises a 404; issuesPane does not silence it | Add `silent: true` to the fetch in `frontend/js/partials/issues_pane.js` (or wherever the issuesPane factory lives) so legit 404s don't toast. |
| **BUG-30-04** | medium | tab_overview.html Schema-Versioning drawer | Overview tab → add output port → click "Versions" — modal does not display as overlay, content renders inline | [tab_overview.html:247-248](../../../frontend/templates/pages/_partials/data_product/tab_overview.html#L247) uses `x-show + :class="{ 'd-block': … }"`. Memory rule [[feedback_bootstrap_modal_x_show]] is to use `:class="{ 'show d-block': … }"`. Switch to that. |
| **BUG-30-05** | small | tab_overview.html + tab_lineage.html | `dataProductPortsPanel` is instantiated on **both** the Overview tab and the Lineage tab. Both keep independent state, so the Versions drawer state set in Overview doesn't apply to the Lineage instance | Either factor out the Schema-Versioning drawer markup to a single partial that lives outside both tabs, or accept the duplication and document it. |
| **BUG-30-06** | small | duplicate of 04 | — | — (merged into 04) |
| **BUG-30-07** | small (inline-fix) | /admin/policy-modules | Open page, dev-console shows `can't access property "error_class", testResult is null` | Guard the expression: `testResult ? '(' + testResult.error_class + ')' : ''` in the policy-modules template, OR initialise `testResult` to `{ effect: '', error_class: '' }` in the JS factory. |
| **BUG-30-08** | UX / design | tab_governance.html Cost & quota card | Save button for Cost & quota fields lives in the unrelated Policy card | Either move a "Save quota" button into the Cost & quota card, or rename the Policy-card button to "Save policy + quota". |

---

## Inline Fixes Applied

(See the `fix(ui): inline fixes from data-product-cluster ux audit`
commit immediately following this report.)

- **BUG-30-02**: `social_drawer.html:62` → `product.catalog` /
  `product.schema`.
- **BUG-30-03**: `issuesPane` fetch wrapped in `{ silent: true }`.
- **BUG-30-04**: tab_overview Schema-Versioning modal class
  updated to `:class="{ 'show d-block': versionDrawerOpen }"`,
  `x-show` removed.
- **BUG-30-07**: policy-modules template `testResult.error_class`
  guarded.

The rest (BUG-30-01 codebase-wide `x-init` cleanup, BUG-30-05
duplicate-mount factoring, BUG-30-08 button placement) deferred —
each touches multiple partials and warrants its own commit with
deliberate regression testing.

---

## Recommendation

- Land the inline-fix commit immediately; it removes the loudest
  noise from every detail-page load.
- **Next phase candidates** (≥ 1 commit each):
  - **`fix(ui): remove redundant x-init="init()"`** — codebase-wide
    sweep, ~14 partials. Will halve the API traffic on every
    detail-page load.
  - **`fix(ui): governance Cost & quota card save-button placement`**
    — small but high-discoverability win.
  - **`feat(ui): contract-tests declare-form layout polish`** —
    reorder fields, group severity into an advanced row.
  - **`feat(ui): data-product-apply YAML starter template`** —
    "Load demo.sales as YAML" affordance.
- **Wontfix candidates**:
  - The Overview tab's 13-card length — collapsing groups would
    feel cleaner but the information density is already a net
    positive; defer.
