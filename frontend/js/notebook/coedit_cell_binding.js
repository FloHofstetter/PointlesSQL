/**
 * Co-edit per-cell binding — `y-codemirror.next` triple resolver +
 * cells-order CRDT sync.
 *
 * `cellYBinding(cell)` returns the `{ ytext, awareness, undoManager }`
 * triple that `cellEditor()` needs to swap its local history for
 * `yCollab`.  The triple is only handed back when the client has
 * completed the initial sync round-trip — pre-sync cells fall back
 * to standalone CodeMirror and pick up co-edit on the next mount
 * (`_rebindCellEditorsAfterSync`).
 *
 * Local cell reorder writes to the `cells_order` Y.Array on drop
 * (`_syncCellsOrderToYDoc`); peer reorders trigger
 * `_reconcileCellsFromOrder` via the observer installed in
 * `_installCellsOrderObserver`.  In-progress drags are skipped to
 * avoid clobbering the live-preview reorder.
 *
 * Reads `this._coedit` (from coedit_core) and `this._awareness`
 * (from coedit_awareness).  The `installCoeditLifecycle` facade
 * guarantees both are in place by the time `_initCoedit` runs.
 */

import { Text as YText, UndoManager as YUndoManager } from 'yjs';

import { cellEditor } from './cell_editor.js';

const CELLS_ORDER_KEY = 'cells_order';
const CELLS_TEXT_KEY = 'cells_text';

export function installCoeditCellBinding(state) {
  state.cellYBinding = function (cell) {
    // resolve the ``{ ytext, awareness, undoManager }``
    // triple ``cellEditor()`` needs to swap its local history for
    // ``y-codemirror.next``'s ``yCollab`` extension.  Returns null
    // when the prerequisites are not met (cell missing uuid,
    // coedit client not synced, or no awareness — anonymous render).
    // Callers fall back to standalone CodeMirror in that case.
    if (!cell || !cell.cell_uuid) return null;
    if (!this._coedit || !this._coedit.synced) return null;
    if (!this._awareness) return null;
    const ydoc = this._coedit.ydoc;
    if (!ydoc) return null;
    const texts = ydoc.getMap(CELLS_TEXT_KEY);
    let ytext = texts.has(cell.cell_uuid) ? texts.get(cell.cell_uuid) : null;
    if (!ytext) {
      // Cell minted in this tab (no save round-trip yet) → seed the
      // shared map so peers see the new key.  yCollab will populate
      // the actual text on first mount.
      const fresh = new YText();
      ydoc.transact(() => {
        texts.set(cell.cell_uuid, fresh);
        const order = ydoc.getArray(CELLS_ORDER_KEY);
        let present = false;
        for (let i = 0; i < order.length; i += 1) {
          if (order.get(i) === cell.cell_uuid) { present = true; break; }
        }
        if (!present) order.push([cell.cell_uuid]);
      });
      ytext = fresh;
    }
    return {
      ytext,
      awareness: this._awareness,
      undoManager: new YUndoManager(ytext),
    };
  };

  state._syncCellsOrderToYDoc = function (cell) {
    // local reorder write-through.  Translates the
    // current ``this.cells`` Alpine order into a ``cells_order``
    // Y.Array delete+insert under the local origin so peers receive
    // the move without waiting for the save round-trip.  Skipped when
    // co-edit is not active, the doc has not synced yet, or the cell
    // has no ``cell_uuid`` (un-saved cells are not in the Y.Array
    // until ``cellYBinding`` seeds them at first edit).
    if (!cell || !cell.cell_uuid) return;
    if (!this._coedit || !this._coedit.synced) return;
    const ydoc = this._coedit.ydoc;
    if (!ydoc) return;
    const order = ydoc.getArray(CELLS_ORDER_KEY);
    let fromIdx = -1;
    for (let i = 0; i < order.length; i += 1) {
      if (order.get(i) === cell.cell_uuid) { fromIdx = i; break; }
    }
    if (fromIdx < 0) return;
    // Find the uuid currently AFTER ``cell`` in the local Alpine
    // array — that's the anchor we insert before in the Y.Array.
    // Walking the local array (not the Y.Array) keeps the two
    // representations consistent even when some cells are uuid-less.
    const localIdx = this.cells.findIndex((c) => c && c.id === cell.id);
    if (localIdx < 0) return;
    let anchorUuid = null;
    for (let i = localIdx + 1; i < this.cells.length; i += 1) {
      const c = this.cells[i];
      if (c && c.cell_uuid && c.cell_uuid !== cell.cell_uuid) {
        anchorUuid = c.cell_uuid;
        break;
      }
    }
    ydoc.transact(() => {
      order.delete(fromIdx, 1);
      if (anchorUuid == null) {
        order.push([cell.cell_uuid]);
        return;
      }
      let insertIdx = -1;
      for (let i = 0; i < order.length; i += 1) {
        if (order.get(i) === anchorUuid) { insertIdx = i; break; }
      }
      if (insertIdx < 0) order.push([cell.cell_uuid]);
      else order.insert(insertIdx, [cell.cell_uuid]);
    }, 'pql-local-reorder');
  };

  state._reconcileCellsFromOrder = function () {
    // peer reorder reconcile.  Reads the canonical
    // ``cells_order`` uuid list from the Y.Doc and rebuilds the
    // Alpine ``cells`` array so the DOM order matches.  Cells
    // without a ``cell_uuid`` (freshly added locally, not yet
    // saved) are preserved at the tail in their current relative
    // order — they will join the canonical order once the save
    // reconciler assigns a uuid and broadcasts it back.
    if (!this._coedit || !this._coedit.synced) return;
    if (!Array.isArray(this.cells)) return;
    const ydoc = this._coedit.ydoc;
    if (!ydoc) return;
    const order = ydoc.getArray(CELLS_ORDER_KEY);
    const remoteUuids = order.toArray();
    const remoteSet = new Set(remoteUuids);
    const byUuid = new Map();
    const orphans = [];                       // cell has uuid but is NOT in cells_order
    const localOnly = [];                     // cell has no uuid yet (un-saved)
    for (const c of this.cells) {
      if (!c) continue;
      if (!c.cell_uuid) { localOnly.push(c); continue; }
      if (remoteSet.has(c.cell_uuid)) byUuid.set(c.cell_uuid, c);
      else orphans.push(c);                   // preserve — server seed may be stale
    }
    const reordered = [];
    for (const uuid of remoteUuids) {
      const cell = byUuid.get(uuid);
      if (cell) reordered.push(cell);
    }
    // Tail: cells whose uuids weren't in the canonical order (legacy
    // notebooks where ``cells_order`` was seeded before some cells
    // gained uuids), then cells that have no uuid yet at all.
    reordered.push(...orphans);
    reordered.push(...localOnly);
    // Bail when the order is identical to avoid Alpine re-keying
    // churn (and the cascading editor remount risk).
    if (reordered.length === this.cells.length) {
      let identical = true;
      for (let i = 0; i < reordered.length; i += 1) {
        if (reordered[i].id !== this.cells[i].id) { identical = false; break; }
      }
      if (identical) return;
    }
    this.cells = reordered;
  };

  state._installCellsOrderObserver = function () {
    if (!this._coedit || !this._coedit.ydoc) return;
    if (this._cellsOrderObserverInstalled) return;
    const order = this._coedit.ydoc.getArray(CELLS_ORDER_KEY);
    const self = this;
    order.observe((event) => {
      // Skip echoes of our own ``_syncCellsOrderToYDoc`` transaction —
      // ``this.cells`` already reflects the move locally.  Remote
      // mutations carry a different (or absent) ``transaction.local``
      // flag depending on the y-protocols path; both branches are
      // safe to ignore when the origin matches our local tag.
      if (event.transaction && event.transaction.local) return;
      // while the user is actively dragging a cell,
      // ``this.cells`` is in an intermediate state that does NOT
      // match ``cells_order`` (we only write to Y.Doc on drop).
      // Skipping reconcile here keeps the live-preview reorder
      // from being clobbered by a peer's unrelated edit; the
      // post-drop sync will reconverge on the user's release.
      if (self._dragInProgress) return;
      self._reconcileCellsFromOrder();
    });
    this._cellsOrderObserverInstalled = true;
  };

  state._rebindCellEditorsAfterSync = function () {
    // sync-timing rebind.  Cells that mounted
    // before ``createCoeditClient`` finished the sync_step2 handshake
    // got ``cellYBinding(cell)`` returning ``null`` (synced=false) and
    // mounted as standalone CodeMirror.  Once ``onSynced`` fires we
    // walk every editor that's still un-bound, destroy it, and remount
    // it Y-bound.  ``cell.source`` is the canonical text the standalone
    // listener wrote on every keystroke, so the remount seeds the
    // shared ``Y.Text`` with the same content peers would have seen on
    // a fresh open.  No-op when the editor registry is empty (anon
    // render / SSR test).
    const editors = this._editors;
    if (!editors || typeof editors !== 'object') return;
    if (!Array.isArray(this.cells)) return;
    for (const cell of this.cells) {
      if (!cell || !cell.id) continue;
      const existing = editors[cell.id];
      if (!existing || existing._yBinding) continue;
      const host = document.getElementById(`pql-cell-host-${cell.id}`);
      if (!host) continue;
      const binding = this.cellYBinding(cell);
      if (!binding) continue;
      const source = typeof existing.getSource === 'function'
        ? existing.getSource()
        : String(cell.source || '');
      try { existing.destroy(); } catch (_e) { /* swallow */ }
      const fresh = cellEditor({
        initialSource: source,
        language:
          cell.cell_type === 'sql'
            ? 'sql'
            : cell.cell_type === 'markdown'
              ? 'markdown'
              : 'python',
        onSourceChange: (value) => this._onCellSourceChange(cell.id, value),
        yBinding: binding,
      });
      editors[cell.id] = fresh;
      host.dataset.pqlCellInit = '';
      host.innerHTML = '';
      // Mount is async; let it run in the background so onSynced
      // doesn't block the WS message loop.
      fresh.mount(host).catch(() => { /* swallow */ });
    }
  };
}
