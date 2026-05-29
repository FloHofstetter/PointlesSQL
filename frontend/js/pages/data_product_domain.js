// Data-product domain + transformation panel (data-product detail page).
//
// Self-contained factory used in the Overview tab: shows the product's
// owning domain (with an assign control for steward/admin) and the list
// of bound transformations (notebook / dbt model).

export function dataProductDomainPanel(catalog, schema, canManage) {
  return {
    catalog: catalog,
    schema: schema,
    canManage: !!canManage,
    domain: null,
    domains: [],
    transformations: [],
    selectedDomainId: '',
    bindKind: 'notebook',
    bindNotebookId: '',
    bindDbtModel: '',
    loading: false,
    error: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.loading = true;
      this.error = '';
      try {
        const dpRes = await fetch(
          '/api/data-products/' +
            encodeURIComponent(this.catalog) +
            '/' +
            encodeURIComponent(this.schema)
        );
        if (dpRes.ok) {
          const detail = await dpRes.json();
          this.domain = (detail.product && detail.product.domain) || null;
          this.selectedDomainId = this.domain ? String(this.domain.id) : '';
        }
        const txRes = await fetch(
          '/api/data-products/' +
            encodeURIComponent(this.catalog) +
            '/' +
            encodeURIComponent(this.schema) +
            '/transformations'
        );
        if (txRes.ok) {
          const txData = await txRes.json();
          this.transformations = txData.transformations || [];
        }
        if (this.canManage && this.domains.length === 0) {
          const dRes = await fetch('/api/domains');
          if (dRes.ok) {
            const dData = await dRes.json();
            this.domains = dData.domains || [];
          }
        }
      } catch (e) {
        this.error = 'Failed to load domain info: ' + e.message;
      } finally {
        this.loading = false;
      }
    },

    async assign() {
      this.error = '';
      const domainId = this.selectedDomainId ? parseInt(this.selectedDomainId, 10) : null;
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          encodeURIComponent(this.catalog) +
          '/' +
          encodeURIComponent(this.schema) +
          '/domain',
        { method: 'PATCH', body: { domain_id: domainId } }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to assign domain';
        return;
      }
      window.pqlApi.reloadWithToast(domainId ? 'Domain assigned.' : 'Domain cleared.');
    },

    async bind() {
      this.error = '';
      const body = { kind: this.bindKind };
      if (this.bindKind === 'notebook') {
        if (!this.bindNotebookId.trim()) {
          this.error = 'Notebook id is required';
          return;
        }
        body.notebook_id = this.bindNotebookId.trim();
      } else {
        if (!this.bindDbtModel.trim()) {
          this.error = 'dbt model name is required';
          return;
        }
        body.dbt_model_name = this.bindDbtModel.trim();
      }
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          encodeURIComponent(this.catalog) +
          '/' +
          encodeURIComponent(this.schema) +
          '/transformations',
        { method: 'POST', body: body }
      );
      if (!res.ok) {
        this.error = res.error || 'Failed to bind transformation';
        return;
      }
      this.bindNotebookId = '';
      this.bindDbtModel = '';
      await this.reload();
    },

    async unbind(id) {
      const res = await window.pqlApi.fetch(
        '/api/data-products/' +
          encodeURIComponent(this.catalog) +
          '/' +
          encodeURIComponent(this.schema) +
          '/transformations/' +
          id,
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      await this.reload();
    },
  };
}
