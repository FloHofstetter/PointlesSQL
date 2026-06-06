# Scheduler Task-Chain Editor — visual DAG authoring

> **Mode:** `live` · **Surface:** standalone Drawflow editor at `/jobs/{id}/dag`

Replays the path an operator takes when editing a job's task graph
visually instead of through the JSON `POST /api/jobs` shape: drop task
blocks, wire dependencies, edit each task's config, save, and overlay a
run's per-task status. The editor reuses the **same Drawflow shell** the
data-product canvas uses — the scheduler only supplies its own block
catalog (one block per runnable executor kind) and its own
persistence/validate/run-status bundles.

## Setup

1. Start PointlesSQL + soyuz-catalog (default ports):

   ```bash
   uv run soyuz-catalog          # terminal 1
   uv run pointlessql            # terminal 2
   ```

2. Create a job with a few tasks (or reuse one). The fastest seed is the
   JSON create endpoint — `depends_on` references task **names** here:

   ```bash
   curl -sX POST http://127.0.0.1:8000/api/jobs \
     -H 'Content-Type: application/json' \
     -b "$COOKIE" \
     -d '{"name":"etl-demo","cron_expr":"0 * * * *","tasks":[
           {"name":"extract","kind":"python","config":{"script":"x=1"}},
           {"name":"transform","kind":"python","depends_on":["extract"]},
           {"name":"load","kind":"pg_sync","depends_on":["transform"]}]}'
   ```

   Note the returned job `id`.

## Walkthrough

### Wave 1 — open the editor

1. Navigate to `/jobs/{id}` (the job detail page). Confirm the task
   table lists `extract → transform → load`.
2. Click **Edit DAG** (top-right action row). The URL becomes
   `/jobs/{id}/dag` and the Drawflow stage paints three task nodes wired
   `extract → transform → load`, auto-laid-out left-to-right.
3. Confirm the left palette lists one chip per runnable kind (Python,
   Pg Sync, Papermill, …) — fed live from `GET /api/jobs/{id}/_kinds`,
   so it never drifts from what the scheduler can execute.
4. The topbar shows `3 tasks · 2 dependencies` and a green **valid**
   badge. The browser console is clean.

### Wave 2 — edit a task

1. Click the `transform` node. The right drawer opens with its name,
   max-retries, backoff, and a Parameters (JSON) editor.
2. Change **Max retries** to `2`, set Parameters to `{"script": "y=2"}`.
   The node body summary updates (`transform · 2× retry`).
3. The topbar save-state flips to *Saving…* then *✓ Saved* (autosave),
   or click **Save**.
4. Reload the page — the change persisted (the editor re-reads the graph
   from `GET /api/jobs/{id}/canvas`).

### Wave 3 — add + wire a new task

1. Drag a **Python** chip from the palette onto the stage. A new
   unnamed task node appears.
2. Drag from the `load` node's right (`out`) pin to the new node's left
   (`deps`) pin. A dependency edge forms (a task may depend on many
   upstream tasks — every input pin accepts multiple wires).
3. Give the new task a name in the drawer, then **Save**. The editor
   reloads and the new node's id becomes `task-{pk}` — the server minted
   a real `JobTask` and the client-side id was remapped.
4. Confirm via `GET /api/jobs/{id}/canvas` that the new task + edge are
   present.

### Wave 4 — validation guardrails

1. Clear a task's name → the **valid** badge turns to *1 issue* and the
   bottom-left issue panel reads `name is required`.
2. Wire the graph into a cycle (drag `load → extract`). Save is rejected
   — the cycle never lands (the save runs `validate_dag` before commit
   and rolls back).
3. Restore a valid graph; the badge returns to **valid**.

### Wave 5 — run-status overlay

1. Back on `/jobs/{id}`, click **Run now**, then return to the DAG
   editor.
2. In the topbar run picker, select the latest run. Each node takes its
   `TaskRun` status tint (running / succeeded / failed / skipped),
   turning the editor into a live run monitor.
3. Select **No run overlay** to clear the tints.

### Wave 6 — live-loop safety

1. Trigger a run and, while a task is still `running`, open the editor
   and try to delete that task + Save.
2. Save is refused with *cannot delete task(s) with an in-flight run* —
   the canvas can never desync a job mid-execution.

## Notes

- There is **no graph store** for the scheduler: a job's `JobTask` rows
  *are* the document. Node positions are therefore not persisted; the
  editor lays the DAG out on load.
- An edge `A → B` means **B depends on A** (source `out` pin → target
  `deps` pin), matching the direction `validate_dag` / the topo-sort use.
- The editor is read-only for non-owners; only the job owner (or an
  admin) sees the palette and a writable Save.
