# Notebook jobs walkthrough

Exercises the Papermill executor: create-job modal with
`kind=papermill`, a single-notebook Run-now that writes the executed
output under `notebooks/runs/{run_id}.ipynb`, the "Open in JupyterLab"
link on the runs table, the `POINTLESSQL_PRINCIPAL` env-var hand-off
from scheduler to kernel, and the negative paths (missing path, `..`
traversal, cell failure).

## Preconditions

- Stack up with the e2e overlay; seed script run.
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
 d.cron = '0 0 1 1 *'; // never auto-triggers
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
 [frontend/templates/pages/job_detail.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/job_detail.html).

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
 inherited it ( wiring in
 [pointlessql/pql/pql.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/pql/pql.py)).

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
 [services/scheduler.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/scheduler.py)).
 - Assert: `notebooks/runs/{run_id}.ipynb` still exists (papermill
 writes the partial output before raising) and the offending
 cell shows the traceback when opened in JupyterLab.

### Part E — typed parameters UI

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
 return inputs.map(i => i.type); // ['number', 'checkbox', 'text']
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
 d.submit(); // don't await — reload fires on success
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
 instead of the raw JSON `<pre>` blob used before.

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
browser_click('#createJobModal trigger') # "New job" button
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
browser_snapshot() # verify rendered executed cells

# Part D — negative cases repeat Part A's modal pattern
```

## Found bugs

No bugs surfaced in the live replay against the e2e
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
 three layers of (executor, env-var hand-off, PQL
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

### Part E live run

No bugs surfaced in the live replay. All six Part E steps
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
 turned the `ValidationError` into the standard 422
 JSON envelope the Alpine `inspect()` method knows to unpack.
- Notable quirk found during the walk (not a bug, but pinned in
 the playbook): the Advanced `<details>` block's inner textarea
 has non-null `offsetParent` in Firefox even when the disclosure
 is closed, so "visible input" counts via `offsetParent !== null`
 are unreliable. Part E step 12 now targets
 `input[x-model="p.value"]` directly.

## Part F — Output artifacts card

 lands an "Output artifacts" card on `/jobs/{id}` that
renders the executed notebook inline via nbconvert, with a toggle
between the static `Rendered` HTML and the interactive
`JupyterLab` iframe. The card auto-selects the most recent
completed run; clicking any row in the "Recent runs" table below
swaps the selection.

Precondition: Part E left a succeeded papermill run on disk at
`notebooks/runs/{run_id}.ipynb`. If the stack was restarted between
Part E and here, Run-now the `smoke_typed_params.ipynb` job once.

### Steps

1. `browser_navigate` to `/jobs/{id}` for the typed-params
 job (or any papermill job with a completed run).
2. `browser_snapshot` — confirm the DOM ordering is:
 1. "DAG tasks" card (if present)
 2. **"Output artifacts" card** (new; the header reads
 `Output artifacts · run #<rid>` once the Alpine `init()`
 auto-select fires)
 3. "Recent runs" card
3. Assert the iframe's `src` attribute equals
 `/jobs/{id}/runs/{latest_rid}/notebook` — this is the
 `viewMode === "rendered"` branch of `iframeSrc()`. The iframe
 body should contain the parameter injection cell's
 `count = 3 (int)` output line (or whatever the seed notebook
 prints).
4. Click the `JupyterLab` toggle button. `browser_wait_for` the
 iframe's `src` to change to
 `http://{host}:{jupyter_port}/lab/tree/runs/{latest_rid}.ipynb`.
 The embedded JupyterLab loads the same ipynb in the editable
 kernel view.
5. Toggle back to `Rendered`. `browser_network_requests` should
 show **only one** `GET /jobs/{id}/runs/{rid}/notebook` — the
 second hit loads from the `runs/{rid}.html` sidecar written
 during step 3's first render, and the iframe cache hit keeps
 the browser from reissuing a request.
6. Scroll to the Recent runs table. Click a **different** row
 (any succeeded/failed run from an earlier tick, if present).
 Assert the `$dispatch("run-selected", …)` Alpine event fires
 and the card's iframe src updates to the clicked `run_id`.
7. With a row still selected, click "Download.ipynb" in the card
 footer. `browser_network_requests` should record a
 `GET /jobs/{id}/runs/{rid}/notebook/download?format=ipynb` with
 `Content-Disposition: attachment; filename=…ipynb` and a `200`
 status.
8. Click "Download.html". First hit triggers the nbconvert
 sidecar write (same mechanics as the inline route), returns the
 cached HTML with a `.html` filename.

### Negative paths

- Navigate to `/jobs/{id}/runs/99999999/notebook` for a `run_id`
 that does not belong to this job — expect 404 from
 `_load_papermill_run_output_path`, served through the centralized
 error handler.
- Navigate to `/jobs/{non_papermill_id}/runs/{rid}/notebook` for a
 `python` or `pg_sync` job — same 404 path (the validator rejects
 non-papermill kinds before touching disk).
- Sign in as a non-owner, non-admin and visit the render route for
 a job owned by another user — 404 (the validator inherits
 `_load_job_or_404`'s ownership rule; the render endpoint never
 reveals whether a run exists for a job the caller cannot see).

### Expected bugs surfaced

Nothing pre-identified. Playbook replay notes land below; if
something is weird, file it as `BUG-26-NN` with a concrete fix
location (template line, route file + line, service function) —
no "felt off" entries.

### Part F live run

Two bugs surfaced in the first live replay against a Playwright
MCP session; both fixed in the same sprint commit.

- **BUG-26-01** (same-commit fix): the iframe inside
 `<template x-if="selectedRunId !== null">` was cloned into the
 DOM by Alpine, but the clone's `:src="iframeSrc()"` directive
 was never processed — the iframe stayed in the DOM with a
 literal `:src` attribute and an empty `src`, so no render ever
 loaded even though `iframeSrc()` returned the correct URL.
 Alpine 3.14's `x-if` clone path does walk directives on the
 clone, but this particular combination (iframe + `:src` bound
 to a method call + conditional via `x-if`) leaves the attribute
 unbound on first paint. Switched to `x-show` + an always-
 present `<iframe>` with `:src="selectedRunId !== null ?
 iframeSrc() : 'about:blank'"`. `x-show` keeps the node in the
 DOM so Alpine's initial walk binds the `:src` directive
 normally, which eliminates the timing issue entirely. The
 placeholder `<div>` that was previously in the `null`-branch
 template now uses `x-show` + `x-cloak` as well so it doesn't
 flash during Alpine init.
- **BUG-26-02** (same-commit fix): the Recent runs `<tr>` carried
 `x-on:click="$dispatch('run-selected', { runId:... })"` but
 the row lives inside the plain-HTML Recent runs card, which is
 not wrapped in an `x-data` scope. Alpine only processes
 directives on descendants of an `x-data` root, so the
 `x-on:click` was ignored and the event was never dispatched —
 the Output artifacts card's `window` listener sat idle and the
 selection never swapped. The DAG tasks table upstream wraps
 its `.table-responsive` in `x-data="{...}"` for the same
 reason ([job_detail.html:106](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/job_detail.html#L106));
 we have no state to carry here so the simpler fix was to swap
 the `x-on:click` for a plain `onclick=
 "window.dispatchEvent(new CustomEvent('run-selected',...))"`.
 The "Open in JupyterLab" anchor inside the row changed from
 `x-on:click.stop` to `onclick="event.stopPropagation()"` for
 the same "outside Alpine scope" reason, so popping out to
 JupyterLab no longer fires the row-click path by accident.
- Everything else worked on the first try: view toggle
 (Rendered ↔ JupyterLab iframe src swap), auto-select of the
 most recent succeeded run on page load, the `.ipynb`
 download (200, `Content-Type: application/x-ipynb+json`,
 `Content-Disposition: attachment; filename="job13_run12.ipynb"`),
 the `.html` download (200 + sidecar auto-generated on demand),
 and all three negative paths (cross-job `run_id` → 404,
 non-papermill job kind → 404, nonexistent `run_id` → 404)
 with the exact domain-exception messages emitted by
 `_load_papermill_run_output_path`.

## Part G — Workspace browser

 closes the last authoring gap: a `/notebooks/workspace`
page with a sidebar-style notebook tree, a browser-driven upload
endpoint, and a **Schedule…** button per notebook leaf that pre-
fills the create-job modal on `/jobs`. Together they replace the
 ritual of `docker cp`-ing notebooks into the container
and typing the path into the modal by hand.

Precondition: logged in as `admin@pql.test`. The workspace nav
link is only visible for admins — non-admins see the stack
without it (that is verified in the negative pass at the bottom).

### Steps

1. `browser_navigate` to `/notebooks/workspace`. `browser_snapshot`
 the tree card. Assert:
 - `smoke_papermill.ipynb` (from Part A) is present as a leaf
 with a `PARAMS` badge on the row — it has a
 `parameters`-tagged cell, so
 `list_workspace_tree` → `papermill.inspect_notebook` returns
 a non-empty dict.
 - `smoke_typed_params.ipynb` (from Part E) is present with a
 `PARAMS` badge.
 - No top-level `runs/` directory appears. The tree helper
 skips it at the root level because its contents are
 executor output keyed by `job_run_id`.
2. Upload a fresh notebook via the **Upload notebook** card on
 the right:
 - `browser_fill_form` on `#wsTargetPath` with
 `playbook_upload.ipynb`, leave the **Overwrite** checkbox
 unchecked.
 - `browser_file_upload` on `#wsFile` with a minimal
 `playbook_upload.ipynb` blob whose first cell is
 `parameters`-tagged (`message: str = "hello"` is enough).
 - Click **Upload**. `browser_network_requests` should show
 `POST /api/notebooks/upload` → `200`; the response body
 reads `{"path": "playbook_upload.ipynb", "status": "created"}`.
 The Alpine card flashes the `Uploaded …` success alert and
 the tree refreshes (another `GET /api/notebooks/tree` fires
 from `reload()`).
3. Assert `playbook_upload.ipynb` is now in the tree.
4. Click **Schedule…** on the `playbook_upload.ipynb` row.
 `browser_wait_for` the URL to become
 `/jobs?prefill_kind=papermill&prefill_notebook_path=playbook_upload.ipynb`.
 `browser_snapshot` the modal. Assert:
 - The create-job modal is open (Bootstrap `modal.show` called
 from `applyPrefill`).
 - `select[x-model="kind"]` reads `papermill`.
 - `input[x-model="notebookPath"]` contains
 `playbook_upload.ipynb`.
 - The typed-parameters card rendered a single row for
 `message (str)` with the quoted default stripped to `hello`
 — the `x-init="applyPrefill()"` chains
 `inspect()` before the modal opens, so the typed form is
 already populated by the time the user sees it.
 - `browser_evaluate` reads `window.location.search` — it
 should be empty (the `history.replaceState({}, '', '/jobs')`
 call swapped the query string out so a reload does not re-
 open the modal).
5. Fill the **Name** input (`workspace-upload-demo`) and submit.
 Assert the page reloads to `/jobs` and the new job row is
 present.
6. Click into the new job. **Run-now**. `browser_wait_for` the
 run status to become `succeeded` (the scheduler tick is
 2 s under the e2e overlay). Scroll to the **Output artifacts**
 card from Part F; assert the most recent run is auto-selected
 and the rendered HTML iframe shows the parameter-injection
 output line (`message = "hello"`).

### Negative paths

- Upload a `.py` file via the same form (or `curl -F` against
 `/api/notebooks/upload`): expect `422`, error message
 `uploaded file must have an.ipynb extension: 'script.py'`.
 The request never touches disk.
- Upload an `.ipynb` with `target_path=../escape.ipynb`: expect
 `422`, error message contains
 `escapes the notebooks directory`. Matches the
 `resolve_upload_target` traversal guard.
- Re-upload the same `playbook_upload.ipynb` without the
 **Overwrite** box ticked: expect `422`,
 `file already exists at 'playbook_upload.ipynb'; pass overwrite=true to replace`.
 Re-upload once more **with** the box ticked: expect `200` and
 `{"status": "overwritten"}`. The tree still shows exactly one
 `playbook_upload.ipynb` leaf.
- `browser_navigate` to `/jobs?prefill_kind=papermill` (without
 `prefill_notebook_path`): the modal must stay closed — the
 `applyPrefill()` guard short-circuits when the path is missing.
- Sign out, sign in as `user@pql.test`, then `browser_navigate`
 to `/notebooks/workspace`: expect `403`. `browser_snapshot`
 the navbar: the **Workspace** link is absent (the `{% if
 current_user.is_admin %}` gate in `base.html` hides it).

### Expected bugs surfaced

Nothing pre-identified. Playbook replay notes land below; if
something is weird, file it as `BUG-27-NN` with a concrete fix
location (template line, route file + line, service function).

### Part G live run

One bug surfaced in the first live replay against a Playwright
MCP session; fixed in the same-sprint fix commit.

- **BUG-27-01** (same-sprint fix): `.ipynb_checkpoints/` — the
 directory JupyterLab auto-writes next to every edited notebook
 — leaked into the workspace tree as a top-level directory.
 `list_workspace_tree` only filtered the executor's `runs/`
 subdir by name; Jupyter's checkpoint dirs (which appear at
 *any* depth, once per edited notebook) were noise users had to
 wade through. Fix: in `services/notebook_workspace.py` the
 `_walk` helper now also skips any directory whose name starts
 with a `.` (and, symmetrically, any dot-prefixed notebook
 file). The rule is "dotdirs and dotfiles are storage
 artefacts, not user content" — the same principle most file
 browsers apply. Test added:
 `test_tree_excludes_dot_prefixed_dirs_at_any_depth`.
- Everything else worked on the first try:
 - Step 2 upload 200, `playbook_upload.ipynb` lands on disk,
 tree reload via `reload()` picks up the new leaf with the
 `PARAMS` badge (the uploaded notebook has a
 `parameters`-tagged cell).
 - Step 4 Schedule…: URL went to
 `/jobs?prefill_kind=papermill&prefill_notebook_path=playbook_upload.ipynb`;
 after `applyPrefill` ran the query string was gone
 (`history.replaceState({}, '', '/jobs')`), the modal was open,
 `kind=papermill`, `notebookPath=playbook_upload.ipynb`, and
 one typed-params row rendered.
 - Step 5 create + Step 6 Run-now: job `#15` landed,
 scheduler's 2 s tick picked it up (plus one manual Run-now),
 both runs went `succeeded` in ~2 s each, and the
 Output-artifacts iframe at `/jobs/15/runs/15/notebook` renders
 the `uploaded-notebook says: hello` stdout from the cell
 body.
 - All four negative assertions land the exact domain-exception
 strings: `uploaded file must have an.ipynb extension:
 'script.py'`, `notebook upload target_path '../escape.ipynb'
 escapes the notebooks directory`, `file already exists at
 'playbook_upload.ipynb'; pass overwrite=true to replace`, and
 the `overwrite=true` replay returns 200 +
 `{"status": "overwritten"}`.
 - Non-admin pass: `/notebooks/workspace` → 403 HTML,
 `GET /api/notebooks/tree` → 403 JSON envelope with message
 `user@pql.test lacks admin on system 'admin'`, navbar
 Workspace link absent (the `{% if current_user.is_admin %}`
 gate in `base.html` held).
- Pre-existing quirk (not a bug, documented here so
 the next replay does not retag it): when a Papermill notebook
 declares an *untyped* default — e.g. `message = "hello"`
 without the `message: str = "hello"` annotation —
 `papermill.inspect_notebook` returns `inferred_type_name="None"`
 and the `coerceDefault` helper falls through to
 `String(d)`, which leaves the literal `"hello"` (with surrounding
 quotes) in the input. The seeded `smoke_papermill.ipynb`
 already exhibits this and it has not been a problem in any
 previous replay — noting it here so it does not look like a
 regression on the next pass.
