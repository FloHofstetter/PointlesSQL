// Workspace mesh-graph browse page: the emergent dependency graph
// (products as nodes, declared upstream input-ports as edges) rendered
// with cytoscape, plus a small node legend.

export function meshGraph() {
  return {
    loading: true,
    error: '',
    nodeCount: 0,
    edgeCount: 0,

    async init() {
      try {
        const res = await fetch('/api/mesh/graph');
        if (!res.ok) {
          this.error = 'Failed to load mesh graph';
          this.loading = false;
          return;
        }
        const data = await res.json();
        this.nodeCount = (data.nodes || []).length;
        this.edgeCount = (data.edges || []).length;
        this.loading = false;
        this.$nextTick(() => this.render(data));
      } catch (e) {
        this.error = 'Failed to load mesh graph: ' + e.message;
        this.loading = false;
      }
    },

    async render(data) {
      if (!data.nodes || data.nodes.length === 0) return;
      try {
        if (typeof window.loadCytoscapeOnce === 'function') await window.loadCytoscapeOnce();
        if (typeof cytoscape !== 'function') return;
        cytoscape({
          container: document.getElementById('mesh-cy'),
          elements: {
            nodes: data.nodes.map((n) => ({
              data: { id: n.id, label: n.ref, domain: n.domain ? n.domain.slug : '' },
            })),
            edges: data.edges.map((e) => ({
              data: { source: e.source, target: e.target, label: e.port_name },
            })),
          },
          layout: { name: 'breadthfirst', directed: true, spacingFactor: 1.2 },
          style: [
            {
              selector: 'node',
              style: {
                label: 'data(label)',
                'font-size': '10px',
                'background-color': '#0d6efd',
                color: '#212529',
                'text-valign': 'bottom',
                'text-margin-y': 3,
              },
            },
            {
              selector: 'edge',
              style: {
                'curve-style': 'bezier',
                'target-arrow-shape': 'triangle',
                'line-color': '#adb5bd',
                'target-arrow-color': '#adb5bd',
                width: 1.5,
              },
            },
          ],
        });
      } catch (e) {
        console.error('mesh graph render failed', e);
      }
    },
  };
}
