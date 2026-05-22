/**
 * Notebook editor — Kernel-execution mixin.
 *
 * Owns the WebSocket connection to the per-notebook ipykernel
 * subprocess, the cell-run lifecycle (``runCell``,
 * ``runCellAndAdvance``, ``interruptKernel``, ``restartKernel``),
 * the iopub-frame dispatcher (``_onKernelFrame``), and the
 * Variable Inspector helpers. Extracted from ``notebook_editor.js``
 * in Phase 70.5.
 *
 * The mixin depends on ``createKernelClient`` and ``renderOutputFrame``
 * being already imported by the coordinator; methods reach them via
 * the closure rather than re-importing here, so the module stays a
 * pure behavior-installer.
 */

import { createKernelClient } from './kernel_ws.js';
import { renderOutputFrame } from './output_renderer.js';

export function installKernelExecution(state, deps) {
  const computeContentHash = deps.computeContentHash;

  state._connectKernel = function () {
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
      onVariableSnapshot: (params) => this._onVariableSnapshot(params),
      onVariableDetail: (params) => this._onVariableDetail(params),
    });
    this._kernel.connect();
  };

  state._onVariableSnapshot = function (params) {
    const payload = params && params.payload;
    if (Array.isArray(payload)) this.inspectorVars = payload;
  };

  state._onVariableDetail = function (params) {
    const payload = params && params.payload;
    if (payload && typeof payload === 'object') {
      this.inspectorDetail = payload;
      this.inspectorDetailFor = payload.name || null;
    }
  };

  state._onKernelFrame = function (frame) {
    if (!frame || typeof frame !== 'object') return;
    const hash = frame.content_hash;
    if (!hash) return;
    const cell = this.cells.find((c) => c.content_hash === hash);
    if (frame.channel === 'iopub') {
      const msgType = frame.msg_type;
      if (msgType === 'status') {
        if (cell) {
          const execState = (frame.content && frame.content.execution_state) || '';
          if (execState === 'busy') this._runStatus[hash] = 'running';
          else if (execState === 'idle' && this._runStatus[hash] === 'running') {
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
        // Phase 94: stamp run-start for wall-clock duration display.
        this._runStartedAt[hash] = performance.now();
        this._runDurationMs[hash] = null;
        if (cell) this._renderCellOutput(cell);
        return;
      }
      if (
        msgType === 'stream' ||
        msgType === 'execute_result' ||
        msgType === 'display_data' ||
        msgType === 'error'
      ) {
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
      // Phase 94: finalise wall-clock duration. Use the iopub-time
      // start stamped earlier; if missing (race or pre-mixin frame)
      // skip silently rather than report a bogus value.
      const startedAt = this._runStartedAt[hash];
      let durationMs = null;
      if (startedAt != null) {
        durationMs = performance.now() - startedAt;
        this._runDurationMs[hash] = durationMs;
        delete this._runStartedAt[hash];
      }
      // Sprint 112.5 — push the run onto the bounded ring buffer
      // that drives the meta panel's Activity section.  Skip the
      // ``__pql_*`` synthetic probes (variable inspector etc.)
      // since they are not user-visible cells.
      if (cell && !String(hash).startsWith('__pql_') && Array.isArray(this._recentRunsRing)) {
        const idx = this.cells.findIndex((c) => c.id === cell.id);
        const labelSrc = (cell.source || '').replace(/\s+/g, ' ').trim();
        const label = labelSrc.length > 48 ? `${labelSrc.slice(0, 48)}…` : labelSrc;
        this._recentRunsRing.unshift({
          cellId: cell.id,
          cellIndex: idx >= 0 ? idx + 1 : null,
          cellType: cell.cell_type,
          label: label || '(empty)',
          status: status || 'ok',
          execCount: execCount != null ? execCount : null,
          durationMs,
          finishedAt: Date.now(),
        });
        if (this._recentRunsRing.length > 5) {
          this._recentRunsRing.length = 5;
        }
      }
      // Auto-refresh the variable inspector only for user-driven runs.
      // The inspector's own probe carries ``__pql_vars__`` /
      // ``__pql_vardetail__`` as content_hash, and refreshing on its
      // own reply spins an unbounded loop that grew IPython's
      // ``_ih`` / ``_oh`` indefinitely (caught Phase 105 replay).
      if (this.inspectorOpen && !String(hash).startsWith('__pql_')) {
        this.requestVariableSnapshot();
      }
    }
  };

  state.requestVariableSnapshot = function () {
    if (!this._kernel || this.kernelStatus !== 'ready') return;
    try {
      this._kernel
        .execute('__pql_vars__', '__pql_inspect__()', {
          cellType: 'code',
          silent: true,
        })
        .catch(() => {
          /* swallow — fail-quiet for inspector refresh */
        });
    } catch {
      /* WS not ready — ignore */
    }
  };

  state.requestVariableDetail = async function (name) {
    if (!this._kernel || this.kernelStatus !== 'ready') return;
    if (!name) return;
    const safe = String(name).replace(/[^A-Za-z0-9_]/g, '');
    if (!safe) return;
    try {
      await this._kernel.execute(
        '__pql_vardetail__',
        `__pql_inspect_detail__('${safe}')`,
        { cellType: 'code', silent: true },
      );
    } catch {
      /* fail-quiet */
    }
  };

  // Sprint 113.2 — inspector visibility moved onto the unified
  // right drawer.  Kept as a thin alias for legacy callers.
  state.toggleInspector = function () {
    if (typeof this.openRightDrawer === 'function') {
      this.openRightDrawer('variables');
    }
  };

  state.runCell = async function (cell) {
    if (!cell) return;
    if (!this._kernel || this._kernel.readyState !== WebSocket.OPEN) {
      this.errorMessage = 'Kernel not connected.';
      return;
    }
    if (cell.cell_type === 'markdown') return;
    const fresh = await this._refreshCellHash(cell);
    try {
      await this._kernel.execute(fresh.contentHash, fresh.source, {
        cellType: cell.cell_type,
        resultVar: cell.result_var || null,
      });
    } catch (e) {
      this.errorMessage = (e && e.message) || String(e);
    }
  };

  state._refreshCellHash = async function (cell) {
    const editor = this._editors[cell.id];
    const source = editor ? editor.getSource() : cell.source;
    const newHash = await computeContentHash(source);
    if (newHash !== cell.content_hash) {
      this._liveOutputs[newHash] = this._liveOutputs[cell.content_hash] || [];
      delete this._liveOutputs[cell.content_hash];
      cell.content_hash = newHash;
    }
    cell.source = source;
    return { contentHash: newHash, source: source };
  };

  state.interruptKernel = async function () {
    if (!this._kernel) return;
    try {
      await this._kernel.interrupt();
    } catch (e) {
      this.errorMessage = (e && e.message) || String(e);
    }
  };

  state.runCellAndAdvance = async function (cell) {
    await this.runCell(cell);
    const idx = this.cells.findIndex((c) => c.id === cell.id);
    if (idx < 0) return;
    if (idx === this.cells.length - 1) {
      await this.addCellAtEnd('code');
    } else {
      const next = this.cells[idx + 1];
      if (next && this._editors[next.id]) this._editors[next.id].focus();
    }
  };

  // Phase 113.6 — bulk-run helpers (Run all / Run above / Run below).
  // Cells are awaited sequentially so a downstream cell sees the
  // kernel state left by upstream cells (the Jupyter default).
  // Markdown cells are skipped silently.  Errors halt the run so the
  // user can fix the failing cell before continuing — also matches
  // Jupyter's "Run All" default.
  state.runAllInProgress = false;

  state.runRange = async function (from, to) {
    if (!this._kernel || this._kernel.readyState !== WebSocket.OPEN) {
      this.errorMessage = 'Kernel not connected.';
      return;
    }
    if (this.runAllInProgress) return;
    const start = Math.max(0, from | 0);
    const end = Math.min(this.cells.length, to | 0);
    if (end <= start) return;
    this.runAllInProgress = true;
    try {
      for (let i = start; i < end; i++) {
        if (!this.runAllInProgress) break;
        const cell = this.cells[i];
        if (!cell || cell.cell_type === 'markdown') continue;
        try {
          await this.runCell(cell);
        } catch (e) {
          this.errorMessage = (e && e.message) || String(e);
          break;
        }
      }
    } finally {
      this.runAllInProgress = false;
    }
  };

  state.runAllCells = async function () {
    await this.runRange(0, this.cells.length);
  };

  state.runAllAbove = async function (cell) {
    const idx = this.cells.findIndex((c) => c.id === cell.id);
    if (idx <= 0) return;
    await this.runRange(0, idx);
  };

  state.runAllBelow = async function (cell) {
    const idx = this.cells.findIndex((c) => c.id === cell.id);
    if (idx < 0) return;
    await this.runRange(idx, this.cells.length);
  };

  // Toolbar split-button variants — operate on the currently focused
  // cell (``_focusedCellId``, set by ``@focusin`` on each editor host).
  state.runAllAboveFocused = async function () {
    const cell = this.focusedCell();
    if (!cell) return;
    await this.runAllAbove(cell);
  };

  state.runAllBelowFocused = async function () {
    const cell = this.focusedCell();
    if (!cell) return;
    await this.runAllBelow(cell);
  };

  state.focusedCell = function () {
    if (!this._focusedCellId) return null;
    return this.cells.find((c) => c.id === this._focusedCellId) || null;
  };

  state.focusedCellIndex = function () {
    if (!this._focusedCellId) return -1;
    return this.cells.findIndex((c) => c.id === this._focusedCellId);
  };

  state.cancelRunAll = function () {
    this.runAllInProgress = false;
  };

  state.restartKernel = async function () {
    if (!this._kernel) return;
    try {
      await this._kernel.restart();
      this._liveOutputs = {};
      this._runStatus = {};
      this._renderAllOutputs();
    } catch (e) {
      this.errorMessage = (e && e.message) || String(e);
    }
  };
}
