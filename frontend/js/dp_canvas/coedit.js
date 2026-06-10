/*
 * Conditional opt-in canvas co-edit binding.
 *
 * Activated only when the editor URL carries ``?coedit=1`` so the
 * single-user mode stays unchanged.  Builds a Y.Doc with a "canvas"
 * Y.Map containing one "json" entry — the serialised CanvasDoc.
 * The editor's reload pipeline reads that entry to rebuild the
 * Drawflow surface on every remote update.
 *
 * Wire-format tags mirror pointlessql/api/dp_canvas_coedit_ws.py.
 */

const TAG_SYNC_STEP1 = 0x00;
const TAG_SYNC_STEP2 = 0x01;
const TAG_SYNC_UPDATE = 0x02;
const TAG_AWARENESS_UPDATE = 0x03;

export function isCoeditEnabled() {
  try {
    const u = new URL(window.location.href);
    return u.searchParams.get('coedit') === '1';
  } catch (e) {
    return false;
  }
}

let _yjsCache = null;
async function _loadYjs() {
  if (_yjsCache) return _yjsCache;
  const [Y, syncProtocol, awarenessProtocol, encoding, decoding] = await Promise.all([
    import('yjs'),
    import('y-protocols/sync'),
    import('y-protocols/awareness'),
    import('lib0/encoding'),
    import('lib0/decoding'),
  ]);
  _yjsCache = { Y, sync: syncProtocol, awareness: awarenessProtocol, encoding, decoding };
  return _yjsCache;
}

/**
 * Wire the canvas editor to the per-DP co-edit hub.
 *
 * @param {object} editor  the dpCanvasEditor Alpine instance
 * @param {number|string} dpId  the data-product id
 * @returns {Promise<object|null>}  a controller with destroy() or null when disabled
 */
export async function attachCanvasCoedit(editor, dpId) {
  if (!isCoeditEnabled()) return null;
  const { Y, sync, awareness, encoding, decoding } = await _loadYjs();
  const doc = new Y.Doc();
  const canvasMap = doc.getMap('canvas');
  let suppressLocal = false;

  const aw = new awareness.Awareness(doc);

  const wsUrl =
    (window.location.protocol === 'https:' ? 'wss://' : 'ws://') +
    window.location.host +
    `/ws/dp-canvas/${dpId}`;
  const ws = new WebSocket(wsUrl);
  ws.binaryType = 'arraybuffer';

  function syncDocToEditor() {
    const json = canvasMap.get('json');
    if (typeof json !== 'string' || !json.trim()) return;
    let parsed;
    try {
      parsed = JSON.parse(json);
    } catch (e) {
      return;
    }
    suppressLocal = true;
    try {
      editor._loadIntoDrawflow(parsed);
    } finally {
      window.setTimeout(() => {
        suppressLocal = false;
      }, 50);
    }
  }

  canvasMap.observe((_event) => {
    syncDocToEditor();
  });

  ws.onopen = () => {
    const encoder = encoding.createEncoder();
    encoding.writeVarUint(encoder, 0); // sync message id
    sync.writeSyncStep1(encoder, doc);
    const payload = encoding.toUint8Array(encoder);
    // Frame: TAG_SYNC_STEP1 + state vector (the message body).
    const sv = Y.encodeStateVector(doc);
    const buf = new Uint8Array(1 + sv.length);
    buf[0] = TAG_SYNC_STEP1;
    buf.set(sv, 1);
    ws.send(buf);
  };

  ws.onmessage = (ev) => {
    const data = new Uint8Array(ev.data);
    if (!data.length) return;
    const tag = data[0];
    const payload = data.slice(1);
    if (tag === TAG_SYNC_STEP2) {
      try {
        Y.applyUpdate(doc, payload, 'remote');
      } catch (e) {}
    } else if (tag === TAG_SYNC_UPDATE) {
      try {
        Y.applyUpdate(doc, payload, 'remote');
      } catch (e) {}
    } else if (tag === TAG_AWARENESS_UPDATE) {
      try {
        awareness.applyAwarenessUpdate(aw, payload, 'remote');
      } catch (e) {}
    }
  };

  // Push local doc updates upstream as TAG_SYNC_UPDATE.
  doc.on('update', (update, origin) => {
    if (origin === 'remote') return;
    if (ws.readyState !== WebSocket.OPEN) return;
    const buf = new Uint8Array(1 + update.length);
    buf[0] = TAG_SYNC_UPDATE;
    buf.set(update, 1);
    ws.send(buf);
  });

  // Push awareness changes upstream.
  aw.on('update', ({ added, updated, removed }, origin) => {
    if (origin === 'remote') return;
    if (ws.readyState !== WebSocket.OPEN) return;
    const changed = added.concat(updated).concat(removed);
    const payload = awareness.encodeAwarenessUpdate(aw, changed);
    const buf = new Uint8Array(1 + payload.length);
    buf[0] = TAG_AWARENESS_UPDATE;
    buf.set(payload, 1);
    ws.send(buf);
  });

  // Editor → Y.Doc mirror: whenever the local user mutates a node /
  // edge, capture the editor's current serialisation into the
  // single "json" slot.  Y emits an update which the on('update')
  // hook above relays to the server.
  function pushLocalSerialisation() {
    if (suppressLocal) return;
    const json = JSON.stringify(editor._buildDocument());
    if (canvasMap.get('json') === json) return;
    canvasMap.set('json', json);
  }

  const originalScheduleAutosave = editor._scheduleAutosave.bind(editor);
  editor._scheduleAutosave = () => {
    pushLocalSerialisation();
    return originalScheduleAutosave();
  };

  const localState = {
    name: 'me',
    color: '#0d6efd',
  };
  aw.setLocalState(localState);

  return {
    destroy() {
      try {
        ws.close();
      } catch (e) {}
      try {
        aw.destroy();
      } catch (e) {}
      try {
        doc.destroy();
      } catch (e) {}
      editor._scheduleAutosave = originalScheduleAutosave;
    },
    awareness: aw,
    doc,
  };
}
