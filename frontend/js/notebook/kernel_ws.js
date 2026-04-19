// Sprint 76 — ipykernel WebSocket carved out of main.js.
//
// Owns: socket handle, namespace-introspect buffer, all frame routing
// (hello / ack / interrupted / restarted / error / kernel_msg).  The
// factory closure holds every bit of WS state so multiple tabs on one
// page each get their own socket without bleed-through.
//
// Out of scope (stays in main.js): the per-tab Alpine-reactive state
// (kernelStatus, kernelSessionId, executingCells, variables), which we
// mutate through the ``alpine`` ref the caller hands in.  Cell-affordance
// status pills are driven directly from here because they are
// closure-scoped records, not Alpine state — setStatus /
// setExecutionCount / start/stopElapsed are pure DOM mutators from
// cell_affordances.js.

import { NAMESPACE_INTROSPECT_CODE } from './cell_parser.js';
import {
    setStatus,
    setExecutionCount,
    startElapsed,
    stopElapsed,
    resetElapsed,
} from './cell_affordances.js';
import { toast } from '../api.js';

// Sprint 96: ``resolveCellId`` maps an incoming content-hash back to
// the transient per-session cell label (``cell-N``) that
// ``cellAffordances`` / ``zoneManager`` / ``executingCells`` key on.
// The caller (main.js) owns the content-hash ↔ cell-id mapping and
// passes a closure so this module stays stateless wrt cell identity.
// ``__pql_``-prefixed internal hashes (namespace introspect) are
// handled below the resolver and never hit it.
export function createKernelWs({
    alpine,
    zoneManager,
    cellAffordances,
    resolveCellId,
}) {
    let ws = null;
    let namespaceBuffer = '';

    function open() {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${proto}://${location.host}/ws/notebook/kernel`
            + `?path=${encodeURIComponent(alpine.path)}`;
        alpine.kernelStatus = 'connecting';
        try {
            ws = new WebSocket(url);
        } catch (err) {
            console.error('[notebook-editor] ws open failed', err);
            alpine.kernelStatus = 'error';
            return;
        }
        ws.addEventListener('message', (ev) => {
            let frame;
            try { frame = JSON.parse(ev.data); } catch { return; }
            handleFrame(frame);
        });
        ws.addEventListener('close', (ev) => {
            alpine.kernelStatus = 'disconnected';
            if (ev.code === 4401) {
                toast('error', 'Kernel auth expired — reload.');
            }
        });
        ws.addEventListener('error', () => {
            alpine.kernelStatus = 'error';
        });
    }

    function send(obj) {
        if (!ws || ws.readyState !== WebSocket.OPEN) {
            toast('error', 'Kernel not connected');
            return false;
        }
        ws.send(JSON.stringify(obj));
        return true;
    }

    function sendNamespaceIntrospect() {
        namespaceBuffer = '';
        return send({
            type: 'execute',
            content_hash: '__pql_namespace__',
            code: NAMESPACE_INTROSPECT_CODE,
        });
    }

    function handleFrame(frame) {
        switch (frame.type) {
            case 'hello':
                alpine.kernelStatus = 'ready';
                alpine.kernelSessionId = frame.kernel_session_id;
                break;
            case 'ack':
                break;
            case 'interrupted':
                toast('info', 'Kernel interrupted');
                break;
            case 'restarted':
                alpine.kernelSessionId = frame.kernel_session_id;
                zoneManager.clearAllOutputs();
                alpine.executingCells = {};
                alpine.kernelStatus = 'ready';
                // Kernel was reset — counters and elapsed pills from the
                // previous session are stale.
                for (const cellId of Object.keys(cellAffordances)) {
                    const rec = cellAffordances[cellId];
                    setStatus(rec, 'idle');
                    setExecutionCount(rec, null);
                    resetElapsed(rec);
                }
                toast('success', 'Kernel restarted');
                break;
            case 'error':
                toast('error', frame.message || 'kernel error');
                break;
            case 'kernel_msg':
                renderMsg(frame);
                break;
        }
    }

    function renderMsg(frame) {
        // Sprint 62: route ``__pql_`` content-hash values to the internal-introspect
        // handler instead of the output renderer + persistence path.
        if (frame.content_hash && frame.content_hash.startsWith('__pql_')) {
            if (frame.content_hash === '__pql_namespace__') {
                handleNamespace(frame);
            }
            return;
        }
        // Sprint 96: resolve the incoming content-hash to the current
        // cell-id label; if the user edited the source between dispatch
        // and reply (thereby changing the hash), ``cellId`` will be
        // ``null`` and the frame is silently dropped — matching the
        // Databricks / VSCode behaviour where mid-run edits orphan
        // the output.
        const cellId = frame.content_hash
            ? resolveCellId(frame.content_hash)
            : null;
        if (frame.msg_type === 'status') {
            if (cellId) {
                const record = cellAffordances[cellId];
                if (frame.content.execution_state === 'idle') {
                    const next = { ...alpine.executingCells };
                    delete next[cellId];
                    alpine.executingCells = next;
                    // Sprint 66: stop the live elapsed tick but leave
                    // the final status pill flip to the forthcoming
                    // ``execute_reply`` — ok/error/aborted are only
                    // known from the shell-channel reply.
                    if (record) stopElapsed(record);
                    if (alpine.variablesVisible) {
                        window.setTimeout(() => alpine._refreshVariables(), 50);
                    }
                } else if (frame.content.execution_state === 'busy') {
                    alpine.executingCells = {
                        ...alpine.executingCells, [cellId]: true,
                    };
                    if (record) {
                        setStatus(record, 'running');
                        setExecutionCount(record, '*');
                        startElapsed(record);
                    }
                }
            }
            return;
        }
        if (!cellId) return;
        if (frame.msg_type === 'execute_input') {
            const record = cellAffordances[cellId];
            if (record && frame.content && frame.content.execution_count != null) {
                setExecutionCount(record, frame.content.execution_count);
            }
            return;
        }
        // Sprint 72: ipywidgets minimal placeholder — swallow comm frames
        // so they never reach the output zone.
        if (frame.msg_type === 'comm_open'
                || frame.msg_type === 'comm_msg'
                || frame.msg_type === 'comm_close') {
            return;
        }
        if (frame.msg_type === 'execute_reply') {
            const record = cellAffordances[cellId];
            if (record) {
                stopElapsed(record);
                const content = frame.content || {};
                const replyStatus = content.status;
                if (replyStatus === 'ok') {
                    setStatus(record, 'ok');
                } else if (replyStatus === 'aborted') {
                    setStatus(record, 'cancelled');
                } else if (replyStatus === 'error') {
                    if (content.ename === 'KeyboardInterrupt') {
                        setStatus(record, 'cancelled');
                    } else {
                        setStatus(record, 'error');
                    }
                } else {
                    setStatus(record, 'idle');
                }
            }
            return;
        }
        zoneManager.appendOutput(cellId, frame.msg_type, frame.content);
    }

    function handleNamespace(frame) {
        if (frame.msg_type === 'stream'
                && frame.content && frame.content.name === 'stdout') {
            namespaceBuffer += frame.content.text || '';
            return;
        }
        if (frame.msg_type === 'status'
                && frame.content && frame.content.execution_state === 'idle') {
            try {
                const parsed = JSON.parse(namespaceBuffer);
                if (parsed && typeof parsed === 'object') {
                    alpine.variables = parsed;
                }
            } catch {}
            namespaceBuffer = '';
        }
    }

    function isOpen() {
        return !!ws && ws.readyState === WebSocket.OPEN;
    }

    return { open, send, sendNamespaceIntrospect, isOpen };
}
