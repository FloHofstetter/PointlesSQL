/**
 * Notebook editor — Cell-management mixin.
 *
 * Owns add / delete / move / convert operations on the cell list,
 * including the per-cell ``cellEditor`` lifecycle (mount, destroy,
 * re-mount on type change). Extracted from ``notebook_editor.js``
 * in Phase 70.6.
 */

import { cellEditor } from './cell_editor.js';

export function installCellOperations(state, deps) {
  const computeContentHash = deps.computeContentHash;

  state._nextCellOrdinal = function () {
    let max = -1;
    for (const cell of this.cells) {
      const m = /^cell-(\d+)$/.exec(cell.id || '');
      if (m) {
        const n = parseInt(m[1], 10);
        if (Number.isFinite(n) && n > max) max = n;
      }
    }
    return max + 1;
  };

  state._makeBlankCell = async function (cellType = 'code') {
    const ordinal = this._nextCellOrdinal();
    const source = '';
    return {
      id: `cell-${ordinal}`,
      content_hash: await computeContentHash(source),
      cell_type: cellType,
      source: source,
      result_var: null,
      _dirty: false,
      exec_count: null,
      status: null,
    };
  };

  state._insertCellAt = async function (index, cell) {
    this.cells.splice(index, 0, cell);
    this.dirty = true;
    await this.$nextTick();
    const host = document.getElementById(`pql-cell-host-${cell.id}`);
    if (host && !this._editors[cell.id]) {
      const editor = cellEditor({
        initialSource: cell.source,
        language:
          cell.cell_type === 'sql'
            ? 'sql'
            : cell.cell_type === 'markdown'
            ? 'markdown'
            : 'python',
        onSourceChange: (value) => this._onCellSourceChange(cell.id, value),
      });
      this._editors[cell.id] = editor;
      await editor.mount(host);
    }
  };

  state.addCellAbove = async function (cell, cellType = 'code') {
    const idx = this.cells.findIndex((c) => c.id === cell.id);
    if (idx < 0) return;
    const fresh = await this._makeBlankCell(cellType);
    await this._insertCellAt(idx, fresh);
  };

  state.addCellBelow = async function (cell, cellType = 'code') {
    const idx = this.cells.findIndex((c) => c.id === cell.id);
    const insertAt = idx < 0 ? this.cells.length : idx + 1;
    const fresh = await this._makeBlankCell(cellType);
    await this._insertCellAt(insertAt, fresh);
  };

  state.addCellAtEnd = async function (cellType = 'code') {
    const fresh = await this._makeBlankCell(cellType);
    await this._insertCellAt(this.cells.length, fresh);
  };

  state.deleteCell = function (cell) {
    const idx = this.cells.findIndex((c) => c.id === cell.id);
    if (idx < 0) return;
    const editor = this._editors[cell.id];
    if (editor) {
      editor.destroy();
      delete this._editors[cell.id];
    }
    delete this._liveOutputs[cell.content_hash];
    delete this._runStatus[cell.content_hash];
    this.cells.splice(idx, 1);
    this.dirty = true;
  };

  state._moveCell = async function (cell, delta) {
    const idx = this.cells.findIndex((c) => c.id === cell.id);
    if (idx < 0) return;
    const target = idx + delta;
    if (target < 0 || target >= this.cells.length) return;
    const [removed] = this.cells.splice(idx, 1);
    this.cells.splice(target, 0, removed);
    this.dirty = true;
  };

  state.moveCellUp = async function (cell) {
    await this._moveCell(cell, -1);
  };

  state.moveCellDown = async function (cell) {
    await this._moveCell(cell, +1);
  };

  state.convertCellType = async function (cell, newType) {
    if (cell.cell_type === newType) return;
    const editor = this._editors[cell.id];
    const source = editor ? editor.getSource() : cell.source;
    if (editor) {
      editor.destroy();
      delete this._editors[cell.id];
    }
    cell.cell_type = newType;
    cell.source = source;
    cell.content_hash = await computeContentHash(source);
    cell.result_var = newType === 'sql' ? cell.result_var : null;
    cell.exec_count = null;
    cell.status = null;
    delete this._liveOutputs[cell.content_hash];
    cell._dirty = true;
    this.dirty = true;
    await this.$nextTick();
    const host = document.getElementById(`pql-cell-host-${cell.id}`);
    if (host) {
      const fresh = cellEditor({
        initialSource: source,
        language:
          newType === 'sql' ? 'sql' : newType === 'markdown' ? 'markdown' : 'python',
        onSourceChange: (value) => this._onCellSourceChange(cell.id, value),
      });
      this._editors[cell.id] = fresh;
      host.dataset.pqlCellInit = '';
      host.innerHTML = '';
      await fresh.mount(host);
    }
  };
}
