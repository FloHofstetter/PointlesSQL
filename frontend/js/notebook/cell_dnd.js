/**
 * Notebook editor — Cell drag-drop reorder mixin.
 *
 * The entire ``.pql-notebook-cell__header`` element acts as a
 * desktop-window-style drag handle.  During a drag, the cell
 * under the cursor is **immediately re-spliced** in
 * ``this.cells`` so the user sees the dragged cell physically
 * take its destination position (live preview, à la
 * Trello / Notion).  A FLIP helper
 * (First-Last-Invert-Play) animates the displaced cells into
 * place over ~180 ms so the reorder reads as a smooth slide
 * rather than a snap.
 *
 * To keep peers quiet during the drag, the intermediate
 * splices use ``_moveCellTo(..., { broadcast: false })`` —
 * the canonical ``cells_order`` Y.Array gets ONE write on
 * ``drop`` with the final position.
 *
 * ``_dragInProgress`` blocks the ``cells_order`` observer from
 * clobbering the in-progress local reorder when a peer makes
 * an unrelated mutation mid-drag.
 */

const FLIP_DURATION_MS = 180;
const FLIP_EASING = 'cubic-bezier(0.2, 0, 0, 1)';

export function installCellDnd(state) {
  state.dragState = { draggingCellId: null };
  state._dragInProgress = false;

  state.onCellDragStart = function (ev, cell) {
    if (!cell || !cell.id) return;
    this.dragState = { draggingCellId: cell.id };
    this._dragInProgress = true;
    try {
      ev.dataTransfer.effectAllowed = 'move';
      ev.dataTransfer.setData('application/x-pql-cell-id', cell.id);
    } catch (_e) { /* swallow — some browsers reject custom MIME on file: */ }
  };

  state.onCellDragOver = function (ev, target) {
    if (!this.dragState.draggingCellId) return;
    if (!target || !target.id) return;
    if (target.id === this.dragState.draggingCellId) return;
    try { ev.dataTransfer.dropEffect = 'move'; } catch (_e) { /* swallow */ }
    const draggedIdx = this.cells.findIndex((c) => c.id === this.dragState.draggingCellId);
    const targetIdx = this.cells.findIndex((c) => c.id === target.id);
    if (draggedIdx < 0 || targetIdx < 0) return;
    // Use the HEADER rect (not the wrapper) for the above/below
    // midpoint split — the wrapper can be hundreds of pixels tall
    // because it includes the editor body, which makes the "above"
    // half stretch way past the visible header and a hover on the
    // adjacent cell's header always classifies as "above" → no-op
    // for the common case of swapping two adjacent cells.  The
    // header is the only zone that visually reads as a drop target
    // anyway (cursor stays ``grab`` over it).
    const header = ev.currentTarget.querySelector('.pql-notebook-cell__header')
                || ev.currentTarget;
    const rect = header.getBoundingClientRect();
    const aboveHalf = ev.clientY - rect.top < rect.height / 2;
    let insertAt = aboveHalf ? targetIdx : targetIdx + 1;
    // Splice removes the dragged cell first, which shifts every
    // index after ``draggedIdx`` down by one.  Compensate so the
    // visual target row remains the actual destination.
    if (insertAt > draggedIdx) insertAt -= 1;
    if (insertAt === draggedIdx) return;
    this._flipReorderCells(() => this._moveCellTo(draggedIdx, insertAt, { broadcast: false }));
  };

  state.onCellDragLeave = function () { /* no-op — live-splice replaces the indicator pattern */ };

  state.onCellDrop = function () {
    const draggingId = this.dragState.draggingCellId;
    this._resetCellDragState();
    if (!draggingId) return;
    // Cell is already at its final position from the last
    // ``dragover``.  Sync the canonical order to the Y.Doc once.
    const cell = this.cells.find((c) => c.id === draggingId);
    if (cell && typeof this._syncCellsOrderToYDoc === 'function') {
      this._syncCellsOrderToYDoc(cell);
    }
  };

  state.onCellDragEnd = function () {
    // ``drop`` already fired for a successful drop; ``dragend``
    // also fires when the user releases outside any drop target
    // (i.e. cancels the drag).  Either way, clear the visual flag
    // so the source cell loses its ``--dragging`` opacity.
    this._resetCellDragState();
  };

  state._resetCellDragState = function () {
    this.dragState = { draggingCellId: null };
    this._dragInProgress = false;
  };

  state._flipReorderCells = function (mutator) {
    // FLIP animation: capture every cell's bounding-rect TOP
    // before the mutation, run the mutation, then on the next
    // animation frame compute the inverse-deltaY for each cell
    // and transition it back to its identity transform.
    const beforeTops = new Map();
    const els = document.querySelectorAll('.pql-notebook-cell');
    for (const el of els) {
      const id = this._cellElId(el);
      if (id) beforeTops.set(id, el.getBoundingClientRect().top);
    }
    mutator();
    // ``$nextTick`` fires after Alpine has flushed the
    // ``this.cells`` mutation into the DOM (re-keyed list).
    this.$nextTick(() => {
      const after = document.querySelectorAll('.pql-notebook-cell');
      for (const el of after) {
        const id = this._cellElId(el);
        if (!id) continue;
        const oldTop = beforeTops.get(id);
        if (oldTop == null) continue;
        const newTop = el.getBoundingClientRect().top;
        const dy = oldTop - newTop;
        if (Math.abs(dy) < 1) continue;
        el.style.transition = 'none';
        el.style.transform = `translateY(${dy}px)`;
        // Force reflow so the next style write registers as a
        // transition starting point (without this, the browser
        // collapses both writes into a single frame and the
        // animation is skipped).
        // eslint-disable-next-line no-unused-expressions
        el.offsetHeight;
        el.style.transition = `transform ${FLIP_DURATION_MS}ms ${FLIP_EASING}`;
        el.style.transform = '';
      }
      // Cleanup inline styles after the animation runs so the
      // next layout pass isn't pinned by a stale transition.
      setTimeout(() => {
        for (const el of after) {
          el.style.transition = '';
          el.style.transform = '';
        }
      }, FLIP_DURATION_MS + 20);
    });
  };

  state._cellElId = function (el) {
    // the cell wrapper carries ``data-cell-id="cell.id"``
    // explicitly so the FLIP helper can resolve every cell (incl.
    // markdown view-mode cells that don't mount a CodeMirror host).
    return el.getAttribute('data-cell-id');
  };
}
