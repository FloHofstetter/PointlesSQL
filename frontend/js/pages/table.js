// table detail page factories.
//
// Three Alpine factories used by frontend/templates/pages/table.html:
//
//   tableStats()      column-stat profile button + sparkline rendering
//   tableDiscussion() polymorphic /api/social/table/{ref}/comments pane
//   tableReadme()     polymorphic /api/social/table/{ref}/readme pane
//
// Endorsements + Followers panes reuse the kind-agnostic socialTabs
// factory + the polymorphic partials.  Discussion + README stay
// table-flavoured here because the data_product variants carry extra
// fields (resolved bodies, version anchors) that aren't relevant on
// tables.

export function tableStats(fullName) {
  return {
    loading: false,
    columns: [],
    deltaVersion: null,
    cached: false,

    async init() {
      const res = await window.pqlApi.fetch(
        '/api/tables/' + encodeURIComponent(fullName) + '/stats',
        { silent: true }
      );
      if (res.ok && res.data && Array.isArray(res.data.columns)) {
        this.columns = res.data.columns;
        this.deltaVersion = res.data.delta_log_version;
        this.cached = this.columns.length > 0;
        if (this.cached) this.$nextTick(() => this.drawSparklines());
      }
      // Charts drawn while the Columns tab is hidden size to 0×0 and
      // render blank; redraw when the pane hosting the sparklines first
      // becomes visible.
      document.addEventListener('shown.bs.tab', (e) => {
        const sel = e.target && e.target.getAttribute('data-bs-target');
        const pane = sel ? document.querySelector(sel) : null;
        if (this.cached && pane && pane.querySelector('.pql-stats-sparkline')) {
          this.$nextTick(() => this.drawSparklines());
        }
      });
    },

    async profile() {
      this.loading = true;
      const res = await window.pqlApi.fetch(
        '/api/tables/' + encodeURIComponent(fullName) + '/profile',
        { method: 'POST', silent: true }
      );
      this.loading = false;
      if (!res.ok) {
        if (window.pqlToast) {
          window.pqlToast.error(res.error || 'Profile failed');
        }
        return;
      }
      this.columns = res.data.columns || [];
      this.deltaVersion = res.data.delta_log_version;
      this.cached = !!res.data.cached;
      this.$nextTick(() => this.drawSparklines());
    },

    async clearCache() {
      if (!window.confirm('Clear all cached statistics for this table?')) return;
      const res = await window.pqlApi.fetch(
        '/api/tables/' + encodeURIComponent(fullName) + '/stats',
        { method: 'DELETE', silent: true }
      );
      if (res.ok || res.status === 204) {
        this.columns = [];
        this.deltaVersion = null;
        this.cached = false;
      }
    },

    drawSparklines() {
      if (!window.Chart) return;
      const hosts = document.querySelectorAll('.pql-stats-sparkline');
      hosts.forEach((host) => {
        const name = host.dataset.colName;
        const col = this.columns.find((c) => c.column_name === name);
        if (!col || !Array.isArray(col.stats.top_5)) return;
        // Idempotent: wipe any previous canvas so re-profile
        // doesn't stack charts.
        host.innerHTML = '';
        const canvas = document.createElement('canvas');
        host.appendChild(canvas);
        new window.Chart(canvas, {
          type: 'bar',
          data: {
            labels: col.stats.top_5.map((e) => String(e[0] ?? '')),
            datasets: [
              {
                data: col.stats.top_5.map((e) => e[1]),
                backgroundColor: '#0d6efd',
              },
            ],
          },
          options: {
            responsive: true,
            maintainAspectRatio: false,
            animation: false,
            plugins: { legend: { display: false }, tooltip: { enabled: true } },
            scales: { x: { display: false }, y: { display: false } },
          },
        });
      });
    },
  };
}

export function tableDiscussion(ref) {
  const url = '/api/social/table/' + encodeURI(ref) + '/comments';
  return {
    ref,
    commentsLoaded: false,
    comments: [],
    draftBody: '',
    postBusy: false,

    async init() {
      await this.loadComments();
    },

    async loadComments() {
      const res = await window.pqlApi.fetch(url, { silent: true });
      if (!res.ok) {
        this.commentsLoaded = true;
        return;
      }
      this.comments = (res.data && res.data.comments) || [];
      this.commentsLoaded = true;
    },

    async submitNew() {
      const body = this.draftBody.trim();
      if (!body || this.postBusy) return;
      this.postBusy = true;
      try {
        const res = await window.pqlApi.fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ body_md: body }),
        });
        if (!res.ok) {
          if (window.pqlToast) window.pqlToast.error('Comment failed to post.');
          return;
        }
        this.draftBody = '';
        await this.loadComments();
      } finally {
        this.postBusy = false;
      }
    },

    async deleteComment(commentId) {
      if (!window.confirm('Soft-delete this comment?')) return;
      const res = await window.pqlApi.fetch(url + '/' + commentId, {
        method: 'DELETE',
      });
      if (!res.ok) {
        if (window.pqlToast) window.pqlToast.error('Delete failed.');
        return;
      }
      await this.loadComments();
    },
  };
}

export function tableReadme(ref) {
  const url = '/api/social/table/' + encodeURI(ref) + '/readme';
  return {
    ref,
    readmeLoaded: false,
    body: '',
    draftBody: '',
    editing: false,
    saveBusy: false,

    get renderedBody() {
      // Prefer the shared markdown renderer if loaded; otherwise
      // fall back to raw text so a missing dependency is visible
      // but not page-breaking.
      if (window.pqlMarkdown && window.pqlMarkdown.render) {
        return window.pqlMarkdown.render(this.body || '');
      }
      return '<pre class="small">' + this._escape(this.body || '') + '</pre>';
    },

    _escape(s) {
      return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
    },

    async init() {
      const res = await window.pqlApi.fetch(url, { silent: true });
      if (res.ok && res.data) {
        this.body = res.data.body_md || '';
      }
      this.readmeLoaded = true;
    },

    startEdit() {
      this.draftBody = this.body;
      this.editing = true;
    },

    cancelEdit() {
      this.draftBody = '';
      this.editing = false;
    },

    async save() {
      if (this.saveBusy) return;
      this.saveBusy = true;
      try {
        const res = await window.pqlApi.fetch(url, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ body_md: this.draftBody }),
          silent: true,
        });
        if (!res.ok) {
          if (window.pqlToast) {
            window.pqlToast.error(
              res.status === 403 ? 'README edit is admin-only on tables for now.' : 'Save failed.'
            );
          }
          return;
        }
        this.body = (res.data && res.data.body_md) || this.draftBody;
        this.editing = false;
      } finally {
        this.saveBusy = false;
      }
    },
  };
}
