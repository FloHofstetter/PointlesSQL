// Metric-view browser (/metric-views).
//
// metricViews: catalog/schema pickers + per-schema view list + a
// definition editor (dimensions/measures/filter) + a query panel
// that compiles and runs governed metric queries server-side.

export function metricViews() {
  return {
    catalogs: [],
    schemas: [],
    catalog: '',
    schema: '',
    views: [],
    loading: false,
    error: '',

    editor: null,
    editorError: '',
    saving: false,

    queryView: null,
    q: { dimensions: [], measures: [], where: '', order_by: '', limit: 100 },
    result: null,
    running: false,
    showSql: false,

    async init() {
      const res = await window.pqlApi.fetch('/api/catalogs');
      if (res.ok) this.catalogs = res.data || [];
    },

    async loadSchemas() {
      this.schemas = [];
      if (!this.catalog) return;
      const res = await window.pqlApi.fetch(
        '/api/catalogs/' + encodeURIComponent(this.catalog) + '/schemas'
      );
      if (res.ok) this.schemas = res.data || [];
    },

    async loadViews() {
      this.error = '';
      this.views = [];
      this.queryView = null;
      this.editor = null;
      if (!this.catalog || !this.schema) return;
      this.loading = true;
      const res = await window.pqlApi.fetch(
        '/api/metric-views?catalog_name=' +
          encodeURIComponent(this.catalog) +
          '&schema_name=' +
          encodeURIComponent(this.schema)
      );
      this.loading = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to load metric views';
        return;
      }
      this.views = (res.data && res.data.metric_views) || [];
    },

    openCreate() {
      this.editorError = '';
      this.editor = {
        full_name: '',
        name: '',
        source_table_full_name: this.catalog + '.' + this.schema + '.',
        comment: '',
        spec: {
          dimensions: [{ name: '', expr: '' }],
          measures: [{ name: '', expr: '' }],
          filter: '',
        },
      };
    },

    openEdit(view) {
      this.editorError = '';
      this.editor = {
        full_name: view.full_name,
        name: view.name,
        source_table_full_name: view.source_table_full_name,
        comment: view.comment || '',
        spec: {
          dimensions: (view.spec.dimensions || []).map((d) => ({ name: d.name, expr: d.expr })),
          measures: (view.spec.measures || []).map((m) => ({ name: m.name, expr: m.expr })),
          filter: view.spec.filter || '',
        },
      };
    },

    _specPayload() {
      const spec = {
        dimensions: this.editor.spec.dimensions.filter((d) => d.name && d.expr),
        measures: this.editor.spec.measures.filter((m) => m.name && m.expr),
      };
      if (this.editor.spec.filter) spec.filter = this.editor.spec.filter;
      return spec;
    },

    async save() {
      this.editorError = '';
      this.saving = true;
      let res;
      if (this.editor.full_name) {
        res = await window.pqlApi.fetch(
          '/api/metric-views/' + encodeURIComponent(this.editor.full_name),
          {
            method: 'PATCH',
            body: {
              spec: this._specPayload(),
              comment: this.editor.comment || null,
              source_table_full_name: this.editor.source_table_full_name,
            },
          }
        );
      } else {
        res = await window.pqlApi.fetch('/api/metric-views', {
          method: 'POST',
          body: {
            name: this.editor.name.trim(),
            catalog_name: this.catalog,
            schema_name: this.schema,
            source_table_full_name: this.editor.source_table_full_name.trim(),
            spec: this._specPayload(),
            comment: this.editor.comment || null,
          },
        });
      }
      this.saving = false;
      if (!res.ok) {
        this.editorError = res.error || 'Failed to save metric view';
        return;
      }
      this.editor = null;
      await this.loadViews();
    },

    async remove(view) {
      if (!window.confirm('Delete metric view "' + view.full_name + '"?')) return;
      const res = await window.pqlApi.fetch(
        '/api/metric-views/' + encodeURIComponent(view.full_name),
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      await this.loadViews();
    },

    toggleQuery(view) {
      if (this.queryView && this.queryView.full_name === view.full_name) {
        this.queryView = null;
        return;
      }
      this.queryView = view;
      this.result = null;
      this.showSql = false;
      this.q = {
        dimensions: (view.spec.dimensions || []).slice(0, 1).map((d) => d.name),
        measures: (view.spec.measures || []).slice(0, 1).map((m) => m.name),
        where: '',
        order_by: '',
        limit: 100,
      };
    },

    async runQuery() {
      this.error = '';
      this.running = true;
      const body = {
        dimensions: this.q.dimensions,
        measures: this.q.measures,
      };
      if (this.q.where) body.where = this.q.where;
      if (this.q.order_by) body.order_by = this.q.order_by;
      if (this.q.limit) body.limit = this.q.limit;
      const res = await window.pqlApi.fetch(
        '/api/metric-views/' + encodeURIComponent(this.queryView.full_name) + '/query',
        { method: 'POST', body: body }
      );
      this.running = false;
      if (!res.ok) {
        this.error = res.error || 'Query failed';
        this.result = null;
        return;
      }
      this.result = res.data;
    },
  };
}
