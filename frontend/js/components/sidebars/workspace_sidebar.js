/**
 * Workspace context-panel Alpine factory.
 *
 * Phase 24.2 — replaces the static "Notebooks" link with a flat
 * list of every ``.py`` / ``.ipynb`` notebook the scheduler can
 * pick up.  Source: ``/api/notebooks/tree`` (admin-only); the
 * rail item is already ``is_admin``-gated, so non-admins never
 * reach this partial.  No "recently opened" surface — the
 * workspace page does not have a per-notebook detail view.
 */

const STORAGE_KEY = 'pql.workspace.tree';

function activePathFromUrl() {
    if (window.location.pathname !== '/notebooks/workspace') return '';
    const params = new URLSearchParams(window.location.search);
    return params.get('path') || '';
}

function flattenLeaves(nodes) {
    const out = [];
    const walk = (entries) => {
        for (const n of entries || []) {
            if (n.kind === 'notebook') {
                out.push({ path: n.path, format: n.format || '' });
            } else if (n.children) {
                walk(n.children);
            }
        }
    };
    walk(nodes);
    out.sort((a, b) => a.path.localeCompare(b.path));
    return out;
}

export function workspaceSidebar() {
    return {
        items: [],
        loading: false,
        error: null,
        activePath: activePathFromUrl(),

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
                const res = await fetch('/api/notebooks/tree');
                if (!res.ok) throw new Error('HTTP ' + res.status);
                const data = await res.json();
                const tree = Array.isArray(data) ? data : (data?.tree || []);
                this.items = flattenLeaves(tree).slice(0, 30);
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

        leafName(path) {
            const i = (path || '').lastIndexOf('/');
            return i >= 0 ? path.slice(i + 1) : path;
        },

        parentDir(path) {
            const i = (path || '').lastIndexOf('/');
            return i >= 0 ? path.slice(0, i) : '';
        },

        formatBadge(format) {
            if (format === 'py') return 'bg-info text-dark';
            if (format === 'ipynb') return 'bg-warning text-dark';
            return 'bg-secondary';
        },

        isActive(path) {
            return path === this.activePath;
        },
    };
}
