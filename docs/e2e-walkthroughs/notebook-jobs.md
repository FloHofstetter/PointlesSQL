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

### Part E — typed parameters UI (Sprint 25)

Exercises the `GET /api/notebooks/inspect` endpoint and the typed
form the create-job modal renders from its response. `seed-e2e.py`
drops `notebooks/smoke_typed_params.ipynb` whose `parameters`-cell
declares `count: int = 3`, `enabled: bool = True`, and
`label: str = "hello"` — one parameter per input-type branch the
modal handles.

12. **Open the modal, switch to papermill, click "Load parameters"**.
    - Action: navigate to `/jobs`, click "New job", then:
      ```js
      const d = Alpine.$data(document.querySelector('#createJobModal'));
      d.kind = 'papermill';
      d.name = 'smoke_typed_params';
      d.cron = '0 0 1 1 *';
      d.notebookPath = 'smoke_typed_params.ipynb';
      await d.inspect();
      return d.params.map(p => [p.name, p.inferred_type, p.value]);
      ```
    - Assert: the return is
      `[['count', 'int', 3], ['enabled', 'bool', true], ['label', 'str', 'hello']]`.
    - Assert: three rows render inside the "Parameters" card —
      a number input, a checkbox, and a text input. Count them by
      their Alpine binding, which is only set on the typed-form
      inputs (not on the form-fixed name/cron/notebookPath
      fields):
      ```js
      const inputs = Array.from(document.querySelectorAll('#createJobModal input[x-model="p.value"]'));
      return inputs.map(i => i.type);   // ['number', 'checkbox', 'text']
      ```
      Do *not* filter by `offsetParent !== null` on children of the
      `<details>` block — Firefox leaves the inner textarea in the
      flow even when the disclosure is closed, so that check is
      flaky across engines.

13. **Override the values and submit**.
    - Action:
      ```js
      d.params[0].value = 7;
      d.params[1].value = false;
      // d.params[2].value stays "hello"
      d.name = 'smoke_typed_params';
      d.cron = '0 0 1 1 *';
      d.submit();                    // don't await — reload fires on success
      ```
    - Assert: `POST /api/jobs` captured via
      `browser_network_requests(filter: '/api/jobs', requestBody: true)`
      carries
      `config.parameters = {count: 7, enabled: false, label: "hello"}`.
      `count` serializes as the integer `7` (not the string `"7"`)
      because `typedValue()` runs `parseInt` for `inferred_type ===
      'int'`. Avoid trying to `await d.submit()` — the handler's
      `window.location.reload()` tears down the evaluate context
      before the promise resolves.
    - Assert: the browser navigates to `/jobs/{new_id}`; the
      Configuration card's new **Parameters** block renders three
      rows — `count → 7`, `enabled → false`, `label → "hello"` —
      instead of the raw JSON `<pre>` blob used before Sprint 25.

14. **Run-now and verify the resolved overrides executed**.
    - Action: trigger Run-now the same way Part B does
      (`POST /api/jobs/{id}/run`).
    - Wait ~5 s for the scheduler tick, then reload
      `/jobs/{id}`. Assert the runs-table first row reads
      `succeeded` / `manual`.
    - Assert: the output notebook has the papermill-injected
      overrides. Fetch directly from the Jupyter contents API
      (note: path is `/api/contents/...`, not `/lab/api/...` —
      the latter returns the lab HTML shell):
      ```js
      const r = await fetch(`http://127.0.0.1:8888/api/contents/runs/${runId}.ipynb`);
      const nb = await r.json();
      return nb.content.cells[2].outputs[0].text;
      ```
    - Assert: the body cell's stdout reads `count= 7 int\nenabled=
      False bool\nlabel= hello str\n` — confirming the typed form's
      values made it through `config.parameters` into the papermill
      kernel with the right Python types.

15. **Advanced fallback — raw JSON still works**.
    - Action: re-open the modal, switch `kind` to papermill,
      expand the `<details>` "Advanced" block, tick
      "Use raw JSON below instead of the typed form", fill
      `parametersJson` with `{"count": 11, "enabled": true, "label": "raw"}`,
      submit without calling `inspect()`.
    - Assert: `POST /api/jobs` carries those three keys verbatim,
      with `count: 11` still an integer (the browser's `JSON.parse`
      preserves numeric type).
    - Assert: `d.useAdvanced === true` wins over any prior
      `d.params` array — `collectParams()` returns the parsed
      textarea, not the typed form.

16. **Negative — notebook does not exist**.
    - Action:
      ```js
      d.notebookPath = 'does_not_exist.ipynb';
      d.params = [];
      await d.inspect();
      return [d.paramsError, d.params.length];
      ```
    - Assert: `paramsError` contains
      `"papermill notebook not found: 'does_not_exist.ipynb'"`
      (the 422 JSON envelope bubbles up from `_wrap_catalog_errors`
      via the centralized handler), `params` stays empty, the
      typed-form block does not render.

17. **Negative — `..` traversal**.
    - Action: `d.notebookPath = '../secret.ipynb'; await d.inspect();`
    - Assert: `paramsError` contains `"escapes the notebooks directory"`.
      The inspect call is validated by the same
      `resolve_notebook_path` helper the executor uses, so the
      error string matches Part D's traversal negative.

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

No bugs surfaced in the Sprint 24 live replay against the e2e
overlay. All four parts and the four negative cases landed on the
error strings documented above with no surprises.

Live-run notes (no bugs):

- Part A: the modal's `kind` select exposes `dag` and `papermill`;
  flipping to `papermill` hides the DAG textarea
  (`offsetParent === null`) and reveals the `notebook_path` +
  `parameters` inputs. Submit built a payload with
  `kind: "papermill"` and `run_as_user_id` set to the current
  admin's id — verified by fetching `/api/jobs/{id}` after create.
- Part B: a seeded `smoke_papermill.ipynb` with a
  `parameters`-tagged cell + a body cell that prints
  `os.environ['POINTLESSQL_PRINCIPAL']` and
  `PQL().list_catalogs()` executed end-to-end in ~6.7 s. The
  output notebook at `/app/notebooks/runs/{run_id}.ipynb` carried
  `principal= <run-as-user-email>`, the papermill-injected
  `# Parameters` cell with the submitted override, and a
  catalog list served via the principal-forwarded client — all
  three layers of Sprint 24 (executor, env-var hand-off, PQL
  principal inheritance) verified at once.
- Part C: the runs-table row gains a trailing "Open in JupyterLab"
  cell with `href="http://<host>:8888/lab/tree/runs/{run_id}.ipynb"`.
  JupyterLab's contents API (`/api/contents/runs/{run_id}.ipynb`)
  returns the executed notebook JSON including the cell outputs.
- Part D: all four negative cases produced the expected error
  strings:
  - Missing `notebookPath` — client-side Alpine guard:
    `"notebook path is required"`, modal stays open, no POST.
  - `..` traversal — Job row *is* created (API doesn't speculate
    on executor-specific config), the Run-now landing flips
    status to `failed` with
    `"papermill notebook_path '../secret.ipynb' escapes the
    notebooks directory"`.
  - Missing file — same shape, error
    `"papermill notebook not found: 'does_not_exist.ipynb'"`.
  - `1 / 0` failing cell — status `failed` with
    `"papermill execution failed in cell 1: ZeroDivisionError:
    division by zero"`. The partial output at
    `notebooks/runs/{run_id}.ipynb` carries the full traceback
    in the offending cell's `outputs` array — visible when the
    "Open in JupyterLab" link is followed.
- Cross-check: the link renders on `failed` runs too, matching the
  `run.status in ("succeeded", "failed")` template guard.

### Sprint 25 — Part E live run

No bugs surfaced in the Sprint 25 live replay. All six Part E steps
produced the expected values on the first pass:

- Step 12: `GET /api/notebooks/inspect?path=smoke_typed_params.ipynb`
  returned `[{count, int, 3}, {enabled, bool, True}, {label, str,
  "hello"}]`; the modal rendered three `input[x-model="p.value"]`
  fields with types `number`, `checkbox`, and `text`. The `str`
  default was correctly stripped of its surrounding `"` quotes by
  the `coerceDefault` char-code check (34/39), so the text input
  carried `"hello"` without quote literals.
- Step 13: the captured `POST /api/jobs` request body carried
  `config.parameters: {"count": 7, "enabled": false, "label":
  "hello"}` with `count` as a JSON integer, confirming the
  `parseInt` branch of `typedValue()` wins over the default string
  coercion Alpine's `x-model` would have produced on the number
  input.
- Step 14: the output notebook at `/api/contents/runs/{rid}.ipynb`
  carried a papermill-injected `# Parameters` cell reading
  `count = 7`, `enabled = False`, `label = "hello"`, and the body
  cell's stdout was `count= 7 int`, `enabled= False bool`,
  `label= hello str` — end-to-end typed-form-to-kernel plumbing
  verified in a single job run (~2.8 s total).
- Step 15: advanced fallback — ticking the `<details>` checkbox
  and re-submitting with `parametersJson = '{"count": 11,
  "enabled": true, "label": "raw"}'` produced a POST body with
  those three keys verbatim; the prior `d.params` array was
  ignored because `collectParams()` short-circuits on
  `this.useAdvanced`.
- Steps 16/17: negative inspect calls against
  `does_not_exist.ipynb` and `../secret.ipynb` each landed the
  exact string the `resolve_notebook_path` helper raises
  (`papermill notebook not found: 'does_not_exist.ipynb'` and
  `papermill notebook_path '../secret.ipynb' escapes the notebooks
  directory`) in `d.paramsError`, and `d.params` stayed empty so
  no typed-form block rendered. The centralized error handler
  (Sprint 14) turned the `ValidationError` into the standard 422
  JSON envelope the Alpine `inspect()` method knows to unpack.
- Notable quirk found during the walk (not a bug, but pinned in
  the playbook): the Advanced `<details>` block's inner textarea
  has non-null `offsetParent` in Firefox even when the disclosure
  is closed, so "visible input" counts via `offsetParent !== null`
  are unreliable. Part E step 12 now targets
  `input[x-model="p.value"]` directly.
