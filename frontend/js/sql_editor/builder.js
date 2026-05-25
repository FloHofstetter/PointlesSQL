/**
 * Visual Query Builder mixin for the SQL editor.
 *
 * State + methods that back the "Builder" panel: a Grafana-style
 * toggle that turns a single-table SELECT into a form (filters +
 * group-by + aggregates + order-by + limit) and writes the
 * generated SQL back into the editor.
 *
 * Round-tripping is best-effort: when the user has hand-edited
 * SQL the server cannot mechanically reverse into builder state,
 * ``builderUnsupported`` flips to ``true`` and the UI hides the
 * panel until the user picks "Reset builder".
 */

export const builderMethods = {
  builderOpen: false,
  builderState: {
    table_fqn: '',
    filters: [],
    group_by: [],
    aggregates: [],
    order_by: [],
    limit: 100,
  },
  builderColumns: [],
  builderColumnsLoading: false,
  builderUnsupported: false,
  builderError: null,
  builderOperators: [
    '=',
    '!=',
    '<',
    '<=',
    '>',
    '>=',
    'LIKE',
    'ILIKE',
    'IN',
    'IS NULL',
    'IS NOT NULL',
  ],
  builderAggregates: ['COUNT', 'SUM', 'AVG', 'MIN', 'MAX'],

  async toggleBuilder() {
    if (this.builderOpen) {
      this.builderOpen = false;
      return;
    }
    const sql = this.getSQL();
    if (sql && sql.trim()) {
      const res = await window.pqlApi.fetch('/api/sql/builder/parse', {
        method: 'POST',
        body: { sql },
        silent: true,
      });
      if (res.ok && res.data && res.data.state) {
        this.builderState = {
          table_fqn: '',
          filters: [],
          group_by: [],
          aggregates: [],
          order_by: [],
          limit: 100,
          ...res.data.state,
        };
        this.builderUnsupported = false;
      } else {
        this.builderUnsupported = true;
      }
    } else {
      this.builderUnsupported = false;
    }
    this.builderOpen = true;
    if (this.builderState.table_fqn) {
      this.loadBuilderColumns();
    }
  },

  resetBuilder() {
    this.builderState = {
      table_fqn: '',
      filters: [],
      group_by: [],
      aggregates: [],
      order_by: [],
      limit: 100,
    };
    this.builderUnsupported = false;
    this.builderColumns = [];
  },

  async loadBuilderColumns() {
    const fqn = (this.builderState.table_fqn || '').trim();
    if (!fqn) {
      this.builderColumns = [];
      return;
    }
    this.builderColumnsLoading = true;
    const res = await window.pqlApi.fetch('/api/sql/builder/columns', {
      method: 'POST',
      body: { table_fqn: fqn },
      silent: true,
    });
    this.builderColumnsLoading = false;
    if (res.ok && res.data && Array.isArray(res.data.columns)) {
      this.builderColumns = res.data.columns;
      this.builderError = null;
    } else {
      this.builderColumns = [];
      this.builderError = (res.data && res.data.detail) || 'Could not probe columns.';
    }
  },

  addBuilderFilter() {
    this.builderState.filters.push({ column: '', op: '=', value: '' });
  },
  removeBuilderFilter(idx) {
    this.builderState.filters.splice(idx, 1);
  },
  addBuilderAggregate() {
    this.builderState.aggregates.push({ fn: 'COUNT', column: '*', alias: '' });
  },
  removeBuilderAggregate(idx) {
    this.builderState.aggregates.splice(idx, 1);
  },
  addBuilderOrder() {
    this.builderState.order_by.push({ column: '', dir: 'asc' });
  },
  removeBuilderOrder(idx) {
    this.builderState.order_by.splice(idx, 1);
  },

  async applyBuilder() {
    this.builderError = null;
    const res = await window.pqlApi.fetch('/api/sql/builder/build', {
      method: 'POST',
      body: this.builderState,
      silent: true,
    });
    if (res.ok && res.data && res.data.sql) {
      this.setSQL(res.data.sql);
    } else {
      this.builderError = (res.data && res.data.detail) || 'Could not render SQL.';
    }
  },
};
