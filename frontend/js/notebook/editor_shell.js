// Phase 12.7 Sprint 68 — multi-notebook tab bar / editor shell.
//
// The shell is the outer Alpine scope on ``/notebook/editor``.  It
// owns the tab bar, the left file-tree sidebar, and the close-
// confirm modal.  Each tab renders its own ``notebookTabEditor``
// child scope (one Monaco instance, one kernel WS, one LSP WS).
//
// Sprint-65's reactivity-boundary discipline extends to this scope.
// ``tabs`` is an array of plain objects carrying primitives only —
// ``{ id, path, label, dirty, saveState, mounted }``.  Monaco
// editors / kernel WS / LSP clients / cell-affordance DOM refs live
// inside each tab's own ``notebookTabEditor`` closure, out of
// Alpine's deep-reactive walk.  The grep gate
// (``scripts/check-frontend-no-reactive-monaco.sh``) also blocks
// ``this._tabRefs`` / ``this._tabFactories`` so any future
// temptation to aggregate tab state onto the shell trips CI first.
//
// localStorage shape (key ``pql.nbedit.tabs.v1``):
// ``{ active: "<path>", paths: [ "<p1>", "<p2>", ... ] }``.
// Minimal on-disk schema — tab labels derive from the path basename
// at hydration time, dirty state is transient, tab ids are regenerated
// each session (Monaco + kernel WSes are per-session anyway).

import { createFileTreeSlice } from './file_tree.js';

const STORAGE_KEY = 'pql.nbedit.tabs.v1';
const MAX_TABS = 10;
const TAB_BAR_CSS_CLASS_PREFIX = 'pql-nbedit-tab';

function tabIdFor(path) {
    // Deterministic per-path id within a session.  Collisions are
    // impossible because ``openTab`` rejects an already-open path
    // before minting, so the id is effectively the path itself with
    // a tab-safe prefix.
    return 'tab:' + path;
}

function basename(path) {
    if (!path) return '';
    const idx = path.lastIndexOf('/');
    return idx === -1 ? path : path.slice(idx + 1);
}

function csrfToken() {
    const meta = document.querySelector('meta[name="csrf-token"]');
    return meta ? meta.content : '';
}

async function fetchBundle(path) {
    // Sprint 68 backend endpoint; same shape as the Jinja route's
    // ``initial_document`` context.  CSRF is not required for a GET,
    // but the project's middleware honours the same-origin check so
    // no extra header plumbing is needed here.
    const res = await fetch(
        '/api/notebook/doc?path=' + encodeURIComponent(path),
        { credentials: 'same-origin' },
    );
    if (!res.ok) {
        throw new Error(
            'failed to load notebook bundle (HTTP ' + res.status + ')',
        );
    }
    return await res.json();
}

function loadPersistedTabs() {
    try {
        const raw = window.localStorage.getItem(STORAGE_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        if (!parsed || !Array.isArray(parsed.paths)) return null;
        // Dedup defensively — a stale write from an older build could
        // carry duplicates; the tabs model assumes uniqueness.
        const seen = new Set();
        const paths = parsed.paths.filter((p) => {
            if (typeof p !== 'string' || !p) return false;
            if (seen.has(p)) return false;
            seen.add(p);
            return true;
        });
        return {
            active: typeof parsed.active === 'string' ? parsed.active : null,
            paths,
        };
    } catch {
        return null;
    }
}

function persistTabs(state) {
    try {
        window.localStorage.setItem(STORAGE_KEY, JSON.stringify({
            active: state.active,
            paths: state.paths,
        }));
    } catch {
        // Private-mode / quota errors: tabs just won't survive a
        // reload.  Not worth surfacing to the user.
    }
}

export function createNotebookEditorShell({ initialPath, initialBundle }) {
    // Sprint 67 file-tree slice — moved from the per-editor factory
    // to the shell in Sprint 68 so one sidebar governs N tabs.
    const fileTreeSlice = createFileTreeSlice({
        getActivePath: () => {
            // Read-through accessor; the shell owns ``activeTabId``
            // and derives the path from the tabs list on demand.
            // Reads happen during row render (often), but the list
            // is short so O(N) is fine.
            const scope = fileTreeScopeRef;
            if (!scope) return null;
            const tab = scope.tabs.find((t) => t.id === scope.activeTabId);
            return tab ? tab.path : null;
        },
        isPathOpenInAnyTab: (path) => {
            const scope = fileTreeScopeRef;
            if (!scope) return false;
            return scope.tabs.some((t) => t.path === path);
        },
    });

    // The slice closures above need to read live shell state.  Alpine
    // assigns ``this`` to the factory return during scope construction,
    // so we grab the reactive proxy into ``fileTreeScopeRef`` at mount
    // and let the closures read from it.
    let fileTreeScopeRef = null;

    return Object.assign({}, fileTreeSlice, {
        // ─── tabs model ───
        //
        // Each tab is a plain POJO: ``{ id, path, label, dirty,
        // saveState, mounted, bundle }``.  ``bundle`` is the initial
        // document for the first-opened tab (server-rendered) or
        // ``null`` for lazy tabs; the child ``notebookTabEditor``
        // reads it once on first ``mount()``.  The list itself lives
        // on the Alpine proxy — x-for renders it; only primitives
        // inside each entry are reactive.
        tabs: [],
        activeTabId: null,

        // ─── close-confirm modal (Sprint 68) ───
        closeConfirmOpen: false,
        closeConfirmTabId: null,
        closeConfirmBusy: false,

        async mount() {
            fileTreeScopeRef = this;
            // Sidebar fetch fires in parallel with tab hydration.
            // Errors bubble into ``treeError`` for the inline alert;
            // multi-tab does not depend on it.
            this.loadTreeInitial();
            this._hydrateTabs();
            // Wire event-bus listeners from the sidebar and any tab
            // emitting state changes.  Listeners are attached once
            // per shell instance; the lifetime of the shell equals
            // the lifetime of the page so no explicit detach is
            // needed (reload tears the window down anyway).
            document.addEventListener('pql:open-tab', (ev) => {
                const path = ev && ev.detail && ev.detail.path;
                if (typeof path === 'string' && path) this.openTab(path);
            });
            document.addEventListener('pql:file-renamed', (ev) => {
                const oldPath = ev && ev.detail && ev.detail.oldPath;
                const newPath = ev && ev.detail && ev.detail.newPath;
                if (typeof oldPath === 'string' && typeof newPath === 'string') {
                    this._renameOpenTab(oldPath, newPath);
                }
            });
            document.addEventListener('pql:file-deleted', (ev) => {
                const path = ev && ev.detail && ev.detail.path;
                if (typeof path === 'string') this._closeTabByPath(path);
            });
            document.addEventListener('pql:tab-state-changed', (ev) => {
                const detail = ev && ev.detail;
                if (!detail || !detail.tabId) return;
                this._applyChildStateChange(detail);
            });
        },

        // ─── tabs lifecycle ───

        _hydrateTabs() {
            const persisted = loadPersistedTabs();
            const seedPath = initialPath;
            const paths = [];
            if (persisted && persisted.paths.length) {
                for (const p of persisted.paths) paths.push(p);
            }
            if (seedPath && !paths.includes(seedPath)) {
                // Server-rendered page wins over stored list — the
                // URL the user typed/bookmarked must always surface
                // as a tab, even on an existing multi-tab session.
                paths.unshift(seedPath);
            }
            const activePath = (seedPath && paths.includes(seedPath))
                ? seedPath
                : (persisted && paths.includes(persisted.active)
                    ? persisted.active
                    : paths[0] || null);
            this.tabs = paths.slice(0, MAX_TABS).map((path) => ({
                id: tabIdFor(path),
                path,
                label: basename(path),
                dirty: false,
                saveState: 'saved',
                mounted: false,
                // Only the URL-matching tab gets the server-rendered
                // bundle; the rest lazy-fetch on first activation.
                bundle: (path === seedPath) ? (initialBundle || null) : null,
            }));
            this.activeTabId = activePath ? tabIdFor(activePath) : null;
            this._persist();
        },

        openTab(path) {
            // Already open → activate.  This is the common row-click
            // path when the user re-clicks a file already in a tab.
            const existing = this.tabs.find((t) => t.path === path);
            if (existing) {
                this.activateTab(existing.id);
                return;
            }
            if (this.tabs.length >= MAX_TABS) {
                if (window.pqlToast) {
                    window.pqlToast.warning(
                        'Tab limit reached (' + MAX_TABS
                        + '). Close a tab before opening another.',
                    );
                }
                return;
            }
            const id = tabIdFor(path);
            // Appending a plain object keeps the x-for ``:key="t.id"``
            // DOM diff cheap — no other entry re-keys.
            this.tabs = [
                ...this.tabs,
                {
                    id,
                    path,
                    label: basename(path),
                    dirty: false,
                    saveState: 'saved',
                    mounted: false,
                    bundle: null,
                },
            ];
            this.activeTabId = id;
            this._persist();
        },

        activateTab(tabId) {
            if (this.activeTabId === tabId) return;
            const tab = this.tabs.find((t) => t.id === tabId);
            if (!tab) return;
            this.activeTabId = tabId;
            this._persist();
            // The child ``notebookTabEditor``'s ``x-init`` invokes
            // ``mount()`` on first activation; subsequent activations
            // just flip ``x-show``.  No event dispatch needed —
            // x-init fires exactly once because the outer ``x-for``
            // is keyed by tab id and the inner block never unmounts
            // for an already-active tab.
        },

        requestCloseTab(tabId) {
            const tab = this.tabs.find((t) => t.id === tabId);
            if (!tab) return;
            if (tab.dirty) {
                // Bootstrap-modal pattern per BUG-67-01: ``:class``
                // gates the ``.d-block`` utility so the modal shows
                // above its own ``display: none`` default.  Alpine
                // 3.14's ``x-show`` fights with that in the
                // off→on→off cycle; ``:class`` does not.
                this.closeConfirmTabId = tabId;
                this.closeConfirmOpen = true;
                return;
            }
            this._closeTab(tabId);
        },

        cancelCloseConfirm() {
            if (this.closeConfirmBusy) return;
            this.closeConfirmOpen = false;
            this.closeConfirmTabId = null;
        },

        async confirmCloseTabDiscard() {
            const tabId = this.closeConfirmTabId;
            this.closeConfirmOpen = false;
            this.closeConfirmTabId = null;
            if (tabId) this._closeTab(tabId);
        },

        async confirmCloseTabSave() {
            const tabId = this.closeConfirmTabId;
            if (!tabId) return;
            this.closeConfirmBusy = true;
            try {
                // The child scope is the authority on save.  Emit an
                // event it listens for on ``document``; this keeps
                // the shell from reaching into the tab's Alpine
                // proxy directly, which would bypass the child's
                // in-flight / queued guards.
                const done = new Promise((resolve) => {
                    const handler = (ev) => {
                        const d = ev && ev.detail;
                        if (!d || d.tabId !== tabId) return;
                        if (d.saveState === 'saved' || d.saveState === 'error') {
                            document.removeEventListener(
                                'pql:tab-state-changed', handler,
                            );
                            resolve(d.saveState);
                        }
                    };
                    document.addEventListener(
                        'pql:tab-state-changed', handler,
                    );
                });
                document.dispatchEvent(new CustomEvent('pql:save-tab', {
                    detail: { tabId },
                }));
                const state = await done;
                if (state === 'error') {
                    // Keep the modal open so the user can retry; the
                    // per-tab toast already surfaced the error.
                    this.closeConfirmBusy = false;
                    return;
                }
                this.closeConfirmOpen = false;
                this.closeConfirmTabId = null;
                this._closeTab(tabId);
            } finally {
                this.closeConfirmBusy = false;
            }
        },

        _closeTab(tabId) {
            const idx = this.tabs.findIndex((t) => t.id === tabId);
            if (idx === -1) return;
            const wasActive = this.activeTabId === tabId;
            this.tabs = this.tabs.filter((t) => t.id !== tabId);
            if (wasActive) {
                // Activate the neighbour — prefer the tab to the
                // left, fall back to the right, null out if no tabs.
                const next = this.tabs[Math.max(0, idx - 1)] || null;
                this.activeTabId = next ? next.id : null;
            }
            this._persist();
        },

        _closeTabByPath(path) {
            const tab = this.tabs.find((t) => t.path === path);
            if (!tab) return;
            this._closeTab(tab.id);
        },

        _renameOpenTab(oldPath, newPath) {
            // Update every tab whose path matches — typically one.
            // Kernel registry keys by ``(user_id, path)``; the
            // kernel for the old path stays alive under its old key
            // until session shutdown, but the tab's child factory
            // still holds the WS by the old URL so no reconnect is
            // needed for the currently-running kernel.  A fresh
            // reload would bind under the new path.  Sprint 68
            // accepts this as-is — reopening the file post-rename
            // is the cleanest migration if the user needs a fresh
            // kernel keyed by ``newPath``.
            let touched = false;
            this.tabs = this.tabs.map((t) => {
                if (t.path !== oldPath) return t;
                touched = true;
                return Object.assign({}, t, {
                    path: newPath,
                    label: basename(newPath),
                    // Keep ``id`` stable so the child factory's
                    // closure (Monaco, WS, LSP) survives the rename;
                    // the id is only a DOM key, not a path lookup.
                });
            });
            if (touched) this._persist();
        },

        _applyChildStateChange(detail) {
            const { tabId, dirty, saveState, mounted } = detail;
            let touched = false;
            this.tabs = this.tabs.map((t) => {
                if (t.id !== tabId) return t;
                const next = Object.assign({}, t);
                if (typeof dirty === 'boolean' && next.dirty !== dirty) {
                    next.dirty = dirty;
                    touched = true;
                }
                if (typeof saveState === 'string' && next.saveState !== saveState) {
                    next.saveState = saveState;
                    touched = true;
                }
                if (typeof mounted === 'boolean' && next.mounted !== mounted) {
                    // Sprint 68: the tab factory fires ``mounted: true``
                    // synchronously inside its ``mount()``.  Persisting
                    // it onto the shell's tabs array is what keeps the
                    // template's x-if wrapper evaluating true through
                    // subsequent tab switches — without it, x-if flips
                    // back to false on tab-switch-away and destroys
                    // the Monaco + kernel the user was mid-session with.
                    next.mounted = mounted;
                    touched = true;
                }
                return touched ? next : t;
            });
        },

        _persist() {
            const active = (() => {
                const tab = this.tabs.find((t) => t.id === this.activeTabId);
                return tab ? tab.path : null;
            })();
            persistTabs({
                active,
                paths: this.tabs.map((t) => t.path),
            });
        },

        // ─── helpers the template reads ───

        isTabActive(tabId) { return tabId === this.activeTabId; },

        activeTabPath() {
            const tab = this.tabs.find((t) => t.id === this.activeTabId);
            return tab ? tab.path : null;
        },

        tabChromeClass(tab) {
            const classes = [TAB_BAR_CSS_CLASS_PREFIX];
            if (tab.id === this.activeTabId) classes.push(TAB_BAR_CSS_CLASS_PREFIX + '-active');
            if (tab.dirty) classes.push(TAB_BAR_CSS_CLASS_PREFIX + '-dirty');
            return classes.join(' ');
        },

        // Sprint 68: the tab factory needs a fresh ``bundleLoader``
        // closure rather than an eagerly-resolved Promise so the
        // fetch fires only when mount() runs.  The shell hands each
        // tab its own loader keyed on the tab's current path.
        bundleLoaderFor(path) {
            return () => fetchBundle(path);
        },
    });
}
