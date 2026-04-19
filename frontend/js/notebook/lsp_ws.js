// Sprint 76 — pyright LSP WebSocket carved out of main.js.
//
// Owns: lspWs socket handle, PyrightClient instance, document URI,
// monotonic document version.  The factory closure keeps those private
// so two notebook tabs never share a single LSP document view by
// accident.
//
// The ``open()`` call returns after ``textDocument/didOpen`` — caller
// is free to fire-and-forget or await; diagnostics flow over the
// ``publishDiagnostics`` notification into Monaco's model-markers
// surface.  ``notifyDidChange()`` sends a full-document sync because
// notebook documents are small enough that incremental sync would cost
// more in bookkeeping than it saves on the wire.

import {
    PyrightClient,
    bindPyrightModel,
    lspSeverityToMonaco,
} from './pyright_client.js';

export function createLspWs({ alpine, refs, monaco }) {
    let lspWs = null;
    let lspClient = null;
    let lspDocUri = null;
    let lspDocVersion = 0;

    async function open() {
        const proto = location.protocol === 'https:' ? 'wss' : 'ws';
        const url = `${proto}://${location.host}/ws/notebook/lsp`
            + `?path=${encodeURIComponent(alpine.path)}`;
        alpine.lspStatus = 'connecting';
        try {
            lspWs = new WebSocket(url);
        } catch (err) {
            console.error('[notebook-editor] lsp ws failed', err);
            alpine.lspStatus = 'error';
            return;
        }
        lspClient = new PyrightClient(lspWs);
        lspWs.addEventListener('message', (ev) => {
            try { lspClient._onMessage(JSON.parse(ev.data)); } catch {}
        });
        lspWs.addEventListener('close', (ev) => {
            if (ev.code === 4404) {
                alpine.lspStatus = 'unavailable';
            } else {
                alpine.lspStatus = 'error';
            }
        });
        lspWs.addEventListener('error', () => {
            alpine.lspStatus = 'error';
        });
        await new Promise((resolve, reject) => {
            const onOpen = () => { resolve(); };
            const onErr = () => reject(new Error('ws errored before open'));
            lspWs.addEventListener('open', onOpen, { once: true });
            lspWs.addEventListener('error', onErr, { once: true });
        });

        lspDocUri = `file:///notebook/${alpine.path}`;
        lspDocVersion = 1;
        try {
            await lspClient.request('initialize', {
                processId: null,
                clientInfo: { name: 'pointlessql-editor', version: '0.1' },
                rootUri: null,
                capabilities: {
                    textDocument: {
                        synchronization: { didSave: false, dynamicRegistration: false },
                        completion: {
                            completionItem: {
                                snippetSupport: false,
                                documentationFormat: ['markdown', 'plaintext'],
                            },
                        },
                        hover: { contentFormat: ['markdown', 'plaintext'] },
                        signatureHelp: {
                            signatureInformation: {
                                documentationFormat: ['markdown', 'plaintext'],
                            },
                        },
                        definition: { linkSupport: false },
                        publishDiagnostics: { relatedInformation: false },
                    },
                },
            });
        } catch (e) {
            console.error('[notebook-editor] lsp initialize failed', e);
            alpine.lspStatus = 'error';
            return;
        }
        lspClient.notify('initialized', {});
        const model = refs.get('model');
        lspClient.notify('textDocument/didOpen', {
            textDocument: {
                uri: lspDocUri,
                languageId: 'python',
                version: lspDocVersion,
                text: model.getValue(),
            },
        });
        bindPyrightModel(model, lspClient, lspDocUri);
        lspClient.on('textDocument/publishDiagnostics', (params) => {
            if (params.uri !== lspDocUri) return;
            const markers = (params.diagnostics || []).map((d) => ({
                startLineNumber: d.range.start.line + 1,
                startColumn: d.range.start.character + 1,
                endLineNumber: d.range.end.line + 1,
                endColumn: d.range.end.character + 1,
                severity: lspSeverityToMonaco(d.severity || 1, monaco),
                message: d.message,
                source: d.source || 'pyright',
                code: typeof d.code === 'object' ? d.code.value : d.code,
            }));
            monaco.editor.setModelMarkers(model, 'pyright', markers);
        });
        alpine.lspStatus = 'ready';
    }

    function notifyDidChange() {
        if (!lspClient || !lspDocUri) return;
        lspDocVersion++;
        lspClient.notify('textDocument/didChange', {
            textDocument: {
                uri: lspDocUri,
                version: lspDocVersion,
            },
            contentChanges: [{ text: refs.get('model').getValue() }],
        });
    }

    return { open, notifyDidChange };
}
