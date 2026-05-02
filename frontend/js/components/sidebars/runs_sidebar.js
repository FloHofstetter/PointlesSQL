/**
 * Runs context-panel Alpine factory.
 *
 * Phase 24.0 — replaces the static "All runs" link in the context
 * panel with a navigable list of recent agent runs grouped by
 * status.  Pattern mirrors :func:`catalogTree` in
 * ``catalog_tree.js`` (sessionStorage instant-paint + async refetch
 * + ``pathFromUrl``-based active highlight).
 */

const STORAGE_KEY = 'pql.runs.recent';

function runIdFromUrl() {
    const m = window.location.pathname.match(/^\/runs\/([^/]+)/);
    return m ? m[1] : '';
}

const ACTIVE_STATUSES = new Set(['running', 'queued']);
const NEEDS_APPROVAL_STATUSES = new Set(['needs_approval', 'pending_approval']);

export function runsSidebar() {
    return {
        items: [],
        loading: false,
        error: null,
        activeId: runIdFromUrl(),

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
                const res = await fetch('/api/runs?limit=15');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                const list = Array.isArray(data?.runs) ? data.runs : [];
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
            const out = { needs_approval: [], running: [], recent: [] };
            for (const r of this.items) {
                if (NEEDS_APPROVAL_STATUSES.has(r.status)) {
                    out.needs_approval.push(r);
                } else if (ACTIVE_STATUSES.has(r.status)) {
                    out.running.push(r);
                } else {
                    out.recent.push(r);
                }
            }
            out.recent = out.recent.slice(0, 10);
            return out;
        },

        statusBadgeClass(status) {
            if (status === 'succeeded' || status === 'completed' || status === 'approved') {
                return 'bg-success';
            }
            if (status === 'failed' || status === 'rolled_back') return 'bg-danger';
            if (status === 'denied') return 'bg-secondary';
            if (NEEDS_APPROVAL_STATUSES.has(status)) return 'bg-warning text-dark';
            if (ACTIVE_STATUSES.has(status)) return 'bg-info text-dark';
            return 'bg-secondary';
        },

        shortId(id) {
            return (id || '').slice(0, 8);
        },

        relativeTime(iso) {
            if (!iso) return '';
            if (typeof window.pqlRelativeTime === 'function') {
                try { return window.pqlRelativeTime(iso); } catch (e) {}
            }
            return iso.slice(0, 16).replace('T', ' ');
        },

        isActive(id) {
            return id === this.activeId;
        },
    };
}
