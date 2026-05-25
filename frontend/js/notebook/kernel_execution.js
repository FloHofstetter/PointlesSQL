/**
 * Notebook editor — Kernel-execution mixin.
 *
 * Owns the WebSocket connection to the per-notebook ipykernel
 * subprocess, the cell-run lifecycle (``runCell``,
 * ``runCellAndAdvance``, ``interruptKernel``, ``restartKernel``),
 * and the iopub-frame dispatcher (``_onKernelFrame``).
 *
 * Variable-inspector probes + frame handlers live in the sibling
 * `variable_inspector.js` module; this installer composes them in so
 * the dispatcher can call `this.requestVariableSnapshot()` and the
 * kernel-client can route variable frames to `this._onVariableSnapshot`
 * / `_onVariableDetail` on the same state object.
 *
 * The mixin depends on ``createKernelClient`` and ``renderOutputFrame``
 * being already imported by the coordinator; methods reach them via
 * the closure rather than re-importing here, so the module stays a
 * pure behavior-installer.
 */

import { createKernelClient } from './kernel_ws.js';
import { renderOutputFrame } from './output_renderer.js';
import { installVariableInspector } from './variable_inspector.js';

/**
 * @typedef {Object} KernelExecutionSlots
 * State + methods attached by ``installKernelExecution``.  Composes
 * with {@link import('./variable_inspector.js').VariableInspectorSlots}
 * because the installer calls ``installVariableInspector(state)`` first
 * so the iopub-frame dispatcher can reach the variable handlers.
 *
 * @property {boolean} runAllInProgress
 * @property {() => void} _connectKernel
 * @property {(frame: Object) => void} _onKernelFrame
 * @property {(cell: Object) => Promise<void>} runCell
 * @property {(cell: Object) => Promise<string>} _refreshCellHash
 * @property {() => Promise<void>} interruptKernel
 * @property {(cell: Object) => Promise<void>} runCellAndAdvance
 * @property {(from: number, to: number) => Promise<void>} runRange
 * @property {() => Promise<void>} runAllCells
 * @property {(cell: Object) => Promise<void>} runAllAbove
 * @property {(cell: Object) => Promise<void>} runAllBelow
 * @property {() => void} cancelRunAll
 * @property {() => Promise<void>} restartKernel
 */

export function installKernelExecution(state, deps) {
  const computeContentHash = deps.computeContentHash;

  // Install variable-inspector surface first so the kernel-client
  // wiring below can reference its frame handlers via `this`.
  installVariableInspector(state);

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
        // stamp run-start for wall-clock duration display.
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
      // finalise wall-clock duration. Use the iopub-time
      // start stamped earlier; if missing (race or pre-mixin frame)
      // skip silently rather than report a bogus value.
      const startedAt = this._runStartedAt[hash];
      let durationMs = null;
      if (startedAt != null) {
        durationMs = performance.now() - startedAt;
        this._runDurationMs[hash] = durationMs;
        delete this._runStartedAt[hash];
      }
      // push the run onto the bounded ring buffer
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
      // ``_ih`` / ``_oh`` indefinitely (caught during replay testing).
      if (this.inspectorOpen && !String(hash).startsWith('__pql_')) {
        this.requestVariableSnapshot();
      }
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

  // bulk-run helpers (Run all / Run above / Run below).
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
