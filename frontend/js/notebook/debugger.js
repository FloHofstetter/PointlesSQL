/**
 * Notebook editor — step-through debugger mixin.
 *
 * Drives the Jupyter Debug Protocol (debugpy via ipykernel) for one
 * cell at a time: dump the cell source into the kernel, set
 * breakpoints by line number, run the cell, and react to ``stopped``
 * events by loading the stack trace + scope variables of the paused
 * frame.  All DAP requests travel through the kernel WebSocket's
 * ``debug`` JSON-RPC method; DAP *events* arrive asynchronously as
 * ``debug_event`` notifies routed to `_onDebugEvent`.
 *
 * The DAP ``seq`` / ``type`` envelope fields are stamped server-side
 * by the kernel session (the single sequence authority across tabs
 * sharing one kernel), so `buildDapRequest` deliberately omits them.
 *
 * Breakpoints are entered as comma-separated 1-based line numbers in
 * the debug panel rather than via a CodeMirror gutter click — the
 * per-cell editor builds its extension list once at mount with no
 * reconfiguration hooks, and visible gutter markers would need a
 * state-field extension threaded through the shared editor factory.
 *
 * Pure helpers (`parseBreakpointLines`, `buildDapRequest`,
 * `mapStackFrames`, `mapScopes`, `mapVariables`) are exported for
 * direct unit testing under node:test.
 */

/**
 * Parse a comma/whitespace-separated breakpoint string into sorted,
 * de-duplicated, positive 1-based line numbers.
 *
 * @param {string} text - Raw input, e.g. ``"2, 5,5  9"``.
 * @returns {Array<number>} Sorted unique line numbers, e.g. [2, 5, 9].
 */
export function parseBreakpointLines(text) {
  if (typeof text !== 'string') return [];
  const out = new Set();
  for (const part of text.split(/[,\s]+/)) {
    if (!part) continue;
    const n = Number(part);
    if (Number.isInteger(n) && n > 0) out.add(n);
  }
  return Array.from(out).sort((a, b) => a - b);
}

/**
 * Build the DAP request content for one command.
 *
 * ``type: "request"`` is included for wire-shape clarity; the kernel
 * session overwrites both ``type`` and ``seq`` server-side.
 *
 * @param {string} command - DAP command name (``debugInfo``, …).
 * @param {Object} [args] - DAP ``arguments`` payload.
 * @returns {{type: string, command: string, arguments: Object}}
 */
export function buildDapRequest(command, args = {}) {
  return { type: 'request', command: String(command), arguments: args || {} };
}

/**
 * Map a DAP ``stackTrace`` response body to panel-friendly frames.
 *
 * @param {Object} body - ``debug_reply`` body with ``stackFrames``.
 * @returns {Array<{id: number, name: string, line: number|null, source: string}>}
 */
export function mapStackFrames(body) {
  const frames = body && Array.isArray(body.stackFrames) ? body.stackFrames : [];
  return frames.map((f) => ({
    id: f.id,
    name: f.name || '(unknown)',
    line: f.line != null ? f.line : null,
    source: (f.source && (f.source.name || f.source.path)) || '',
  }));
}

/**
 * Map a DAP ``scopes`` response body to ``{name, variablesReference}``.
 *
 * @param {Object} body - ``debug_reply`` body with ``scopes``.
 * @returns {Array<{name: string, variablesReference: number, expensive: boolean}>}
 */
export function mapScopes(body) {
  const scopes = body && Array.isArray(body.scopes) ? body.scopes : [];
  return scopes.map((s) => ({
    name: s.name || '',
    variablesReference: s.variablesReference || 0,
    expensive: !!s.expensive,
  }));
}

/**
 * Map a DAP ``variables`` response body to one display level of
 * ``{name, type, value}`` rows.  Nested ``variablesReference``
 * expansion is intentionally not offered — the panel shows one level.
 *
 * @param {Object} body - ``debug_reply`` body with ``variables``.
 * @returns {Array<{name: string, type: string, value: string}>}
 */
export function mapVariables(body) {
  const vars = body && Array.isArray(body.variables) ? body.variables : [];
  return vars
    .filter((v) => v && typeof v.name === 'string')
    .map((v) => ({
      name: v.name,
      type: v.type || '',
      value: v.value != null ? String(v.value) : '',
    }));
}

/**
 * Install the debugger surface onto the notebook editor state.
 *
 * State slots are declared here (not in the coordinator) so the
 * feature stays one cohesive module:
 *
 * * ``debugActive`` — a debug session is attached and a cell ran
 *   under it; stepping buttons render.
 * * ``debugBusy`` — a DAP round-trip is in flight; guards re-entry.
 * * ``debugPanelOpen`` — panel visibility.
 * * ``debugCellHash`` — content_hash of the cell being debugged.
 * * ``breakpointInput`` / ``breakpointLines`` — raw text + parsed
 *   lines for the current debug run.
 * * ``stopped`` — ``null`` while running; on pause carries
 *   ``{threadId, frames, scopes, variables, frameId}``.
 *
 * @param {Object} state - The notebook editor Alpine state object.
 */
export function installNotebookDebugger(state) {
  state.debugActive = false;
  state.debugBusy = false;
  state.debugPanelOpen = false;
  state.debugCellHash = null;
  state.breakpointInput = '';
  state.breakpointLines = [];
  state.stopped = null;
  state._debugTargetCellId = null;

  // --- plumbing -------------------------------------------------------

  state._debugRequest = async function (command, args = {}) {
    if (!this._kernel || this._kernel.readyState !== WebSocket.OPEN) {
      throw new Error('Kernel not connected.');
    }
    const res = await this._kernel.debug(buildDapRequest(command, args));
    const reply = (res && res.reply) || {};
    if (reply.success === false) {
      throw new Error(reply.message || `debug command ${command} failed`);
    }
    return reply;
  };

  // --- panel entry ----------------------------------------------------

  state.openDebugger = function (cell) {
    if (!cell) return;
    this._debugTargetCellId = cell.id;
    this.debugPanelOpen = true;
  };

  state.debugTargetCell = function () {
    if (this._debugTargetCellId == null) return null;
    return this.cells.find((c) => c.id === this._debugTargetCellId) || null;
  };

  state.closeDebugPanel = async function () {
    // Stop first so closing the panel can never leave the kernel
    // wedged at a breakpoint with no visible affordance to resume.
    if (this.debugActive) await this.debugStop();
    this.debugPanelOpen = false;
  };

  // Refresh the target cell's source + hash from its editor, parse
  // the breakpoint input, and hand off to ``debugCell``.
  state.startDebugCell = async function () {
    const cell = this.debugTargetCell();
    if (!cell || cell.cell_type !== 'code') {
      this.errorMessage = 'Debugger: pick a Python code cell first.';
      return;
    }
    const fresh = await this._refreshCellHash(cell);
    const lines = parseBreakpointLines(this.breakpointInput);
    await this.debugCell(fresh.contentHash, fresh.source, lines);
  };

  // --- core DAP flow --------------------------------------------------

  state.debugCell = async function (contentHash, source, lines) {
    if (this.debugBusy) return;
    if (!this._kernel || this._kernel.readyState !== WebSocket.OPEN) {
      this.errorMessage = 'Kernel not connected.';
      return;
    }
    this.debugBusy = true;
    try {
      const info = await this._debugRequest('debugInfo', {});
      if (!(info.body && info.body.isStarted)) {
        await this._debugRequest('initialize', {
          clientID: 'pointlessql',
          clientName: 'PointlesSQL notebook',
          adapterID: 'debugpy',
          locale: 'en',
          linesStartAt1: true,
          columnsStartAt1: true,
          pathFormat: 'path',
        });
        await this._debugRequest('attach', {});
      }
      const dump = await this._debugRequest('dumpCell', { code: source });
      const sourcePath = dump.body && dump.body.sourcePath;
      if (!sourcePath) throw new Error('Debugger: dumpCell returned no sourcePath.');
      await this._debugRequest('setBreakpoints', {
        source: { path: sourcePath },
        breakpoints: lines.map((line) => ({ line })),
        sourceModified: false,
      });
      await this._debugRequest('configurationDone', {});
      this.debugActive = true;
      this.debugCellHash = contentHash;
      this.breakpointLines = lines;
      this.stopped = null;
      // Run the cell through the normal execute path so outputs,
      // run-history and persistence behave exactly like a plain run.
      await this._kernel.execute(contentHash, source, { cellType: 'code' });
    } catch (e) {
      this.errorMessage = (e && e.message) || String(e);
    } finally {
      this.debugBusy = false;
    }
  };

  // --- event handling -------------------------------------------------

  state._onDebugEvent = function (params) {
    const content = params && params.content;
    if (!content || typeof content !== 'object') return;
    if (content.event === 'stopped') {
      const threadId = content.body && content.body.threadId;
      if (threadId != null) this._onDebugStopped(threadId);
      return;
    }
    if (content.event === 'continued') {
      this.stopped = null;
    }
  };

  state._onDebugStopped = async function (threadId) {
    try {
      const st = await this._debugRequest('stackTrace', { threadId });
      const frames = mapStackFrames(st.body);
      this.stopped = { threadId, frames, scopes: [], variables: [], frameId: null };
      if (frames.length > 0) await this.debugSelectFrame(frames[0].id);
    } catch (e) {
      this.errorMessage = (e && e.message) || String(e);
    }
  };

  state.debugSelectFrame = async function (frameId) {
    if (!this.stopped) return;
    try {
      const sc = await this._debugRequest('scopes', { frameId });
      const scopes = mapScopes(sc.body);
      // Prefer the cheap scope (debugpy marks "Globals" expensive in
      // cell frames); fall back to whatever the adapter offered.
      const primary = scopes.find((s) => !s.expensive) || scopes[0] || null;
      let variables = [];
      if (primary && primary.variablesReference) {
        const v = await this._debugRequest('variables', {
          variablesReference: primary.variablesReference,
        });
        variables = mapVariables(v.body);
      }
      this.stopped = { ...this.stopped, frameId, scopes, variables };
    } catch (e) {
      this.errorMessage = (e && e.message) || String(e);
    }
  };

  // --- stepping -------------------------------------------------------

  state._debugStep = async function (command) {
    if (!this.stopped) return;
    const threadId = this.stopped.threadId;
    // Optimistically clear: the next ``stopped`` event repopulates.
    this.stopped = null;
    try {
      await this._debugRequest(command, { threadId });
    } catch (e) {
      this.errorMessage = (e && e.message) || String(e);
    }
  };

  state.debugContinue = function () {
    return this._debugStep('continue');
  };

  state.debugNext = function () {
    return this._debugStep('next');
  };

  state.debugStepIn = function () {
    return this._debugStep('stepIn');
  };

  state.debugStepOut = function () {
    return this._debugStep('stepOut');
  };

  state.debugStop = async function () {
    try {
      if (this.stopped) {
        // Resume first so disconnect never leaves the kernel paused
        // inside the user's cell.
        await this._debugRequest('continue', { threadId: this.stopped.threadId });
      }
      await this._debugRequest('disconnect', {
        restart: false,
        terminateDebuggee: false,
      });
    } catch (e) {
      this.errorMessage = (e && e.message) || String(e);
    } finally {
      this.debugActive = false;
      this.stopped = null;
      this.debugCellHash = null;
      this.breakpointLines = [];
    }
  };
}
