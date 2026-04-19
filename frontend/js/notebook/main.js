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
// BUG-64-02 boundary discipline (Sprint-64; see closure_state.js):
// Monaco model / editor refs live in `refs` (createClosureRefs), not
// on the returned object.  Other private state (timers, WebSocket
// handles, DOM-node maps, accumulator buffers, parsed-cell cache)
// also lives in closure-scoped `let` vars to keep the reactive
// surface small and predictable.  The returned object carries
// primitive UI state + bound methods only.  Sprint 68 adds
// ``tabRefs`` and ``tabFactories`` to the grep-gate; a shell that
// aggregates per-tab closure bags onto its Alpine-reactive ``this._``
// would reproduce BUG-64-02 at N× scale.

import {
    joinCells,
    splitCells,
    CELL_MARKER_RE,
    NAMESPACE_INTROSPECT_CODE,
} from './cell_parser.js';
import { getCellType, parseMarkerTag } from './cell_types.js';
import {
    mountAffordances,
    mountInserter,
    moveToolbar,
    moveInserter,
    removeAffordances,
    setStatus,
    setExecutionCount,
    setPinState,
    startElapsed,
    stopElapsed,
    resetElapsed,
} from './cell_affordances.js';
import { renderMarkdown } from './markdown.js';
import { loadMonaco } from './monaco_loader.js';
import {
    PyrightClient,
    bindPyrightModel,
    lspSeverityToMonaco,
    registerPyrightProvidersOnce,
} from './pyright_client.js';
import { appendOutputFrame } from './output_renderer.js';
import { createClosureRefs } from './closure_state.js';
import { buildOutline } from './outline.js';

function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

// Databricks-style debounce: save 1500 ms after the user stops typing.
// Explicit Save button still works as a force-flush.
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
    // Sprint 68: initial bundle may be null on lazy-loaded tabs; cells
    // are populated inside mount() once the bundle resolves.
    let cells = [];
    // Sprint 70: outline entries derived from ``cells`` + a 150ms
    // debounce timer for onDidChangeContent-triggered recomputes.
    // Both MUST live in closure scope — the reactivity-boundary gate
    // blocks ``this._outlineEntries`` / ``this._outlineTimer`` because
    // a setTimeout handle parked on Alpine's proxy would let the
    // reactive walk recurse into the timer's captured closure.
    let outlineEntries = [];
    let outlineTimer = null;
    let saveTimerHandle = null;
    let saveInFlight = false;
    let saveQueued = false;
    let ws = null;
    let lspWs = null;
    let lspClient = null;
    let lspDocUri = null;
    let lspDocVersion = 0;
    let namespaceBuffer = '';
    let catalogTables = null;
    const outputZones = {};   // cellId → { zoneId, domNode }
    const markdownZones = {}; // cellId → { zoneId, domNode, sourceRange }
    // Sprint 66: per-cell affordances (toolbar content widget +
    // below-cell inserter view zone).  Closure-scoped so Monaco
    // content-widget + DOM refs never reach Alpine's reactive proxy
    // — same BUG-64-02 discipline as outputZones / markdownZones.
    const cellAffordances = {}; // cellId → record (see cell_affordances.js)
    // Sprint 66: captured at mount() so closure-scoped callbacks
    // (per-cell run button, inserter) can re-enter the Alpine object
    // without being bound at construction time.  Never assigned to
    // ``this.X`` — the reactivity-boundary gate forbids it.
    let reactiveRoot = null;
    let initialOutputs = [];
    let mounted = false;

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
        // ``outlineEntries`` list.  Assigned a fresh array
        // (``outlineEntries.slice()``) on every recompute so Alpine's
        // x-for diffs once per real change; a getter would produce a
        // fresh array on every reactive tick and thrash DOM.  Mirrors
        // how ``variables`` is reassigned on each introspect reply.
        outline: [],
        outlineVisible: false,
        catalogInsertOpen: false,
        catalogInsertQuery: '',
        // True once openCatalogInsert() has populated the closure-
        // local catalogTables list — drives the modal's "Loading…"
        // / "No tables found" placeholder switch without exposing
        // the (non-reactive) array itself to Alpine.
        catalogTablesLoaded: false,
        // Sprint 68: flipped true after the first ``mount()`` resolves.
        // The shell reads it to decide whether a freshly-activated
        // tab still needs lazy-loading; the per-tab template's
        // ``x-init`` calls ``mount()`` only while this is false.
        mounted: false,

        async mount() {
            if (mounted) return; // Sprint 68: lazy-mount is fire-once.
            mounted = true;
            this.mounted = true;
            reactiveRoot = this;
            // Sprint 68: tell the shell "this tab is now mounted" so
            // the shell's tab.mounted flag flips to true *before*
            // any async work (Monaco/kernel/LSP bootstrapping).  That
            // flag is what keeps the x-if wrapper evaluating true
            // when the user switches to a different tab — without
            // this event, Alpine's tab.mounted lookup would miss the
            // stub→real scope swap and the pane would unmount on
            // first tab-switch-away, losing Monaco + kernel state.
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
                cells = (bundle.cells || []).slice();
                recomputeOutline();
                initialOutputs = bundle.outputs || [];
                this.dirty = bundle.dirty === true;
                this.saveState = this.dirty ? 'pending' : 'saved';
                emitStateChange({ dirty: this.dirty, saveState: this.saveState });
                const monaco = await loadMonaco();
                const joined = joinCells(cells);
                const model = monaco.editor.createModel(joined.text, 'python');
                refs.set('model', model);
                const editor = monaco.editor.create(this.$refs.editor, {
                    model,
                    theme: 'vs-dark',
                    automaticLayout: true,
                    minimap: { enabled: false },
                    fontSize: 13,
                    scrollBeyondLastLine: false,
                });
                refs.set('editor', editor);
                applyDecorations(monaco, joined.cellRanges);
                model.onDidChangeContent(() => {
                    this.dirty = true;
                    this.saveState = 'pending';
                    emitStateChange({ dirty: true, saveState: 'pending' });
                    scheduleAutosave(() => this.save());
                });
                // Shift+Enter / Ctrl+Enter bind to the editor instance
                // — they only fire when Monaco has focus, which keeps
                // the toolbar and Alpine inputs safe to use normal
                // Enter semantics.
                editor.addCommand(
                    monaco.KeyMod.Shift | monaco.KeyCode.Enter,
                    () => this.runCurrentCell(),
                );
                editor.addCommand(
                    monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter,
                    () => this.runCurrentCell(),
                );
                registerPaletteActions(monaco, editor, this);
                // Foreign-notebook load path: UUIDs were minted server-
                // side, flush them to disk so the user doesn't see a
                // stale "unsaved" badge on first visit.
                if (this.dirty) {
                    saveTimerHandle = window.setTimeout(
                        () => this.save(),
                        INITIAL_FLUSH_MS,
                    );
                }
                replayPersistedOutputs();
                rebuildCellAffordances();
                rebuildMarkdownZones();
                updateHiddenAreas();
                editor.onDidChangeCursorPosition(() => updateHiddenAreas());
                model.onDidChangeContent(() => {
                    rebuildCellAffordances();
                    rebuildMarkdownZones();
                    updateHiddenAreas();
                    notifyLspDidChange();
                    recomputeOutlineDebounced();
                });
                registerPyrightProvidersOnce(monaco);
                openKernelWS(this);
                openLSP(monaco, this).catch((err) =>
                    console.error('[notebook-editor] lsp open failed', err));
                // Sprint 68: the shell's close-confirm "Save &
                // close" path fires this event; each tab scope
                // filters by its own tabId so exactly one factory
                // handles each request.  The shell awaits the
                // next ``pql:tab-state-changed`` emission from
                // ``save()`` to know the outcome.
                if (tabId) {
                    document.addEventListener('pql:save-tab', (ev) => {
                        const detail = ev && ev.detail;
                        if (!detail || detail.tabId !== tabId) return;
                        this.save();
                    });
                }
            } catch (err) {
                console.error('[notebook-editor] mount failed', err);
                if (window.pqlToast) {
                    window.pqlToast.error('Editor failed to load: ' + err.message);
                }
            }
        },

        clearCurrentCellOutputs() {
            const cell = currentCellAtCursor();
            if (!cell) return;
            clearOutput(cell.id);
            sendKernelFrame({ type: 'clear_cell', cell_id: cell.id });
        },

        runCurrentCell() {
            const cell = currentCellAtCursor();
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
            const typeId = cellType || cellTypeOf(cellId);
            if (!getCellType(typeId).canExecute) return;
            const source = cellSourceById(cellId);
            clearOutput(cellId);
            this.executingCells = { ...this.executingCells, [cellId]: true };
            if (typeId === 'sql') {
                sendKernelFrame({
                    type: 'execute_sql',
                    cell_id: cellId,
                    source,
                    result_var: cellResultVarById(cellId),
                });
            } else {
                sendKernelFrame({ type: 'execute', cell_id: cellId, code: source });
            }
        },

        interruptKernel() {
            sendKernelFrame({ type: 'interrupt' });
        },

        restartKernel() {
            this.kernelStatus = 'restarting';
            sendKernelFrame({ type: 'restart' });
        },

        runAllCells() {
            const allCells = splitCells(refs.get('model').getValue());
            for (const c of allCells) {
                if (!getCellType(c.cell_type).canExecute) continue;
                clearOutput(c.id);
                this.executingCells = { ...this.executingCells, [c.id]: true };
                sendCellFrame(c);
            }
        },

        runCellsAbove() {
            const cell = currentCellAtCursor();
            if (!cell) return;
            const allCells = splitCells(refs.get('model').getValue());
            for (const c of allCells) {
                if (c.id === cell.id) break;
                if (!getCellType(c.cell_type).canExecute) continue;
                clearOutput(c.id);
                this.executingCells = { ...this.executingCells, [c.id]: true };
                sendCellFrame(c);
            }
        },

        // Sprint 66: ``+ Code`` / ``+ Markdown`` inserter between
        // cells.  Synthesises a fresh marker with the registry's
        // ``markerTag`` and executes a Monaco edit just after the
        // anchor cell's last body line.  UUID minting mirrors
        // ``addCellBelow`` / ``addCellAbove``.
        insertCellAfter(afterCellId, typeId) {
            const model = refs.get('model');
            const editor = refs.get('editor');
            const monaco = window.monaco;
            if (!model || !editor || !monaco) return;
            const descriptor = getCellType(typeId);
            const newId = (window.crypto && window.crypto.randomUUID)
                ? window.crypto.randomUUID()
                : 'cell-' + Date.now();
            const marker = `\n# %%${descriptor.markerTag} pql_cell_id="${newId}"\n\n`;
            const endLine = cellEndLine(afterCellId);
            const anchorLine = endLine === null ? model.getLineCount() : endLine;
            const anchorCol = model.getLineMaxColumn(anchorLine);
            editor.executeEdits('pql-insert-after', [{
                range: new monaco.Range(anchorLine, anchorCol, anchorLine, anchorCol),
                text: marker,
                forceMoveMarkers: true,
            }]);
            rescanDecorations();
            editor.focus();
        },

        addCellBelow() {
            const model = refs.get('model');
            const editor = refs.get('editor');
            if (!model || !editor) return;
            const newId = (window.crypto && window.crypto.randomUUID)
                ? window.crypto.randomUUID()
                : 'cell-' + Date.now();
            const marker = `\n\n# %%${getCellType('code').markerTag} pql_cell_id="${newId}"\n`;
            const lastLine = model.getLineCount();
            const lastCol = model.getLineMaxColumn(lastLine);
            editor.executeEdits('add-cell', [{
                range: new window.monaco.Range(lastLine, lastCol, lastLine, lastCol),
                text: marker,
                forceMoveMarkers: true,
            }]);
            rescanDecorations();
        },

        addCellAbove(markdown) {
            const cell = currentCellAtCursor();
            const monaco = window.monaco;
            const editor = refs.get('editor');
            const newId = (window.crypto && window.crypto.randomUUID)
                ? window.crypto.randomUUID() : 'cell-' + Date.now();
            const tag = markdown ? getCellType('markdown').markerTag : getCellType('code').markerTag;
            const marker = `# %%${tag} pql_cell_id="${newId}"\n\n`;
            const targetLine = cell ? findCellMarkerLine(cell.id) : 1;
            const insertAt = new monaco.Range(targetLine, 1, targetLine, 1);
            editor.executeEdits('add-cell-above', [{
                range: insertAt, text: marker, forceMoveMarkers: true,
            }]);
            editor.setPosition({ lineNumber: targetLine + 1, column: 1 });
            rescanDecorations();
        },

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

        // Sprint 70: outline-row click handler.  Reuses
        // ``findCellMarkerLine`` to locate the cell's marker line and
        // jumps Monaco to the first content line (marker + 1), mirrors
        // the ``addCellAbove`` navigation pattern and adds
        // ``revealLineInCenter`` for smooth viewport scrolling.
        jumpToCell(cellId) {
            const editor = refs.get('editor');
            if (!editor) return;
            const contentLine = findCellMarkerLine(cellId) + 1;
            editor.setPosition({ lineNumber: contentLine, column: 1 });
            editor.revealLineInCenter(contentLine);
            editor.focus();
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
            if (!ws || this.kernelStatus !== 'ready') return;
            namespaceBuffer = '';
            sendKernelFrame({
                type: 'execute',
                cell_id: '__pql_namespace__',
                code: NAMESPACE_INTROSPECT_CODE,
            });
        },

        async save() {
            const model = refs.get('model');
            if (!model) return;
            if (saveTimerHandle) {
                window.clearTimeout(saveTimerHandle);
                saveTimerHandle = null;
            }
            if (saveInFlight) {
                saveQueued = true;
                return;
            }
            saveInFlight = true;
            this.loading = true;
            this.saveState = 'saving';
            try {
                const newCells = splitCells(model.getValue());
                const resp = await fetch('/api/notebook/doc', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken(),
                    },
                    body: JSON.stringify({ path: this.path, cells: newCells }),
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
                if (window.pqlToast) window.pqlToast.error('Save failed: ' + err.message);
            } finally {
                this.loading = false;
                saveInFlight = false;
                if (saveQueued) {
                    saveQueued = false;
                    scheduleAutosave(() => this.save());
                }
            }
        },
    });

    // ─────────────────── closure-scoped helpers ───────────────────
    //
    // Defined after the return object so the orchestrator's outer
    // shape reads top-down.  Each helper closes over `refs` plus the
    // closure-scoped state above; none touches `this`.

    function scheduleAutosave(callback) {
        if (saveTimerHandle) window.clearTimeout(saveTimerHandle);
        saveTimerHandle = window.setTimeout(callback, AUTOSAVE_DEBOUNCE_MS);
    }

    // Sprint 70: recompute the outline and mirror it onto the reactive
    // root as a fresh array.  Re-splits from the live Monaco model
    // rather than reading the closure-local ``cells`` because ``cells``
    // is only refreshed on save / ``rescanDecorations`` — NOT on every
    // content change.  Replay-caught: without a re-split, the outline
    // lags behind typing until the next autosave.  A 150ms debounce
    // (NOT the 1500ms autosave cadence) keeps the TOC feeling
    // responsive without running the regex on every keystroke.  The
    // ``reactiveRoot`` guard is defensive — mount() captures ``this``
    // before content changes can fire.  See outline.js for the
    // extractor's BUG-69-01 rationale.
    function recomputeOutline() {
        const model = refs.get('model');
        const liveCells = model ? splitCells(model.getValue()) : cells;
        outlineEntries = buildOutline(liveCells);
        if (reactiveRoot) {
            reactiveRoot.outline = outlineEntries.slice();
        }
    }

    function recomputeOutlineDebounced() {
        if (outlineTimer) window.clearTimeout(outlineTimer);
        outlineTimer = window.setTimeout(() => {
            outlineTimer = null;
            recomputeOutline();
        }, 150);
    }

    function applyDecorations(monaco, ranges) {
        const editor = refs.get('editor');
        if (!editor) return;
        const decos = ranges.map((r) => ({
            range: new monaco.Range(r.startLine, 1, r.endLine, 1),
            options: {
                isWholeLine: true,
                className: getCellType(r.cellType).bandClass,
            },
        }));
        decorationIds = editor.deltaDecorations(decorationIds, decos);
    }

    function rescanDecorations() {
        const model = refs.get('model');
        const newCells = splitCells(model.getValue());
        const ranges = [];
        const lines = model.getValue().split('\n');
        let currentStart = null;
        let currentType = 'code';
        for (let i = 0; i < lines.length; i++) {
            const m = lines[i].match(CELL_MARKER_RE);
            if (m) {
                if (currentStart !== null) {
                    ranges.push({ startLine: currentStart, endLine: i, cellType: currentType });
                }
                currentType = parseMarkerTag(m[1]);
                currentStart = i + 2;
            }
        }
        if (currentStart !== null) {
            ranges.push({ startLine: currentStart, endLine: lines.length, cellType: currentType });
        }
        applyDecorations(window.monaco, ranges);
        cells = newCells;
        rebuildCellAffordances();
        recomputeOutline();
    }

    function currentCellAtCursor() {
        const editor = refs.get('editor');
        const model = refs.get('model');
        if (!editor || !model) return null;
        const pos = editor.getPosition();
        if (!pos) return null;
        const above = model.getValueInRange({
            startLineNumber: 1, startColumn: 1,
            endLineNumber: pos.lineNumber, endColumn: model.getLineMaxColumn(pos.lineNumber),
        }).split('\n');
        for (let i = above.length - 1; i >= 0; i--) {
            const m = above[i].match(CELL_MARKER_RE);
            if (m) return { id: m[2], cellType: parseMarkerTag(m[1]) };
        }
        return null;
    }

    function cellTypeOf(cellId) {
        const model = refs.get('model');
        if (!model) return 'code';
        const lines = model.getValue().split('\n');
        for (const line of lines) {
            const m = line.match(CELL_MARKER_RE);
            if (m && m[2] === cellId) return parseMarkerTag(m[1]);
        }
        return 'code';
    }

    function cellSourceById(cellId) {
        const lines = refs.get('model').getValue().split('\n');
        const out = [];
        let collecting = false;
        for (const line of lines) {
            const m = line.match(CELL_MARKER_RE);
            if (m) {
                if (m[2] === cellId) { collecting = true; continue; }
                if (collecting) break;
            } else if (collecting) {
                out.push(line);
            }
        }
        return out.join('\n');
    }

    // Sprint 71: read the ``result_var`` segment from the marker line
    // for SQL cells.  Returns ``null`` for any cell type other than
    // SQL or for SQL cells with no segment / an invalid identifier.
    function cellResultVarById(cellId) {
        const model = refs.get('model');
        if (!model) return null;
        const lines = model.getValue().split('\n');
        for (const line of lines) {
            const m = line.match(CELL_MARKER_RE);
            if (m && m[2] === cellId) {
                if (parseMarkerTag(m[1]) !== 'sql') return null;
                return m[3] || null;
            }
        }
        return null;
    }

    // Sprint 71: send the matching frame for a parsed cell.  Single
    // place that knows about the SQL → ``execute_sql`` branch so the
    // run-all / run-above paths stay symmetric with ``runCellById``.
    function sendCellFrame(cell) {
        if (cell.cell_type === 'sql') {
            sendKernelFrame({
                type: 'execute_sql',
                cell_id: cell.id,
                source: cell.source,
                result_var: cell.resultVar || null,
            });
        } else {
            sendKernelFrame({ type: 'execute', cell_id: cell.id, code: cell.source });
        }
    }

    function cellEndLine(cellId) {
        const lines = refs.get('model').getValue().split('\n');
        let start = null;
        for (let i = 0; i < lines.length; i++) {
            const m = lines[i].match(CELL_MARKER_RE);
            if (m) {
                if (start !== null) return i;
                if (m[2] === cellId) start = i + 1;
            }
        }
        return start !== null ? lines.length : null;
    }

    function findCellMarkerLine(cellId) {
        const lines = refs.get('model').getValue().split('\n');
        for (let i = 0; i < lines.length; i++) {
            const m = lines[i].match(CELL_MARKER_RE);
            if (m && m[2] === cellId) return i + 1;
        }
        return 1;
    }

    // Sprint 71: rewrite a SQL cell's marker line in place to add /
    // update / drop the ``result_var="<name>"`` segment.  Mirrors the
    // ``joinCells`` rule so a save → reload round-trip is byte-stable
    // with what the parser would produce.  No-op if the cell is not a
    // SQL cell or the marker is missing.
    function applyResultVarToMarker(cellId, name) {
        const editor = refs.get('editor');
        const model = refs.get('model');
        const monaco = window.monaco;
        if (!editor || !model || !monaco) return;
        const lineNumber = findCellMarkerLine(cellId);
        const lineText = model.getLineContent(lineNumber);
        const m = lineText.match(CELL_MARKER_RE);
        if (!m || parseMarkerTag(m[1]) !== 'sql') return;
        const tag = ' [sql]';
        let newLine = `# %%${tag} pql_cell_id="${cellId}"`;
        if (name) newLine += ` result_var="${name}"`;
        if (newLine === lineText) return;
        const range = new monaco.Range(
            lineNumber, 1, lineNumber, model.getLineMaxColumn(lineNumber),
        );
        editor.executeEdits('result-var-edit', [{ range, text: newLine, forceMoveMarkers: true }]);
    }

    function ensureOutputZone(cellId, afterLineNumber) {
        const editor = refs.get('editor');
        let zone = outputZones[cellId];
        if (zone) {
            // Re-anchor if the cell's end line has shifted.
            editor.changeViewZones((accessor) => {
                accessor.removeZone(zone.zoneId);
                zone.zoneId = accessor.addZone({
                    afterLineNumber,
                    heightInPx: Math.max(zone.domNode.offsetHeight, 24),
                    domNode: zone.domNode,
                });
            });
            return zone.domNode;
        }
        const dom = document.createElement('div');
        dom.className = 'pql-nbedit-output';
        let zoneId = null;
        editor.changeViewZones((accessor) => {
            zoneId = accessor.addZone({
                afterLineNumber,
                heightInPx: 24,
                domNode: dom,
            });
        });
        outputZones[cellId] = { zoneId, domNode: dom };
        return dom;
    }

    function layoutOutputZone(cellId) {
        const zone = outputZones[cellId];
        if (!zone) return;
        refs.get('editor').changeViewZones((accessor) => {
            accessor.layoutZone(zone.zoneId);
        });
    }

    function clearOutput(cellId) {
        const zone = outputZones[cellId];
        if (!zone) return;
        zone.domNode.innerHTML = '';
        layoutOutputZone(cellId);
    }

    function clearAllOutputs() {
        for (const cellId of Object.keys(outputZones)) {
            clearOutput(cellId);
        }
    }

    function appendOutput(cellId, msgType, content) {
        const endLine = cellEndLine(cellId);
        if (endLine === null) return;
        const dom = ensureOutputZone(cellId, endLine);
        appendOutputFrame(dom, msgType, content);
        layoutOutputZone(cellId);
    }

    function replayPersistedOutputs() {
        if (!initialOutputs || initialOutputs.length === 0) return;
        // Pick the latest kernel_session_id we see in the replay.
        // If the current live WS session differs (hello arrives later)
        // we still paint the most recent persisted snapshot — the
        // first live execute will clear and re-emit.
        let latestSession = null;
        for (const row of initialOutputs) {
            if (!latestSession || row.kernel_session_id > latestSession) {
                latestSession = row.kernel_session_id;
            }
        }
        for (const row of initialOutputs) {
            if (row.kernel_session_id !== latestSession) continue;
            appendOutput(row.cell_id, row.msg_type, row.content);
        }
    }

    // ─────────── per-cell affordances (Sprint 66) ───────────
    //
    // Walks the current model, mounts a toolbar content widget +
    // below-cell inserter view zone for every live cell, and
    // disposes any that no longer exist.  Idempotent — callers
    // invoke after every content change (rescanDecorations,
    // markdown-zone rebuild).

    function rebuildCellAffordances() {
        const editor = refs.get('editor');
        const model = refs.get('model');
        const monaco = window.monaco;
        if (!editor || !model || !monaco) return;
        const lines = model.getValue().split('\n');
        const cellList = [];
        let current = null;
        for (let i = 0; i < lines.length; i++) {
            const m = lines[i].match(CELL_MARKER_RE);
            if (m) {
                if (current) {
                    current.endLine = i;
                    cellList.push(current);
                }
                current = {
                    id: m[2],
                    typeId: parseMarkerTag(m[1]),
                    markerLine: i + 1,
                    endLine: lines.length,
                };
            }
        }
        if (current) cellList.push(current);

        const alive = new Set(cellList.map((c) => c.id));
        for (const cellId of Object.keys(cellAffordances)) {
            if (!alive.has(cellId)) {
                removeAffordances(editor, cellAffordances[cellId]);
                delete cellAffordances[cellId];
            }
        }

        const handlers = {
            onRun: (cellId) => {
                // Reuse the same execution seam the toolbar uses — the
                // returned object is the Alpine reactive root; grab
                // it off the Monaco DOM parent so the closure does
                // not need a bound ``this``.
                const alpine = reactiveRoot;
                if (!alpine) return;
                alpine.runCellById(cellId);
            },
            onInsert: (cellId, typeId) => {
                const alpine = reactiveRoot;
                if (!alpine) return;
                alpine.insertCellAfter(cellId, typeId);
            },
            // Sprint 69: pin a markdown cell into source view.  The
            // flag lives on markdownZones[cellId] so it survives
            // rebuilds within the session but not page reload.
            onTogglePin: (cellId) => {
                const zone = markdownZones[cellId];
                if (!zone) return;
                zone.editModePinned = !zone.editModePinned;
                const record = cellAffordances[cellId];
                if (record) setPinState(record, zone.editModePinned);
                updateHiddenAreas();
            },
            // Sprint 71: persist the result_var input back into the
            // marker line via a Monaco edit op so on-disk state stays
            // the source of truth (no parallel JS-side cell metadata
            // store).  Pass ``null`` to drop the segment.
            onResultVarChange: (cellId, name) => {
                applyResultVarToMarker(cellId, name);
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
                    cell.typeId === 'sql' ? cellResultVarById(cell.id) : null,
                );
                cellAffordances[cell.id] = record;
                // Sprint 69: a freshly mounted markdown toolbar must
                // mirror any pin flag already on the zone (e.g. after
                // a content edit triggered a full rebuild).
                if (cell.typeId === 'markdown') {
                    const z = markdownZones[cell.id];
                    if (z && z.editModePinned) setPinState(record, true);
                }
            } else {
                moveToolbar(editor, record, cell.markerLine);
            }
            // Inserter sits right after the cell's last body line —
            // endLine is the line index (0-based) of the next marker
            // or the final line count.
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

    // ─────────── markdown preview zones + hidden-areas ───────────

    function rebuildMarkdownZones() {
        const editor = refs.get('editor');
        const model = refs.get('model');
        if (!editor || !model) return;
        const lines = model.getValue().split('\n');
        const cellList = [];
        let current = null;
        for (let i = 0; i < lines.length; i++) {
            const m = lines[i].match(CELL_MARKER_RE);
            if (m) {
                if (current) {
                    current.endLine = i;
                    cellList.push(current);
                }
                current = parseMarkerTag(m[1]) === 'markdown'
                    ? { id: m[2], markerLine: i + 1, sourceStart: i + 2, endLine: lines.length }
                    : null;
            }
        }
        if (current) cellList.push(current);

        const alive = new Set(cellList.map((c) => c.id));
        for (const cellId of Object.keys(markdownZones)) {
            if (!alive.has(cellId)) {
                const z = markdownZones[cellId];
                editor.changeViewZones((acc) => acc.removeZone(z.zoneId));
                delete markdownZones[cellId];
            }
        }

        for (const cell of cellList) {
            // Strip jupytext's leading "# " from each markdown body
            // line so the rendered markdown matches how the user sees
            // it in .ipynb tools.
            const body = cell.sourceStart <= cell.endLine
                ? lines.slice(cell.sourceStart - 1, cell.endLine)
                      .map((l) => l.replace(/^#\s?/, ''))
                      .join('\n')
                : '';
            let zone = markdownZones[cell.id];
            if (!zone) {
                const dom = document.createElement('div');
                dom.className = 'pql-nbedit-md-preview';
                dom.addEventListener('click', () => focusMarkdownSource(cell.id));
                let zoneId = null;
                editor.changeViewZones((acc) => {
                    zoneId = acc.addZone({
                        afterLineNumber: cell.markerLine,
                        heightInPx: 40,
                        domNode: dom,
                    });
                });
                zone = { zoneId, domNode: dom, editModePinned: false };
                markdownZones[cell.id] = zone;
            } else {
                editor.changeViewZones((acc) => {
                    acc.removeZone(zone.zoneId);
                    zone.zoneId = acc.addZone({
                        afterLineNumber: cell.markerLine,
                        heightInPx: Math.max(zone.domNode.offsetHeight, 40),
                        domNode: zone.domNode,
                    });
                });
            }
            zone.sourceRange = { startLine: cell.sourceStart, endLine: cell.endLine };
            zone.domNode.innerHTML = renderMarkdown(body)
                || '<em class="text-muted">Empty markdown cell — click to edit.</em>';
            editor.changeViewZones((acc) => acc.layoutZone(zone.zoneId));
        }
    }

    function focusMarkdownSource(cellId) {
        const zone = markdownZones[cellId];
        if (!zone || !zone.sourceRange) return;
        const editor = refs.get('editor');
        editor.setPosition({
            lineNumber: zone.sourceRange.startLine,
            column: 1,
        });
        editor.focus();
        // setPosition fires onDidChangeCursorPosition which in turn
        // re-computes hidden areas, so the click-to-edit unhide is
        // automatic.
    }

    function updateHiddenAreas() {
        const editor = refs.get('editor');
        if (!editor) return;
        const pos = editor.getPosition();
        const cursorLine = pos ? pos.lineNumber : 1;
        const hidden = [];
        for (const cellId of Object.keys(markdownZones)) {
            const z = markdownZones[cellId];
            if (!z.sourceRange) continue;
            // Sprint 69: a pinned cell stays unhidden regardless of
            // cursor position — the user explicitly clicked the
            // pencil to keep its source visible while typing
            // elsewhere.
            if (z.editModePinned) continue;
            const { startLine, endLine } = z.sourceRange;
            if (cursorLine < startLine || cursorLine > endLine) {
                hidden.push({
                    startLineNumber: startLine,
                    endLineNumber: endLine,
                    startColumn: 1,
                    endColumn: 1,
                });
            }
        }
        // setHiddenAreas hides the ranges purely at the view layer —
        // the model (and therefore getValue() + save) stays intact.
        editor.setHiddenAreas(hidden);
    }

    // ─────────────────── kernel WebSocket ───────────────────

    function openKernelWS(alpine) {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${proto}://${location.host}/ws/notebook/kernel`
            + `?path=${encodeURIComponent(alpine.path)}`;
        alpine.kernelStatus = 'connecting';
        try {
            ws = new WebSocket(url);
        } catch (err) {
            console.error('[notebook-editor] ws open failed', err);
            alpine.kernelStatus = 'error';
            return;
        }
        ws.addEventListener('message', (ev) => {
            let frame;
            try { frame = JSON.parse(ev.data); } catch { return; }
            handleKernelFrame(alpine, frame);
        });
        ws.addEventListener('close', (ev) => {
            alpine.kernelStatus = 'disconnected';
            if (ev.code === 4401 && window.pqlToast) {
                window.pqlToast.error('Kernel auth expired — reload.');
            }
        });
        ws.addEventListener('error', () => {
            alpine.kernelStatus = 'error';
        });
    }

    function handleKernelFrame(alpine, frame) {
        switch (frame.type) {
            case 'hello':
                alpine.kernelStatus = 'ready';
                alpine.kernelSessionId = frame.kernel_session_id;
                break;
            case 'ack':
                break;
            case 'interrupted':
                if (window.pqlToast) window.pqlToast.info('Kernel interrupted');
                break;
            case 'restarted':
                alpine.kernelSessionId = frame.kernel_session_id;
                clearAllOutputs();
                alpine.executingCells = {};
                alpine.kernelStatus = 'ready';
                // Sprint 66: kernel was reset — counters and elapsed
                // pills from the previous session are stale.
                for (const cellId of Object.keys(cellAffordances)) {
                    const rec = cellAffordances[cellId];
                    setStatus(rec, 'idle');
                    setExecutionCount(rec, null);
                    resetElapsed(rec);
                }
                if (window.pqlToast) window.pqlToast.success('Kernel restarted');
                break;
            case 'error':
                if (window.pqlToast) window.pqlToast.error(frame.message || 'kernel error');
                break;
            case 'kernel_msg':
                renderKernelMsg(alpine, frame);
                break;
        }
    }

    function sendKernelFrame(obj) {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            if (window.pqlToast) window.pqlToast.error('Kernel not connected');
            return false;
        }
        ws.send(JSON.stringify(obj));
        return true;
    }

    function renderKernelMsg(alpine, frame) {
        // Sprint 62: route ``__pql_`` cell_ids to the internal-
        // introspect handler instead of the output renderer +
        // persistence path.
        if (frame.cell_id && frame.cell_id.startsWith('__pql_')) {
            if (frame.cell_id === '__pql_namespace__') {
                handleNamespaceFrame(alpine, frame);
            }
            return;
        }
        // `status` isn't tied to a cell when it's the generic
        // idle/busy beat — but the parent msg_id (if present) lets
        // the server annotate which execute it maps to.
        if (frame.msg_type === 'status') {
            if (frame.cell_id) {
                const record = cellAffordances[frame.cell_id];
                if (frame.content.execution_state === 'idle') {
                    const next = { ...alpine.executingCells };
                    delete next[frame.cell_id];
                    alpine.executingCells = next;
                    // Sprint 66: stop the live elapsed tick but leave
                    // the final status pill flip to the forthcoming
                    // ``execute_reply`` — ok/error/aborted are only
                    // known from the shell-channel reply.
                    if (record) stopElapsed(record);
                    // Namespace has likely changed — refresh the
                    // Variable Explorer only when the user panel is
                    // open, so inactive tabs don't pay for the
                    // introspect.
                    if (alpine.variablesVisible) {
                        window.setTimeout(() => alpine._refreshVariables(), 50);
                    }
                } else if (frame.content.execution_state === 'busy') {
                    alpine.executingCells = {
                        ...alpine.executingCells, [frame.cell_id]: true,
                    };
                    if (record) {
                        setStatus(record, 'running');
                        setExecutionCount(record, '*');
                        startElapsed(record);
                    }
                }
            }
            return;
        }
        if (!frame.cell_id) return;
        // Sprint 66: ``execute_input`` carries the kernel's monotonic
        // counter; surface it in the per-cell pill so users see
        // ``[*]`` → ``[7]`` like every other notebook UI.  No output
        // zone side-effect (the submitted code is already visible in
        // Monaco).
        if (frame.msg_type === 'execute_input') {
            const record = cellAffordances[frame.cell_id];
            if (record && frame.content && frame.content.execution_count != null) {
                setExecutionCount(record, frame.content.execution_count);
            }
            return;
        }
        // Sprint 66: ``execute_reply`` is the final verdict — shell-
        // channel reply with status ``ok`` / ``error`` / ``aborted``.
        // Jupyter surfaces ``Interrupt`` as ``status='error'`` with
        // ``ename='KeyboardInterrupt'`` (the cell's execute raised),
        // not as ``status='aborted'`` (which is reserved for
        // skipped-due-to-prior-error).  Remap KeyboardInterrupt to
        // ``cancelled`` so the red error pill doesn't mislabel an
        // intentional stop.
        // Sprint 72: ipywidgets minimal placeholder.  ``comm_open`` /
        // ``comm_msg`` / ``comm_close`` carry the bidirectional
        // widget-state protocol; until a future sprint vendors a real
        // widget-manager, we silently swallow them so the default
        // ``appendOutput`` branch does not paint protocol noise into
        // the cell's output zone.  The user-visible affordance is the
        // placeholder card the renderer paints when ``display_data``
        // carries ``application/vnd.jupyter.widget-view+json``.  No
        // ``console`` log — a single ``IntSlider()`` instantiation
        // emits dozens of comm frames and would flood DevTools.
        if (frame.msg_type === 'comm_open'
                || frame.msg_type === 'comm_msg'
                || frame.msg_type === 'comm_close') {
            return;
        }
        if (frame.msg_type === 'execute_reply') {
            const record = cellAffordances[frame.cell_id];
            if (record) {
                stopElapsed(record);
                const content = frame.content || {};
                const replyStatus = content.status;
                if (replyStatus === 'ok') {
                    setStatus(record, 'ok');
                } else if (replyStatus === 'aborted') {
                    setStatus(record, 'cancelled');
                } else if (replyStatus === 'error') {
                    if (content.ename === 'KeyboardInterrupt') {
                        setStatus(record, 'cancelled');
                    } else {
                        setStatus(record, 'error');
                    }
                } else {
                    setStatus(record, 'idle');
                }
            }
            return;
        }
        appendOutput(frame.cell_id, frame.msg_type, frame.content);
    }

    function handleNamespaceFrame(alpine, frame) {
        if (frame.msg_type === 'stream'
                && frame.content && frame.content.name === 'stdout') {
            namespaceBuffer += frame.content.text || '';
            return;
        }
        if (frame.msg_type === 'status'
                && frame.content && frame.content.execution_state === 'idle') {
            try {
                const parsed = JSON.parse(namespaceBuffer);
                if (parsed && typeof parsed === 'object') {
                    alpine.variables = parsed;
                }
            } catch {}
            namespaceBuffer = '';
        }
    }

    // ─────────────────── LSP / pyright wiring ───────────────────

    async function openLSP(monaco, alpine) {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${proto}://${location.host}/ws/notebook/lsp`
            + `?path=${encodeURIComponent(alpine.path)}`;
        alpine.lspStatus = 'connecting';
        try {
            lspWs = new WebSocket(url);
        } catch (err) {
            console.error('[notebook-editor] lsp ws failed', err);
            alpine.lspStatus = 'error';
            return;
        }
        lspClient = new PyrightClient(lspWs);
        lspWs.addEventListener('message', (ev) => {
            try { lspClient._onMessage(JSON.parse(ev.data)); } catch {}
        });
        lspWs.addEventListener('close', (ev) => {
            if (ev.code === 4404) {
                alpine.lspStatus = 'unavailable';
            } else {
                alpine.lspStatus = 'error';
            }
        });
        lspWs.addEventListener('error', () => {
            alpine.lspStatus = 'error';
        });
        await new Promise((resolve, reject) => {
            const onOpen = () => { resolve(); };
            const onErr = () => reject(new Error('ws errored before open'));
            lspWs.addEventListener('open', onOpen, { once: true });
            lspWs.addEventListener('error', onErr, { once: true });
        });

        // Initialise pyright.  rootUri is null because we don't know
        // the absolute path on the client; pyright runs single-file
        // checking off the file-URI we hand it on didOpen.
        lspDocUri = `file:///notebook/${alpine.path}`;
        lspDocVersion = 1;
        try {
            await lspClient.request('initialize', {
                processId: null,
                clientInfo: { name: 'pointlessql-editor', version: '0.1' },
                rootUri: null,
                capabilities: {
                    textDocument: {
                        synchronization: { didSave: false, dynamicRegistration: false },
                        completion: {
                            completionItem: {
                                snippetSupport: false,
                                documentationFormat: ['markdown', 'plaintext'],
                            },
                        },
                        hover: { contentFormat: ['markdown', 'plaintext'] },
                        signatureHelp: {
                            signatureInformation: {
                                documentationFormat: ['markdown', 'plaintext'],
                            },
                        },
                        definition: { linkSupport: false },
                        publishDiagnostics: { relatedInformation: false },
                    },
                },
            });
        } catch (e) {
            console.error('[notebook-editor] lsp initialize failed', e);
            alpine.lspStatus = 'error';
            return;
        }
        lspClient.notify('initialized', {});
        const model = refs.get('model');
        lspClient.notify('textDocument/didOpen', {
            textDocument: {
                uri: lspDocUri,
                languageId: 'python',
                version: lspDocVersion,
                text: model.getValue(),
            },
        });
        bindPyrightModel(model, lspClient, lspDocUri);
        lspClient.on('textDocument/publishDiagnostics', (params) => {
            if (params.uri !== lspDocUri) return;
            const markers = (params.diagnostics || []).map((d) => ({
                startLineNumber: d.range.start.line + 1,
                startColumn: d.range.start.character + 1,
                endLineNumber: d.range.end.line + 1,
                endColumn: d.range.end.character + 1,
                severity: lspSeverityToMonaco(d.severity || 1, monaco),
                message: d.message,
                source: d.source || 'pyright',
                code: typeof d.code === 'object' ? d.code.value : d.code,
            }));
            monaco.editor.setModelMarkers(model, 'pyright', markers);
        });
        alpine.lspStatus = 'ready';
    }

    function notifyLspDidChange() {
        if (!lspClient || !lspDocUri) return;
        lspDocVersion++;
        // Full-document sync — cheap enough for notebooks, avoids the
        // range-based diff tracking we'd need for incremental sync.
        lspClient.notify('textDocument/didChange', {
            textDocument: {
                uri: lspDocUri,
                version: lspDocVersion,
            },
            contentChanges: [{ text: refs.get('model').getValue() }],
        });
    }

    // ─────────────── command palette registrations ───────────────

    function registerPaletteActions(monaco, editor, alpine) {
        // Monaco's built-in command palette opens on F1 / Ctrl+Shift+P;
        // addAction registrations show up there automatically, and
        // each action can bind its own keybindings if we want one.
        const add = (id, label, run, keybindings) =>
            editor.addAction({
                id: `pql.${id}`,
                label,
                keybindings: keybindings || [],
                contextMenuGroupId: 'pql',
                run: () => run(),
            });
        add('runAll', 'PointlesSQL: Run all cells', () => alpine.runAllCells());
        add('runAbove', 'PointlesSQL: Run all cells above cursor', () => alpine.runCellsAbove());
        add('clearOutputs', 'PointlesSQL: Clear outputs of current cell', () =>
            alpine.clearCurrentCellOutputs());
        add('restartKernel', 'PointlesSQL: Restart kernel', () => alpine.restartKernel());
        add('insertBelow', 'PointlesSQL: Insert cell below', () => alpine.addCellBelow());
        add('insertAbove', 'PointlesSQL: Insert cell above', () => alpine.addCellAbove());
        add('insertMarkdown', 'PointlesSQL: Insert markdown cell below', () =>
            alpine.addCellAbove(true));
        add('insertFromCatalog', 'PointlesSQL: Insert from catalog…', () =>
            alpine.openCatalogInsert(),
            [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyI]);
        add('toggleVariables', 'PointlesSQL: Toggle variable explorer', () =>
            alpine.toggleVariables());
    }
}
