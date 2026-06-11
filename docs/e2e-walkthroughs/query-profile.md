# Query profile walkthrough

> **Mode:** `browser` · **Surface:** /sql (Profile button + panel)

Exercise the runtime-profile mode of the SQL editor: run a SELECT
with profiling enabled, read the per-operator breakdown, confirm the
rows still arrive, and verify the profile persists on the history
row.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first.
- A seeded table with a handful of rows (the steps call it
  `e2e.demo.orders` — substitute the real seeded FQN).

## Walkthrough

### Part A — Profile run (3 steps)

1. **Land on the editor**.
   - Action: `browser_navigate('http://127.0.0.1:8000/sql')`.
   - Assert: heading "SQL"; toolbar carries Run, Explain, and the
     new **Profile** button (speedometer icon).

2. **Run with profile**.
   - Action: type
     `SELECT status, count(*) AS n FROM e2e.demo.orders GROUP BY status ORDER BY n DESC`
     into the editor; click **Profile**.
   - Assert: the result table renders the grouped rows (this is a
     real run, not a plan dump); above the table a
     "Runtime profile" panel lists operators slowest-first, each
     row with a name (e.g. `TABLE_SCAN`, `HASH_GROUP_BY`), a bar, a
     `… ms · …%` figure, and a row count; the header shows
     "`N` operators · `X` ms measured".

3. **Plain run has no panel**.
   - Action: click **Run** (same SQL).
   - Assert: rows render, no "Runtime profile" panel.

### Part B — Persistence + guards (2 steps)

4. **History row carries the profile**.
   - Action: query the metadata DB (or `GET /api/...` via the
     history surface): latest `query_history` row for the SQL.
   - Assert: `status = succeeded` and `profile_json` is non-NULL
     JSON for the profiled run; the plain run's row has
     `profile_json` NULL.

5. **Non-SELECT is rejected**.
   - Action: POST `/api/sql/execute` with
     `{"sql": "DROP TABLE e2e.demo.orders", "profile": true}`.
   - Assert: HTTP 400, detail mentions profiling is SELECT-only
     (the table is untouched).
