// Admin entity-discovery review queue (/admin/entity-discovery).
//
// Exports: adminEntityDiscovery — pending list + accept/reject/defer/run-now.

export function adminEntityDiscovery() {
  return {
    candidates: [],
    loading: false,
    error: '',

    async load() {
      this.loading = true;
      this.error = '';
      const res = await window.pqlApi.fetch('/api/entity-link-candidates?status=pending');
      this.loading = false;
      if (!res.ok) {
        this.error = res.error || 'Failed to load candidates';
        return;
      }
      this.candidates = res.data?.candidates || [];
    },

    async decide(candidateId, verb) {
      const res = await window.pqlApi.fetch(
        '/api/entity-link-candidates/' + candidateId + '/' + verb,
        { method: 'POST' }
      );
      if (!res.ok) return;
      await this.load();
    },

    async runNow() {
      const res = await window.pqlApi.fetch('/api/admin/entity-discovery/run-now', {
        method: 'POST',
      });
      if (!res.ok) {
        this.error = res.error || 'Discovery run failed';
        return;
      }
      await this.load();
    },
  };
}
