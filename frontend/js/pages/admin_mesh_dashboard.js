// Admin mesh-dashboard (/admin/mesh-dashboard).
//
// Exports: adminMeshDashboard — vital-signs + cost-by-product + top consumers.

export function adminMeshDashboard() {
  return {
    health: null,
    costByProduct: [],
    topConsumers: [],
    totalCost: 0,
    error: '',
    loading: false,

    async load() {
      this.loading = true;
      this.error = '';
      const [healthRes, costRes, consumersRes] = await Promise.all([
        window.pqlApi.fetch('/api/mesh/health/full'),
        window.pqlApi.fetch('/api/cost/by-product'),
        window.pqlApi.fetch('/api/cost/by-consumer'),
      ]);
      this.loading = false;
      if (!healthRes.ok || !costRes.ok || !consumersRes.ok) {
        this.error = 'Failed to load mesh-dashboard data';
        return;
      }
      this.health = healthRes.json;
      this.costByProduct = costRes.json?.products || [];
      this.topConsumers = (consumersRes.json?.consumers || []).slice(0, 10);
      this.totalCost = this.costByProduct.reduce(
        (sum, row) => sum + (row.total_estimated_cost || 0),
        0
      );
    },
  };
}
