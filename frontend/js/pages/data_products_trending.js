// Auto-extracted from frontend/templates/pages/data_products_trending.html.
// Exports: dataProductsTrending.
//
export function dataProductsTrending(initial, canCrossWorkspace) {
  return {
    rows: initial || [],
    scope: 'current',
    canCrossWorkspace: !!canCrossWorkspace,

    init() {
      /* server already rendered the initial table */
    },

    async reload() {
      try {
        const params = new URLSearchParams({ workspace_scope: this.scope, limit: '10' });
        const res = await fetch('/api/data-products/trending?' + params.toString());
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.rows = data.trending || [];
      } catch (e) {
        console.error('trending reload failed', e);
      }
    },
  };
}
