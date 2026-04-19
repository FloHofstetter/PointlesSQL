// Phase 12.7 Sprint 75 — Monaco command palette registrations.
//
// Carved out of main.js because the action list is pure registration:
// 14 ``editor.addAction`` calls that delegate to the Alpine reactive
// root.  Keeping this in a separate module lets the orchestrator stay
// focused on lifecycle wiring; new commands land here without touching
// the factory shell.

export function registerNotebookCommands(monaco, editor, alpine) {
    // Monaco's built-in command palette opens on F1 / Ctrl+Shift+P;
    // addAction registrations show up there automatically, and each
    // action can bind its own keybindings if we want one.
    const add = (id, label, run, keybindings) =>
        editor.addAction({
            id: `pql.${id}`,
            label,
            keybindings: keybindings || [],
            contextMenuGroupId: 'pql',
            run: () => run(),
        });
    add('runAll', 'PointlesSQL: Run all cells', () => alpine.runAllCells());
    add('runAbove', 'PointlesSQL: Run all cells above cursor', () => alpine.runCellsAbove());
    add('clearOutputs', 'PointlesSQL: Clear outputs of current cell', () =>
        alpine.clearCurrentCellOutputs());
    add('restartKernel', 'PointlesSQL: Restart kernel', () => alpine.restartKernel());
    add('insertBelow', 'PointlesSQL: Insert cell below', () => alpine.addCellBelow());
    add('insertAbove', 'PointlesSQL: Insert cell above', () => alpine.addCellAbove());
    add('insertMarkdown', 'PointlesSQL: Insert markdown cell below', () =>
        alpine.addCellAbove(true));
    add('insertFromCatalog', 'PointlesSQL: Insert from catalog…', () =>
        alpine.openCatalogInsert(),
        [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Shift | monaco.KeyCode.KeyI]);
    add('toggleVariables', 'PointlesSQL: Toggle variable explorer', () =>
        alpine.toggleVariables());
    // Sprint 74: surface the post-Sprint-70 / -73 / -74 commands in
    // Monaco's command palette with stable ``pql.*`` ids.
    add('toggleOutline', 'PointlesSQL: Toggle outline / table of contents', () =>
        alpine.toggleOutline());
    add('openHistory', 'PointlesSQL: Show run history for current cell', () =>
        alpine.openHistoryForCurrentCell());
    add('openSettings', 'PointlesSQL: Open editor settings…', () =>
        alpine.openSettings());
    add('openKeymap', 'PointlesSQL: Show keymap overlay…', () =>
        alpine.openKeymap(),
        [monaco.KeyMod.CtrlCmd | monaco.KeyMod.Alt | monaco.KeyCode.Slash]);
}
