/**
 * Notebook editor — co-edit lifecycle mixin (Phase 105.3 scaffold +
 * Phase 105.4 awareness layer).
 *
 * Spins up :func:`createCoeditClient` after the notebook's
 * ``notebook_uuid`` lands, keeps a single status field
 * (``coeditStatus``) that the toolbar binds to for the live pill,
 * builds a y-protocols ``Awareness`` instance seeded with the
 * current viewer's id/name/colour, and surfaces a deduped peer list
 * (``coeditPeers``) for the toolbar's avatar rail.
 *
 * The client itself is the passive scaffold from
 * ``./coedit_client.js`` — Y.Doc stays in sync with the server but
 * is not yet bound to the per-cell CodeMirror views.  That wiring
 * lands in Phase 105.3b once the save-path barrier (Phase 105.5)
 * has solved the cell_uuid reconciler race.  Awareness frames are
 * already relayed by the Sprint-105.2 hub, so the presence layer
 * works without further server changes.
 */

import { Awareness, encodeAwarenessUpdate } from 'y-protocols/awareness';

import { createCoeditClient } from './coedit_client.js';

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
  state.coeditPeers = [];

  state._initCoedit = function () {
    if (this._coedit) return;
    if (!this.notebookUuid) return;
    const user = this._coeditUser;
    // No identifiable user (anonymous render path / SSR test) → still
    // open the WS so the toolbar pill paints, but skip the awareness
    // wiring entirely.  The Phase 105.2 hub will reject anon callers
    // upstream, so this branch only fires in degenerate flows.
    const haveUser = !!(user && Number(user.id) > 0);
    this._coedit = createCoeditClient({
      notebookUuid: this.notebookUuid,
      onStatusChange: (next) => { this.coeditStatus = next; },
      onCellRemap: (remap) => { this._applyCellUuidRemap(remap); },
    });
    if (haveUser) {
      // Awareness needs an in/out Y.Doc — the client's ``ydoc`` is the
      // only one that exists, so we anchor to it and hand the
      // instance back to the client via ``setAwareness`` (the wire
      // handler reads it through a closure-captured ``let``).  This
      // also keeps the awareness clientID aligned with every local
      // doc-update, which 105.3b's ``y-codemirror.next`` will rely on.
      this._awareness = new Awareness(this._coedit.ydoc);
      this._awareness.setLocalState({
        user: {
          id: Number(user.id),
          name: String(user.name || 'anonymous'),
          color: _userColor(user.id),
        },
        cursor: null,
      });
      this._coedit.setAwareness(this._awareness);
      this._wireAwarenessUplink();
      this._wirePeerRailRefresh();
      this._installBeforeUnloadCleanup();
    }
    this._coedit.connect();
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
    const refresh = () => {
      if (self._coeditPeerRefresh) return;
      self._coeditPeerRefresh = setTimeout(() => {
        self._coeditPeerRefresh = null;
        self._renderPeerRail();
      }, PEER_RAIL_RENDER_THROTTLE_MS);
    };
    aw.on('change', refresh);
    // Paint once immediately so the local user shows in dev tools
    // without waiting for the first remote update.
    this._renderPeerRail();
  };

  state._renderPeerRail = function () {
    if (!this._awareness) {
      this.coeditPeers = [];
      return;
    }
    const localId = this._coeditUser ? Number(this._coeditUser.id) : 0;
    const peers = [];
    for (const [clientId, value] of this._awareness.getStates()) {
      if (!value || !value.user) continue;
      if (Number(value.user.id) === localId) continue;
      peers.push({
        clientId,
        id: Number(value.user.id) || 0,
        name: String(value.user.name || 'anonymous'),
        color: String(value.user.color || _userColor(value.user.id)),
        initials: _initials(value.user.name),
        agent: value.agent || null,
      });
    }
    // Stable ordering so re-renders don't reshuffle avatars.
    peers.sort((a, b) => a.clientId - b.clientId);
    this.coeditPeers = peers;
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

  state._applyCellUuidRemap = function (remap) {
    // Phase 105.5 — server told us the canonical cell_uuid changed
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
