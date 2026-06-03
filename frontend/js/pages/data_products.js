// Data-product browse page (/data-products).
//
// Single ``dataProductsBrowse`` factory: client-side filter / sort /
// view-mode toggle over the /api/data-products list.  Three views —
// ``marketplace`` (discovery card grid, the default), ``table``, and
// ``cards`` — share one filter + sort pipeline.

const ENDORSEMENT_BADGES = {
  'production-ready': { label: 'Production-ready', variant: 'success', icon: 'check-circle' },
  'verified-by-steward': { label: 'Verified', variant: 'info', icon: 'patch-check' },
  deprecated: { label: 'Deprecated', variant: 'warning', icon: 'exclamation-triangle' },
  'under-review': { label: 'Under review', variant: 'secondary', icon: 'hourglass-split' },
  'branch-approved-for-promotion': {
    label: 'Promote-approved',
    variant: 'primary',
    icon: 'git',
  },
};

// Endorsement types that read as "this product is trustworthy to consume".
const CERTIFIED_TYPES = ['production-ready', 'verified-by-steward'];

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
    viewMode: 'marketplace',
    // Marketplace discovery facets (no-ops in table/cards views).
    mktDomain: 'all',
    mktLifecycle: 'all',
    mktCertified: false,

    async init() {
      try {
        const saved = localStorage.getItem('pql.dp.view-mode');
        if (saved === 'cards' || saved === 'table' || saved === 'marketplace') {
          this.viewMode = saved;
        }
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

    // --- Marketplace discovery helpers -------------------------------

    // Distinct owning domains across the loaded products, for the
    // domain facet chips. Sorted by name.
    get domainList() {
      const seen = new Map();
      for (const p of this.products) {
        if (p.domain && p.domain.slug && !seen.has(p.domain.slug)) {
          seen.set(p.domain.slug, { slug: p.domain.slug, name: p.domain.name });
        }
      }
      return [...seen.values()].sort((a, b) => a.name.localeCompare(b.name));
    },

    // Distinct lifecycle states present, for the lifecycle facet chips.
    get lifecycleList() {
      const seen = new Set();
      for (const p of this.products) {
        if (p.lifecycle_state) seen.add(p.lifecycle_state);
      }
      return [...seen].sort();
    },

    isCertified(p) {
      return (p.endorsements || []).some((e) => CERTIFIED_TYPES.includes(e.type));
    },

    endorsementBadge(type) {
      return ENDORSEMENT_BADGES[type] || { label: type, variant: 'light', icon: 'tag' };
    },

    get filtered() {
      const f = (this.filter || '').toLowerCase();
      const arr = this.products.filter((p) => {
        if (f) {
          const hay = (
            p.ref +
            ' ' +
            (p.description || '') +
            ' ' +
            ((p.domain && p.domain.name) || '') +
            ' ' +
            (p.glossary_terms || []).join(' ')
          ).toLowerCase();
          if (!hay.includes(f)) return false;
        }
        // Table/cards quick chips.
        if (this.activeChip === 'has_comments' && !(p.comment_count_7d > 0)) return false;
        if (this.activeChip === 'has_readme' && !p.has_readme) return false;
        if (this.activeChip === 'stale' && p.freshness_status !== 'stale') return false;
        // Marketplace facets (default to no-op).
        if (this.mktDomain !== 'all' && (!p.domain || p.domain.slug !== this.mktDomain)) {
          return false;
        }
        if (this.mktLifecycle !== 'all' && p.lifecycle_state !== this.mktLifecycle) return false;
        if (this.mktCertified && !this.isCertified(p)) return false;
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
