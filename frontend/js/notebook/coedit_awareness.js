/**
 * Co-edit awareness — peer rail render + presence broadcast.
 *
 * Wires three things on top of the `_awareness` instance that
 * `coedit_core.js`' `_initCoedit` creates:
 *
 *   1. Outbound: local awareness mutations are encoded and pushed
 *      over the WS as tag-0x03 frames (`_wireAwarenessUplink`).
 *   2. Inbound: remote awareness `change` events trigger a throttled
 *      peer-rail rebuild (`_wirePeerRailRefresh` → `_renderPeerRail`).
 *   3. Agent pseudo-peers: REST agent-presence events stitch into the
 *      same peer rail under a robot-icon branch (`_applyAgentPresence`).
 *
 * Sync-recovery rebroadcast: the late-joiner re-emit in the awareness
 * `change` handler closes the Phase-108 race where the recipient's
 * `setLocalState` frame arrived before our own.  Bounded loop — the
 * recipient's own re-broadcast surfaces as `updated`, not `added`,
 * so it does not re-fire.
 */

import { encodeAwarenessUpdate } from 'y-protocols/awareness';

import { initials as _initials, avatarColor as _userColor } from '../avatars.js';

const REMOTE_ORIGIN = 'pql-coedit-remote';
const PEER_RAIL_RENDER_THROTTLE_MS = 100;

export function installCoeditAwareness(state) {
  state._coeditPeerRefresh = null;
  state._coeditBeforeUnload = null;
  state._coeditAgentPeers = {};
  state.coeditPeers = [];

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
    } catch (_err) {
      /* swallow */
    }
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

    const refresh = (changes) => {
      if (!this._coeditPeerRefresh) {
        this._coeditPeerRefresh = setTimeout(() => {
          this._coeditPeerRefresh = null;
          this._renderPeerRail();
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
        changes &&
        Array.isArray(changes.added) &&
        changes.added.some((id) => id !== aw.clientID)
      ) {
        this._broadcastLocalAwareness();
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
        color: '#5a6cf0', // pinned co-edit-agent indigo for visual contrast
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

    this._coeditBeforeUnload = () => {
      try {
        aw.setLocalState(null);
      } catch (_e) {
        /* swallow */
      }
      this._coeditBeforeUnload = null;
    };
    window.addEventListener('beforeunload', this._coeditBeforeUnload);
  };
}
