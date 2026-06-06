/*
 * Multi-selection and clipboard for the canvas editor.
 *
 * Shift-click multi-select styling, bulk delete (one undo command for the
 * whole set), and copy / paste of a node+edge sub-graph through
 * localStorage so a selection survives reloads and tabs.  Pasted nodes get
 * fresh ids and a +40px offset.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

import { generateNodeId } from './_render_helpers.js';

export const clipboardMethods = {
  _clearMultiSelection() {
    if (this.multiSelectedNodeIds.length === 0) return;
    this.multiSelectedNodeIds = [];
    this._refreshMultiSelectStyles();
  },
  _refreshMultiSelectStyles() {
    const df = this._drawflow;
    if (!df) return;
    const selected = new Set(this.multiSelectedNodeIds);
    for (const [pqlId, dfId] of Object.entries(this._drawflowNodes)) {
      const el = df.container.querySelector(`#node-${dfId}`);
      if (!el) continue;
      el.classList.toggle('pql-node-selected-multi', selected.has(pqlId));
    }
  },
  async bulkDeleteSelected() {
    const ids = [...this.multiSelectedNodeIds];
    if (ids.length === 0) return;
    const ok = window.confirm(`Delete ${ids.length} blocks?`);
    if (!ok) return;
    const df = this._drawflow;
    if (!df) return;
    const set = new Set(ids);
    const removedNodes = ids
      .map((id) => this.nodes[id])
      .filter(Boolean)
      .map((n) => ({
        id: n.id,
        block_type: n.block_type,
        config: JSON.parse(JSON.stringify(n.config || {})),
        position: { ...(n.position || { x: 100, y: 100 }) },
      }));
    const removedEdges = Object.values(this.edges).filter(
      (e) => set.has(e.source_node_id) || set.has(e.target_node_id)
    );
    this._suppressAutosave = true;
    for (const pqlId of ids) {
      const dfId = this._drawflowNodes[pqlId];
      if (dfId != null) df.removeNodeId('node-' + dfId);
    }
    this._suppressAutosave = false;
    this.multiSelectedNodeIds = [];
    this._syncFromDrawflow();
    this._pushCommand({
      do: () => {
        // Re-apply the delete (re-resolve current drawflow ids by pql_id).
        for (const n of removedNodes) {
          const cur = this._drawflowNodes[n.id];
          if (cur != null) this._drawflow.removeNodeId('node-' + cur);
          delete this._drawflowNodes[n.id];
          delete this.nodes[n.id];
        }
        this._syncFromDrawflow();
      },
      undo: () => {
        // Re-create nodes + re-wire edges that were within the deleted set.
        this._suppressAutosave = true;
        for (const n of removedNodes) {
          const def = this.catalog.BLOCK_DEFS[n.block_type];
          if (!def) continue;
          this._spawnNode(n.block_type, n.position, n.config, n.id);
        }
        for (const e of removedEdges) {
          const sd = this._drawflowNodes[e.source_node_id];
          const td = this._drawflowNodes[e.target_node_id];
          if (sd == null || td == null) continue;
          const targetIdx = this.catalog.pinIndexFor(
            this.nodes[e.target_node_id]?.block_type,
            e.target_pin,
            'in'
          );
          try {
            this._drawflow.addConnection(sd, td, 'output_1', `input_${targetIdx + 1}`);
          } catch (_e) {
            // Skip.
          }
        }
        this._suppressAutosave = false;
        this._syncFromDrawflow();
      },
    });
    this._scheduleMinimapRender();
  },
  copySelectionToClipboard() {
    const ids =
      this.multiSelectedNodeIds.length > 0
        ? [...this.multiSelectedNodeIds]
        : this.selectedNodeId
          ? [this.selectedNodeId]
          : [];
    if (ids.length === 0) return;
    const set = new Set(ids);
    const nodes = ids
      .map((id) => this.nodes[id])
      .filter(Boolean)
      .map((n) => ({
        id: n.id,
        block_type: n.block_type,
        config: JSON.parse(JSON.stringify(n.config || {})),
        position: { ...(n.position || { x: 100, y: 100 }) },
      }));
    const edges = Object.values(this.edges).filter(
      (e) => set.has(e.source_node_id) && set.has(e.target_node_id)
    );
    const payload = { kind: 'pql-canvas-clipboard', version: 1, nodes, edges };
    try {
      window.localStorage.setItem('pql-canvas-clipboard', JSON.stringify(payload));
    } catch (_e) {
      // Quota / disabled — silent.
    }
  },
  pasteClipboard() {
    let payload = null;
    try {
      const raw = window.localStorage.getItem('pql-canvas-clipboard');
      if (raw) payload = JSON.parse(raw);
    } catch (_e) {
      return;
    }
    if (!payload || payload.kind !== 'pql-canvas-clipboard' || !Array.isArray(payload.nodes)) {
      return;
    }
    const df = this._drawflow;
    if (!df) return;
    const idMap = {};
    this._suppressAutosave = true;
    for (const n of payload.nodes) {
      const def = this.catalog.BLOCK_DEFS[n.block_type];
      if (!def) continue;
      const newId = generateNodeId();
      idMap[n.id] = newId;
      const pos = {
        x: (n.position && n.position.x ? n.position.x : 100) + 40,
        y: (n.position && n.position.y ? n.position.y : 100) + 40,
      };
      this._spawnNode(n.block_type, pos, JSON.parse(JSON.stringify(n.config || {})), newId);
    }
    for (const e of payload.edges || []) {
      const srcNew = idMap[e.source_node_id];
      const tgtNew = idMap[e.target_node_id];
      if (!srcNew || !tgtNew) continue;
      const srcDf = this._drawflowNodes[srcNew];
      const tgtDf = this._drawflowNodes[tgtNew];
      if (!srcDf || !tgtDf) continue;
      const targetIdx = this.catalog.pinIndexFor(this.nodes[tgtNew].block_type, e.target_pin, 'in');
      try {
        df.addConnection(srcDf, tgtDf, 'output_1', `input_${targetIdx + 1}`);
      } catch (_e) {
        // Skip invalid wire.
      }
    }
    this._suppressAutosave = false;
    this._syncFromDrawflow();
    const pastedIds = Object.values(idMap);
    if (pastedIds.length > 0) {
      this._pushCommand({
        do: () => {
          // Best-effort re-paste: re-invoke from the clipboard payload.
          this.pasteClipboard();
        },
        undo: () => {
          for (const newId of pastedIds) {
            const dfId = this._drawflowNodes[newId];
            if (dfId != null) this._drawflow.removeNodeId('node-' + dfId);
            delete this._drawflowNodes[newId];
            delete this.nodes[newId];
          }
          this._syncFromDrawflow();
        },
      });
    }
    this._scheduleMinimapRender();
  },
};
