/**
 * Data-product detail page — Schema / consumer Data tab — friendly types, sample previews, forks, heatmap.
 *
 * One slice of the ``dataProductDetail`` Alpine factory.  ``installDpSchema``
 * mutates the shared component object in place (the project's mixin-installer
 * pattern); ``this`` resolves to the live component at call time, so the
 * method bodies are unchanged from the original single-file factory.
 */

export function installDpSchema(state) {
  Object.assign(state, {

    async copySnippet(kind) {
      const snip = this.consumeSnippets[kind];
      if (snip) navigator.clipboard.writeText(snip);
    },

    /**
     * Map a contract column type to a plain-language label a
     * non-technical consumer understands. The raw type stays on the
     * row's ``title`` for the engineer reading the same column.
     *
     * @param {string} type - one of the contract primitive types.
     * @returns {string} a human-friendly type name.
     */
    friendlyType(type) {
      const map = {
        string: 'Text',
        integer: 'Whole number',
        long: 'Whole number',
        double: 'Decimal number',
        decimal: 'Decimal number',
        boolean: 'Yes / no',
        timestamp: 'Date & time',
        date: 'Date',
        binary: 'Binary',
        array: 'List',
        struct: 'Nested record',
      };
      if (map[type]) return map[type];
      const t = String(type || '');
      return t ? t.charAt(0).toUpperCase() + t.slice(1) : 'Value';
    },

    /**
     * Render a column's nullability as a consumer-facing word.
     *
     * @param {boolean} nullable - the contract nullable flag.
     * @returns {string} "optional" when nullable, else "required".
     */
    friendlyNullable(nullable) {
      return nullable ? 'optional' : 'required';
    },

    /**
     * Toggle the inline sample-data panel for one contract table,
     * fetching the first rows from the shared catalog-preview endpoint
     * on first open. Objects are reassigned (not mutated in place) so
     * Alpine's reactivity picks up the per-table keys.
     *
     * @param {string} name - the contract table name.
     */
    async toggleSample(name) {
      const open = !this.sampleOpen[name];
      this.sampleOpen = { ...this.sampleOpen, [name]: open };
      if (!open || this.samples[name]) return;
      this.sampleLoading = { ...this.sampleLoading, [name]: true };
      const fallback = {
        error: 'preview_unavailable',
        detail: 'Sample data could not be loaded.',
      };
      try {
        const res = await fetch(
          '/api/catalogs/' +
            encodeURIComponent(this.product.catalog) +
            '/schemas/' +
            encodeURIComponent(this.product.schema) +
            '/tables/' +
            encodeURIComponent(name) +
            '/preview'
        );
        const data = res.ok ? await res.json() : fallback;
        this.samples = { ...this.samples, [name]: data };
      } catch (e) {
        console.error('sample preview failed', e);
        this.samples = { ...this.samples, [name]: fallback };
      } finally {
        this.sampleLoading = { ...this.sampleLoading, [name]: false };
      }
    },
    async loadForks() {
      this.forksLoaded = false;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/forks'
        );
        if (!res.ok) {
          this.forks = [];
          return;
        }
        const data = await res.json();
        this.forks = data.forks || [];
      } catch (e) {
        console.error('forks load failed', e);
        this.forks = [];
      } finally {
        this.forksLoaded = true;
      }
    },
    async loadHeatmap() {
      this.heatmapLoaded = false;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/heatmap'
        );
        if (!res.ok) {
          this.heatmap = { cells: [], total: 0 };
          return;
        }
        this.heatmap = await res.json();
      } catch (e) {
        console.error('heatmap load failed', e);
        this.heatmap = { cells: [], total: 0 };
      } finally {
        this.heatmapLoaded = true;
      }
    }
  });
}
