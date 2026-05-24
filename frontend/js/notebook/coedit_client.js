/**
 * co-edit Y.Doc client (passive scaffold) +
 * awareness-frame wiring.
 *
 * Owns the WebSocket lifecycle against
 * ``/ws/notebook/coedit/{notebook_uuid}`` (the hub) and
 * keeps a local :class:`Y.Doc` in lock-step with the server's
 * authoritative replica.  The wire format mirrors the server side
 * one-to-one:
 *
 *   * ``0x00`` sync_step1  — client → server state-vector handshake.
 *   * ``0x01`` sync_step2  — server → client full-state on connect.
 *   * ``0x02`` sync_update — bidirectional incremental update.
 *   * ``0x03`` awareness   — opaque presence bytes, relayed.
 *
 * This module deliberately does NOT bind the Y.Doc to any
 * CodeMirror view yet — that wiring lands once the
 * save-path race against the cell_uuid reconciler (the * barrier) is in place.  For 105.3 the client connects, keeps the
 * Doc in sync, and exposes the connection status so the toolbar
 * can paint a live / offline pill.  Awareness payloads are forwarded
 * via ``onAwarenessUpdate`` and — when a y-protocols ``Awareness``
 * instance is supplied — applied with the same ``pql-coedit-remote``
 * origin marker the Y.Doc uses, so the mixin (``coedit.js``) can
 * filter remote-driven state changes from local cursor moves.
 */

import * as Y from 'yjs';
import { applyAwarenessUpdate } from 'y-protocols/awareness';

const TAG_SYNC_STEP1 = 0x00;
const TAG_SYNC_STEP2 = 0x01;
const TAG_SYNC_UPDATE = 0x02;
const TAG_AWARENESS_UPDATE = 0x03;
const TAG_CELL_UUID_REMAP = 0x04;
const TAG_AGENT_PRESENCE = 0x05;

const CELLS_ORDER_KEY = 'cells_order';
const CELLS_TEXT_KEY = 'cells_text';

// Marker on Y.Doc local-update events so the client doesn't echo
// remote updates back as new sync_update frames.  Pycrdt on the
// server side discards no-op merges, but the round-trip is wasted
// bandwidth either way.
const ORIGIN_REMOTE = 'pql-coedit-remote';

// Capped exponential backoff for transient WS failures.  Hub-level
// 4xxx close codes (auth / role / missing notebook) skip reconnect
// entirely — see the close handler below.
const _RECONNECT_BASE_MS = 1000;
const _RECONNECT_MAX_MS = 30000;

function _wsUrlFor(notebookUuid) {
  const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
  return `${proto}//${window.location.host}/ws/notebook/coedit/${encodeURIComponent(notebookUuid)}`;
}

export function createCoeditClient({
  notebookUuid,
  onStatusChange = () => {},
  onAwarenessUpdate = () => {},
  onCellRemap = () => {},
  onAgentPresence = () => {},
  onSynced = () => {},
  awareness: initialAwareness = null,
} = {}) {
  if (!notebookUuid) {
    throw new Error('createCoeditClient: notebookUuid is required');
  }

  const ydoc = new Y.Doc();
  // Late-binding: callers create the y-protocols Awareness instance
  // against ``ydoc`` after the client exists (the mixin path), so
  // ``setAwareness`` lets them attach it without rebuilding the
  // closure-captured handler.
  let awareness = initialAwareness;
  let ws = null;
  let status = 'idle';
  let synced = false;
  let reconnectTimer = null;
  let reconnectAttempts = 0;
  let closedByUser = false;

  function _setStatus(next) {
    if (next === status) return;
    status = next;
    try { onStatusChange(next); } catch (_e) { /* swallow */ }
  }

  function _sendFrame(tag, payload) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return;
    const body = payload instanceof Uint8Array ? payload : new Uint8Array(payload);
    const frame = new Uint8Array(1 + body.length);
    frame[0] = tag;
    frame.set(body, 1);
    ws.send(frame);
  }

  function _onLocalUpdate(update, origin) {
    // Remote-origin updates were applied by us; the server already
    // saw the originating sync_update frame.
    if (origin === ORIGIN_REMOTE) return;
    // Pre-handshake updates would race against sync_step2 — defer
    // until the initial sync round-trip completes.
    if (!synced) return;
    _sendFrame(TAG_SYNC_UPDATE, update);
  }

  ydoc.on('update', _onLocalUpdate);

  function _handleFrame(frame) {
    if (!frame || frame.length === 0) return;
    const tag = frame[0];
    const payload = frame.subarray(1);
    if (tag === TAG_SYNC_STEP2 || tag === TAG_SYNC_UPDATE) {
      try {
        Y.applyUpdate(ydoc, payload, ORIGIN_REMOTE);
      } catch (err) {
        // Malformed update — server validates on its side, so this
        // is normally unreachable.  Log + drop; the connection stays.
        // eslint-disable-next-line no-console
        console.warn('[coedit] malformed update from server', err);
        return;
      }
      if (!synced && tag === TAG_SYNC_STEP2) {
        synced = true;
        _setStatus('live');
        // Echo our own state-vector so the server backfills any
        // updates we had before connecting.  For 105.3's empty-Doc
        // bootstrap this is a no-op; harmless either way.
        _sendFrame(TAG_SYNC_STEP1, Y.encodeStateVector(ydoc));
        // cells that mounted before the
        // handshake landed got no ``cellYBinding`` (synced was
        // false) and silently fell back to standalone CodeMirror.
        // Fire ``onSynced`` so the mixin can rebind their editors
        // exactly once, the first time the server confirms sync.
        try { onSynced(); } catch (_e) { /* swallow */ }
      }
    } else if (tag === TAG_CELL_UUID_REMAP) {
      // server-originated advisory.  Payload is a
      // JSON ``{old_uuid: new_uuid}`` mapping that the
      // ``/api/notebooks/save`` handler emitted after the cell-
      // reconciler minted fresh UUIDs.  Patch the local Y.Doc so
      // any cells_text / cells_order entries pinned to the stale
      // key follow over, then surface the dict to the mixin so the
      // Alpine state (cells[].cell_uuid, cellCounts, etc.) and any
      // Phase-105.3b CodeMirror binding can rebind to the new key.
      let remap = null;
      try {
        remap = JSON.parse(new TextDecoder().decode(payload));
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('[coedit] malformed cell_uuid_remap', err);
        return;
      }
      if (remap && typeof remap === 'object') {
        try {
          ydoc.transact(() => {
            const order = ydoc.getArray(CELLS_ORDER_KEY);
            const texts = ydoc.getMap(CELLS_TEXT_KEY);
            for (const [oldU, newU] of Object.entries(remap)) {
              if (oldU === newU) continue;
              if (texts.has(oldU)) {
                const prior = texts.get(oldU);
                let priorText = '';
                try {
                  priorText = typeof prior === 'string'
                    ? prior
                    : (prior && typeof prior.toString === 'function' ? prior.toString() : '');
                } catch (_e) { /* swallow */ }
                texts.delete(oldU);
                texts.set(newU, new Y.Text(priorText));
              }
              for (let i = 0; i < order.length; i += 1) {
                if (order.get(i) === oldU) {
                  order.delete(i, 1);
                  order.insert(i, [newU]);
                }
              }
            }
          }, ORIGIN_REMOTE);
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn('[coedit] failed to apply local cell_uuid remap', err);
        }
        try { onCellRemap(remap); } catch (_e) { /* swallow */ }
      }
    } else if (tag === TAG_AGENT_PRESENCE) {
      // agent broadcast.  Server-emitted JSON payload
      // describing a pseudo-peer (agent_run_id, name, cell_uuid,
      // action).  The mixin layers it into ``coeditPeers`` so the
      // toolbar avatar rail renders agents alongside humans.
      let parsed = null;
      try {
        parsed = JSON.parse(new TextDecoder().decode(payload));
      } catch (err) {
        // eslint-disable-next-line no-console
        console.warn('[coedit] malformed agent_presence', err);
        return;
      }
      if (parsed && typeof parsed === 'object') {
        try { onAgentPresence(parsed); } catch (_e) { /* swallow */ }
      }
    } else if (tag === TAG_AWARENESS_UPDATE) {
      // y-protocols awareness state lands here as opaque bytes.  When
      // a local Awareness instance is wired up, apply the diff with
      // the same remote-origin marker the Y.Doc uses so the mixin's
      // ``update`` listener can early-return for echoes.  The raw
      // callback still fires for callers that prefer to deserialise
      // the payload themselves (e.g. Phase 105.6 agent presence).
      if (awareness !== null) {
        try {
          applyAwarenessUpdate(awareness, payload, ORIGIN_REMOTE);
        } catch (err) {
          // eslint-disable-next-line no-console
          console.warn('[coedit] malformed awareness frame', err);
        }
      }
      try { onAwarenessUpdate(payload); } catch (_e) { /* swallow */ }
    }
    // Unknown tags are silently dropped to stay forward-compatible
    // with a future server that adds frame types.
  }

  function _scheduleReconnect() {
    if (closedByUser || reconnectTimer) return;
    const delay = Math.min(
      _RECONNECT_MAX_MS,
      _RECONNECT_BASE_MS * Math.pow(2, reconnectAttempts),
    );
    reconnectAttempts += 1;
    reconnectTimer = setTimeout(() => {
      reconnectTimer = null;
      _open();
    }, delay);
  }

  function _open() {
    if (ws && (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CONNECTING)) {
      return;
    }
    _setStatus('connecting');
    try {
      ws = new WebSocket(_wsUrlFor(notebookUuid));
    } catch (_err) {
      _setStatus('error');
      _scheduleReconnect();
      return;
    }
    ws.binaryType = 'arraybuffer';

    ws.addEventListener('open', () => {
      reconnectAttempts = 0;
      _sendFrame(TAG_SYNC_STEP1, Y.encodeStateVector(ydoc));
    });

    ws.addEventListener('message', (ev) => {
      if (typeof ev.data === 'string') return;
      _handleFrame(new Uint8Array(ev.data));
    });

    ws.addEventListener('close', (ev) => {
      synced = false;
      if (ev.code === 4401 || ev.code === 4403 || ev.code === 4404) {
        // Auth / role / missing-notebook — no reconnect makes sense.
        _setStatus('unauthorized');
        return;
      }
      _setStatus('offline');
      _scheduleReconnect();
    });

    ws.addEventListener('error', () => {
      // Close fires next with a real status update.
    });
  }

  return {
    ydoc,
    get status() { return status; },
    get synced() { return synced; },
    connect() {
      closedByUser = false;
      reconnectAttempts = 0;
      _open();
    },
    sendAwarenessUpdate(payload) {
      _sendFrame(TAG_AWARENESS_UPDATE, payload);
    },
    setAwareness(next) {
      awareness = next || null;
    },
    get awareness() { return awareness; },
    close() {
      closedByUser = true;
      if (reconnectTimer) {
        clearTimeout(reconnectTimer);
        reconnectTimer = null;
      }
      try { ydoc.off('update', _onLocalUpdate); } catch (_e) { /* swallow */ }
      if (ws) {
        try { ws.close(); } catch (_e) { /* swallow */ }
        ws = null;
      }
      _setStatus('idle');
    },
  };
}
