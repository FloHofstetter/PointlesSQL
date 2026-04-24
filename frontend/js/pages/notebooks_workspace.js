/**
 * Notebooks workspace page Alpine factory.
 *
 * Phase 12.12.2 trimmed this module to the read-only surface:
 * fetch the nested tree from ``/api/notebooks/tree`` (with
 * sessionStorage caching), flatten it for rendering, and offer a
 * "Schedule…" button per notebook leaf that hands off to the
 * ``/jobs`` create-modal via prefill query params. The upload +
 * open-in-editor affordances were removed with the browser editor.
 *
 * ``bootstrap.js`` re-attaches the factory to
 * ``window.notebookWorkspace`` so the template's
 * ``x-data="notebookWorkspace()"`` resolves unchanged.
 */

const STORAGE_KEY = 'pql.notebooks';
const OPEN_KEY = 'pql.notebooks.open';

/**
 * Flatten a nested tree into a list of rows. A row is rendered only
 * when every one of its ancestor directories is open (per `open`).
 * The root directories are always visible.
 */
function flatten(tree, open) {
    const out = [];
    function visit(nodes, depth, ancestorsVisible) {
        for (const n of nodes) {
            if (ancestorsVisible) {
                out.push({
                    path: n.path,
                    name: n.name,
                    kind: n.kind,
                    format: n.format || 'ipynb',
                    depth: depth,
                    parameters_tagged: !!n.parameters_tagged,
                });
            }
            if (n.kind === 'dir' && n.children && n.children.length) {
                const opened = !!open['d:' + n.path];
                visit(n.children, depth + 1, ancestorsVisible && opened);
            }
        }
    }
    visit(tree || [], 0, true);
    return out;
}

export function notebookWorkspace() {
    return {
        tree: null,
        loading: false,
        error: null,
        open: {},

        isOpen(key) { return !!this.open[key]; },

        toggle(key) {
            this.open[key] = !this.open[key];
            try { sessionStorage.setItem(OPEN_KEY, JSON.stringify(this.open)); } catch (e) {}
        },

        flatRows() { return flatten(this.tree, this.open); },

        async load() {
            try {
                const cached = sessionStorage.getItem(STORAGE_KEY);
                if (cached) this.tree = JSON.parse(cached);
                const openCached = sessionStorage.getItem(OPEN_KEY);
                if (openCached) this.open = JSON.parse(openCached);
            } catch (e) {}

            if (!this.tree) await this.fetchTree();
            else this.fetchTree();
        },

        async reload() {
            try { sessionStorage.removeItem(STORAGE_KEY); } catch (e) {}
            this.tree = null;
            await this.fetchTree();
        },

        async fetchTree() {
            this.loading = true;
            this.error = null;
            try {
                const res = await fetch('/api/notebooks/tree');
                if (!res.ok) {
                    const body = await res.json().catch(() => null);
                    throw new Error(body?.error?.message || ('HTTP ' + res.status));
                }
                const data = await res.json();
                this.tree = data;
                try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(data)); } catch (e) {}
            } catch (e) {
                if (!this.tree) this.error = 'Failed to load tree: ' + e.message;
            } finally {
                this.loading = false;
            }
        },

        schedule(path) {
            const qs = new URLSearchParams({
                prefill_kind: 'papermill',
                prefill_notebook_path: path,
            });
            window.location.href = '/jobs?' + qs.toString();
        },
    };
}
