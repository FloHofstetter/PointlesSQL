// Per-API-key admin detail page for /admin/api-keys/{name}.
// Two Alpine factories: grants editor + usage sparkline.

export function apiKeyGrants(keyName) {
  return {
    keyName,
    catalogGrants: [],
    ipGrants: [],
    newCatalog: { catalog_name: '', schema_name: '' },
    newIp: { cidr: '', label: '' },
    busy: false,

    async load() {
      const res = await window.pqlApi.fetch(
        '/api/admin/api-keys/' + encodeURIComponent(this.keyName) + '/grants'
      );
      if (res.ok) {
        this.catalogGrants = res.data.catalog_grants;
        this.ipGrants = res.data.ip_grants;
      }
    },

    async addCatalog() {
      if (!this.newCatalog.catalog_name.trim()) return;
      this.busy = true;
      const body = {
        catalog_name: this.newCatalog.catalog_name.trim(),
      };
      if (this.newCatalog.schema_name.trim()) {
        body.schema_name = this.newCatalog.schema_name.trim();
      }
      const res = await window.pqlApi.fetch(
        '/api/admin/api-keys/' + encodeURIComponent(this.keyName) + '/grants/catalog',
        { method: 'POST', body }
      );
      this.busy = false;
      if (res.ok) {
        this.newCatalog = { catalog_name: '', schema_name: '' };
        window.pqlToast?.success('Catalog grant added.');
        await this.load();
      } else {
        window.pqlToast?.error(res.error || 'Failed to add catalog grant.');
      }
    },

    async removeCatalog(id) {
      if (!window.confirm('Remove this catalog grant?')) return;
      this.busy = true;
      const res = await window.pqlApi.fetch(
        '/api/admin/api-keys/' + encodeURIComponent(this.keyName) + '/grants/catalog/' + id,
        { method: 'DELETE' }
      );
      this.busy = false;
      if (res.ok) {
        window.pqlToast?.success('Grant removed.');
        await this.load();
      } else {
        window.pqlToast?.error(res.error || 'Failed to remove grant.');
      }
    },

    async addIp() {
      if (!this.newIp.cidr.trim()) return;
      this.busy = true;
      const body = { cidr: this.newIp.cidr.trim() };
      if (this.newIp.label.trim()) body.label = this.newIp.label.trim();
      const res = await window.pqlApi.fetch(
        '/api/admin/api-keys/' + encodeURIComponent(this.keyName) + '/grants/ip',
        { method: 'POST', body }
      );
      this.busy = false;
      if (res.ok) {
        this.newIp = { cidr: '', label: '' };
        window.pqlToast?.success('IP grant added.');
        await this.load();
      } else {
        window.pqlToast?.error(res.error || 'Failed to add IP grant.');
      }
    },

    async removeIp(id) {
      if (!window.confirm('Remove this IP grant?')) return;
      this.busy = true;
      const res = await window.pqlApi.fetch(
        '/api/admin/api-keys/' + encodeURIComponent(this.keyName) + '/grants/ip/' + id,
        { method: 'DELETE' }
      );
      this.busy = false;
      if (res.ok) {
        window.pqlToast?.success('Grant removed.');
        await this.load();
      } else {
        window.pqlToast?.error(res.error || 'Failed to remove grant.');
      }
    },
  };
}

export function apiKeyUsageChart(keyName) {
  return {
    keyName,
    totalLabel: 'Loading…',
    topIps: [],
    loading: true,

    init() {
      this.load();
    },

    async load() {
      const res = await window.pqlApi.fetch(
        '/api/admin/api-keys/' + encodeURIComponent(this.keyName) + '/usage'
      );
      this.loading = false;
      if (!res.ok) {
        this.totalLabel = 'Failed to load';
        return;
      }
      const days = res.data.days;
      this.topIps = res.data.top_ips;
      const total = days.reduce((sum, d) => sum + d.count, 0);
      this.totalLabel = `${total} request${total === 1 ? '' : 's'} (30d)`;
      // Render a simple chart via a canvas without Chart.js to avoid
      // pulling in another bundle.  Vertical bars, equal width.
      const canvas = this.$refs.chart;
      if (!canvas) return;
      const ctx = canvas.getContext('2d');
      if (!ctx) return;
      const w = canvas.clientWidth || 600;
      const h = canvas.clientHeight || 100;
      canvas.width = w;
      canvas.height = h;
      ctx.clearRect(0, 0, w, h);
      const peak = Math.max(1, ...days.map((d) => d.count));
      const barWidth = Math.max(2, Math.floor(w / days.length) - 2);
      ctx.fillStyle = '#0d6efd';
      days.forEach((d, i) => {
        const barHeight = Math.round((d.count / peak) * (h - 6));
        const x = i * (barWidth + 2);
        const y = h - barHeight;
        ctx.fillRect(x, y, barWidth, barHeight);
      });
    },
  };
}
