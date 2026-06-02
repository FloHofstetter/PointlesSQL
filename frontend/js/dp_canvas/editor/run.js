/*
 * Materialise-run controls for the canvas editor.
 *
 * Kicks off the /canvas/materialize POST, surfaces per-sink ok / failed
 * outcomes in the inline run dock, and stamps the matching OutputPort nodes
 * with run-result classes.  Refuses to run while validation errors are
 * outstanding and focuses the first offending block instead.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const runMethods = {
  async runCanvas() {
    if (this.running) return;
    this.runDockOpen = true;
    this.runResult = null;
    this.runError = null;
    this._clearSinkRunMarks();

    // Validation errors are already drawn on the canvas (node badges +
    // the Errors list in the drawer); refuse to run and point the user
    // at the first offending block instead of failing server-side.
    if (this.errors.length > 0) {
      const n = this.errors.length;
      this.runError = `Fix ${n} validation ${n === 1 ? 'error' : 'errors'} before running.`;
      const first = this.errors.find((e) => e.node_id);
      if (first) this.focusNode(first.node_id);
      return;
    }

    this.running = true;
    const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/materialize`, {
      method: 'POST',
      body: {
        document: this._buildDocument(),
        expected_base_version: this.version,
      },
      silent: true,
    });
    this.running = false;
    if (!res.ok) {
      this.runError = res.error || 'Run failed';
      return;
    }
    this.runResult = res.data;
    this.version = res.data.graph_version;
    this.saveState = 'saved';
    this.lastSavedAt = new Date().toISOString();
    this._applySinkRunMarks(res.data.sinks);
  },
  closeRunDock() {
    this.runDockOpen = false;
  },
  _outputNodeForSink(sink) {
    return Object.values(this.nodes).find(
      (n) =>
        n.block_type === 'OutputPort' &&
        (n.config.materialized_table === sink.target_fqn || n.config.port_name === sink.port_name)
    );
  },
  focusSinkByTarget(targetFqn) {
    const node = this._outputNodeForSink({ target_fqn: targetFqn, port_name: null });
    if (node) this.focusNode(node.id);
  },
  _clearSinkRunMarks() {
    const df = this._drawflow;
    if (!df) return;
    df.container.querySelectorAll('.pql-node-run-ok, .pql-node-run-failed').forEach((el) => {
      el.classList.remove('pql-node-run-ok', 'pql-node-run-failed');
    });
  },
  _applySinkRunMarks(sinks) {
    const df = this._drawflow;
    if (!df || !Array.isArray(sinks)) return;
    for (const sink of sinks) {
      const node = this._outputNodeForSink(sink);
      if (!node) continue;
      const dfId = this._drawflowNodes[node.id];
      if (!dfId) continue;
      const wrap = df.container.querySelector(`#node-${dfId}`);
      if (!wrap) continue;
      wrap.classList.add(sink.status === 'ok' ? 'pql-node-run-ok' : 'pql-node-run-failed');
    }
  },
};
