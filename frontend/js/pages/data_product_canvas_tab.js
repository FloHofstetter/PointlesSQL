/*
 * Canvas tab on the data-product detail page — Alpine factory.
 *
 * A lightweight summary card that links to the standalone visual editor
 * and lazy-loads the canvas version list when the tab is first shown, so
 * the initial detail-page render isn't blocked by an extra round-trip for
 * users who never open the Canvas tab.
 */

/**
 * @param {{id: number}} product - the data product the detail page renders.
 */
export function dataProductCanvasTab(product) {
  return {
    product,
    versions: null,
    loading: false,
    error: null,
    async load() {
      if (this.versions !== null || this.loading) return;
      this.loading = true;
      const res = await window.pqlApi.fetch(`/api/dp/${this.product.id}/canvas/versions`, {
        silent: true,
      });
      this.loading = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to load versions';
        return;
      }
      this.versions = res.data.versions || [];
    },
  };
}
