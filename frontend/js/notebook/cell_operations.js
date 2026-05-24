/**
 * Notebook editor — Cell-management mixin.
 *
 * Owns add / delete / move / convert operations on the cell list,
 * including the per-cell ``cellEditor`` lifecycle (mount, destroy,
 * re-mount on type change). Extracted from ``notebook_editor.js``
 * .
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

  state._moveCellTo = async function (fromIdx, toIdx, { broadcast = true } = {}) {
    if (fromIdx === toIdx) return;
    if (fromIdx < 0 || fromIdx >= this.cells.length) return;
    if (toIdx < 0 || toIdx >= this.cells.length) return;
    const cell = this.cells[fromIdx];
    this.cells.splice(fromIdx, 1);
    this.cells.splice(toIdx, 0, cell);
    this.dirty = true;
    // mirror the reorder onto the shared Y.Array so
    // peer tabs converge without waiting for the save round-trip.
    // ``broadcast=false`` is used by the live-drag preview in
    // ``cell_dnd.js`` so peers see ONLY the final position once
    // ``drop`` fires, not every intermediate splice.
    if (broadcast && typeof this._syncCellsOrderToYDoc === 'function') {
      this._syncCellsOrderToYDoc(cell);
    }
  };

  state._moveCell = async function (cell, delta) {
    const idx = this.cells.findIndex((c) => c.id === cell.id);
    if (idx < 0) return;
    await this._moveCellTo(idx, idx + delta);
  };

  state.moveCellUp = async function (cell) {
    await this._moveCell(cell, -1);
  };

  state.moveCellDown = async function (cell) {
    await this._moveCell(cell, +1);
  };

  /**
   * insert a cell drafted by the AI assistant.
   *
   * Called by the chat-integration mixin after an accept on a
   * ``propose`` proposal.  Inserts the cell either after the
   * targeted UUID, at the end of the notebook, or — when both
   * locators are missing — at the end as a safe fallback.  Marks
   * the cell with ``_proposalPending`` so the next save flushes a
   * provenance acceptance for it (the save-path reconciler then
   * mints the final cell_uuid).
   */
  state.insertCellFromProposal = async function ({
    afterCellUuid,
    atEnd,
    cellType,
    source,
    proposalId,
    agentRunId,
  }) {
    const ordinal = this._nextCellOrdinal();
    const newCell = {
      id: `cell-${ordinal}`,
      content_hash: await computeContentHash(source || ''),
      cell_uuid: null,
      cell_type: cellType === 'markdown' ? 'markdown' : 'code',
      source: source || '',
      result_var: null,
      tags: [],
      _dirty: true,
      exec_count: null,
      status: null,
      _proposalPending: { proposalId, agentRunId, action: 'propose' },
    };
    let insertAt = this.cells.length;
    if (afterCellUuid) {
      const idx = this.cells.findIndex((c) => c.cell_uuid === afterCellUuid);
      if (idx >= 0) insertAt = idx + 1;
    } else if (!atEnd) {
      // Neither locator → still safe-default to end.
      insertAt = this.cells.length;
    }
    await this._insertCellAt(insertAt, newCell);
    this._pendingProvenance = this._pendingProvenance || [];
    this._pendingProvenance.push({
      proposal_id: proposalId,
      agent_run_id: agentRunId,
      action: 'propose',
      placeholder_cell_id: newCell.id,
    });
    return newCell;
  };

  /**
   * apply an accepted ``fix`` proposal to an existing cell.
   *
   * Finds the cell by stable ``cell_uuid``, replaces its source,
   * re-renders the CodeMirror editor, marks the cell dirty, and
   * records a pending provenance acceptance for the next save.
   */
  state.updateCellSourceByUuid = async function (
    cellUuid,
    newSource,
    { proposalId, agentRunId },
  ) {
    const cell = this.cells.find((c) => c.cell_uuid === cellUuid);
    if (!cell) return null;
    cell.source = newSource;
    cell.content_hash = await computeContentHash(newSource);
    cell._dirty = true;
    cell._proposalPending = { proposalId, agentRunId, action: 'fix' };
    this.dirty = true;
    const editor = this._editors[cell.id];
    if (editor && typeof editor.setSource === 'function') {
      editor.setSource(newSource);
    }
    this._pendingProvenance = this._pendingProvenance || [];
    this._pendingProvenance.push({
      proposal_id: proposalId,
      agent_run_id: agentRunId,
      action: 'fix',
      target_cell_uuid: cellUuid,
    });
    return cell;
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
