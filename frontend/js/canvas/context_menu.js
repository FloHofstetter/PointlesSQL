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
    // Mutually exclusive with the other canvas popovers.
    this._closeOutputPlusPicker();
    if (typeof this.closeInlinePeek === 'function') this.closeInlinePeek();
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
    const df = this._drawflow;
    const rect = df.container.getBoundingClientRect();
    // Keyboard-invoked context menus (Menu key / Shift+F10) carry
    // clientX/clientY 0,0, which would pin the menu to the window corner —
    // anchor those to the right-clicked element (or the stage) instead.
    let cx = ev.clientX;
    let cy = ev.clientY;
    if (!cx && !cy) {
      const anchor = (nodeEl || df.container).getBoundingClientRect();
      cx = anchor.left + Math.min(anchor.width / 2, 160);
      cy = anchor.top + Math.min(anchor.height / 2, 120);
    }
    // Keep the menu on the stage — a right-click near the drawer or the
    // bottom edge would otherwise open it half-hidden (or under the
    // drawer, which then swallows the clicks).
    cx = Math.min(cx, rect.right - 210);
    cy = Math.min(cy, rect.bottom - 150);
    // Stash the drop position (canvas-local) for "add block here".
    this._ctxDropPos = {
      x: (cx - rect.left - (df.canvas_x || 0)) / (df.zoom || 1),
      y: (cy - rect.top - (df.canvas_y || 0)) / (df.zoom || 1),
    };
    this.ctxMenu = { open: true, x: cx, y: cy, kind, nodeId, edgeId };
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
