/**
 * Lineage drill-down sub-pane Alpine factories.
 *
 * Three factories — ``rowTracePane`` / ``columnTracePane`` /
 * ``valueChangesPane`` — back the three new sub-pills inside the
 * Lineage top-tab on ``/runs/{id}``.  Each pane fetches from one
 * of the existing JSON endpoints
 * (``/api/lineage/row-trace``, ``/api/lineage/column-trace``,
 * ``/api/lineage/value-changes``) and renders steps inline so the
 * audit-reviewer never has to leave the run-detail page.
 *
 * Deep-link contract — three custom window events:
 *
 *   pql:trace-row    detail = { table, rowId }
 *   pql:trace-column detail = { table, column }
 *   pql:trace-value  detail = { table, rowId, column? }
 *
 * Each pane factory's ``init()`` listens for its own event,
 * stuffs its inputs from ``event.detail``, activates its sub-pill
 * via Bootstrap 5's ``Tab`` JS API, and triggers ``fetch()``.
 *
 * Helper functions ``window.pqlLineageTraceRow / TraceColumn /
 * TraceValue`` are exposed for plain inline-handler dispatch from
 * Summary buttons + Graph side-panel buttons.
 *
 * The standalone ``/catalogs/.../rows/{row_id}/trace`` and
 * ``/catalogs/.../columns/{name}/trace`` pages stay route-mounted
 * unchanged — these sub-panes are additive.
 */

function _activateTab(tabBtnId) {
  const btn = document.getElementById(tabBtnId);
  if (!btn) return;
  if (window.bootstrap && window.bootstrap.Tab) {
    window.bootstrap.Tab.getOrCreateInstance(btn).show();
    return;
  }
  btn.click();
}

export function rowTracePane() {
  return {
    table: '',
    rowId: '',
    loading: false,
    loaded: false,
    error: null,
    steps: [],

    init() {
      window.addEventListener('pql:trace-row', (evt) => {
        const detail = evt.detail || {};
        if (detail.table) this.table = String(detail.table);
        if (detail.rowId) this.rowId = String(detail.rowId);
        _activateTab('tab-lineage-row-trace-btn');
        if (this.table && this.rowId) {
          this.fetch();
        }
      });
    },

    async fetch() {
      if (!this.table || !this.rowId) return;
      this.loading = true;
      this.error = null;
      try {
        const url =
          '/api/lineage/row-trace?table=' +
          encodeURIComponent(this.table) +
          '&row_id=' +
          encodeURIComponent(this.rowId);
        const resp = await fetch(url, {
          headers: { Accept: 'application/json' },
        });
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          this.error = body.detail || 'HTTP ' + resp.status;
          this.steps = [];
        } else {
          const body = await resp.json();
          this.steps = body.steps || [];
          this.loaded = true;
        }
      } catch (err) {
        this.error = err.message || String(err);
        this.steps = [];
      } finally {
        this.loading = false;
      }
    },
  };
}

export function columnTracePane() {
  return {
    table: '',
    column: '',
    loading: false,
    loaded: false,
    error: null,
    steps: [],

    init() {
      window.addEventListener('pql:trace-column', (evt) => {
        const detail = evt.detail || {};
        if (detail.table) this.table = String(detail.table);
        if (detail.column) this.column = String(detail.column);
        _activateTab('tab-lineage-column-trace-btn');
        if (this.table && this.column) {
          this.fetch();
        }
      });
    },

    async fetch() {
      if (!this.table || !this.column) return;
      this.loading = true;
      this.error = null;
      try {
        const url =
          '/api/lineage/column-trace?table=' +
          encodeURIComponent(this.table) +
          '&column=' +
          encodeURIComponent(this.column);
        const resp = await fetch(url, {
          headers: { Accept: 'application/json' },
        });
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          this.error = body.detail || 'HTTP ' + resp.status;
          this.steps = [];
        } else {
          const body = await resp.json();
          this.steps = body.steps || [];
          this.loaded = true;
        }
      } catch (err) {
        this.error = err.message || String(err);
        this.steps = [];
      } finally {
        this.loading = false;
      }
    },
  };
}

export function valueChangesPane() {
  return {
    table: '',
    rowId: '',
    column: '',
    loading: false,
    loaded: false,
    error: null,
    changes: [],

    init() {
      window.addEventListener('pql:trace-value', (evt) => {
        const detail = evt.detail || {};
        if (detail.table) this.table = String(detail.table);
        if (detail.rowId) this.rowId = String(detail.rowId);
        if (detail.column !== undefined && detail.column !== null) {
          this.column = String(detail.column);
        }
        _activateTab('tab-lineage-value-changes-btn');
        if (this.table && this.rowId) {
          this.fetch();
        }
      });
    },

    async fetch() {
      if (!this.table || !this.rowId) return;
      this.loading = true;
      this.error = null;
      try {
        let url =
          '/api/lineage/value-changes?table=' +
          encodeURIComponent(this.table) +
          '&row_id=' +
          encodeURIComponent(this.rowId);
        if (this.column) {
          url += '&column=' + encodeURIComponent(this.column);
        }
        const resp = await fetch(url, {
          headers: { Accept: 'application/json' },
        });
        if (!resp.ok) {
          const body = await resp.json().catch(() => ({}));
          this.error = body.detail || 'HTTP ' + resp.status;
          this.changes = [];
        } else {
          const body = await resp.json();
          this.changes = body.changes || [];
          this.loaded = true;
        }
      } catch (err) {
        this.error = err.message || String(err);
        this.changes = [];
      } finally {
        this.loading = false;
      }
    },
  };
}

/**
 * Wire up the deep-link plumbing once on document load.
 *
 * - Exposes ``window.pqlLineageTraceRow / TraceColumn / TraceValue``
 *   helper functions for inline-onclick dispatch from templates.
 * - Binds click handlers to every
 *   ``button[data-pql-trace-row="1"]`` rendered inside the Summary
 *   sub-pane.  The button carries ``data-table`` + ``data-row-id``
 *   attributes; the handler dispatches the matching custom event.
 *
 * Idempotent: safe to call multiple times.  Buttons rendered after
 * the initial pass (none today, but future HTMX swaps for example)
 * pick up wiring via event delegation on ``document.body``.
 */
export function bindLineageTraceButtons() {
  if (window.__pqlLineageTraceBound) return;
  window.__pqlLineageTraceBound = true;

  window.pqlLineageTraceRow = (table, rowId) => {
    window.dispatchEvent(new CustomEvent('pql:trace-row', { detail: { table, rowId } }));
  };
  window.pqlLineageTraceColumn = (table, column) => {
    window.dispatchEvent(new CustomEvent('pql:trace-column', { detail: { table, column } }));
  };
  window.pqlLineageTraceValue = (table, rowId, column) => {
    window.dispatchEvent(
      new CustomEvent('pql:trace-value', {
        detail: { table, rowId, column: column || null },
      })
    );
  };

  document.body.addEventListener('click', (evt) => {
    const target = evt.target instanceof Element ? evt.target : null;
    if (!target) return;
    const btn = target.closest('button[data-pql-trace-row="1"]');
    if (!btn) return;
    evt.preventDefault();
    const table = btn.getAttribute('data-table') || '';
    const rowId = btn.getAttribute('data-row-id') || '';
    if (table && rowId) {
      window.pqlLineageTraceRow(table, rowId);
    }
  });
}
