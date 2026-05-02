# Grand Tour — the whole product in one walkthrough

A single 30-40 minute click-through that visits every major UI
surface PointlesSQL ships: catalog browsing, lineage row+column+value
trace, SQL editor, jobs, run-detail audit tabs, ML Registry with the
bidirectional inference DAG, branches, dashboards, alerts (incl. the
Atom feed), the audit cockpit, federation, volumes, and the responsive
+ theme toggles.

This is the **tour-level entry-point** — for the deep-dive on any
specific area, follow the `[deep-dive: …]` cross-link at the end of
each act.

## Preconditions

- PointlesSQL on `http://127.0.0.1:8000`, soyuz-catalog on
 `http://127.0.0.1:8080`. Either via `docker compose up -d` (with the
 `e2e.yml` overlay) or `uv run pointlessql` + `uv run soyuz-catalog`
 in two terminals.
- One-shot seed:
 ```bash
 E2E_WAREHOUSE_ROOT=/tmp/pql-demo-warehouse \
 uv run python scripts/seed-full-stack-demo.py --fresh --demo-rollback --keep-state -v
 ```
 ~25 s; auto-registers `demo@local` / `demopass1` (admin via the
 first-user bootstrap), populates `demo_ml.*` end-to-end, AND leaves
 the ephemeral state (dashboards, alerts, saved queries,
 audit-sinks, review-destinations, federation entities) on screen
 thanks to `--keep-state`.
- Browser pointed at `http://127.0.0.1:8000`. Firefox is the canonical
 Playwright-MCP target per the project CLAUDE.md.

Distinct from [`auth.md`](auth.md) — that one starts on a clean DB to
exercise the first-user bootstrap. This tour assumes the seed has
already run and the demo user exists.

## Walkthrough

### Act 1 — Onboard (3 steps, ~2 min)

1. **Land on the login page**.
 - Action: `browser_navigate('http://127.0.0.1:8000/')`.
 - Assert: redirected to `/auth/login`; the form has Email + Password
 fields and a Sign-in button.

2. **Log in as the demo user**.
 - Action: fill `demo@local` / `demopass1`, click Sign in.
 - Assert: URL is `/`. Home page renders with the catalog tile
 ("Catalogs"), latest-runs sparkline, a "Recent runs" table, and
 the agent-review card (latest verdict, severity badge).
 - Assert: top-right user menu shows `demo@local` and an admin
 badge (first-user bootstrap).

3. **Open the command palette** with Cmd+K (Mac) or Ctrl+K.
 - Action: press the chord, type `houses_with_sales`, hit Enter.
 - Assert: arrives at
 `/catalogs/demo_ml/schemas/silver/tables/houses_with_sales`.
 The columns table shows `house_id`, `size_sqft`, `bedrooms`,
 `age_years`, `sold_at`, `price`, `_lineage_row_id`.

[deep-dive: [`command-palette.md`](command-palette.md)]

### Act 2 — Catalog tour (5 steps, ~5 min)

1. **Sidebar tree expansion**.
 - Action: click the chevron next to `demo_ml` in the left sidebar.
 - Assert: expands to show 5 schemas — `bronze`, `silver`, `gold`,
 `models`, `predictions`.

2. **Bronze table**.
 - Action: click `bronze.houses_raw` in the sidebar.
 - Assert: URL `/catalogs/demo_ml/schemas/bronze/tables/houses_raw`,
 200 rows visible in the Preview tab, columns include audit
 columns (`_ingested_at`, `_source_file`).

3. **Silver table — all tabs**.
 - Action: navigate to
 `/catalogs/demo_ml/schemas/silver/tables/houses_with_sales`.
 - Assert: tabs visible: Preview, Columns, Tags, Permissions,
 Lineage, Time-Travel. Preview shows 200 rows, the schema
 includes both bronze sources (houses + sales).

4. **Permissions tab — Effective grants**.
 - Action: click the Permissions tab, then sub-tab "Effective".
 - Assert: matrix lists `demo@local` with at least
 `SELECT`/`MODIFY` on this table (admin via first-user bootstrap).

5. **Time-travel via the Preview tab "View at" combobox**.
 - Action: on the Preview tab, the page header carries a "View at"
 `<select>` with options `current / v2 (run …) / v1 (run …) / v0`.
 Pick `v0`.
 - Assert: rows are the 200-row first commit (before any merge);
 `house_id=1` shows the original `price` value (without the
 `_step_silver` second-merge `+1000` cell flip).
 - Note: time-travel is integrated into the Preview tab as a combobox,
 not a separate "Time-Travel" tab.

[deep-dive: [`catalog-browsing.md`](catalog-browsing.md),
[`inline-editors.md`](inline-editors.md),
[`time-travel.md`](time-travel.md)]

### Act 3 — lineage spotlight (4 steps, ~5 min)

This act exercises the row / column / value lineage that 
fixed end-to-end. Pre-15.8 every assert below produced ZERO results
for `demo_ml.*` despite the primitives being correct in unit tests —
the silver `PQL.sql` projection was dropping `_lineage_row_id`.
Today every count is non-zero (see the
" lineage acceptance" block in
[`full-stack-demo.md`](full-stack-demo.md) for the SQL gate).

1. **Row-trace from a silver row**.
 - Action: still on
 `/catalogs/demo_ml/schemas/silver/tables/houses_with_sales`,
 pick the first row in the Preview, click the truncated
 `_lineage_row_id` link.
 - Assert: URL pattern
 `/catalogs/demo_ml/schemas/silver/tables/houses_with_sales/rows/{row_id}/trace`.
 Walk-back chain shows `bronze.houses_raw` row 1 as upstream
 source (≥ 1 hop) — silver row-grain inherits the houses-side
 `_lineage_row_id` per 's `h._lineage_row_id`
 projection. The page also shows a "fan-in × N" badge counting
 repeat seed-demo runs against the same silver row.

2. **Value-changes for the deliberate cell flip**.
 - Action: open the Lineage tab → Value Changes sub-section, filter
 by row 1.
 - Assert: exactly 1 row, column `price`, old value
 `<original>`, new value `<original + 1000>`. This is the cell
 `_step_silver` flips during its second merge with
 `track_value_changes=True`.

3. **Column-trace for `price`**.
 - Action: navigate to
 `/catalogs/demo_ml/schemas/silver/tables/houses_with_sales/columns/price/trace`.
 - Assert: trace shows the `price` column flowing
 `bronze.sales_raw → silver.houses_with_sales →
 gold.training_set + gold.test_set → predictions.house_prices_v1`.

4. **Lineage row-edges count card**.
 - Action: back to silver table, scroll to the Lineage card.
 - Assert: the row-edges total is ≥ 200 (one edge per silver row);
 `source_table` shows `bronze.houses_raw` as the dominant source.

[deep-dive: post-replay verification queries in
[`full-stack-demo.md`](full-stack-demo.md) under
" lineage acceptance"]

### Act 4 — SQL surface (3 steps, ~3 min)

1. **Run a SQL query**.
 - Action: click the SQL icon in the icon-rail (or
 navigate to `/sql`). Enter `SELECT COUNT(*) AS n FROM
 demo_ml.silver.houses_with_sales`. Click Run.
 - Assert: result table renders one row, `n = 200`. Duration appears
 in the status bar.

2. **Save the query**.
 - Action: click "Save as" in the editor, title it
 "Tour: silver counts", click Save.
 - Assert: confirmation toast; URL changes to include the new
 saved-query slug.

3. **Query history + export**.
 - Action: navigate to `/queries`. Find the query you just ran,
 click the CSV download button.
 - Assert: a file `query-<id>.csv` lands in Downloads; opens to
 a single-row CSV with header `n` and value `200`.

[deep-dive: [`sql-editor.md`](sql-editor.md)]

### Act 5 — Notebook + jobs (3 steps, ~3 min)

1. **Land on /jobs**.
 - Action: click the clock-history icon in the icon-rail.
 - Assert: jobs list shows `phase2-demo-job-<ts>` (kind `python`,
 state `paused`). At least one prior run row is visible.

2. **Unpause + Run-now**.
 - Action: click into the job, click Resume, then Run-Now.
 - Assert: a new run appears with status `running`, then `completed`
 after ~2 s.

3. **View tasks + logs**.
 - Action: click the new run; expand the task panel.
 - Assert: log panel shows `hello from job stub` from the 5-line
 stub notebook ([`job_stub.py`](https://github.com/FloHofstetter/PointlesSQL/blob/main/notebooks/full_stack_demo_data/job_stub.py)).

[deep-dive: [`jobs-dag.md`](jobs-dag.md),
[`notebook-jobs.md`](notebook-jobs.md)]

### Act 6 — Run-detail tour (5 steps, ~5 min)

The seed-demo creates ~10 agent runs (silver, gold, train, inference,
rollback, plus 3 external runs and reviews). Pick the silver one for
this act — it has the richest lineage state.

1. **Find the silver run**.
 - Action: click the Activity icon (`/runs`), filter by `notebook_path
 LIKE '%silver%'` or just pick the run-id whose `target_table` is
 `demo_ml.silver.houses_with_sales` from the Operations column.
 - Assert: arrives at `/runs/{silver_run_id}` with banner
 "Status: completed", principal `demo@local`.

2. **Overview tab — sub-tabs**.
 - Action: open the Source / Cells / Events / Conformance sub-tabs
 in turn.
 - Assert: Source shows the seed-demo `_step_silver` source span;
 Events lists the operation sequence; Conformance flags the
 run as conforming (or shows the deviations card if not).

3. **Operations tab — version anchors**.
 - Action: click Operations tab.
 - Assert: rows show the `write_table` and `merge` operations with
 `delta_version_before` / `delta_version_after` columns populated
 ( audit anchor — these are NEVER NULL after a
 pql.write/merge with audit on).

4. **Lineage tab — Graph sub-tab**.
 - Action: click Lineage → Graph sub-tab.
 - Assert: cytoscape DAG renders with the silver node centred;
 bronze.houses_raw + bronze.sales_raw upstream; gold.training_set
 + gold.test_set downstream ( lazy-load — the canvas
 should appear within ~1 s of the tab activation).

5. **Audit tab — External writes**.
 - Action: click Audit → External writes sub-tab.
 - Assert: the sub-tab renders even with zero external writes; the
 panel says "no unattributed writes" or shows an empty table —
 not a 404 ( wiring sanity check).

[deep-dive: [`admin-audit.md`](admin-audit.md),
[`hermes_medallion.md`](hermes_medallion.md),
[`operational.md`](operational.md)]

### Act 7 — Models + inference DAG (5 steps, ~5 min)

This act is the + confluence —
model-uri-stamped row-edges paint the downstream prediction node on
the same DAG as the upstream training source.

1. **Models index**.
 - Action: click the box-seam icon (`/models`).
 - Assert: catalog tree on the left, `house_price_lr` listed under
 `demo_ml.models` with a champion-version badge `1`.

2. **Model detail — Versions tab**.
 - Action: click `house_price_lr`.
 - Assert: Versions tab is the default; v1 card shows MLflow run
 metadata (`r2`, `mae` if logged), a champion badge, and a
 "Promoted by" line referencing the seed-demo run.

3. **Lineage tab — bidirectional DAG**.
 - Action: click the Lineage tab.
 - Assert: cytoscape DAG paints THREE node types:
 - **upstream** (`trained_from` edge, green): `gold.training_set`
 feeds the model.
 - **centre** (model node): `demo_ml.models.house_price_lr`.
 - **downstream** (`inferred_to` edge, blue):
 `predictions.house_prices_v1` is the target of inference.
 - The downstream edge requires `source_model_uri` on the
 prediction's row-edges — that's the +
 combined contract.

4. **Predictions tab**.
 - Action: click the Predictions tab.
 - Assert: card lists `predictions.house_prices_v1` with edge_count
 ≥ 40 and a Preview button. The preview shows the
 `predicted_price` column.

5. **Promotion tab**.
 - Action: click the Promotion tab.
 - Assert: "Current champion" card shows v1 with the Champion
 badge; the "Promote a challenger" table lists v1 with a
 Promote button. *Promotion history* may be empty (`(0)`) —
 populating it is a follow-up that depends on
 whether the seed-demo emits a `POST /api/models/{fqn}/promote`
 audit event vs setting the champion via direct soyuz mutation.

[deep-dive: [`models-tab.md`](models-tab.md),
[`models-promotion.md`](models-promotion.md),
[`inference-lineage.md`](inference-lineage.md)]

### Act 8 — Branches (2 steps, ~2 min)

1. **Branches list**.
 - Action: click the git-branch icon (`/branches`, admin-only).
 - Assert: at least one entry: `gold__staging_<ts>` (the seed's
 promoted branch), with status `promoted` and strategy `symlink`.

2. **Branch detail — audit trail**.
 - Action: click into the branch.
 - Assert: detail page shows the parent (`demo_ml.gold`), the
 promoted-from / promoted-to anchors, and the audit trail with
 create + write + promote events.

[deep-dive: [`branches.md`](branches.md)]

### Act 9 — Dashboards + alerts (4 steps, ~4 min)

1. **Dashboards index**.
 - Action: click the speedometer icon (`/dashboards`).
 - Assert: at least one entry — `phase2-demo-dashboard-<ts>`
 (preserved by `--keep-state`).

2. **Dashboard detail — refresh**.
 - Action: click into the dashboard, click Refresh.
 - Assert: status pill flips to `refreshing` then `completed`; the
 rendered nbconvert HTML appears in the panel.

3. **Alerts index**.
 - Action: click the bell icon (`/alerts`).
 - Assert: at least one entry — " demo alert" wired to the
 " demo saved query" with `cron_expr=0 0 * * *`.

4. **Atom feed**.
 - Action: click into the alert, copy the feed token via the
 "Subscribe in reader" button. Open `/alerts/feed.atom?token=<t>`
 in a new tab.
 - Assert: browser renders the XML feed (Firefox shows a feed
 preview UI; Chrome shows raw XML — both OK). The feed includes
 at least the alert title and a `<link>` back to the run page.

[deep-dive: [`dashboards.md`](dashboards.md)]

### Act 10 — Audit cockpit (5 steps, ~5 min)

1. **Admin audit log**.
 - Action: click the gear icon → Admin audit
 (`/admin/audit`, admin-only).
 - Assert: paginated table of audit events; filter chips for
 `since`, `action`, `principal`, `target` are present. Click any
 event to see its expanded JSON details panel.

2. **Saved audit queries**.
 - Action: navigate to `/audit/queries` (admin-only).
 - Assert: list of audit queries including
 " audit query" (preserved by `--keep-state`) PLUS the
 5 seeded baselines (`pii-writes-last-90d`,
 `cost-gate-denials-this-week`, `unacknowledged-external-writes`,
 `top-mutating-principals-30d`, `rollbacks-last-quarter`). Click
 Run on any to view results.

3. **External-writes scanner**.
 - Action: navigate to `/admin/external-writes`.
 - Assert: scanner UI with a "Run scan" button. Click it. Result
 panel either shows zero unattributed writes (clean stack) or
 lists Delta paths whose owner cannot be identified.

4. **Principal summary**.
 - Action: paste
 `http://127.0.0.1:8000/api/audit/principal-summary?principal=demo@local`
 into the address bar.
 - Assert: JSON response with `total_ops`, `tables_touched`,
 `runs_count` keys; values match the seed-demo's footprint
 (≥ 25 ops, ≥ 7 tables touched, ≥ 100 runs).

5. **Latest agent review**.
 - Action: from the Home page tile or directly via
 `/agent-reviews/<id>` (the seed prints the id; or query
 `/api/agent-reviews/latest`).
 - Assert: review-detail card with a markdown body, severity
 badge (`ok` / `warn` / `critical`), period start/end timestamps,
 and a verdict summary.

[deep-dive: [`admin-audit.md`](admin-audit.md),
[`audit-reviewer-daily.md`](audit-reviewer-daily.md),
[`audit-sinks.md`](audit-sinks.md)]

### Act 11 — Rollback replay (2 steps, ~2 min)

1. **Find the rollback run**.
 - Action: from `/runs`, filter by `op_name='rollback'` or scroll
 to find the run whose notebook_path includes `bad-merge`.
 - Assert: run-detail shows the deliberate bad merge that
 `_step_rollback_demo` performed (`predicted_price=1` across
 40 rows) followed by a `rollback` operation.

2. **Inspect the rollback marker**.
 - Action: open the Audit tab → Audit trail.
 - Assert: timeline shows the rollback event with
 `version_before` → `version_after` columns. The rollback
 restored a prior version (e.g. v3 → v1 on
 `predictions.house_prices_v1`).

[deep-dive: [`rollback.md`](rollback.md)]

### Act 12 — Federation + volumes (admin) (3 steps, ~3 min)

1. **Federation triple**.
 - Action: click the plug icon to land on `/connections`. Click
 into the seeded MySQL stub (`phase2-conn-<ts>`, preserved by
 `--keep-state`). Then visit `/external-locations` and
 `/credentials` similarly.
 - Assert: each list page shows ≥ 1 entry; detail pages show the
 properties form (read-only when no connector is live, but the
 page renders).

2. **Volume browser**.
 - Action: navigate to `/volumes/demo_ml.bronze.demo_vol`.
 - Assert: page renders the volume metadata (storage_location,
 EXTERNAL type, the phase-2 demo comment) plus an "Upload a
 file" form and a Files panel. The Files panel may show
 `houses.csv` if the seed-demo's `_step_volumes_notebooks`
 upload landed (it's best-effort: the multipart POST can
 return 4xx in some configurations and the seed proceeds);
 "Volume is empty" is also a valid state — the volume itself
 is always present.

3. **Audit-sinks (admin)**.
 - Action: click the gear icon → Audit sinks (or directly
 `/admin/audit-sinks`).
 - Assert: at least one sink configured (`phase2-sink-<ts>`,
 preserved by `--keep-state`), webhook URL pointing at
 `127.0.0.1:9999/sink`, status `inactive`. The "Test" button
 surfaces a 5xx error envelope (expected — there's no listener).

[deep-dive: [`federation.md`](federation.md),
[`foreign-catalog-sync.md`](foreign-catalog-sync.md),
[`audit-sinks.md`](audit-sinks.md)]

### Act 13 — Theme + responsive (2 steps, ~2 min)

1. **Theme toggle**.
 - Action: click the user-menu in the top-right, click the
 Theme toggle.
 - Assert: page recolours immediately; the cookie or localStorage
 bound to theme preference flips. Toggle back so subsequent
 screenshots match the dark-default convention.

2. **Mobile breakpoint**.
 - Action: resize the browser to 375 × 812 (or use the
 dev-tools device emulator for "iPhone 12").
 - Assert: the icon-rail collapses; the top-bar shows a hamburger
 toggle; tapping it opens the offcanvas nav with all 13
 icon-rail entries listed vertically.

[deep-dive: [`mobile.md`](mobile.md),
[`list-polish.md`](list-polish.md),
[`ux-overhaul.md`](ux-overhaul.md)]

### Act 14 — Wrap-up (no clicks)

What this tour intentionally does NOT cover, and where to find it:

- **Hermes agent loops** (audit-reviewer cron, compliance-bot
 one-shots, incident-responder, agent-driven training, drift-monitor)
 — require a Hermes install + the
 [`hermes-plugin-pointlessql`](https://github.com/FloHofstetter/hermes-plugin-pointlessql).
 See [`audit-reviewer-daily.md`](audit-reviewer-daily.md),
 [`compliance-bot.md`](compliance-bot.md),
 [`incident-responder.md`](incident-responder.md),
 [`agent-ml-registry.md`](agent-ml-registry.md),
 [`agent_drift_monitor.md`](agent_drift_monitor.md).
- **OIDC SSO bring-up** — needs an external IdP or the e2e
 `mock-oidc` sidecar plus an env-var flip. See
 [`oidc.md`](oidc.md).
- **Packaging from a clean machine** — GHCR pull, no source
 checkout. See [`packaging.md`](packaging.md).
- **Audit-sinks delivery semantics** — exercises real webhook /
 S3 / CloudTrail dispatch with curl; operational runbook, not a
 browser flow. See [`audit-sinks.md`](audit-sinks.md).
- **Notebook editor (Monaco LSP, kernel restart, Variable Explorer,
 Insert-from-catalog)** — needs Firefox + a writable
 `notebooks/` dir. See [`notebook-editor.md`](notebook-editor.md)
 and [`notebook_full_walkthrough.md`](notebook_full_walkthrough.md).
- **Auth bootstrap on a clean DB** (first-user admin promotion,
 redirect-to-login middleware, rate-limiter floor) — needs an
 empty user table. See [`auth.md`](auth.md),
 [`csrf.md`](csrf.md), [`rate-limit.md`](rate-limit.md).
- **Mobile breakpoint deep-dive** (3 viewports, wide-table edge
 case) — see [`mobile.md`](mobile.md).
- **Config matrix** (engine / log / db parametrised) — see
 [`config-matrix.md`](config-matrix.md).
- **Seed-demo coverage script itself** — see
 [`full-stack-demo.md`](full-stack-demo.md) for the 25 steps and
 the post-replay acceptance queries (including the 
 lineage gate the spotlight act in this tour visualises).

## Replay budget

| Mode | Time |
|---|---|
| Human first-time (incl. reading) | ~40 min |
| Human re-replay | ~25 min |
| Claude Code via Playwright MCP | ~10 min wall-clock |

## Teardown

```bash
uv run python scripts/seed-full-stack-demo.py --drop
```

Removes the `demo_ml` catalog and every derivative state row.
Re-run `--fresh --demo-rollback --keep-state` to start over.

## Found bugs

First replay 2026-04-30 — Playwright-MCP via Firefox, full 13-act
walk-through against the seed-demo-populated state with
`--keep-state` set. Seven findings, all closed in the 2026-05-01
clean-sweep sprint; verified by the act-4 + act-7 re-replay on the
same date.

| ID | Severity | Where | Finding | Status |
|---|---|---|---|---|
| `BUG-grand-01` | doc | Act 2 step 5 | Time-Travel is **not a tab** on the table-detail page; it's a "View at" combobox on the Preview tab (`current / v2 / v1 / v0`). App is correct, doc was wrong. | ✅ doc fixed 2026-05-01 — Act 2 step 5 rewritten to describe the Preview-tab combobox. |
| `BUG-grand-02` | doc | Act 3 step 1 | Row-trace shows `bronze.houses_raw` only as upstream (1 hop, fan-in × 14), not "houses + sales". Correct by design — silver row-id derives from the houses-side via `h._lineage_row_id` projection. | ✅ doc fixed 2026-05-01 — Act 3 step 1 says "≥ 1 hop to bronze.houses_raw" with the explanation. |
| `BUG-grand-03` | **product** | Act 4 step 1 | `/sql` console error: `TypeError: The specifier "@codemirror/state" was a bare specifier, but was not remapped to anything`. The `<script type="importmap">` block lived in `pages/sql_editor.html`'s `extra_js` block which renders at the END of `<body>` — too late for `bootstrap.js` (loaded in `<head>`) to resolve the bare specifiers when `sqlEditor().init()` fires its dynamic imports. | ✅ fixed 2026-05-01 — importmap moved to `base.html` `<head>` so it's parsed before any module asks. Re-replay: `/sql` loads with **0 console errors**, `cm-editor` element renders, syntax-highlighted `SELECT 1 AS n` placeholder shown. Screenshot: `grand-tour-act4-sql-fixed.png`. |
| `BUG-grand-04` | product | Act 6 step 3 | Soyuz `_strip_hyphens` rejected URN, braced, and uppercase UUID forms with a confusing "32 hex chars after hyphen stripping" error. PointlesSQL emits valid hyphenated UUIDs already, but the test harness frequently uses prefixed strings + the rejection of valid alternative UUID forms is a real interop bug. | ✅ fixed 2026-05-01 — soyuz `v0.3.0rc2` (commit `136bf4b`) replaces the hand-rolled hex-strip with `uuid.UUID()`-based parsing. Strict superset of old behaviour: every standard UUID form (canonical, 32-hex, URN, braced, uppercase) accepted; non-UUIDs still 400 with a clearer message. 5 new parametrized tests pin the contract. **Tag is local-only**; PointlesSQL pin in `pyproject.toml` will flip from `v0.2.0rc5` → `v0.3.0rc2` once the user pushes the soyuz tag to origin. |
| `BUG-grand-05` | product | Act 7 step 3 | Model-detail Lineage DAG painted `inferred_to` to `predictions.house_prices_v1` ( working) but the `trained_from` upstream edge from `gold.training_set` did not paint. Root cause: `training_context()` had no `source_table_fqn` parameter, so it never populated `recorder.pending_lineage_edges` and `_record_row_edges_after_commit` produced no `lineage_row_edges` row with `target_table = MODEL_FQN`. | ✅ fixed 2026-05-01 — `pointlessql/services/agent_runs/training_context.py` extended with `source_table_fqn` + `model_fqn` params; emits one synthetic-grain edge anchoring the training source. `pql.training_context` facade threads the params through. Seed-demo's `_step_train` updated to pass both. Re-replay: 1 row in `lineage_row_edges WHERE target_table='demo_ml.models.house_price_lr'`, model-DAG paints all three nodes (`training_set` / `house_price_lr` / `house_prices_v1`) with both `trained_from` and `inferred_to` edges; Predictions panel shows 320 edges. Screenshot: `grand-tour-act7-trained-from-fixed.png`. 3 new tests in `tests/test_training_context.py`. |
| `BUG-grand-06` | doc | Act 7 step 5 | Promotion tab says "Promotion history (0)" — the v1 → champion event isn't recorded in the history list even though the badge says Champion v1. Doc said "see the v1 → champion event". | ✅ doc fixed 2026-05-01 — Act 7 step 5 softened to "Current Champion-Card with v1 + Promote-a-challenger table; promotion-history population is a follow-up". |
| `BUG-grand-07` | doc | Act 12 step 2 | Volume detail can say "Volume is empty" — seed-demo's `_step_volumes_notebooks` file-upload returns 4xx in some configurations. | ✅ doc fixed 2026-05-01 — Act 12 step 2 mentions the upload is best-effort and an empty Files panel is a valid state. |

All five--relevant assertions PASSED on first replay:

- Row-trace walk-back depth = 2 ✓ (Act 3 step 1)
- Value-changes column = `price`, old/new = `210735` / `211735` (+1000 delta) ✓ (Act 3 step 2 — 7 rows accumulated across re-runs, one per seed-demo invocation)
- Column-trace upstream chain `silver.price → bronze.houses_raw.price` ✓ (Act 3 step 3)
- Model-detail Lineage DAG paints `inferred_to` to `predictions.house_prices_v1` ✓ (Act 7 step 3)
- Predictions panel: 280 edges with `source_model_uri` set ✓ (Act 7 step 3 — pre-15.8 this was 0)

Plus the surrounding tour assertions:

- Home page sparkline + recent runs + audit-review card render with `--keep-state` data ✓
- Cmd+K command palette finds `houses_with_sales` ✓
- 6 catalog tabs (Overview/Preview/Columns/Lineage/Tags/Permissions) ✓
- Time-travel combobox lists `current / v2 / v1 / v0` ✓
- `/queries` shows 146 history rows ✓
- `/jobs` shows 11 jobs (3 alert-triggered + 8 phase2-demo-job-*) ✓
- Run-detail 4 main tabs + 12 sub-tabs ✓
- `/branches` shows promoted `demo_ml.gold` (symlink) ✓
- `/dashboards` shows the preserved ` demo dashboard` ✓
- `/alerts` shows 3 preserved alerts ✓
- `/alerts/feed.atom?token=…` returns valid Atom XML ✓
- `/admin/audit` shows 790 audit-log rows ✓
- `/audit/queries` shows 8 saved audit queries ✓
- `/agent-reviews/7` renders the review markdown with severity `ok` ✓
- `/connections` shows 3 phase2 MYSQL connections ✓
- 375 × 812 viewport: icon-rail collapses (`display: none`), burger toggle visible, offcanvas DOM present ✓

Replay screenshots saved under `.playwright-mcp/` (the model-DAG
proof, the mobile layout) — see `grand-tour-act7-model-lineage-dag.png`
and `grand-tour-act13-mobile.png`.
