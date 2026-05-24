/**
 * Notebook editor — Persistence + cell-metadata mixin.
 *
 * Owns the keymap install (Cmd/Ctrl-S → save), notebook save
 * roundtrip, autosave debouncer, source-change handler, cell-label
 * formatter, params-tag toggle, and cell run-history fetch.
 * Extracted from ``notebook_editor.js`` in Phase 70.7.
 */

export function installPersistence(state) {
  state._installKeymap = function () {
    this._onKeydown = (ev) => {
      if (ev.key !== 's' && ev.key !== 'S') return;
      if (!(ev.metaKey || ev.ctrlKey)) return;
      ev.preventDefault();
      this.save();
    };
    window.addEventListener('keydown', this._onKeydown);
  };

  state.save = async function () {
    if (this.saving || this.mtimeConflict) return;
    this.saving = true;
    try {
      // translate ``placeholder_cell_id`` (transient
      // ordinal id the chat-integration mixin records when it
      // inserts a proposed cell) into the ``placeholder_index``
      // (position in the saved cells array) that the server's
      // reconciler can map to the final ``cell_uuid``.  For fix
      // proposals the target_cell_uuid is already stable and is
      // passed through as-is.
      const proposalAcceptances = (this._pendingProvenance || []).map(
        (acc) => {
          if (acc.action === 'propose' && acc.placeholder_cell_id) {
            const idx = this.cells.findIndex(
              (c) => c.id === acc.placeholder_cell_id,
            );
            return {
              proposal_id: acc.proposal_id,
              agent_run_id: acc.agent_run_id,
              action: acc.action,
              placeholder_index: idx,
            };
          }
          return {
            proposal_id: acc.proposal_id,
            agent_run_id: acc.agent_run_id,
            action: acc.action,
            target_cell_uuid: acc.target_cell_uuid || null,
          };
        },
      );
      const payload = {
        path: this.path,
        expected_mtime: this.mtime,
        cells: this.cells.map((cell) => ({
          cell_type: cell.cell_type,
          source: cell.source,
          result_var: cell.result_var || null,
          tags: Array.isArray(cell.tags) ? cell.tags : [],
          // surface the client-tracked cell_uuid so
          // the save-handler can detect Pass-3 reconciler mints and
          // broadcast a CRDT remap to every connected tab.  Cells
          // added in-session without a uuid send ``null``; the
          // reconciler will mint and return one.
          cell_uuid: cell.cell_uuid || null,
        })),
        proposal_acceptances: proposalAcceptances,
      };
      const res = await window.pqlApi.fetch('/api/notebooks/save', {
        method: 'POST',
        body: JSON.stringify(payload),
        headers: { 'Content-Type': 'application/json' },
        silent: true,
      });
      if (res.status === 409) {
        this.mtimeConflict = true;
        this.errorMessage = 'Notebook changed on disk — reload to see the latest version.';
        return;
      }
      if (!res.ok) {
        this.errorMessage =
          (res.data && res.data.detail) || `Save failed (HTTP ${res.status}).`;
        return;
      }
      const data = res.data || {};
      const updated = data.cells || [];
      for (let i = 0; i < this.cells.length; i++) {
        if (updated[i] && updated[i].content_hash) {
          this.cells[i].content_hash = updated[i].content_hash;
        }
        if (updated[i] && updated[i].cell_uuid) {
          this.cells[i].cell_uuid = updated[i].cell_uuid;
        }
        this.cells[i]._dirty = false;
      }
      this.mtime = data.mtime || this.mtime;
      if (data.notebook_uuid) {
        this.notebookUuid = data.notebook_uuid;
      }
      this.dirty = false;
      this.lastSavedAt = new Date();
      this.errorMessage = '';
      // clear the proposal-acceptance buffer on
      // successful save; provenance rows are now written.  Also
      // clear the per-cell ``_proposalPending`` markers so the
      // "from chat" chips fade.
      this._pendingProvenance = [];
      for (const c of this.cells) {
        if (c._proposalPending) delete c._proposalPending;
      }
      // refresh per-cell social counts post-save so the
      // chips reflect any cells that got minted UUIDs this round.
      this.refreshCellCounts();
      // refresh authorship envelopes too; the save just
      // upserted user-authorship for every cell.
      this.loadCellAttributions();
      // refresh per-cell lineage badges so a cell
      // that just ran a write-op surfaces it without a page reload.
      this.loadCellLineageBulk();
      // refresh per-cell pinned-fact chips for the
      // same reason (a cell whose content_hash changes loses its
      // pin badge and re-aligns to the new hash).
      this.loadCellFactsBulk();
    } catch (err) {
      this.errorMessage = (err && err.message) || String(err);
    } finally {
      this.saving = false;
    }
  };

  state._onCellSourceChange = function (cellId, value) {
    const cell = this.cells.find((c) => c.id === cellId);
    if (!cell) return;
    cell.source = value;
    cell._dirty = true;
    this.dirty = true;
    this._scheduleAutosave();
  };

  state._scheduleAutosave = function () {
    if (this._autosaveTimer) clearTimeout(this._autosaveTimer);
    this._autosaveTimer = setTimeout(() => {
      this._autosaveTimer = null;
      if (this.dirty && !this.saving && !this.mtimeConflict) this.save();
    }, 5000);
  };

  state.cellLabel = function (cell) {
    const tags = Array.isArray(cell.tags) ? cell.tags : [];
    if (tags.includes('parameters')) {
      if (cell.cell_type === 'sql') return 'SQL · PARAMS';
      if (cell.cell_type === 'markdown') return 'Markdown · PARAMS';
      return 'PARAMS';
    }
    if (cell.cell_type === 'sql') {
      return cell.result_var ? `SQL → ${cell.result_var}` : 'SQL';
    }
    if (cell.cell_type === 'markdown') return 'Markdown';
    return 'Code';
  };

  state.cellHasParamsTag = function (cell) {
    return Array.isArray(cell.tags) && cell.tags.includes('parameters');
  };

  state.toggleParamsTag = function (cell) {
    if (!cell) return;
    if (!Array.isArray(cell.tags)) cell.tags = [];
    const idx = cell.tags.indexOf('parameters');
    if (idx >= 0) cell.tags.splice(idx, 1);
    else cell.tags.push('parameters');
    cell._dirty = true;
    this.dirty = true;
    this._scheduleAutosave();
  };

  state.toggleHistoryFor = async function (cell) {
    if (this.historyOpenFor === cell.id) {
      this.historyOpenFor = null;
      return;
    }
    await this._fetchHistory(cell);
    this.historyOpenFor = cell.id;
  };

  state._fetchHistory = async function (cell) {
    try {
      const url =
        `/api/notebooks/cell-history?path=${encodeURIComponent(this.path)}` +
        `&content_hash=${encodeURIComponent(cell.content_hash)}&limit=5`;
      const res = await window.pqlApi.fetch(url, { silent: true });
      if (res.ok) {
        this._historyByCell[cell.id] = (res.data && res.data.runs) || [];
      } else {
        this._historyByCell[cell.id] = [];
      }
    } catch (_e) {
      this._historyByCell[cell.id] = [];
    }
  };

  state.historyForCell = function (cell) {
    return this._historyByCell[cell.id] || [];
  };
}
