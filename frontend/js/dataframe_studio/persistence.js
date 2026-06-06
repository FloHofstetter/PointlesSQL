/*
 * Compile / preview / validate + emit for the DataFrame Studio.
 *
 * The Studio is sink-free and ephemeral: there is no save, no version
 * ledger, no UC materialise.  It compiles the slice ending at the chosen
 * terminal node to a governed SELECT (``/api/dataframe-studio/compile``),
 * previews it (``/preview``), validates schema flow (``/validate``), and
 * hands the SQL to a notebook cell or the clipboard.
 *
 * Also carries the no-op / re-pointed stubs the shared canvas bundles call.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const studioPersistenceMethods = {
  // The node whose output the SELECT emits: the explicit selection, else the
  // unique leaf (a node with no outgoing edge), else null (ambiguous).
  _terminalNodeId() {
    if (this.selectedNodeId && this.nodes[this.selectedNodeId]) return this.selectedNodeId;
    const hasOutgoing = new Set(Object.values(this.edges).map((e) => e.source_node_id));
    const leaves = Object.keys(this.nodes).filter((id) => !hasOutgoing.has(id));
    return leaves.length === 1 ? leaves[0] : null;
  },
  async loadLatest() {
    // The Studio opens empty; a future iteration can rehydrate from the
    // notebook cell metadata it emitted to (passed via ?notebook=&cell=).
    this.loading = false;
    this.saveState = 'idle';
    this._scheduleValidate();
  },
  // The shared shell autosaves on edits; the Studio has nothing to persist,
  // so the trigger only re-validates + clears the stale compiled SQL.
  _scheduleAutosave() {
    this.compiledSql = '';
  },
  _scheduleValidate() {
    if (this._validateTimer) window.clearTimeout(this._validateTimer);
    this._validateTimer = window.setTimeout(() => this.validate(), 800);
  },
  async validate() {
    if (this.validating) return;
    if (this.nodeCount === 0) {
      this.errors = [];
      this.pinSchemas = {};
      this._refreshAllNodeErrors();
      return;
    }
    this.validating = true;
    const res = await window.pqlApi.fetch('/api/dataframe-studio/validate', {
      method: 'POST',
      body: { document: this._buildDocument() },
      silent: true,
    });
    this.validating = false;
    if (!res.ok) return;
    this.errors = res.data.errors || [];
    this.pinSchemas = res.data.pin_schemas || {};
    this.edgeCategories = res.data.edge_categories || {};
    this._refreshAllNodeErrors();
    this._refreshAllNodeBodies();
    this._refreshEdgeCategoryStyles();
  },
  async compileStudio() {
    const terminal = this._terminalNodeId();
    if (!terminal) {
      this.compileError = 'Select the node to emit (or leave a single leaf node).';
      return;
    }
    this.compileError = null;
    const res = await window.pqlApi.fetch('/api/dataframe-studio/compile', {
      method: 'POST',
      body: { document: this._buildDocument(), terminal_node_id: terminal },
      silent: true,
    });
    if (!res.ok) {
      this.compileError = res.error || 'Compile failed';
      return;
    }
    if ((res.data.errors || []).length) {
      this.compiledSql = '';
      this.errors = res.data.errors;
      this._refreshAllNodeErrors();
      this.compileError = 'Pipeline has errors — see the canvas.';
      return;
    }
    this.compiledSql = res.data.sql || '';
    this.compiledColumns = res.data.columns || [];
  },
  async runPreview() {
    const terminal = this._terminalNodeId();
    if (!terminal) {
      this.previewError = 'Select the node to preview.';
      return;
    }
    this.previewBusy = true;
    this.previewError = null;
    const res = await window.pqlApi.fetch('/api/dataframe-studio/preview', {
      method: 'POST',
      body: {
        document: this._buildDocument(),
        terminal_node_id: terminal,
        limit: this.previewLimit,
      },
      silent: true,
    });
    this.previewBusy = false;
    if (!res.ok) {
      this.previewError = res.error || 'Preview failed';
      return;
    }
    if ((res.data.errors || []).length) {
      this.previewError = res.data.errors.map((e) => e.message).join('; ');
      this.previewResult = null;
      return;
    }
    this.previewResult = {
      columns: res.data.columns || [],
      rows: res.data.rows || [],
      truncated: res.data.truncated,
      row_count: res.data.row_count,
    };
    this.previewOpen = true;
  },
  // Re-point the shared "preview this node" gesture at the Studio preview.
  openPreviewForSelected() {
    this.runPreview();
  },
  async copySql() {
    if (!this.compiledSql) await this.compileStudio();
    if (!this.compiledSql) return;
    try {
      await navigator.clipboard.writeText(this.compiledSql);
      this.copyState = 'copied';
      window.setTimeout(() => {
        this.copyState = 'idle';
      }, 1500);
    } catch (_e) {
      this.copyState = 'idle';
    }
  },
  async copyPqlCall() {
    if (!this.compiledSql) await this.compileStudio();
    if (!this.compiledSql) return;
    const snippet = `df = pql.sql("""\n${this.compiledSql}\n""")`;
    try {
      await navigator.clipboard.writeText(snippet);
      this.copyState = 'copied';
      window.setTimeout(() => {
        this.copyState = 'idle';
      }, 1500);
    } catch (_e) {
      this.copyState = 'idle';
    }
  },

  // CodeMirror mounts for the Filter predicate + Raw SQL fields, reused by
  // the data-product config-form partials.  Identical to the DP editor's,
  // minus the data-product route coupling.
  async mountPredicateCm(host, nodeId, field) {
    if (!host) return;
    const { mountPredicateEditor } = await import('../dp_canvas/codemirror_predicate.js');
    const node = this.nodes[nodeId];
    if (!node) return;
    await mountPredicateEditor(host, {
      initialValue: String((node.config && node.config[field]) || ''),
      onChange: (value) => {
        const live = this.nodes[nodeId];
        if (!live) return;
        if ((live.config[field] || '') === value) return;
        live.config[field] = value;
        this.onConfigChanged();
      },
      getColumns: () => this.upstreamColumns(nodeId, 'in'),
    });
  },
  async mountSqlCm(host, nodeId, field) {
    if (!host) return;
    const { mountSqlEditor } = await import('../dp_canvas/codemirror_predicate.js');
    const node = this.nodes[nodeId];
    if (!node) return;
    await mountSqlEditor(host, {
      initialValue: String((node.config && node.config[field]) || ''),
      onChange: (value) => {
        const live = this.nodes[nodeId];
        if (!live) return;
        if ((live.config[field] || '') === value) return;
        live.config[field] = value;
        this.onConfigChanged();
      },
      getColumns: () => this.upstreamColumns(nodeId, 'in'),
    });
  },

  // --- stubs for data-product-only features the shared bundles call -------
  upstreamColumns(nodeId, pinName) {
    for (const edge of Object.values(this.edges)) {
      if (edge.target_node_id === nodeId && edge.target_pin === pinName) {
        const schema = this.pinSchemas[`${edge.source_node_id}:${edge.source_pin}`];
        if (schema && Array.isArray(schema.columns)) {
          return schema.columns.map((c) => c.name);
        }
      }
    }
    return [];
  },
  openInlinePeek() {
    // no-op: the Studio uses the full preview panel instead of an inline peek.
  },
};
