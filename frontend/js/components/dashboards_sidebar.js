// Auto-extracted from frontend/templates/components/dashboards_sidebar.html.
// Single ``dashboardTree`` Alpine factory.  The original IIFE shape
// defined ``slugFromUrl`` as a sibling helper — inlined here as a
// module-local helper.

const STORAGE_KEY = 'pql.dashboards';

function slugFromUrl() {
  const m = window.location.pathname.match(/^\/dashboards\/([^/]+)/);
  return m ? m[1] : '';
}

export function dashboardTree() {
  return {
    items: null,
    loading: false,
    error: null,
    activeSlug: slugFromUrl(),

    async load() {
      try {
        const cached = sessionStorage.getItem(STORAGE_KEY);
        if (cached) this.items = JSON.parse(cached);
      } catch (_e) {
        /* swallow */
      }

      if (!this.items) await this.fetchItems();
      else this.fetchItems();
    },

    async reload() {
      try {
        sessionStorage.removeItem(STORAGE_KEY);
      } catch (_e) {
        /* swallow */
      }
      this.items = null;
      await this.fetchItems();
    },

    async fetchItems() {
      this.loading = true;
      this.error = null;
      try {
        const res = await fetch('/api/dashboards/tree');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.items = data;
        try {
          sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        } catch (_e) {
          /* swallow */
        }
      } catch (e) {
        if (!this.items) this.error = 'Failed to load dashboards: ' + e.message;
      } finally {
        this.loading = false;
      }
    },
  };
}
