/*
 * Node lifecycle operations for the canvas editor.
 *
 * Palette drag-and-drop, delete / duplicate of the selected node (each with
 * an undo command), focus-and-centre, auto-layout tidy, and the
 * sensible-defaults pass that seeds a freshly wired block's config from its
 * upstream columns.  onConfigChanged() is the shared autosave + revalidate
 * trigger the config forms call after every edit.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

import { generateNodeId } from './_render_helpers.js';

export const nodeOpsMethods = {
  onPaletteDragStart(event, kind) {
    if (!this.canWrite) {
      event.preventDefault();
      return;
    }
    event.dataTransfer.setData('text/plain', kind);
    event.dataTransfer.effectAllowed = 'copy';
  },
  onCanvasDrop(event) {
    if (!this.canWrite) return;
    const kind = event.dataTransfer.getData('text/plain');
    if (!kind || !this.catalog.BLOCK_DEFS[kind]) return;
    const def = this.catalog.BLOCK_DEFS[kind];
    const rect = event.currentTarget.getBoundingClientRect();
    const pos = { x: event.clientX - rect.left - 60, y: event.clientY - rect.top - 30 };
    const pqlId = generateNodeId();
    this._spawnNode(kind, pos, def.defaultConfig(), pqlId);
    this._refreshNodeBody(pqlId);
    this._renderOutputPlus(pqlId);
    this._scheduleAutosave();
    this._scheduleValidate();
    this._pushCommand({
      do: () => {
        // Re-create requires re-mint of df-id; punt and just call drop logic
        // recursively from the snapshot.  For simplicity the redo just no-ops
        // when the node already exists.
        if (this.nodes[pqlId]) return;
        this._spawnNode(kind, pos, def.defaultConfig(), pqlId);
      },
      undo: () => {
        const cur = this._drawflowNodes[pqlId];
        if (cur != null) this._drawflow.removeNodeId('node-' + cur);
        delete this._drawflowNodes[pqlId];
        delete this.nodes[pqlId];
        if (this.selectedNodeId === pqlId) this.selectedNodeId = null;
      },
    });
    this._scheduleMinimapRender();
  },
  deleteSelectedNode() {
    if (!this.selectedNodeId || !this.canWrite) return;
    const pqlId = this.selectedNodeId;
    const snapshotNode = this.nodes[pqlId]
      ? {
          id: pqlId,
          block_type: this.nodes[pqlId].block_type,
          config: JSON.parse(JSON.stringify(this.nodes[pqlId].config || {})),
          position: { ...(this.nodes[pqlId].position || { x: 100, y: 100 }) },
        }
      : null;
    const snapshotEdges = Object.values(this.edges).filter(
      (e) => e.source_node_id === pqlId || e.target_node_id === pqlId
    );
    const dfId = this._drawflowNodes[pqlId];
    if (dfId) this._drawflow.removeNodeId('node-' + dfId);
    delete this._drawflowNodes[pqlId];
    delete this.nodes[pqlId];
    this.selectedNodeId = null;
    this._syncFromDrawflow();
    if (snapshotNode) {
      this._pushCommand({
        do: () => {
          const cur = this._drawflowNodes[pqlId];
          if (cur != null) this._drawflow.removeNodeId('node-' + cur);
          delete this._drawflowNodes[pqlId];
          delete this.nodes[pqlId];
          this._syncFromDrawflow();
        },
        undo: () => {
          const def = this.catalog.BLOCK_DEFS[snapshotNode.block_type];
          if (!def) return;
          this._suppressAutosave = true;
          this._spawnNode(
            snapshotNode.block_type,
            snapshotNode.position,
            snapshotNode.config,
            pqlId
          );
          for (const e of snapshotEdges) {
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
    }
    this._scheduleMinimapRender();
  },
  duplicateSelectedNode() {
    if (!this.selectedNodeId || !this.canWrite) return;
    const src = this.nodes[this.selectedNodeId];
    if (!src) return;
    const def = this.catalog.BLOCK_DEFS[src.block_type];
    if (!def) return;
    const newPqlId = generateNodeId();
    const pos = {
      x: (src.position?.x || 100) + 40,
      y: (src.position?.y || 100) + 40,
    };
    this._spawnNode(src.block_type, pos, JSON.parse(JSON.stringify(src.config || {})), newPqlId);
    this._refreshNodeBody(newPqlId);
    this.selectedNodeId = newPqlId;
    this._scheduleAutosave();
    this._scheduleValidate();
    this._pushCommand({
      do: () => {
        // No-op: redo re-adds the duplicate would need full re-clone path.
        // For simplicity, redo of duplicate is best-effort no-op.
      },
      undo: () => {
        const cur = this._drawflowNodes[newPqlId];
        if (cur != null) this._drawflow.removeNodeId('node-' + cur);
        delete this._drawflowNodes[newPqlId];
        delete this.nodes[newPqlId];
        if (this.selectedNodeId === newPqlId) this.selectedNodeId = null;
        this._syncFromDrawflow();
      },
    });
    this._scheduleMinimapRender();
  },
  focusNode(nodeId) {
    if (!nodeId) return;
    const dfId = this._drawflowNodes[nodeId];
    if (!dfId) return;
    this.selectedNodeId = nodeId;
    // Drawflow exposes no public selectNodeById; centring requires
    // poking into its module-local state. Selecting via the DOM
    // click handler is the least-invasive equivalent.
    const el = this._drawflow.container.querySelector(`#node-${dfId}`);
    if (el && typeof el.click === 'function') el.click();
  },
  _applySensibleDefaultsIfEmpty(nodeId) {
    const node = this.nodes[nodeId];
    if (!node) return;
    const upstream = this.upstreamColumns(nodeId, 'in');
    if (upstream.length === 0) return;
    const cfg = node.config || {};
    switch (node.block_type) {
      case 'Sort':
        if (!cfg.order_by || cfg.order_by.length === 0) {
          cfg.order_by = [{ column: upstream[0], direction: 'asc' }];
          node.config = cfg;
        }
        break;
      case 'Project':
        if (!cfg.columns || cfg.columns.length === 0) {
          cfg.columns = upstream.slice(0, 3);
          node.config = cfg;
        }
        break;
      case 'GroupBy':
        if (!cfg.keys || cfg.keys.length === 0) {
          cfg.keys = [upstream[0]];
          node.config = cfg;
        }
        break;
      default:
        return;
    }
    this._refreshNodeBody(nodeId);
  },
  async autoTidy() {
    const df = this._drawflow;
    if (!df) return;
    const { computeLayout, animateTo } = await import('./_auto_layout.js');
    const nodes = Object.values(this.nodes);
    const edges = Object.values(this.edges);
    if (nodes.length === 0) return;
    const targets = computeLayout(nodes, edges, { rankdir: 'LR' });
    if (!targets || Object.keys(targets).length === 0) return;
    const currentPos = {};
    for (const n of nodes) currentPos[n.id] = n.position || { x: 100, y: 100 };
    this._suppressAutosave = true;
    await animateTo(df, this._drawflowNodes, currentPos, targets, 250);
    // Persist final positions into the editor state.
    for (const [pqlId, pos] of Object.entries(targets)) {
      if (this.nodes[pqlId]) this.nodes[pqlId].position = { x: pos.x, y: pos.y };
    }
    this._suppressAutosave = false;
    this._scheduleAutosave();
    this._scheduleMinimapRender();
  },
  onConfigChanged() {
    if (this.selectedNodeId) this._refreshNodeBody(this.selectedNodeId);
    if (this._suppressAutosave) return;
    this._scheduleAutosave();
    this._scheduleValidate();
  },
};
