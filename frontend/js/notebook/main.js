// Phase 12.7 Sprint 65 — Alpine factory orchestrator for the notebook editor.
//
// This module is the orchestrator only.  Cell parsing, ANSI/markdown
// rendering, Monaco loading, pyright JSON-RPC, and mime-bundle output
// rendering live in sibling modules; this file wires them together
// against a Monaco editor instance, an ipykernel WebSocket, and a
// pyright LSP WebSocket, and returns the reactive object Alpine binds
// to via x-data.
//
// Sprint 68 split the factory's responsibilities.  What used to be
// ``createNotebookEditor`` (single-tab page) is now
// ``createNotebookTabEditor`` (one Monaco instance over one path,
// N instances per page).  The file-tree sidebar + tab bar + tab
// list + localStorage persistence live in ``editor_shell.js``.
// The tab-editor factory takes an optional ``initial`` bundle; if
// ``null``, a ``bundleLoader`` async function is invoked on first
// mount to fetch ``/api/notebook/doc?path=…`` — this is how non-
// initial tabs lazy-load their content without a page reload.
//
// Sprint 76 carved out four more sub-modules: kernel_ws.js (ipykernel
// socket + frame routing), lsp_ws.js (pyright socket + didChange),
// cell_scanner.js (pure decoration-range scan), cell_editor.js (insert /
// add-below / add-above / result-var marker rewrite).  Each owns its
// own closure state so the orchestrator here is wiring-only.
//
// BUG-64-02 boundary discipline (Sprint-64; see closure_state.js):
// Monaco model / editor refs live in `refs` (createClosureRefs), not
// on the returned object.  Other private state (timers, DOM-node maps,
// accumulator buffers, parsed-cell cache) also lives in closure-scoped
// `let` vars to keep the reactive surface small and predictable.  The
// returned object carries primitive UI state + bound methods only.

import {
    joinCells,
    splitCells,
    computeContentHash,
} from './cell_parser.js';
import { getCellType } from './cell_types.js';
import {
    mountAffordances,
    mountInserter,
    moveToolbar,
    moveInserter,
    removeAffordances,
    setPinState,
} from './cell_affordances.js';
import { loadMonaco } from './monaco_loader.js';
import { registerPyrightProvidersOnce } from './pyright_client.js';
import { createClosureRefs } from './closure_state.js';
import { createOutlineRecomputer } from './outline.js';
import { openPopover as openRunHistoryPopover } from './run_history.js';
import { mountSettingsDrawer, openSettingsDrawer, loadSettings } from './settings_drawer.js';
import { mountKeymapOverlay, openKeymapOverlay } from './keymap_overlay.js';
import {
    currentCellAtCursor as introspectCurrentCellAtCursor,
    cellTypeOf as introspectCellTypeOf,
    cellSourceById as introspectCellSourceById,
    cellResultVarById as introspectCellResultVarById,
    cellEndLine as introspectCellEndLine,
    findCellMarkerLine as introspectFindCellMarkerLine,
} from './cell_introspector.js';
import { createOutputZoneManager } from './output_zone_manager.js';
import { createAutosaveScheduler } from './autosave_scheduler.js';
import { registerNotebookCommands } from './commands.js';
import { scanCellRanges, rangesToDecorations } from './cell_scanner.js';
import { createCellEditor } from './cell_editor.js';
import { createKernelWs } from './kernel_ws.js';
import { createLspWs } from './lsp_ws.js';
import { toast, csrfToken } from '../api.js';

// Databricks-style debounce: save 1500 ms after the user stops typing
// by default; Sprint 74 makes the value mutable per-tab via the
// settings drawer (broadcast over ``pql:settings-changed``).  The
// per-tab autosaveScheduler (autosave_scheduler.js) now owns the
// mutable debounce + timer + in-flight + queued state — main.js no
// longer keeps a module-level ``let _autosaveDebounceMs``.
const AUTOSAVE_DEBOUNCE_MS = 1500;
// Brief delay on initial load before auto-flushing the UUID-upgrade
// save for a foreign notebook.  Keeps the user-visible "Saving…" tag
// from flashing during the render.
const INITIAL_FLUSH_MS = 400;

export function createNotebookTabEditor({
    path,
    tabId = null,
    initial = null,
    bundleLoader = null,
}) {
    const refs = createClosureRefs(['editor', 'model']);

    // Closure-scoped private state.  Anything that does not need to
    // reactively re-render the DOM lives here, not as `this._X`.
    let decorationIds = [];
    let cells = [];
    let catalogTables = null;
    const cellAffordances = {}; // cellId → record (see cell_affordances.js)
    // Sprint 96: content-hash ↔ transient cell-id mapping maintained
    // alongside cellAffordances.  Outgoing WS frames address cells by
    // content-hash (stable identity, server-side DB key); incoming
    // kernel messages carry a ``content_hash`` that must be mapped
    // back to the transient ``cell-N`` label used as the DOM record
    // key.  Both maps are rebuilt in ``rebuildCellAffordances`` so a
    // source edit that changes the hash re-indexes atomically.
    const contentHashByCellId = {};
    const cellIdByContentHash = {};
    let reactiveRoot = null;
    let initialOutputs = [];
    let mounted = false;

    // Sprint 76: kernel + LSP socket handles live in the sub-module
    // factories; main.js only keeps the references so the alpine
    // methods (runCellById, interrupt/restart, etc.) can reach them.
    let kernelWs = null;
    let lspWs = null;

    // Sprint 75: closure-scoped sub-managers.  Each owns its own
    // private state (timers, view-zone maps, in-flight flags) inside
    // its factory closure — the BUG-64-02 reactivity boundary stays
    // intact because the manager objects themselves carry only method
    // refs, no raw timers / DOM nodes / Monaco refs.
    const autosaveScheduler = createAutosaveScheduler({
        debounceMs: AUTOSAVE_DEBOUNCE_MS,
    });
    const zoneManager = createOutputZoneManager({
        getEditor: () => refs.get('editor'),
        getModel: () => refs.get('model'),
        getCellEndLine: (cellId) => introspectCellEndLine(refs.get('model'), cellId),
        resolveCellId: (hash) => cellIdByContentHash[hash] || null,
    });
    const outlineRecomputer = createOutlineRecomputer({
        getCells: () => {
            const model = refs.get('model');
            return model ? splitCells(model.getValue()) : cells;
        },
        onUpdate: (entries) => {
            if (reactiveRoot) reactiveRoot.outline = entries;
        },
    });
    // Sprint 76: cell-editor factory is pure wrt alpine state and can
    // be instantiated at factory time; the other two need ``alpine``
    // (=this) and are instantiated inside mount().
    const cellEditor = createCellEditor({ refs, rescanDecorations });

    // Sprint 68: notify the shell whenever dirty or save state
    // transitions so the tab-bar chrome (filename + unsaved dot) stays
    // in sync without the shell having to poll per-tab scopes.
    function emitStateChange(extra) {
        if (!tabId) return;
        const detail = Object.assign({ tabId, path }, extra || {});
        document.dispatchEvent(
            new CustomEvent('pql:tab-state-changed', { detail }),
        );
    }

    return Object.assign({}, {
        path,
        tabId,
        dirty: false,
        loading: false,
        // "idle" | "pending" | "saving" | "saved" | "error"
        saveState: 'saved',
        // "connecting" | "ready" | "restarting" | "disconnected" | "error"
        kernelStatus: 'connecting',
        kernelSessionId: null,
        executingCells: {},
        // "connecting" | "ready" | "error" | "unavailable" — surfaced
        // next to kernelStatus on the toolbar so the user sees when
        // completions / hovers should respond.
        lspStatus: 'connecting',
        // Variable Explorer state — populated by the
        // ``__pql_namespace__`` internal introspect that fires on
        // every kernel idle.  `items` is the parsed dict of
        // name → {type, shape, repr, preview_html}.
        variables: {},
        variablesVisible: false,
        // Sprint 70: reactive mirror of the closure-scoped
        // ``outlineEntries`` list.  Assigned a fresh array on every
        // recompute so Alpine's x-for diffs once per real change.
        outline: [],
        outlineVisible: false,
        catalogInsertOpen: false,
        catalogInsertQuery: '',
        catalogTablesLoaded: false,
        // Sprint 68: flipped true after the first ``mount()`` resolves.
        mounted: false,

        async mount() {
            if (mounted) return; // Sprint 68: lazy-mount is fire-once.
            mounted = true;
            this.mounted = true;
            reactiveRoot = this;
            emitStateChange({ mounted: true });
            try {
                // Sprint 68: resolve the initial bundle.  First-tab
                // opens carry it eagerly (server-rendered into the
                // page template); lazy tabs defer to the bundleLoader
                // closure, which hits GET /api/notebook/doc.
                let bundle = initial;
                if (!bundle && bundleLoader) {
                    bundle = await bundleLoader();
                }
                if (!bundle) {
                    bundle = { cells: [], dirty: true, outputs: [] };
                }
                // Sprint 71 BUG-71-02 fix: server bundle uses
                // snake_case ``result_var`` for SQL cells; joinCells
                // + the rest of the JS cell shape expect camelCase
                // ``resultVar``.  Normalise at the wire boundary.
                cells = (bundle.cells || []).map((c) => {
                    const out = { id: c.id, cell_type: c.cell_type, source: c.source };
                    if (c.cell_type === 'sql') {
                        out.resultVar = c.result_var || c.resultVar || null;
                    } else {
                        out.resultVar = null;
                    }
                    return out;
                });
                outlineRecomputer.recompute();
                initialOutputs = bundle.outputs || [];
                this.dirty = bundle.dirty === true;
                this.saveState = this.dirty ? 'pending' : 'saved';
                emitStateChange({ dirty: this.dirty, saveState: this.saveState });
                const monaco = await loadMonaco();
                // Sprint 74: pull persisted theme + font-size + autosave
                // debounce from localStorage (defaults vs-dark / 13 /
                // 1500ms).
                const settings = loadSettings();
                autosaveScheduler.setDebounceMs(settings.debounceMs);
                const joined = joinCells(cells);
                const model = monaco.editor.createModel(joined.text, 'python');
                refs.set('model', model);
                const editor = monaco.editor.create(this.$refs.editor, {
                    model,
                    theme: settings.theme,
                    automaticLayout: true,
                    minimap: { enabled: false },
                    fontSize: settings.fontSize,
                    scrollBeyondLastLine: false,
                });
                refs.set('editor', editor);
                document.addEventListener('pql:settings-changed', (ev) => {
                    const next = (ev && ev.detail) || {};
                    if (next.theme) monaco.editor.setTheme(next.theme);
                    if (next.fontSize) editor.updateOptions({ fontSize: next.fontSize });
                    if (Number.isFinite(next.debounceMs)) {
                        autosaveScheduler.setDebounceMs(next.debounceMs);
                    }
                });
                mountSettingsDrawer();
                mountKeymapOverlay();
                applyDecorations(monaco, joined.cellRanges);

                // Sprint 76: kernel + LSP factories need ``this`` +
                // zoneManager + cellAffordances; construct them now
                // that mount has resolved those references.
                kernelWs = createKernelWs({
                    alpine: this,
                    zoneManager,
                    cellAffordances,
                    resolveCellId: (hash) => cellIdByContentHash[hash] || null,
                });
                lspWs = createLspWs({ alpine: this, refs, monaco });

                model.onDidChangeContent(() => {
                    this.dirty = true;
                    this.saveState = 'pending';
                    emitStateChange({ dirty: true, saveState: 'pending' });
                    autosaveScheduler.schedule(() => this.save());
                });
                editor.addCommand(
                    monaco.KeyMod.Shift | monaco.KeyCode.Enter,
                    () => this.runCurrentCell(),
                );
                editor.addCommand(
                    monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter,
                    () => this.runCurrentCell(),
                );
                registerNotebookCommands(monaco, editor, this);
                if (this.dirty) {
                    autosaveScheduler.scheduleWith(() => this.save(), INITIAL_FLUSH_MS);
                }
                // Sprint 96: populate the content-hash ↔ cell-id
                // mapping before the initial replay so persisted rows
                // key on the live cell labels; replaying first would
                // drop every row because the resolver would find no
                // match yet.
                rebuildCellAffordances();
                zoneManager.replayPersistedOutputs(initialOutputs);
                zoneManager.rebuildMarkdownZones();
                zoneManager.updateHiddenAreas();
                editor.onDidChangeCursorPosition(() => zoneManager.updateHiddenAreas());
                model.onDidChangeContent(() => {
                    rebuildCellAffordances();
                    zoneManager.rebuildMarkdownZones();
                    zoneManager.updateHiddenAreas();
                    lspWs.notifyDidChange();
                    outlineRecomputer.recomputeDebounced();
                });
                registerPyrightProvidersOnce(monaco);
                kernelWs.open();
                lspWs.open().catch((err) =>
                    console.error('[notebook-editor] lsp open failed', err));
                if (tabId) {
                    document.addEventListener('pql:save-tab', (ev) => {
                        const detail = ev && ev.detail;
                        if (!detail || detail.tabId !== tabId) return;
                        this.save();
                    });
                }
            } catch (err) {
                console.error('[notebook-editor] mount failed', err);
                toast('error', 'Editor failed to load: ' + err.message);
            }
        },

        clearCurrentCellOutputs() {
            const cell = introspectCurrentCellAtCursor(refs.get('editor'), refs.get('model'));
            if (!cell) return;
            zoneManager.clearOutput(cell.id);
            const contentHash = contentHashByCellId[cell.id];
            if (kernelWs && contentHash) {
                kernelWs.send({ type: 'clear_cell', content_hash: contentHash });
            }
        },

        runCurrentCell() {
            const cell = introspectCurrentCellAtCursor(refs.get('editor'), refs.get('model'));
            if (!cell) return;
            this.runCellById(cell.id, cell.cellType);
        },

        // Sprint 66: single execution seam that both keybindings,
        // toolbar, palette, and per-cell run buttons share.  The
        // registry's ``canExecute`` gate decides which cells run.
        // Sprint 71: SQL cells take a different WS frame so the
        // server-side route can parse + privilege-check before the
        // kernel ever sees the wrapped Python helper call.
        runCellById(cellId, cellType) {
            const model = refs.get('model');
            const typeId = cellType || introspectCellTypeOf(model, cellId);
            if (!getCellType(typeId).canExecute) return;
            const source = introspectCellSourceById(model, cellId);
            const contentHash = computeContentHash(source);
            // Re-pin the mapping so the matching kernel_msg routes back
            // here even if the user immediately edits the cell (the
            // edit would bump the hash; this keeps the just-dispatched
            // execution addressable until the execute_reply lands).
            contentHashByCellId[cellId] = contentHash;
            cellIdByContentHash[contentHash] = cellId;
            zoneManager.clearOutput(cellId);
            this.executingCells = { ...this.executingCells, [cellId]: true };
            if (!kernelWs) return;
            if (typeId === 'sql') {
                kernelWs.send({
                    type: 'execute_sql',
                    content_hash: contentHash,
                    source,
                    result_var: introspectCellResultVarById(model, cellId),
                });
            } else {
                kernelWs.send({
                    type: 'execute',
                    content_hash: contentHash,
                    code: source,
                });
            }
        },

        interruptKernel() {
            if (kernelWs) kernelWs.send({ type: 'interrupt' });
        },

        restartKernel() {
            this.kernelStatus = 'restarting';
            if (kernelWs) kernelWs.send({ type: 'restart' });
        },

        runAllCells() {
            const allCells = splitCells(refs.get('model').getValue());
            for (const c of allCells) {
                if (!getCellType(c.cell_type).canExecute) continue;
                zoneManager.clearOutput(c.id);
                this.executingCells = { ...this.executingCells, [c.id]: true };
                sendCellFrame(c);
            }
        },

        runCellsAbove() {
            const cell = introspectCurrentCellAtCursor(refs.get('editor'), refs.get('model'));
            if (!cell) return;
            const allCells = splitCells(refs.get('model').getValue());
            for (const c of allCells) {
                if (c.id === cell.id) break;
                if (!getCellType(c.cell_type).canExecute) continue;
                zoneManager.clearOutput(c.id);
                this.executingCells = { ...this.executingCells, [c.id]: true };
                sendCellFrame(c);
            }
        },

        // Sprint 66 + 76: cell-mutation delegations to cell_editor.js.
        // The four ops all rewrite the Monaco model + trigger
        // ``rescanDecorations`` on insert/add paths; applyResultVar
        // skips the rescan because it doesn't change cell boundaries.
        insertCellAfter: cellEditor.insertCellAfter,
        addCellBelow: cellEditor.addCellBelow,
        addCellAbove: cellEditor.addCellAbove,

        toggleVariables() {
            this.variablesVisible = !this.variablesVisible;
            if (this.variablesVisible) {
                this.outlineVisible = false;
                this._refreshVariables();
            }
        },

        // Sprint 70: right-side Outline panel toggle.  Mutually
        // exclusive with ``variablesVisible`` so the two asides never
        // occupy the 320px right slot at the same time.
        toggleOutline() {
            this.outlineVisible = !this.outlineVisible;
            if (this.outlineVisible) this.variablesVisible = false;
        },

        // Sprint 70: outline-row click handler.
        jumpToCell(cellId) {
            const editor = refs.get('editor');
            if (!editor) return;
            const contentLine = introspectFindCellMarkerLine(refs.get('model'), cellId) + 1;
            editor.setPosition({ lineNumber: contentLine, column: 1 });
            editor.revealLineInCenter(contentLine);
            editor.focus();
        },

        // Sprint 74: settings + keymap surface.  Both delegate to
        // module-scoped factories that mount lazily on first open so
        // the bootstrap stub doesn't import them eagerly.
        openSettings() {
            openSettingsDrawer();
        },
        openKeymap() {
            openKeymapOverlay();
        },
        openHistoryForCurrentCell() {
            const cell = introspectCurrentCellAtCursor(refs.get('editor'), refs.get('model'));
            if (!cell) return;
            const record = cellAffordances[cell.id];
            const anchorEl = record && record.historyBtn
                ? record.historyBtn
                : (record && record.runBtn ? record.runBtn : document.body);
            openHistoryPopover(cell.id, anchorEl);
        },

        async openCatalogInsert() {
            this.catalogInsertOpen = true;
            this.catalogInsertQuery = '';
            if (catalogTables) return;
            try {
                const res = await fetch('/api/tree');
                if (!res.ok) {
                    catalogTables = [];
                    this.catalogTablesLoaded = true;
                    return;
                }
                const tree = await res.json();
                const items = [];
                for (const cat of tree || []) {
                    for (const sch of cat.schemas || []) {
                        for (const tbl of sch.tables || []) {
                            items.push({
                                full: `${cat.name}.${sch.name}.${tbl.name}`,
                                catalog: cat.name,
                                schema: sch.name,
                                name: tbl.name,
                            });
                        }
                    }
                }
                catalogTables = items;
                this.catalogTablesLoaded = true;
            } catch (e) {
                console.error('[notebook-editor] tree fetch failed', e);
                catalogTables = [];
                this.catalogTablesLoaded = true;
            }
        },

        get filteredCatalogTables() {
            const q = (this.catalogInsertQuery || '').toLowerCase().trim();
            const all = catalogTables || [];
            if (!q) return all.slice(0, 80);
            return all.filter((t) => t.full.toLowerCase().includes(q)).slice(0, 80);
        },

        get catalogTablesEmpty() {
            return this.catalogTablesLoaded && (catalogTables || []).length === 0;
        },

        pickCatalogTable(table) {
            const editor = refs.get('editor');
            const snippet = `pql.read_table("${table.full}")`;
            const pos = editor.getPosition();
            if (!pos) return;
            const monaco = window.monaco;
            editor.executeEdits('pql-insert-catalog', [{
                range: new monaco.Range(pos.lineNumber, pos.column, pos.lineNumber, pos.column),
                text: snippet,
                forceMoveMarkers: true,
            }]);
            this.catalogInsertOpen = false;
            editor.focus();
        },

        _refreshVariables() {
            if (!this.variablesVisible) return;
            if (!kernelWs || this.kernelStatus !== 'ready') return;
            kernelWs.sendNamespaceIntrospect();
        },

        async save() {
            const model = refs.get('model');
            if (!model) return;
            autosaveScheduler.cancel();
            if (!autosaveScheduler.beginSave()) return; // queued — earlier in-flight save will re-fire
            this.loading = true;
            this.saveState = 'saving';
            try {
                const newCells = splitCells(model.getValue());
                // Sprint 71 BUG-71-02 fix: server expects snake_case
                // ``result_var`` for SQL cells; splitCells returns
                // camelCase ``resultVar`` to keep the JS-side cell
                // shape uniform.  Normalise here at the wire boundary.
                const wireCells = newCells.map((c) => {
                    const out = { id: c.id, cell_type: c.cell_type, source: c.source };
                    if (c.cell_type === 'sql') out.result_var = c.resultVar || null;
                    return out;
                });
                const resp = await fetch('/api/notebook/doc', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken(),
                    },
                    body: JSON.stringify({ path: this.path, cells: wireCells }),
                });
                if (!resp.ok) {
                    const text = await resp.text();
                    throw new Error(text || `save failed (${resp.status})`);
                }
                cells = newCells;
                this.dirty = false;
                this.saveState = 'saved';
                emitStateChange({ dirty: false, saveState: 'saved' });
            } catch (err) {
                console.error('[notebook-editor] save failed', err);
                this.saveState = 'error';
                emitStateChange({ dirty: this.dirty, saveState: 'error' });
                toast('error', 'Save failed: ' + err.message);
            } finally {
                this.loading = false;
                autosaveScheduler.endSave(() => this.save());
            }
        },
    });

    // ─────────────────── closure-scoped helpers ───────────────────
    //
    // Defined after the return object so the orchestrator's outer
    // shape reads top-down.  Each helper closes over `refs` plus the
    // closure-scoped state above; none touches `this`.

    function applyDecorations(monaco, ranges) {
        const editor = refs.get('editor');
        if (!editor) return;
        decorationIds = editor.deltaDecorations(
            decorationIds,
            rangesToDecorations(monaco, ranges),
        );
    }

    function rescanDecorations() {
        const model = refs.get('model');
        const ranges = scanCellRanges(model);
        applyDecorations(window.monaco, ranges);
        cells = splitCells(model.getValue());
        rebuildCellAffordances();
        outlineRecomputer.recompute();
    }

    // Sprint 71: send the matching frame for a parsed cell.  Single
    // place that knows about the SQL → ``execute_sql`` branch so the
    // run-all / run-above paths stay symmetric with ``runCellById``.
    // Sprint 96: WS frames address cells by ``content_hash`` — the
    // parsed ``cell.content_hash`` is recomputed by ``splitCells`` so
    // no hashing happens here; the transient ``cell.id`` is used only
    // for the local ``executingCells`` / zone-manager routing.
    function sendCellFrame(cell) {
        if (!kernelWs) return;
        contentHashByCellId[cell.id] = cell.content_hash;
        cellIdByContentHash[cell.content_hash] = cell.id;
        if (cell.cell_type === 'sql') {
            kernelWs.send({
                type: 'execute_sql',
                content_hash: cell.content_hash,
                source: cell.source,
                result_var: cell.resultVar || null,
            });
        } else {
            kernelWs.send({
                type: 'execute',
                content_hash: cell.content_hash,
                code: cell.source,
            });
        }
    }

    // Sprint 73: open the per-cell run-history popover.  Resolves the
    // current Monaco source for diffing against historical snapshots;
    // ``onRerun`` ships the historical source straight to the kernel
    // via the existing ``execute`` WS frame (NOT ``execute_sql``,
    // since the history rows for SQL cells already hold the wrapped
    // ``__pql_sql_run(...)`` snippet — re-running it executes the same
    // SQL the kernel saw originally without re-walking the route's
    // privilege check).
    function openHistoryPopover(cellId, anchorEl) {
        const currentSource = introspectCellSourceById(refs.get('model'), cellId);
        openRunHistoryPopover({
            path,
            contentHash: contentHashByCellId[cellId] || computeContentHash(currentSource),
            anchorEl,
            currentSource,
            onRerun: (historicalSource) => {
                const historicalHash = computeContentHash(historicalSource);
                contentHashByCellId[cellId] = historicalHash;
                cellIdByContentHash[historicalHash] = cellId;
                zoneManager.clearOutput(cellId);
                if (kernelWs) {
                    kernelWs.send({
                        type: 'execute',
                        content_hash: historicalHash,
                        code: historicalSource,
                    });
                }
            },
        });
    }

    // ─────────── per-cell affordances (Sprint 66) ───────────
    //
    // Walks the current model, mounts a toolbar content widget +
    // below-cell inserter view zone for every live cell, and disposes
    // any that no longer exist.  Idempotent — callers invoke after
    // every content change (rescanDecorations, markdown-zone rebuild).

    function rebuildCellAffordances() {
        const editor = refs.get('editor');
        const model = refs.get('model');
        const monaco = window.monaco;
        if (!editor || !model || !monaco) return;
        // Sprint 96: derive the cell list from :func:`splitCells` so
        // we pick up its content-hash computation + legacy-marker
        // tolerance without duplicating the regex walk here.  The
        // marker line is re-located by scanning the raw text for the
        // ordinal-th ``# %%`` line (cell-parser matches either
        // grammar) so the toolbar content widget pins to the right
        // row even on legacy notebooks mid-migration.
        const text = model.getValue();
        const parsedCells = splitCells(text);
        const lines = text.split('\n');
        const markerLineNumbers = [];
        for (let i = 0; i < lines.length; i++) {
            if (/^#\s*%%/.test(lines[i])) markerLineNumbers.push(i + 1);
        }
        const cellList = parsedCells.map((c, i) => ({
            id: c.id,
            content_hash: c.content_hash,
            typeId: c.cell_type,
            markerLine: markerLineNumbers[i] || 1,
            endLine: markerLineNumbers[i + 1]
                ? markerLineNumbers[i + 1] - 1
                : lines.length,
        }));

        // Rebuild the content-hash ↔ cell-id indices atomically so
        // any frame arriving mid-rescan resolves against a consistent
        // snapshot.
        for (const key of Object.keys(contentHashByCellId)) delete contentHashByCellId[key];
        for (const key of Object.keys(cellIdByContentHash)) delete cellIdByContentHash[key];
        for (const cell of cellList) {
            contentHashByCellId[cell.id] = cell.content_hash;
            cellIdByContentHash[cell.content_hash] = cell.id;
        }

        const alive = new Set(cellList.map((c) => c.id));
        for (const cellId of Object.keys(cellAffordances)) {
            if (!alive.has(cellId)) {
                removeAffordances(editor, cellAffordances[cellId]);
                delete cellAffordances[cellId];
            }
        }
        // Sprint 98 BUG-98-05: output zones are keyed on the transient
        // cell-id label, which renumbers on every source edit.  Prune
        // zones whose label is no longer in the live set so a
        // ``setValue`` / insert / delete does not leave ghost outputs
        // glued to dead labels.
        zoneManager.pruneOrphanOutputZones(alive);

        const handlers = {
            onRun: (cellId) => {
                const alpine = reactiveRoot;
                if (!alpine) return;
                alpine.runCellById(cellId);
            },
            onInsert: (cellId, typeId) => {
                const alpine = reactiveRoot;
                if (!alpine) return;
                alpine.insertCellAfter(cellId, typeId);
            },
            // Sprint 69: pin a markdown cell into source view.
            onTogglePin: (cellId) => {
                const pinned = zoneManager.toggleMarkdownPin(cellId);
                if (pinned === null) return;
                const record = cellAffordances[cellId];
                if (record) setPinState(record, pinned);
                zoneManager.updateHiddenAreas();
            },
            // Sprint 71: persist the result_var input back into the
            // marker line via a Monaco edit op so on-disk state stays
            // the source of truth.  Pass ``null`` to drop the segment.
            onResultVarChange: (cellId, name) => {
                cellEditor.applyResultVarToMarker(cellId, name);
            },
            // Sprint 73: per-cell run-history popover.
            onShowHistory: (cellId, anchorEl) => {
                openHistoryPopover(cellId, anchorEl);
            },
        };

        for (const cell of cellList) {
            let record = cellAffordances[cell.id];
            if (!record) {
                record = mountAffordances(
                    editor,
                    cell.id,
                    cell.typeId,
                    cell.markerLine,
                    handlers,
                    cell.typeId === 'sql' ? introspectCellResultVarById(model, cell.id) : null,
                );
                cellAffordances[cell.id] = record;
                if (cell.typeId === 'markdown') {
                    const z = zoneManager.getMarkdownZone(cell.id);
                    if (z && z.editModePinned) setPinState(record, true);
                }
            } else {
                moveToolbar(editor, record, cell.markerLine);
            }
            const afterLine = cell.endLine;
            if (!record.inserterZone) {
                record.inserterZone = mountInserter(
                    editor,
                    cell.id,
                    afterLine,
                    handlers,
                );
            } else {
                moveInserter(editor, record.inserterZone, afterLine);
            }
        }
    }
}
