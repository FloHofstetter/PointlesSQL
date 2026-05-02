/**
 * Jobs context-panel Alpine factory.
 *
 * Lists scheduled jobs split into Active (not paused) + Paused
 * buckets.
 */

const STORAGE_KEY = 'pql.jobs.recent';

function activeJobIdFromUrl() {
    const m = window.location.pathname.match(/^\/jobs\/(\d+)/);
    return m ? Number(m[1]) : null;
}

export function jobsSidebar() {
    return {
        items: [],
        loading: false,
        error: null,
        activeId: activeJobIdFromUrl(),

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
                const res = await fetch('/api/jobs');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                const list = Array.isArray(data) ? data : (data?.jobs || []);
                list.sort((a, b) => {
                    const ta = a?.last_run_at || a?.updated_at || a?.created_at || '';
                    const tb = b?.last_run_at || b?.updated_at || b?.created_at || '';
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
                active: this.items.filter(j => !j.is_paused).slice(0, 8),
                paused: this.items.filter(j => j.is_paused).slice(0, 5),
            };
        },

        statusBadgeClass(status) {
            if (status === 'succeeded') return 'bg-success';
            if (status === 'failed') return 'bg-danger';
            if (status === 'running') return 'bg-info text-dark';
            return 'bg-secondary';
        },

        humanCron(expr) {
            if (!expr) return '';
            if (typeof window.pqlHumanizeCron === 'function') {
                try { return window.pqlHumanizeCron(expr); } catch (e) {}
            }
            return expr;
        },

        isActive(id) {
            return id === this.activeId;
        },
    };
}
