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
      if (this.inspectorOpen) this.requestVariableSnapshot();
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

  state.toggleInspector = function () {
    this.inspectorOpen = !this.inspectorOpen;
    if (this.inspectorOpen) this.requestVariableSnapshot();
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
