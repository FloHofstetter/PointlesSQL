/**
 * Notebook editor — Cell drag-drop reorder mixin (Phase 115).
 *
 * Installs grip-handle DnD on top of ``_moveCellTo`` from
 * ``cell_operations.js``.  The mixin owns the transient
 * ``dragState`` (which cell is being dragged, which row is the
 * hover-target, and whether the drop edge is above or below the
 * target's vertical midpoint) plus the handlers that the template
 * binds on the grip button and the row wrapper.
 *
 * Only the grip element carries ``draggable="true"`` so CodeMirror's
 * native text-selection drag inside the editor body keeps working.
 * The drop indicator is rendered via two CSS classes
 * (``--drop-above`` / ``--drop-below``) the row toggles based on
 * ``cellDropIndicator(cell)``.
 */

export function installCellDnd(state) {
  state.dragState = { draggingCellId: null, dropTargetId: null, dropEdge: null };

  state.onCellDragStart = function (ev, cell) {
    if (!cell || !cell.id) return;
    this.dragState = {
      draggingCellId: cell.id,
      dropTargetId: null,
      dropEdge: null,
    };
    try {
      ev.dataTransfer.effectAllowed = 'move';
      ev.dataTransfer.setData('application/x-pql-cell-id', cell.id);
    } catch (_e) { /* swallow — some browsers reject custom MIME on file: */ }
  };

  state.onCellDragOver = function (ev, target) {
    if (!this.dragState.draggingCellId) return;
    if (!target || target.id === this.dragState.draggingCellId) return;
    const rect = ev.currentTarget.getBoundingClientRect();
    const edge = ev.clientY - rect.top < rect.height / 2 ? 'above' : 'below';
    if (
      this.dragState.dropTargetId !== target.id
      || this.dragState.dropEdge !== edge
    ) {
      this.dragState = {
        draggingCellId: this.dragState.draggingCellId,
        dropTargetId: target.id,
        dropEdge: edge,
      };
    }
    try { ev.dataTransfer.dropEffect = 'move'; } catch (_e) { /* swallow */ }
  };

  state.onCellDragLeave = function (ev, target) {
    if (!target) return;
    // Only clear when leaving the SAME row that is the current
    // drop-target; the next ``dragover`` on an adjacent row will
    // immediately re-set it.  Without this guard, the indicator
    // flickers between rows during rapid mouse movement.
    if (this.dragState.dropTargetId === target.id) {
      this.dragState = {
        draggingCellId: this.dragState.draggingCellId,
        dropTargetId: null,
        dropEdge: null,
      };
    }
  };

  state.onCellDrop = function (ev, target) {
    const fromId = this.dragState.draggingCellId;
    const edge = this.dragState.dropEdge;
    this._resetCellDragState();
    if (!fromId || !target || fromId === target.id || !edge) return;
    const fromIdx = this.cells.findIndex((c) => c.id === fromId);
    let toIdx = this.cells.findIndex((c) => c.id === target.id);
    if (fromIdx < 0 || toIdx < 0) return;
    if (edge === 'below') toIdx += 1;
    // After splice-removal of ``cell[fromIdx]``, every index after
    // ``fromIdx`` shifts down by one.  Compensate so the visual
    // target the user dropped onto remains the actual destination.
    if (toIdx > fromIdx) toIdx -= 1;
    if (toIdx === fromIdx) return;
    this._moveCellTo(fromIdx, toIdx);
  };

  state.onCellDragEnd = function () {
    this._resetCellDragState();
  };

  state._resetCellDragState = function () {
    this.dragState = { draggingCellId: null, dropTargetId: null, dropEdge: null };
  };

  state.cellDropIndicator = function (cell) {
    const s = this.dragState;
    if (!s.draggingCellId || !cell) return null;
    if (s.dropTargetId !== cell.id) return null;
    return s.dropEdge;
  };
}
