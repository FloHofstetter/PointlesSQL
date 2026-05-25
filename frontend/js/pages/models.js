// Auto-extracted from frontend/templates/pages/models.html.
// Exports: modelsBrowse.
//
// ``catalogs`` was a Jinja-injected literal in the IIFE body; now
// passed in as a constructor arg so this module stays Jinja-free.
export function modelsBrowse(catalogs) {
  return {
    catalogs: catalogs || [],
    catalogName: '',
    schemaName: '',
    models: [],
    loading: false,
    error: null,

    async init() {
      await this.reload();
    },

    async onCatalogChange() {
      if (!this.catalogName) this.schemaName = '';
      await this.reload();
    },

    async reload() {
      this.loading = true;
      this.error = null;
      try {
        const params = new URLSearchParams({ enrich_latest: '1' });
        if (this.catalogName) params.set('catalog_name', this.catalogName);
        if (this.schemaName) params.set('schema_name', this.schemaName);
        const res = await fetch('/api/models?' + params.toString());
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.models = Array.isArray(data.models) ? data.models : [];
      } catch (e) {
        this.error = 'Failed to load models: ' + e.message;
      } finally {
        this.loading = false;
      }
    },
  };
}
