/**
 * Workspace drag-drop move + inline rename mixin.
 *
 * installed on both the workspace-sidebar and the
 * workspace-page factories.  Reuses the existing
 * ``_renameNotebookApi`` (move = rename with a different parent
 * prefix); zero backend changes.
 *
 * Drag-drop rules:
 * - Only notebook rows are draggable.  Folder drag is intentionally
 *   omitted in this the backend rename helper only
 *   supports files; folder-rename arrives in a follow-up.
 * - Only folder rows accept drops.  Drop onto the panel root
 *   moves the notebook to the workspace root.
 * - Drop onto the same parent is a no-op.
 * - Drop onto an existing target name surfaces the backend's 422.
 *
 * Inline rename:
 * - F2 () and double-click both set
 *   ``inlineRenameFor = path``.  The template swaps the label span
 *   for an input.  Enter / blur commit; Escape cancels.
 */

function _leafName(p) {
  const i = (p || '').lastIndexOf('/');
  return i >= 0 ? p.slice(i + 1) : p;
}

function _parentDir(p) {
  const i = (p || '').lastIndexOf('/');
  return i >= 0 ? p.slice(0, i) : '';
}

export function installWorkspaceDnd(state) {
  // ── Drag-drop state ────────────────────────────────────────────
  state.dragState = { draggingPath: null, dropTarget: null };

  state.onDragStart = function (ev, row) {
    if (!row || row.kind !== 'notebook') {
      ev.preventDefault();
      return;
    }
    this.dragState.draggingPath = row.path;
    ev.dataTransfer.effectAllowed = 'move';
    try {
      ev.dataTransfer.setData('application/x-pql-path', row.path);
      ev.dataTransfer.setData('text/plain', row.path);
    } catch {
      // setData can throw in stricter browsers; the in-memory
      // dragState carries the same info as fallback.
    }
  };

  state.onDragOver = function (ev, row) {
    const from = this.dragState.draggingPath;
    if (!from) return;
    // Only folders accept drops.  Root drop is handled by a
    // panel-level @dragover (see _isRootDropZone).
    if (!row || row.kind !== 'dir') return;
    if (_parentDir(from) === row.path) return;
    // Block dropping onto a descendant (would create a cycle).
    if (row.path.startsWith(from + '/')) return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = 'move';
    this.dragState.dropTarget = row.path;
  };

  state.onDragLeave = function (ev, row) {
    if (this.dragState.dropTarget === row.path) {
      this.dragState.dropTarget = null;
    }
  };

  state.onDrop = async function (ev, row) {
    const from = this.dragState.draggingPath;
    this.dragState.draggingPath = null;
    this.dragState.dropTarget = null;
    if (!from) return;
    if (!row || row.kind !== 'dir') return;
    if (_parentDir(from) === row.path) return;
    if (row.path.startsWith(from + '/')) return;
    ev.preventDefault();
    const to = row.path + '/' + _leafName(from);
    try {
      await this._renameNotebookApi(from, to);
    } catch (e) {
      if (window.pqlToast) {
        window.pqlToast.error((e && e.message) || String(e));
      }
    }
  };

  // Root-level drop (anywhere outside a row that's not a folder).
  state.onRootDragOver = function (ev) {
    const from = this.dragState.draggingPath;
    if (!from) return;
    if (_parentDir(from) === '') return;
    ev.preventDefault();
    ev.dataTransfer.dropEffect = 'move';
  };

  state.onRootDrop = async function (ev) {
    const from = this.dragState.draggingPath;
    this.dragState.draggingPath = null;
    this.dragState.dropTarget = null;
    if (!from) return;
    if (_parentDir(from) === '') return;
    ev.preventDefault();
    try {
      await this._renameNotebookApi(from, _leafName(from));
    } catch (e) {
      if (window.pqlToast) {
        window.pqlToast.error((e && e.message) || String(e));
      }
    }
  };

  state.isDropTarget = function (row) {
    return !!row && this.dragState.dropTarget === row.path;
  };

  // ── Inline rename ──────────────────────────────────────────────
  state.inlineRenameFor = null;
  state.inlineRenameValue = '';

  state.startInlineRename = function (row) {
    if (!row || row.kind !== 'notebook') return;
    this.inlineRenameFor = row.path;
    this.inlineRenameValue = _leafName(row.path);
    this.$nextTick(() => {
      const input = this.$el.querySelector(
        'input[data-pql-inline-rename="' + CSS.escape(row.path) + '"]'
      );
      if (input) {
        input.focus();
        // Select the basename (before the extension).
        const dot = input.value.lastIndexOf('.');
        input.setSelectionRange(0, dot > 0 ? dot : input.value.length);
      }
    });
  };

  state.cancelInlineRename = function () {
    this.inlineRenameFor = null;
    this.inlineRenameValue = '';
  };

  state.commitInlineRename = async function (row) {
    const from = this.inlineRenameFor;
    const newLeaf = (this.inlineRenameValue || '').trim();
    this.inlineRenameFor = null;
    if (!from || !newLeaf) return;
    const leafBefore = _leafName(from);
    if (newLeaf === leafBefore) return;
    const parent = _parentDir(from);
    const to = parent ? parent + '/' + newLeaf : newLeaf;
    try {
      await this._renameNotebookApi(from, to);
    } catch (e) {
      if (window.pqlToast) {
        window.pqlToast.error((e && e.message) || String(e));
      }
    }
  };

  state.isInlineRenaming = function (row) {
    return !!row && this.inlineRenameFor === row.path;
  };

  // Hook the context menu's F2 path so it triggers inline rename
  // instead of opening the modal.  Modal-based rename is still
  // reachable via the right-click "Rename…" item.
  const _prevKey = state.onTreeKeydown;
  state.onTreeKeydown = function (ev) {
    if (ev.key === 'F2') {
      const rows =
        typeof this.filteredRows === 'function'
          ? this.filteredRows()
          : typeof this.flatRows === 'function'
            ? this.flatRows()
            : [];
      const row = rows.find((r) => r.path === this.focusedPath);
      if (row && row.kind === 'notebook') {
        ev.preventDefault();
        this.startInlineRename(row);
        return;
      }
    }
    if (_prevKey) _prevKey.call(this, ev);
  };
}
