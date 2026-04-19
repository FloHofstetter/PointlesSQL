/**
 * Notebooks workspace page Alpine factory.
 *
 * Sprint 94 lifted the inline ``<script>`` block from
 * ``pages/notebooks_workspace.html`` into this ESM module.
 * ``bootstrap.js`` re-attaches the factory to
 * ``window.notebookWorkspace`` so the template's
 * ``x-data="notebookWorkspace()"`` resolves unchanged.
 *
 * Owns the workspace tree fetch + sessionStorage cache, the
 * dir-open toggle map, the upload form, and the "Schedule…"
 * button that prefills the create-job modal.
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
        targetPath: '',
        overwrite: false,
        uploading: false,
        uploadError: null,
        uploadStatus: null,

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

        async upload() {
            this.uploadError = null;
            this.uploadStatus = null;
            const files = this.$refs.file.files;
            if (!files || files.length === 0) {
                this.uploadError = 'pick a notebook file to upload';
                return;
            }
            if (!this.targetPath) {
                this.uploadError = 'target path is required';
                return;
            }
            this.uploading = true;
            try {
                const form = new FormData();
                form.append('file', files[0]);
                form.append('target_path', this.targetPath);
                form.append('overwrite', this.overwrite ? 'true' : 'false');
                const res = await fetch('/api/notebooks/upload', {
                    method: 'POST',
                    body: form,
                });
                const body = await res.json().catch(() => null);
                if (!res.ok) {
                    this.uploadError = body?.error?.message || ('HTTP ' + res.status);
                    return;
                }
                this.uploadStatus = 'Uploaded ' + body.path + ' (' + body.status + ').';
                this.$refs.uploadForm.reset();
                this.targetPath = '';
                this.overwrite = false;
                await this.reload();
            } catch (e) {
                this.uploadError = String(e);
            } finally {
                this.uploading = false;
            }
        },
    };
}
