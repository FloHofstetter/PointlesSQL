/**
 * Workspace right-click context menu + keyboard navigation mixin.
 *
 * Phase 114.2 — installed on both the workspace-sidebar factory and
 * the workspace-page factory so right-click + arrow keys + F2 +
 * Delete all behave identically on every tree row.  Surfaces a
 * single floating menu (the meta-panel + drawer stack at z=1040,
 * the menu floats at 1050) and a row-focus model that walks the
 * visible tree in DOM order.
 *
 * The mixin assumes the parent factory exposes:
 * - ``filteredRows()`` returning rows with ``{ kind, path, name }``
 *   (workspace-sidebar) OR ``flatRows()`` returning the same shape
 *   (workspace-page).  The mixin tries the sidebar method first and
 *   falls back to the page method.
 * - ``openEditor(path)``       — opens the in-browser editor
 * - ``renameNotebook(path)``   — opens the rename modal
 * - ``deleteNotebook(path)``   — opens the delete-confirm modal
 * - ``schedule(path)``         — navigates to /jobs prefill
 * - ``toggle(path)`` / ``isOpen(path)`` — folder open state
 *
 * It does NOT assume Alpine ``$root`` or any cross-scope hop —
 * everything is local to the parent factory's ``$data`` proxy.
 */

function _copyToClipboard(text) {
    try {
        navigator.clipboard.writeText(text);
        if (window.pqlToast) window.pqlToast.success('Path copied.');
    } catch {
        if (window.pqlToast) window.pqlToast.error('Could not copy.');
    }
}

function _rowsOf(state) {
    if (typeof state.filteredRows === 'function') return state.filteredRows();
    if (typeof state.flatRows === 'function') return state.flatRows();
    return [];
}

function _itemsFor(state, row, opts) {
    if (!row) return [];
    if (row.kind === 'notebook') {
        const items = [
            {
                key: 'open',
                label: 'Open in editor',
                icon: 'bi-pencil-square',
                onClick: () => state.openEditor(row.path),
            },
            {
                key: 'open-new-tab',
                label: 'Open in new tab',
                icon: 'bi-box-arrow-up-right',
                onClick: () => {
                    window.open(
                        '/notebooks/edit/' + encodeURI(row.path),
                        '_blank',
                        'noopener,noreferrer',
                    );
                },
            },
        ];
        if (typeof state.schedule === 'function') {
            items.push({
                key: 'schedule',
                label: 'Schedule…',
                icon: 'bi-calendar-plus',
                onClick: () => state.schedule(row.path),
            });
        }
        items.push({ key: 'sep1', divider: true });
        items.push({
            key: 'rename',
            label: 'Rename…',
            icon: 'bi-input-cursor-text',
            shortcut: 'F2',
            onClick: () => state.renameNotebook(row.path),
        });
        items.push({
            key: 'copy-path',
            label: 'Copy path',
            icon: 'bi-clipboard',
            onClick: () => _copyToClipboard(row.path),
        });
        items.push({ key: 'sep2', divider: true });
        items.push({
            key: 'delete',
            label: 'Delete…',
            icon: 'bi-trash',
            shortcut: 'Del',
            danger: true,
            onClick: () => state.deleteNotebook(row.path),
        });
        return items;
    }
    // Folder row
    const items = [
        {
            key: 'toggle',
            label: state.isOpen(row.path) ? 'Collapse folder' : 'Expand folder',
            icon: state.isOpen(row.path) ? 'bi-chevron-down' : 'bi-chevron-right',
            onClick: () => state.toggle(row.path),
        },
    ];
    if (typeof state.openCreate === 'function') {
        items.push({
            key: 'new-here',
            label: 'New notebook here',
            icon: 'bi-plus-square',
            onClick: () => {
                state.openCreate();
                // Seed the input with the folder path so the user only
                // needs to type the filename.
                if (state.pathDialog) {
                    state.pathDialog.value = row.path + '/new_notebook.py';
                }
            },
        });
    }
    items.push({ key: 'sep1', divider: true });
    items.push({
        key: 'copy-path',
        label: 'Copy path',
        icon: 'bi-clipboard',
        onClick: () => _copyToClipboard(row.path),
    });
    return items;
}

export function installWorkspaceContextMenu(state, opts) {
    opts = opts || {};

    state.contextMenu = {
        open: false,
        x: 0,
        y: 0,
        row: null,
        items: [],
        focusIndex: -1,
    };

    state.focusedPath = null;

    state.openContextMenu = function (ev, row) {
        ev.preventDefault();
        ev.stopPropagation();
        // Clamp menu to viewport so it doesn't render off-screen on
        // right-click near the bottom-right edge.
        const menuW = 220;
        const menuH = 300;
        const vw = window.innerWidth;
        const vh = window.innerHeight;
        const x = Math.min(ev.clientX, vw - menuW - 4);
        const y = Math.min(ev.clientY, vh - menuH - 4);
        this.contextMenu.row = row;
        this.contextMenu.items = _itemsFor(this, row, opts);
        this.contextMenu.x = Math.max(0, x);
        this.contextMenu.y = Math.max(0, y);
        this.contextMenu.focusIndex = -1;
        this.contextMenu.open = true;
    };

    state.closeContextMenu = function () {
        this.contextMenu.open = false;
        this.contextMenu.row = null;
        this.contextMenu.items = [];
    };

    state.runContextMenuItem = function (item) {
        if (!item || item.divider) return;
        try { item.onClick(); } catch (e) {
            if (window.pqlToast) window.pqlToast.error(String(e && e.message || e));
        }
        this.closeContextMenu();
    };

    // ── Keyboard navigation on the tree ────────────────────────────
    state.onTreeKeydown = function (ev) {
        // Skip if the focus is inside the search input or any other
        // editable surface — let the browser handle caret movement.
        const tag = (ev.target && ev.target.tagName) || '';
        if (tag === 'INPUT' || tag === 'TEXTAREA') {
            if (ev.key === 'Escape') {
                // Allow Escape to bubble — the search input itself
                // clears via @keydown.escape on its own binding.
            }
            return;
        }
        const rows = _rowsOf(this);
        if (!rows.length) return;
        let idx = rows.findIndex((r) => r.path === this.focusedPath);
        const moveTo = (newIdx) => {
            if (newIdx < 0 || newIdx >= rows.length) return;
            this.focusedPath = rows[newIdx].path;
            this.$nextTick(() => {
                const el = this.$el.querySelector(
                    '[data-pql-tree-row="' + CSS.escape(rows[newIdx].path) + '"]',
                );
                if (el) el.focus();
            });
        };
        if (ev.key === 'ArrowDown') {
            ev.preventDefault();
            moveTo(idx < 0 ? 0 : idx + 1);
        } else if (ev.key === 'ArrowUp') {
            ev.preventDefault();
            moveTo(idx < 0 ? 0 : idx - 1);
        } else if (ev.key === 'ArrowRight') {
            ev.preventDefault();
            const row = rows[idx];
            if (row && row.kind === 'dir' && !this.isOpen(row.path)) {
                this.toggle(row.path);
            }
        } else if (ev.key === 'ArrowLeft') {
            ev.preventDefault();
            const row = rows[idx];
            if (row && row.kind === 'dir' && this.isOpen(row.path)) {
                this.toggle(row.path);
            }
        } else if (ev.key === 'Enter') {
            ev.preventDefault();
            const row = rows[idx];
            if (!row) return;
            if (row.kind === 'dir') this.toggle(row.path);
            else this.openEditor(row.path);
        } else if (ev.key === 'F2') {
            ev.preventDefault();
            const row = rows[idx];
            if (row && row.kind === 'notebook') this.renameNotebook(row.path);
        } else if (ev.key === 'Delete' || ev.key === 'Backspace') {
            const row = rows[idx];
            if (row && row.kind === 'notebook') {
                ev.preventDefault();
                this.deleteNotebook(row.path);
            }
        } else if (ev.key === '/') {
            const input = this.$el.querySelector(
                '.pql-workspace-tree__search-input, input[type="search"]',
            );
            if (input) {
                ev.preventDefault();
                input.focus();
            }
        } else if (ev.key === 'Escape') {
            this.focusedPath = null;
            if (ev.target && typeof ev.target.blur === 'function') ev.target.blur();
        }
    };

    state.onRowFocus = function (row) {
        this.focusedPath = row.path;
    };
}
