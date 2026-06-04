/**
 * Data-product detail page — Diff and Cytoscape lineage tabs.
 *
 * One slice of the ``dataProductDetail`` Alpine factory.  ``installDpInsights``
 * mutates the shared component object in place (the project's mixin-installer
 * pattern); ``this`` resolves to the live component at call time, so the
 * method bodies are unchanged from the original single-file factory.
 */

export function installDpInsights(state) {
  Object.assign(state, {

    async loadDiff() {
      this.diffLoading = true;
      this.diffError = null;
      try {
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/diff'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        this.diff = await res.json();
      } catch (e) {
        this.diffError = 'Diff failed: ' + e.message;
      } finally {
        this.diffLoading = false;
      }
    },

    async loadLineage() {
      try {
        if (typeof window.loadCytoscapeOnce === 'function') {
          await window.loadCytoscapeOnce();
        }
        const res = await fetch(
          '/api/data-products/' + this.product.catalog + '/' + this.product.schema + '/lineage'
        );
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        if (!data.nodes || data.nodes.length === 0) {
          this.lineageEmpty = true;
          this.lineageLoaded = true;
          return;
        }
        this.lineageLoaded = true;
        if (typeof window.renderModelGraph === 'function') {
          window.renderModelGraph('dp-cy', data);
        } else if (typeof cytoscape === 'function') {
          cytoscape({
            container: document.getElementById('dp-cy'),
            elements: { nodes: data.nodes, edges: data.edges },
            layout: { name: 'breadthfirst' },
            style: [
              { selector: 'node', style: { label: 'data(label)', 'background-color': '#0d6efd' } },
              {
                selector: 'edge',
                style: { 'curve-style': 'bezier', 'target-arrow-shape': 'triangle' },
              },
            ],
          });
        }
      } catch (e) {
        console.error('lineage load failed', e);
        this.lineageEmpty = true;
        this.lineageLoaded = true;
      }
    }
  });
}
