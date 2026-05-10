/**
 * SQL editor — query execute / cancel + elapsed-time counter.
 *
 * Split out of ``sql_editor.js``. Owns the
 * ``run({explain})`` and ``cancel()`` flows that talk to
 * ``/api/sql/execute`` + ``/api/sql/execute/{id}/cancel``, the
 * elapsed-seconds counter that ticks while a query runs (so the UI
 * can show ``Ran for 12s``), and the ``_generateQueryId`` UUID
 * helper.
 *
 * After a successful execute, ``run()`` either populates
 * ``this.result`` (table view) or ``this.explainText`` (EXPLAIN
 * mode) and re-runs the chart auto-pick if the chart view is
 * active. The auto-pick lives in ``sql_editor_chart.js``.
 */

import { toast } from '../api.js';

export const executeMethods = {
 /** Format a single result cell for text rendering. */
 formatCell(value) {
 if (value === null || value === undefined) return '';
 if (typeof value === 'object') return JSON.stringify(value);
 return String(value);
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

 /**
 * Heuristic destructive-statement detector for the editor's
 * confirmation modal (Phase 63.7). Server-side AST classification
 * is the source of truth for execution; this is purely a UX
 * speed-bump that warns before submitting "DROP TABLE …", "DROP
 * SCHEMA …", or "DELETE FROM … " without a WHERE clause. False
 * positives are acceptable — extra confirmation never hurts.
 */
 _isDestructive(query) {
 const cleaned = query
 // Strip /* … */ block comments and -- line comments so a
 // commented-out DROP doesn't trigger the modal.
 .replace(/\/\*[\s\S]*?\*\//g, ' ')
 .replace(/--[^\n]*/g, ' ')
 .replace(/\s+/g, ' ')
 .trim()
 .toUpperCase();
 if (/^DROP\s+(TABLE|SCHEMA|CATALOG)\b/.test(cleaned)) return 'drop';
 if (/^DELETE\s+FROM\s+/.test(cleaned) && !/\sWHERE\s/.test(cleaned)) {
 return 'delete-all';
 }
 return null;
 },

 _confirmDestructive(kind) {
 const msg = kind === 'drop'
 ? 'This statement will permanently remove a UC object. Confirm?'
 : 'This DELETE has no WHERE clause and will remove every row in the target. Confirm?';
 // Plain confirm() is fine for the MVP — a Bootstrap modal
 // would add layout work without changing the UX semantics
 // since users see exactly the same yes/no decision.
 return window.confirm(msg);
 },

 async run(opts) {
 if (this.running) return;
 const query = this.getSQL().trim();
 if (!query) {
 this.error = 'Enter a query to run.';
 this.errorTitle = 'Nothing to run';
 this.result = null;
 this.explainText = null;
 this.explainPlan = null;
 return;
 }
 const explain = !!(opts && opts.explain);
 if (!explain && !(opts && opts.skipConfirm)) {
 const destructive = this._isDestructive(query);
 if (destructive && !this._confirmDestructive(destructive)) {
 return;
 }
 }
 this.running = true;
 this.error = null;
 this.result = null;
 this.explainText = null;
 this.explainPlan = null;
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
 this.explainPlan = res.data.explain_plan || null;
 this.referencedTables = res.data.referenced_tables || [];
 this.lastRun = {
 ok: true,
 summary: `Explained in ${res.data.duration_ms} ms`,
 };
 } else if (res.data.kind === 'dml' || res.data.kind === 'ddl') {
 // Phase 63: write statement landed via the dispatcher.
 // The result envelope carries target / rows_affected /
 // agent_run_id rather than a row table; render via the
 // dml/ddl card branch.
 this.result = res.data;
 this.referencedTables = res.data.referenced_tables || [];
 this.currentHistoryId = res.data.history_id || null;
 const verb = res.data.stmt_type
 ? res.data.stmt_type.replace(/_/g, ' ').toUpperCase()
 : (res.data.kind === 'dml' ? 'DML' : 'DDL');
 const target = res.data.target ? ` on ${res.data.target}` : '';
 const rows = res.data.rows_affected != null
 ? ` · ${res.data.rows_affected} row${res.data.rows_affected === 1 ? '' : 's'} affected`
 : '';
 this.lastRun = {
 ok: true,
 summary: `${verb}${target}${rows}`,
 };
 } else {
 this.result = res.data;
 this.referencedTables = res.data.referenced_tables || [];
 this.currentHistoryId = res.data.history_id || null;
 // Reset chart selection for the new result set unless a
 // history deep-link pre-seeded it.
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
 if (res.ok || res.status === 204) {
 toast('info', 'Cancel requested.');
 } else {
 toast('error', res.error || `Cancel failed (HTTP ${res.status})`);
 }
 },
};
