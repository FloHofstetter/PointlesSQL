// Phase 12.6 Sprint 58 — Monaco-based notebook editor (skeleton).
//
// ADR 0001 locks the architecture: single Monaco instance over the
// whole .py file, cell boundaries rendered via Monaco decorations,
// cell identities carried as UUIDs in jupytext `# %% id=<uuid>`
// markers. This file is the client half; the server half lives in
// pointlessql/services/notebook_doc.py.
//
// Out of scope for Sprint 58 and deferred to later sprints:
//   - cell execution (Sprint 59, ZMQ kernel over WebSocket)
//   - output rendering (Sprint 60, persisted in SQLite)
//   - Pyright LSP (Sprint 61)
//   - Variable explorer + catalog insert (Sprint 62)
//
// Loader pattern mirrors the Monaco AMD bundle: base.html loads
// `vs/loader.js` synchronously, we then configure `require.paths.vs`
// against our vendored copy and call `require(['vs/editor/editor.main'])`
// before Alpine's `mount()` starts touching Monaco APIs.
(function () {
    const MONACO_BASE = '/static/js/vendor/monaco/vs';
    let monacoReady = null;

    function loadMonaco() {
        if (monacoReady) return monacoReady;
        monacoReady = new Promise((resolve, reject) => {
            try {
                // Monaco's loader publishes `require`/`define` as globals.
                // The RequireJS-style config below pins the base URL so
                // every sub-module (language workers, themes) resolves
                // under our vendored tree.
                if (typeof require !== 'function' || !require.config) {
                    reject(new Error('monaco loader not present — check vendor script'));
                    return;
                }
                require.config({ paths: { vs: MONACO_BASE } });
                require(['vs/editor/editor.main'], () => {
                    if (typeof monaco === 'undefined') {
                        reject(new Error('monaco module loaded but global missing'));
                        return;
                    }
                    resolve(monaco);
                });
            } catch (err) {
                reject(err);
            }
        });
        return monacoReady;
    }

    // Serialise `cells[]` into a single buffer with `# %% id=<uuid>`
    // markers on marker lines. Keeps cell source unchanged. Returns
    // `{ text, cellRanges }` where cellRanges[i] = {startLine, endLine}
    // (1-based inclusive) for the i-th cell's *source* region — the
    // marker itself is excluded so decorations colour only content.
    function joinCells(cells) {
        const lines = [];
        const ranges = [];
        for (let i = 0; i < cells.length; i++) {
            const cell = cells[i];
            const markerTag = cell.cell_type === 'markdown' ? ' [markdown]' : '';
            const marker = `# %%${markerTag} pql_cell_id="${cell.id}"`;
            if (i > 0) lines.push('');
            lines.push(marker);
            const bodyStart = lines.length + 1; // 1-based
            const src = cell.source.length > 0 ? cell.source.split('\n') : [''];
            for (const line of src) lines.push(line);
            const bodyEnd = lines.length;
            ranges.push({ startLine: bodyStart, endLine: bodyEnd, cellType: cell.cell_type });
        }
        return { text: lines.join('\n'), cellRanges: ranges };
    }

    // Reparse the current buffer into `cells[]` using the same
    // marker grammar the server honours. We keep the client parser
    // intentionally narrow: only the canonical `# %% id=<uuid>`
    // form we wrote out is recognised. Foreign marker variants are
    // a server-side concern (jupytext handles them on load).
    function splitCells(text) {
        const lines = text.split('\n');
        const cells = [];
        let currentId = null;
        let currentType = 'code';
        let buffer = [];
        const flush = () => {
            if (currentId === null) return;
            // Strip a single trailing blank line introduced between cells
            // by the `joinCells` emitter so round-trips are byte-stable.
            if (buffer.length > 0 && buffer[buffer.length - 1] === '') {
                buffer.pop();
            }
            cells.push({ id: currentId, cell_type: currentType, source: buffer.join('\n') });
        };
        const markerRe = /^#\s*%%(\s+\[markdown\])?\s+pql_cell_id="([0-9a-fA-F-]{36})"\s*$/;
        for (const line of lines) {
            const m = line.match(markerRe);
            if (m) {
                flush();
                currentId = m[2];
                currentType = m[1] ? 'markdown' : 'code';
                buffer = [];
            } else if (currentId !== null) {
                buffer.push(line);
            }
            // Lines before the first marker are discarded — jupytext
            // treats them as file-level frontmatter, which the
            // skeleton does not yet let the user edit.
        }
        flush();
        return cells;
    }

    function csrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.content : '';
    }

    // Databricks-style debounce: save 1500 ms after the user stops
    // typing. Explicit Save button still works as a force-flush.
    const AUTOSAVE_DEBOUNCE_MS = 1500;
    // Brief delay on initial load before auto-flushing the
    // UUID-upgrade save for a foreign notebook. Keeps the user-
    // visible "Saving…" tag from flashing during the render.
    const INITIAL_FLUSH_MS = 400;

    window.notebookEditor = function notebookEditor({ path, initial }) {
        return {
            path,
            dirty: initial.dirty === true,
            loading: false,
            // "idle" | "pending" | "saving" | "saved" | "error"
            saveState: initial.dirty === true ? 'pending' : 'saved',
            _editor: null,
            _model: null,
            _decorationIds: [],
            _cells: initial.cells.slice(),
            _saveTimer: null,
            _saveInFlight: false,
            _saveQueued: false,

            async mount() {
                try {
                    const monaco = await loadMonaco();
                    const joined = joinCells(this._cells);
                    this._model = monaco.editor.createModel(joined.text, 'python');
                    this._editor = monaco.editor.create(this.$refs.editor, {
                        model: this._model,
                        theme: 'vs-dark',
                        automaticLayout: true,
                        minimap: { enabled: false },
                        fontSize: 13,
                        scrollBeyondLastLine: false,
                    });
                    this._applyDecorations(joined.cellRanges);
                    this._model.onDidChangeContent(() => {
                        this.dirty = true;
                        this.saveState = 'pending';
                        this._scheduleAutosave();
                    });
                    // Foreign-notebook load path: UUIDs were minted
                    // server-side, flush them to disk so the user
                    // doesn't see a stale "unsaved" badge on first
                    // visit.
                    if (this.dirty) {
                        this._saveTimer = window.setTimeout(
                            () => this.save(),
                            INITIAL_FLUSH_MS,
                        );
                    }
                } catch (err) {
                    console.error('[notebook-editor] mount failed', err);
                    if (window.pqlToast) {
                        window.pqlToast.error('Editor failed to load: ' + err.message);
                    }
                }
            },

            _scheduleAutosave() {
                if (this._saveTimer) window.clearTimeout(this._saveTimer);
                this._saveTimer = window.setTimeout(
                    () => this.save(),
                    AUTOSAVE_DEBOUNCE_MS,
                );
            },

            _applyDecorations(ranges) {
                if (!this._editor) return;
                const monaco = window.monaco;
                const decos = ranges.map((r) => ({
                    range: new monaco.Range(r.startLine, 1, r.endLine, 1),
                    options: {
                        isWholeLine: true,
                        className: r.cellType === 'markdown'
                            ? 'pql-nbedit-cell-band-markdown'
                            : 'pql-nbedit-cell-band-code',
                    },
                }));
                this._decorationIds = this._editor.deltaDecorations(this._decorationIds, decos);
            },

            addCellBelow() {
                if (!this._model) return;
                const newId = (window.crypto && window.crypto.randomUUID)
                    ? window.crypto.randomUUID()
                    : 'cell-' + Date.now();
                const marker = `\n\n# %% pql_cell_id="${newId}"\n`;
                const lastLine = this._model.getLineCount();
                const lastCol = this._model.getLineMaxColumn(lastLine);
                this._editor.executeEdits('add-cell', [{
                    range: new window.monaco.Range(lastLine, lastCol, lastLine, lastCol),
                    text: marker,
                    forceMoveMarkers: true,
                }]);
                this._rescanDecorations();
            },

            _rescanDecorations() {
                const cells = splitCells(this._model.getValue());
                // Recompute ranges from the live buffer — marker
                // positions have moved since mount().
                const ranges = [];
                const lines = this._model.getValue().split('\n');
                const markerRe = /^#\s*%%(\s+\[markdown\])?\s+pql_cell_id="([0-9a-fA-F-]{36})"\s*$/;
                let currentStart = null;
                let currentType = 'code';
                for (let i = 0; i < lines.length; i++) {
                    const m = lines[i].match(markerRe);
                    if (m) {
                        if (currentStart !== null) {
                            ranges.push({ startLine: currentStart, endLine: i, cellType: currentType });
                        }
                        currentType = m[1] ? 'markdown' : 'code';
                        currentStart = i + 2; // 1-based, skip marker
                    }
                }
                if (currentStart !== null) {
                    ranges.push({ startLine: currentStart, endLine: lines.length, cellType: currentType });
                }
                this._applyDecorations(ranges);
                this._cells = cells;
            },

            async save() {
                if (!this._model) return;
                if (this._saveTimer) {
                    window.clearTimeout(this._saveTimer);
                    this._saveTimer = null;
                }
                // Serialise concurrent saves — autosave + a manual
                // click during flight must not race on the same
                // file. If a save is already running, mark that the
                // buffer has moved on so we re-fire once the in-
                // flight save completes.
                if (this._saveInFlight) {
                    this._saveQueued = true;
                    return;
                }
                this._saveInFlight = true;
                this.loading = true;
                this.saveState = 'saving';
                try {
                    const cells = splitCells(this._model.getValue());
                    const resp = await fetch('/api/notebook/doc', {
                        method: 'POST',
                        headers: {
                            'Content-Type': 'application/json',
                            'X-CSRF-Token': csrfToken(),
                        },
                        body: JSON.stringify({ path: this.path, cells }),
                    });
                    if (!resp.ok) {
                        const text = await resp.text();
                        throw new Error(text || `save failed (${resp.status})`);
                    }
                    this._cells = cells;
                    this.dirty = false;
                    this.saveState = 'saved';
                } catch (err) {
                    console.error('[notebook-editor] save failed', err);
                    this.saveState = 'error';
                    if (window.pqlToast) window.pqlToast.error('Save failed: ' + err.message);
                } finally {
                    this.loading = false;
                    this._saveInFlight = false;
                    if (this._saveQueued) {
                        this._saveQueued = false;
                        // Flush whatever was typed during the last save.
                        this._scheduleAutosave();
                    }
                }
            },
        };
    };
})();
