// Mesh-entity registry browse page: the polysemic identifiers shared
// across the mesh, each with the columns it is bound to.  Read-only;
// entities are managed under /admin/mesh-entities.

export function meshEntities() {
  return {
    loading: true,
    error: '',
    entities: [],
    filter: '',

    async init() {
      try {
        const res = await fetch('/api/mesh/entities');
        if (!res.ok) {
          this.error = 'Failed to load mesh entities';
          this.loading = false;
          return;
        }
        const data = await res.json();
        this.entities = data.entities || [];
        this.loading = false;
      } catch (e) {
        this.error = 'Failed to load mesh entities: ' + e.message;
        this.loading = false;
      }
    },

    get filtered() {
      const q = this.filter.trim().toLowerCase();
      if (!q) return this.entities;
      return this.entities.filter(
        (e) => e.name.toLowerCase().includes(q) || e.slug.toLowerCase().includes(q)
      );
    },
  };
}
