// Interop tab + SLO panel for the data-product detail page.
//
// dataProductInterop: the product's neighbourhood in the mesh graph,
// polysemic-entity bindings (+ "joinable on" hints across products), a
// point-in-time read manifest, and the bitemporal convention status.
//
// dataProductSloPanel: declared service-level objectives + their live
// verdicts and pass-rate chip, shown on the Overview tab.
//
// Both fetch product-scoped aggregates; mutations go through
// window.pqlApi (steward/admin-gated server-side). canManage comes back
// in the aggregate so the templates never need is_steward.

function dpBase(catalog, schema) {
  return '/api/data-products/' + encodeURIComponent(catalog) + '/' + encodeURIComponent(schema);
}

export function dataProductInterop(catalog, schema) {
  return {
    catalog: catalog,
    schema: schema,
    canManage: false,
    loaded: false,
    error: '',
    neighbourhood: { nodes: [], edges: [], center: null },
    bindings: [],
    availableEntities: [],
    bitemporal: {},
    newBinding: { entity_slug: '', table: '', column: '' },
    joinOther: '',
    joinSuggestions: null,
    joinError: '',
    pit: { when: '', products: '' },
    pitManifest: null,
    pitError: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/interop');
        if (!res.ok) {
          this.error = 'Failed to load interop';
          return;
        }
        const data = await res.json();
        this.canManage = !!data.can_manage;
        this.neighbourhood = data.neighbourhood || { nodes: [], edges: [], center: null };
        this.bindings = data.bindings || [];
        this.availableEntities = data.available_entities || [];
        this.bitemporal = data.bitemporal || {};
        this.loaded = true;
        this.$nextTick(() => this.renderGraph());
      } catch (e) {
        this.error = 'Failed to load interop: ' + e.message;
      }
    },

    async renderGraph() {
      const nodes = this.neighbourhood.nodes || [];
      if (nodes.length === 0) return;
      try {
        if (typeof window.loadCytoscapeOnce === 'function') await window.loadCytoscapeOnce();
        if (typeof cytoscape !== 'function') return;
        const center = this.neighbourhood.center;
        cytoscape({
          container: document.getElementById('dp-mesh-cy'),
          elements: {
            nodes: nodes.map((n) => ({
              data: { id: n.id, label: n.ref, center: n.ref === center ? 1 : 0 },
            })),
            edges: (this.neighbourhood.edges || []).map((e) => ({
              data: { source: e.source, target: e.target, label: e.port_name },
            })),
          },
          layout: { name: 'breadthfirst', directed: true },
          style: [
            {
              selector: 'node',
              style: {
                label: 'data(label)',
                'font-size': '9px',
                'background-color': '#0d6efd',
              },
            },
            { selector: 'node[center = 1]', style: { 'background-color': '#dc3545' } },
            {
              selector: 'edge',
              style: { 'curve-style': 'bezier', 'target-arrow-shape': 'triangle', width: 1 },
            },
          ],
        });
      } catch (e) {
        console.error('mesh neighbourhood render failed', e);
      }
    },

    async bindEntity() {
      this.error = '';
      if (
        !this.newBinding.entity_slug ||
        !this.newBinding.table.trim() ||
        !this.newBinding.column.trim()
      ) {
        this.error = 'Entity, table and column are required';
        return;
      }
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/entities', {
        method: 'POST',
        body: { ...this.newBinding },
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to bind entity';
        return;
      }
      this.newBinding = { entity_slug: '', table: '', column: '' };
      await this.reload();
    },

    async removeBinding(id) {
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/entities/' + id, {
        method: 'DELETE',
      });
      if (res.ok) await this.reload();
    },

    async loadJoinable() {
      this.joinError = '';
      this.joinSuggestions = null;
      if (!this.joinOther.trim()) {
        this.joinError = 'Enter a catalog.schema to compare';
        return;
      }
      const url =
        dpBase(this.catalog, this.schema) +
        '/joinable?other=' +
        encodeURIComponent(this.joinOther.trim());
      const res = await fetch(url);
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        this.joinError = (data.error && data.error.message) || 'Failed to compute join keys';
        return;
      }
      const data = await res.json();
      this.joinSuggestions = data.suggestions || [];
    },

    async runPointInTime() {
      this.pitError = '';
      this.pitManifest = null;
      if (!this.pit.when) {
        this.pitError = 'Pick an as-of timestamp';
        return;
      }
      const products = this.pit.products
        .split(',')
        .map((s) => s.trim())
        .filter((s) => s.length > 0);
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/point-in-time-read',
        {
          method: 'POST',
          body: { when: new Date(this.pit.when).toISOString(), products: products },
        }
      );
      if (!res.ok) {
        this.pitError = res.error || 'Point-in-time read failed';
        return;
      }
      this.pitManifest = res.data;
    },
  };
}

export function dataProductSloPanel(catalog, schema, canManage) {
  return {
    catalog: catalog,
    schema: schema,
    canManage: !!canManage,
    loaded: false,
    error: '',
    slos: [],
    kinds: {},
    evaluation: { results: [], passed: 0, failed: 0, unmeasured: 0, pass_rate: null },
    newSlo: { slo_kind: 'volume', target_value: '', table: '', comparator: '', unit: '' },

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      try {
        const [slosRes, evalRes] = await Promise.all([
          fetch(dpBase(this.catalog, this.schema) + '/slos'),
          fetch(dpBase(this.catalog, this.schema) + '/slo-evaluation'),
        ]);
        if (slosRes.ok) {
          const data = await slosRes.json();
          this.slos = data.slos || [];
          this.kinds = data.kinds || {};
        }
        if (evalRes.ok) this.evaluation = await evalRes.json();
        this.loaded = true;
      } catch (e) {
        this.error = 'Failed to load SLOs: ' + e.message;
      }
    },

    passRateLabel() {
      const r = this.evaluation.pass_rate;
      if (r === null || r === undefined) return '—';
      return Math.round(r * 100) + '%';
    },

    passRateClass() {
      const r = this.evaluation.pass_rate;
      if (r === null || r === undefined) return 'bg-secondary';
      if (this.evaluation.failed > 0) return 'bg-danger';
      return r >= 1 ? 'bg-success' : 'bg-warning text-dark';
    },

    verdictClass(v) {
      if (v === 'pass') return 'text-bg-success';
      if (v === 'fail') return 'text-bg-danger';
      return 'text-bg-secondary';
    },

    async declare() {
      this.error = '';
      if (!this.newSlo.slo_kind) {
        this.error = 'Pick an SLO kind';
        return;
      }
      const body = {
        slo_kind: this.newSlo.slo_kind,
        target_value: this.newSlo.target_value === '' ? null : Number(this.newSlo.target_value),
        table: this.newSlo.table || null,
        comparator: this.newSlo.comparator || null,
        unit: this.newSlo.unit || null,
      };
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/slos', {
        method: 'POST',
        body: body,
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to declare SLO';
        return;
      }
      this.newSlo = { slo_kind: 'volume', target_value: '', table: '', comparator: '', unit: '' };
      await this.reload();
    },

    async remove(id) {
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/slos/' + id, {
        method: 'DELETE',
      });
      if (res.ok) await this.reload();
    },
  };
}
