/*
 * Cross-data-product navigation for the canvas editor.
 *
 * The breadcrumb trail that records DP drill-ins (double-click a
 * DataProduct block to open its canvas in place) and the DP picker that
 * populates a DataProduct block's port options.
 *
 * Methods are plain (never arrow) so `this` binds to the Alpine proxy.
 */

export const navigationMethods = {
  _restoreBreadcrumb() {
    try {
      const raw = window.localStorage.getItem('pql.dp_canvas.breadcrumb');
      this.breadcrumbTrail = raw ? JSON.parse(raw) : [];
    } catch (e) {
      this.breadcrumbTrail = [];
    }
  },
  _pushBreadcrumb() {
    const entry = {
      dp_id: this.product.id,
      ref: this.product.ref || `${this.product.catalog}.${this.product.schema}`,
    };
    const trail = (this.breadcrumbTrail || []).filter((e) => e.dp_id !== entry.dp_id);
    trail.push(entry);
    window.localStorage.setItem('pql.dp_canvas.breadcrumb', JSON.stringify(trail.slice(-6)));
  },
  popBreadcrumbBack() {
    const trail = this.breadcrumbTrail || [];
    const prev = trail[trail.length - 1];
    if (!prev) return;
    const updated = trail.slice(0, -1);
    window.localStorage.setItem('pql.dp_canvas.breadcrumb', JSON.stringify(updated));
    window.location.href = `/dp/${prev.dp_id}/canvas`;
  },
  _onCanvasDoubleClick(ev) {
    const nodeEl = ev.target.closest('.drawflow-node');
    if (!nodeEl) return;
    const dfId = (nodeEl.id || '').replace('node-', '');
    const pqlId = Object.keys(this._drawflowNodes).find(
      (k) => String(this._drawflowNodes[k]) === dfId
    );
    const node = pqlId && this.nodes[pqlId];
    if (!node || node.block_type !== 'DataProduct') return;
    const targetDpId = Number(node.config.dp_id || 0);
    if (!targetDpId) return;
    this._pushBreadcrumb();
    window.location.href = `/dp/${targetDpId}/canvas`;
  },
  async ensureDpPickerLoaded() {
    if (this.dpPicker.loaded) return;
    const res = await window.pqlApi.fetch('/api/dp/_picker', { silent: true });
    if (!res.ok) return;
    this.dpPicker = { loaded: true, products: res.data.data_products || [] };
  },
  dpPortsFor(dpId) {
    const entry = (this.dpPicker.products || []).find((p) => p.dp_id === dpId);
    return entry ? entry.output_ports : [];
  },
  onDataProductPicked(node) {
    // After cfg.dp_id changes, default the port to the first available.
    const ports = this.dpPortsFor(node.config.dp_id);
    if (ports.length > 0 && !ports.some((p) => p.name === node.config.port_name)) {
      node.config.port_name = ports[0].name;
      node.config.materialized_table = ports[0].location || '';
    } else if (node.config.port_name) {
      const port = ports.find((p) => p.name === node.config.port_name);
      node.config.materialized_table = (port && port.location) || '';
    }
    this.onConfigChanged();
  },
};
