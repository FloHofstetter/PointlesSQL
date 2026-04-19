// Phase 12.7 Sprint 74 — keymap overlay (Ctrl+Alt+/).
//
// Static commands array: enumerates every editor command added in
// Sprint 62 + 65–73 + 74.  Adding a new command in a future sprint
// means appending one row here — the overlay does NOT introspect
// Monaco's command registry because Monaco's id space includes
// hundreds of built-in commands the user does not need to see.
//
// Bound to ``Ctrl+Alt+/`` rather than ``Ctrl+/`` because the latter
// is Monaco's default toggle-line-comment binding; we don't want to
// shadow it.  Reachable via the gear/? toolbar buttons too.

const COMMANDS = [
    {
        id: 'shiftEnter',
        label: 'Run current cell',
        binding: 'Shift+Enter',
        sprint: 'Sprint 62',
    },
    {
        id: 'ctrlEnter',
        label: 'Run current cell (alternative)',
        binding: 'Ctrl+Enter',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.runAll',
        label: 'Run all cells',
        binding: 'Command palette',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.runAbove',
        label: 'Run all cells above cursor',
        binding: 'Command palette',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.clearOutputs',
        label: 'Clear outputs of current cell',
        binding: 'Command palette',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.restartKernel',
        label: 'Restart kernel',
        binding: 'Command palette',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.insertBelow',
        label: 'Insert cell below',
        binding: 'Command palette',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.insertAbove',
        label: 'Insert cell above',
        binding: 'Command palette',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.insertMarkdown',
        label: 'Insert markdown cell below',
        binding: 'Command palette',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.insertFromCatalog',
        label: 'Insert from catalog…',
        binding: 'Ctrl+Shift+I',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.toggleVariables',
        label: 'Toggle variable explorer',
        binding: 'Command palette',
        sprint: 'Sprint 62',
    },
    {
        id: 'pql.toggleOutline',
        label: 'Toggle outline / table of contents',
        binding: 'Command palette',
        sprint: 'Sprint 70 (palette wired this sprint)',
    },
    {
        id: 'pql.openHistory',
        label: 'Open run-history popover for current cell',
        binding: 'Command palette',
        sprint: 'Sprint 73 (palette wired this sprint)',
    },
    {
        id: 'pql.openSettings',
        label: 'Open editor settings drawer',
        binding: 'Command palette',
        sprint: 'Sprint 74',
    },
    {
        id: 'pql.openKeymap',
        label: 'Open this keymap overlay',
        binding: 'Ctrl+Alt+/',
        sprint: 'Sprint 74',
    },
];

let _modalEl = null;
let _bsModal = null;

function buildModal() {
    const root = document.createElement('div');
    root.className = 'modal fade pql-nbedit-keymap-overlay';
    root.tabIndex = -1;
    root.setAttribute('aria-labelledby', 'pql-nbedit-keymap-title');
    root.innerHTML = `
        <div class="modal-dialog modal-lg modal-dialog-scrollable">
          <div class="modal-content">
            <div class="modal-header">
              <h5 class="modal-title" id="pql-nbedit-keymap-title">Editor commands &amp; keybindings</h5>
              <button type="button" class="btn-close" data-bs-dismiss="modal" aria-label="Close"></button>
            </div>
            <div class="modal-body">
              <table class="table table-sm pql-nbedit-keymap-table">
                <thead>
                  <tr>
                    <th>Command</th>
                    <th>Description</th>
                    <th>Binding</th>
                    <th>Added</th>
                  </tr>
                </thead>
                <tbody></tbody>
              </table>
            </div>
            <div class="modal-footer">
              <small class="text-muted me-auto">
                Monaco's command palette (F1 or Ctrl+Shift+P) lists every
                pql.* action with the same id and label.
              </small>
              <button type="button" class="btn btn-secondary btn-sm" data-bs-dismiss="modal">Close</button>
            </div>
          </div>
        </div>
    `;
    const tbody = root.querySelector('tbody');
    for (const cmd of COMMANDS) {
        const tr = document.createElement('tr');
        tr.innerHTML = `
            <td><code>${cmd.id}</code></td>
            <td>${cmd.label}</td>
            <td><kbd>${cmd.binding}</kbd></td>
            <td><small class="text-muted">${cmd.sprint}</small></td>
        `;
        tbody.appendChild(tr);
    }
    return root;
}

export function mountKeymapOverlay() {
    if (_modalEl) return;
    _modalEl = buildModal();
    document.body.appendChild(_modalEl);
}

export function openKeymapOverlay() {
    if (!_modalEl) mountKeymapOverlay();
    if (!window.bootstrap || !window.bootstrap.Modal) {
        _modalEl.classList.add('show');
        _modalEl.style.display = 'block';
        return;
    }
    if (!_bsModal) {
        _bsModal = new window.bootstrap.Modal(_modalEl);
    }
    _bsModal.show();
}

// Exposed for tests + introspection.
export function listCommands() {
    return COMMANDS.slice();
}
