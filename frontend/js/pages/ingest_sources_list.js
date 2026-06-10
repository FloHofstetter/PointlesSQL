// Ingest-sources list page factory.
export function ingestSourcesList() {
  return {
    loading: true,
    sources: [],
    async load() {
      this.loading = true;
      const res = await window.pqlApi.fetch('/api/ingest/sources');
      if (res.ok && res.data) {
        this.sources = res.data.sources || [];
      }
      this.loading = false;
    },
  };
}
