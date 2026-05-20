# Native notebook editor walkthrough

> **Mode:** `browser` · **Phase:** 12.10 · **Surface:** Native .py notebook editor

> **⚠️ Partial refresh status (Sprint H.3, 2026-05-12):**  Routes
> updated for Phase-12.12's `/notebooks/edit/` →
> `/notebooks/edit/{path}` rename and the `pql-notebook-shell` →
> `pql-notebook-shell` + `pql-notebook-toolbar` →
> `pql-notebook-toolbar` Phase-67 renames; **per-feature class
> selectors below remain stale**.  Many `pql-nbedit-*` references
> describe features that were renamed or restructured across
> Phases 67/68 (cell toolbar, status pill, history popover,
> outline, settings drawer, etc.) without the playbook being
> propagated.  Replay-driver should look up the current class
> name in DevTools rather than treating the selectors here as
> the source of truth.  Comprehensive refresh queued as a
> follow-up phase (out of scope for the Sprint-H.3 sweep).
> File-path links in the "Critical files" footers may also point
> at pre-Phase-12.12 module locations (e.g.
> `notebook_workspace.py` is now `notebook/_workspace.py`).

Verifies the Monaco-based notebook editor end-to-end —
load + save round-trip, kernel execute, output persistence across
page reload, kernel restart, Pyright LSP (completion + hover),
Variable Explorer, Insert-from-catalog modal, and the retired-
JupyterLab surface. Replaces the `notebook.md`
playbook (the embedded JupyterLab iframe retired).

## Preconditions

- Stack up with the e2e overlay; **any authenticated user** can
  reach the editor (Phase 70 dropped the admin gate). Run both
  admin and member personas through the full walkthrough.
- `notebooks/` is writable by the PointlesSQL process (default
 for both local dev and the Docker overlay).
- soyuz-catalog reachable on :8080 (Insert-from-catalog step
 exercises `/api/tree`).
- **Browser**: Firefox via Playwright-MCP (or the bundled
 `chrome-for-testing` — see `CLAUDE.md` for why the system
 Chrome channel flakes). Monaco's AMD loader needs modern
 JS; all target browsers are fine.

## Walkthrough

### Part A — First open: UUID mint + autosave

1. **Landing route**.
 - Action: `browser_navigate('http://127.0.0.1:8000/notebooks/workspace')`
 - Assert: workspace page renders with file-tree, the "Edit"
   affordance on `scratch.py` navigates to
   `/notebooks/edit/scratch.py`, page title contains
   `Editor · scratch.py`, navbar "Notebook" link is active.
   The "New notebook…" button in the card header also opens the
   editor at the freshly-created file once a `.py` path is
   confirmed at the prompt.

2. **Monaco boots + single empty cell**.
 - Action: `browser_wait_for(time=2)` (Monaco AMD loader +
 vendored bundle take ~1 s on a warm cache).
 - Assert: the `.pql-notebook-shell` div has a Monaco editor
 instance; the buffer contains exactly one `# %%
 pql_cell_id="…"` marker (empty cell scaffold from
 `notebook_editor_page` when the file doesn't exist yet).

3. **Toolbar pills**.
 - Action: `browser_snapshot()` of the `.pql-notebook-toolbar`.
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
 lines. The UUID regex is `[0-9a-fA-F-]{36}`.

### Part B — Execute, outputs, persistence

5. **Type code into the cell**.
 - Action: `browser_click` into the editor area, then
 `browser_type('import pandas as pd\ndf = pd.DataFrame({"a":[1,2,3]})\ndf')`.
 - Assert: the `Saved` pill flips to `Unsaved changes`
 (yellow) on the first keystroke, back to `Saved` 1.5 s
 after the last keystroke ( autosave debounce).

6. **Run the cell (Shift+Enter)**.
 - Action: place cursor inside the cell, press `Shift+Enter`.
 - Assert:
 - A Monaco view zone appears directly beneath the cell.
 - Within ~2 s the view zone contains a pandas-styled HTML
 table (first 3 rows of `df`) — the rich-mime
 renderer for `text/html`.
 - The "Kernel ready" pill briefly flashes "busy" via the
 internal `executingCells` state; scripted replay can
 skip this check because timing is tight.

7. **Outputs persist across reload**.
 - Action: `browser_navigate` away (e.g. to `/`) and back to
 `/notebooks/edit/scratch.py`.
 - Assert: before the kernel WS opens, the rendered pandas
 HTML is *already* visible in the output zone — the
 replay path runs synchronously on Alpine
 mount, so there is no "empty view → output arrives"
 flicker. The Network panel shows no new kernel execute
 in this interval.

8. **Clear-cell button purges row + DOM**.
 - Action: click `Clear cell`.
 - Assert: the view zone collapses to zero height; reload the
 page — the output zone stays empty ( persistence
 hook deleted the row).

9. **Restart kernel wipes every session row**.
 - Prereq: re-run the cell so there's at least one output.
 - Action: click `Restart`.
 - Assert:
 - Toolbar pill briefly shows `Restarting…` → `Kernel ready`.
 - Every view zone in the editor is empty immediately
 after restart.
 - Reloading the page does not repopulate outputs (the
 restart path clears all persisted rows for
 the outgoing session).

### Part C — Pyright LSP

10. **Completion on `json.`**.
 - Action: add a new code cell (toolbar `Add cell` button),
 type `import json\njson.` and let the cursor rest
 after the dot.
 - Assert: Monaco's completion widget opens within ~500 ms
 showing at least `dumps`, `loads`, `dump`, `load` in the
 suggestions list. Each entry's "detail" column carries
 pyright's type signature.

11. **Hover on `json.dumps`**.
 - Action: type `json.dumps(...)` somewhere, hover the
 `dumps` identifier.
 - Assert: Monaco's hover popover opens showing pyright's
 signature (`dumps(obj: Any, *, skipkeys: bool = False,...) -> str`)
 and the docstring.

12. **Diagnostic on a bad reference**.
 - Action: type `undefinedsymbol_xyz` on a line of its own.
 - Assert: within ~1 s a red squiggle appears under the
 identifier. Hovering it shows pyright's diagnostic
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
 - Assert: right-side sidebar expands. If no user cells
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
 - Assert: `404` (the route was removed; any
 future re-introduction would need to pass through a
 new route handler).

20. ** output card is single-view**.
 - Action: navigate to `/jobs/<papermill-job>` with a
 completed run.
 - Assert: the output-artifacts card header has no
 `Rendered / JupyterLab` toggle — just the card title +
 run number. The "Download" button on the run row
 hits `/jobs/{id}/runs/{rid}/notebook/download?format=ipynb`.

21. ** open-in-notebook returns editor_url**.
 - Action: from a UC table detail page, admin-click "Open
 in notebook".
 - Assert: the browser navigates to
 `/notebooks/edit/scratch/<generated>.py` (not to a
 JupyterLab tree URL). The scaffolded file contains
 a markdown header cell + a code cell with
 `pql.table("cat.schema.tbl")` + `df.head()` — jupytext
 Percent format with two `pql_cell_id="<UUID>"` markers.

22. **Papermill schedules a `.py` notebook** (optional — needs
 the scheduler overlay).
 - Action: from `/jobs`, create a papermill job with
 `notebook_path: scratch.py`, Run now.
 - Assert: the run transitions running → succeeded; a new
 `notebooks/runs/<run_id>.ipynb` appears on disk; the
 jupytext-convert temp
 `notebooks/runs/<run_id>.input.ipynb` does **not**
 exist after the run (the `finally` block unlinked it).

## Found bugs

**BUG-69-01** (commit TBD). The first replay loaded
``markdown-it.min.js`` and ``katex.min.js`` *after*
``monaco/vs/loader.js``. Both scripts ship UMD wrappers that
detect ``typeof define === 'function' && define.amd`` and register
as anonymous AMD modules — which collides with Monaco's loader
contract ("Can only have one anonymous define call per script
file") and throws the moment KaTeX executes. Fix: reorder the
three markdown vendor scripts to load *before* ``monaco/vs/
loader.js``, so ``window.define`` does not yet exist when their
UMD wrappers execute and they fall through to the plain-script
branch that binds ``window.markdownit`` / ``window.katex`` as
globals. The template now documents the ordering rationale in a
Jinja comment so a future refactor does not shuffle the two
blocks by accident. Caught on the Part-J first-open step during
the mandated Playwright-MCP replay — a clean illustration of
``feedback_run_playbook_as_gate``: neither ruff nor pyright nor
pydoclint nor the reactivity-boundary grep gate could have caught
an AMD vs global loader-order collision.

**BUG-64-01** (commit TBD). The editor template opened
the root `x-data` attribute with double quotes and pasted the
``{{ notebook_path|tojson }}`` expression straight inside:

```html
<div class="pql-notebook-shell"
 x-data="notebookEditor({ path: {{ notebook_path|tojson }},... })">
```

Jinja's ``|tojson`` emits proper JSON (``"scratch.py"``), but
those inner double quotes terminate the outer ``x-data`` HTML
attribute — Alpine then parses only up to the first inner
quote, reports ``expected expression, got '}'``, and every
subsequent ``x-data``-scoped reference ("mount is not defined",
"saveState is not defined", "kernelStatus is not defined")
fires against an empty Alpine scope. The symptom was a blank
editor page with 25 console errors.

Fixed by switching the outer attribute to single quotes:

```html
<div class="pql-notebook-shell"
 x-data='notebookEditor({ path: {{ notebook_path|tojson }},... })'>
```

Single-quoted attribute + double-quoted JSON round-trips cleanly;
the trailing comma before the closing ``})`` was also dropped
(JSON5 tolerance doesn't live inside Alpine's expression parser).
This class of bug escaped every –63 gate because
``ruff`` / ``pyright`` / ``pydoclint`` don't inspect Jinja
templates + Alpine x-data expressions, and the playbook (which
was going to catch it) landed in the same sprint as the bug.
**Lesson**: run the playbook as a gate, not a close-out, when
the sprint touches Alpine scopes.

**BUG-64-02** (commit TBD). After BUG-64-01's x-data fix, Alpine
mounted the editor scope but `mount()` froze on the very first
``monaco.editor.create()`` call when the model used a non-trivial
language (`python`, `javascript`,...). A plaintext model worked.
The hang was completely silent: no console.error, Firefox at 1 %
CPU, no thrown exception, just `monaco.editor.create()` never
returning.

Root cause: every property of an Alpine ``x-data`` return value
is wrapped in a deep-reactive Vue Proxy. 's `mount()`
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

Fix in [frontend/js/notebook_editor.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook_editor.js):
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
green within 10 s. The first keystroke triggered
autosave → ``POST /api/notebook/doc`` writes ``notebooks/scratch.py``
on disk → uvicorn's dev-mode autoreload watcher saw the file
change and restarted the entire ASGI process → kernel + Pyright
WebSockets dropped → pills went red ("Kernel disconnected",
"Pyright error"). Symptom in the log:

```
INFO: 127.0.0.1:54554 - "POST /api/notebook/doc HTTP/1.1" 200 OK
StatReload detected changes in 'notebooks/scratch.py'. Reloading...
WARNING pyright-langserver did not stop — killing
INFO scheduler: stopped
INFO kernel shut down for demo@pql.test notebook=scratch.py
```

Fix in [pointlessql/api/main.py:cli()](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py):
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
 + -followup paths compose cleanly without
 a flash of "unsaved" on foreign-notebook open.
- Part B persistence — 's replay-on-mount paints
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
 is the papermill output viewer (which uses
 nbconvert HTML, not JupyterLab).

## Part G — : per-cell affordances

 second sprint lifts the editor from a single Python
buffer with global toolbar to a per-cell-affordance UI with a
cell-type registry. Every cell now has a toolbar row above its
marker (execution count, status pill, elapsed timer, run button)
and a hover-revealed ``+ Code`` / ``+ Markdown`` inserter below
its body.

Setup: open a notebook with at least one code cell and one
markdown cell.

1. **Cell toolbar visible** — each cell shows a ~26px toolbar row
 above its ``# %%`` marker. Code cells show ``▶ [ ] idle …
 PYTHON``. Markdown cells show ``markdown … MARKDOWN`` (no run
 button, no ``[n]`` count).

2. **Run a code cell via the per-cell button** — click the ``▶``
 button. Expect:
 - Count pill flips ``[ ]`` → ``[*]`` on ``execute_input``.
 - Status pill flips ``idle`` → ``running`` (yellow, pulsing)
 on ``status: busy``.
 - Elapsed pill ticks from ``0ms`` upward every 100 ms.
 - On ``execute_reply.status = ok`` the status pill goes
 ``ok`` (green) and the count pill settles on the kernel's
 monotonic counter (``[1]``, ``[2]``, …).

3. **Run a cell that raises** — type ``1 / 0``, run it. Status
 pill flips to ``error`` (red). Traceback renders in the
 existing output zone. Count pill advances; elapsed pill
 freezes at the run duration.

4. **Interrupt a long run** — type ``import time; time.sleep(60)``,
 click ``▶``, then press the toolbar ``Interrupt`` button
 while the status pill is ``running``. Expect the status pill
 to transition to ``cancelled`` (not ``error``). Elapsed pill
 shows the time-until-interrupt.

5. **``+`` inserter** — hover between two cells. The 22px gap
 below each cell reveals two buttons: ``+ Code`` and
 ``+ Markdown``.
 - Click ``+ Code``: a new code cell appears below the anchor
 cell with its own toolbar and a fresh UUID marker.
 - Click ``+ Markdown``: a new markdown cell appears with a
 preview zone immediately below its marker (
 markdown-zone machinery unchanged).

6. **Kernel restart resets counters** — run two code cells so
 their count pills show ``[1]`` and ``[2]``. Click
 ``Restart``. Expect all count pills to reset to ``[ ]``, all
 status pills to ``idle``, elapsed pills to clear.

7. **Page reload sanity (BUG-64-02 regression gate)** — start a
 long-running cell, reload the page before it finishes. Expect
 Monaco to re-hydrate, toolbars to rebuild on each cell, and no
 ``Proxy → circular`` error in DevTools. (The captured
 ``reactiveRoot`` in the closure prevents per-cell click
 handlers from re-entering a dead Alpine instance.)

### What shipped for

- [frontend/js/notebook/cell_types.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_types.js) — registry.
 One descriptor per type (``code``, ``markdown``).
 adds ``sql`` here without touching any other module.
- [frontend/js/notebook/cell_affordances.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_affordances.js)
 — factory for the toolbar and inserter view zones. All DOM
 and timer state lives closure-scoped; BUG-64-02 invariant
 preserved.
- [frontend/js/notebook/cell_parser.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_parser.js)
 — widened ``CELL_MARKER_RE`` to ``(\s+\[\w+\])?`` so forward-
 compat tags round-trip cleanly.
- [frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
 — ``renderKernelMsg`` now intercepts ``execute_input`` +
 ``execute_reply``; ``runCellById`` is the single execution
 seam; ``insertCellAfter`` drives the inserter.
- [frontend/templates/pages/notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 — CSS additions for ``.pql-nbedit-cell-toolbar``,
 ``.pql-nbedit-status-pill``, ``.pql-nbedit-inserter``.
- [scripts/check-frontend-no-reactive-monaco.sh](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/check-frontend-no-reactive-monaco.sh)
 — widened forbidden list to cover ``this._cellAffordances``,
 ``this._statusWidgets``, ``this._cellWidgets``,
 ``this._reactiveRoot``.

**No backend changes.** The ``notebook_cell_runs`` schema from
Alembic 017 already reserves the ``execution_count``,
``started_at``, ``finished_at`` columns — will be the
sprint that actually writes them back from the server.

### What the replay caught

**Alpine-vs-ESM race regression.** 's
``<script type="module" src="bootstrap.js">`` and Alpine's CDN
``<script defer>`` are both deferred; pushed the module
graph from 9 to 11 modules and the extra two network round-trips
were enough to let Alpine evaluate ``x-data="notebookEditor(...)"``
before ``window.notebookEditor`` existed, leaving the reactive
scope empty (every binding printed a
``ReferenceError: <key> is not defined`` warning).

Fix: converted [bootstrap.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/bootstrap.js)
from a module to a classic IIFE that registers the factory
synchronously at parse time and dynamic-imports
[main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js) inside the
factory's ``mount()`` method. Same shape as the SQL-
editor mitigation documented in commit ``b830300``. The script
tag also carries a ``?v=sprint66`` query to bust Firefox's
module-cache entry for consumers upgrading from.

**KeyboardInterrupt is not ``status=aborted``.** Jupyter surfaces
a user-interrupted cell as ``execute_reply.status='error'`` with
``ename='KeyboardInterrupt'`` — ``status='aborted'`` is reserved
for requests skipped because an earlier request in the same
``execute_reply`` chain failed. The initial handler
only remapped ``aborted`` → ``cancelled`` so interrupts showed up
as red ``error`` pills. Refined the reply handler in
[main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js) to also map
``ename==='KeyboardInterrupt'`` → ``cancelled``.

## Part H — : file-tree sidebar + notebook CRUD

 third sprint lands a left-side file-tree sidebar inside
the editor so the user can browse, create, rename, and delete
notebooks without leaving Monaco. The full-screen
``/notebooks/workspace`` page stays as-is; this sidebar is the
slim mirror.

Setup: start with at least two ``.py`` notebooks in the workspace
directory (e.g. ``scratch/one.py`` and ``scratch/two.py``).

1. **Sidebar renders on first open** — navigate to
 ``/notebooks/edit/scratch/one.py``. Expect a 260px left
 panel titled ``NOTEBOOKS`` listing every directory + ``.py``
 file under the notebooks root. The currently-open row
 (``one.py``) has a faint blue tint. ``.ipynb`` leaves render
 muted — they're listed so the tree stays faithful, but the
 name is not click-to-open from here (the native editor only
 handles ``.py``; open those on ``/notebooks/workspace``
 instead).

2. **Toggle persists** — click ``Files`` in the toolbar. Sidebar
 collapses. Reload — sidebar stays collapsed (state written to
 ``localStorage['pql.nbedit.filesVisible']``). Click again to
 restore; reload again; sidebar stays open.

3. **Open another notebook** — click ``two.py`` in the sidebar.
 Expect a hard navigation to ``/notebooks/edit/scratch/
 two.py``. Monaco re-mounts against the new buffer; kernel
 reconnects against the new ``(user_id, path)`` key; the
 sidebar's current-row highlight moves to ``two.py``.

4. **New notebook** — click the ``+`` icon in the sidebar header.
 A Bootstrap modal opens with a path input. Type
 ``scratch/sprint67-playbook.py`` and hit Enter (or click
 ``Create``). Expect:
 - ``POST /api/notebooks/create`` returns 200
 ``{"path": "scratch/sprint67-playbook.py", "status": "created"}``.
 - Modal closes, page navigates to the new path.
 - Editor shows one empty code cell.
 - Type ``x = 1`` and wait 1.5 s for autosave. Refresh the
 sidebar — the new file is now listed.

 Error case: re-open the modal, type the same path again,
 ``Create``. Expect an inline red alert ``notebook already
 exists at 'scratch/sprint67-playbook.py'`` and the modal
 stays open.

5. **Rename notebook** — hover over ``sprint67-playbook.py`` in
 the sidebar → a pencil icon appears → click it. Rename modal
 opens with the current path pre-filled. Change to
 ``scratch/sprint67-playbook-renamed.py`` and click ``Rename``.
 Expect:
 - ``PATCH /api/notebooks/rename`` succeeds.
 - Because the renamed file is the *currently open* one, the
 page hard-reloads at the new URL.
 - Any outputs or run rows from step 4 survive the rename
 (verify: run ``x = 42`` before renaming, then check
 Variable Explorer after reload — ``x`` should still be
 defined server-side after the kernel reconnects, and the
 persisted output row re-plays on the new path because of
 the ``rename_path`` UPDATE in ``notebook_outputs.py``).

 Now rename a *different* file (pencil on ``two.py``) to
 ``two-renamed.py``. Expect the modal to close and the sidebar
 to refresh in place — no full-page reload, because the
 currently-open notebook was untouched.

6. **Delete notebook** — hover over ``one.py`` → trash icon
 appears → click. Confirmation modal opens showing the full
 path and the cascade warning. Click ``Delete``. Expect:
 - ``DELETE /api/notebooks?path=scratch/one.py`` returns 200.
 - Modal closes; sidebar row disappears.
 - File is gone from disk (verify: ``ls notebooks/scratch/`` has
 no ``one.py``).
 - Any ``notebook_outputs`` rows keyed to that path are purged
 (verify:
 ``sqlite3 pointlessql.db "select count(*) from notebook_outputs where file_path='scratch/one.py'"``
 prints ``0``).

 Try to delete the currently-open file (trash icon on
 ``sprint67-playbook-renamed.py`` after step 5's redirect).
 Expect the icon to be disabled with tooltip ``Close this
 notebook first`` — deleting the open file from underneath the
 editor is a dangling-state hazard we refuse at the UI layer.

### What shipped for

- [pointlessql/services/notebook_workspace.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/notebook_workspace.py)
 — added ``resolve_notebook_target``, ``create_empty_notebook``,
 ``rename_notebook``, ``delete_notebook``; ``resolve_upload_target``
 now delegates to the shared resolver.
- [pointlessql/services/notebook_outputs.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/notebook_outputs.py)
 — added ``rename_path`` next to ``clear_path`` so rename
 preserves the replay cache.
- [pointlessql/api/main.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py)
 — ``POST /api/notebooks/create``, ``PATCH /api/notebooks/rename``,
 ``DELETE /api/notebooks?path=…``; all admin-only, all audit-logged.
- [frontend/js/notebook/file_tree.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/file_tree.js)
 — new ESM module exporting ``createFileTreeSlice`` (Alpine
 sub-object) and ``flattenTree`` (pure). AbortController lives in
 closure scope.
- [frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
 — spreads the file-tree slice into the returned reactive root;
 ``mount()`` fires ``loadTreeInitial()`` alongside the kernel /
 LSP opens.
- [frontend/js/notebook/bootstrap.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/bootstrap.js)
 — added matching pre-mount keys + method stubs so Alpine's
 ``x-show`` / ``x-text`` expressions survive the pre-mount window.
- [frontend/templates/pages/notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 — ``<aside class="pql-nbedit-files">`` + Files toggle in the
 toolbar + three Bootstrap modals (new / rename / delete). CSS
 added for ``.pql-nbedit-files`` and its per-row affordances.
- [scripts/check-frontend-no-reactive-monaco.sh](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/check-frontend-no-reactive-monaco.sh)
 — widened forbidden list to cover ``this._treeFetchCtrl`` /
 ``this._treeAbort``.

**No Alembic migration** — the ``notebook_outputs`` and
``notebook_cell_runs`` schemas from earlier sprints already have
``file_path`` as a plain column, so the rename is a straight
``UPDATE`` and the delete cascade is a straight ``DELETE``.

### What the replay caught

**BUG-67-01 — Alpine x-show vs Bootstrap's ``.modal`` CSS.** Alpine
3.14.1's ``x-show`` sets ``style.display = ''`` on "show" (empty
string, not the captured inline ``'block'``). Bootstrap 5's CSS
has ``.modal { display: none }`` with no override for ``.modal.show``
on the container itself (``.show`` only styles ``.modal-dialog``
transforms). Net effect: the first-time ``false → true``
transition on any ``.modal[x-show="…"]`` in the editor *removes*
the inline ``display: block`` we authored in the template → CSS
cascade kicks in → ``display: none`` from ``.modal`` wins → modal
stays invisible even while Alpine thinks ``newFileOpen=true``.

The pre-existing Catalog-Insert modal (-ish) has the same
latent bug — Ctrl+Shift+I rendered the dimmed overlay but no
modal content. Not noticed because the Catalog flow was
typically exercised via Playwright-MCP clicks in prior replays,
which fired ``data.catalogInsertOpen = true`` programmatically in
a state where the ``display:block`` was still in place — a red
herring pathway that masked the latent bug until 's
replay touched a cold modal.

Fix (applied to all four editor modals in this sprint): replace
``x-show`` with ``:class="{ 'd-block': flag }"``. Bootstrap's
``.d-block`` utility is ``display: block !important``, which
beats both Alpine's inline manipulation and the ``.modal {
display: none }`` CSS default. The inline ``style`` attribute
keeps just the backdrop ``background`` colour. ``x-cloak`` stays
so Alpine-reactive children don't flash on first paint.

Replayed Parts A–H in Firefox after the fix — all four modals
(Catalog, New, Rename, Delete) render and dismiss cleanly; the
six sidebar flows (render, toggle, open, new, rename-
current-file-hard-reload, delete-other-file-tree-refresh) all
pass.

## Part I — : multi-notebook tab bar

 fourth sprint adds a tab bar above the editor so the
user can keep several notebooks open in one page and switch
between them without a reload. Each tab hosts its own Monaco
editor + kernel WS + LSP WS — the closure-ref factory
is already N-instance-safe, and the affordance machinery
is editor-scoped (not model-scoped), so swapping tabs is a CSS
``display`` flip, not a Monaco teardown.

Setup: start with two ``.py`` notebooks in the workspace
(e.g. ``scratch.py`` and ``scratch/tab-b.py``). Clear
``localStorage['pql.nbedit.tabs.v1']`` before each replay so tab
hydration starts from a known state.

1. **Tab bar on first open** — navigate to
 ``/notebooks/edit/scratch.py``. Expect:
 - A horizontal tab strip directly below the nav bar with one
 tab labelled ``scratch.py`` (the basename of the URL path).
 - The tab has the "active" visual treatment (filled
 background + a thin bottom border in the Bootstrap primary
 colour).
 - An ``×`` close button appears on hover of the tab.
 - No dirty dot (the file was just saved / just materialised).
 - The Files sidebar toggle lives in the tab-bar's right-side
 area, **not** in the per-tab toolbar (the sidebar is
 shell-scoped, not tab-scoped).

2. **Open a second tab from the sidebar** — with the Files
 sidebar visible, click ``scratch/tab-b.py``. Expect:
 - No full page reload (the URL in the address bar stays on
 ``?path=scratch.py``, and the network log shows exactly one
 extra request: ``GET /api/notebook/doc?path=scratch/tab-b.py``).
 - A second tab slides in to the right; it becomes active.
 - The first tab's chrome loses the "active" styling but the
 tab itself stays in the strip.
 - The first tab's Monaco editor + kernel WS + LSP WS are
 preserved (confirm: ``monaco.editor.getEditors().length ===
 2`` in the console; ``monaco.editor.getModels().length === 2``;
 neither editor is disposed).

3. **Switch back and forth preserves state** — type
 ``x = 1`` in ``tab-b.py``'s editor, switch to ``scratch.py``,
 type ``y = 2``, switch back to ``tab-b.py``. Expect:
 - Each tab's cursor position + buffer content is intact.
 - Each tab's toolbar shows its own kernel status + Pyright
 status (both independently ``ready``).
 - The Variable Explorer in each tab is populated from that
 tab's own kernel (``x`` in one tab's panel, ``y`` in the
 other).

4. **Dirty dot on the tab chrome** — type into ``scratch.py``'s
 editor and assert the dirty dot (a small ``•`` in the tab)
 appears within one frame. Wait 1.5 s for autosave; the dot
 disappears once ``saveState`` flips to ``saved``. The dot
 reflects the tab's own dirty state, not the active tab's —
 switching away does not hide it.

5. **Close a clean tab** — click the ``×`` on ``scratch/tab-b.py``.
 Expect:
 - No confirmation prompt (the tab is clean).
 - The tab disappears from the strip.
 - The active tab becomes the left neighbour
 (``scratch.py``).
 - ``localStorage['pql.nbedit.tabs.v1']`` now lists only
 ``scratch.py``.
 - The Monaco editor + kernel WS for ``tab-b.py`` are torn
 down (``monaco.editor.getEditors().length === 1``).

6. **Close a dirty tab — confirm modal** — open ``tab-b.py``
 again, type a character to flip it dirty, then click its
 ``×`` before autosave fires. Expect:
 - A Bootstrap modal opens titled "Unsaved changes" with three
 buttons: Cancel, Discard & close, Save & close.
 - The modal uses the ``:class="{ 'd-block': flag }"``
 pattern (BUG-67-01); on off→on→off transitions the modal
 stays visible (``x-show`` strips the inline ``display:block``
 and Bootstrap's ``.modal { display: none }`` cascades).
 - ``Cancel`` dismisses the modal and leaves the tab in place.
 - ``Discard & close`` closes the tab without saving.
 - ``Save & close`` flushes ``POST /api/notebook/doc`` first,
 waits for the save to resolve, then closes. If the save
 errors, the modal stays open and the error toast surfaces
 via the per-tab ``save()`` handler.

7. **localStorage persistence across reload** — with two tabs
 open (``scratch.py`` active, ``tab-b.py`` lazy), reload the
 page. Expect:
 - Both tabs rehydrate from ``localStorage['pql.nbedit.tabs.v1']``
 + the URL's ``?path=…`` overrides the stored ``active``.
 - The URL-matching tab is mounted eagerly (Monaco + kernel
 up within ~2 s).
 - The non-active tab is present in the strip but **lazy** —
 its inner ``x-if`` stays false, no second Monaco is created,
 no second kernel WS opens. Verify via
 ``monaco.editor.getEditors().length === 1`` immediately
 post-reload.
 - Click the lazy tab: within ~1.5 s, a second Monaco is
 created, ``GET /api/notebook/doc?path=…`` fires, and the
 tab's kernel/Pyright handshake begins. Subsequent switches
 back to the eager tab are free (no re-mount).

8. **Kernel sharing for two tabs of the same file** — click
 ``scratch.py`` in the sidebar while ``scratch.py`` is already
 open as a tab. Expect:
 - ``openTab('scratch.py')`` short-circuits (the path is
 already open) → the existing tab becomes active, no second
 tab added.
 - No extra kernel WS opens because the shell detected the
 duplicate path.
 - This is the frontend counterpart of the kernel registry's
 ``(user_id, path)`` keying: even if the
 frontend *had* opened a second tab for the same path, the
 server would hand both WS subscribers the same
 ``KernelSession``. We verify this server-side invariant is
 preserved end-to-end by instrumenting
 ``kernel_registry._sessions`` and asserting exactly one
 ``KernelSession`` exists for a given ``(user_id,
 'scratch.py')`` key across the lifetime of the test.

9. **Rename an open notebook updates the tab chrome** — with
 ``scratch/tab-b.py`` open in a tab, hover its row in the
 sidebar → pencil icon → rename to ``scratch/tab-b-renamed.py``.
 Expect:
 - The sidebar's ``PATCH /api/notebooks/rename`` returns 200.
 - The tab chrome updates in place: label flips to
 ``tab-b-renamed.py``; its DOM tab id stays stable
 (``tab:scratch/tab-b.py`` → ``tab:scratch/tab-b-renamed.py``?
 No — the shell *updates* the tab's ``path`` + ``label``
 but the ``id`` stays the -stable-per-session
 value to keep Monaco + kernel WS alive across the rename).
 - No full-page reload — the rename-current-file
 hard-reload is replaced by an in-place event (``pql:file-
 renamed``) so Monaco + kernel survive.
 - ``localStorage`` now lists the new path.

10. **Delete an open notebook closes the tab silently** — in the
 sidebar, hover a non-active open tab's row (e.g. the other
 open ``.py``) → the trash icon is **disabled** (tooltip:
 ``Close this notebook in every tab first``). Click the
 matching tab's ``×`` to close it, then click the row's
 trash. Confirm delete. Expect:
 - ``DELETE /api/notebooks?path=…`` returns 200.
 - The sidebar row disappears (tree refresh).
 - If the file had still been open in any tab at the moment
 the sidebar emits ``pql:file-deleted``, the shell silently
 closes the matching tab (no confirm, no toast — the file
 is gone on disk, preserving an orphan tab confuses the
 user).

11. **Tab cap / overflow** — open tabs until the ten-tab cap is
 reached; the eleventh call produces a toast
 ``Tab limit reached (10). Close a tab before opening
 another.`` and the new tab is not added. With many tabs
 open, the tab strip overflows horizontally with
 ``overflow-x: auto`` — no dropdown overflow menu.

### What shipped for

- [pointlessql/api/main.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py) —
 new ``GET /api/notebook/doc`` endpoint returning the same
 ``{cells, dirty, outputs}`` bundle the HTML route embeds
 (via shared ``_build_notebook_doc_bundle`` helper). The
 only backend change in this otherwise frontend-only sprint.
- [frontend/js/notebook/editor_shell.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/editor_shell.js)
 — **new** module: Alpine factory ``createNotebookEditorShell``
 owning the tabs model, activeTabId, close-confirm modal,
 localStorage persistence, and the cross-scope event bus
 (``pql:open-tab`` / ``pql:file-renamed`` / ``pql:file-
 deleted`` / ``pql:tab-state-changed`` / ``pql:save-tab``).
- [frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
 — renamed ``createNotebookEditor`` → ``createNotebookTabEditor``;
 added ``tabId`` + optional ``initial`` + optional
 ``bundleLoader`` args; moved cell/output initialisation into
 ``mount()`` so lazy tabs bootstrap on first activation; emits
 ``pql:tab-state-changed`` for ``mounted`` / ``dirty`` /
 ``saveState`` transitions so the shell can keep tab chrome
 in sync without polling a proxy.
- [frontend/js/notebook/bootstrap.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/bootstrap.js)
 — two factories registered on ``window``:
 ``notebookEditorShell`` (outer scope) and
 ``notebookTabEditor`` (per-tab scope). Each has its own pre-
 mount stub scope to avoid the BUG-64-02 class of
 pre-mount-warning spam.
- [frontend/js/notebook/file_tree.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/file_tree.js)
 — API reshaped to accept ``getActivePath`` + ``isPathOpenInAnyTab``
 callbacks instead of a static ``currentPath``; navigation-like
 methods (``openNotebook``, ``submitCreateNotebook``,
 ``submitRenameNotebook``, ``submitDeleteNotebook``) dispatch
 CustomEvents on ``document`` instead of calling
 ``window.location.assign``.
- [frontend/templates/pages/notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 — outer ``x-data="notebookEditorShell(...)"`` wrapper; new
 ``.pql-nbedit-tabbar`` above the layout; tab panes via
 ``<template x-for="tab in tabs">`` with inner
 ``x-data="notebookTabEditor(...)"`` scopes and lazy-mount
 ``x-if="tab.mounted || tab.id === activeTabId"``; new
 close-confirm modal (``:class`` gated per BUG-67-01). Files
 toggle moved from per-tab toolbar to shell-level tab-bar.
- [scripts/check-frontend-no-reactive-monaco.sh](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/check-frontend-no-reactive-monaco.sh)
 — widened forbidden list to cover ``this._tabRefs`` and
 ``this._tabFactories`` so a future temptation to aggregate
 per-tab closure bags onto the shell's Alpine proxy trips CI.

### What the replay caught

**Tab-mounted flag lost during stub→real scope swap.** The
bootstrap stub seeds ``tabs = [seedTab]`` synchronously with
``mounted: false``. The template's pre-mount ``x-init="tab.mounted
= true; mount()"`` sets the flag on the seed object, but the
subsequent ``editor_shell.js`` import + ``_hydrateTabs()`` replaces
the tabs array wholesale — the flag is dropped on the floor.
Alpine's ``:key="tab.id"`` diff reuses the DOM element so x-init
does **not** re-fire, leaving ``tab.mounted: false`` on the live
tab. Net effect: opening a second tab makes the first tab's
``x-if`` (``tab.mounted || active``) evaluate false, Alpine
unmounts the pane, Monaco + kernel are torn down mid-session.

Fix: the per-tab factory fires ``pql:tab-state-changed { mounted:
true }`` **synchronously** at the top of ``mount()``, before any
async Monaco/kernel/LSP work. The shell's listener updates
``tab.mounted`` in the tabs array. Discovered during Part I
step 2 replay when a second-tab-open visibly blanked the first
tab — the fix landed in the same sprint before the walkthrough
went green.

## Part J — : markdown-it + KaTeX + pencil pin

 fifth sprint replaces the regex markdown
renderer with ``markdown-it`` (CommonMark-conformant — tables,
nested lists, task lists, autolinking), layers KaTeX for
``$…$`` / ``$$…$$`` math via ``markdown-it-texmath``, and adds a
per-cell pencil button that pins a markdown cell into source view
independently of cursor position. All three libs are vendored under
``frontend/js/vendor/`` via ``scripts/vendor-markdown-libs.sh``
(mirrors the Monaco pattern from ADR 0001); the pencil button is
the first per-cell affordance gated by the descriptor's
new optional ``affordances`` array.

Setup: run ``bash scripts/vendor-markdown-libs.sh`` once to populate
the three gitignored vendor dirs. Clear
``localStorage['pql.nbedit.tabs.v1']`` and open
``/notebooks/edit/scratch.py`` in Firefox (Playwright MCP's
bundled Firefox; the Chrome channel is unsupported per the
 backstory).

1. **markdown-it renders a CommonMark table** — insert a markdown
 cell whose source is:
 ```
 | Catalog | Tables |
 |---|---|
 | bronze | 12 |
 | silver | 7 |
 ```
 Expect: the preview view zone renders a real ``<table>`` with
 borders (styled by ``.pql-nbedit-md-preview table`` in the
 template). The regex renderer would have rendered
 this as plain text lines — a regression here means the new
 script tag order is wrong or markdown-it failed to load.

2. **Nested bullet list** — source:
 ```
 - top
 - nested
 - deeper
 ```
 Expect: real nested ``<ul>`` structure with progressive
 indentation. The pass only supported one level.

3. **Inline KaTeX math** — source ``Einstein: $E = mc^2$``.
 Expect: ``$E = mc^2$`` renders as a ``<span class="katex">``
 block with the KaTeX-formatted equation (the inline ``c^2``
 shows as a superscript, not a literal ``^2``). Hovering over
 the KaTeX node shows no browser console warnings.

4. **Block KaTeX math** — source:
 ```
 $$\int_0^1 x^2 \, dx = \frac{1}{3}$$
 ```
 Expect: centered block equation with an integral sign, proper
 limits, and a fraction. The output wraps in a ``<section>``
 (texmath's block marker) and the CSS pins it centered.

5. **Pencil pin — keeps source visible** — hover the markdown
 cell's toolbar; a pencil button appears to the right of the
 cell-type label. Click it. Expect:
 - Button icon switches from ``bi-pencil`` (outline) to
 ``bi-pencil-fill`` and gains the warning-coloured
 ``pql-nbedit-pin-btn-active`` treatment.
 - Button title flips to "Unpin (return to preview)".
 - Click into a different cell (code or markdown). The pinned
 cell's source stays visible — the auto-hide on
 cursor-leave is suppressed for this cell.

6. **Pencil unpin** — click the pinned cell's pencil again. Expect:
 - Button reverts to outline ``bi-pencil``.
 - With the cursor still outside the cell, Monaco re-hides the
 source; the preview pane takes over the view zone.

7. **Pin state is session-only** — pin a cell, then hard-reload
 the page (Ctrl+Shift+R). Expect: every markdown cell opens
 with pencil outline / unpinned. The flag lives on the in-memory
 ``markdownZones[cellId]`` object; the jupytext marker grammar
 and ADR 0001 are untouched by this sprint.

8. **Cells without ``pin`` affordance have no pencil** — verify
 code cells do not render a pencil button. Only cell types
 whose registry descriptor includes ``affordances: ['pin']``
 (currently ``markdown`` only) get the button.

9. **KaTeX drop sanity (optional)** — temporarily delete the
 ``<script src="/static/js/vendor/katex/...">`` and the
 ``<script src="/static/js/vendor/markdown-it-texmath/...">``
 tags from ``frontend/templates/pages/notebook_editor.html``
 and hard-reload. Expect: markdown still renders; ``$E=mc^2$``
 shows as literal dollar-wrapped text. Revert the template
 edits — this step only exists to prove the drop is
 one-commit-sized for the trim policy.

10. **Regression — / 67 / 68 stay green** — run the
 relevant earlier-sprint steps (toolbar affordances, file tree
 sidebar, tab bar) and confirm no visual regressions.

### What shipped for

- [frontend/js/notebook/markdown.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/markdown.js)
 — full rewrite. ``renderMarkdown(src)`` now delegates to a
 cached ``markdown-it`` instance (cached in a module-scoped
 ``let mdSingleton`` variable, not on any Alpine proxy) with
 linkify + breaks, layered ``markdown-it-texmath`` when
 ``window.texmath`` + ``window.katex`` are both present.
- [frontend/js/notebook/cell_types.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_types.js)
 — ``markdown`` descriptor gains ``affordances: ['pin']``.
- [frontend/js/notebook/cell_affordances.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_affordances.js)
 — pencil button in ``makeToolbarDom`` gated on
 ``descriptor.affordances.includes('pin')``; new exported
 ``setPinState(record, pinned)`` flips the icon + title +
 active class.
- [frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
 — ``handlers.onTogglePin`` owns the in-memory pin flag on
 ``markdownZones[cellId].editModePinned``; ``updateHiddenAreas``
 skips pinned cells; a rebuild re-syncs the pencil state via
 ``setPinState`` so a content edit that rebuilds affordances
 does not desync the button icon.
- [frontend/templates/pages/notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 — KaTeX CSS link, three UMD ``<script>`` tags (markdown-it,
 katex, texmath — KaTeX before texmath so ``.use(window.texmath,
 { engine: window.katex })`` finds its engine), bootstrap.js
 cache bust bumped to ``?v=sprint69``, new CSS for the pencil
 button + markdown-it tables / nested lists / blockquotes /
 KaTeX blocks.
- [scripts/vendor-markdown-libs.sh](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/vendor-markdown-libs.sh)
 — **new** fetch script mirroring ``vendor-monaco.sh``. Pins
 markdown-it 14.1.0, markdown-it-texmath 1.0.0, KaTeX 0.16.11
 via env overrides. Appends a ``window.texmath = texmath``
 line to the vendored texmath.js (ships CommonJS-only).
- [.gitignore](https://github.com/FloHofstetter/PointlesSQL/blob/main/.gitignore) — three new vendor dirs.
- [scripts/check-frontend-no-reactive-monaco.sh](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/check-frontend-no-reactive-monaco.sh)
 — widened forbidden list to cover ``this._mdSingleton``,
 ``this._mdPinState``, ``this._pinHandlers`` so a future
 temptation to cache the markdown-it instance or pin-handler
 closures on an Alpine proxy trips CI. markdown-it carries deep
 rule registries that Alpine's reactive walk would wrap and
 traverse on every re-render — 's variant of the
 / BUG-64-02 class of bug.

### What the replay caught

**BUG-69-01 — UMD vs AMD loader-order collision.** See the
Found-bugs section at the top of this playbook for the full
write-up. Caught on the first Part-J open; fixed in the same
sprint by swapping the script-tag order so the three markdown
vendor bundles load before Monaco's AMD loader activates.
The Playwright-MCP replay is what surfaced it — the module
graph boots fine in Node / unit-style probes where no AMD loader
exists at all.

## Part K — : Outline / TOC panel + cell jump

 sixth sprint bolts on a right-side Outline panel — peer
of the Variable Explorer (same 320px slot, mutually exclusive).
Lists markdown H1/H2/H3 ATX headings (indented per level) and
each code cell's first non-blank stripped line (``# Load …`` stripped
to ``Load …``, truncated to 60 chars with ``…``). Click an entry
and Monaco jumps to the cell's first content line via
``revealLineInCenter`` + ``focus``.

Extraction is a pure regex over ``cell.source`` — no markdown-it
coupling, which deliberately dodges the UMD/AMD
loader-order class (BUG-69-01). The outline renders even if the
markdown vendor bundle fails to load.

### Fixture

Open ``/notebooks/edit/scratch.py`` in Firefox (Playwright
MCP's bundled Firefox; the system Chrome channel is unsupported
per the backstory). The fixture used when replaying
 is four cells:

```
# %% [markdown] pql_cell_id="aaaaaaaa-…"
# Heading 1
## Sub
### Deep

# %% pql_cell_id="bbbbbbbb-…"
import pandas as pd
x = 1

# %% pql_cell_id="cccccccc-…"
# Load customers
df = pd.DataFrame({"a": [1,2,3]})

# %% [markdown] pql_cell_id="dddddddd-…"
Just prose here, no headings at all.
```

### Step 1 — Panel mounts empty

1. Confirm the ``Outline`` toolbar button is present between
 ``Variables`` and ``Run cell``, styled ``btn-outline-secondary``
 (outlined).
2. Confirm no right panel is visible.

### Step 2 — Open outline

1. Click ``Outline``.
2. Assert: button flips to ``btn-primary`` (filled).
3. Assert: a 320px right aside appears (``display: block``,
 ``offsetWidth: 320``).
4. Assert: five rows rendered in source order:
 - "Heading 1" (l1 indent, bold)
 - "Sub" (l2 indent)
 - "Deep" (l3 indent, muted)
 - "import pandas as pd" (code row, monospace, muted)
 - "Load customers" (code row — leading ``# `` stripped)
5. The no-heading markdown cell contributes zero rows.

### Step 3 — Click jumps + scrolls + focuses

1. Move Monaco's cursor to line 1 and call
 ``editor.revealLine(1)`` so the target cell is out of view.
2. Click the "import pandas as pd" row.
3. Assert: ``editor.getPosition()`` returns
 ``{lineNumber: <cell body line>, column: 1}``.
4. Assert: ``editor.hasTextFocus() === true`` (``revealLineInCenter``
 + ``focus`` both fired).

### Step 4 — Edit updates outline (debounced 150ms)

1. Insert ``## Newly Added\n`` before the ``## Sub`` line via
 ``model.setValue()``.
2. Wait 250ms (> 150ms debounce).
3. Assert: outline grows to 6 rows; the heading-level sequence
 becomes ``[H1 Heading 1, H2 Newly Added, H2 Sub, H3 Deep]``.
4. ``model.setValue(original)`` to restore and wait another 250ms
 so the on-disk fixture stays clean.

### Step 5 — Mutual exclusion with Variables

1. With Outline open, click ``Variables``.
2. Assert after ~50ms: ``outlineVisible === false``,
 ``variablesVisible === true``; outline aside ``display: none``,
 vars aside ``display: block``.
3. Click ``Outline``.
4. Assert: flags swap again; only the Outline panel is visible.

### Step 6 — Close both

1. Click ``Outline`` again.
2. Assert: ``outlineVisible === false``, ``variablesVisible ===
 false``; Monaco fills the full horizontal room.

### Step 7 — Gated CI still passes

```
bash scripts/check-frontend-no-reactive-monaco.sh
```

Expect exit 0 with ``OK — no Alpine-reactive Monaco/Worker/WS/
timer refs in frontend/js/notebook/``. The widening
added ``outlineEntries``, ``outlineTimer``, ``outlineDebounce`` to
the forbidden list so a future change cannot regress by parking
the 150ms debounce handle on Alpine's proxy.

### Known quirks (v1)

- **Leading ``#`` stripped from code-cell label.** A first
 non-blank line like ``# Load customers`` becomes "Load
 customers" — intentional, mirrors how Databricks names cells
 via ``# MAGIC`` / ``# COMMAND`` prefixes. A Python comment
 that happens to start with ``#`` + space will read as the
 cell's name, which is usually what the author wants.
- **Fenced code blocks inside markdown cells are NOT
 fence-aware.** A line like ``# bash comment`` at column 1
 inside a ```` ```bash ```` fence still regex-matches as H1.
 Accepted for v1; fence tracking would pull markdown-it
 back into the extractor and reopen the BUG-69-01 class.
- **Setext headings (``Heading\n====`` / ``----``) not
 rendered.** ATX (``#``, ``##``, ``###``) only; H4+ silently
 skipped.

### What the replay caught

**BUG-70-01 — stale closure ``cells`` in debounced recompute.**
First Part-K Step 4 replay flipped the expected outline entries
to the PRE-edit list, not the POST-edit one. Root cause: the
initial wiring called ``buildOutline(cells)`` with the
closure-scoped ``cells`` array, which is only refreshed on save
path + ``rescanDecorations()``. Free-form typing inside a cell
never refreshes it, so the 150ms debounce was reading stale
data. Fix in the same commit: ``recomputeOutline()`` re-splits
from the live Monaco model (``splitCells(model.getValue())``)
with a fallback to ``cells`` when ``refs.get('model')`` is null
(mount-time before Monaco creates the model). See
[frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
``recomputeOutline`` near the ``scheduleAutosave`` block.

**BUG-70-02 — over-stripping jupytext prefix double-shifted
headings.** First regex pass stripped a leading ``# `` from
each markdown line to mirror 's ``rebuildMarkdownZones``
unwrap. That turned ``## Sub`` → ``# Sub`` (level 1) and
``### Deep`` → ``## Deep`` (level 2) — every heading's level
shifted down by one. Root cause: the server's notebook_doc
load path already strips the jupytext ``# `` comment-prefix
before sending the bundle; Monaco's model and
``/api/notebook/doc`` both return raw, unwrapped markdown. Fix
in the same commit: removed the client-side strip from
[frontend/js/notebook/outline.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/outline.js).

### Files changed

- [frontend/js/notebook/outline.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/outline.js)
 — **new**, pure ``buildOutline(cells)`` regex extractor.
- [frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
 — closure-scoped ``outlineEntries`` + 150ms debounce timer;
 reactive ``this.outline`` assigned fresh slice on change;
 ``toggleOutline`` (mutex with ``toggleVariables``);
 ``jumpToCell(cellId)`` reusing ``findCellMarkerLine``;
 recompute re-splits from the live Monaco model to sidestep
 the stale-closure-``cells`` trap.
- [frontend/templates/pages/notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 — ``Outline`` toolbar button; right-side ``<aside class
 ="pql-nbedit-outline">`` mirroring the Variables aside;
 inline CSS for per-level indent classes.
- [scripts/check-frontend-no-reactive-monaco.sh](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/check-frontend-no-reactive-monaco.sh)
 — widened forbidden pattern to cover
 ``this._outlineEntries``, ``this._outlineTimer``,
 ``this._outlineDebounce``.

## Part L — : SQL cell (DuckDB via PQL.sql)

**Preconditions.**

- A seeded 3-part table the test admin can ``SELECT`` from.
 In a fresh dev stack ``main.default.demo`` is the canonical
 fixture; if absent, register one via the SQL editor or the
 ``/admin`` seeders before running the playbook.
- ``scratch.py`` open in [/notebook/editor](http://127.0.0.1:8000/notebook/editor) — a Code
 cell at top is fine; the SQL cell goes below.

**L1 — ``+ SQL`` inserter shows up.** Hover the cell-bottom
inserter zone and assert a ``+ SQL`` button appears next to
``+ Code`` and ``+ Markdown``. ``mcp__playwright__browser_click``
on it. A new cell with ``pql-nbedit-cell-band-sql`` band class,
toolbar label ``SQL``, ``▶`` run button, and a
``pql-nbedit-result-var`` input mounts. Marker line on disk
should read ``# %% [sql] pql_cell_id="<uuid>"`` with no
``result_var=`` segment yet.

**L2 — Type SELECT.** ``mcp__playwright__browser_type`` into
the cell:

```
SELECT * FROM main.default.demo LIMIT 5
```

Saved pill cycles ``Unsaved`` → ``Saved`` after the autosave
debounce.

**L3 — Set ``result_var``.** Click the ``pql-nbedit-result-var``
input, ``mcp__playwright__browser_type`` ``demo_df``. Wait at
least 400 ms for the 300 ms debounce + the autosave debounce.
Read the raw file: marker line should now read
``# %% [sql] pql_cell_id="<uuid>" result_var="demo_df"``.
Fields with non-identifier characters (e.g. ``df!``) flip the
input's border to ``--bs-danger`` via
``pql-nbedit-result-var-error`` and do **not** mutate the marker
until the user fixes the input.

**L4 — Run SQL cell.** Click the ``▶`` button or press
``Shift+Enter``. Status pill flips ``idle`` → ``running``
within ~50 ms; flips to ``ok`` within ~3 s. Output zone
contains a pandas-styled HTML table with the LIMIT-5 rows
(``pql-nbedit-output-html`` wrapper).

**L5 — Reference ``result_var`` from a Python cell.** Insert a
``+ Code`` cell below the SQL cell, type ``demo_df.shape``, run
with ``Shift+Enter``. Output zone shows ``(5, N)`` where N is
the column count of ``main.default.demo``.

**L6 — Variable Explorer.** Toggle the right-side Variables
panel. ``demo_df`` appears with type ``pandas.DataFrame``,
shape ``[5, N]``, ``head()``-rendered preview HTML.

**L7 — Round-trip stability.** Hard-reload the editor
(``mcp__playwright__browser_navigate`` to the same URL). SQL
cell + ``result_var`` input + output zone all restore from the
on-disk file + ``notebook_outputs`` replay. ``demo_df`` is
**not** in the kernel namespace until the cell runs again — the
DataFrame lives in the kernel process which restarts on browser
reload's WS reconnect (kernel session is kept across reloads,
but globals only persist within a kernel session).

**L8 — Drop ``result_var`` segment.** Clear the
``pql-nbedit-result-var`` input. Wait the debounce. Marker
line drops the ``result_var="..."`` segment and reads
``# %% [sql] pql_cell_id="<uuid>"`` again. Re-run the SQL cell
— output still renders inline; Variables panel does **not**
display ``demo_df`` (no binding).

**L9 — Privilege denial path.** As a non-admin user (or with
``SELECT`` revoked on ``main.default.demo``), run an L4-style
SQL cell against the table. Expected: the output zone shows an
``error`` mime with ``ename=AuthorizationError`` and the
soyuz-catalog denial message — the kernel never executes the
query, so no ``[*]`` running indicator and no DataFrame binding.

### Files changed

- [frontend/js/notebook/cell_types.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_types.js)
 — registered ``sql`` descriptor with ``markerTag: ' [sql]'``,
 ``canExecute: true``, ``bandClass: 'pql-nbedit-cell-band-sql'``,
 ``affordances: ['result_var']``.
- [frontend/js/notebook/cell_parser.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_parser.js)
 — widened ``CELL_MARKER_RE`` to capture optional
 ``result_var="<ident>"`` (group 3); ``splitCells`` /
 ``joinCells`` round-trip the field; ``RESULT_VAR_RE`` exported
 for the affordance validator.
- [frontend/js/notebook/cell_affordances.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_affordances.js)
 — ``result_var`` input + 300 ms debounce + ``RESULT_VAR_RE``
 validator with ``pql-nbedit-result-var-error`` CSS class;
 ``+ SQL`` inserter button next to ``+ Code`` / ``+ Markdown``;
 ``removeAffordances`` clears the debounce on cell teardown.
- [frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
 — ``runCellById`` branches on ``typeId === 'sql'`` and emits
 the ``execute_sql`` WS frame; ``runAllCells`` / ``runCellsAbove``
 share the new ``sendCellFrame`` helper; ``cellResultVarById``
 reads the marker; ``applyResultVarToMarker`` writes back via
 ``editor.executeEdits`` so on-disk text stays the source of
 truth.
- [pointlessql/api/main.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py)
 — new ``execute_sql`` WS branch that re-uses the
 ``/api/sql/execute`` parse + privilege-check loop via the
 shared ``_resolve_sql_approved_tables`` helper; refactored
 ``_wipe_cell_for_new_execute`` so ``execute`` and
 ``execute_sql`` share the persistence prelude.
- [pointlessql/services/kernel_session.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/kernel_session.py)
 — ``_NOTEBOOK_BOOTSTRAP_CODE`` defines ``__pql_sql_run`` in
 the kernel; ``_run_bootstrap`` runs it silently between
 ``wait_for_ready`` and the pump tasks (with a
 ``_BOOTSTRAP_TIMEOUT`` safety net); ``restart`` re-queues the
 bootstrap via the regular execute path under reserved cell_id
 ``__pql_sql_bootstrap__`` so ``_is_internal_cell`` skips
 persistence.

### What the replay caught

**BUG-71-01 — pandas got the column-spec dicts as the column index.**
The first ``__pql_sql_run`` definition passed ``res.columns``
straight to ``pd.DataFrame(...)``, but ``SQLResult.columns`` is
``list[dict[str, str]]`` (each entry has ``name`` + ``type``). The
DataFrame still constructed, but ``DataFrame.__repr__`` raised
``TypeError`` when ``display(df)`` triggered the text/plain fallback
— the cell emitted both an ``html`` mime (which rendered fine) and
an ``error`` mime (which painted the cell red). Status pill read
``ok`` because ``execute_reply.status`` only watches the cell's top-
level result, not displays mid-flight. Fix in the same commit:
extract the bare names via ``[c.get("name") if isinstance(c, dict)
else c for c in res.columns]`` before constructing the DataFrame.
Caught at the L4 step on the first replay.
- [frontend/templates/pages/notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 — ``.pql-nbedit-cell-band-sql`` band hue + ``.pql-nbedit-result-var``
 input styling.
- [scripts/check-frontend-no-reactive-monaco.sh](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/check-frontend-no-reactive-monaco.sh)
 — widened forbidden pattern to cover ``this._resultVarTimers``
 / ``this._sqlBootstrap``.

## Part M — : ipywidgets minimal placeholder

**Preconditions.**

- ``ipywidgets>=8.1`` is in the resolved environment (added to
 ``pyproject.toml`` as part of this sprint; ``uv sync`` after
 pulling).
- Fresh kernel — restart it via the toolbar after the dependency
 bump so the kernel subprocess inherits the new ``sys.path``.
- ``scratch.py`` open in [/notebook/editor](http://127.0.0.1:8000/notebook/editor).

**M1 — Synthetic widget bundle renders the placeholder card.**
Insert a Code cell, type:

```python
from IPython.display import display
display({'application/vnd.jupyter.widget-view+json':
 {'model_id': 'abc12345xyz9876', 'version_major': 2,
 'version_minor': 0}}, raw=True)
```

Run. Assert: status pill flips ``running`` → ``ok``; output zone
contains a ``.pql-nbedit-output-widget-placeholder`` card showing
``model_id: abc12345…`` and the disclaimer ``Interactive widgets
will render in a future release. Install widgets in the kernel to
see live updates here.`` No ``error`` mime; no console errors.

**M2 — Real ``ipywidgets.IntSlider``.** Insert a Code cell:

```python
import ipywidgets as w
w.IntSlider(value=42, min=0, max=100)
```

Run. Assert: status pill flips ``ok``; output zone shows the
placeholder card with the kernel-emitted widget ``model_id``.
Behind the scenes the kernel emits ``execute_result`` with BOTH
``application/vnd.jupyter.widget-view+json`` and ``text/plain``
("IntSlider(value=42)"); the renderer's new branch picks the
widget bundle over the text fallback so users do not see the bare
repr leak through.

**M3 — Comm frames silently swallowed.** Run:

```python
slider = w.IntSlider()
slider.observe(lambda c: print(c))
slider
```

Assert: placeholder card renders for the slider; no client-side
crash; **DevTools console shows no ``comm_open`` / ``comm_msg`` /
``comm_close`` entries** — the WS forwards them as before but the
client's ``renderKernelMsg`` swallows them (a single
``IntSlider()`` instantiation emits dozens; logging would flood
DevTools and obscure real errors). ``slider.observe(...)``'s
callback never fires because no real widget-manager round-trip
exists yet — this is expected; the placeholder text says so.

**M4 — Missing-``model_id`` fallback.** Send a malformed widget
bundle:

```python
display({'application/vnd.jupyter.widget-view+json': {}}, raw=True)
```

Assert: output zone shows a placeholder card whose text is exactly
``Widget output (unrenderable)`` (no model_id, no disclaimer).

**M5 — Persistence + replay.** Hard-reload the editor. Assert:
the M1 / M2 / M4 placeholder cards rebuild from
``notebook_outputs`` rows — the widget bundle survives the
serialise / deserialise round-trip because 's
``mime_bundle`` column stores the raw ``data`` dict verbatim.

### What the replay caught

**BUG-72-01 — ES module disk cache hides new mime branches in
PointlesSQL until you hard-reload.** The notebook editor's
[bootstrap.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/bootstrap.js) carries a
``?v=sprintNN`` query param so its own ``<script>`` invalidates,
but the modules it dynamically imports
([editor_shell.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/editor_shell.js) +
[main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js) + the eight
siblings, including [output_renderer.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/output_renderer.js))
do **not** carry a version param, so the browser keeps the
previous deploy's modules in disk cache even after the bootstrap
script bumps. Verified via
``import('/static/js/notebook/output_renderer.js?_t=' + Date.now())``
in DevTools — the cache-busted URL pulled the new code, while the
unversioned import in the editor page still resolved to the old
function body. Initial workaround attempt (bumping bootstrap.js's
``?v=`` query) does **not** propagate to the inner dynamic
imports — the URLs they request are unchanged, so the disk-cached
siblings still load. **Real fix landed in the tail
commit**: a new HTTP middleware
[``static_module_revalidate_middleware``](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py)
stamps ``Cache-Control: no-cache, must-revalidate`` on every
``/static/js/notebook/*`` response so the browser MUST issue a
conditional ``If-Modified-Since`` request next time. Starlette's
StaticFiles answers 304 when unchanged (cheap) but a sprint-fresh
module is delivered immediately on the next page load — no
hard-reload needed. Verified by reloading the editor in
Playwright-MCP without ``Ctrl+Shift+R``: the dynamic
``import('/static/js/notebook/output_renderer.js')`` returned the
new function body that includes the widget branch.

### Files changed

- [pyproject.toml](https://github.com/FloHofstetter/PointlesSQL/blob/main/pyproject.toml) — added
 ``ipywidgets>=8.1`` dependency. ``uv lock`` resolved
 ``ipywidgets-8.1.8`` + ``jupyterlab-widgets-3.0.16`` +
 ``widgetsnbextension-4.0.15``.
- [frontend/js/notebook/output_renderer.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/output_renderer.js)
 — new high-priority MIME branch in ``renderMimeBundle`` for
 ``application/vnd.jupyter.widget-view+json`` (must come BEFORE
 ``text/html`` so the widget bundle wins over the fallback
 ``text/plain`` repr).
- [frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
 — silent swallow of ``comm_open`` / ``comm_msg`` / ``comm_close``
 in ``renderKernelMsg``.
- [frontend/templates/pages/notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 — ``.pql-nbedit-output-widget-placeholder`` + ``.pql-nbedit-widget-model-id``
 + ``.pql-nbedit-widget-note`` styles; bootstrap script version
 bumped to ``sprint72``.

**No Alembic migration.** Trim-safe — the placeholder branch is
the upgrade seam a future sprint will replace with a real
widget-manager.

## Part N — : per-cell run history + diff

**Preconditions.**

- Alembic 018 applied (``uv run alembic upgrade head`` after pull;
 verify with ``uv run alembic check``).
- ``scripts/vendor-diff-lib.sh`` has been run so
 ``frontend/js/vendor/jsdiff/diff.min.js`` exists (the script tag
 in [notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 references it as a vendored UMD bundle).
- ``scratch.py`` open in [/notebook/editor](http://127.0.0.1:8000/notebook/editor).

**N1 — History button mounts on every executable cell.** Hover any
code cell's toolbar. Assert: a clock-icon
``.pql-nbedit-history-btn`` appears next to the run button on every
``code`` and ``sql`` cell — and **not** on markdown
cells (markdown is ``canExecute: false``, so no run-history row
ever lands for it).

**N2 — Two runs of the same cell stack into the popover.** Pick
a code cell, run it (status pill ``ok``), edit the body to a
different value, run again (status pill ``ok`` with a higher
``execution_count`` pill). Click the History button. Assert:
popover header reads ``Last 2 runs``; both rows show timestamp
+ duration + status pill + ``[N]`` execution-count pill, both
carry a ``view diff`` button + a ``re-run`` button. Newest-first
ordering — the first row's stamp is later than the second's.

**N3 — Diff renders source-vs-current.** Edit the cell again so
the live Monaco buffer differs from both historical snapshots.
Open the popover, click ``view diff`` on the first (newest) row.
Assert: an inline jsdiff-rendered ``.pql-nbedit-diff`` table
appears under the row header with three classes of rows —
``.pql-nbedit-diff-ctx`` (unchanged context lines, sign ``" "``),
``.pql-nbedit-diff-del`` (lines only in the historical source,
sign ``"-"``), ``.pql-nbedit-diff-add`` (lines only in the live
buffer, sign ``"+"``). Click ``hide diff`` (button text flips):
the table collapses; click again, it re-renders.

**N4 — Re-run replays the historical source without touching
Monaco.** In the popover, click the ``re-run`` button on the
older row. Assert: popover closes; cell's status pill flips to
``running`` then back to ``ok``; **the Monaco buffer is unchanged**
(your N3 edits remain on screen); a fresh history row lands at
the TOP of the popover on the next open with the historical
source as its ``source`` column. Variable Explorer reflects the
historical version's side effects (e.g. ``x`` = the old value).

**N5 — Identical-source diff message.** Edit the cell back to
match a historical source verbatim. Open popover, click ``view
diff`` on the matching row. Assert: ``(sources are identical)``
text instead of an empty table.

**N6 — File-delete cascades into the history table.** Sidebar
``Delete`` action on a notebook → assert ``notebook_cell_run_sources``
rows for that file_path are gone (cascade-via-service in
``clear_path``). File-rename: rows re-key onto the new path
(cascade-via-service in ``rename_path``); pre-rename runs
survive in the popover after reload.

**N7 — Persistence across kernel restart.** Note the popover row
count. Restart the kernel. Open the popover again. Assert:
**all prior runs are still visible** — the history table is the
audit trail and explicitly survives kernel restarts (only file-
level operations cascade). ``clear_session`` does NOT touch the
history table.

**N8 — Per-cell clear-outputs preserves history.** Run a cell,
clear its outputs (``Clear`` palette command), open popover.
Assert: history rows still listed — ``clear_cell`` deletes
``notebook_outputs`` + the ``notebook_cell_runs`` upsert row, but
explicitly does NOT touch ``notebook_cell_run_sources`` (the
audit trail is what we want to PRESERVE across re-runs).

### What the replay caught

**BUG-73-01 — ``clear_cell`` cascade was wiping history on every
re-run.** The first version of the
[notebook_outputs.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/notebook_outputs.py)
service threaded ``NotebookCellRunSource`` deletes through the
``clear_cell`` cascade alongside ``NotebookOutput`` and
``NotebookCellRun``. But ``clear_cell`` is called from
``_wipe_cell_for_new_execute`` at the top of every execute_request
to wipe the previous run's outputs from the persistence cache —
threading the history table into that path meant every re-run
deleted the prior run's row before the new ``record_cell_run_start``
inserted its own. Result: only the most-recent run ever existed
in the table; popover header always read ``Last 1 run``. Caught
at the N2 step on the first replay (DB query showed exactly one
row even after three runs). Fix in the same commit: removed the
``NotebookCellRunSource`` delete from ``clear_cell`` AND
``clear_session``; cascade now lives only in ``clear_path`` (file
delete) and ``rename_path`` (file rename). ``notebook_cell_runs``
still cascades on ``clear_cell`` because that table holds
"current state per session", not history.

### Files changed

- [pointlessql/alembic/versions/018_notebook_cell_run_sources.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/alembic/versions/018_notebook_cell_run_sources.py)
 — new migration creating ``notebook_cell_run_sources`` with
 autoincrement id PK, ``ix_notebook_cell_run_sources_path_cell``
 on ``(file_path, cell_id, started_at)``. No FK to
 ``notebook_cell_runs`` — link is logical, cascade via service.
- [pointlessql/models.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/models.py)
 — new ``NotebookCellRunSource`` ORM model mirroring the migration.
- [pointlessql/services/notebook_outputs.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/notebook_outputs.py)
 — ``record_cell_run_start`` (insert + return id),
 ``record_cell_run_finish`` (stamp status + finish + execution
 count by id), ``list_cell_run_sources`` (newest-first read with
 ISO timestamps). ``clear_path`` + ``rename_path`` extended;
 ``clear_cell`` + ``clear_session`` deliberately NOT extended
 (BUG-73-01 fix).
- [pointlessql/api/main.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py)
 — ``pending_run_sources`` map keyed by ``(cell_id,
 kernel_session_id)``; ``_wipe_cell_for_new_execute`` calls
 ``record_cell_run_start`` and stashes the returned id;
 ``_handle_shell_lifecycle`` pops the id on ``execute_reply`` and
 calls ``record_cell_run_finish``. New
 ``GET /api/notebook/cell-runs?path=…&cell_id=…&limit=…`` admin-
 gated route. ``pending_run_sources`` cleared on kernel restart
 + on dropped reply on a fresh start for the same key.
- [frontend/js/notebook/run_history.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/run_history.js)
 — new module. Closure-scoped ``_historyCache``, ``_popoverEl``,
 ``_inflightAbort``. ``openPopover`` fetches
 ``/api/notebook/cell-runs``, renders newest-first with
 ``view diff`` (jsdiff-based ``.pql-nbedit-diff`` table, cap at
 10000 input lines) + ``re-run`` (sends historical source via
 ``execute`` WS frame, does NOT touch Monaco).
- [frontend/js/notebook/cell_affordances.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_affordances.js)
 — clock-icon ``.pql-nbedit-history-btn`` mounted on every
 ``canExecute`` cell; ``handlers.onShowHistory(cellId, anchorEl)``
 callback plumbed through ``mountAffordances``.
- [frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
 — ``openHistoryPopover(cellId, anchorEl)`` reads current source
 via ``cellSourceById`` for diffing, threads ``onRerun`` →
 ``sendKernelFrame({type:'execute',...})`` (NOT
 ``execute_sql``, since SQL history rows hold the wrapped
 ``__pql_sql_run(...)`` snippet — re-running it executes the
 same SQL the kernel saw without re-walking privilege checks).
- [scripts/vendor-diff-lib.sh](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/vendor-diff-lib.sh)
 — new vendoring script for jsdiff 5.2.0 (npm ``diff``, MIT,
 ~10 KB UMD ``window.Diff``). Mirrors
 ``vendor-markdown-libs.sh`` shape.
- [.gitignore](https://github.com/FloHofstetter/PointlesSQL/blob/main/.gitignore)
 — added ``frontend/js/vendor/jsdiff/`` (mirrors the markdown-it
 / KaTeX gitignore entries).
- [frontend/templates/pages/notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 — ``<script src="/static/js/vendor/jsdiff/diff.min.js?v=sprint73">``
 tag; bootstrap.js bumped to ``?v=sprint73``;
 ``.pql-nbedit-history-btn`` /
 ``.pql-nbedit-history-popover`` / ``.pql-nbedit-diff`` styles.
- [scripts/check-frontend-no-reactive-monaco.sh](https://github.com/FloHofstetter/PointlesSQL/blob/main/scripts/check-frontend-no-reactive-monaco.sh)
 — widened forbidden pattern to cover ``this._historyCache`` /
 ``this._historyPopover`` / ``this._historyAbort``.

**Trim-safe.** (theme + keymap + phase close) does not
import the run-history module; revert is sprint-local.

## Part O — : settings drawer + keymap overlay + phase close

**Preconditions.**

- ``scratch.py`` open in [/notebook/editor](http://127.0.0.1:8000/notebook/editor) on a fresh
 profile (localStorage empty so defaults apply).
- Hard-reload the page if upgrading from a pre-sprint-74 deploy —
 the bootstrap.js version was bumped to ``?v=sprint74``.

**O1 — Toolbar buttons mount.** Inspect the toolbar. Assert: a
gear icon button (``i.bi-gear``) and a question-mark icon
(``i.bi-question-circle``) sit between the ``Outline`` toggle and
the ``Run cell`` button. Both have hover tooltips; clicking them
opens the drawer / overlay singletons lazy-mounted to ``<body>``
on first open.

**O2 — Settings drawer opens + changes persist.** Click the gear
icon. Assert: a right-side Bootstrap offcanvas
(``.pql-nbedit-settings-drawer``) slides in with three controls —
``Theme`` (select), ``Font size`` (number), ``Autosave
debounce`` (number). Defaults: ``vs-dark`` / ``13`` / ``1500``.
Change theme to ``vs`` (light); assert Monaco's background flips
from dark to ``rgb(255, 255, 254)`` within a tick (Monaco's
``setTheme`` is page-global). Change font-size to ``18``; assert
``editor.getOptions().get(fontInfo).fontSize === 18`` and the
line heights visibly grow. Change debounce to ``500``; edit a
cell; assert the ``Saved`` pill flips ~500 ms after last
keystroke (down from 1500 ms). All three persist to
localStorage under
``pql.nbedit.theme.v1`` / ``pql.nbedit.fontSize.v1`` /
``pql.nbedit.autosave.debounceMs.v1``.

**O3 — Reload preserves settings.** Reload the page. Assert:
drawer re-initialises with the user's saved values; Monaco
opens in the light theme with 18 px font; autosave fires after
500 ms. No ``ReferenceError`` on Alpine's x-show /
x-bind expressions during the pre-mount window — bootstrap.js's
tab-scope stub was extended with ``outlineVisible`` +
``outline`` + the four new methods so the toolbar
template never evaluates an undefined symbol.

**O4 — Ctrl+Alt+/ keymap overlay.** Focus Monaco. Press
``Ctrl+Alt+/``. Assert: a centred Bootstrap modal
(``.pql-nbedit-keymap-overlay``) opens with a 15-row table
listing every command — ``shiftEnter`` / ``ctrlEnter`` (direct
keybinds), then 13 ``pql.*`` palette actions ( +
70 + 73 + 74 additions). Each row shows id / description /
binding / added-in-sprint. Close via the ``×`` button; press
``Ctrl+Alt+/`` again → reopens. (``Ctrl+/`` stays bound to
Monaco's default ``toggle-line-comment`` — we deliberately do
not shadow it.)

**O5 — Palette actions work.** Open Monaco's built-in command
palette (``F1`` or ``Ctrl+Shift+P``). Type ``pql.``. Assert:
all 13 ``pql.*`` actions from the overlay show up with the same
id and label; firing any of them has the same effect as the
corresponding toolbar button or keybinding (e.g.
``pql.openSettings`` opens the drawer; ``pql.openHistory`` opens
the run-history popover for the cell at the cursor;
``pql.toggleOutline`` toggles the outline aside).

**O6 — Multi-tab theme sharing.** Open two notebook tabs via the
 sidebar. Change the theme in tab A; assert tab B's
Monaco also flips — ``monaco.editor.setTheme`` is page-global
(documented UX). Font-size + debounce are per-instance, so
changing them in tab A does NOT bleed into tab B without an
explicit broadcast on that tab's editor too. (Current
implementation: both tabs subscribe to
``document``-level ``pql:settings-changed`` events, so they DO
stay in sync by design — confirmed at replay time.)

**O7 — close state.** Open
[ROADMAP.md](https://github.com/FloHofstetter/PointlesSQL/blob/main/ROADMAP.md); scroll to the node.
Assert: header flipped ``⏳ open`` → ``✅ done`` with a close-out
prose block summarising Sprints 65-74 and their commit hashes.
CHANGELOG.md shows the entry at the top of
``[Unreleased]``.

### Files changed

- [frontend/js/notebook/settings_drawer.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/settings_drawer.js)
 — new module. Bootstrap offcanvas with theme / fontSize /
 debounce controls; broadcasts ``pql:settings-changed``
 CustomEvent on change; reads + persists via three localStorage
 keys under the ``pql.nbedit.*.v1`` namespace ( /
 convention).
- [frontend/js/notebook/keymap_overlay.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/keymap_overlay.js)
 — new module. Static 15-row commands array + Bootstrap modal
 renderer. Reachable via the toolbar ``?`` button, ``Ctrl+Alt+/``
 keybind, and the ``pql.openKeymap`` palette action.
- [frontend/js/notebook/main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js)
 — imports both new modules; applies loaded settings on Monaco
 create (``theme`` / ``fontSize``); lifts ``_autosaveDebounceMs``
 out of module scope so ``scheduleAutosave`` reads it at
 flush-queue time; listens for ``pql:settings-changed`` and
 re-applies via ``monaco.editor.setTheme`` +
 ``editor.updateOptions({fontSize})`` + the debounce mutation;
 ``registerPaletteActions`` extended with
 ``pql.toggleOutline`` / ``pql.openHistory`` /
 ``pql.openSettings`` / ``pql.openKeymap``; new Alpine methods
 ``openSettings`` / ``openKeymap`` /
 ``openHistoryForCurrentCell``.
- [frontend/js/notebook/bootstrap.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/bootstrap.js)
 — extended the tab-scope stub with ``outlineVisible`` /
 ``outline`` and the four new Alpine methods so the
 pre-mount window does not emit ``ReferenceError`` on
 ``x-show`` / ``@click`` expressions.
- [frontend/templates/pages/notebook_editor.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/notebook_editor.html)
 — gear + ``?`` toolbar buttons; bootstrap.js script tag bumped
 to ``?v=sprint74``.

### What the replay caught

**BUG-74-01 — double-backticks inside an HTML template literal
terminated the string early, crashing the mount.** The keymap
overlay's ``buildModal`` included a footer explainer that used
GitHub-flavoured markdown-style double backticks (``\`pql.*\```)
inside the backtick-quoted ``.innerHTML`` template literal.
JavaScript's template-literal grammar does not nest backticks —
the first inner backtick closed the literal, and the rest of the
HTML became a syntax error inside ``buildModal``, which threw
the moment ``mountKeymapOverlay`` called it. Symptom: Alpine's
``mount()`` caught the error at [main.js:317](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js#L317)
with a ``Error @ http://…/main.js:317`` log; the settings drawer
mounted fine (earlier in the mount flow), but the keymap overlay
never materialised and the per-cell affordances never rebuilt.
Fix in the same commit: replaced ``\`\`pql.*\`\``` with plain
``pql.*`` text. Caught pre-gate via
``mod.createNotebookTabEditor({...}).mount()`` in a cache-busted
import, which surfaced the real stack trace
(``buildModal@keymap_overlay.js:137:18``) that the
catch-and-log in mount hid.

### close

 is the final sprint of. The phase-12.7
ROADMAP node flips ``⏳ open`` → ``✅ done``. Summary of what
landed across the phase:

- **** — module split + closure-refs factory + BUG-64-02
 reactivity-boundary grep gate.
- **** — cell-type registry + per-cell affordances (run
 button, status pill, exec-count pill, elapsed pill, inserter).
- **** — file-tree sidebar + notebook CRUD endpoints.
- **** — multi-notebook tab bar (N Monaco instances).
- **** — markdown-it + KaTeX + pencil-pin toggle.
- **** — outline / TOC panel + cell-jump.
- **** — SQL cell type (DuckDB via PQL.sql,
 ``result_var=``).
- **** — ipywidgets minimal placeholder (``comm_*``
 swallow + widget-view+json card).
- **** — per-cell run history + diff (Alembic 018).
- **** — settings drawer + keymap overlay + phase close.

## tail — BUG-71-02 + BUG-72-01 root fix + replay completion

After 's commit landed, a closing audit pass replayed the
parts of L / M / N / O that the live walkthrough had skipped. Two
bugs surfaced and were fixed in a single follow-up commit;
documentation of BUG-72-01 above was also corrected (the original
"workaround" claim that bumping bootstrap.js's ``?v=`` query
fixed the cache problem was wrong — see the corrected paragraph
in the "What the replay caught" section).

### BUG-71-02 — server-side notebook_doc dropped the [sql] tag + result_var on round-trip

's frontend correctly parsed and serialised
``# %% [sql] pql_cell_id="…" result_var="…"`` markers, but the
server-side
[``notebook_doc.py``](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/notebook_doc.py)
service used jupytext for both load and save. jupytext only
recognises ``[markdown]`` as a cell-type tag — anything else
(``[sql]``, ``[raw]``, …) is silently dropped from the marker
line, and the cell is parsed as a plain code cell. The
``result_var`` segment was equally invisible. Result: opening a
notebook whose disk file had a SQL cell rendered it as a code
cell on the editor (no SQL band, no run-via-execute_sql, no
``result_var`` input populated); saving the editor's SQL cell
back stripped the tag again. Save also rejected
``cell_type='sql'`` outright in the
[``api_save_notebook_doc``](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py)
validator — it only allowed ``code`` / ``markdown`` — so
autosave silently failed for SQL cells.

**Fix (single follow-up commit):**

1. Extended
 [``notebook_doc.NotebookCell``](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/services/notebook_doc.py)
 with an optional ``result_var: str | None`` field.
2. Added a module-level ``_PQL_MARKER_RE`` mirroring
 [cell_parser.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/cell_parser.js)'s
 ``CELL_MARKER_RE``.
3. ``load_document`` post-parses the raw.py file with the regex
 to recover ``[sql]`` tags + ``result_var`` segments and
 overrides what jupytext returned.
4. ``save_document`` post-writes the.py file (after
 ``jupytext.write``) via a new ``_rewrite_sql_markers`` helper
 that rewrites code-cell markers for SQL cells back to
 ``# %% [sql] pql_cell_id="…" result_var="…"``.
5. ``api_save_notebook_doc`` accepts ``cell_type='sql'`` +
 reads optional ``result_var``.
6. ``api_load_notebook_doc`` includes ``result_var`` in the JSON
 bundle for every cell.
7. [main.js](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/js/notebook/main.js) normalises
 ``result_var`` ↔ ``resultVar`` at the wire boundary on both
 load (incoming bundle) and save (outgoing POST body).

**Verified post-fix:**

- L7 round-trip: a fixture file with
 ``# %% [sql] pql_cell_id="…" result_var="demo_df"`` opens with
 ``cellType='sql'``, ``result_var`` input pre-populated, SQL
 band CSS rendered. ``GET /api/notebook/doc?path=…`` returns
 ``{cell_type:'sql', result_var:'demo_df'}`` for that cell.
- L8 drop ``result_var=``: clearing the input rewrites the
 marker line to ``# %% [sql] pql_cell_id="…"`` (segment dropped,
 ``[sql]`` tag preserved).
- L9 privilege denial: a SQL cell against
 ``nonexistent.schema.forbidden`` surfaces
 ``CatalogNotFoundError: Catalog 'nonexistent' does not exist``
 in the cell's output zone before the kernel executes.

### BUG-72-01 root fix landed

The original "bump bootstrap.js's ``?v=``" workaround claim was
wrong. The real fix in the same follow-up commit:
[``static_module_revalidate_middleware``](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/main.py)
stamps ``Cache-Control: no-cache, must-revalidate`` on every
``/static/js/notebook/*`` response. Starlette's StaticFiles
already supports conditional GETs via
``If-Modified-Since`` — the middleware just forces the browser to
issue them. Verified: a non-hard-reload page load delivers the
post-fix renderer's widget branch without manual cache-bust.

### additional Playwright-MCP coverage post-fix

- **L6 Variable Explorer:** SQL cell with
 ``result_var="demo_df"`` runs → Variables panel shows
 ``demo_df`` as ``pandas.DataFrame`` shape ``[5, 4]``.

### additional Playwright-MCP coverage post-fix

- **M1** synthetic widget bundle → placeholder card with
 truncated ``model_id``.
- **M2** real ``ipywidgets.IntSlider()`` → placeholder card with
 the kernel-emitted ``model_id`` (8-char prefix).
- **M3** ``slider.observe(...)`` → placeholder renders, no
 client crash, no ``comm_*`` console noise.
- **M4** missing ``model_id`` → ``Widget output (unrenderable)``
 fallback.

### additional Playwright-MCP coverage post-fix

- **N6** file-delete cascade: ``clear_path('disposable.py')``
 zeroed ``notebook_cell_run_sources`` for that path; other
 files' rows untouched.
- **N7** kernel-restart persistence: history row count for cell
 ``bbbbbbbb`` stayed at 2 across a kernel restart (``clear_session``
 deliberately does NOT cascade into the history table).
- **N8** clear-outputs preserves history: a fresh run +
 ``pql.clearOutputs`` palette action grew the history table from
 2 → 3 rows; the per-execute audit trail explicitly survives the
 output-zone wipe.

### additional Playwright-MCP coverage post-fix

- **O3** reload persistence: localStorage carries
 ``pql.nbedit.theme.v1`` / ``pql.nbedit.fontSize.v1`` /
 ``pql.nbedit.autosave.debounceMs.v1`` across navigations;
 Monaco re-applies all three on mount.
- **O5** palette actions: ``editor.getAction('pql.openSettings').run()``,
 ``pql.openKeymap``, ``pql.toggleOutline``, ``pql.openHistory``
 all fire and produce the expected DOM effect (drawer opens,
 modal opens, outline aside flips, history popover renders).
- **O6** multi-tab broadcast: dispatching a manual
 ``pql:settings-changed`` ``CustomEvent`` on ``document`` flips
 the editor's ``fontSize`` (18 → 14) and Monaco's background
 (``rgb(30, 30, 30)`` → ``rgb(255, 255, 254)``) — confirms the
 per-tab listener picks up cross-tab broadcasts as designed.
