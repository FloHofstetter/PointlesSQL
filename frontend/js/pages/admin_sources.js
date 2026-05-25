// Auto-extracted from frontend/templates/pages/admin_sources.html.
// Exports: adminSourcesList.
//
export function adminSourcesList() {
  return {
    loading: true,
    sources: [],
    filter: '',
    showFailedOnly: false,
    async load() {
      this.loading = true;
      const res = await window.pqlApi.fetch('/api/admin/ingest-sources');
      this.loading = false;
      if (res.ok && res.data) {
        this.sources = res.data.sources || [];
      }
    },
    filtered() {
      let xs = this.sources;
      if (this.showFailedOnly) {
        xs = xs.filter((s) => s.errors_7d > 0 || s.last_pull_ok === false);
      }
      const q = (this.filter || '').toLowerCase().trim();
      if (!q) return xs;
      return xs.filter((s) => (s.name + ' ' + s.kind).toLowerCase().includes(q));
    },
  };
}
