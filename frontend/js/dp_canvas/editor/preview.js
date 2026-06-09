/*
 * Data preview for the canvas editor.
 *
 * The compact inline peek popover anchored at a node, the full preview
 * modal (with cache-bust), the upstream-column lookup that feeds the
 * CodeMirror predicate / SQL editors, and the lazy mounts for those
 * editors.  All read-only against the /canvas/preview endpoint.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const previewMethods = {
  // ---------------------------------------------------------------------
  // Inline preview peek — a compact popover at a node showing the first
  // few output rows, reusing the same /canvas/preview endpoint as the
  // full modal but capped tight.
  // ---------------------------------------------------------------------

  async openInlinePeek(nodeId, anchorEl) {
    if (!nodeId) return;
    // Mutually exclusive with the other canvas popovers.
    this.closeContextMenu();
    this._closeOutputPlusPicker();
    const stage = this.$refs.canvas.parentElement;
    const sr = stage.getBoundingClientRect();
    const ar = (anchorEl || this.$refs.canvas).getBoundingClientRect();
    this.inlinePeek = {
      open: true,
      x: ar.right - sr.left + 8,
      y: ar.top - sr.top,
      nodeId,
      loading: true,
      columns: [],
      rows: [],
    };
    try {
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/preview`, {
        method: 'POST',
        body: { document: this._buildDocument(), upto_node_id: nodeId, limit: 5 },
        silent: true,
      });
      if (!this.inlinePeek.open || this.inlinePeek.nodeId !== nodeId) return;
      if (res.ok && res.data) {
        this.inlinePeek = {
          ...this.inlinePeek,
          loading: false,
          columns: res.data.columns || [],
          rows: (res.data.rows || []).slice(0, 5),
        };
      } else {
        this.inlinePeek = { ...this.inlinePeek, loading: false };
      }
    } catch (_e) {
      this.inlinePeek = { ...this.inlinePeek, loading: false };
    }
  },
  closeInlinePeek() {
    this.inlinePeek = { ...this.inlinePeek, open: false };
  },
  async mountPredicateCm(host, nodeId, field) {
    await this._mountCmEditor(host, nodeId, field, false);
  },
  async mountSqlCm(host, nodeId, field) {
    await this._mountCmEditor(host, nodeId, field, true);
  },
  // CodeMirror loads from the CDN import map, which can take seconds on a
  // cold cache and fails outright on an offline / CDN-blocked host.  Both
  // cases used to leave a silent empty box where the predicate / SQL field
  // should be — show a loading placeholder while the import is in flight
  // and degrade to a plain editable field when it never arrives, so the
  // block stays configurable no matter what.
  async _mountCmEditor(host, nodeId, field, multiLine) {
    if (!host) return;
    const node = this.nodes[nodeId];
    if (!node) return;
    const onChange = (value) => {
      const live = this.nodes[nodeId];
      if (!live) return;
      if ((live.config[field] || '') === value) return;
      live.config[field] = value;
      this.onConfigChanged();
    };
    const placeholder = document.createElement('div');
    placeholder.className = 'pql-canvas-cm-loading text-muted small';
    placeholder.textContent = 'Loading editor…';
    host.appendChild(placeholder);
    try {
      const { mountPredicateEditor, mountSqlEditor } = await import('../codemirror_predicate.js');
      const mount = multiLine ? mountSqlEditor : mountPredicateEditor;
      await mount(host, {
        initialValue: String((node.config && node.config[field]) || ''),
        onChange,
        getColumns: () => this.upstreamColumns(nodeId, 'in'),
      });
    } catch (_e) {
      const fallback = document.createElement(multiLine ? 'textarea' : 'input');
      fallback.className = 'form-control form-control-sm font-monospace';
      if (multiLine) fallback.rows = 6;
      fallback.value = String((node.config && node.config[field]) || '');
      fallback.addEventListener('input', () => onChange(fallback.value));
      host.appendChild(fallback);
      const note = document.createElement('div');
      note.className = 'form-text small text-warning-emphasis';
      note.textContent = 'Rich editor unavailable — using a plain field.';
      host.appendChild(note);
    } finally {
      placeholder.remove();
    }
  },
  upstreamColumns(nodeId, pinName) {
    // Walk reverse edges to find the upstream node feeding *pinName*,
    // then return its output PinSchema columns (if cached).
    for (const edge of Object.values(this.edges)) {
      if (edge.target_node_id === nodeId && edge.target_pin === pinName) {
        const key = `${edge.source_node_id}:${edge.source_pin}`;
        const schema = this.pinSchemas[key];
        if (schema && Array.isArray(schema.columns)) {
          return schema.columns.map((c) => c.name);
        }
      }
    }
    return [];
  },
  canPreviewSelected() {
    const node = this.selectedNode;
    if (!node) return false;
    if (node.block_type === 'OutputPort') return false;
    return true;
  },
  openPreviewForSelected() {
    if (!this.canPreviewSelected()) return;
    this.previewNodeId = this.selectedNodeId;
    this.previewOpen = true;
    this.previewResult = null;
    this.previewError = null;
    // Auto-fire on open so the user sees rows without an extra click.
    this.runPreview();
  },
  closePreviewModal() {
    this.previewOpen = false;
  },
  async runPreview(opts = {}) {
    if (this.previewBusy) return;
    if (!this.previewNodeId) return;
    this.previewBusy = true;
    this.previewError = null;
    // Marching-ants on every edge whose target is upstream of the
    // preview-target node — i.e. the path the executor is walking.
    this._setRunningEdges(this._edgesUpstreamOf(this.previewNodeId));
    const bust = opts.bust ? '?bust=1' : '';
    try {
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/preview${bust}`, {
        method: 'POST',
        body: {
          document: this._buildDocument(),
          upto_node_id: this.previewNodeId,
          limit: this.previewLimit,
        },
        silent: true,
      });
      this.previewBusy = false;
      if (!res.ok) {
        this.previewError = res.error || 'Preview failed';
        return;
      }
      this.previewResult = res.data;
      if (this.previewNodeId && res.data && typeof res.data.row_count === 'number') {
        this.previewRowCountByNode[this.previewNodeId] = res.data.row_count;
        this._refreshAllNodeBodies();
      }
    } finally {
      this.previewBusy = false;
      this._setRunningEdges(new Set());
    }
  },
};
