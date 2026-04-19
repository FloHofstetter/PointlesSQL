# Native notebook editor walkthrough

Verifies the Phase-12.6 Monaco-based notebook editor end-to-end —
load + save round-trip, kernel execute, output persistence across
page reload, kernel restart, Pyright LSP (completion + hover),
Variable Explorer, Insert-from-catalog modal, and the retired-
JupyterLab surface.  Replaces the Sprint-23 `notebook.md`
playbook (the embedded JupyterLab iframe retired in Sprint 63).

## Preconditions

- Stack up with the e2e overlay; admin user logged in.
- `notebooks/` is writable by the PointlesSQL process (default
  for both local dev and the Docker overlay).
- soyuz-catalog reachable on :8080 (Insert-from-catalog step
  exercises `/api/tree`).
- **Browser**: Firefox via Playwright-MCP (or the bundled
  `chrome-for-testing` — see `CLAUDE.md` for why the system
  Chrome channel flakes).  Monaco's AMD loader needs modern
  JS; all target browsers are fine.

## Walkthrough

### Part A — First open: UUID mint + autosave

1. **Landing route**.
   - Action: `browser_navigate('http://127.0.0.1:8000/notebook')`
   - Assert: 302 redirect to
     `/notebook/editor?path=scratch.py`, page title contains
     `Editor · scratch.py`, navbar "Notebook" link is active.

2. **Monaco boots + single empty cell**.
   - Action: `browser_wait_for(time=2)` (Monaco AMD loader +
     vendored bundle take ~1 s on a warm cache).
   - Assert: the `.pql-nbedit-editor` div has a Monaco editor
     instance; the buffer contains exactly one `# %%
     pql_cell_id="…"` marker (empty cell scaffold from
     `notebook_editor_page` when the file doesn't exist yet).

3. **Toolbar pills**.
   - Action: `browser_snapshot()` of the `.pql-nbedit-toolbar`.
   - Assert:
     - `Kernel ready` (green) within ~3 s of load — ipykernel
       starts on first WS connect.
     - `Pyright ready` (green) within ~3 s — pyright-langserver
       starts with its Node bundle.
     - `Saved` (green) — the file was just materialised with
       one cell on first save.

4. **First save materialises the file**.
   - Action (shell, adjust path):
     ```bash
     cat notebooks/scratch.py
     ```
   - Assert: a jupytext Percent header is present, followed by
     one `# %% pql_cell_id="<UUID>"` marker and zero source
     lines.  The UUID regex is `[0-9a-fA-F-]{36}`.

### Part B — Execute, outputs, persistence

5. **Type code into the cell**.
   - Action: `browser_click` into the editor area, then
     `browser_type('import pandas as pd\ndf = pd.DataFrame({"a":[1,2,3]})\ndf')`.
   - Assert: the `Saved` pill flips to `Unsaved changes`
     (yellow) on the first keystroke, back to `Saved` 1.5 s
     after the last keystroke (Sprint-58 autosave debounce).

6. **Run the cell (Shift+Enter)**.
   - Action: place cursor inside the cell, press `Shift+Enter`.
   - Assert:
     - A Monaco view zone appears directly beneath the cell.
     - Within ~2 s the view zone contains a pandas-styled HTML
       table (first 3 rows of `df`) — the Sprint-60 rich-mime
       renderer for `text/html`.
     - The "Kernel ready" pill briefly flashes "busy" via the
       internal `executingCells` state; scripted replay can
       skip this check because timing is tight.

7. **Outputs persist across reload**.
   - Action: `browser_navigate` away (e.g. to `/`) and back to
     `/notebook/editor?path=scratch.py`.
   - Assert: before the kernel WS opens, the rendered pandas
     HTML is *already* visible in the output zone — the
     Sprint-60 replay path runs synchronously on Alpine
     mount, so there is no "empty view → output arrives"
     flicker.  The Network panel shows no new kernel execute
     in this interval.

8. **Clear-cell button purges row + DOM**.
   - Action: click `Clear cell`.
   - Assert: the view zone collapses to zero height; reload the
     page — the output zone stays empty (Sprint-60 persistence
     hook deleted the row).

9. **Restart kernel wipes every session row**.
   - Prereq: re-run the cell so there's at least one output.
   - Action: click `Restart`.
   - Assert:
     - Toolbar pill briefly shows `Restarting…` → `Kernel ready`.
     - Every view zone in the editor is empty immediately
       after restart.
     - Reloading the page does not repopulate outputs (the
       Sprint-60 restart path clears all persisted rows for
       the outgoing session).

### Part C — Pyright LSP

10. **Completion on `json.`**.
    - Action: add a new code cell (toolbar `Add cell` button),
      type `import json\njson.` and let the cursor rest
      after the dot.
    - Assert: Monaco's completion widget opens within ~500 ms
      showing at least `dumps`, `loads`, `dump`, `load` in the
      suggestions list.  Each entry's "detail" column carries
      pyright's type signature.

11. **Hover on `json.dumps`**.
    - Action: type `json.dumps(...)` somewhere, hover the
      `dumps` identifier.
    - Assert: Monaco's hover popover opens showing pyright's
      signature (`dumps(obj: Any, *, skipkeys: bool = False, ...) -> str`)
      and the docstring.

12. **Diagnostic on a bad reference**.
    - Action: type `undefinedsymbol_xyz` on a line of its own.
    - Assert: within ~1 s a red squiggle appears under the
      identifier.  Hovering it shows pyright's diagnostic
      message ("undefinedsymbol_xyz" is not defined).

### Part D — Insert from catalog

13. **Open the modal**.
    - Action: press `Ctrl+Shift+I` (or click the `Catalog`
      toolbar button, or invoke the command palette entry
      "PointlesSQL: Insert from catalog…").
    - Assert: the Bootstrap modal overlays the editor; the
      filter input is focused; the list populates within
      ~500 ms from `/api/tree`.

14. **Filter + pick**.
    - Action: type `main` into the filter; click the first
      remaining entry.
    - Assert: modal closes; the editor's cursor line now
      contains `pql.read_table("main.<schema>.<table>")`
      (exact table name depends on the seeded catalog).
    - Assert: Monaco reports no Pyright diagnostic on the
      new line (PQL is importable).

### Part E — Variable Explorer

15. **Open the sidebar**.
    - Action: click the `Variables` toolbar button (or the
      "Toggle variable explorer" command-palette entry).
    - Assert: right-side sidebar expands.  If no user cells
      have run since the last restart, the sidebar shows
      "No user variables yet. Run a cell that defines one."

16. **DataFrame row**.
    - Prereq: run the Part-B cell that defined `df`.
    - Action: observe the sidebar auto-refresh on idle
      (50 ms scheduled debounce per `_handleKernelFrame`).
    - Assert: a row named `df` with type `DataFrame`, shape
      `[3, 1]`, and a 3-row `head()` HTML preview (the
      `.pql-nbedit-vars-df` class is scoped in the template
      so the preview inherits the sidebar styles).

17. **Scalar row**.
    - Action: add a cell `answer = 42`, run it.
    - Assert: sidebar now has an `answer` row with type `int`
      and `repr` `42`.

### Part F — Post-retirement surfaces

18. **No JupyterLab iframe anywhere**.
    - Action: `browser_evaluate(() => document.querySelectorAll('iframe').length)`
      on both `/` and `/jobs/<any-papermill-job>`.
    - Assert: zero iframes matching `src*="lab/"` on the
      home + catalog + jobs pages.

19. **`/api/jupyter/status` is gone**.
    - Action: `fetch('/api/jupyter/status').then(r => r.status)`
    - Assert: `404` (the route was removed in Sprint 63; any
      future re-introduction would need to pass through a
      new route handler).

20. **Sprint-26 output card is single-view**.
    - Action: navigate to `/jobs/<papermill-job>` with a
      completed run.
    - Assert: the output-artifacts card header has no
      `Rendered / JupyterLab` toggle — just the card title +
      run number.  The "Download" button on the run row
      hits `/jobs/{id}/runs/{rid}/notebook/download?format=ipynb`.

21. **Sprint-34 open-in-notebook returns editor_url**.
    - Action: from a UC table detail page, admin-click "Open
      in notebook".
    - Assert: the browser navigates to
      `/notebook/editor?path=scratch/<generated>.py` (not to a
      JupyterLab tree URL).  The scaffolded file contains
      a markdown header cell + a code cell with
      `pql.table("cat.schema.tbl")` + `df.head()` — jupytext
      Percent format with two `pql_cell_id="<UUID>"` markers.

22. **Papermill schedules a `.py` notebook** (optional — needs
    the scheduler overlay).
    - Action: from `/jobs`, create a papermill job with
      `notebook_path: scratch.py`, Run now.
    - Assert: the run transitions running → succeeded; a new
      `notebooks/runs/<run_id>.ipynb` appears on disk; the
      Sprint-63 jupytext-convert temp
      `notebooks/runs/<run_id>.input.ipynb` does **not**
      exist after the run (the `finally` block unlinked it).

## Found bugs

**BUG-64-01** (commit TBD). The Sprint-58 editor template opened
the root `x-data` attribute with double quotes and pasted the
``{{ notebook_path|tojson }}`` expression straight inside:

```html
<div class="pql-nbedit-root"
     x-data="notebookEditor({ path: {{ notebook_path|tojson }}, ... })">
```

Jinja's ``|tojson`` emits proper JSON (``"scratch.py"``), but
those inner double quotes terminate the outer ``x-data`` HTML
attribute — Alpine then parses only up to the first inner
quote, reports ``expected expression, got '}'``, and every
subsequent ``x-data``-scoped reference ("mount is not defined",
"saveState is not defined", "kernelStatus is not defined")
fires against an empty Alpine scope.  The symptom was a blank
editor page with 25 console errors.

Fixed by switching the outer attribute to single quotes:

```html
<div class="pql-nbedit-root"
     x-data='notebookEditor({ path: {{ notebook_path|tojson }}, ... })'>
```

Single-quoted attribute + double-quoted JSON round-trips cleanly;
the trailing comma before the closing ``})`` was also dropped
(JSON5 tolerance doesn't live inside Alpine's expression parser).
This class of bug escaped every Sprint 58–63 gate because
``ruff`` / ``pyright`` / ``pydoclint`` don't inspect Jinja
templates + Alpine x-data expressions, and the playbook (which
was going to catch it) landed in the same sprint as the bug.
**Lesson**: run the playbook as a gate, not a close-out, when
the sprint touches Alpine scopes.

**BUG-64-02** (commit TBD). After BUG-64-01's x-data fix, Alpine
mounted the editor scope but `mount()` froze on the very first
``monaco.editor.create()`` call when the model used a non-trivial
language (`python`, `javascript`, ...). A plaintext model worked.
The hang was completely silent: no console.error, Firefox at 1 %
CPU, no thrown exception, just `monaco.editor.create()` never
returning.

Root cause: every property of an Alpine ``x-data`` return value
is wrapped in a deep-reactive Vue Proxy. Sprint 58's `mount()`
stored the model on `this._model`, then passed `this._model`
into ``monaco.editor.create({ model: this._model })``. Monaco
read the proxied model's internal properties (uri, version,
tokenization state) — each read returns *another* proxy and
also touches Monaco's own circular references. The recursion
plus reactive tracking on every internal field stalled the
synchronous create call indefinitely.

Standalone repro confirmed Monaco itself is fine: a plain HTML
page that loads vendored Monaco and runs the same
`createModel('print(1)', 'python')` + `editor.create({model})`
returns in ~80 ms. Same code under our Alpine x-data: hangs
forever.

Fix in [frontend/js/notebook_editor.js](../../frontend/js/notebook_editor.js):
hoist `_model` and `_editor` into closure-scoped `let` vars
inside the `notebookEditor()` factory and remove them from the
returned object. All 50-odd in-method `this._editor` /
`this._model` references stay as plain `_editor` / `_model`
identifiers (lexically scoped to the factory closure, never
proxied). The reactive part of the returned object now only
carries primitive UI state (`saveState`, `kernelStatus`, dirty
flag, etc.) — Monaco internals never go through Vue reactivity.

This class of bug also escapes ruff/pyright/pydoclint because
neither the AMD bundle nor the Alpine wrapper is type-checked
at the JS layer. **Lesson**: Monaco / Web Worker / WebSocket
objects must NEVER live as `this.X` inside an Alpine factory —
they belong in closure scope. Add a CodeQL or grep gate in CI
that fails on `this\._(editor|model)\s*=` if we add more
Monaco surfaces.

**BUG-64-03** (commit TBD). With BUG-64-02 fixed, the editor
rendered and both pills (Kernel ready / Pyright ready) flipped
green within 10 s. The first keystroke triggered Sprint-58
autosave → ``POST /api/notebook/doc`` writes ``notebooks/scratch.py``
on disk → uvicorn's dev-mode autoreload watcher saw the file
change and restarted the entire ASGI process → kernel + Pyright
WebSockets dropped → pills went red ("Kernel disconnected",
"Pyright error"). Symptom in the log:

```
INFO:     127.0.0.1:54554 - "POST /api/notebook/doc HTTP/1.1" 200 OK
StatReload detected changes in 'notebooks/scratch.py'. Reloading...
WARNING  pyright-langserver did not stop — killing
INFO     scheduler: stopped
INFO     kernel shut down for demo@pql.test notebook=scratch.py
```

Fix in [pointlessql/api/main.py:cli()](../../pointlessql/api/main.py):
pin uvicorn's reload watcher to the source trees:

```python
project_root = Path(__file__).resolve().parent.parent
uvicorn.run(..., reload=True,
            reload_dirs=[str(project_root),
                         str(project_root.parent / "frontend")])
```

After the fix, the autosave POST round-trips silently and the
WS connections survive. **Lesson**: when adding a feature that
writes to the working directory in dev, audit ``reload=True``
upstream and explicitly scope ``reload_dirs``.

## What worked on the first try

- Part A (first open + UUID mint + autosave flush) — the
  Sprint-58 + Sprint-58-followup paths compose cleanly without
  a flash of "unsaved" on foreign-notebook open.
- Part B persistence — Sprint-60's replay-on-mount paints
  outputs before the WS handshake completes, so there is no
  visible empty-then-populated flicker.
- Part C completion + hover + diagnostics against `json` and
  an undefined symbol — pyright's bundled Node binary starts
  in ~1 s on a warm cache.
- Part D Insert-from-catalog round-trip — the Ctrl+Shift+I
  binding fires even from inside a focused Monaco instance
  because the command is registered via `editor.addAction`
  rather than a bare document-level hotkey.
- Part F retirement surfaces — the only iframe left in the app
  is the Sprint-26 papermill output viewer (which uses
  nbconvert HTML, not JupyterLab).

## Part G — Sprint 66: per-cell affordances

Phase 12.7 second sprint lifts the editor from a single Python
buffer with global toolbar to a per-cell-affordance UI with a
cell-type registry.  Every cell now has a toolbar row above its
marker (execution count, status pill, elapsed timer, run button)
and a hover-revealed ``+ Code`` / ``+ Markdown`` inserter below
its body.

Setup: open a notebook with at least one code cell and one
markdown cell.

1. **Cell toolbar visible** — each cell shows a ~26px toolbar row
   above its ``# %%`` marker.  Code cells show ``▶ [ ] idle …
   PYTHON``.  Markdown cells show ``markdown … MARKDOWN`` (no run
   button, no ``[n]`` count).

2. **Run a code cell via the per-cell button** — click the ``▶``
   button.  Expect:
   - Count pill flips ``[ ]`` → ``[*]`` on ``execute_input``.
   - Status pill flips ``idle`` → ``running`` (yellow, pulsing)
     on ``status: busy``.
   - Elapsed pill ticks from ``0ms`` upward every 100 ms.
   - On ``execute_reply.status = ok`` the status pill goes
     ``ok`` (green) and the count pill settles on the kernel's
     monotonic counter (``[1]``, ``[2]``, …).

3. **Run a cell that raises** — type ``1 / 0``, run it.  Status
   pill flips to ``error`` (red).  Traceback renders in the
   existing output zone.  Count pill advances; elapsed pill
   freezes at the run duration.

4. **Interrupt a long run** — type ``import time; time.sleep(60)``,
   click ``▶``, then press the toolbar ``Interrupt`` button
   while the status pill is ``running``.  Expect the status pill
   to transition to ``cancelled`` (not ``error``).  Elapsed pill
   shows the time-until-interrupt.

5. **``+`` inserter** — hover between two cells.  The 22px gap
   below each cell reveals two buttons: ``+ Code`` and
   ``+ Markdown``.
   - Click ``+ Code``: a new code cell appears below the anchor
     cell with its own toolbar and a fresh UUID marker.
   - Click ``+ Markdown``: a new markdown cell appears with a
     preview zone immediately below its marker (Sprint 58
     markdown-zone machinery unchanged).

6. **Kernel restart resets counters** — run two code cells so
   their count pills show ``[1]`` and ``[2]``.  Click
   ``Restart``.  Expect all count pills to reset to ``[ ]``, all
   status pills to ``idle``, elapsed pills to clear.

7. **Page reload sanity (BUG-64-02 regression gate)** — start a
   long-running cell, reload the page before it finishes.  Expect
   Monaco to re-hydrate, toolbars to rebuild on each cell, and no
   ``Proxy → circular`` error in DevTools.  (The captured
   ``reactiveRoot`` in the closure prevents per-cell click
   handlers from re-entering a dead Alpine instance.)

### What shipped for Sprint 66

- [frontend/js/notebook/cell_types.js](../../frontend/js/notebook/cell_types.js) — registry.
  One descriptor per type (``code``, ``markdown``).  Sprint 71
  adds ``sql`` here without touching any other module.
- [frontend/js/notebook/cell_affordances.js](../../frontend/js/notebook/cell_affordances.js)
  — factory for the toolbar and inserter view zones.  All DOM
  and timer state lives closure-scoped; BUG-64-02 invariant
  preserved.
- [frontend/js/notebook/cell_parser.js](../../frontend/js/notebook/cell_parser.js)
  — widened ``CELL_MARKER_RE`` to ``(\s+\[\w+\])?`` so forward-
  compat tags round-trip cleanly.
- [frontend/js/notebook/main.js](../../frontend/js/notebook/main.js)
  — ``renderKernelMsg`` now intercepts ``execute_input`` +
  ``execute_reply``; ``runCellById`` is the single execution
  seam; ``insertCellAfter`` drives the inserter.
- [frontend/templates/pages/notebook_editor.html](../../frontend/templates/pages/notebook_editor.html)
  — CSS additions for ``.pql-nbedit-cell-toolbar``,
  ``.pql-nbedit-status-pill``, ``.pql-nbedit-inserter``.
- [scripts/check-frontend-no-reactive-monaco.sh](../../scripts/check-frontend-no-reactive-monaco.sh)
  — widened forbidden list to cover ``this._cellAffordances``,
  ``this._statusWidgets``, ``this._cellWidgets``,
  ``this._reactiveRoot``.

**No backend changes.**  The ``notebook_cell_runs`` schema from
Alembic 017 already reserves the ``execution_count``,
``started_at``, ``finished_at`` columns — Sprint 73 will be the
sprint that actually writes them back from the server.

### What the replay caught

**Alpine-vs-ESM race regression.**  Sprint 65's
``<script type="module" src="bootstrap.js">`` and Alpine's CDN
``<script defer>`` are both deferred; Sprint 66 pushed the module
graph from 9 to 11 modules and the extra two network round-trips
were enough to let Alpine evaluate ``x-data="notebookEditor(...)"``
before ``window.notebookEditor`` existed, leaving the reactive
scope empty (every binding printed a
``ReferenceError: <key> is not defined`` warning).

Fix: converted [bootstrap.js](../../frontend/js/notebook/bootstrap.js)
from a module to a classic IIFE that registers the factory
synchronously at parse time and dynamic-imports
[main.js](../../frontend/js/notebook/main.js) inside the
factory's ``mount()`` method.  Same shape as the Sprint-41 SQL-
editor mitigation documented in commit ``b830300``.  The script
tag also carries a ``?v=sprint66`` query to bust Firefox's
module-cache entry for consumers upgrading from Sprint 65.

**KeyboardInterrupt is not ``status=aborted``.**  Jupyter surfaces
a user-interrupted cell as ``execute_reply.status='error'`` with
``ename='KeyboardInterrupt'`` — ``status='aborted'`` is reserved
for requests skipped because an earlier request in the same
``execute_reply`` chain failed.  The initial Sprint-66 handler
only remapped ``aborted`` → ``cancelled`` so interrupts showed up
as red ``error`` pills.  Refined the reply handler in
[main.js](../../frontend/js/notebook/main.js) to also map
``ename==='KeyboardInterrupt'`` → ``cancelled``.
