// Admin glossary cockpit (/admin/glossary).
//
// adminGlossary: create-term form + per-row delete + per-row column
// binding management (add/remove a catalog.schema.table.column binding).

export function adminGlossary() {
  return {
    form: { slug: '', term: '', definition: '' },
    creating: false,
    error: '',
    bindings: {},
    open: {},
    drafts: {},

    async create() {
      this.error = '';
      this.creating = true;
      const body = { slug: this.form.slug.trim(), term: this.form.term.trim() };
      if (this.form.definition) body.definition = this.form.definition.trim();
      const res = await window.pqlApi.fetch('/api/admin/glossary', { method: 'POST', body: body });
      this.creating = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to create term';
        return;
      }
      window.pqlApi.reloadWithToast('Glossary term created.');
    },

    async deleteTerm(termId, slug) {
      if (!window.confirm('Delete glossary term "' + slug + '" and all its bindings?')) return;
      const res = await window.pqlApi.fetch('/api/admin/glossary/' + termId, { method: 'DELETE' });
      if (!res.ok) return;
      window.pqlApi.reloadWithToast('Glossary term deleted.');
    },

    async toggle(termId) {
      this.open[termId] = !this.open[termId];
      if (this.open[termId]) {
        if (!this.drafts[termId]) {
          this.drafts[termId] = { catalog: '', schema: '', table: '', column: '' };
        }
        if (!this.bindings[termId]) await this.loadBindings(termId);
      }
    },

    async loadBindings(termId) {
      const res = await window.pqlApi.fetch('/api/admin/glossary/' + termId + '/bindings');
      if (!res.ok) return;
      this.bindings[termId] = (res.data && res.data.bindings) || [];
    },

    async bind(termId, draft) {
      this.error = '';
      const body = {
        catalog: (draft.catalog || '').trim(),
        schema: (draft.schema || '').trim(),
        table: (draft.table || '').trim(),
        column: (draft.column || '').trim(),
      };
      const res = await window.pqlApi.fetch('/api/admin/glossary/' + termId + '/bindings', {
        method: 'POST',
        body: body,
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to bind column';
        return;
      }
      draft.catalog = draft.schema = draft.table = draft.column = '';
      await this.loadBindings(termId);
    },

    async unbind(termId, bindingId) {
      const res = await window.pqlApi.fetch(
        '/api/admin/glossary/' + termId + '/bindings/' + bindingId,
        { method: 'DELETE' }
      );
      if (!res.ok) return;
      await this.loadBindings(termId);
    },
  };
}
