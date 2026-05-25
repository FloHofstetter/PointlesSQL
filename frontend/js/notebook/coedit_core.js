/**
 * Co-edit core — Y.Doc + WS client lifecycle, status mgmt, toolbar
 * pill bindings.
 *
 * Spins up :func:`createCoeditClient` after the notebook's
 * ``notebook_uuid`` lands, keeps a single status field
 * (``coeditStatus``) that the toolbar binds to for the live pill,
 * and exposes ``coeditLabel`` / ``coeditDotClass`` / ``coeditPillClass``
 * / ``coeditTooltip`` for the pill render.
 *
 * Awareness + per-cell binding live in sibling installers
 * (`coedit_awareness.js`, `coedit_cell_binding.js`).  This installer
 * creates the `_awareness` instance inside `_initCoedit` (so the
 * client constructor can receive it via `setAwareness`) but expects
 * the wire/render methods (`_wireAwarenessUplink`,
 * `_wirePeerRailRefresh`, `_installBeforeUnloadCleanup`,
 * `_broadcastLocalAwareness`, `_applyAgentPresence`) plus the
 * cell-binding hooks (`_rebindCellEditorsAfterSync`,
 * `_installCellsOrderObserver`) to already be attached on `this` by
 * the time `_initCoedit` runs.  The `installCoeditLifecycle` facade
 * in `coedit.js` guarantees that ordering.
 */

import { Awareness } from 'y-protocols/awareness';

import { createCoeditClient } from './coedit_client.js';

// FNV-1a-32 over the user-id string → HSL hue (0..359).  Deterministic
// across reloads + tabs so the same user always gets the same colour.
// Duplicated in coedit_awareness.js for the peer-rail render path —
// 10-LOC stable function, two file-private copies beat a cross-module
// export here.
function _userColor(userId) {
  const text = String(userId || 'anon');
  let h = 0x811c9dc5;
  for (let i = 0; i < text.length; i += 1) {
    h ^= text.charCodeAt(i);
    h = (h + ((h << 1) + (h << 4) + (h << 7) + (h << 8) + (h << 24))) >>> 0;
  }
  const hue = h % 360;
  return `hsl(${hue}, 65%, 45%)`;
}

export function installCoeditCore(state, { userInfo = null } = {}) {
  state.coeditStatus = 'idle';
  state._coedit = null;
  state._awareness = null;
  state._coeditUser = userInfo || null;

  state._initCoedit = function () {
    if (this._coedit) return;
    if (!this.notebookUuid) return;
    const user = this._coeditUser;
    // No identifiable user (anonymous render path / SSR test) → still
    // open the WS so the toolbar pill paints, but skip the awareness
    // wiring entirely.  The hub will reject anon callers
    // upstream, so this branch only fires in degenerate flows.
    const haveUser = !!(user && Number(user.id) > 0);
    this._coedit = createCoeditClient({
      notebookUuid: this.notebookUuid,
      onStatusChange: (next) => { this.coeditStatus = next; },
      onCellRemap: (remap) => { this._applyCellUuidRemap(remap); },
      onAgentPresence: (presence) => { this._applyAgentPresence(presence); },
      onSynced: () => {
        this._rebindCellEditorsAfterSync();
        this._installCellsOrderObserver();
        // the initial ``setLocalState`` below fires
        // its ``update`` event before the WS finishes connecting, so
        // ``sendAwarenessUpdate`` short-circuits on the readyState
        // gate and the broadcast frame is dropped.  Once the server
        // confirms sync (sync_step2) the socket is provably open;
        // re-emit the local state vector so peers see us without
        // waiting for the first user input.
        this._broadcastLocalAwareness();
      },
    });
    if (haveUser) {
      // Awareness needs an in/out Y.Doc — the client's ``ydoc`` is the
      // only one that exists, so we anchor to it and hand the
      // instance back to the client via ``setAwareness`` (the wire
      // handler reads it through a closure-captured ``let``).  This
      // also keeps the awareness clientID aligned with every local
      // doc-update, which `y-codemirror.next`'s yCollab extension
      // relies on.
      this._awareness = new Awareness(this._coedit.ydoc);
      this._coedit.setAwareness(this._awareness);
      // wire the WS uplink + peer-rail refresh
      // BEFORE the first ``setLocalState`` so any late callers that
      // mutate awareness (e.g. yCollab cursor tracking) fire through
      // an attached listener.  The initial broadcast itself rides
      // the ``onSynced`` rebroadcast above; the in-process listener
      // ordering only matters for subsequent state mutations.
      this._wireAwarenessUplink();
      this._wirePeerRailRefresh();
      this._installBeforeUnloadCleanup();
      this._awareness.setLocalState({
        user: {
          id: Number(user.id),
          name: String(user.name || 'anonymous'),
          color: _userColor(user.id),
        },
        cursor: null,
      });
    }
    this._coedit.connect();
  };

  state._applyCellUuidRemap = function (remap) {
    // server told us the canonical cell_uuid changed
    // for one or more cells (Pass-3 mint in the reconciler).  Patch
    // every Alpine surface that keys by cell_uuid so the next render
    // tick reflects the new id.  The Y.Doc was already updated under
    // the remote-origin marker by ``coedit_client.js`` before this
    // callback fired; this is the JS-side mirror only.
    if (!remap || typeof remap !== 'object') return;
    const keys = Object.keys(remap);
    if (keys.length === 0) return;
    if (Array.isArray(this.cells)) {
      for (const cell of this.cells) {
        if (cell && cell.cell_uuid && remap[cell.cell_uuid]) {
          cell.cell_uuid = remap[cell.cell_uuid];
        }
      }
    }
    if (this.cellCounts && typeof this.cellCounts === 'object') {
      const next = { ...this.cellCounts };
      for (const [oldU, newU] of Object.entries(remap)) {
        if (Object.prototype.hasOwnProperty.call(next, oldU)) {
          next[newU] = next[oldU];
          delete next[oldU];
        }
      }
      this.cellCounts = next;
    }
    // Stash the latest mapping so the per-cell CodeMirror binding can
    // rebind to the new ``ytext`` reference without re-mounting the
    // entire editor.
    this._pendingCellRemap = remap;
  };

  state._teardownCoedit = function () {
    if (this._coeditPeerRefresh) {
      clearTimeout(this._coeditPeerRefresh);
      this._coeditPeerRefresh = null;
    }
    if (this._coeditBeforeUnload) {
      window.removeEventListener('beforeunload', this._coeditBeforeUnload);
      this._coeditBeforeUnload = null;
    }
    if (this._awareness) {
      try { this._awareness.setLocalState(null); } catch (_e) { /* swallow */ }
      try { this._awareness.destroy(); } catch (_e) { /* swallow */ }
      this._awareness = null;
    }
    if (!this._coedit) return;
    try { this._coedit.close(); } catch (_e) { /* swallow */ }
    this._coedit = null;
    this.coeditStatus = 'idle';
    this.coeditPeers = [];
  };

  state.coeditLabel = function () {
    switch (this.coeditStatus) {
      case 'live': return 'Live';
      case 'connecting': return 'Connecting…';
      case 'offline': return 'Reconnecting…';
      case 'unauthorized': return 'View-only';
      case 'error': return 'Unavailable';
      default: return 'Offline';
    }
  };

  state.coeditDotClass = function () {
    switch (this.coeditStatus) {
      case 'live': return 'bg-success';
      case 'connecting':
      case 'offline': return 'bg-warning';
      case 'unauthorized': return 'bg-secondary';
      case 'error': return 'bg-danger';
      default: return 'bg-secondary';
    }
  };

  // vital-pill class for the toolbar status cluster.
  // Mirrors ``coeditDotClass`` but emits the pill design's class
  // pair so the toolbar's status reads as semantic state instead
  // of decoration.  ``vitalPillClass('coedit')`` on the editor
  // root scope delegates to this method.
  state.coeditPillClass = function () {
    switch (this.coeditStatus) {
      case 'live': return 'pql-vital-pill pql-vital-pill--success';
      case 'connecting':
      case 'offline': return 'pql-vital-pill pql-vital-pill--warning';
      case 'error': return 'pql-vital-pill pql-vital-pill--danger';
      case 'unauthorized':
      default: return 'pql-vital-pill pql-vital-pill--idle';
    }
  };

  state.coeditTooltip = function () {
    switch (this.coeditStatus) {
      case 'live': return 'Co-edit channel connected — changes sync across open tabs.';
      case 'connecting': return 'Opening co-edit channel…';
      case 'offline': return 'Co-edit channel dropped — reconnecting.';
      case 'unauthorized': return 'You are viewing this notebook in read-only mode.';
      case 'error': return 'Co-edit channel unavailable on this host.';
      default: return 'Co-edit channel idle.';
    }
  };
}
