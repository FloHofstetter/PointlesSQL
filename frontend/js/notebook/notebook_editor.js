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

import { installBranchBinding } from './branch_binding.js';
import { installCellAuthorship } from './cell_authorship.js';
import { installCellFacts } from './cell_facts.js';
import { installCellLineage } from './cell_lineage.js';
import { installCellOperations } from './cell_operations.js';
import { installChatIntegration } from './chat_integration.js';
import { installCoeditLifecycle } from './coedit.js';
import { installJobsOrchestration } from './jobs_orchestration.js';
import { installKernelExecution } from './kernel_execution.js';
import { installMarkdownOutput } from './markdown_output.js';
import { installNotebookTags } from './notebook_tags.js';
import { installPersistence } from './persistence.js';
import { installReplays } from './replays.js';
import { installRevisions } from './revisions.js';
import { installSequenceProposals } from './sequence_proposals.js';
import { installShareDialog } from './share_dialog.js';
import { installWidgetsPanel } from './widgets_panel.js';
import { installPermissionsPanel } from './permissions_panel.js';

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

export function notebookEditor({ initialPath = '', currentUser = null } = {}) {
 const state = {
 path: initialPath,
 currentUser: currentUser || {},
 cells: [],
 // Phase 113.6 — id of the cell whose editor currently has focus.
 // Drives the toolbar's Run-all split-button "above/below selected"
 // items.  Updated by @focusin on each cell's editor host.
 _focusedCellId: null,
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
 // Sprint 113.3 — unified Run-notebook modal state.
 // Collapses the former Phase 67.2 Schedule modal + Phase 67.3 Run-Once
 // modal into one tabbed surface.  Submitting + error + parameters are
 // shared between the two tabs (run-now / schedule); name + cronExpr
 // only apply on the schedule tab, status only on the run-now tab.
 runModal: {
  open: false,
  tab: 'run-now',
  submitting: false,
  error: '',
  parameters: {},
  name: '',
  cronExpr: '0 5 * * *',
  status: '',
 },
 // Phase 67.4 Notebook-Jobs panel state.
 jobsPanelOpen: false,
 jobsPanel: { scheduled_jobs: [], recent_runs: [] },
 // Phase 67.5 Variable Inspector state (visibility now lives on
 // ``rightDrawer.tab`` per Sprint 113.2; the data fields stay here
 // because kernel_execution.js + WS frames write them by name).
 inspectorVars: [],
 inspectorDetail: null,
 inspectorDetailFor: null,
 _editors: {},
 _onKeydown: null,
 _kernel: null,
 _liveOutputs: {},
 _runStatus: {},
 // Phase 94: per-cell run-duration tracking, keyed by content_hash.
 // Wall-clock delta captured client-side from performance.now()
 // between the ``execute_input`` iopub frame and the matching
 // ``execute_reply`` on the shell channel. Persistent display
 // across reload would require the backend to pass through the
 // existing ``NotebookCellRun.started_at`` / ``finished_at`` fields
 // over the WS frame — out of scope for Phase 94.
 _runStartedAt: {},
 _runDurationMs: {},
 _autosaveTimer: null,
 _historyByCell: {},
 historyOpenFor: null,
 // Phase 95.2 — per-cell social: notebook UUID + bulk-count snapshot.
 // ``notebookUuid`` lands from /api/notebooks/load; ``cellCounts`` is
 // a ``{ cell_uuid -> { comments, reactions, followers } }`` map
 // populated by ``refreshCellCounts()`` once on init and after each
 // save.  Cells that have no entry are simply rendered without a
 // count badge.
 notebookUuid: null,
 cellCounts: {},
 // Phase 96 — AI-assistant provenance buffer.  ``_pendingProvenance``
 // collects accepted-proposal records between Insert/Apply click and
 // the next /api/notebooks/save call, which flushes them as
 // notebook_cell_provenance rows.  Visibility of the chat panel
 // itself now lives on ``rightDrawer.tab`` (Sprint 113.2).
 _pendingProvenance: [],
 // Sprint 113.2 — unified right-edge drawer.  Collapses the former
 // Chat (Phase 96) + Variables (Phase 67.5) + Social (Phase 77.6)
 // overlays into one fixed-position drawer with a tab strip.  All
 // six tab bodies stay in the DOM (x-show, not x-if) so the chat
 // WebSocket subscription survives tab switches.
 rightDrawer: { open: false, tab: 'chat' },
 // Sprint 112.5 — bounded ring buffer of recent notebook-wide cell
 // runs, populated by the kernel ``execute_reply`` handler in
 // ``kernel_execution.js``.  Surfaced in the meta panel's Activity
 // section via ``recentNotebookRuns()``.  Size 5 keeps the surface
 // glanceable; older entries are pushed off the tail.
 _recentRunsRing: [],

 /**
  * Phase 95.2 — fetch per-cell social counts for this notebook.
  *
  * Called on initial load + after every successful save.  Failures
  * are non-fatal (chips stay at their last-known counts) so a
  * transient API hiccup never blocks the editor.
  */
 async refreshCellCounts() {
  if (!this.notebookUuid) return;
  try {
   const res = await window.pqlApi.fetch(
    `/api/social/notebook_cell/_bulk_counts?notebook_id=${encodeURIComponent(this.notebookUuid)}`,
    { silent: true },
   );
   if (res.ok && res.data && res.data.counts) {
    this.cellCounts = res.data.counts;
   }
  } catch {
   // Non-fatal — leave the prior snapshot in place.
  }
 },

 /**
  * Initial-counts payload for one cell's ``cellThread`` factory.
  */
 cellCountsFor(cell) {
  if (!cell || !cell.cell_uuid) return null;
  return this.cellCounts[cell.cell_uuid] || null;
 },

 /**
  * Format the most recent run duration for ``cell`` as a human
  * string ("0.2s" / "1.4s" / "2m 3s"), or '' if the cell hasn't
  * finished a run yet in this session.
  */
 runDurationFor(cell) {
  if (!cell || !cell.content_hash) return '';
  const ms = this._runDurationMs[cell.content_hash];
  if (ms == null || !Number.isFinite(ms) || ms < 0) return '';
  if (ms < 1000) return `${Math.round(ms)}ms`;
  if (ms < 60000) return `${(ms / 1000).toFixed(1)}s`;
  const m = Math.floor(ms / 60000);
  const s = Math.round((ms - m * 60000) / 1000);
  return `${m}m ${s}s`;
 },

 /**
  * Sprint 112.5 — colour class for the toolbar save dot.
  *
  * Maps the editor's load/save/dirty axis onto a single Bootstrap
  * background utility so the toolbar shows one at-a-glance state
  * instead of four separate badges.
  */
 saveDotClass() {
  if (this.loading || this.saving) return 'bg-warning';
  if (this.dirty) return 'bg-warning';
  if (this.lastSavedAt) return 'bg-success';
  return 'bg-secondary';
 },

 /**
  * Tooltip for the toolbar save dot.  Mirrors what the old
  * Loading / Saving / Unsaved / Saved badges used to spell out.
  */
 saveDotTooltip() {
  if (this.loading) return 'Loading notebook…';
  if (this.saving) return 'Saving…';
  if (this.dirty) return 'Unsaved changes';
  if (this.lastSavedAt) return 'All changes saved';
  return 'No save state yet';
 },

 /**
  * Sprint 112.5 — colour class for the toolbar kernel dot.
  */
 kernelDotClass() {
  switch (this.kernelStatus) {
   case 'ready': return 'bg-success';
   case 'connecting': return 'bg-warning';
   case 'disconnected':
   case 'closed':
   default: return 'bg-secondary';
  }
 },

 /**
  * Tooltip for the toolbar kernel dot.
  */
 kernelDotTooltip() {
  switch (this.kernelStatus) {
   case 'ready': return 'Kernel ready';
   case 'connecting': return 'Kernel connecting…';
   case 'closed': return 'Kernel closed';
   default: return 'Kernel disconnected';
  }
 },

 /**
  * Sprint 112.5 — Activity section recent-runs feed.
  *
  * Bounded snapshot of the last five cell runs across the whole
  * notebook.  Each row carries cell index, label, status,
  * duration (ms), and a startedAt epoch-ms timestamp for
  * relative-time rendering.  The ring is appended to by
  * ``installKernelExecution``'s execute_reply handler and never
  * grows beyond ``_recentRunsRing.length`` cap of 5.
  */
 recentNotebookRuns() {
  return Array.isArray(this._recentRunsRing) ? this._recentRunsRing : [];
 },

 /**
  * Sprint 112.5 — derived "currently running" cell, if any.
  *
  * Reads the kernel-execution mixin's ``_runStartedAt`` map
  * (populated on ``execute_input`` iopub frame, cleared on
  * ``execute_reply``) and returns the matching cell + start
  * timestamp.  Returns ``null`` when no run is in flight.
  */
 currentlyRunningCell() {
  const starts = this._runStartedAt || {};
  for (const hash of Object.keys(starts)) {
   if (String(hash).startsWith('__pql_')) continue;
   const cell = this.cells.find((c) => c.content_hash === hash);
   if (cell) return { cell, startedAt: starts[hash] };
  }
  return null;
 },

 /**
  * Phase 107.2 — count of currently-open editor panels.
  *
  * Drives the toolbar's "Close all (N)" affordance, which surfaces
  * once ≥2 panels stack on top of each other.  Includes the
  * Phase-96 chat drawer even though it's fixed-position rather than
  * inline-stacked, so "Close all" maps to the user's "clear my
  * workspace" intent regardless of the underlying layout.
  *
  * Phase 112 — Tags / Branch / Access surfaces moved into the
  * right meta panel and no longer drive separate toggle panels,
  * so they drop from the count.  Revisions stays here because its
  * cell-diff drawer is still a wide overlay opened from the meta
  * panel's "See all & diff" button.
  */
 /**
  * Sprint 113.2 — toggle the unified right drawer to a specific
  * tab.  Re-clicking the toolbar button for the currently-open tab
  * closes the drawer (toggle semantics); clicking a different
  * toolbar button switches the tab without re-opening if the
  * drawer is already open (which it always is in that path).
  */
 openRightDrawer(tab) {
  const next = String(tab || 'chat');
  if (this.rightDrawer.open && this.rightDrawer.tab === next) {
   this.rightDrawer.open = false;
   return;
  }
  this.rightDrawer.tab = next;
  this.rightDrawer.open = true;
  if (next === 'variables' && typeof this.requestVariableSnapshot === 'function') {
   this.requestVariableSnapshot();
  }
 },

 openPanelCount() {
  let n = 0;
  if (this.jobsPanelOpen) n++;
  if (this.replays && this.replays.open) n++;
  if (this.sequenceProposals && this.sequenceProposals.open) n++;
  if (this.widgetsPanel && this.widgetsPanel.open) n++;
  if (this.revisions && this.revisions.open) n++;
  if (this.rightDrawer && this.rightDrawer.open) n++;
  return n;
 },

 closeAllPanels() {
  this.jobsPanelOpen = false;
  if (this.replays) this.replays.open = false;
  if (this.sequenceProposals) this.sequenceProposals.open = false;
  if (this.widgetsPanel) this.widgetsPanel.open = false;
  if (this.revisions) this.revisions.open = false;
  this.rightDrawer.open = false;
 },

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
 this.notebookUuid = res.data.notebook_uuid || null;
 this.cells = (res.data.cells || []).map((cell) => ({
 ...cell,
 _dirty: false,
 }));
 this.outputs = res.data.outputs || [];
 this.refreshCellCounts();
 this.loadCellAttributions();
 // Phase 98.C Wave-D — lineage badges read the same audit trail
 // and are cheap; loaded alongside attribution so the chip strip
 // paints on first render.
 this.loadCellLineageBulk();
 this._seedLiveOutputs();
 this.loading = false;
 // Wait one frame so Alpine's x-for has rendered the cell DOM,
 // then mount per-cell CodeMirror editors.
 await this.$nextTick();
 await this._mountAllEditors();
 this._renderAllOutputs();
 this._installKeymap();
 this._connectKernel();
 // Phase 105.3 — open the co-edit WebSocket once the notebook
 // UUID is known.  Passive scaffold: keeps a server-mirrored
 // Y.Doc warm + drives the toolbar live pill.  No editor
 // binding yet (lands in 105.3b after the 105.5 save-barrier).
 this._initCoedit();
 // Phase 96 — listen for chat-panel accept events so the
 // editor can apply proposed cell inserts / fixes.
 this._installChatProposalListener();
 // Phase 104 — listen for multi-cell sequence proposals so the
 // inbox surfaces them whether the drawer is open or not.
 this._installSequenceListener();
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
 this._removeChatProposalListener();
 this._removeSequenceListener();
 this._teardownCoedit();
 },
 };
 installJobsOrchestration(state);
 installKernelExecution(state, { computeContentHash: _computeContentHash });
 installCellOperations(state, { computeContentHash: _computeContentHash });
 installMarkdownOutput(state, { computeContentHash: _computeContentHash });
 installPersistence(state);
 installChatIntegration(state);
 installNotebookTags(state);
 installCellAuthorship(state);
 installCellLineage(state);
 installCellFacts(state);
 installRevisions(state);
 installShareDialog(state);
 installBranchBinding(state);
 installReplays(state);
 installSequenceProposals(state);
 installWidgetsPanel(state);
 installPermissionsPanel(state);
 installCoeditLifecycle(state, { userInfo: currentUser });
 return state;
}
