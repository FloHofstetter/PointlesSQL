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
import { installCellOperations } from './cell_operations.js';
import { installJobsOrchestration } from './jobs_orchestration.js';
import { installKernelExecution } from './kernel_execution.js';
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
 const state = {
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
 // Phase 67.1: Papermill parameters declared by the notebook's
 // ``tags=["parameters"]`` cell, populated by ``loadParameters()``
 // after the initial load. The Schedule + Run-Once modals read
 // this array to render typed override forms.
 parameters: [],
 _parametersLoaded: false,
 // Phase 67.2 Schedule modal state.
 scheduleModalOpen: false,
 scheduleSubmitting: false,
 scheduleError: '',
 scheduleForm: { name: '', cronExpr: '0 5 * * *', parameters: {} },
 // Phase 67.3 Run-Once modal state.
 runOnceModalOpen: false,
 runOnceSubmitting: false,
 runOnceError: '',
 runOnceStatus: '',
 runOnceForm: { parameters: {} },
 // Phase 67.4 Notebook-Jobs panel state.
 jobsPanelOpen: false,
 jobsPanel: { scheduled_jobs: [], recent_runs: [] },
 // Phase 67.5 Variable Inspector state.
 inspectorOpen: false,
 inspectorVars: [],
 inspectorDetail: null,
 inspectorDetailFor: null,
 _editors: {},
 _onKeydown: null,
 _kernel: null,
 _liveOutputs: {},
 _runStatus: {},
 _autosaveTimer: null,
 _historyByCell: {},
 historyOpenFor: null,

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
 // Fire-and-forget — populates ``this.parameters`` once papermill
 // has introspected the notebook. The Schedule + Run-Once modals
 // poll-on-open so a slow inspect call never blocks page load.
 this.loadParameters();
 this.loadNotebookJobs();
 } catch (err) {
 this.errorMessage = (err && err.message) || String(err);
 this.loading = false;
 }
 },

 /**
 * Fetch the notebook's papermill parameter declarations.
 *
 * Cached in ``this.parameters`` after the first call. Re-call after
 * a save that may have toggled the ``parameters`` tag on a cell so
 * the UI stays in sync with the on-disk truth.
 */
 async loadParameters() {
 if (!this.path) return;
 try {
 const res = await window.pqlApi.fetch(
 `/api/notebooks/inspect?path=${encodeURIComponent(this.path)}`,
 { silent: true },
 );
 if (res.ok && Array.isArray(res.data)) {
 this.parameters = res.data;
 this._parametersLoaded = true;
 }
 } catch {
 // Non-fatal — the notebook may simply have no parameters cell.
 this.parameters = [];
 this._parametersLoaded = true;
 }
 },

 // Job-orchestration methods (Schedule modal, Run-Once modal,
 // Notebook-Jobs panel) live in ``./jobs_orchestration.js`` and
 // get installed onto ``state`` below.

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

 // Kernel + execution methods (_connectKernel, _onKernelFrame,
 // runCell, runCellAndAdvance, interrupt/restart, Variable
 // Inspector helpers) live in ``./kernel_execution.js`` and get
 // installed onto ``state`` below.

 async toggleHistoryFor(cell) {
 if (this.historyOpenFor === cell.id) {
 this.historyOpenFor = null;
 return;
 }
 await this._fetchHistory(cell);
 this.historyOpenFor = cell.id;
 },

 async _fetchHistory(cell) {
 try {
 const url = `/api/notebooks/cell-history?path=${encodeURIComponent(this.path)}`
 + `&content_hash=${encodeURIComponent(cell.content_hash)}&limit=5`;
 const res = await window.pqlApi.fetch(url, { silent: true });
 if (res.ok) {
 this._historyByCell[cell.id] = (res.data && res.data.runs) || [];
 } else {
 this._historyByCell[cell.id] = [];
 }
 } catch (_e) {
 this._historyByCell[cell.id] = [];
 }
 },

 historyForCell(cell) {
 return this._historyByCell[cell.id] || [];
 },

 // Cell management ops (add/delete/move/convert + per-cell
 // editor lifecycle) live in ``./cell_operations.js`` and get
 // installed onto ``state`` below.

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
 tags: Array.isArray(cell.tags) ? cell.tags : [],
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
 // Markdown cells default to view-mode and only mount the
 // editor on demand when the user clicks into them.
 if (cell.cell_type === 'markdown') {
 cell.view_mode = true;
 await this._renderMarkdown(cell);
 return;
 }
 cell.view_mode = false;
 const host = document.getElementById(`pql-cell-host-${cell.id}`);
 if (!host || this._editors[cell.id]) return;
 const editor = cellEditor({
 initialSource: cell.source,
 language: cell.cell_type === 'sql' ? 'sql' : 'python',
 onSourceChange: (value) => this._onCellSourceChange(cell.id, value),
 });
 this._editors[cell.id] = editor;
 await editor.mount(host);
 });
 await Promise.all(promises);
 },

 async _renderMarkdown(cell) {
 try {
 const res = await window.pqlApi.fetch(
 '/api/notebooks/render-markdown',
 {
 method: 'POST',
 body: JSON.stringify({ source: cell.source || '' }),
 headers: { 'Content-Type': 'application/json' },
 silent: true,
 },
 );
 if (res.ok) {
 cell._renderedHtml = (res.data && res.data.html) || '';
 } else {
 cell._renderedHtml = '<em>Failed to render markdown.</em>';
 }
 } catch (err) {
 cell._renderedHtml = `<em>${(err && err.message) || String(err)}</em>`;
 }
 },

 async enterMarkdownEdit(cell) {
 if (cell.cell_type !== 'markdown') return;
 cell.view_mode = false;
 await this.$nextTick();
 const host = document.getElementById(`pql-cell-host-${cell.id}`);
 if (!host) return;
 if (this._editors[cell.id]) {
 this._editors[cell.id].focus();
 return;
 }
 const editor = cellEditor({
 initialSource: cell.source,
 language: 'markdown',
 onSourceChange: (value) => this._onCellSourceChange(cell.id, value),
 });
 this._editors[cell.id] = editor;
 host.dataset.pqlCellInit = '';
 host.innerHTML = '';
 await editor.mount(host);
 editor.focus();
 },

 async exitMarkdownEdit(cell) {
 if (cell.cell_type !== 'markdown') return;
 // Pull the latest source from the editor before tearing it down.
 const editor = this._editors[cell.id];
 if (editor) {
 cell.source = editor.getSource();
 cell.content_hash = await _computeContentHash(cell.source);
 editor.destroy();
 delete this._editors[cell.id];
 }
 await this._renderMarkdown(cell);
 cell.view_mode = true;
 },

 _onCellSourceChange(cellId, value) {
 const cell = this.cells.find((c) => c.id === cellId);
 if (!cell) return;
 cell.source = value;
 cell._dirty = true;
 this.dirty = true;
 this._scheduleAutosave();
 },

 _scheduleAutosave() {
 if (this._autosaveTimer) clearTimeout(this._autosaveTimer);
 this._autosaveTimer = setTimeout(() => {
 this._autosaveTimer = null;
 if (this.dirty && !this.saving && !this.mtimeConflict) this.save();
 }, 5000);
 },

 cellLabel(cell) {
 // Phase 67.7 — params-tagged cells render as a dedicated label so
 // the user sees at a glance which cell the Schedule/Run-Once modals
 // will read defaults from.
 const tags = Array.isArray(cell.tags) ? cell.tags : [];
 if (tags.includes('parameters')) {
 if (cell.cell_type === 'sql') return 'SQL · PARAMS';
 if (cell.cell_type === 'markdown') return 'Markdown · PARAMS';
 return 'PARAMS';
 }
 if (cell.cell_type === 'sql') {
 return cell.result_var
 ? `SQL → ${cell.result_var}`
 : 'SQL';
 }
 if (cell.cell_type === 'markdown') return 'Markdown';
 return 'Code';
 },

 cellHasParamsTag(cell) {
 return Array.isArray(cell.tags) && cell.tags.includes('parameters');
 },

 toggleParamsTag(cell) {
 if (!cell) return;
 if (!Array.isArray(cell.tags)) cell.tags = [];
 const idx = cell.tags.indexOf('parameters');
 if (idx >= 0) cell.tags.splice(idx, 1);
 else cell.tags.push('parameters');
 cell._dirty = true;
 this.dirty = true;
 this._scheduleAutosave();
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
 installJobsOrchestration(state);
 installKernelExecution(state, { computeContentHash: _computeContentHash });
 installCellOperations(state, { computeContentHash: _computeContentHash });
 return state;
}
