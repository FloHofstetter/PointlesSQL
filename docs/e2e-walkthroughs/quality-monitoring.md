# Quality monitoring walkthrough

> **Mode:** `browser` · **Surface:** /quality

Exercise table quality monitors: create a monitor on a seeded
table, run a baseline scan, mutate the table into an anomaly
(volume drop), and watch the anomaly appear, then resolve.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first (admin —
  monitor creation is admin-gated, viewing is not).
- A seeded Delta table with ≥100 rows the test may rewrite (create
  a scratch copy from a notebook if unsure; the steps call it
  `e2e.demo.orders_scratch`).

## Walkthrough

### Part A — monitor + baseline (3 steps)

1. **Land on the page**.
   - Action: `browser_navigate('http://127.0.0.1:8000/quality')`.
   - Assert: heading "Quality", empty monitor list, create form
     visible for the admin.

2. **Create the monitor**.
   - Action: target `e2e.demo.orders_scratch`, cron `*/5 * * * *`,
     create.
   - Assert: monitor row appears (target, cron, active); a hidden
     backing job exists under `/jobs` (kind `quality_monitor`).

3. **Baseline scan**.
   - Action: click "Run now"; reload.
   - Assert: the monitor detail shows a snapshot for the table
     (row count, column count, captured_at); zero anomalies.

### Part B — anomaly lifecycle (3 steps)

4. **Provoke a volume drop**.
   - Action: from a notebook, overwrite the scratch table with
     <50 % of its rows (`pql.write_table(..., mode="overwrite")`).

5. **Detect**.
   - Action: "Run now" again; reload.
   - Assert: an anomaly appears — kind `volume_drop`, severity
     `critical`, observed/expected row counts; a second "Run now"
     does **not** duplicate it (open anomalies dedupe).

6. **Resolve**.
   - Action: restore the original row count from the notebook;
     "Run now"; reload.
   - Assert: the anomaly row carries a resolved badge/timestamp.
