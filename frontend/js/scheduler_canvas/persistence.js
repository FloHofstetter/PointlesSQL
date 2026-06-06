/*
 * Save / load / validate persistence for the scheduler task-chain editor.
 *
 * Round-trips the graph against ``/api/jobs/{id}/canvas`` (the JobTask ⇄
 * CanvasDoc bridge).  Unlike the data-product editor there is no version
 * ledger and no schema flow — a job's tasks *are* the document — so a save
 * reloads the freshly-rebuilt doc to pick up the ``task-{pk}`` ids the
 * server minted for new nodes.
 *
 * Also carries the small no-op stubs the shared canvas bundles call for
 * data-product-only features the scheduler does not have (column schema
 * flow, inline preview peek).
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const schedulerPersistenceMethods = {
  saveStateLabel() {
    if (this.saveState === 'saving') return 'Saving…';
    if (this.saveState === 'error') return 'Save failed';
    if (this.saveState === 'saved') return '✓ Saved';
    return '';
  },
  saveStateTooltip() {
    if (this.saveState === 'error') return this.saveError || 'Save failed';
    if (this.saveState === 'saved' && this.lastSavedAt) {
      return 'Last saved at ' + new Date(this.lastSavedAt).toLocaleString();
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
    const res = await window.pqlApi.fetch(`/api/jobs/${this.jobId}/canvas`, { silent: true });
    if (!res.ok) {
      this.loading = false;
      this.saveState = 'error';
      this.saveError = res.error || 'Load failed';
      return;
    }
    if (res.data.document) {
      this._suppressAutosave = true;
      this._loadIntoDrawflow(res.data.document);
      this._suppressAutosave = false;
    }
    this.loading = false;
    this.saveState = 'saved';
    this.lastSavedAt = new Date().toISOString();
    this._scheduleValidate();
    // The bridge does not persist node positions, so lay the DAG out
    // left-to-right on load instead of stacking every task at the origin.
    if (Object.keys(this.nodes).length > 0) {
      this.$nextTick(() => this.autoTidy());
    }
  },
  _scheduleAutosave() {
    if (!this.canWrite) return;
    if (this._saveTimer) window.clearTimeout(this._saveTimer);
    this._saveTimer = window.setTimeout(() => this.save(), 1500);
  },
  _scheduleValidate() {
    if (this._validateTimer) window.clearTimeout(this._validateTimer);
    this._validateTimer = window.setTimeout(() => this.validate(), 800);
  },
  async save() {
    if (!this.canWrite || this.saving) return;
    this.saving = true;
    this.saveState = 'saving';
    this.saveError = null;
    const res = await window.pqlApi.fetch(`/api/jobs/${this.jobId}/canvas`, {
      method: 'POST',
      body: { document: this._buildDocument() },
      silent: true,
    });
    this.saving = false;
    if (!res.ok) {
      this.saveState = 'error';
      this.saveError = res.error || 'Save failed';
      return;
    }
    this.saveState = 'saved';
    this.lastSavedAt = new Date().toISOString();
    // Reload the rebuilt doc so editor-minted node ids become task-{pk}.
    if (res.data.document) {
      this._suppressAutosave = true;
      this._loadIntoDrawflow(res.data.document);
      this._suppressAutosave = false;
      this._scheduleValidate();
    }
  },
  async validate() {
    if (this.validating) return;
    if (this.nodeCount === 0) {
      this.issues = [];
      return;
    }
    this.validating = true;
    const res = await window.pqlApi.fetch(`/api/jobs/${this.jobId}/canvas/validate`, {
      method: 'POST',
      body: { document: this._buildDocument() },
      silent: true,
    });
    this.validating = false;
    if (!res.ok) {
      this.saveError = res.error || 'Validate failed';
      return;
    }
    this.issues = res.data.issues || [];
  },

  // --- stubs for data-product-only features the shared bundles call -------
  // The scheduler has no column schema, so sensible-defaults + drop-target
  // highlighting find no upstream columns; preview / inline-peek do not exist.
  upstreamColumns() {
    return [];
  },
  openInlinePeek() {
    // no-op: the scheduler has no per-node data preview.
  },
  openPreviewForSelected() {
    // no-op: the scheduler has no per-node data preview.
  },
};
