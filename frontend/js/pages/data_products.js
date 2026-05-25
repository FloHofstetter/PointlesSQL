// Data-product browse page (/data-products).
//
// Single ``dataProductsBrowse`` factory: client-side filter / sort /
// view-mode toggle over the /api/data-products list.

export function dataProductsBrowse() {
  return {
    products: [],
    filter: '',
    loading: false,
    reloading: false,
    error: null,
    activeChip: 'all',
    sortKey: 'ref',
    sortDir: 'asc',
    viewMode: 'table',

    async init() {
      try {
        const saved = localStorage.getItem('pql.dp.view-mode');
        if (saved === 'cards' || saved === 'table') this.viewMode = saved;
      } catch (_e) {
        /* swallow */
      }
      await this.reload();
    },

    setView(mode) {
      this.viewMode = mode;
      try {
        localStorage.setItem('pql.dp.view-mode', mode);
      } catch (_e) {
        /* swallow */
      }
    },

    async reload() {
      this.loading = true;
      this.error = null;
      try {
        const res = await fetch('/api/data-products');
        if (!res.ok) throw new Error('HTTP ' + res.status);
        const data = await res.json();
        this.products = Array.isArray(data.data_products) ? data.data_products : [];
      } catch (e) {
        this.error = 'Failed to load data products: ' + e.message;
      } finally {
        this.loading = false;
      }
    },

    async reloadFromYaml() {
      this.reloading = true;
      this.error = null;
      try {
        const res = await fetch('/api/data-products/reload', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
        });
        if (!res.ok) {
          const body = await res.json().catch(() => ({}));
          throw new Error(body.detail || 'HTTP ' + res.status);
        }
        await this.reload();
      } catch (e) {
        this.error = 'Yaml reload failed: ' + e.message;
      } finally {
        this.reloading = false;
      }
    },

    toggleSort(key) {
      if (this.sortKey === key) {
        this.sortDir = this.sortDir === 'asc' ? 'desc' : 'asc';
      } else {
        this.sortKey = key;
        this.sortDir = 'asc';
      }
    },

    sortIcon(key) {
      if (this.sortKey !== key) return 'bi-chevron-expand text-muted';
      return this.sortDir === 'asc' ? 'bi-chevron-up' : 'bi-chevron-down';
    },

    get filtered() {
      const f = (this.filter || '').toLowerCase();
      let arr = this.products.filter((p) => {
        if (f) {
          const hay = (p.ref + ' ' + (p.description || '')).toLowerCase();
          if (!hay.includes(f)) return false;
        }
        if (this.activeChip === 'has_comments' && !(p.comment_count_7d > 0)) return false;
        if (this.activeChip === 'has_readme' && !p.has_readme) return false;
        if (this.activeChip === 'stale' && p.freshness_status !== 'stale') return false;
        return true;
      });
      const key = this.sortKey;
      const dir = this.sortDir === 'asc' ? 1 : -1;
      const get = (p, k) => {
        if (k === 'downstream_count' || k === 'agent_run_count_7d') {
          return (p.badges && p.badges[k]) || 0;
        }
        return p[k];
      };
      arr.sort((a, b) => {
        let av = get(a, key);
        let bv = get(b, key);
        if (av === undefined || av === null) av = '';
        if (bv === undefined || bv === null) bv = '';
        if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
        return String(av).localeCompare(String(bv)) * dir;
      });
      return arr;
    },

    get recentlyActive() {
      const scored = this.products
        .map((p) => ({
          p,
          score: (p.comment_count_7d || 0) + 0.5 * (p.review_count || 0),
        }))
        .filter((x) => x.score > 0)
        .sort((a, b) => b.score - a.score)
        .slice(0, 5);
      return scored.map((x) => x.p);
    },
  };
}
