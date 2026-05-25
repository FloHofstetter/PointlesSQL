// Auto-extracted from frontend/templates/pages/home.html.
//
// Two Alpine factories.  Both used to live as `window.X` assignments
// inside an IIFE; here they are named exports + bootstrap.js attaches
// them on window.  Sparkline data comes through Alpine ctx (no DOM
// reads at factory-definition time), so no DOMContentLoaded gating
// is needed.

export function homeSparkline(ctx) {
  const days = Array.isArray(ctx && ctx.days) ? ctx.days : [];
  let total = 0;
  let succeeded = 0;
  for (const d of days) {
    total += d.total || 0;
    succeeded += d.succeeded || 0;
  }
  const overall = total > 0 ? Math.round((succeeded / total) * 100) + '%' : '—';
  return { totals: { total, succeeded, pct: overall } };
}

export function homeRecentCatalogs() {
  return {
    items: [],
    init() {
      try {
        const raw = localStorage.getItem('pql.recentCatalogs');
        const parsed = raw ? JSON.parse(raw) : [];
        this.items = Array.isArray(parsed) ? parsed.slice(0, 5) : [];
      } catch (_e) {
        this.items = [];
      }
    },
  };
}
