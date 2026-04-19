// Phase 12.7 — notebook editor entry script.
//
// Sprint 66: converted from ``<script type="module">`` to a classic
// IIFE so that ``window.notebookEditor`` is registered
// **synchronously** during HTML parse.  Alpine's CDN ``<script
// defer>`` and a module-typed bootstrap both run at the same defer
// priority, but the eleven-module ESM graph cannot resolve before
// Alpine starts walking x-data — it burns its boot budget on the
// network round-trips.  The Sprint-41 SQL-editor fix (commit
// b830300) documented the same class of race and settled on the
// same mitigation: keep the entry script synchronous, lazy-import
// the heavy modules inside the factory's ``mount()``.
//
// Sprint 68 split the single-scope ``notebookEditor`` into two
// distinct factories: ``notebookEditorShell`` (tab bar + sidebar +
// close-confirm modal — one per page) and ``notebookTabEditor``
// (Monaco + kernel + LSP — N per page, one per open tab).  Each
// has its own pre-mount scope stub so Alpine does not emit
// "X is not defined" warnings during the pre-mount window that
// BUG-64-02's race produced.
//
// The lazy-import path goes through ``editor_shell.js`` +
// ``main.js`` → ten siblings.  This file only ever touches DOM via
// the reactive scope Alpine hands into ``mount()``; it never
// reaches into Monaco / WebSocket / Pyright directly, so
// BUG-64-02's reactivity-boundary invariant still holds — the
// heavy refs stay in ``main.js`` + ``editor_shell.js`` closure
// scopes, not on ``this``.

(function () {
    // Sprint 68: shell-scope stub.  Keeps every key Alpine's
    // x-bind / x-show / x-text expressions touch during the
    // pre-mount window defined, so the log stays quiet even when
    // the ``import('./editor_shell.js')`` network trip is in
    // flight.  Mirrors the key list in ``editor_shell.js`` —
    // extend both together when a new reactive field lands.
    function shellInitialScope(args) {
        let filesVisible = true;
        try {
            const raw = window.localStorage.getItem('pql.nbedit.filesVisible');
            if (raw !== null) filesVisible = raw === '1';
        } catch {}
        const initialPath = args && args.initialPath;
        const initialBundle = args && args.initialBundle;
        // Seed a single tab immediately so the x-for rendering the
        // tab bar + tab panes already sees a row before mount()
        // resolves — otherwise the active editor would blink into
        // existence after Monaco loads, long after first paint.
        const seedTab = initialPath
            ? {
                id: 'tab:' + initialPath,
                path: initialPath,
                label: (() => {
                    const i = initialPath.lastIndexOf('/');
                    return i === -1 ? initialPath : initialPath.slice(i + 1);
                })(),
                dirty: (initialBundle && initialBundle.dirty === true) || false,
                saveState: 'saved',
                mounted: false,
                bundle: initialBundle || null,
            }
            : null;
        return {
            tabs: seedTab ? [seedTab] : [],
            activeTabId: seedTab ? seedTab.id : null,
            closeConfirmOpen: false,
            closeConfirmTabId: null,
            closeConfirmBusy: false,
            // Sprint-67 sidebar state.  Mirror of createFileTreeSlice
            // keys so x-show / x-model in the sidebar survive the
            // pre-mount window.
            tree: null,
            open: {},
            treeLoading: false,
            treeError: null,
            filesVisible,
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
        };
    }

    window.notebookEditorShell = function (args) {
        const scope = Object.assign(shellInitialScope(args), {
            // ─── stubs for method bindings ───
            flatTreeRows() { return []; },
            isDirOpen() { return false; },
            toggleDir() {},
            toggleFilesSidebar() {},
            isCurrentPath() { return false; },
            isPathOpen() { return false; },
            async loadTreeInitial() {},
            async reloadTree() {},
            openNotebook() {},
            beginCreateNotebook() {},
            cancelCreateNotebook() {},
            async submitCreateNotebook() {},
            beginRenameNotebook() {},
            cancelRenameNotebook() {},
            async submitRenameNotebook() {},
            beginDeleteNotebook() {},
            cancelDeleteNotebook() {},
            async submitDeleteNotebook() {},
            // Tabs stubs
            openTab() {},
            activateTab() {},
            requestCloseTab() {},
            cancelCloseConfirm() {},
            async confirmCloseTabDiscard() {},
            async confirmCloseTabSave() {},
            isTabActive(tabId) { return tabId === this.activeTabId; },
            activeTabPath() { return null; },
            tabChromeClass() { return 'pql-nbedit-tab'; },
            bundleLoaderFor() { return async () => null; },

            async mount() {
                const mod = await import('/static/js/notebook/editor_shell.js');
                const real = mod.createNotebookEditorShell(args || {});
                const descriptors = Object.getOwnPropertyDescriptors(real);
                for (const key of Object.keys(descriptors)) {
                    const d = descriptors[key];
                    if (d.get || d.set) {
                        Object.defineProperty(this, key, d);
                    }
                }
                for (const key of Object.keys(real)) {
                    const d = descriptors[key];
                    if (d && (d.get || d.set)) continue;
                    this[key] = real[key];
                }
                await real.mount.call(this);
            },
        });
        return scope;
    };

    // Sprint 68: per-tab editor stub.  Matches the key list in
    // main.js's ``createNotebookTabEditor`` factory output.  Every
    // x-bind / x-show / x-text / @click in the tab template must
    // find a stub key here to survive the pre-mount window.
    function tabInitialScope(args) {
        const path = args && args.path;
        const tabId = args && args.tabId;
        const bundle = args && args.initial;
        const dirty = (bundle && bundle.dirty === true) || false;
        return {
            path,
            tabId,
            dirty,
            loading: false,
            saveState: dirty ? 'pending' : 'saved',
            kernelStatus: 'connecting',
            kernelSessionId: null,
            executingCells: {},
            lspStatus: 'connecting',
            variables: {},
            variablesVisible: false,
            catalogInsertOpen: false,
            catalogInsertQuery: '',
            catalogTablesLoaded: false,
            mounted: false,
        };
    }

    window.notebookTabEditor = function (args) {
        const scope = Object.assign(tabInitialScope(args), {
            get catalogTablesEmpty() { return false; },
            get filteredCatalogTables() { return []; },

            clearCurrentCellOutputs() {},
            runCurrentCell() {},
            runCellById() {},
            interruptKernel() {},
            restartKernel() {},
            runAllCells() {},
            runCellsAbove() {},
            addCellBelow() {},
            addCellAbove() {},
            insertCellAfter() {},
            toggleVariables() {},
            openCatalogInsert() {},
            pickCatalogTable() {},
            _refreshVariables() {},
            async save() {},

            async mount() {
                const mod = await import('/static/js/notebook/main.js');
                const real = mod.createNotebookTabEditor(args || {});
                const descriptors = Object.getOwnPropertyDescriptors(real);
                for (const key of Object.keys(descriptors)) {
                    const d = descriptors[key];
                    if (d.get || d.set) {
                        Object.defineProperty(this, key, d);
                    }
                }
                for (const key of Object.keys(real)) {
                    const d = descriptors[key];
                    if (d && (d.get || d.set)) continue;
                    this[key] = real[key];
                }
                await real.mount.call(this);
            },
        });
        return scope;
    };
})();
