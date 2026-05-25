/**
 * Notebook editor — Markdown + Output-rendering mixin.
 *
 * Owns output frame seeding (``_seedLiveOutputs``), output rendering
 * (``_renderCellOutput``, ``_renderAllOutputs``,
 * ``_outputContainerFor``), per-cell editor mounting
 * (``_mountAllEditors``), and the markdown edit/view toggle
 * (``_renderMarkdown``, ``enterMarkdownEdit``,
 * ``exitMarkdownEdit``). Extracted from ``notebook_editor.js``
 * .
 */

import { cellEditor } from './cell_editor.js';
import { renderOutputFrame } from './output_renderer.js';

export function installMarkdownOutput(state, deps) {
  const computeContentHash = deps.computeContentHash;

  state._seedLiveOutputs = function () {
    this._liveOutputs = {};
    for (const out of this.outputs) {
      const hash = out.content_hash;
      if (!hash) continue;
      if (!this._liveOutputs[hash]) this._liveOutputs[hash] = [];
      this._liveOutputs[hash].push(out);
    }
  };

  state._outputContainerFor = function (cell) {
    return document.getElementById(`pql-cell-output-${cell.id}`);
  };

  state._renderCellOutput = function (cell) {
    const host = this._outputContainerFor(cell);
    if (!host) return;
    host.innerHTML = '';
    const frames = this._liveOutputs[cell.content_hash] || [];
    for (const frame of frames) {
      host.appendChild(renderOutputFrame(frame));
    }
  };

  state._renderAllOutputs = function () {
    for (const cell of this.cells) {
      this._renderCellOutput(cell);
    }
  };

  /**
   * clear the rendered output frames + run duration for
   * a single cell without re-running it.
   *
   * Drops the live-output buffer keyed by ``content_hash`` and clears
   * the DOM container.  The cell's ``exec_count`` stays as-is so the
   * Out[N] label and run-history are still meaningful.  A subsequent
   * ``runCell`` call will re-populate the live outputs from fresh
   * iopub frames.
   */
  state._clearOutput = function (cell) {
    if (!cell || !cell.content_hash) return;
    delete this._liveOutputs[cell.content_hash];
    delete this._runDurationMs[cell.content_hash];
    delete this._runStartedAt[cell.content_hash];
    const host = this._outputContainerFor(cell);
    if (host) host.innerHTML = '';
  };

  state._mountAllEditors = async function () {
    const promises = this.cells.map(async (cell) => {
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
        // resolve the y-codemirror.next binding when
        // the coedit client is synced and the cell carries a stable
        // uuid; ``cellYBinding`` returns null otherwise and the
        // editor falls back to standalone CodeMirror.
        yBinding: typeof this.cellYBinding === 'function' ? this.cellYBinding(cell) : null,
      });
      this._editors[cell.id] = editor;
      await editor.mount(host);
    });
    await Promise.all(promises);
  };

  state._renderMarkdown = async function (cell) {
    try {
      const res = await window.pqlApi.fetch('/api/notebooks/render-markdown', {
        method: 'POST',
        body: JSON.stringify({ source: cell.source || '' }),
        headers: { 'Content-Type': 'application/json' },
        silent: true,
      });
      if (res.ok) {
        cell._renderedHtml = (res.data && res.data.html) || '';
      } else {
        cell._renderedHtml = '<em>Failed to render markdown.</em>';
      }
    } catch (err) {
      cell._renderedHtml = `<em>${(err && err.message) || String(err)}</em>`;
    }
  };

  state.enterMarkdownEdit = async function (cell) {
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
      // markdown cells join co-edit through the same
      // shared Y.Doc map as code/sql cells; the language extension
      // differs but the binding is identical.
      yBinding: typeof this.cellYBinding === 'function' ? this.cellYBinding(cell) : null,
    });
    this._editors[cell.id] = editor;
    host.dataset.pqlCellInit = '';
    host.innerHTML = '';
    await editor.mount(host);
    editor.focus();
  };

  state.exitMarkdownEdit = async function (cell) {
    if (cell.cell_type !== 'markdown') return;
    const editor = this._editors[cell.id];
    if (editor) {
      cell.source = editor.getSource();
      cell.content_hash = await computeContentHash(cell.source);
      editor.destroy();
      delete this._editors[cell.id];
    }
    await this._renderMarkdown(cell);
    cell.view_mode = true;
  };
}
