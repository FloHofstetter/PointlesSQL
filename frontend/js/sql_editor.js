/**
 * Phase 12 SQL editor Alpine component.
 *
 * Bootstraps CodeMirror 6 into the #pql-sql-editor-root div and wires
 * the Run button + Cmd/Ctrl+Enter to POST /api/sql/execute, rendering
 * the result table inline.  The editor is single-instance per page —
 * this page is /sql.
 */
import { EditorState } from '@codemirror/state';
import { EditorView, keymap, highlightActiveLine, lineNumbers } from '@codemirror/view';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { syntaxHighlighting, defaultHighlightStyle, bracketMatching } from '@codemirror/language';
import { sql } from '@codemirror/lang-sql';
import { oneDark } from '@codemirror/theme-one-dark';

let cmView = null;

window.sqlEditor = function () {
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

        init() {
            const host = document.getElementById('pql-sql-editor-root');
            if (!host || cmView) return;
            const runShortcut = {
                key: 'Mod-Enter',
                run: () => {
                    this.run();
                    return true;
                },
                preventDefault: true,
            };
            // Honour ?prefill=<urlencoded sql> so the /queries re-run button
            // (Sprint 50) and future deep-links open with a pre-filled query.
            // Clean the URL so a reload isn't a second re-run.
            const qs = new URLSearchParams(window.location.search);
            const prefill = qs.get('prefill');
            const startingDoc = prefill && prefill.trim() ? prefill : 'SELECT 1 AS n';
            if (prefill) {
                try { history.replaceState({}, '', '/sql'); } catch (e) { /* ignore */ }
            }
            const saveShortcut = {
                key: 'Mod-s',
                run: () => {
                    this.openSaveModal();
                    return true;
                },
                preventDefault: true,
            };
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
                        keymap.of([
                            runShortcut,
                            saveShortcut,
                            ...defaultKeymap,
                            ...historyKeymap,
                        ]),
                    ],
                }),
                parent: host,
            });
            this.refreshSaved();
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
            const res = await window.pqlApi.fetch(`/api/saved-queries/${encodeURIComponent(row.slug)}`, {
                method: 'DELETE',
                silent: true,
            });
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
            // Prefer crypto.randomUUID where available; fall back to a
            // timestamp+random blend so sessions on older browsers still
            // emit unique IDs.  Only used as a registry key, not a secret.
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

        async run() {
            if (this.running) return;
            const query = this.getSQL().trim();
            if (!query) {
                this.error = 'Enter a query to run.';
                this.errorTitle = 'Nothing to run';
                this.result = null;
                return;
            }
            this.running = true;
            this.error = null;
            this.result = null;
            this.currentQueryId = this._generateQueryId();
            this._startElapsed();
            const started = performance.now();
            const res = await window.pqlApi.fetch('/api/sql/execute', {
                method: 'POST',
                body: { sql: query, query_id: this.currentQueryId },
                silent: true, // we render the error inline, no auto-toast
            });
            this._stopElapsed();
            this.running = false;
            this.currentQueryId = null;
            const elapsed = Math.round(performance.now() - started);
            if (res.ok && res.data) {
                this.result = res.data;
                this.referencedTables = res.data.referenced_tables || [];
                this.lastRun = {
                    ok: true,
                    summary: `Ran in ${res.data.duration_ms} ms · ${res.data.row_count} row${res.data.row_count === 1 ? '' : 's'}`,
                };
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
};
