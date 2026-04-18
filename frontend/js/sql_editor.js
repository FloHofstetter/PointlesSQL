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
            cmView = new EditorView({
                state: EditorState.create({
                    doc: 'SELECT 1 AS n',
                    extensions: [
                        lineNumbers(),
                        highlightActiveLine(),
                        history(),
                        bracketMatching(),
                        syntaxHighlighting(defaultHighlightStyle),
                        sql(),
                        oneDark,
                        keymap.of([runShortcut, ...defaultKeymap, ...historyKeymap]),
                    ],
                }),
                parent: host,
            });
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
            const started = performance.now();
            const res = await window.pqlApi.fetch('/api/sql/execute', {
                method: 'POST',
                body: { sql: query },
                silent: true, // we render the error inline, no auto-toast
            });
            this.running = false;
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
    };
};
