// Phase 12.7 Sprint 67 — file-tree sidebar for the notebook editor.
//
// Exports a factory ``createFileTreeSlice`` that returns a mixin Alpine
// sub-object plugged into ``main.js``'s ``createNotebookEditor``
// factory.  The sidebar renders ``/api/notebooks/tree`` on the left of
// the editor, with per-leaf open / rename / delete and a "New…" button
// in the header; multi-tab handoff is Sprint 68's business, so "open"
// here is a hard navigation.
//
// Deliberately does **not** share code with the full-screen
// ``/notebooks/workspace`` page's inline Alpine factory — that factory
// carries upload + schedule surfaces the sidebar does not want, and
// the slim-mirror scope this sprint was framed under does not justify
// extracting a shared component.  If a later sprint needs the shared
// surface, unify at that moment.
//
// BUG-64-02 invariant: the returned sub-object carries primitive UI
// state + methods only.  The single non-primitive (an AbortController
// for inflight tree fetches) lives in closure scope below — never on
// ``this``.

const TREE_STORAGE_KEY = 'pql.nbedit.tree';
const TREE_OPEN_KEY = 'pql.nbedit.tree.open';
const VISIBLE_KEY = 'pql.nbedit.filesVisible';

/**
 * Flatten the nested ``/api/notebooks/tree`` response into a list of
 * rows for rendering.  A node is visible only when every one of its
 * ancestor directories is open per ``open``; the root row is always
 * visible.  Shared shape with the workspace-page flattener so a user
 * who toggled state on one surface does not re-navigate from scratch
 * on the other, though the two storage keys are independent by
 * design.
 */
export function flattenTree(tree, open) {
    const out = [];
    function visit(nodes, depth, ancestorsVisible) {
        for (const n of nodes) {
            if (ancestorsVisible) {
                out.push({
                    path: n.path,
                    name: n.name,
                    kind: n.kind,
                    format: n.format || 'ipynb',
                    depth,
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

function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

async function parseBodyError(res) {
    try {
        const body = await res.json();
        return body?.error?.message || ('HTTP ' + res.status);
    } catch {
        return 'HTTP ' + res.status;
    }
}

/**
 * Build the Alpine sub-object that owns the sidebar's reactive state
 * and CRUD methods.  ``currentPath`` is the path the editor is
 * currently displaying — the trash button is disabled on that row
 * and rename-in-place triggers a reload at the new URL.
 */
export function createFileTreeSlice({ currentPath }) {
    // Closure-scoped; never reaches Alpine's reactive proxy.  If a
    // second fetch fires before the first resolves, the older one is
    // aborted so a late response cannot overwrite fresher tree state.
    let abortController = null;

    const initiallyVisible = (() => {
        try {
            const raw = window.localStorage.getItem(VISIBLE_KEY);
            if (raw === null) return true; // Sprint 67: sidebar is the headline feature — default visible.
            return raw === '1';
        } catch {
            return true;
        }
    })();

    return {
        // Tree state.  ``tree`` holds the raw response; ``open`` is a
        // flat dict keyed by ``'d:' + dir.path`` so sessionStorage
        // can round-trip it intact.
        tree: null,
        open: {},
        treeLoading: false,
        treeError: null,

        // Sidebar toggle — defaults to true on first page load,
        // persists subsequent user toggles in localStorage so reload
        // respects the last choice.
        filesVisible: initiallyVisible,

        // Modal state machine.  Three disjoint booleans keep the
        // templates trivial — ``x-show`` on each modal reads the
        // matching flag.  Scratchpads hold the input values so the
        // same input can be cleared / pre-filled per action.
        newFileOpen: false,
        newFilePath: '',
        newFileError: null,
        newFileBusy: false,

        renameFileOpen: false,
        renameFileFrom: '',
        renameFileTo: '',
        renameFileError: null,
        renameFileBusy: false,

        deleteFileOpen: false,
        deleteFilePath: '',
        deleteFileError: null,
        deleteFileBusy: false,

        // ─── lifecycle ───

        async loadTreeInitial() {
            try {
                const cached = window.sessionStorage.getItem(TREE_STORAGE_KEY);
                if (cached) this.tree = JSON.parse(cached);
                const openCached = window.sessionStorage.getItem(TREE_OPEN_KEY);
                if (openCached) this.open = JSON.parse(openCached);
            } catch {
                // sessionStorage unavailable or corrupt — fall through to fetchTree.
            }
            if (!this.tree) {
                await this.fetchTree();
            } else {
                // Still refresh in the background so a stale cache
                // never outlives a real write.
                this.fetchTree();
            }
        },

        async reloadTree() {
            try { window.sessionStorage.removeItem(TREE_STORAGE_KEY); } catch {}
            this.tree = null;
            await this.fetchTree();
        },

        async fetchTree() {
            if (abortController) abortController.abort();
            abortController = new AbortController();
            this.treeLoading = true;
            this.treeError = null;
            try {
                const res = await fetch('/api/notebooks/tree', {
                    signal: abortController.signal,
                });
                if (!res.ok) throw new Error(await parseBodyError(res));
                const data = await res.json();
                this.tree = data;
                try {
                    window.sessionStorage.setItem(TREE_STORAGE_KEY, JSON.stringify(data));
                } catch {}
            } catch (e) {
                if (e.name === 'AbortError') return;
                if (!this.tree) this.treeError = 'Failed to load tree: ' + e.message;
            } finally {
                this.treeLoading = false;
            }
        },

        flatTreeRows() {
            return flattenTree(this.tree, this.open);
        },

        isDirOpen(key) { return !!this.open[key]; },

        toggleDir(key) {
            this.open = Object.assign({}, this.open, { [key]: !this.open[key] });
            try { window.sessionStorage.setItem(TREE_OPEN_KEY, JSON.stringify(this.open)); } catch {}
        },

        toggleFilesSidebar() {
            this.filesVisible = !this.filesVisible;
            try { window.localStorage.setItem(VISIBLE_KEY, this.filesVisible ? '1' : '0'); } catch {}
        },

        // ─── actions ───

        openNotebook(path) {
            if (path === currentPath) return;
            window.location.assign('/notebook/editor?path=' + encodeURIComponent(path));
        },

        isCurrentPath(path) { return path === currentPath; },

        // New ─────────────────────────────────────────────────────────

        beginCreateNotebook() {
            this.newFilePath = '';
            this.newFileError = null;
            this.newFileBusy = false;
            this.newFileOpen = true;
        },
        cancelCreateNotebook() {
            if (this.newFileBusy) return;
            this.newFileOpen = false;
        },
        async submitCreateNotebook() {
            const path = (this.newFilePath || '').trim();
            if (!path) {
                this.newFileError = 'Path is required.';
                return;
            }
            if (!path.endsWith('.py')) {
                this.newFileError = 'Path must end in .py';
                return;
            }
            this.newFileBusy = true;
            this.newFileError = null;
            try {
                const res = await fetch('/api/notebooks/create', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken(),
                    },
                    body: JSON.stringify({ path }),
                });
                if (!res.ok) {
                    this.newFileError = await parseBodyError(res);
                    return;
                }
                this.newFileOpen = false;
                window.location.assign('/notebook/editor?path=' + encodeURIComponent(path));
            } catch (e) {
                this.newFileError = 'Create failed: ' + (e.message || e);
            } finally {
                this.newFileBusy = false;
            }
        },

        // Rename ──────────────────────────────────────────────────────

        beginRenameNotebook(path) {
            this.renameFileFrom = path;
            this.renameFileTo = path;
            this.renameFileError = null;
            this.renameFileBusy = false;
            this.renameFileOpen = true;
        },
        cancelRenameNotebook() {
            if (this.renameFileBusy) return;
            this.renameFileOpen = false;
        },
        async submitRenameNotebook() {
            const oldPath = this.renameFileFrom;
            const newPath = (this.renameFileTo || '').trim();
            if (!newPath) {
                this.renameFileError = 'New path is required.';
                return;
            }
            if (newPath === oldPath) {
                this.renameFileOpen = false;
                return;
            }
            this.renameFileBusy = true;
            this.renameFileError = null;
            try {
                const res = await fetch('/api/notebooks/rename', {
                    method: 'PATCH',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-CSRF-Token': csrfToken(),
                    },
                    body: JSON.stringify({ old_path: oldPath, new_path: newPath }),
                });
                if (!res.ok) {
                    this.renameFileError = await parseBodyError(res);
                    return;
                }
                this.renameFileOpen = false;
                if (oldPath === currentPath) {
                    // Editor's ``path`` prop, kernel session key, and
                    // autosave target all derive from the URL at page
                    // load; hard-reload keeps them in sync without
                    // reinventing redirect-while-connected plumbing.
                    window.location.assign('/notebook/editor?path=' + encodeURIComponent(newPath));
                    return;
                }
                await this.reloadTree();
            } catch (e) {
                this.renameFileError = 'Rename failed: ' + (e.message || e);
            } finally {
                this.renameFileBusy = false;
            }
        },

        // Delete ──────────────────────────────────────────────────────

        beginDeleteNotebook(path) {
            if (path === currentPath) return; // Trash stays disabled for the open file.
            this.deleteFilePath = path;
            this.deleteFileError = null;
            this.deleteFileBusy = false;
            this.deleteFileOpen = true;
        },
        cancelDeleteNotebook() {
            if (this.deleteFileBusy) return;
            this.deleteFileOpen = false;
        },
        async submitDeleteNotebook() {
            const path = this.deleteFilePath;
            if (!path) {
                this.deleteFileOpen = false;
                return;
            }
            this.deleteFileBusy = true;
            this.deleteFileError = null;
            try {
                const res = await fetch(
                    '/api/notebooks?path=' + encodeURIComponent(path),
                    {
                        method: 'DELETE',
                        headers: { 'X-CSRF-Token': csrfToken() },
                    },
                );
                if (!res.ok) {
                    this.deleteFileError = await parseBodyError(res);
                    return;
                }
                this.deleteFileOpen = false;
                await this.reloadTree();
            } catch (e) {
                this.deleteFileError = 'Delete failed: ' + (e.message || e);
            } finally {
                this.deleteFileBusy = false;
            }
        },
    };
}
