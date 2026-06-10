// Saved-views list page factory.
export function savedViewsList() {
  return {
    loading: true,
    views: [],
    async load() {
      this.loading = true;
      const res = await window.pqlApi.fetch('/api/views');
      if (res.ok && res.data) {
        this.views = res.data.views || [];
      }
      this.loading = false;
    },
  };
}
