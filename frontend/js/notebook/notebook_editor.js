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
 saving: false,
 lastSavedAt: null,
 mtime: null,
 errorMessage: '',
 mtimeConflict: false,
 _editors: {},
 _onKeydown: null,

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
 this.mtime = res.data.mtime || null;
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
 this._installKeymap();
 } catch (err) {
 this.errorMessage = (err && err.message) || String(err);
 this.loading = false;
 }
 },

 _installKeymap() {
 // Cmd/Ctrl-S save; bound at the window so a focused CodeMirror
 // sub-editor cannot eat the event before we see it.
 this._onKeydown = (ev) => {
 if (ev.key !== 's' && ev.key !== 'S') return;
 if (!(ev.metaKey || ev.ctrlKey)) return;
 ev.preventDefault();
 this.save();
 };
 window.addEventListener('keydown', this._onKeydown);
 },

 async save() {
 if (this.saving || this.mtimeConflict) return;
 this.saving = true;
 try {
 const payload = {
 path: this.path,
 expected_mtime: this.mtime,
 cells: this.cells.map((cell) => ({
 cell_type: cell.cell_type,
 source: cell.source,
 result_var: cell.result_var || null,
 })),
 };
 const res = await window.pqlApi.fetch('/api/notebooks/save', {
 method: 'POST',
 body: JSON.stringify(payload),
 headers: { 'Content-Type': 'application/json' },
 silent: true,
 });
 if (res.status === 409) {
 this.mtimeConflict = true;
 this.errorMessage = 'Notebook changed on disk — reload to see the latest version.';
 return;
 }
 if (!res.ok) {
 this.errorMessage = (res.data && res.data.detail)
 || `Save failed (HTTP ${res.status}).`;
 return;
 }
 const data = res.data || {};
 const updated = data.cells || [];
 // Re-key our in-memory cells with the freshly-computed
 // content_hashes so subsequent run-history lookups, output
 // routing, and (later) WS execute frames address the same
 // identity the server now persists.
 for (let i = 0; i < this.cells.length; i++) {
 if (updated[i] && updated[i].content_hash) {
 this.cells[i].content_hash = updated[i].content_hash;
 }
 this.cells[i]._dirty = false;
 }
 this.mtime = data.mtime || this.mtime;
 this.dirty = false;
 this.lastSavedAt = new Date();
 this.errorMessage = '';
 } catch (err) {
 this.errorMessage = (err && err.message) || String(err);
 } finally {
 this.saving = false;
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
 if (this._onKeydown) {
 window.removeEventListener('keydown', this._onKeydown);
 this._onKeydown = null;
 }
 },
 };
}
