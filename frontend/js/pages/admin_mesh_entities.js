// Admin mesh-entity registry: create + delete the polysemic identifiers
// the mesh shares.  Bindings to product columns happen on each product's
// Interop tab, so this page manages the entity names only.

export function adminMeshEntities() {
  return {
    loading: true,
    error: '',
    entities: [],
    newEntity: { name: '', slug: '', description: '' },

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      try {
        const res = await fetch('/api/admin/mesh-entities');
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

    async create() {
      this.error = '';
      if (!this.newEntity.name.trim()) {
        this.error = 'Name is required';
        return;
      }
      const res = await window.pqlApi.fetch('/api/admin/mesh-entities', {
        method: 'POST',
        body: { ...this.newEntity },
      });
      if (!res.ok) {
        this.error = res.error || 'Failed to create entity';
        return;
      }
      this.newEntity = { name: '', slug: '', description: '' };
      await this.reload();
    },

    async remove(id) {
      const res = await window.pqlApi.fetch('/api/admin/mesh-entities/' + id, { method: 'DELETE' });
      if (res.ok) await this.reload();
    },
  };
}
