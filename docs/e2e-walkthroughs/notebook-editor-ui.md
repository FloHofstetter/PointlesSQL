# Notebook editor — UI surfaces walkthrough

> **Mode:** `browser` · **Surface:** Native .py notebook editor (UI surfaces)

Continues the [notebook-editor core walkthrough](notebook-editor.md)
into the UI surface deep-dive: per-cell affordances, the file-tree
sidebar, multi-notebook tabs, markdown + KaTeX rendering, and the
Outline / TOC panel.

## Preconditions

- The [notebook-editor core walkthrough](notebook-editor.md) has been
  replayed end-to-end (auth, kernel-ready, Pyright-ready, autosave,
  Variable Explorer, Insert-from-catalog).
- The browser session from the core walkthrough is still open at
  `/notebooks/edit/scratch.py`, with the kernel + Pyright + autosave
  pills green.
- The partial-refresh caveats on per-feature class selectors from the
  core walkthrough still apply here.

## Part G — per-cell affordances

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
``started_at``, ``finished_at`` columns — will be the actually writes them back from the server.

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

## Part H — file-tree sidebar + notebook CRUD

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

## Part I — multi-notebook tab bar

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

## Part J — markdown-it + KaTeX + pencil pin

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

## Part K — Outline / TOC panel + cell jump

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


## Related playbooks

- [Notebook editor — core](notebook-editor.md)
- [Notebook editor — advanced cells](notebook-editor-advanced.md)
