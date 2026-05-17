# Run-comparisons walkthrough

> **Mode:** `browser` · **Phase:** 18.4 · **Surface:** /runs/a/diff/b + /jobs/.../compare

PointlesSQL has TWO compare surfaces with similar names but
different routes, different audiences, and different tab
shapes. This playbook covers both end-to-end so a reader stops
mixing them up:

| Route | Page | Audience | Sprint |
|---|---|---|---|
| `/runs/{a}/diff/{b}` | [`agent_run_compare.html`](../../frontend/templates/pages/agent_run_compare.html) | Audit / agent supervision | 18.4 |
| `/jobs/{job_id}/runs/{a}/compare?with={b}` | [`run_compare.html`](../../frontend/templates/pages/run_compare.html) | Notebook job ops | 12.x |

The audit run-diff is structured: 6 tabs (Ops, Lineage, Rejects,
Tools, Cells, Column lineage) with Chart.js bar charts on the
Lineage and Rejects tabs. The jobs run-compare is unstructured:
a side-by-side of the two runs' rendered notebook iframes.

## Preconditions

- Stack up + seed:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-full-stack-demo.py \
    --fresh --demo-rollback --keep-state
  ```
  `seed-e2e.py` alone is NOT enough — both compare pages need
  ≥ 2 historical agent runs (audit) or ≥ 2 historical job runs
  (jobs) to have anything to diff.
- [`auth.md`](auth.md) (admin@pql.test signed in).
- [`jobs-dag.md`](jobs-dag.md) ran once in this stack (gives
  the jobs page two real runs against the same job).
- Playwright MCP Firefox lock-file gotcha: see CLAUDE.md
  line 227-235.

## Walkthrough

### Part A — Audit run-diff (8 steps)

1. **Pick two run IDs to compare**.
   - Action:
     ```js
     async () => (await (await fetch('/api/runs?limit=10',
       {credentials:'same-origin'})).json()).runs.slice(0,2).map(r=>r.id)
     ```
   - Assert: returns an array of two run IDs (UUIDs). Stash
     them as `RUN_A` and `RUN_B`.

2. **Land on the diff page**.
   - Action: navigate to `/runs/${RUN_A}/diff/${RUN_B}`.
   - Assert: title `Compare runs · PointlesSQL`. Heading reads
     "Compare runs" with the two run IDs in the breadcrumb.

3. **Verify all 6 tabs are present**.
   - Action:
     ```js
     () => Array.from(document.querySelectorAll('.nav-link[data-bs-target]'))
       .map(b => b.getAttribute('data-bs-target'))
     ```
   - Assert: returns `['#tab-ops', '#tab-lineage', '#tab-rejects',
     '#tab-tools', '#tab-cells', '#tab-column-lineage']` in that
     order. Default-active tab is Ops.

4. **Ops tab — added/removed/changed columns**.
   - Action: stay on the default Ops tab.
   - Assert: page renders three sub-cards or sections labelled
     "Added in B" / "Removed in B" / "Changed in B" with op
     diffs (op_name, target_table, params).

5. **Lineage tab — Chart.js render gotcha**.
   - Action: click "Lineage".
   - Assert (network): `GET /api/runs/${RUN_A}/diff/${RUN_B}`
     returns 200 with `lineage_charts` object containing
     `value_change_volume_per_table` and `row_count_delta_per_table`
     arrays.
   - Assert (canvas): both `<canvas>` elements have non-zero
     dimensions AFTER the tab is shown. The page guards against
     the tab-pane-display-none-renders-empty trap with a
     `shown.bs.tab` listener that re-fires `renderBars()` on
     first activation. If you see two grey rectangles instead of
     bars, the charts rendered while the tab was hidden — see
     screenshots `phase18-replay-11`/`12`/`13` for prior-art
     manual triggers.
   - Mitigation:
     ```js
     () => { document.querySelector('#tab-lineage-btn').click(); }
     ```
     then `browser_wait_for(time: 2)` before asserting canvas
     dimensions.

6. **Rejects tab — pattern-shift chart**.
   - Action: click "Rejects".
   - Assert (canvas): `chart-rejects` renders a stacked bar of
     `reject_pattern_shift` (per-reason changes between the two
     runs).

7. **Cells tab** (notebook-cell-level diff).
   - Action: click "Cells".
   - Assert: panels labelled "Added in B" / "Removed in B" /
     "Changed in B" with cell source previews. May be empty if
     both runs share the same notebook source.

8. **Column lineage tab**.
   - Action: click "Column lineage".
   - Assert: lists added/removed column-level edges between the
     two runs. Empty for runs with identical column lineage.

### Part B — Jobs run-compare (5 steps)

1. **Pick two job runs**.
   - Action: navigate to `/jobs`, click any job that has ≥ 2
     runs in its history table. The job-detail page shows the
     "Runs" table with each row's id; the page has a "Compare"
     UI affordance (per Sprint 12.x).
   - Assert: arrives at `/jobs/{job_id}` with at least 2 entries
     in the run history.

2. **Open the side-by-side compare**.
   - Action: select two runs and click "Compare", OR navigate
     directly to `/jobs/{job_id}/runs/{a}/compare?with={b}`.
   - Assert: title `Compare runs · {job_name} · PointlesSQL`.
     Two side-by-side cards, each with the run's metadata
     header (status badge, started, finished, duration, trigger)
     plus a 620px-tall iframe loading the run's rendered notebook.

3. **Verify both iframes load**.
   - Action:
     ```js
     () => Array.from(document.querySelectorAll('iframe'))
       .map(f => ({src: f.src, height: f.offsetHeight}))
     ```
   - Assert: returns two entries pointing at
     `/jobs/{job_id}/runs/{a}/notebook` and the same for `b`,
     each `height >= 600`.

4. **Spot a diff manually**.
   - The page header carries the explicit info banner: "Cell-
     level diffing is not implemented — this view is a side-by-
     side of two rendered runs. Eyeball outputs row-for-row, or
     download both ipynb files and diff locally."
   - Assert: `.alert.alert-info` block containing this exact
     text is present.

5. **Status badges differ on success/failure**.
   - Action: pick two runs where one succeeded and one failed
     (the seed-full-stack-demo seeds at least one failed run).
   - Assert: left card shows `bg-success badge`, right shows
     `bg-danger badge` (or whichever status combination matches
     the chosen pair).

## Playwright MCP script

Browser replay for both compare surfaces:

1. `browser_navigate('http://127.0.0.1:8000/runs')`
   — pick two recent run rows; capture their UUIDs as `A` and `B`.
2. `browser_navigate('http://127.0.0.1:8000/runs/<A>/diff/<B>')`
   — `browser_wait_for(".diff-tab-list")`; assert 6 top tabs.
3. `browser_click("Operations")`
   — `browser_evaluate('() => document.querySelectorAll("table tbody tr").length')` ≥ 1
   (the actual DOM uses standard `<table>` tbody rows, not a
   `.diff-row` class — see BUG-41-02).
4. `browser_click("Charts")`
   — `browser_wait_for("canvas")` (Chart.js renders); assert ≥ 1
   chart canvas is visible (Phase 18.4 prior-art mitigation).
5. `browser_click("Conformance")` — assert per-rule status pills.
6. `browser_navigate('http://127.0.0.1:8000/jobs/<job_id>/runs/<a>/compare?with=<b>')`
   — assert the side-by-side jobs run-compare loads.
7. `browser_evaluate('() => document.querySelectorAll(".compare-col").length')`
   — assert exactly 2 columns (left = a, right = b).

## Found bugs

- **BUG-41-02** ✅ Fixed in same edit — Sprint-D MCP script
  used `.diff-row` selector that doesn't exist in the rendered
  DOM. The compare page uses standard `<table>` rows for
  per-axis diffs (Operations / Tool calls / Queries / etc).
  Selector replaced with `table tbody tr`. Surfaced 2026-05-07
  during Phase 41 smoke replay; the page itself renders fine
  (4 metric cards across the top, 6 tabs in the tab list, A/B
  identity panels populated).

(none surfaced during the chrome-only smoke pass; the data path
in Part A steps 4-8 was not exercised in this session because
the e2e seed used was the lighter `seed-e2e.py`. The Chart.js
async-render mitigation in step 5 is documented from prior-art
screenshots but not freshly verified here. A follow-up replay
on `seed-full-stack-demo.py --demo-rollback --keep-state`
should land any new BUG-NN-NN here.)

## Cleanup

The compare pages are read-only — no cleanup needed.
