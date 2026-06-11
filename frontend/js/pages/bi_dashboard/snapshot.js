// BI snapshot page factory (/bi/{slug}/snapshots/{id}).
//
// Read-only sibling of the dashboard view: every widget paints from
// the frozen payload the server inlined into the page config, so no
// data endpoint is ever called. Charts reuse the same lazy-loaded
// ECharts renderers as the live grid — only the data source differs.

import { renderMarkdownWidget, renderWidget, renderWidgetError } from './render.js';

export function biSnapshotView(config) {
  return {
    widgets: config.widgets || [],

    async init() {
      await Promise.all(this.widgets.map((w) => this._paint(w)));
    },

    async _paint(entry) {
      const el = this.$root.querySelector(`[data-widget-id="${entry.widget_id}"]`);
      if (!el) return;
      if (entry.error) {
        renderWidgetError(el, entry.error);
        return;
      }
      if (entry.kind === 'markdown') {
        renderMarkdownWidget(el, entry.markdown || '');
        return;
      }
      const widget = { kind: entry.kind, chart_spec: entry.chart_spec || {} };
      const data = {
        columns: entry.columns || [],
        rows: entry.rows || [],
        row_count: entry.row_count || 0,
        truncated: !!entry.truncated,
      };
      await renderWidget(el, widget, data);
    },
  };
}
