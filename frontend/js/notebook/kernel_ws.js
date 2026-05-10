/**
 * Browser ↔ /ws/notebook/kernel JSON-RPC client.
 *
 * Speaks the wire protocol the route handler defines:
 *   inbound : {id, method, params}
 *   outbound: {id, result|error}  + {notify, params}
 *
 * Connection lifecycle is owned by ``notebookEditor`` via
 * :func:`createKernelClient`.  The factory exposes ``connect()``,
 * ``execute(contentHash, source)``, ``interrupt()``, ``restart()``
 * and ``close()``; every method that triggers a kernel reply returns
 * a ``Promise`` that resolves with the matching ``{id, result}``
 * frame.  Streamed kernel-message frames invoke the
 * ``onMessage(payload)`` callback so the editor can route them to
 * the right cell's output zone.
 */

function _wsUrlForPath(notebookPath) {
 const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
 const enc = encodeURIComponent(notebookPath);
 return `${proto}//${window.location.host}/ws/notebook/kernel?path=${enc}`;
}

export function createKernelClient({
 notebookPath,
 onMessage = () => {},
 onReady = () => {},
 onClose = () => {},
 onError = () => {},
} = {}) {
 if (!notebookPath) {
 throw new Error('createKernelClient: notebookPath is required');
 }
 let ws = null;
 let nextId = 1;
 const pending = new Map();
 let kernelSessionId = null;

 function _route(payload) {
 if (payload && typeof payload === 'object') {
 if (payload.notify === 'ready') {
 kernelSessionId = (payload.params && payload.params.kernel_session_id) || null;
 try { onReady(payload.params || {}); }
 catch (e) { onError(e); }
 return;
 }
 if (payload.notify === 'kernel_message') {
 try { onMessage(payload.params || {}); }
 catch (e) { onError(e); }
 return;
 }
 if (typeof payload.id === 'number' && pending.has(payload.id)) {
 const { resolve, reject } = pending.get(payload.id);
 pending.delete(payload.id);
 if (payload.error) reject(new Error(payload.error.message || 'kernel error'));
 else resolve(payload.result || {});
 return;
 }
 }
 }

 function _request(method, params = {}) {
 if (!ws || ws.readyState !== WebSocket.OPEN) {
 return Promise.reject(new Error('kernel WebSocket not open'));
 }
 const id = nextId++;
 const frame = JSON.stringify({ id, method, params });
 return new Promise((resolve, reject) => {
 pending.set(id, { resolve, reject });
 ws.send(frame);
 });
 }

 return {
 get kernelSessionId() { return kernelSessionId; },
 get readyState() { return ws ? ws.readyState : WebSocket.CLOSED; },

 connect() {
 if (ws && ws.readyState === WebSocket.OPEN) return;
 ws = new WebSocket(_wsUrlForPath(notebookPath));
 ws.addEventListener('message', (ev) => {
 let payload = null;
 try { payload = JSON.parse(ev.data); }
 catch (e) { onError(e); return; }
 _route(payload);
 });
 ws.addEventListener('close', (ev) => {
 // Reject any in-flight requests so callers don't hang.
 for (const { reject } of pending.values()) {
 reject(new Error(`kernel WebSocket closed (code ${ev.code})`));
 }
 pending.clear();
 try { onClose(ev); } catch (_e) { /* ignore */ }
 });
 ws.addEventListener('error', (ev) => {
 try { onError(ev); } catch (_e) { /* ignore */ }
 });
 },

 execute(contentHash, source, options = {}) {
 return _request('execute', {
 content_hash: contentHash,
 source: source,
 cell_type: options.cellType || 'code',
 result_var: options.resultVar || null,
 });
 },

 interrupt() { return _request('interrupt', {}); },

 restart() { return _request('restart', {}); },

 close() {
 if (ws && ws.readyState === WebSocket.OPEN) ws.close();
 ws = null;
 },
 };
}
