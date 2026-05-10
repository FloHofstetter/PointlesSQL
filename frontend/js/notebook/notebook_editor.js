/**
 * Top-level notebook editor — Alpine factory mounted on
 * ``frontend/templates/pages/notebook_editor.html``.
 *
 * Owns the cell list, the per-cell ``cellEditor()`` instances (one
 * CodeMirror per cell), and the load round-trip with the server.
 *
 * Sprint 66.1 scope (this file's first cut):
 *   * Load notebook via ``GET /api/notebooks/load`` on mount.
 *   * Render one cell card per cell with an isolated CodeMirror.
 *   * Render the persisted-output payload as text (Sprint 66.3
 *     replaces this with the proper MIME-bundle renderer).
 *
 * Later sprints add: save (66.2), execute via WS (66.3), cell ops
 * (66.4), SQL cells with catalog completion (66.5), markdown
 * edit/view toggle (66.6), keyboard model + autosave (66.7).
 */

import { cellEditor } from './cell_editor.js';

export function notebookEditor({ initialPath = '' } = {}) {
 return {
 path: initialPath,
 cells: [],
 outputs: [],
 dirty: false,
 loading: true,
 errorMessage: '',
 _editors: {},

 async init() {
 try {
 const res = await window.pqlApi.fetch(
 `/api/notebooks/load?path=${encodeURIComponent(this.path)}`,
 { silent: true },
 );
 if (!res.ok) {
 this.errorMessage = (res.data && res.data.detail)
 || `Failed to load notebook (HTTP ${res.status}).`;
 this.loading = false;
 return;
 }
 this.path = res.data.path || this.path;
 this.dirty = !!res.data.dirty;
 this.cells = (res.data.cells || []).map((cell) => ({
 ...cell,
 _dirty: false,
 }));
 this.outputs = res.data.outputs || [];
 this.loading = false;
 // Wait one frame so Alpine's x-for has rendered the cell DOM,
 // then mount per-cell CodeMirror editors.
 await this.$nextTick();
 await this._mountAllEditors();
 } catch (err) {
 this.errorMessage = (err && err.message) || String(err);
 this.loading = false;
 }
 },

 async _mountAllEditors() {
 const promises = this.cells.map(async (cell) => {
 const host = document.getElementById(`pql-cell-host-${cell.id}`);
 if (!host || this._editors[cell.id]) return;
 const editor = cellEditor({
 initialSource: cell.source,
 language: cell.cell_type === 'sql'
 ? 'sql'
 : (cell.cell_type === 'markdown' ? 'markdown' : 'python'),
 onSourceChange: (value) => this._onCellSourceChange(cell.id, value),
 });
 this._editors[cell.id] = editor;
 await editor.mount(host);
 });
 await Promise.all(promises);
 },

 _onCellSourceChange(cellId, value) {
 const cell = this.cells.find((c) => c.id === cellId);
 if (!cell) return;
 cell.source = value;
 cell._dirty = true;
 this.dirty = true;
 },

 outputsForCell(contentHash) {
 // Sprint 66.1 scope: surface persisted outputs as plain text so the
 // page exercises the load round-trip.  Sprint 66.3 swaps this for
 // the proper MIME-bundle-aware renderer.
 const matching = this.outputs.filter(
 (o) => o.content_hash === contentHash,
 );
 if (!matching.length) return '';
 const lines = [];
 for (const out of matching) {
 const c = out.content || {};
 if (out.msg_type === 'stream' && typeof c.text === 'string') {
 lines.push(c.text);
 } else if (
 out.msg_type === 'execute_result'
 || out.msg_type === 'display_data'
 ) {
 const data = c.data || {};
 if (typeof data['text/plain'] === 'string') {
 lines.push(data['text/plain']);
 } else if (typeof data['text/markdown'] === 'string') {
 lines.push(data['text/markdown']);
 } else if (typeof data['text/html'] === 'string') {
 lines.push('[html output]');
 } else if (data['image/png']) {
 lines.push('[image]');
 }
 } else if (out.msg_type === 'error') {
 const tb = Array.isArray(c.traceback) ? c.traceback.join('\n') : '';
 lines.push(tb || `${c.ename}: ${c.evalue}`);
 }
 }
 return lines.join('\n');
 },

 cellLabel(cell) {
 if (cell.cell_type === 'sql') {
 return cell.result_var
 ? `SQL → ${cell.result_var}`
 : 'SQL';
 }
 if (cell.cell_type === 'markdown') return 'Markdown';
 return 'Code';
 },

 destroy() {
 for (const editor of Object.values(this._editors)) {
 editor.destroy();
 }
 this._editors = {};
 },
 };
}
