/**
 * Branches context-panel Alpine factory.
 *
 * Lists active + promoted Delta-branches grouped by status.
 */

const STORAGE_KEY = 'pql.branches.recent';

function activeFqnFromHash() {
    if (window.location.pathname !== '/branches') return '';
    return decodeURIComponent((window.location.hash || '').replace(/^#/, ''));
}

export function branchesSidebar() {
    return {
        items: [],
        loading: false,
        error: null,
        activeFqn: activeFqnFromHash(),

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
                const res = await fetch('/api/branches');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                const list = Array.isArray(data?.branches) ? data.branches : [];
                list.sort((a, b) => {
                    const ta = a?.tags?.created_at || '';
                    const tb = b?.tags?.created_at || '';
                    return tb.localeCompare(ta);
                });
                this.items = list.slice(0, 15);
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
            const out = { active: [], promoted: [], discarded: [] };
            for (const b of this.items) {
                const status = b?.tags?.status || 'active';
                if (status === 'promoted') out.promoted.push(b);
                else if (status === 'discarded') out.discarded.push(b);
                else out.active.push(b);
            }
            return out;
        },

        statusBadgeClass(status) {
            if (status === 'active') return 'bg-info text-dark';
            if (status === 'promoted') return 'bg-success';
            if (status === 'discarded') return 'bg-secondary';
            return 'bg-secondary';
        },

        relativeTime(iso) {
            if (!iso) return '';
            if (typeof window.pqlRelativeTime === 'function') {
                try { return window.pqlRelativeTime(iso); } catch (e) {}
            }
            return iso.slice(0, 16).replace('T', ' ');
        },

        isActive(fqn) {
            return fqn === this.activeFqn;
        },
    };
}
