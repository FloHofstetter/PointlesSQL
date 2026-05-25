// Auto-extracted from frontend/templates/pages/data_products_candidates.html.
// Exports: dataProductsCandidates.
//
export function dataProductsCandidates(initial, isAdmin) {
  return {
    rows: initial || [],
    isAdmin: !!isAdmin,
    lastDraftPath: '',

    init() {},

    async dismiss(row) {
      try {
        const res = await fetch('/api/data-products/candidates/' + row.id + '/dismiss', {
          method: 'POST',
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        row.status = 'dismissed';
      } catch (e) {
        console.error('dismiss failed', e);
      }
    },

    async generate(row) {
      try {
        const res = await fetch('/api/data-products/candidates/' + row.id + '/generate-draft', {
          method: 'POST',
        });
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.lastDraftPath = data.draft_path || '';
      } catch (e) {
        console.error('generate draft failed', e);
      }
    },
  };
}
