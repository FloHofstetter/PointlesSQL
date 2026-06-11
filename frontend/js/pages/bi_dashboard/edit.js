// AI/BI dashboard editor factory (/bi/{slug}/edit).
//
// Gridstack runs editable here: drags and resizes queue a debounced
// layout PUT, the drawer drives widget CRUD through the JSON API, and
// the params editor PATCHes the dashboard's parameter specs. Adding
// a widget reloads the page (the grid item is server-rendered);
// editing re-renders the card in place via the shared render module.

import { pqlApi, toast } from '../../api.js';
import { loadWidget, refreshWidgets } from './render.js';

const LAYOUT_DEBOUNCE_MS = 800;

function blankForm() {
  return {
    kind: 'chart',
    title: '',
    sql_text: '',
    saved_query_id: '',
    markdown: '',
    chart_type: 'bar',
    chart_x: '',
    chart_y: '',
  };
}

export function biDashboardEdit(config) {
  return {
    slug: config.slug,
    widgets: config.widgets || [],
    paramRows: (config.params || []).map((p) => ({
      name: p.name || '',
      label: p.label || '',
      type: p.type || 'string',
      default: p.default == null ? '' : String(p.default),
    })),
    grid: null,
    error: '',
    savingParams: false,
    drawer: {
      open: false,
      widgetId: null,
      saving: false,
      running: false,
      runResult: '',
      error: '',
      form: blankForm(),
    },
    _layoutTimer: null,

    async init() {
      await this._initGrid();
      await this.refreshAll();
    },

    async _initGrid() {
      const el = this.$root.querySelector('[data-bi-grid]');
      if (!el) return;
      try {
        const mod = await import('gridstack');
        const GridStack = mod.GridStack || mod.default;
        this.grid = GridStack.init({ margin: 6, cellHeight: 90, column: 12 }, el);
        el.classList.add('pql-bi-grid--ready');
        this.grid.on('change', () => this._queueLayoutSave());
      } catch (e) {
        this.error = 'Layout library unavailable — drag and resize are disabled.';
      }
    },

    paramDefaults() {
      const values = {};
      for (const p of this.paramRows) {
        if (p.name && p.default !== '') values[p.name] = p.default;
      }
      return values;
    },

    async refreshAll() {
      await refreshWidgets(
        this.$root,
        this.widgets,
        (id) => `/api/bi/dashboards/${this.slug}/widgets/${id}/data`,
        this.paramDefaults()
      );
    },

    // ── layout ──────────────────────────────────────────────────

    positions() {
      const map = {};
      if (!this.grid) return map;
      for (const node of this.grid.engine.nodes) {
        if (node.id == null) continue;
        map[node.id] = { x: node.x, y: node.y, w: node.w, h: node.h };
      }
      return map;
    },

    _queueLayoutSave() {
      window.clearTimeout(this._layoutTimer);
      this._layoutTimer = window.setTimeout(() => this.saveLayout(true), LAYOUT_DEBOUNCE_MS);
    },

    async saveLayout(silent) {
      const positions = this.positions();
      if (!Object.keys(positions).length) return;
      const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}/layout`, {
        method: 'PUT',
        body: { positions: positions },
        silent: !!silent,
      });
      if (res.ok && !silent) toast('success', 'Layout saved.');
    },

    // ── widget drawer ───────────────────────────────────────────

    openAdd() {
      this.drawer = {
        open: true,
        widgetId: null,
        saving: false,
        running: false,
        runResult: '',
        error: '',
        form: blankForm(),
      };
    },

    openEdit(widgetId) {
      const widget = this.widgets.find((w) => w.id === widgetId);
      if (!widget) return;
      const spec = widget.chart_spec || {};
      this.drawer = {
        open: true,
        widgetId: widgetId,
        saving: false,
        running: false,
        runResult: '',
        error: '',
        form: {
          kind: widget.kind,
          title: widget.title || '',
          sql_text: widget.sql_text || '',
          saved_query_id: widget.saved_query_id == null ? '' : String(widget.saved_query_id),
          markdown: widget.markdown || '',
          chart_type: spec.type || 'bar',
          chart_x: spec.x || '',
          chart_y: spec.y || '',
        },
      };
    },

    _formBody() {
      const f = this.drawer.form;
      const body = { title: f.title.trim() || null };
      if (f.kind === 'markdown') {
        body.markdown = f.markdown;
      } else {
        body.sql_text = f.sql_text.trim() || null;
        body.saved_query_id = f.saved_query_id ? Number(f.saved_query_id) : null;
        if (f.kind === 'chart') {
          body.chart_spec = { type: f.chart_type, x: f.chart_x.trim(), y: f.chart_y.trim() };
        }
      }
      return body;
    },

    async saveWidget() {
      this.drawer.error = '';
      this.drawer.runResult = '';
      this.drawer.saving = true;
      const body = this._formBody();
      if (this.drawer.widgetId === null) {
        body.kind = this.drawer.form.kind;
        const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}/widgets`, {
          method: 'POST',
          body: body,
          silent: true,
        });
        this.drawer.saving = false;
        if (!res.ok) {
          this.drawer.error = res.error || 'Failed to add widget.';
          return;
        }
        pqlApi.reloadWithToast('Widget added.');
        return;
      }
      const res = await pqlApi.fetch(
        `/api/bi/dashboards/${this.slug}/widgets/${this.drawer.widgetId}`,
        { method: 'PATCH', body: body, silent: true }
      );
      this.drawer.saving = false;
      if (!res.ok) {
        this.drawer.error = res.error || 'Failed to save widget.';
        return;
      }
      const idx = this.widgets.findIndex((w) => w.id === this.drawer.widgetId);
      if (idx >= 0) this.widgets[idx] = res.data;
      const titleEl = this.$root.querySelector(`[data-widget-title="${res.data.id}"]`);
      if (titleEl) titleEl.textContent = res.data.title || res.data.kind;
      const bodyEl = this.$root.querySelector(`[data-widget-id="${res.data.id}"]`);
      if (bodyEl) {
        await loadWidget(
          bodyEl,
          res.data,
          `/api/bi/dashboards/${this.slug}/widgets/${res.data.id}/data`,
          this.paramDefaults()
        );
      }
      this.drawer.open = false;
      toast('success', 'Widget saved.');
    },

    async removeWidget(widgetId) {
      if (!window.confirm('Delete this widget?')) return;
      const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}/widgets/${widgetId}`, {
        method: 'DELETE',
      });
      if (!res.ok) return;
      const itemEl = this.$root.querySelector(`.grid-stack-item[gs-id="${widgetId}"]`);
      if (this.grid && itemEl) {
        this.grid.removeWidget(itemEl);
      } else if (itemEl) {
        itemEl.remove();
      }
      this.widgets = this.widgets.filter((w) => w.id !== widgetId);
      toast('success', 'Widget deleted.');
    },

    async runPreview() {
      if (this.drawer.widgetId === null) return;
      this.drawer.running = true;
      this.drawer.runResult = '';
      this.drawer.error = '';
      const res = await pqlApi.fetch(
        `/api/bi/dashboards/${this.slug}/widgets/${this.drawer.widgetId}/data`,
        { method: 'POST', body: { params: this.paramDefaults() }, silent: true }
      );
      this.drawer.running = false;
      if (!res.ok) {
        this.drawer.error = res.error || 'Query failed.';
        return;
      }
      this.drawer.runResult = `${res.data.row_count} rows in ${res.data.duration_ms} ms.`;
    },

    // ── params editor ───────────────────────────────────────────

    addParam() {
      this.paramRows.push({ name: '', label: '', type: 'string', default: '' });
    },

    removeParam(index) {
      this.paramRows.splice(index, 1);
    },

    async saveParams() {
      this.error = '';
      this.savingParams = true;
      const params = this.paramRows.map((p) => ({
        name: p.name.trim(),
        label: p.label.trim() || p.name.trim(),
        type: p.type,
        default: p.default === '' ? null : p.default,
      }));
      const res = await pqlApi.fetch(`/api/bi/dashboards/${this.slug}`, {
        method: 'PATCH',
        body: { params: params },
        silent: true,
      });
      this.savingParams = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to save parameters.';
        return;
      }
      toast('success', 'Parameters saved.');
    },
  };
}
