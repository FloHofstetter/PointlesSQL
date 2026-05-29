// Glossary browse + detail pages (/glossary, /glossary/{slug}).
//
// glossaryBrowse: loads /api/glossary with a client-side text filter.
// glossaryDetail: loads /api/glossary/{slug} (definition + bindings).

export function glossaryBrowse() {
  return {
    terms: [],
    filter: '',
    loading: false,
    error: null,

    async init() {
      await this.reload();
    },

    async reload() {
      this.loading = true;
      this.error = null;
      try {
        const res = await fetch('/api/glossary');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.terms = Array.isArray(data.terms) ? data.terms : [];
      } catch (e) {
        this.error = 'Failed to load glossary: ' + e.message;
      } finally {
        this.loading = false;
      }
    },

    get filtered() {
      const needle = this.filter.trim().toLowerCase();
      if (!needle) return this.terms;
      return this.terms.filter(
        (t) =>
          (t.term || '').toLowerCase().includes(needle) ||
          (t.slug || '').toLowerCase().includes(needle) ||
          (t.definition || '').toLowerCase().includes(needle)
      );
    },
  };
}

export function glossaryDetail(slug) {
  return {
    slug: slug,
    term: null,
    bindings: [],
    loading: false,
    error: null,

    async init() {
      this.loading = true;
      this.error = null;
      try {
        const res = await fetch('/api/glossary/' + encodeURIComponent(this.slug));
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.term = data;
        this.bindings = data.bindings || [];
      } catch (e) {
        this.error = 'Failed to load term: ' + e.message;
      } finally {
        this.loading = false;
      }
    },

    columnHref(b) {
      return (
        '/catalogs/' +
        encodeURIComponent(b.catalog) +
        '/schemas/' +
        encodeURIComponent(b.schema) +
        '/tables/' +
        encodeURIComponent(b.table)
      );
    },
  };
}
