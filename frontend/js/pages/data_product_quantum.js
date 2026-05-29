// Quantum panels for the data-product detail page (Overview tab):
// declared output/input ports, the semantic model + sample SQL, the
// self-generated statistics snapshot, and the discovery URI card.
//
// Each factory is self-contained and fetches its own sub-endpoint,
// mirroring dataProductDomainPanel. Mutations go through window.pqlApi
// (steward/admin-gated server-side); the canManage flag only toggles
// the editing affordances in the UI.

function dpBase(catalog, schema) {
  return '/api/data-products/' + encodeURIComponent(catalog) + '/' + encodeURIComponent(schema);
}

export function dataProductPortsPanel(catalog, schema, canManage) {
  return {
    catalog: catalog,
    schema: schema,
    canManage: !!canManage,
    outputPorts: [],
    inputPorts: [],
    error: '',
    newOutput: { name: '', kind: 'file', format: '', description: '' },
    newInput: { name: '', kind: 'upstream_product', source_ref: '', description: '' },

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      try {
        const outRes = await fetch(dpBase(this.catalog, this.schema) + '/output-ports');
        if (outRes.ok) this.outputPorts = (await outRes.json()).output_ports || [];
        const inRes = await fetch(dpBase(this.catalog, this.schema) + '/input-ports');
        if (inRes.ok) this.inputPorts = (await inRes.json()).input_ports || [];
      } catch (e) {
        this.error = 'Failed to load ports: ' + e.message;
      }
    },

    upstreamHref(port) {
      // upstream_product source_ref is "catalog.schema".
      if (port.kind !== 'upstream_product' || !port.source_ref) return null;
      const parts = port.source_ref.split('.');
      if (parts.length < 2) return null;
      return '/data-products/' + encodeURIComponent(parts[0]) + '/' + encodeURIComponent(parts[1]);
    },

    async addOutput() {
      this.error = '';
      if (!this.newOutput.name.trim()) {
        this.error = 'Output port name is required';
        return;
      }
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/output-ports', {
        method: 'POST',
        body: { ...this.newOutput },
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to add output port';
        return;
      }
      this.newOutput = { name: '', kind: 'file', format: '', description: '' };
      await this.reload();
    },

    async addInput() {
      this.error = '';
      if (!this.newInput.name.trim()) {
        this.error = 'Input port name is required';
        return;
      }
      const res = await window.pqlApi.fetch(dpBase(this.catalog, this.schema) + '/input-ports', {
        method: 'POST',
        body: { ...this.newInput },
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to add input port';
        return;
      }
      this.newInput = { name: '', kind: 'upstream_product', source_ref: '', description: '' };
      await this.reload();
    },

    async removeOutput(id) {
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/output-ports/' + id,
        { method: 'DELETE' }
      );
      if (res.ok) await this.reload();
    },

    async removeInput(id) {
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/input-ports/' + id,
        { method: 'DELETE' }
      );
      if (res.ok) await this.reload();
    },
  };
}

export function dataProductSemanticPanel(catalog, schema, canManage) {
  return {
    catalog: catalog,
    schema: schema,
    canManage: !!canManage,
    concepts: [],
    sampleSql: '',
    editingSql: '',
    error: '',
    newConcept: { concept: '', description: '', maps_to: '' },

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/semantic');
        if (res.ok) {
          const data = await res.json();
          this.concepts = data.concepts || [];
          this.sampleSql = data.sample_sql || '';
          this.editingSql = this.sampleSql;
        }
      } catch (e) {
        this.error = 'Failed to load semantic model: ' + e.message;
      }
    },

    async addConcept() {
      this.error = '';
      if (!this.newConcept.concept.trim()) {
        this.error = 'Concept is required';
        return;
      }
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/semantic/concepts',
        { method: 'POST', body: { ...this.newConcept } }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to add concept';
        return;
      }
      this.newConcept = { concept: '', description: '', maps_to: '' };
      await this.reload();
    },

    async removeConcept(id) {
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/semantic/concepts/' + id,
        { method: 'DELETE' }
      );
      if (res.ok) await this.reload();
    },

    async saveSql() {
      const res = await window.pqlApi.fetch(
        dpBase(this.catalog, this.schema) + '/semantic/sample-sql',
        { method: 'PUT', body: { sample_sql: this.editingSql } }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to save sample SQL';
        return;
      }
      this.sampleSql = this.editingSql;
      window.pqlToast.success('Sample SQL saved.');
    },
  };
}

export function dataProductStatsPanel(catalog, schema) {
  return {
    catalog: catalog,
    schema: schema,
    stats: [],
    error: '',

    async init() {
      try {
        const res = await fetch(dpBase(this.catalog, this.schema) + '/statistics');
        if (res.ok) this.stats = (await res.json()).statistics || [];
      } catch (e) {
        this.error = 'Failed to load statistics: ' + e.message;
      }
    },

    columnCount(row) {
      return row.shape && row.shape.column_count != null ? row.shape.column_count : '—';
    },
  };
}

export function dataProductDiscoveryCard(catalog, schema) {
  return {
    catalog: catalog,
    schema: schema,
    uri: '',
    discoveryHref: '',

    async init() {
      this.discoveryHref = dpBase(this.catalog, this.schema) + '/discovery';
      try {
        const res = await fetch(this.discoveryHref);
        if (res.ok) this.uri = (await res.json()).uri || '';
      } catch (e) {
        this.uri = '';
      }
    },

    async copyUri() {
      if (!this.uri) return;
      try {
        await navigator.clipboard.writeText(this.uri);
        window.pqlToast.success('Discovery URI copied.');
      } catch (e) {
        window.pqlToast.error('Copy failed: ' + e.message);
      }
    },
  };
}
