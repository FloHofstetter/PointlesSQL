// Phase 12.7 Sprint 65 — notebook-editor entry script.
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
// The lazy-import path goes through ``main.js`` → 10 siblings.  This
// file only ever touches DOM via the reactive scope Alpine hands
// into ``mount()``; it never reaches into Monaco / WebSocket /
// Pyright directly, so BUG-64-02's reactivity-boundary invariant
// still holds — the heavy refs stay in ``main.js``'s closure scope,
// not on ``this``.

(function () {
    // Keys the ``main.js`` factory places on the Alpine-reactive
    // scope.  Mirrored here so Alpine's x-bind / x-show / x-text
    // expressions resolve against a scope that already has every key
    // during the pre-mount window.  Missing keys would print the
    // "X is not defined" warnings that Sprint-65 BUG-64-02's race
    // produced.  Kept in one place so drift against ``main.js``'s
    // returned object is obvious when someone adds a new key.
    function initialScope(args) {
        const initial = (args && args.initial) || {};
        const dirty = initial.dirty === true;
        return {
            path: args && args.path,
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
        };
    }

    window.notebookEditor = function (args) {
        const scope = Object.assign(initialScope(args), {
            // Computed getters Alpine reads before mount() resolves —
            // return safe defaults so x-show / x-for survive the
            // pre-mount window without throwing.
            get catalogTablesEmpty() { return false; },
            get filteredCatalogTables() { return []; },

            // Method stubs.  Alpine binds them via @click / x-init;
            // each one is a no-op until mount() swaps in the real
            // implementation.  Keeping the names here prevents
            // "method is not defined" warnings in the pre-mount
            // window.
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

            // Real entry point.  Dynamically imports the orchestrator
            // + ten sibling modules, constructs the real factory, and
            // transplants its properties/getters/methods onto the
            // Alpine-reactive proxy so subsequent mutations flow
            // through the same reactivity listener.
            async mount() {
                const mod = await import('/static/js/notebook/main.js');
                const real = mod.createNotebookEditor(args);
                // Copy getters (filteredCatalogTables, catalogTablesEmpty)
                // via descriptors — plain assignment would call them and
                // freeze the return value.
                const descriptors = Object.getOwnPropertyDescriptors(real);
                for (const key of Object.keys(descriptors)) {
                    const d = descriptors[key];
                    if (d.get || d.set) {
                        Object.defineProperty(this, key, d);
                    }
                }
                // Copy data fields + methods.  Functions bind to the
                // Alpine proxy automatically because they use ``this``
                // for reactive state; closure state stays with the
                // real factory's ``refs`` / ``let`` vars.
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
