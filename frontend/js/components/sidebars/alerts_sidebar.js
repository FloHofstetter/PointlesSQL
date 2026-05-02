/**
 * Alerts context-panel Alpine factory.
 *
 * Phase 24.4 — replaces the static "All alerts" link with a list of
 * configured alerts split into Enabled + Disabled buckets.
 */

const STORAGE_KEY = 'pql.alerts.recent';

function activeSlugFromUrl() {
    const m = window.location.pathname.match(/^\/alerts\/([^/]+)/);
    if (!m) return '';
    if (m[1] === 'new') return '';
    return decodeURIComponent(m[1]);
}

export function alertsSidebar() {
    return {
        items: [],
        loading: false,
        error: null,
        activeSlug: activeSlugFromUrl(),

        async load() {
            try {
                const cached = sessionStorage.getItem(STORAGE_KEY);
                if (cached) this.items = JSON.parse(cached);
            } catch (e) {}
            await this.fetch();
        },

        async fetch() {
            this.loading = true;
            this.error = null;
            try {
                const res = await fetch('/api/alerts');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                const list = Array.isArray(data) ? data : (data?.alerts || []);
                list.sort((a, b) => {
                    const ta = a?.updated_at || a?.created_at || '';
                    const tb = b?.updated_at || b?.created_at || '';
                    return tb.localeCompare(ta);
                });
                this.items = list;
                try {
                    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(this.items));
                } catch (e) {}
            } catch (e) {
                if (!this.items.length) this.error = e.message;
            } finally {
                this.loading = false;
            }
        },

        async reload() {
            try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
            this.items = [];
            await this.fetch();
        },

        grouped() {
            return {
                enabled:  this.items.filter(a => a.is_active).slice(0, 8),
                disabled: this.items.filter(a => !a.is_active).slice(0, 5),
            };
        },

        isActive(slug) {
            return slug === this.activeSlug;
        },
    };
}
