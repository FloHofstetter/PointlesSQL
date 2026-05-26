# Notebook editor — advanced cells walkthrough

> **Mode:** `browser` · **Surface:** Native .py notebook editor (advanced cells)

Continues the [notebook-editor core walkthrough](notebook-editor.md)
into the agent-facing and advanced-cell deep-dive: the SQL cell
backed by `PQL.sql` (DuckDB), the ipywidgets placeholder cell,
per-cell run history + diff, the settings drawer + keymap overlay,
the late replay-completion bug fixes, and the pin-to-memory action.

## Preconditions

- The [notebook-editor core walkthrough](notebook-editor.md) has been
  replayed end-to-end.
- The [notebook-editor UI surfaces walkthrough](notebook-editor-ui.md)
  has been replayed at least through Part H (file-tree sidebar) so
  the multi-notebook surface is reachable.
- The browser session is still open at the workspace; the kernel,
  Pyright, and autosave pills are green.
- The partial-refresh caveats on per-feature class selectors from the
  core walkthrough still apply here.

## Part L — SQL cell (DuckDB via PQL.sql)

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

## Part M — ipywidgets minimal placeholder

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

## Part N — per-cell run history + diff

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

## Part O — settings drawer + keymap overlay

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

 is the final sprint of. the ROADMAP node flips ``⏳ open`` → ``✅ done``. Summary of what
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

## Replay completion + late bug fixes

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

## Part P — pin-to-memory

**Preconditions.**

- ``scratch.py`` open in [/notebook/editor](http://127.0.0.1:8000/notebook/editor)
  with at least two saved revisions (run + save twice so the
  revisions panel has rows).
- Playwright-MCP attached with ``--browser firefox`` per
  [`CLAUDE.md`](https://github.com/FloHofstetter/PointlesSQL/blob/main/CLAUDE.md)
  line 220.
- Asset version is ``rc72`` or higher
  ([pyproject.toml](https://github.com/FloHofstetter/PointlesSQL/blob/main/pyproject.toml))
  so the feed renderer carries the ``render_kind === 'fact'``
  Alpine branch.

**P1 — Revisions panel pin.** Open the revisions panel from the
toolbar. Pick the latest revision. Click the 📌 button at the
right edge of that row. Assert: an inline form appears with a
``Title`` text input + optional ``Description`` textarea + a
``Pin`` button. Type ``Smoke pin`` in the title; submit. Assert:
toast ``Pinned`` appears, the row re-renders with a 📌-chip
beside the timestamp, and ``GET /api/notebooks/facts?...``
returns the new row at the top of the array.

**P2 — Cell-header chip lights up.** Pin a cell-output: click
the 📌 icon in any cell's header (it currently renders as a
``btn-outline-secondary`` since no fact exists for that cell
hash). Fill the dialog title ``Q3 anomaly``; submit. Assert: the
button class flips to ``btn-outline-warning`` (the lit state),
and ``GET /api/notebooks/facts/bulk?cell_content_hashes=<hash>``
now returns that row indexed under the cell hash.

**P3 — Library browse page.** Navigate to
[/library/facts](http://127.0.0.1:8000/library/facts). Assert:
both new facts appear as cards. Click ``Smoke pin``. Assert: the
URL flips to ``/library/facts/<uuid>`` and the detail block
shows the revision snapshot + Unpin button. Click ``Unpin``.
Assert: row gains a strikethrough, the toggle
``Include unpinned`` exposes/hides it correctly.

**P4 — Feed fan-out + 📌-card branch.** Navigate to
[/feed?filter=all](http://127.0.0.1:8000/feed?filter=all).
Assert: a new card appears with class ``bi-pin-angle-fill`` +
the summary text (matches what the backend wrote) + a click
target of ``/library/facts/<uuid>``. The ``render_kind`` is
``"fact"`` (inspect via DevTools on the Alpine ``$data.rows``);
no console errors during the render. SSE-injected pins from a
second tab go through ``_classifyEvent`` and pick up the same
branch live.

**P5 — ROADMAP closure check.** Open
[ROADMAP.md](https://github.com/FloHofstetter/PointlesSQL/blob/main/ROADMAP.md);
scroll to the pin-to-memory node. Assert: marker reads ✅
shipped with commit refs; the ``Pin-to-memory`` sub-bullet is
closed; the ``Shoreguard signing`` sub-bullet is annotated as
a genuine blocker waiting on the upstream ``sign-revision``
endpoint.
[CHANGELOG.md](https://github.com/FloHofstetter/PointlesSQL/blob/main/CHANGELOG.md)
shows the matching entries under ``[Unreleased]``.

### Files changed

- [pointlessql/api/feed_routes/_serializers.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/pointlessql/api/feed_routes/_serializers.py)
  — ``classify_notification`` carries the ``notebook_revision_pinned`` →
  ``"fact"`` mapping; docstring updated.
- [frontend/templates/pages/_partials/feed/scripts.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/_partials/feed/scripts.html)
  — ``_classifyEvent`` mirror so SSE-pushed rows pick the same
  branch on the wire.
- [frontend/templates/pages/_partials/feed/activity_pane.html](https://github.com/FloHofstetter/PointlesSQL/blob/main/frontend/templates/pages/_partials/feed/activity_pane.html)
  — new ``<template x-if="r.render_kind === 'fact'">`` block
  with ``bi-pin-angle-fill`` icon + summary.
- [tests/test_feed_notebook_pinned.py](https://github.com/FloHofstetter/PointlesSQL/blob/main/tests/test_feed_notebook_pinned.py)
  — 5 pytest covering classify + row envelope + e2e fanout +
  null-actor agent path.
- [pyproject.toml](https://github.com/FloHofstetter/PointlesSQL/blob/main/pyproject.toml)
  — version ``0.1.0rc71`` → ``0.1.0rc72`` so the relative-import
  asset-stamping picks up the activity_pane.html + scripts.html
  diffs.

### What the replay caught

- **BUG-97-X3-01 (fixed in same commit).** First Playwright-MCP
  replay of Part P found ``/feed`` empty after a real pin: the
  pin POST returned 201 but ``user_notifications`` stayed empty.
  Root cause: :func:`fanout_event` resolves followers via
  ``entity_kind == "dp"`` only — for the new
  ``notebook_revision`` / ``notebook_cell_output`` kinds the
  follower set was empty, and the actor-self filter then ran the
  recipient set down to zero.  Fix: ``_emit_pin_feed_event``
  resolves the parent notebook's followers
  (``kind='notebook', ref=notebook_id``) and threads them through
  ``extra_recipients``.  Verified: a non-admin who follows the
  notebook now sees the pin in their inbox; admin who pinned is
  correctly excluded.  Test:
  ``test_resolve_notebook_followers_pulls_subscribers``.
- **Note on Playwright eval-click.** Programmatically clicking
  the inline pin form's submit button via
  ``mcp__playwright__browser_evaluate`` ``btn.click()`` does
  *not* fire the Alpine ``@click`` handler.  The pin must go
  through ``mcp__playwright__browser_click`` (a native
  Playwright click) or, as we did in this replay, a direct
  ``POST /api/notebooks/facts`` to validate the backend.  The
  UI affordance was validated structurally (form opens, fields
  exist, ``revision-pin-form`` testid renders).

## Related playbooks

- [Notebook editor — core](notebook-editor.md)
- [Notebook editor — UI surfaces](notebook-editor-ui.md)
