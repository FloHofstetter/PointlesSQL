# Browser Notebook editor walkthrough

> **Mode:** `browser` · **Phase:** 66 · **Surface:** `/notebooks/edit/{path}` cell-by-cell editor

End-to-end exercise of the resurrected notebook editor (Phases 66.0
→ 66.7).  Admin creates a notebook from the workspace tree, opens
the editor, runs Python / SQL / Markdown cells, lands an audit-trail
row, restarts the kernel, and replays a persisted output across a
page reload.

## Preconditions

- E2E stack up:
  ```bash
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml up -d
  docker compose -f docker/docker-compose.yml -f docker/docker-compose.e2e.yml \
    exec pointlessql python /app/scripts/seed-e2e.py
  ```
- [`auth.md`](auth.md) ran first.

## Walkthrough

### Part A — Create a notebook (3 steps)

1. **Open the workspace browser**.
   - Action: navigate to `http://127.0.0.1:8000/notebooks/workspace`.
   - Assert: page renders with the workspace file tree.

2. **Create `demo.py` via the create API**.
   - Action:
     ```bash
     curl -X POST http://127.0.0.1:8000/api/notebooks/create \
       -H 'Content-Type: application/json' -b cookies.txt \
       -d '{"path": "demo.py"}'
     ```
   - Assert: `201` response, body `{"path": "demo.py"}`.

3. **Open the notebook in the editor**.
   - Action: navigate to `http://127.0.0.1:8000/notebooks/edit/demo.py`.
   - Assert: `kernel: ready` pill flips on after the WebSocket
     handshake; one empty code cell renders.

### Part B — Run a Python cell (4 steps)

4. **Type and run a `print()`**.
   - Action: focus the empty cell, type `print('hello world')`,
     press `Shift+Enter`.
   - Assert: an output zone appears under the cell with
     `hello world`; cell badge flips to `[1]`.

5. **Run a multiline computation**.
   - Action: in the new cell that Shift+Enter created, type
     `x = sum(range(10))` then `x` on a second line,
     press `Shift+Enter`.
   - Assert: cell renders the integer `45` (the
     `text/plain`-mime execute_result frame).

6. **Verify an output is persisted**.
   - Action: hard-reload the page (`Cmd+Shift+R`).
   - Assert: both cells re-mount with the previously rendered
     outputs visible — no re-execute happens.  This validates
     the `notebook_outputs` replay path.

7. **Verify the cell-history popover**.
   - Action: click the clock-history icon on the first cell.
   - Assert: a popover lists the prior runs with status pill +
     timestamp + execution_count.  Click again to close.

### Part C — Run a SQL cell (3 steps)

8. **Convert the second cell to SQL**.
   - Action: click the cell-type dropdown (`code`) on the
     second cell → `SQL`.  Notice the `→ df` field appears in
     the toolbar.
   - Assert: editor remounts with SQL syntax highlighting.

9. **Run a SELECT against the seeded silver table**.
   - Action: replace the source with `SELECT n FROM main.public.foo`,
     press `Shift+Enter`.
   - Assert: the cell renders an HTML-formatted DataFrame
     preview underneath; no traceback.  (If the seed table is
     absent on your install, swap in any 3-part-qualified UC
     table you have SELECT on.)

10. **Verify the audit row landed**.
    - Action:
      ```bash
      curl -b cookies.txt 'http://127.0.0.1:8000/api/sql/history?limit=5' \
        | jq '.queries[0]'
      ```
    - Assert: the most recent row carries `notebook_path: "demo.py"`
      and a `notebook_content_hash` matching the SQL cell's badge.

### Part D — Run a Markdown cell + kernel restart (3 steps)

11. **Add and render a Markdown cell**.
    - Action: click `+ Markdown cell`, type `# Heading\n\nA
      paragraph`, press `Shift+Enter`.
    - Assert: the cell switches to view-mode, rendering
      `<h1>Heading</h1>` plus the paragraph; no code-cell
      execute happens.

12. **Restart the kernel**.
    - Action: click `Restart` in the top toolbar.  Re-run the
      first cell (`print('hello world')`).
    - Assert: previous live outputs cleared; new outputs appear;
      the kernel-status pill stays at `kernel: ready`; a fresh
      `kernel_session_id` is reflected (developer-tools console
      shows the post-restart `notify('ready')` frame).

13. **Save + verify file shape**.
    - Action: press `Cmd+S`.  Then on the host:
      ```bash
      cat docker-volume-or-host-mount/notebooks/demo.py
      ```
    - Assert: the file contains canonical jupytext markers —
      `# %%`, `# %% [markdown]`, `# %% [sql] df` — and is
      free of any PointlesSQL-specific tokens (no
      `pql_cell_id="..."`).  The file is generically
      VSCode/Vim-editable.

## Coverage

* `/api/notebooks/{create,rename,delete,load,save,render-markdown,cell-history}` REST routes.
* `/notebooks/edit/{path:path}` HTML editor page.
* `/ws/notebook/kernel` WebSocket — execute / interrupt / restart.
* Per-cell live + persisted output rendering.
* SQL-cell privilege check + `query_history` audit row.
* Markdown cell edit/view toggle.
* Cell management (add / delete / move / convert).
* Kernel restart clearing in-memory state.
