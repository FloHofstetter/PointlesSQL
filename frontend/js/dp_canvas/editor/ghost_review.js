/*
 * Agent ghost-diff review for the canvas editor.
 *
 * Loads a proposed CanvasDoc (pasted or handed off via a ?propose= URL
 * param), diffs it against the live canvas through /canvas/ghost-diff, lets
 * the human accept or reject each change, then merges the accepted deltas
 * and saves.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const ghostReviewMethods = {
  // ---------------------------------------------------------------------
  // Agent ghost-diff review — load a proposed CanvasDoc, diff it against
  // the current canvas via /canvas/ghost-diff (read-only), let the human
  // accept or reject each change, then merge the accepted deltas and save.
  // The proposal source is a pasted doc or ``?propose=<base64-json>`` in
  // the URL (e.g. handed off from an agent run).
  // ---------------------------------------------------------------------

  openGhostReview() {
    this.ghost.open = true;
    // Auto-load a proposal handed off via the URL, if present.
    try {
      const raw = new URL(window.location.href).searchParams.get('propose');
      if (raw && !this.ghost.text) {
        this.ghost.text = decodeURIComponent(escape(window.atob(raw)));
      }
    } catch (_e) {
      // Malformed param — ignore, user can paste manually.
    }
  },
  closeGhostReview() {
    this.ghost.open = false;
  },
  async computeGhostDiff() {
    // Mutate ghost.* fields individually rather than replacing the whole
    // nested object — replacing it detaches some Alpine bindings and races
    // the x-for over ghost.errors.
    let proposed;
    try {
      proposed = JSON.parse(this.ghost.text);
    } catch (_e) {
      this.ghost.errors = [{ message: 'Proposal is not valid JSON.' }];
      return;
    }
    this.ghost.busy = true;
    this.ghost.proposed = proposed;
    this.ghost.diff = null;
    this.ghost.errors = [];
    const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/ghost-diff`, {
      method: 'POST',
      body: { proposed_document: proposed },
      silent: true,
    });
    this.ghost.busy = false;
    if (!res.ok) {
      this.ghost.errors = [{ message: res.error || 'ghost-diff failed' }];
      return;
    }
    // Default every change to accepted so "apply" with no fiddling takes
    // the whole proposal; the human unticks what they want to reject.
    const accept = {};
    const d = res.data.diff;
    for (const n of d.added_nodes) accept[`an:${n.id}`] = true;
    for (const n of d.removed_nodes) accept[`rn:${n.id}`] = true;
    for (const n of d.modified_nodes) accept[`mn:${n.id}`] = true;
    for (const e of d.added_edges) accept[`ae:${this._ghostEdgeKey(e)}`] = true;
    for (const e of d.removed_edges) accept[`re:${this._ghostEdgeKey(e)}`] = true;
    this.ghost.diff = d;
    this.ghost.errors = res.data.errors || [];
    this.ghost.accept = accept;
  },
  _ghostEdgeKey(e) {
    return `${e.source_node_id}:${e.source_pin}->${e.target_node_id}:${e.target_pin}`;
  },
  ghostDiffEmpty() {
    const d = this.ghost.diff;
    if (!d) return true;
    return (
      d.added_nodes.length +
        d.removed_nodes.length +
        d.modified_nodes.length +
        d.added_edges.length +
        d.removed_edges.length ===
      0
    );
  },
  async applyGhostSelection() {
    const d = this.ghost.diff;
    const proposed = this.ghost.proposed;
    if (!d || !proposed || !this.canWrite) return;
    const accept = this.ghost.accept;
    // Start from the live canvas; apply only the ticked deltas, taking
    // full node/edge objects (with positions) from the proposed doc.
    const current = this._buildDocument();
    const nodesById = {};
    for (const n of current.nodes) nodesById[n.id] = n;
    const propNodesById = {};
    for (const n of proposed.nodes) propNodesById[n.id] = n;
    for (const n of d.added_nodes) {
      if (accept[`an:${n.id}`] && propNodesById[n.id]) nodesById[n.id] = propNodesById[n.id];
    }
    for (const n of d.modified_nodes) {
      if (accept[`mn:${n.id}`] && propNodesById[n.id]) nodesById[n.id] = propNodesById[n.id];
    }
    for (const n of d.removed_nodes) {
      if (accept[`rn:${n.id}`]) delete nodesById[n.id];
    }
    const edgesByKey = {};
    for (const e of current.edges) edgesByKey[this._ghostEdgeKey(e)] = e;
    const propEdgesByKey = {};
    for (const e of proposed.edges) propEdgesByKey[this._ghostEdgeKey(e)] = e;
    for (const e of d.added_edges) {
      const k = this._ghostEdgeKey(e);
      if (accept[`ae:${k}`] && propEdgesByKey[k]) edgesByKey[k] = propEdgesByKey[k];
    }
    for (const e of d.removed_edges) {
      if (accept[`re:${this._ghostEdgeKey(e)}`]) delete edgesByKey[this._ghostEdgeKey(e)];
    }
    // Drop edges whose endpoints no longer exist after node removals.
    const merged = {
      schema_version: 1,
      nodes: Object.values(nodesById),
      edges: Object.values(edgesByKey).filter(
        (e) => nodesById[e.source_node_id] && nodesById[e.target_node_id]
      ),
      metadata: current.metadata || {},
    };
    this.ghost.busy = true;
    const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas`, {
      method: 'POST',
      body: { document: merged },
      silent: true,
    });
    this.ghost.busy = false;
    if (!res.ok) {
      this.ghost.errors = [{ message: res.error || 'apply failed' }];
      return;
    }
    this.version = res.data.version;
    this._suppressAutosave = true;
    this._loadIntoDrawflow(merged);
    this._suppressAutosave = false;
    this.saveState = 'saved';
    this.lastSavedAt = res.data.created_at;
    this.closeGhostReview();
    this._scheduleValidate();
    this.$nextTick(() => this.fitToView());
  },
};
