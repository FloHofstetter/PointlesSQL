/*
 * Save / load / validate persistence for the canvas editor.
 *
 * Debounced autosave + validate timers, the POST round-trips to the
 * /api/dp/{id}/canvas endpoints, and the small topbar save-state label /
 * tooltip / class helpers that report idle / saving / saved / error.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const persistenceMethods = {
  saveStateLabel() {
    if (this.saveState === 'saving') return 'Saving…';
    if (this.saveState === 'error') return 'Save failed';
    if (this.saveState === 'saved' && this.lastSavedAt) return '✓ Saved';
    if (this.version !== null) return 'v' + this.version;
    return '';
  },
  saveStateTooltip() {
    if (this.saveState === 'error') return this.saveError || 'Save failed';
    if (this.saveState === 'saved' && this.lastSavedAt) {
      const date = new Date(this.lastSavedAt);
      return 'Last saved at ' + date.toLocaleString();
    }
    return '';
  },
  saveStateClass() {
    if (this.saveState === 'error') return 'text-danger';
    if (this.saveState === 'saving') return 'text-muted';
    if (this.saveState === 'saved') return 'text-success';
    return 'text-muted';
  },
  async loadLatest() {
    this.loading = true;
    const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas`, {
      silent: true,
    });
    if (!res.ok) {
      this.loading = false;
      this.saveState = 'error';
      this.saveError = res.error || 'Load failed';
      return;
    }
    this.version = res.data.version;
    if (res.data.document) {
      this._suppressAutosave = true;
      this._loadIntoDrawflow(res.data.document);
      this._suppressAutosave = false;
    }
    this.loading = false;
    this.saveState = 'saved';
    this.lastSavedAt = res.data.created_at || new Date().toISOString();
    this._scheduleValidate();
    // Auto-fit the viewport once per load so multi-node DPs don't open
    // showing only the top-left node.
    if (!this._initialFitDone && Object.keys(this.nodes).length > 0) {
      this._initialFitDone = true;
      this.$nextTick(() => this.fitToView());
    }
  },
  _scheduleAutosave() {
    if (!this.canWrite) return;
    if (this._saveTimer) window.clearTimeout(this._saveTimer);
    this._saveTimer = window.setTimeout(() => this.save(), 1500);
  },
  _scheduleValidate() {
    // Any edit invalidates the last run's per-sink marks.
    this._clearSinkRunMarks();
    if (this._validateTimer) window.clearTimeout(this._validateTimer);
    this._validateTimer = window.setTimeout(() => this.validate(), 800);
  },
  async save() {
    if (!this.canWrite || this.saving) return;
    this.saving = true;
    this.saveState = 'saving';
    this.saveError = null;
    const body = {
      document: this._buildDocument(),
      expected_base_version: this.version,
    };
    const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas`, {
      method: 'POST',
      body,
      silent: true,
    });
    this.saving = false;
    if (!res.ok) {
      this.saveState = 'error';
      this.saveError = res.error || 'Save failed';
      return;
    }
    this.version = res.data.version;
    this.saveState = 'saved';
    this.lastSavedAt = res.data.created_at || new Date().toISOString();
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
    const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/validate`, {
      method: 'POST',
      body: { document: this._buildDocument() },
      silent: true,
    });
    this.validating = false;
    if (!res.ok) {
      // Validation network/server errors are non-fatal — surface in topbar only.
      this.saveError = res.error || 'Validate failed';
      return;
    }
    this.errors = res.data.errors || [];
    this.pinSchemas = res.data.pin_schemas || {};
    this.edgeCategories = res.data.edge_categories || {};
    this._refreshAllNodeErrors();
    this._refreshAllNodeBodies();
    this._refreshEdgeCategoryStyles();
    this._scheduleMinimapRender();
  },
};
