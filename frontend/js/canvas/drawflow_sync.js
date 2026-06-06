/*
 * Drawflow <-> model synchronisation for the canvas editor.
 *
 * Loads a saved CanvasDoc into the Drawflow instance, mirrors Drawflow's
 * live graph back into the reactive `nodes`/`edges` maps (coalescing
 * drag-position updates through requestAnimationFrame), maps Drawflow node
 * ids to PQL node ids, and serialises the current graph back to a document
 * for save / validate / preview.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const drawflowSyncMethods = {
  // Single source of truth for spawning a block: add it to Drawflow, register
  // the df-id <-> pql-id mapping, and seed the reactive node entry.  The nine
  // creation flows (palette drop, output-plus, insert-on-edge, paste,
  // duplicate, and the delete/bulk-delete undo paths) differ only in the
  // config they pass and where they wire afterwards — they all funnel through
  // here.  Returns the Drawflow node id, or null when the block type is
  // unknown.  (_loadIntoDrawflow keeps its own addNode call: it places the
  // Drawflow node at ``pos || 100`` while storing the raw position, an
  // asymmetry this helper deliberately does not carry.)
  _spawnNode(blockType, pos, config, pqlId) {
    const def = this.catalog.BLOCK_DEFS[blockType];
    if (!def) return null;
    const dfId = this._drawflow.addNode(
      blockType,
      def.inputs || 0,
      def.outputs || 0,
      pos.x,
      pos.y,
      blockType,
      { pql_node_id: pqlId, block_type: blockType },
      this.catalog.nodeHtml(blockType, pqlId),
      false
    );
    this._drawflowNodes[pqlId] = dfId;
    this.nodes[pqlId] = { id: pqlId, block_type: blockType, config, position: pos };
    return dfId;
  },
  _loadIntoDrawflow(doc) {
    const df = this._drawflow;
    df.clear();
    this._drawflowNodes = {};
    this.nodes = {};
    this.edges = {};
    this.annotations = ((doc.metadata || {}).annotations || []).map((a) => ({
      ...a,
    }));
    // First pass: add nodes.
    for (const node of doc.nodes || []) {
      const def = this.catalog.BLOCK_DEFS[node.block_type];
      if (!def) continue;
      const pos = node.position || { x: 100, y: 100 };
      const dfId = df.addNode(
        node.block_type,
        def.inputs,
        def.outputs,
        pos.x || 100,
        pos.y || 100,
        node.block_type,
        { pql_node_id: node.id, block_type: node.block_type },
        this.catalog.nodeHtml(node.block_type, node.id),
        false
      );
      this._drawflowNodes[node.id] = dfId;
      this.nodes[node.id] = {
        id: node.id,
        block_type: node.block_type,
        config: { ...def.defaultConfig(), ...(node.config || {}) },
        position: pos,
      };
      this._refreshNodeBody(node.id);
    }
    // Second pass: add edges.
    for (const edge of doc.edges || []) {
      const sourceDf = this._drawflowNodes[edge.source_node_id];
      const targetDf = this._drawflowNodes[edge.target_node_id];
      if (!sourceDf || !targetDf) continue;
      const targetNode = (doc.nodes || []).find((n) => n.id === edge.target_node_id);
      const sourceIdx = 1; // Single-output blocks only.
      const targetIdx = this.catalog.pinIndexFor(
        targetNode ? targetNode.block_type : '',
        edge.target_pin,
        'in'
      );
      try {
        df.addConnection(sourceDf, targetDf, `output_${sourceIdx}`, `input_${targetIdx + 1}`);
      } catch (e) {
        // Connection target invalid (block schema mismatch with saved doc);
        // skip the edge — the validator will surface it later.
      }
    }
    this._syncFromDrawflow();
    this._scheduleDecorateAllConnections();
    this.$nextTick(() => {
      for (const pqlId of Object.keys(this.nodes)) this._renderOutputPlus(pqlId);
      // Loaded nodes are observed via the nodeCreated event, but run one
      // explicit observe + connection sweep here too: it catches any
      // layout settle (web-font swap, scrollbar) between addNode and the
      // first paint, and re-renders existing edges with the patched path.
      for (const dfId of Object.values(this._drawflowNodes)) this._observeNode(dfId);
      this._scheduleConnNodeUpdate();
    });
  },
  // Position-only handler: coalesced via requestAnimationFrame so a 60Hz
  // mousemove stream never triggers a full graph rebuild mid-drag.  The
  // node stays glued to the cursor; the structural sync (autosave,
  // validate, edge re-derive) stays on the connection / data-change paths.
  _onNodePositionChanged(dfId) {
    if (!this._dragDirtyDfIds) this._dragDirtyDfIds = new Set();
    this._dragDirtyDfIds.add(String(dfId));
    if (this._dragRafHandle != null) return;
    this._dragRafHandle = window.requestAnimationFrame(() => {
      this._dragRafHandle = null;
      this._flushDragPositions();
    });
  },
  _flushDragPositions() {
    const dirty = this._dragDirtyDfIds;
    if (!dirty || dirty.size === 0) return;
    this._dragDirtyDfIds = new Set();
    if (!this._drawflow) return;
    const raw = this._drawflow.export();
    const home = raw && raw.drawflow && raw.drawflow.Home;
    const dfNodes = (home && home.data) || {};
    for (const dfId of dirty) {
      const dfNode = dfNodes[dfId];
      if (!dfNode) continue;
      const pqlId = (dfNode.data || {}).pql_node_id;
      if (!pqlId || !this.nodes[pqlId]) continue;
      this.nodes[pqlId].position = { x: dfNode.pos_x, y: dfNode.pos_y };
    }
    if (!this._suppressAutosave) {
      this._scheduleAutosave();
    }
    this._scheduleMinimapRender();
    this._scheduleRerouteOrthogonal();
  },
  _syncFromDrawflow() {
    if (!this._drawflow) return;
    const raw = this._drawflow.export();
    const home = raw && raw.drawflow && raw.drawflow.Home;
    const dfNodes = (home && home.data) || {};
    const newNodes = {};
    const newEdges = {};
    const reverseId = {};

    for (const [dfId, dfNode] of Object.entries(dfNodes)) {
      const data = dfNode.data || {};
      const pqlId = data.pql_node_id;
      if (!pqlId) continue;
      reverseId[dfId] = pqlId;
      const existing = this.nodes[pqlId];
      newNodes[pqlId] = {
        id: pqlId,
        block_type: data.block_type,
        config: existing
          ? existing.config
          : (
              this.catalog.BLOCK_DEFS[data.block_type] || { defaultConfig: () => ({}) }
            ).defaultConfig(),
        position: { x: dfNode.pos_x, y: dfNode.pos_y },
      };
    }
    this._drawflowNodes = {};
    for (const [dfId, pqlId] of Object.entries(reverseId)) {
      this._drawflowNodes[pqlId] = parseInt(dfId, 10);
    }

    // Edges.
    for (const [dfId, dfNode] of Object.entries(dfNodes)) {
      const pqlSourceId = reverseId[dfId];
      if (!pqlSourceId) continue;
      const outputs = dfNode.outputs || {};
      for (const [outputName, outputData] of Object.entries(outputs)) {
        const conns = (outputData && outputData.connections) || [];
        for (const conn of conns) {
          const pqlTargetId = reverseId[conn.node];
          if (!pqlTargetId) continue;
          const sourcePin = 'out';
          const targetIdx = parseInt((conn.output || '').replace('input_', ''), 10) - 1;
          const targetBlock = newNodes[pqlTargetId] ? newNodes[pqlTargetId].block_type : '';
          const targetPin = this.catalog.inputPinName(targetBlock, targetIdx);
          const sourceOutputIdx = parseInt((outputName || '').replace('output_', ''), 10);
          if (!Number.isFinite(sourceOutputIdx)) continue;
          const edgeId = `e-${pqlSourceId}:${sourcePin}->${pqlTargetId}:${targetPin}`;
          newEdges[edgeId] = {
            id: edgeId,
            source_node_id: pqlSourceId,
            source_pin: sourcePin,
            target_node_id: pqlTargetId,
            target_pin: targetPin,
          };
        }
      }
    }

    this.nodes = newNodes;
    this.edges = newEdges;
    // O(1) lookup from a connection SVG's `node_out_node-<src>` /
    // `node_in_node-<tgt>` dfId pair to the canonical edge id.  Rebuilt
    // each sync so hover, click-select and category styling don't each
    // re-scan all nodes × edges per connection.
    this._edgeByDfIds = {};
    for (const edge of Object.values(newEdges)) {
      const srcDf = this._drawflowNodes[edge.source_node_id];
      const tgtDf = this._drawflowNodes[edge.target_node_id];
      if (srcDf != null && tgtDf != null) {
        this._edgeByDfIds[`${srcDf}|${tgtDf}`] = edge.id;
      }
    }
    if (this.selectedNodeId && !newNodes[this.selectedNodeId]) {
      this.selectedNodeId = null;
    }
    // Output-plus visibility tracks outgoing-edge presence; refresh
    // every source node after the edge dict settles so a freshly
    // connected pin hides its plus and a freshly disconnected one
    // un-hides.  Cheap idempotent loop — _renderOutputPlus reuses
    // the existing handle and only updates style.display.
    for (const pqlId of Object.keys(newNodes)) this._renderOutputPlus(pqlId);
    if (!this._suppressAutosave) {
      this._scheduleAutosave();
      this._scheduleValidate();
    }
  },
  _onDrawflowNodeSelected(dfId) {
    for (const [pqlId, mappedDfId] of Object.entries(this._drawflowNodes)) {
      if (String(mappedDfId) === String(dfId)) {
        this.selectedNodeId = pqlId;
        return;
      }
    }
    this.selectedNodeId = null;
  },
  _pqlIdForDfId(dfId) {
    for (const [pqlId, mappedDfId] of Object.entries(this._drawflowNodes)) {
      if (String(mappedDfId) === String(dfId)) return pqlId;
    }
    return null;
  },
  _buildDocument() {
    return {
      schema_version: 1,
      nodes: Object.values(this.nodes).map((node) => ({
        id: node.id,
        block_type: node.block_type,
        config: node.config,
        position: node.position,
      })),
      edges: Object.values(this.edges).map((edge) => ({
        id: edge.id,
        source_node_id: edge.source_node_id,
        source_pin: edge.source_pin,
        target_node_id: edge.target_node_id,
        target_pin: edge.target_pin,
      })),
      metadata: { annotations: this.annotations || [] },
    };
  },
};
