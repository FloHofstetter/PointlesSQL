/*
 * Right-click context menu for the canvas editor.
 *
 * Target-aware menu (node / edge / empty canvas) that reuses the existing
 * duplicate / delete / preview / peek / delete-edge / insert-on-edge
 * actions, plus "add block here" which opens the block picker at the
 * cursor.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const contextMenuMethods = {
  // ---------------------------------------------------------------------
  // Right-click context menu — target-aware, reuses existing actions.
  // ---------------------------------------------------------------------

  _onCanvasContextMenu(ev) {
    const nodeEl = ev.target.closest('.drawflow-node');
    const connEl = ev.target.closest('.connection');
    ev.preventDefault();
    let kind = 'canvas';
    let nodeId = null;
    let edgeId = null;
    if (nodeEl) {
      kind = 'node';
      const m = nodeEl.id && nodeEl.id.match(/^node-(\d+)$/);
      const dfId = m ? parseInt(m[1], 10) : null;
      for (const [pql, df] of Object.entries(this._drawflowNodes)) {
        if (df === dfId) {
          nodeId = pql;
          break;
        }
      }
      if (nodeId) this.selectedNodeId = nodeId;
    } else if (connEl) {
      kind = 'edge';
      edgeId = this._edgeIdForSvg(connEl);
    }
    // Stash the drop position (canvas-local) for "add block here".
    const df = this._drawflow;
    const rect = df.container.getBoundingClientRect();
    this._ctxDropPos = {
      x: (ev.clientX - rect.left - (df.canvas_x || 0)) / (df.zoom || 1),
      y: (ev.clientY - rect.top - (df.canvas_y || 0)) / (df.zoom || 1),
    };
    this.ctxMenu = { open: true, x: ev.clientX, y: ev.clientY, kind, nodeId, edgeId };
  },
  closeContextMenu() {
    this.ctxMenu = { ...this.ctxMenu, open: false };
  },
  ctxAction(action) {
    const { kind, nodeId, edgeId } = this.ctxMenu;
    this.closeContextMenu();
    if (action === 'add') {
      // Open the existing block picker at the cursor; _pickOutputPlusBlock
      // drops a standalone node at the stashed drop position.
      if (!this.canWrite) return;
      this._insertOnEdgeContext = null;
      this.outputPlusPicker = {
        open: true,
        x: this.ctxMenu.x - (this.$refs.canvas.parentElement.getBoundingClientRect().left || 0),
        y: this.ctxMenu.y - (this.$refs.canvas.parentElement.getBoundingClientRect().top || 0),
        sourcePqlId: null,
      };
      return;
    }
    if (kind === 'node' && nodeId) {
      this.selectedNodeId = nodeId;
      if (action === 'duplicate') this.duplicateSelectedNode();
      else if (action === 'delete') this.deleteSelectedNode();
      else if (action === 'preview') this.openPreviewForSelected();
      else if (action === 'peek') {
        const dfId = this._drawflowNodes[nodeId];
        const el = dfId != null && this._drawflow.container.querySelector(`#node-${dfId}`);
        this.openInlinePeek(nodeId, el || null);
      }
    } else if (kind === 'edge' && edgeId) {
      if (action === 'deleteEdge') this.deleteEdgeById(edgeId);
      else if (action === 'insert') this.insertBlockOnEdge(edgeId);
    }
  },
};
