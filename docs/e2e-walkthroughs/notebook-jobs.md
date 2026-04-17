# Notebook jobs walkthrough

Exercises the Sprint 24 Papermill executor: create-job modal with
`kind=papermill`, a single-notebook Run-now that writes the executed
output under `notebooks/runs/{run_id}.ipynb`, the "Open in JupyterLab"
link on the runs table, the `POINTLESSQL_PRINCIPAL` env-var hand-off
from scheduler to kernel, and the negative paths (missing path, `..`
traversal, cell failure).

## Preconditions

- Stack up with the e2e overlay; seed script run (Sprint 22).
- `POINTLESSQL_JUPYTER_ENABLED=true` (default from the overlay — the
  link on the runs table points at the embedded JupyterLab).
- `POINTLESSQL_SCHEDULER_TICK_SECONDS=2` (overlay default; see
  `pointlessql/settings.py:59`).
- `admin@pql.test` and `user@pql.test` exist (`auth.md`).
- `notebooks/smoke_papermill.ipynb` is present. Extend
  `scripts/seed-e2e.py` to write a minimal notebook when absent —
  the body needs a parameters-tagged cell plus one cell that imports
  `pql` and prints `os.environ['POINTLESSQL_PRINCIPAL']`, so the
  principal hand-off can be observed in the output:

  ```json
  {
   "cells": [
    {"cell_type": "code", "metadata": {"tags": ["parameters"]},
     "source": ["message = \"hello\"\n"], "outputs": [], "execution_count": null},
    {"cell_type": "code", "metadata": {},
     "source": [
       "import os\n",
       "from pointlessql.pql import PQL\n",
       "print('principal=', os.environ.get('POINTLESSQL_PRINCIPAL'))\n",
       "print('message=', message)\n",
       "print('catalogs=', PQL().list_catalogs())\n"
     ],
     "outputs": [], "execution_count": null}
   ],
   "metadata": {"kernelspec": {"name": "python3", "display_name": "Python 3"}},
   "nbformat": 4, "nbformat_minor": 5
  }
  ```

- Currently logged in as `admin@pql.test`.

## Walkthrough

### Part A — create a Papermill job via the modal

1. **Navigate to `/jobs`**.
   - Action: `browser_navigate('http://127.0.0.1:8000/jobs')`.
   - Assert: URL is `/jobs`, "New job" button visible (admin-only).

2. **Open `#createJobModal`, flip `kind` to Papermill**.
   - Action: click "New job"; then
     ```js
     const d = Alpine.$data(document.querySelector('#createJobModal'));
     d.kind = 'papermill';
     ```
   - Assert: the DAG textarea hides
     (`browser_evaluate(() => document.querySelector('textarea[x-model="tasks"]').offsetParent === null)`
     returns `true`); the notebook path + parameters inputs become
     visible (`x-show="kind === 'papermill'"` branches).

3. **Submit a Papermill job**.
   - Action:
     ```js
     d.name = 'smoke_papermill';
     d.cron = '0 0 1 1 *';           // never auto-triggers
     d.notebookPath = 'smoke_papermill.ipynb';
     d.parametersJson = '{"message": "from-walkthrough"}';
     await d.submit();
     ```
   - Assert: `d.error === null`, browser navigates to
     `/jobs/{new_id}`. The Configuration card shows
     `Kind: papermill` and `Config: { notebook_path: "...",
     parameters: { message: "from-walkthrough" } }`.
   - Assert: the `POST /api/jobs` request body (captured via
     `browser_network_requests`) carries `kind: "papermill"` at the
     top level and `run_as_user_id` set to the current admin's id.

### Part B — Run now and verify the output artifact

4. **Trigger a manual run via the Alpine wrapper**.
   - Action:
     ```js
     await Alpine.$data(document.querySelector('[x-data*="busy"]'))
         .post('/api/jobs/{id}/run');
     ```
   - Wait ~5 s for the scheduler to pick it up and Papermill to
     spawn the kernel, execute both cells, and write the output.

5. **Assert the run succeeded and the output file exists**.
   - Assert:
     `fetch('/api/jobs/{id}').then(r=>r.json()).then(j=>j.id)`
     matches the created job id.
   - Action:
     ```js
     const runs = await fetch('/api/jobs/{id}/runs').then(r => r.json());
     return runs[0];
     ```
   - Assert: `runs[0].status === 'succeeded'`, `runs[0].trigger ===
     'manual'`, `runs[0].finished_at` is set.
   - Assert: JupyterLab serves the executed notebook. Via
     `browser_evaluate`:
     ```js
     const r = await fetch(
       `http://127.0.0.1:8888/lab/api/contents/runs/${runs[0].id}.ipynb`
     );
     return r.status;
     ```
     Returns `200`.

### Part C — Open in JupyterLab

6. **Reload `/jobs/{id}` and inspect the runs table**.
   - Action: `browser_navigate('http://127.0.0.1:8000/jobs/{id}')`.
   - Assert: the "Recent runs" table row for the succeeded run
     carries a new trailing column with an "Open in JupyterLab"
     button (`<a>` with class `btn-outline-primary`). For non-
     papermill jobs (e.g. a job created earlier in `jobs-dag.md`),
     no such button renders — the conditional is
     `{% if job.kind == "papermill" and run.status in ("succeeded",
     "failed") %}` in
     [frontend/templates/pages/job_detail.html](../../frontend/templates/pages/job_detail.html).

7. **Click "Open in JupyterLab"**.
   - Action: click the link. It opens a new tab pointing at
     `http://127.0.0.1:8888/lab/tree/runs/{run_id}.ipynb`.
   - Assert: the tab title shows the run file; the executed cells
     are visible with their outputs (kernel has already run via
     Papermill, not interactively).
   - Assert: the second cell's stdout shows
     `principal= admin@pql.test`, `message= from-walkthrough`, and a
     non-empty catalog list — confirming that
     `POINTLESSQL_PRINCIPAL` made it to the kernel and that `PQL()`
     inherited it (Sprint 24 wiring in
     [pointlessql/pql/pql.py](../../pointlessql/pql/pql.py)).

### Part D — negative cases

8. **Missing notebook path**. Back on `/jobs`, open the modal, set
   `kind='papermill'`, leave `notebookPath` empty, submit.
   - Assert: `d.error` contains `"notebook path is required"`
     (client-side guard), modal stays open.

9. **`..` traversal**. Set `notebookPath = '../secret.ipynb'`,
   submit.
   - Assert: POST `/api/jobs` returns 422, `d.error` contains
     `"escapes the notebooks directory"` (the executor rejects it
     at run-time, but the Job row is accepted — the first Run-now
     lands on the validation).
   - Note: the traversal check fires inside the executor (only
     when a run is actually scheduled), so the Job row *is*
     created. After a manual Run-now, the run status flips to
     `failed` with this error string. This is intentional — the
     API route does not speculate on executor-specific config
     shapes.

10. **Missing notebook file**. Submit with
    `notebookPath='does_not_exist.ipynb'`, then Run now.
    - Assert: run flips to `failed` with error
      `"papermill notebook not found: 'does_not_exist.ipynb'"`.
    - Assert: "Open in JupyterLab" link appears (status is
      `failed`), but clicking it 404s inside JupyterLab because
      no output was written.

11. **Cell that raises**. Temporarily add a second notebook
    `notebooks/bad_papermill.ipynb` with a cell that does
    `1 / 0`, create a Papermill job pointing at it, Run now.
    - Assert: run status is `failed`, error contains
      `"papermill execution failed in cell"` and
      `"ZeroDivisionError"` (the `PapermillExecutionError` ->
      `EngineError` conversion in
      [services/scheduler.py](../../pointlessql/services/scheduler.py)).
    - Assert: `notebooks/runs/{run_id}.ipynb` still exists (papermill
      writes the partial output before raising) and the offending
      cell shows the traceback when opened in JupyterLab.

## Playwright MCP script

```text
# Part A
browser_navigate('http://127.0.0.1:8000/jobs')
browser_click('#createJobModal trigger')        # "New job" button
browser_evaluate(async () => {
    const d = Alpine.$data(document.querySelector('#createJobModal'));
    d.kind = 'papermill';
    d.name = 'smoke_papermill';
    d.cron = '0 0 1 1 *';
    d.notebookPath = 'smoke_papermill.ipynb';
    d.parametersJson = '{"message": "from-walkthrough"}';
    await d.submit();
    return window.location.pathname;
})

# Part B — trigger + poll
browser_evaluate(async () => {
    await Alpine.$data(document.querySelector('[x-data*="busy"]'))
        .post('/api/jobs/{id}/run');
})
# wait 5s, fetch /api/jobs/{id}/runs, assert status=succeeded

# Part C — follow the JupyterLab link
browser_click('a[href*="/lab/tree/runs/"]')
browser_snapshot()                 # verify rendered executed cells

# Part D — negative cases repeat Part A's modal pattern
```

## Found bugs

_(Filled in during the live replay. Keep the same discipline as
Sprint 22/23: same-commit fixes where trivial, otherwise a
`BUG-24-NN` TODO with a named fix location.)_
