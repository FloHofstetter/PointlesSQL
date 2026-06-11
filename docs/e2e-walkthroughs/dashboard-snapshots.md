# Dashboard schedules & snapshots walkthrough

> **Mode:** `browser` · **Surface:** /bi/{slug} (schedule + snapshots)

Exercise scheduled dashboard snapshots: schedule a dashboard,
capture a manual snapshot, open the read-only snapshot page, and
verify the in-app delivery.

## Preconditions

- E2E stack up + seeded; [`auth.md`](auth.md) ran first.
- A BI dashboard with at least a counter and a table widget exists
  (see [bi-dashboards.md](bi-dashboards.md) Part A — reuse it).

## Walkthrough

### Part A — manual snapshot (3 steps)

1. **Open the dashboard** and find the new **Schedule** button and
   **Snapshots** drawer (owner view).

2. **Snapshot now**.
   - Action: open Snapshots → "Snapshot now".
   - Assert: a snapshot row appears (captured_at, `manual`).

3. **Read-only snapshot page**.
   - Action: click the snapshot row.
   - Assert: `/bi/<slug>/snapshots/<id>` renders the dashboard
     title with the captured widget data (counter value + table
     rows) — edits are impossible, the data is the stored payload
     (mutate the source table and reload: the snapshot does NOT
     change).

### Part B — schedule + delivery (2 steps)

4. **Schedule it**.
   - Action: Schedule modal — cron `*/1 * * * *` (e2e cadence),
     active, in-app delivery on; save.
   - Assert: a backing job (kind `bi_snapshot`) exists under
     `/jobs`; after ~a minute a `schedule`-triggered snapshot
     appears in the drawer.

5. **Delivery**.
   - Assert: the owner's bell inbox carries a
     "snapshot created"-style notification deep-linking to the
     snapshot page. Deactivate the schedule afterwards.
