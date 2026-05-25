// Auto-extracted from frontend/templates/pages/saved_view_detail.html.
// Exports: savedViewDetail.
//
export function savedViewDetail(view) {
  const initial = {};
  (view.parameters || []).forEach((p) => {
    initial[p.name] = p.default !== null && p.default !== undefined ? p.default : '';
  });
  return {
    view,
    values: initial,
    running: false,
    result: null,
    error: null,
    showSql: false,
    async run() {
      this.error = null;
      this.running = true;
      const res = await window.pqlApi.fetch('/api/views/' + this.view.slug + '/run', {
        method: 'POST',
        body: { parameters: this.values },
      });
      this.running = false;
      if (res.ok && res.data) {
        this.result = res.data;
      } else {
        this.error = (res.data && res.data.detail) || res.message || 'Run failed';
      }
    },
    copyEmbed() {
      const url = window.location.origin + '/views/' + this.view.slug + '/embed';
      navigator.clipboard.writeText(url);
    },
    copyJsonRows() {
      if (!this.result) return;
      const payload = {
        columns: this.result.columns.map((c) => c.name),
        rows: this.result.rows,
      };
      navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
    },
  };
}
