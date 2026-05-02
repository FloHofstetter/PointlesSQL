/**
 * MLflow context-panel Alpine factory.
 *
 * Phase 24.5 — for the rail's MLflow icon (which today shows the
 * embedded MLflow Tracking UI in an iframe).  The panel surfaces
 * the most-recent UC-registered models with their latest version
 * and status, so the user can drill straight into a model's detail
 * page without a round-trip to /models.
 *
 * Experiments-tree is intentionally out-of-scope; that would need
 * a new endpoint proxying ``mlflow.search_experiments()``.
 */

const STORAGE_KEY = 'pql.mlflow.recent';

function activeFqnFromUrl() {
    const m = window.location.pathname.match(/^\/models\/([^/?#]+)/);
    return m ? decodeURIComponent(m[1]) : '';
}

export function mlflowSidebar() {
    return {
        items: [],
        loading: false,
        error: null,
        activeFqn: activeFqnFromUrl(),

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
                const res = await fetch('/api/models?enrich_latest=true&limit=10');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                const list = Array.isArray(data) ? data : (data?.models || []);
                list.sort((a, b) => (b.updated_at || 0) - (a.updated_at || 0));
                this.items = list.slice(0, 10);
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

        statusBadgeClass(status) {
            if (status === 'READY') return 'bg-success';
            if (status === 'PENDING_REGISTRATION') return 'bg-warning text-dark';
            if (status === 'FAILED_REGISTRATION') return 'bg-danger';
            return 'bg-secondary';
        },

        isActive(fqn) {
            return fqn === this.activeFqn;
        },
    };
}
