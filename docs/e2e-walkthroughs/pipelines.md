# Declarative pipelines walkthrough

> **Mode:** `browser` · **Surface:** /pipelines + /pipelines/{slug}

End-to-end exercise of the declarative-pipeline surface: create a
pipeline with a materialized view and a streaming table, watch the
first run backfill both, append source rows and verify the
streaming table picks up only the increment, and see an
expectation drop violating rows with its violation badge.

## Preconditions

- E2E stack up + seeded (see [admin-secrets.md](admin-secrets.md)
  for the compose commands); [`auth.md`](auth.md) ran first.
- A seeded source table with a numeric column exists (check
  `scripts/seed-e2e.py` for an `e2e.*` table; the steps below call
  it `e2e.demo.orders` with an `amount` column — substitute the
  real seeded FQN).
- The streaming-table steps need the source to carry
  `delta.enableChangeDataFeed=true`; if the seeded table does not,
  create one from a notebook first
  (`PQL` write with `configuration={"delta.enableChangeDataFeed": "true"}`).

## Walkthrough

### Part A — Create + first run (4 steps)

1. **Land on the list**.
   - Action: `browser_navigate('http://127.0.0.1:8000/pipelines')`.
   - Assert: title `Pipelines · PointlesSQL`, heading "Pipelines",
     empty-state row "No pipelines yet."

2. **Create the pipeline**.
   - Action: click "New pipeline"; title `E2E Revenue`, first
     dataset target `e2e.gold.revenue`, first dataset SELECT
     `SELECT sum(amount) AS revenue FROM e2e.demo.orders`; click
     "Create".
   - Assert: redirect to `/pipelines/e2e-revenue-…` (slug carries a
     random suffix); the dataset card shows the target, kind
     "Materialized view", and the SELECT.

3. **Add a streaming table with a drop expectation**.
   - Action: click "+ Dataset"; target `e2e.gold.events`, kind
     "Streaming table", SELECT
     `SELECT * FROM e2e.demo.orders`; click "+ Expectation" on that
     card: name `positive_amount`, constraint `amount > 0`, action
     "drop violating rows". Click "Save definition".
   - Assert: toast "Pipeline definition saved."

4. **Run it**.
   - Action: click "Run now"; wait for the button to re-enable.
   - Assert: the Runs table gains run `#1` with a green `ok` badge;
     the metrics cell lists both datasets with row counts, and the
     `positive_amount: N` badge is grey (0) or yellow (>0) matching
     the seeded data.

### Part B — Incremental + governance (3 steps)

5. **Append source rows** (notebook or SQL editor):
   one row with a positive `amount` and one with a negative
   `amount` into `e2e.demo.orders`.

6. **Run again**.
   - Action: back on the pipeline page, click "Run now".
   - Assert: run `#2` shows the streaming table with exactly
     **1 row written** (the negative row was dropped — its
     `positive_amount` badge shows `1`), while the materialized
     view recomputes in full.

7. **Run a third time without new data**.
   - Action: click "Run now".
   - Assert: run `#3` shows the streaming table as "— no new data"
     (skipped) and status stays `ok`. Console clean throughout.

### Part C — Validation guard (1 step)

8. **Reject a cycle**.
   - Action: edit the materialized view's SELECT to read
     `e2e.gold.events`, and the streaming table's SELECT to read
     `e2e.gold.revenue`; click "Save definition".
   - Assert: a red alert names the cycle; the definition is NOT
     saved (reload shows the previous SQL).
