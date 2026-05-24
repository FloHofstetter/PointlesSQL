/**
 * Notebook editor — co-edit lifecycle mixin
 * (Phase 105.3 scaffold + Phase 105.4 awareness +
 * Phase 105.5 save-path remap + Phase 105.3b per-cell binding).
 *
 * Spins up :func:`createCoeditClient` after the notebook's
 * ``notebook_uuid`` lands, keeps a single status field
 * (``coeditStatus``) that the toolbar binds to for the live pill,
 * builds a y-protocols ``Awareness`` instance seeded with the
 * current viewer's id/name/colour, and surfaces a deduped peer list
 * (``coeditPeers``) for the toolbar's avatar rail.
 *
 * 105.3b layers per-cell ``y-codemirror.next`` binding on top.  The
 * mixin now also exposes ``cellYBinding(cell)`` which returns the
 * ``{ ytext, awareness, undoManager }`` triple that ``cellEditor()``
 * needs to swap its local history for collaborative editing.  The
 * triple is only handed back when the client has completed the
 * initial sync round-trip — pre-sync cells fall back to standalone
 * CodeMirror (and pick up co-edit on the next mount).
 */

import { Awareness, encodeAwarenessUpdate } from 'y-protocols/awareness';
import { Text as YText, UndoManager as YUndoManager } from 'yjs';

import { cellEditor } from './cell_editor.js';
import { createCoeditClient } from './coedit_client.js';

const CELLS_ORDER_KEY = 'cells_order';
const CELLS_TEXT_KEY = 'cells_text';

const REMOTE_ORIGIN = 'pql-coedit-remote';
const PEER_RAIL_RENDER_THROTTLE_MS = 100;

// FNV-1a-32 over the user-id string → HSL hue (0..359).  Deterministic
// across reloads + tabs so the same user always gets the same colour.
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

function _initials(name) {
  const trimmed = String(name || '').trim();
  if (!trimmed) return '?';
  const parts = trimmed.split(/\s+/).filter(Boolean);
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
}

export function installCoeditLifecycle(state, { userInfo = null } = {}) {
  state.coeditStatus = 'idle';
  state._coedit = null;
  state._awareness = null;
  state._coeditUser = userInfo || null;
  state._coeditPeerRefresh = null;
  state._coeditBeforeUnload = null;
  state._coeditAgentPeers = {};
  state.coeditPeers = [];

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
      // doc-update, which 105.3b's ``y-codemirror.next`` will rely on.
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

  state._broadcastLocalAwareness = function () {
    // Encode the current local awareness state and push it onto the
    // WS.  Used by the ``onSynced`` hook to recover the broadcast
    // that the initial ``setLocalState`` lost while the socket was
    // still connecting.  No-op when there is no awareness instance
    // (anonymous render).
    const aw = this._awareness;
    const client = this._coedit;
    if (!aw || !client) return;
    try {
      const payload = encodeAwarenessUpdate(aw, [aw.clientID]);
      client.sendAwarenessUpdate(payload);
    } catch (_err) { /* swallow */ }
  };

  state._wireAwarenessUplink = function () {
    // Local awareness mutations → encode + push as a tag-0x03 frame.
    // Remote-origin updates skip the wire (already delivered).
    const aw = this._awareness;
    const client = this._coedit;
    aw.on('update', ({ added, updated, removed }, origin) => {
      if (origin === REMOTE_ORIGIN) return;
      const changed = added.concat(updated, removed);
      if (changed.length === 0) return;
      try {
        const payload = encodeAwarenessUpdate(aw, changed);
        client.sendAwarenessUpdate(payload);
      } catch (_err) {
        // Encoding failures are non-fatal; the next change will retry.
      }
    });
  };

  state._wirePeerRailRefresh = function () {
    const aw = this._awareness;
    const self = this;
    const refresh = (changes) => {
      if (!self._coeditPeerRefresh) {
        self._coeditPeerRefresh = setTimeout(() => {
          self._coeditPeerRefresh = null;
          self._renderPeerRail();
        }, PEER_RAIL_RENDER_THROTTLE_MS);
      }
      // when a NEW peer's state arrives in the
      // ``added`` set, re-emit our own state so the new joiner
      // sees us.  y-protocols awareness is diff-only: our own
      // ``onSynced`` rebroadcast may have happened before the new
      // peer could subscribe, so without this rebroadcast they
      // would never receive our identity.  Bounded loop: the
      // recipient's own re-broadcast surfaces as ``updated`` here,
      // not ``added``, so we don't re-fire.
      if (
        changes
        && Array.isArray(changes.added)
        && changes.added.some((id) => id !== aw.clientID)
      ) {
        self._broadcastLocalAwareness();
      }
    };
    aw.on('change', refresh);
    // Paint once immediately so the local user shows in dev tools
    // without waiting for the first remote update.
    this._renderPeerRail();
  };

  state._renderPeerRail = function () {
    const peers = [];
    if (this._awareness) {
      // Filter self by Y.js clientID, not user.id — two browser tabs from
      // the same logged-in user share one user.id but get distinct
      // awareness clientIDs, and the multi-tab replay expects each tab to
      // see the other as a peer ("two clientIds, one id").  Filtering by
      // user.id would erase that case and silently drop the peer rail.
      const localClientId = this._awareness.clientID;
      for (const [clientId, value] of this._awareness.getStates()) {
        if (!value || !value.user) continue;
        if (clientId === localClientId) continue;
        peers.push({
          clientId,
          id: Number(value.user.id) || 0,
          name: String(value.user.name || 'anonymous'),
          color: String(value.user.color || _userColor(value.user.id)),
          initials: _initials(value.user.name),
          agent: null,
        });
      }
    }
    // agent presence: stitch in pseudo-peers driven by
    // the REST agent-presence endpoint.  Agents carry a synthetic
    // ``clientId`` (negative so they sort after every real awareness
    // client) and the ``agent`` flag flips the partial onto the
    // robot-icon branch.
    let agentSlot = -1;
    for (const entry of Object.values(this._coeditAgentPeers || {})) {
      peers.push({
        clientId: agentSlot,
        id: 0,
        name: String(entry.name || 'agent'),
        color: '#5a6cf0',  // pinned co-edit-agent indigo for visual contrast
        initials: 'A',
        agent: {
          run_id: String(entry.agent_run_id || ''),
          action: String(entry.action || 'editing'),
          cell_uuid: entry.cell_uuid || null,
        },
      });
      agentSlot -= 1;
    }
    peers.sort((a, b) => a.clientId - b.clientId);
    this.coeditPeers = peers;
  };

  state._applyAgentPresence = function (presence) {
    if (!presence || typeof presence !== 'object') return;
    const runId = String(presence.agent_run_id || '');
    if (!runId) return;
    const map = { ...(this._coeditAgentPeers || {}) };
    if (presence.action === 'clear') {
      delete map[runId];
    } else {
      map[runId] = {
        agent_run_id: runId,
        name: String(presence.name || 'agent'),
        cell_uuid: presence.cell_uuid || null,
        action: String(presence.action || 'editing'),
      };
    }
    this._coeditAgentPeers = map;
    this._renderPeerRail();
  };

  state._installBeforeUnloadCleanup = function () {
    const aw = this._awareness;
    const self = this;
    this._coeditBeforeUnload = () => {
      try { aw.setLocalState(null); } catch (_e) { /* swallow */ }
      self._coeditBeforeUnload = null;
    };
    window.addEventListener('beforeunload', this._coeditBeforeUnload);
  };

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
    // Stash the latest mapping so Phase-105.3b's per-cell
    // CodeMirror binding can rebind to the new ``ytext`` reference
    // without re-mounting the entire editor.
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
