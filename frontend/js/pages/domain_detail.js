// Domain detail page (/domains/{slug}).
//
// ``domainDetail`` loads /api/domains/{slug} and exposes the domain,
// its members (owners/developers), and its owned products.

export function domainDetail(slug) {
  return {
    slug: slug,
    domain: null,
    members: [],
    products: [],
    loading: false,
    error: null,

    async init() {
      this.loading = true;
      this.error = null;
      try {
        const res = await fetch('/api/domains/' + encodeURIComponent(this.slug));
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.domain = data;
        this.members = Array.isArray(data.members) ? data.members : [];
        this.products = Array.isArray(data.products) ? data.products : [];
      } catch (e) {
        this.error = 'Failed to load domain: ' + e.message;
      } finally {
        this.loading = false;
      }
    },

    get owners() {
      return this.members.filter((m) => m.role === 'owner');
    },

    get developers() {
      return this.members.filter((m) => m.role === 'developer');
    },
  };
}
