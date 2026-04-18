// Phase 12.6 Sprint 58 + 59 + 60 — Monaco-based notebook editor.
//
// ADR 0001 locks the architecture: single Monaco instance over the
// whole .py file, cell boundaries rendered via Monaco decorations,
// cell identities carried as UUIDs in jupytext markers of the form
// `# %% pql_cell_id="<uuid>"`. This file is the client half; the
// server halves live in pointlessql/services/notebook_doc.py (save/
// load), pointlessql/services/kernel_session.py (WS ↔ ZMQ), and
// pointlessql/services/notebook_outputs.py (output persistence).
//
// Sprint 58: load, render, autosave.
// Sprint 59: WebSocket to the per-notebook ipykernel, Shift+Enter /
//            Ctrl+Enter to execute the cell at the cursor, text /
//            stream / error outputs rendered ephemerally in a
//            Monaco view zone beneath the cell; Interrupt + Restart
//            toolbar actions.
// Sprint 60: output persistence (load-on-mount, append-per-iopub,
//            clear-on-reexecute / clear-on-restart, Alembic 017),
//            rich mimes (text/html, image/png, image/svg+xml,
//            application/json, ANSI-traceback → HTML), Markdown
//            cells rendered when not being edited.
//
// Out of scope for Sprint 60 and deferred:
//   - Pyright LSP + dual-source autocomplete → Sprint 61
//   - Variable explorer + "insert from catalog" → Sprint 62
//   - ipywidgets (interactive widgets) → Phase 12.7 (explicit
//     split per the Phase-12.6 memory decision)
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

    const CELL_MARKER_RE = /^#\s*%%(\s+\[markdown\])?\s+pql_cell_id="([0-9a-fA-F-]{36})"\s*$/;

    // ANSI → HTML span conversion for tracebacks.  Jupyter error
    // messages carry SGR colour codes straight out of IPython's
    // ``ultratb`` formatter; we translate the common foreground
    // colours, bold, and reset so the traceback reads as intended.
    // Anything we don't handle falls through as a stripped span.
    const ANSI_ESCAPE_RE = /\x1B\[([0-9;]*)m/g;
    const ANSI_FG = {
        30: '#6c757d', 31: '#e85050', 32: '#30c030', 33: '#d0a030',
        34: '#4080ff', 35: '#c050c0', 36: '#30c0c0', 37: '#d0d0d0',
        90: '#a0a0a0', 91: '#ff7070', 92: '#50e050', 93: '#ffd050',
        94: '#6090ff', 95: '#e070e0', 96: '#50d0d0', 97: '#ffffff',
    };

    function escapeHtml(s) {
        return (s || '').replace(/[&<>"']/g, (c) => ({
            '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
        })[c]);
    }

    function ansiToHtml(text) {
        // Walk the string, closing/opening `<span>`s as SGR codes
        // appear.  Keeps the implementation dependency-free and
        // round-trips multi-line tracebacks faithfully.
        let html = '';
        let openSpans = 0;
        let lastIndex = 0;
        text = text || '';
        let m;
        ANSI_ESCAPE_RE.lastIndex = 0;
        while ((m = ANSI_ESCAPE_RE.exec(text)) !== null) {
            html += escapeHtml(text.slice(lastIndex, m.index));
            lastIndex = ANSI_ESCAPE_RE.lastIndex;
            const codes = m[1] ? m[1].split(';').map(Number) : [0];
            for (const code of codes) {
                if (code === 0) {
                    while (openSpans > 0) { html += '</span>'; openSpans--; }
                } else if (code === 1) {
                    html += '<span style="font-weight:bold">';
                    openSpans++;
                } else if (ANSI_FG[code]) {
                    html += `<span style="color:${ANSI_FG[code]}">`;
                    openSpans++;
                }
            }
        }
        html += escapeHtml(text.slice(lastIndex));
        while (openSpans > 0) { html += '</span>'; openSpans--; }
        return html;
    }

    window.notebookEditor = function notebookEditor({ path, initial }) {
        return {
            path,
            dirty: initial.dirty === true,
            loading: false,
            // "idle" | "pending" | "saving" | "saved" | "error"
            saveState: initial.dirty === true ? 'pending' : 'saved',
            // "connecting" | "ready" | "restarting" | "disconnected" | "error"
            kernelStatus: 'connecting',
            kernelSessionId: null,
            executingCells: {},  // cellId → true while kernel is busy for that cell
            _editor: null,
            _model: null,
            _decorationIds: [],
            _cells: initial.cells.slice(),
            _saveTimer: null,
            _saveInFlight: false,
            _saveQueued: false,
            _ws: null,
            _wsReconnectTimer: null,
            _outputZones: {},  // cellId → { zoneId, domNode }
            _markdownZones: {},  // cellId → { zoneId, domNode, editing }
            // Per-cell output-index counter for replay on mount.
            // Sprint 60: we reuse this when persisted outputs are
            // rehydrated into view zones so later kernel messages
            // append below them.
            _initialOutputs: initial.outputs || [],

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
                    // Shift+Enter / Ctrl+Enter bind to the editor
                    // instance — they only fire when Monaco has focus,
                    // which keeps the toolbar and Alpine inputs safe
                    // to use normal Enter semantics.
                    this._editor.addCommand(
                        monaco.KeyMod.Shift | monaco.KeyCode.Enter,
                        () => this.runCurrentCell(),
                    );
                    this._editor.addCommand(
                        monaco.KeyMod.CtrlCmd | monaco.KeyCode.Enter,
                        () => this.runCurrentCell(),
                    );
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
                    this._replayPersistedOutputs();
                    this._openKernelWS();
                } catch (err) {
                    console.error('[notebook-editor] mount failed', err);
                    if (window.pqlToast) {
                        window.pqlToast.error('Editor failed to load: ' + err.message);
                    }
                }
            },

            // Client-side nuke: sends a clear_cell frame for the
            // current cell so both the local view zone *and* the
            // persisted rows go away.  Toolbar "Clear outputs" button.
            clearCurrentCellOutputs() {
                const cell = this._currentCellAtCursor();
                if (!cell) return;
                this._clearOutput(cell.id);
                this._sendKernelFrame({ type: 'clear_cell', cell_id: cell.id });
            },

            // ────────────────────────── kernel / WS ──────────────────────────

            _openKernelWS() {
                const proto = location.protocol === 'https:' ? 'wss' : 'ws';
                const url = `${proto}://${location.host}/ws/notebook/kernel`
                    + `?path=${encodeURIComponent(this.path)}`;
                this.kernelStatus = 'connecting';
                try {
                    this._ws = new WebSocket(url);
                } catch (err) {
                    console.error('[notebook-editor] ws open failed', err);
                    this.kernelStatus = 'error';
                    return;
                }
                this._ws.addEventListener('message', (ev) => {
                    let frame;
                    try { frame = JSON.parse(ev.data); } catch { return; }
                    this._handleKernelFrame(frame);
                });
                this._ws.addEventListener('close', (ev) => {
                    this.kernelStatus = 'disconnected';
                    if (ev.code === 4401 && window.pqlToast) {
                        window.pqlToast.error('Kernel auth expired — reload.');
                    }
                });
                this._ws.addEventListener('error', () => {
                    this.kernelStatus = 'error';
                });
            },

            _handleKernelFrame(frame) {
                switch (frame.type) {
                    case 'hello':
                        this.kernelStatus = 'ready';
                        this.kernelSessionId = frame.kernel_session_id;
                        break;
                    case 'ack':
                        // execute_request was accepted — nothing visual
                        break;
                    case 'interrupted':
                        if (window.pqlToast) window.pqlToast.info('Kernel interrupted');
                        break;
                    case 'restarted':
                        this.kernelSessionId = frame.kernel_session_id;
                        this._clearAllOutputs();
                        this.executingCells = {};
                        this.kernelStatus = 'ready';
                        if (window.pqlToast) window.pqlToast.success('Kernel restarted');
                        break;
                    case 'error':
                        if (window.pqlToast) window.pqlToast.error(frame.message || 'kernel error');
                        break;
                    case 'kernel_msg':
                        this._renderKernelMsg(frame);
                        break;
                }
            },

            _sendKernelFrame(obj) {
                if (!this._ws || this._ws.readyState !== WebSocket.OPEN) {
                    if (window.pqlToast) window.pqlToast.error('Kernel not connected');
                    return false;
                }
                this._ws.send(JSON.stringify(obj));
                return true;
            },

            runCurrentCell() {
                const cell = this._currentCellAtCursor();
                if (!cell) return;
                if (cell.cellType === 'markdown') return;  // Sprint 60 renders markdown
                const source = this._cellSourceById(cell.id);
                this._clearOutput(cell.id);
                this.executingCells = { ...this.executingCells, [cell.id]: true };
                this._sendKernelFrame({ type: 'execute', cell_id: cell.id, code: source });
            },

            interruptKernel() {
                this._sendKernelFrame({ type: 'interrupt' });
            },

            restartKernel() {
                this.kernelStatus = 'restarting';
                this._sendKernelFrame({ type: 'restart' });
            },

            _currentCellAtCursor() {
                if (!this._editor || !this._model) return null;
                const pos = this._editor.getPosition();
                if (!pos) return null;
                const above = this._model.getValueInRange({
                    startLineNumber: 1, startColumn: 1,
                    endLineNumber: pos.lineNumber, endColumn: this._model.getLineMaxColumn(pos.lineNumber),
                }).split('\n');
                for (let i = above.length - 1; i >= 0; i--) {
                    const m = above[i].match(CELL_MARKER_RE);
                    if (m) return { id: m[2], cellType: m[1] ? 'markdown' : 'code' };
                }
                return null;
            },

            _cellSourceById(cellId) {
                const lines = this._model.getValue().split('\n');
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
            },

            _cellEndLine(cellId) {
                const lines = this._model.getValue().split('\n');
                let start = null;
                for (let i = 0; i < lines.length; i++) {
                    const m = lines[i].match(CELL_MARKER_RE);
                    if (m) {
                        if (start !== null) return i;  // 1-based line of the NEXT marker − 1 = this cell's end (0-based i is already that)
                        if (m[2] === cellId) start = i + 1;
                    }
                }
                return start !== null ? lines.length : null;
            },

            _ensureOutputZone(cellId, afterLineNumber) {
                let zone = this._outputZones[cellId];
                if (zone) {
                    // Re-anchor if the cell's end line has shifted.
                    this._editor.changeViewZones((accessor) => {
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
                this._editor.changeViewZones((accessor) => {
                    zoneId = accessor.addZone({
                        afterLineNumber,
                        heightInPx: 24,
                        domNode: dom,
                    });
                });
                this._outputZones[cellId] = { zoneId, domNode: dom };
                return dom;
            },

            _layoutOutputZone(cellId) {
                const zone = this._outputZones[cellId];
                if (!zone) return;
                this._editor.changeViewZones((accessor) => {
                    accessor.layoutZone(zone.zoneId);
                });
            },

            _clearOutput(cellId) {
                const zone = this._outputZones[cellId];
                if (!zone) return;
                zone.domNode.innerHTML = '';
                this._layoutOutputZone(cellId);
            },

            _clearAllOutputs() {
                for (const cellId of Object.keys(this._outputZones)) {
                    this._clearOutput(cellId);
                }
            },

            _renderKernelMsg(frame) {
                // `status` isn't tied to a cell when it's the generic
                // idle/busy beat — but the parent msg_id (if present)
                // lets the server annotate which execute it maps to.
                if (frame.msg_type === 'status') {
                    if (frame.cell_id) {
                        if (frame.content.execution_state === 'idle') {
                            const next = { ...this.executingCells };
                            delete next[frame.cell_id];
                            this.executingCells = next;
                        } else if (frame.content.execution_state === 'busy') {
                            this.executingCells = { ...this.executingCells, [frame.cell_id]: true };
                        }
                    }
                    return;
                }
                if (!frame.cell_id) return;
                this._appendOutput(frame.cell_id, frame.msg_type, frame.content);
            },

            // Shared path for both live kernel_msg frames and the
            // persisted replay that runs on mount.  ``msg_type`` and
            // ``content`` match Jupyter's wire shape; everything else
            // is inferred from the current Monaco buffer.
            _appendOutput(cellId, msgType, content) {
                const endLine = this._cellEndLine(cellId);
                if (endLine === null) return;
                const dom = this._ensureOutputZone(cellId, endLine);
                switch (msgType) {
                    case 'stream': {
                        const pre = document.createElement('pre');
                        pre.className = 'pql-nbedit-output-stream'
                            + (content.name === 'stderr' ? ' pql-nbedit-output-stderr' : '');
                        pre.textContent = content.text || '';
                        dom.appendChild(pre);
                        break;
                    }
                    case 'execute_result':
                    case 'display_data':
                        this._renderMimeBundle(dom, content.data || {}, content.metadata || {});
                        break;
                    case 'error': {
                        const block = document.createElement('pre');
                        block.className = 'pql-nbedit-output-error';
                        const rawTb = (content.traceback || []).join('\n');
                        if (rawTb) {
                            // ANSI → HTML so IPython's coloured
                            // ultratb reads as intended; fallback to
                            // ename/evalue when traceback is empty.
                            block.innerHTML = ansiToHtml(rawTb);
                        } else {
                            block.textContent = `${content.ename}: ${content.evalue}`;
                        }
                        dom.appendChild(block);
                        break;
                    }
                    case 'execute_input':
                        // Server echoes the submitted code — we already
                        // have the source in the editor buffer.
                        break;
                    default:
                        break;
                }
                this._layoutOutputZone(cellId);
            },

            // Render a Jupyter mime bundle (``{mime: data}``) by
            // picking the richest representation the client can
            // display.  Rich mimes (HTML, images, SVG, JSON) land
            // from Sprint 60; ``text/plain`` is the unconditional
            // fallback so a bundle without richer types still
            // renders.
            _renderMimeBundle(dom, data, /* metadata */ _m) {
                if (!data || typeof data !== 'object') return;
                // Priority: html > svg > png > jpeg > json > plain.
                // Matches what nbconvert does for the "lab" template,
                // which is what Sprint-26's papermill view uses.
                if (data['text/html']) {
                    const wrap = document.createElement('div');
                    wrap.className = 'pql-nbedit-output-html';
                    // The kernel is already trusted (it runs arbitrary
                    // user code as the editor user) — emitting raw
                    // HTML does not widen the attack surface.  Any
                    // future sandboxing would need a kernel-level
                    // sandbox, not a client-side sanitiser.
                    wrap.innerHTML = Array.isArray(data['text/html'])
                        ? data['text/html'].join('')
                        : data['text/html'];
                    dom.appendChild(wrap);
                    return;
                }
                if (data['image/svg+xml']) {
                    const wrap = document.createElement('div');
                    wrap.className = 'pql-nbedit-output-svg';
                    const svg = Array.isArray(data['image/svg+xml'])
                        ? data['image/svg+xml'].join('')
                        : data['image/svg+xml'];
                    wrap.innerHTML = svg;
                    dom.appendChild(wrap);
                    return;
                }
                if (data['image/png']) {
                    const img = document.createElement('img');
                    img.className = 'pql-nbedit-output-image';
                    img.src = `data:image/png;base64,${data['image/png']}`;
                    img.alt = 'output image';
                    dom.appendChild(img);
                    return;
                }
                if (data['image/jpeg']) {
                    const img = document.createElement('img');
                    img.className = 'pql-nbedit-output-image';
                    img.src = `data:image/jpeg;base64,${data['image/jpeg']}`;
                    img.alt = 'output image';
                    dom.appendChild(img);
                    return;
                }
                if (data['application/json']) {
                    const pre = document.createElement('pre');
                    pre.className = 'pql-nbedit-output-json';
                    pre.textContent = JSON.stringify(data['application/json'], null, 2);
                    dom.appendChild(pre);
                    return;
                }
                if (data['text/plain']) {
                    const pre = document.createElement('pre');
                    pre.className = 'pql-nbedit-output-result';
                    pre.textContent = Array.isArray(data['text/plain'])
                        ? data['text/plain'].join('')
                        : data['text/plain'];
                    dom.appendChild(pre);
                }
            },

            _replayPersistedOutputs() {
                if (!this._initialOutputs || this._initialOutputs.length === 0) return;
                // Pick the latest kernel_session_id we see in the
                // replay.  If the current live WS session differs
                // (hello frame arrives later) we still paint the
                // most recent persisted snapshot — the first
                // live execute will clear and re-emit.
                let latestSession = null;
                for (const row of this._initialOutputs) {
                    if (!latestSession || row.kernel_session_id > latestSession) {
                        latestSession = row.kernel_session_id;
                    }
                }
                for (const row of this._initialOutputs) {
                    if (row.kernel_session_id !== latestSession) continue;
                    this._appendOutput(row.cell_id, row.msg_type, row.content);
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
