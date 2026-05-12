/**
 * Notebook editor — Markdown + Output-rendering mixin.
 *
 * Owns output frame seeding (``_seedLiveOutputs``), output rendering
 * (``_renderCellOutput``, ``_renderAllOutputs``,
 * ``_outputContainerFor``), per-cell editor mounting
 * (``_mountAllEditors``), and the markdown edit/view toggle
 * (``_renderMarkdown``, ``enterMarkdownEdit``,
 * ``exitMarkdownEdit``). Extracted from ``notebook_editor.js``
 * in Phase 70.7.
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
