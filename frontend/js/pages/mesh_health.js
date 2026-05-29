// Mesh-health dashboard: per-product SLO bands rolled up across the
// workspace, plus a summary tally and worst-offenders list.  Admins can
// trigger an SLO-evaluation scan that logs failures to the audit log.

export function meshHealth(isAdmin) {
  return {
    isAdmin: !!isAdmin,
    loading: true,
    error: '',
    products: [],
    summary: {
      bands: {},
      total_products: 0,
      green_pct: null,
      pass_rate: null,
      worst_offenders: [],
    },
    scanning: false,
    scanResult: '',

    async init() {
      await this.reload();
    },

    async reload() {
      this.error = '';
      try {
        const res = await fetch('/api/mesh/health');
        if (!res.ok) {
          this.error = 'Failed to load mesh health';
          this.loading = false;
          return;
        }
        const data = await res.json();
        this.products = data.products || [];
        this.summary = data.summary || this.summary;
        this.loading = false;
      } catch (e) {
        this.error = 'Failed to load mesh health: ' + e.message;
        this.loading = false;
      }
    },

    bandClass(band) {
      if (band === 'green') return 'text-bg-success';
      if (band === 'red') return 'text-bg-danger';
      return 'text-bg-secondary';
    },

    pct(value) {
      return value === null || value === undefined ? '—' : Math.round(value) + '%';
    },

    rate(value) {
      return value === null || value === undefined ? '—' : Math.round(value * 100) + '%';
    },

    async runScan() {
      this.scanning = true;
      this.scanResult = '';
      const res = await window.pqlApi.fetch('/api/mesh/slo-scan', { method: 'POST' });
      this.scanning = false;
      if (!res.ok) {
        this.error = res.error || 'Scan failed';
        return;
      }
      const v = res.data.violations ? res.data.violations.length : 0;
      this.scanResult =
        'Scanned ' + res.data.products_scanned + ' product(s), ' + v + ' violation(s).';
      window.pqlToast.success(this.scanResult);
      await this.reload();
    },
  };
}
