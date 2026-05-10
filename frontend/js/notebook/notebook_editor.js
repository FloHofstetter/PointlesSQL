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
import { createKernelClient } from './kernel_ws.js';
import { renderOutputFrame } from './output_renderer.js';

// Mirrors `pointlessql.services.notebook._doc.compute_content_hash`
// — FNV-1a 64-bit over the line-right-stripped + LF-normalised source.
// Kept inline (rather than a shared util) so the cell-identity contract
// has one obvious copy on each side.
const _FNV_OFFSET_64 = 0xcbf29ce484222325n;
const _FNV_PRIME_64 = 0x100000001b3n;
const _FNV_MASK_64 = 0xffffffffffffffffn;

async function _computeContentHash(source) {
 const normalised = String(source || '')
 .replace(/\r\n/g, '\n')
 .split('\n')
 .map((line) => line.replace(/\s+$/, ''))
 .join('\n');
 const bytes = new TextEncoder().encode(normalised);
 let h = _FNV_OFFSET_64;
 for (const byte of bytes) {
 h = ((h ^ BigInt(byte)) * _FNV_PRIME_64) & _FNV_MASK_64;
 }
 return h.toString(16).padStart(16, '0');
}

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
 kernelStatus: 'disconnected',
 kernelSessionId: null,
 _editors: {},
 _onKeydown: null,
 _kernel: null,
 _liveOutputs: {},
 _runStatus: {},

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
 this._seedLiveOutputs();
 this.loading = false;
 // Wait one frame so Alpine's x-for has rendered the cell DOM,
 // then mount per-cell CodeMirror editors.
 await this.$nextTick();
 await this._mountAllEditors();
 this._renderAllOutputs();
 this._installKeymap();
 this._connectKernel();
 } catch (err) {
 this.errorMessage = (err && err.message) || String(err);
 this.loading = false;
 }
 },

 _seedLiveOutputs() {
 this._liveOutputs = {};
 for (const out of this.outputs) {
 const hash = out.content_hash;
 if (!hash) continue;
 if (!this._liveOutputs[hash]) this._liveOutputs[hash] = [];
 this._liveOutputs[hash].push(out);
 }
 },

 _outputContainerFor(cell) {
 return document.getElementById(`pql-cell-output-${cell.id}`);
 },

 _renderCellOutput(cell) {
 const host = this._outputContainerFor(cell);
 if (!host) return;
 host.innerHTML = '';
 const frames = this._liveOutputs[cell.content_hash] || [];
 for (const frame of frames) {
 host.appendChild(renderOutputFrame(frame));
 }
 },

 _renderAllOutputs() {
 for (const cell of this.cells) {
 this._renderCellOutput(cell);
 }
 },

 _connectKernel() {
 if (this._kernel) return;
 this.kernelStatus = 'connecting';
 this._kernel = createKernelClient({
 notebookPath: this.path,
 onMessage: (frame) => this._onKernelFrame(frame),
 onReady: (info) => {
 this.kernelStatus = 'ready';
 this.kernelSessionId = info.kernel_session_id || null;
 },
 onClose: () => {
 this.kernelStatus = 'closed';
 },
 onError: (e) => {
 this.errorMessage = (e && e.message) || 'Kernel error';
 },
 });
 this._kernel.connect();
 },

 _onKernelFrame(frame) {
 if (!frame || typeof frame !== 'object') return;
 const hash = frame.content_hash;
 if (!hash) return;
 const cell = this.cells.find((c) => c.content_hash === hash);
 if (frame.channel === 'iopub') {
 const msgType = frame.msg_type;
 if (msgType === 'status') {
 if (cell) {
 const state = (frame.content && frame.content.execution_state) || '';
 if (state === 'busy') this._runStatus[hash] = 'running';
 else if (state === 'idle' && this._runStatus[hash] === 'running') {
 // The execute_reply on the shell channel will set the
 // final ok/error status; "idle" alone just means the
 // kernel is no longer busy with this request.
 }
 }
 return;
 }
 if (msgType === 'execute_input') {
 // First iopub frame for a fresh execute — clear stale outputs.
 this._liveOutputs[hash] = [];
 if (cell) this._renderCellOutput(cell);
 return;
 }
 if (msgType === 'stream'
 || msgType === 'execute_result'
 || msgType === 'display_data'
 || msgType === 'error') {
 if (!this._liveOutputs[hash]) this._liveOutputs[hash] = [];
 this._liveOutputs[hash].push(frame);
 if (cell) {
 const host = this._outputContainerFor(cell);
 if (host) host.appendChild(renderOutputFrame(frame));
 }
 }
 } else if (frame.channel === 'shell' && frame.msg_type === 'execute_reply') {
 const status = frame.content && frame.content.status;
 const execCount = frame.content && frame.content.execution_count;
 this._runStatus[hash] = status || 'ok';
 if (cell) {
 cell.exec_count = execCount;
 cell.status = status;
 }
 }
 },

 async runCell(cell) {
 if (!cell) return;
 if (!this._kernel || this._kernel.readyState !== WebSocket.OPEN) {
 this.errorMessage = 'Kernel not connected.';
 return;
 }
 // Markdown cells don't go through the kernel.
 if (cell.cell_type === 'markdown') return;
 // Refresh content_hash before sending so the kernel routes
 // outputs to the right identity even if the user edited the
 // cell since the last save.
 const fresh = await this._refreshCellHash(cell);
 try {
 await this._kernel.execute(fresh.contentHash, fresh.source);
 } catch (e) {
 this.errorMessage = (e && e.message) || String(e);
 }
 },

 async _refreshCellHash(cell) {
 // Ask the per-cell editor for the current source, recompute the
 // FNV-1a-64 hash client-side, and update the cell.
 const editor = this._editors[cell.id];
 const source = editor ? editor.getSource() : cell.source;
 const newHash = await _computeContentHash(source);
 if (newHash !== cell.content_hash) {
 // Move any persisted live-outputs over to the new hash so
 // the visual state survives a hash change.
 this._liveOutputs[newHash] = this._liveOutputs[cell.content_hash] || [];
 delete this._liveOutputs[cell.content_hash];
 cell.content_hash = newHash;
 }
 cell.source = source;
 return { contentHash: newHash, source: source };
 },

 async interruptKernel() {
 if (!this._kernel) return;
 try { await this._kernel.interrupt(); }
 catch (e) { this.errorMessage = (e && e.message) || String(e); }
 },

 async restartKernel() {
 if (!this._kernel) return;
 try {
 await this._kernel.restart();
 this._liveOutputs = {};
 this._runStatus = {};
 this._renderAllOutputs();
 }
 catch (e) { this.errorMessage = (e && e.message) || String(e); }
 },

 // -- Cell management ops --

 _nextCellOrdinal() {
 let max = -1;
 for (const cell of this.cells) {
 const m = /^cell-(\d+)$/.exec(cell.id || '');
 if (m) {
 const n = parseInt(m[1], 10);
 if (Number.isFinite(n) && n > max) max = n;
 }
 }
 return max + 1;
 },

 async _makeBlankCell(cellType = 'code') {
 const ordinal = this._nextCellOrdinal();
 const source = '';
 return {
 id: `cell-${ordinal}`,
 content_hash: await _computeContentHash(source),
 cell_type: cellType,
 source: source,
 result_var: null,
 _dirty: false,
 exec_count: null,
 status: null,
 };
 },

 async _insertCellAt(index, cell) {
 this.cells.splice(index, 0, cell);
 this.dirty = true;
 await this.$nextTick();
 const host = document.getElementById(`pql-cell-host-${cell.id}`);
 if (host && !this._editors[cell.id]) {
 const editor = cellEditor({
 initialSource: cell.source,
 language: cell.cell_type === 'sql'
 ? 'sql'
 : (cell.cell_type === 'markdown' ? 'markdown' : 'python'),
 onSourceChange: (value) => this._onCellSourceChange(cell.id, value),
 });
 this._editors[cell.id] = editor;
 await editor.mount(host);
 }
 },

 async addCellAbove(cell, cellType = 'code') {
 const idx = this.cells.findIndex((c) => c.id === cell.id);
 if (idx < 0) return;
 const fresh = await this._makeBlankCell(cellType);
 await this._insertCellAt(idx, fresh);
 },

 async addCellBelow(cell, cellType = 'code') {
 const idx = this.cells.findIndex((c) => c.id === cell.id);
 const insertAt = idx < 0 ? this.cells.length : idx + 1;
 const fresh = await this._makeBlankCell(cellType);
 await this._insertCellAt(insertAt, fresh);
 },

 async addCellAtEnd(cellType = 'code') {
 const fresh = await this._makeBlankCell(cellType);
 await this._insertCellAt(this.cells.length, fresh);
 },

 deleteCell(cell) {
 const idx = this.cells.findIndex((c) => c.id === cell.id);
 if (idx < 0) return;
 const editor = this._editors[cell.id];
 if (editor) {
 editor.destroy();
 delete this._editors[cell.id];
 }
 // Drop any live outputs (the persisted notebook_outputs rows
 // for the dead content_hash will be cleared next time the cell
 // is re-executed; nothing here can address it anyway).
 delete this._liveOutputs[cell.content_hash];
 delete this._runStatus[cell.content_hash];
 this.cells.splice(idx, 1);
 this.dirty = true;
 },

 async _moveCell(cell, delta) {
 const idx = this.cells.findIndex((c) => c.id === cell.id);
 if (idx < 0) return;
 const target = idx + delta;
 if (target < 0 || target >= this.cells.length) return;
 const [removed] = this.cells.splice(idx, 1);
 this.cells.splice(target, 0, removed);
 this.dirty = true;
 // Move ops don't touch content_hash, so no editor remount.
 },

 async moveCellUp(cell) { await this._moveCell(cell, -1); },
 async moveCellDown(cell) { await this._moveCell(cell, +1); },

 async convertCellType(cell, newType) {
 if (cell.cell_type === newType) return;
 const editor = this._editors[cell.id];
 const source = editor ? editor.getSource() : cell.source;
 // Tear down + re-mount the editor so the new language extension
 // (python / sql / markdown) takes effect.
 if (editor) { editor.destroy(); delete this._editors[cell.id]; }
 cell.cell_type = newType;
 cell.source = source;
 cell.content_hash = await _computeContentHash(source);
 cell.result_var = newType === 'sql' ? cell.result_var : null;
 cell.exec_count = null;
 cell.status = null;
 // Outputs from the previous cell type don't apply.
 delete this._liveOutputs[cell.content_hash];
 cell._dirty = true;
 this.dirty = true;
 await this.$nextTick();
 const host = document.getElementById(`pql-cell-host-${cell.id}`);
 if (host) {
 const fresh = cellEditor({
 initialSource: source,
 language: newType === 'sql'
 ? 'sql'
 : (newType === 'markdown' ? 'markdown' : 'python'),
 onSourceChange: (value) => this._onCellSourceChange(cell.id, value),
 });
 this._editors[cell.id] = fresh;
 // Reset the host's init guard so the new editor can mount.
 host.dataset.pqlCellInit = '';
 host.innerHTML = '';
 await fresh.mount(host);
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
 if (this._kernel) {
 this._kernel.close();
 this._kernel = null;
 }
 },
 };
}
