/**
 * Top-level notebook editor — Alpine factory mounted on
 * ``frontend/templates/pages/notebook_editor.html``.
 *
 * Coordinator only: owns the Alpine state-default object, the
 * notebook load round-trip (``init()``), the papermill parameter
 * introspection (``loadParameters()``), and the teardown
 * (``destroy()``). All other behaviour lives in sibling submodules
 * which are mixed onto the state via ``install*()`` calls before
 * the state object is returned to Alpine:
 *
 *   * ``./jobs_orchestration.js`` — Schedule + Run-Once + Jobs panel.
 *   * ``./kernel_execution.js`` — kernel WS, run/interrupt/restart,
 *     Variable Inspector.
 *   * ``./cell_operations.js`` — add/delete/move/convert cells.
 *   * ``./markdown_output.js`` — output frames + markdown
 *     edit/view toggle + per-cell editor mount.
 *   * ``./persistence.js`` — save/autosave, keymap, params tag,
 *     cell run-history.
 */

import { installCellOperations } from './cell_operations.js';
import { installJobsOrchestration } from './jobs_orchestration.js';
import { installKernelExecution } from './kernel_execution.js';
import { installMarkdownOutput } from './markdown_output.js';
import { installPersistence } from './persistence.js';

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

 // Output rendering + markdown edit/view toggle + cell-editor
 // mount live in ``./markdown_output.js``.
 // Persistence (save, autosave, keymap, params tag, history) lives
 // in ``./persistence.js``.

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
 installMarkdownOutput(state, { computeContentHash: _computeContentHash });
 installPersistence(state);
 return state;
}
