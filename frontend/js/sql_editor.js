/**
 * Phase 12 SQL editor Alpine component.
 *
 * Sprint 75 Phase 4: native ES module shape; bootstrap.js re-attaches
 * the factory to ``window.sqlEditor`` so Alpine's x-data lookup keeps
 * working unchanged.  The previously module-level ``cmView`` and
 * ``catalogCompletions`` now live inside the factory closure — ESM
 * makes module-singleton state more dangerous on revisit (the original
 * ``host.dataset.pqlCmInit`` re-entry guard catches double-init within
 * one page life, but a fresh factory per call is cleaner).  CodeMirror
 * 6 is ESM-only; we still lazy-load it via dynamic ``import()`` inside
 * ``init()`` so non-/sql pages don't pay the 200 kB+ download.
 */

function flattenTree(tree) {
    const out = [];
    for (const cat of tree || []) {
        const catName = cat && cat.name;
        if (!catName) continue;
        for (const sch of cat.schemas || []) {
            const schName = sch && sch.name;
            if (!schName) continue;
            for (const tbl of sch.tables || []) {
                const tblName = tbl && tbl.name;
                if (!tblName) continue;
                out.push(`${catName}.${schName}.${tblName}`);
            }
        }
    }
    return out;
}

export function sqlEditor() {
    // Sprint 75: per-instance closure state.  Pre-Sprint-75 these were
    // module-level ``let`` vars; in ESM that means cross-mount carryover
    // on the same page.  Closure-scoping isolates each Alpine instance.
    let cmView = null;
    let catalogCompletions = [];

    return {
            running: false,
            result: null,
            error: null,
            errorTitle: 'Query failed',
            referencedTables: [],
            lastRun: null,

            // Saved queries (Sprint 51) state.
            saved: [],
            savedLoading: false,
            saving: false,
            saveForm: { title: '', description: '', is_shared: false },

            // Cancel + elapsed counter (Sprint 52).
            currentQueryId: null,
            elapsedSeconds: 0,
            _tickHandle: null,

            // EXPLAIN (Sprint 53).
            explainText: null,

            // Chart view (Sprint 54).  ``viewMode`` toggles between
            // ``'table'`` (default) and ``'chart'``.  ``chartConfig``
            // carries the user's current selections; the null starts
            // are guarded wherever x-text reads them (Phase-12 trap #4).
            viewMode: 'table',
            chartConfig: { type: 'bar', x: null, y: null },
            _chartInstance: null,
            // Id of the history row the current ``result`` corresponds
            // to.  Set by POST /api/sql/execute response (Sprint 54
            // extends that payload with ``history_id``) and by the
            // deep-link fetch below.  Required so the debounced PATCH
            // knows which row to update.
            currentHistoryId: null,
            _chartSaveTimer: null,

            // Lazy bootstrap so CodeMirror's ESM modules are
            // only fetched on the /sql page and we don't block
            // the rest of the app on a 200 kB+ download.
            async init() {
                const host = document.getElementById('pql-sql-editor-root');
                // Synchronous re-entry guard: Alpine walks the tree
                // twice in some init paths and both calls race
                // through the dynamic imports before ``cmView`` is
                // set, yielding two CodeMirror instances in the
                // same host.  Flag the host ourselves.
                if (!host || host.dataset.pqlCmInit === '1') return;
                host.dataset.pqlCmInit = '1';

                const [
                    stateMod, viewMod, commandsMod, languageMod,
                    sqlMod, themeMod, autocompleteMod,
                ] = await Promise.all([
                    import('@codemirror/state'),
                    import('@codemirror/view'),
                    import('@codemirror/commands'),
                    import('@codemirror/language'),
                    import('@codemirror/lang-sql'),
                    import('@codemirror/theme-one-dark'),
                    import('@codemirror/autocomplete'),
                ]);
                const { EditorState } = stateMod;
                const {
                    EditorView, keymap, highlightActiveLine, lineNumbers,
                } = viewMod;
                const { defaultKeymap, history, historyKeymap } = commandsMod;
                const {
                    syntaxHighlighting, defaultHighlightStyle, bracketMatching,
                } = languageMod;
                const { sql } = sqlMod;
                const { oneDark } = themeMod;
                const { autocompletion, completionKeymap } = autocompleteMod;

                const runShortcut = {
                    key: 'Mod-Enter',
                    run: () => { this.run(); return true; },
                    preventDefault: true,
                };
                const saveShortcut = {
                    key: 'Mod-s',
                    run: () => { this.openSaveModal(); return true; },
                    preventDefault: true,
                };

                // Honour ?prefill=<urlencoded sql> so the /queries
                // re-run button and future deep-links open with a
                // pre-filled query.  Clean the URL so a reload
                // isn't a second re-run.
                const qs = new URLSearchParams(window.location.search);
                const prefill = qs.get('prefill');
                const startingDoc =
                    prefill && prefill.trim() ? prefill : 'SELECT 1 AS n';
                if (prefill) {
                    try { history.replaceState({}, '', '/sql'); }
                    catch (e) { /* ignore */ }
                }

                function tableCompletionSource(context) {
                    if (!catalogCompletions.length) return null;
                    const word = context.matchBefore(/[\w.]*/);
                    if (!word || (word.from === word.to && !context.explicit)) {
                        return null;
                    }
                    return {
                        from: word.from,
                        options: catalogCompletions.map((full) => ({
                            label: full,
                            type: 'class',
                            boost: 1,
                        })),
                    };
                }

                cmView = new EditorView({
                    state: EditorState.create({
                        doc: startingDoc,
                        extensions: [
                            lineNumbers(),
                            highlightActiveLine(),
                            history(),
                            bracketMatching(),
                            syntaxHighlighting(defaultHighlightStyle),
                            sql(),
                            oneDark,
                            autocompletion({ override: [tableCompletionSource] }),
                            keymap.of([
                                runShortcut,
                                saveShortcut,
                                ...completionKeymap,
                                ...defaultKeymap,
                                ...historyKeymap,
                            ]),
                        ],
                    }),
                    parent: host,
                });
                this.refreshSaved();
                this.refreshCompletions();
                // Sprint 54: global ``c`` toggles table ↔ chart when the
                // focus isn't inside CodeMirror or a form control.
                this._onKeydown = this._onKeydown.bind(this);
                window.addEventListener('keydown', this._onKeydown);
                // Sprint 54: if the page was deep-linked with
                // ?history_id=<id> (from a /queries row re-run), fetch
                // the persisted chart config and seed the toolbar.
                const histId = qs.get('history_id');
                if (histId) {
                    const id = parseInt(histId, 10);
                    if (!Number.isNaN(id)) this.seedFromHistory(id);
                }
            },

            destroy() {
                if (this._onKeydown) {
                    window.removeEventListener('keydown', this._onKeydown);
                }
                this.destroyChart();
                if (this._chartSaveTimer) {
                    clearTimeout(this._chartSaveTimer);
                    this._chartSaveTimer = null;
                }
            },

            _onKeydown(ev) {
                if (ev.key !== 'c' || ev.ctrlKey || ev.metaKey || ev.altKey) {
                    return;
                }
                const active = document.activeElement;
                if (!active) { this.toggleView(); return; }
                const tag = (active.tagName || '').toLowerCase();
                if (tag === 'input' || tag === 'textarea' || tag === 'select') return;
                // CodeMirror's inner contenteditable host sits inside
                // #pql-sql-editor-root; leave typing alone when focus
                // is there.
                const host = document.getElementById('pql-sql-editor-root');
                if (host && host.contains(active)) return;
                ev.preventDefault();
                this.toggleView();
            },

            toggleView() {
                if (!this.result) return;
                this.viewMode = this.viewMode === 'chart' ? 'table' : 'chart';
                if (this.viewMode === 'chart') {
                    this._autoPickAxes();
                    this.$nextTick(() => this.renderChart());
                } else {
                    this.destroyChart();
                }
            },

            _autoPickAxes() {
                if (!this.result || !Array.isArray(this.result.columns)) return;
                if (this.chartConfig.x && this.chartConfig.y) return;
                const numericTypes = new Set([
                    'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT',
                    'DOUBLE', 'FLOAT', 'REAL', 'DECIMAL', 'NUMERIC',
                    'HUGEINT', 'UINTEGER', 'UBIGINT', 'USMALLINT', 'UTINYINT',
                ]);
                const cols = this.result.columns;
                const isNumeric = (c) => numericTypes.has((c.type || '').toUpperCase().split('(')[0]);
                let xIdx = null, yIdx = null;
                for (let i = 0; i < cols.length; i += 1) {
                    if (xIdx === null && !isNumeric(cols[i])) xIdx = i;
                    if (yIdx === null && isNumeric(cols[i])) yIdx = i;
                }
                if (xIdx === null) xIdx = 0;
                if (yIdx === null) yIdx = cols.length > 1 ? 1 : 0;
                if (!this.chartConfig.x) this.chartConfig.x = cols[xIdx].name;
                if (!this.chartConfig.y) this.chartConfig.y = cols[yIdx].name;
            },

            onChartConfigChange() {
                if (this.viewMode === 'chart') this.renderChart();
                this._scheduleChartSave();
            },

            _scheduleChartSave() {
                if (!this.currentHistoryId) return;
                if (this._chartSaveTimer) clearTimeout(this._chartSaveTimer);
                this._chartSaveTimer = setTimeout(() => {
                    this._chartSaveTimer = null;
                    this._persistChartConfig();
                }, 500);
            },

            async _persistChartConfig() {
                if (!this.currentHistoryId) return;
                const cfg = this._chartConfigPayload();
                await window.pqlApi.fetch(
                    `/api/queries/${this.currentHistoryId}/chart-config`,
                    { method: 'PATCH', body: { chart_config: cfg }, silent: true },
                );
            },

            _chartConfigPayload() {
                if (!this.chartConfig.x || !this.chartConfig.y) return null;
                return {
                    type: this.chartConfig.type || 'bar',
                    x: this.chartConfig.x,
                    y: this.chartConfig.y,
                };
            },

            destroyChart() {
                if (this._chartInstance) {
                    try { this._chartInstance.destroy(); }
                    catch (e) { /* Chart.js can throw if canvas is gone */ }
                    this._chartInstance = null;
                }
            },

            renderChart() {
                if (!this.result || !window.Chart) return;
                if (!this.chartConfig.x || !this.chartConfig.y) return;
                const canvas = document.getElementById('pql-sql-chart-canvas');
                if (!canvas) return;
                const cols = this.result.columns || [];
                const xIdx = cols.findIndex((c) => c.name === this.chartConfig.x);
                const yIdx = cols.findIndex((c) => c.name === this.chartConfig.y);
                if (xIdx < 0 || yIdx < 0) return;
                this.destroyChart();
                const rows = this.result.rows || [];
                const type = this.chartConfig.type || 'bar';
                let data;
                if (type === 'scatter') {
                    data = {
                        datasets: [{
                            label: `${this.chartConfig.y} vs ${this.chartConfig.x}`,
                            data: rows.map((r) => ({ x: Number(r[xIdx]), y: Number(r[yIdx]) })),
                        }],
                    };
                } else if (type === 'pie') {
                    const buckets = new Map();
                    for (const r of rows) {
                        const key = r[xIdx] === null || r[xIdx] === undefined
                            ? '(null)' : String(r[xIdx]);
                        const val = Number(r[yIdx]);
                        buckets.set(key, (buckets.get(key) || 0) + (Number.isFinite(val) ? val : 0));
                    }
                    data = {
                        labels: [...buckets.keys()],
                        datasets: [{ label: this.chartConfig.y, data: [...buckets.values()] }],
                    };
                } else {
                    data = {
                        labels: rows.map((r) => String(r[xIdx] ?? '')),
                        datasets: [{
                            label: this.chartConfig.y,
                            data: rows.map((r) => Number(r[yIdx])),
                        }],
                    };
                }
                const chartType = type === 'scatter' ? 'scatter'
                    : type === 'pie' ? 'pie'
                    : type === 'line' ? 'line'
                    : 'bar';
                this._chartInstance = new window.Chart(canvas, {
                    type: chartType,
                    data,
                    options: {
                        responsive: true,
                        maintainAspectRatio: false,
                        animation: false,
                        plugins: {
                            legend: { display: chartType === 'pie' || chartType === 'scatter' },
                        },
                    },
                });
            },

            downloadChartPng() {
                const canvas = document.getElementById('pql-sql-chart-canvas');
                if (!canvas || !this._chartInstance) return;
                canvas.toBlob((blob) => {
                    if (!blob) return;
                    const url = URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = url;
                    const stamp = new Date()
                        .toISOString().replace(/[-:T]/g, '').slice(0, 15);
                    a.download = `pointlessql-chart-${stamp}.png`;
                    document.body.appendChild(a);
                    a.click();
                    a.remove();
                    setTimeout(() => URL.revokeObjectURL(url), 1000);
                });
            },

            async seedFromHistory(historyId) {
                const res = await window.pqlApi.fetch(
                    `/api/queries/${historyId}`, { silent: true },
                );
                if (!res.ok || !res.data) return;
                this.currentHistoryId = historyId;
                if (res.data.chart_config) {
                    try {
                        const parsed = typeof res.data.chart_config === 'string'
                            ? JSON.parse(res.data.chart_config)
                            : res.data.chart_config;
                        if (parsed && typeof parsed === 'object') {
                            this.chartConfig = {
                                type: parsed.type || 'bar',
                                x: parsed.x || null,
                                y: parsed.y || null,
                            };
                        }
                    } catch (e) { /* malformed — ignore */ }
                }
            },

            async refreshCompletions() {
                // /api/tree already exists for the sidebar; we reuse
                // it as the autocomplete source.  Non-admin callers
                // see only catalogs they have USE on, which is the
                // correct scope for autocomplete anyway — you should
                // not see tables you can't query.
                const res = await window.pqlApi.fetch('/api/tree', { silent: true });
                if (res.ok && Array.isArray(res.data)) {
                    catalogCompletions = flattenTree(res.data);
                }
            },

            // -- Saved queries (Sprint 51) --

            async refreshSaved() {
                this.savedLoading = true;
                const res = await window.pqlApi.fetch('/api/saved-queries', { silent: true });
                this.savedLoading = false;
                this.saved = res.ok && Array.isArray(res.data) ? res.data : [];
            },

            setSQL(value) {
                if (!cmView) return;
                cmView.dispatch({
                    changes: { from: 0, to: cmView.state.doc.length, insert: value || '' },
                });
            },

            loadSaved(row) {
                if (!row || typeof row.sql_text !== 'string') return;
                this.setSQL(row.sql_text);
                if (window.pqlToast) {
                    window.pqlToast.info(`Loaded "${row.title}"`);
                }
            },

            async deleteSaved(row) {
                if (!row || !row.slug) return;
                if (!window.confirm(`Delete saved query "${row.title}"?`)) return;
                const res = await window.pqlApi.fetch(
                    `/api/saved-queries/${encodeURIComponent(row.slug)}`,
                    { method: 'DELETE', silent: true },
                );
                if (res.ok || res.status === 204) {
                    if (window.pqlToast) {
                        window.pqlToast.success(`Deleted "${row.title}"`);
                    }
                    await this.refreshSaved();
                } else if (window.pqlToast) {
                    window.pqlToast.error(res.error || `HTTP ${res.status}`);
                }
            },

            openSaveModal() {
                this.saveForm = { title: '', description: '', is_shared: false };
                const el = document.getElementById('pqlSaveQueryModal');
                if (!el || !window.bootstrap) return;
                const modal = window.bootstrap.Modal.getOrCreateInstance(el);
                modal.show();
            },

            async saveCurrent() {
                const sqlText = this.getSQL().trim();
                const title = (this.saveForm.title || '').trim();
                if (!title) {
                    if (window.pqlToast) window.pqlToast.error('Title is required.');
                    return;
                }
                if (!sqlText) {
                    if (window.pqlToast) window.pqlToast.error('Nothing to save — the editor is empty.');
                    return;
                }
                this.saving = true;
                const res = await window.pqlApi.fetch('/api/saved-queries', {
                    method: 'POST',
                    body: {
                        title,
                        description: this.saveForm.description || '',
                        sql: sqlText,
                        is_shared: !!this.saveForm.is_shared,
                    },
                    silent: true,
                });
                this.saving = false;
                if (res.ok && res.data) {
                    if (window.pqlToast) {
                        window.pqlToast.success(`Saved as "${res.data.title}"`);
                    }
                    const el = document.getElementById('pqlSaveQueryModal');
                    if (el && window.bootstrap) {
                        window.bootstrap.Modal.getOrCreateInstance(el).hide();
                    }
                    await this.refreshSaved();
                } else if (window.pqlToast) {
                    window.pqlToast.error(res.error || `HTTP ${res.status}`);
                }
            },

            /** Format a single result cell for text rendering. */
            formatCell(value) {
                if (value === null || value === undefined) return '';
                if (typeof value === 'object') return JSON.stringify(value);
                return String(value);
            },

            getSQL() {
                if (!cmView) return '';
                return cmView.state.doc.toString();
            },

            _generateQueryId() {
                if (window.crypto && typeof window.crypto.randomUUID === 'function') {
                    return window.crypto.randomUUID();
                }
                return `qid-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
            },

            _startElapsed() {
                this.elapsedSeconds = 0;
                const started = performance.now();
                this._tickHandle = setInterval(() => {
                    this.elapsedSeconds = Math.floor((performance.now() - started) / 1000);
                }, 250);
            },

            _stopElapsed() {
                if (this._tickHandle) {
                    clearInterval(this._tickHandle);
                    this._tickHandle = null;
                }
            },

            async run(opts) {
                if (this.running) return;
                const query = this.getSQL().trim();
                if (!query) {
                    this.error = 'Enter a query to run.';
                    this.errorTitle = 'Nothing to run';
                    this.result = null;
                    this.explainText = null;
                    return;
                }
                const explain = !!(opts && opts.explain);
                this.running = true;
                this.error = null;
                this.result = null;
                this.explainText = null;
                this.currentQueryId = this._generateQueryId();
                this._startElapsed();
                const started = performance.now();
                const res = await window.pqlApi.fetch('/api/sql/execute', {
                    method: 'POST',
                    body: { sql: query, query_id: this.currentQueryId, explain },
                    silent: true,
                });
                this._stopElapsed();
                this.running = false;
                this.currentQueryId = null;
                const elapsed = Math.round(performance.now() - started);
                if (res.ok && res.data) {
                    if (res.data.is_explain) {
                        this.explainText = res.data.explain_text || '(empty plan)';
                        this.referencedTables = res.data.referenced_tables || [];
                        this.lastRun = {
                            ok: true,
                            summary: `Explained in ${res.data.duration_ms} ms`,
                        };
                    } else {
                        this.result = res.data;
                        this.referencedTables = res.data.referenced_tables || [];
                        this.currentHistoryId = res.data.history_id || null;
                        // Reset chart selection for the new result set
                        // unless a history deep-link pre-seeded it.
                        const cols = res.data.columns || [];
                        const hasX = this.chartConfig.x &&
                            cols.some((c) => c.name === this.chartConfig.x);
                        const hasY = this.chartConfig.y &&
                            cols.some((c) => c.name === this.chartConfig.y);
                        if (!hasX || !hasY) {
                            this.chartConfig = { type: this.chartConfig.type || 'bar', x: null, y: null };
                            this._autoPickAxes();
                        }
                        if (this.viewMode === 'chart') {
                            this.$nextTick(() => this.renderChart());
                        }
                        this.lastRun = {
                            ok: true,
                            summary: `Ran in ${res.data.duration_ms} ms · ${res.data.row_count} row${res.data.row_count === 1 ? '' : 's'}`,
                        };
                    }
                } else {
                    this.errorTitle = res.status === 403 ? 'Permission denied' : 'Query failed';
                    this.error = res.error || `HTTP ${res.status}`;
                    this.referencedTables = [];
                    this.lastRun = {
                        ok: false,
                        summary: `Failed in ${elapsed} ms`,
                    };
                }
            },

            async cancel() {
                if (!this.running || !this.currentQueryId) return;
                const qid = this.currentQueryId;
                const res = await window.pqlApi.fetch(
                    `/api/sql/execute/${encodeURIComponent(qid)}/cancel`,
                    { method: 'POST', silent: true },
                );
                if ((res.ok || res.status === 204) && window.pqlToast) {
                    window.pqlToast.info('Cancel requested.');
                } else if (window.pqlToast) {
                    window.pqlToast.error(res.error || `Cancel failed (HTTP ${res.status})`);
                }
            },
        };
}
