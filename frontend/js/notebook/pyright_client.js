// Phase 12.7 Sprint 65 — pyright LSP JSON-RPC client + Monaco providers.
//
// One PyrightClient per WebSocket; Monaco provider registration is a
// process-global side-effect (keyed on language id, not editor
// instance), so we guard inside each provider via a WeakMap(model →
// {client, uri}) so multiple editor instances on the same page (multi-
// tab is Sprint 68) don't cross-fire.
//
// BUG-64-02 boundary note: PyrightClient holds a WebSocket reference
// and a per-instance Map of pending requests.  The class is plain
// JS — clients should hold one in closure scope (createClosureRefs),
// never as an Alpine x-data field.  The grep gate at
// scripts/check-frontend-no-reactive-monaco.sh enforces this.

export class PyrightClient {
    constructor(ws) {
        this._ws = ws;
        this._nextId = 1;
        this._pending = new Map();
        this._notifications = {};
    }

    _onMessage(msg) {
        if (msg.id !== undefined && this._pending.has(msg.id)) {
            const p = this._pending.get(msg.id);
            this._pending.delete(msg.id);
            if (msg.error) p.reject(msg.error);
            else p.resolve(msg.result);
        } else if (msg.method && this._notifications[msg.method]) {
            this._notifications[msg.method](msg.params || {});
        }
    }

    request(method, params) {
        if (this._ws.readyState !== WebSocket.OPEN) {
            return Promise.reject(new Error('LSP ws not open'));
        }
        const id = this._nextId++;
        this._ws.send(JSON.stringify({ jsonrpc: '2.0', id, method, params }));
        return new Promise((resolve, reject) => {
            this._pending.set(id, { resolve, reject });
            // Bound safety timeout so the Monaco provider never hangs
            // forever on a mute pyright.
            window.setTimeout(() => {
                if (this._pending.has(id)) {
                    this._pending.delete(id);
                    reject(new Error(`LSP ${method} timed out`));
                }
            }, 8000);
        });
    }

    notify(method, params) {
        if (this._ws.readyState !== WebSocket.OPEN) return;
        this._ws.send(JSON.stringify({ jsonrpc: '2.0', method, params }));
    }

    on(method, callback) {
        this._notifications[method] = callback;
    }
}

// Map an LSP CompletionItemKind enum value to the Monaco constant.
// Both are documented integer codes from the LSP spec / Monaco's
// d.ts; straight table lookup keeps the mapping readable even as
// the list grows.
export function lspCompletionKindToMonaco(kind, monaco) {
    const k = monaco.languages.CompletionItemKind;
    return ({
        1: k.Text, 2: k.Method, 3: k.Function, 4: k.Constructor,
        5: k.Field, 6: k.Variable, 7: k.Class, 8: k.Interface,
        9: k.Module, 10: k.Property, 11: k.Unit, 12: k.Value,
        13: k.Enum, 14: k.Keyword, 15: k.Snippet, 16: k.Color,
        17: k.File, 18: k.Reference, 19: k.Folder, 20: k.EnumMember,
        21: k.Constant, 22: k.Struct, 23: k.Event, 24: k.Operator,
        25: k.TypeParameter,
    }[kind] || k.Text);
}

export function lspSeverityToMonaco(severity, monaco) {
    return ({
        1: monaco.MarkerSeverity.Error,
        2: monaco.MarkerSeverity.Warning,
        3: monaco.MarkerSeverity.Info,
        4: monaco.MarkerSeverity.Hint,
    }[severity] || monaco.MarkerSeverity.Info);
}

// Module-level state — provider registration is a global Monaco
// side-effect, so we register at most once per process and discriminate
// by model via the WeakMap.
let _providersRegistered = false;
const _clientsByModel = new WeakMap();

export function bindPyrightModel(model, client, uri) {
    _clientsByModel.set(model, { client, uri });
}

export function registerPyrightProvidersOnce(monaco) {
    if (_providersRegistered) return;
    _providersRegistered = true;

    const lookup = (model) => _clientsByModel.get(model);

    const positionToLsp = (position) => ({
        line: position.lineNumber - 1,
        character: position.column - 1,
    });

    monaco.languages.registerCompletionItemProvider('python', {
        triggerCharacters: ['.', '(', ',', '='],
        provideCompletionItems: async (model, position) => {
            const ctx = lookup(model);
            if (!ctx) return { suggestions: [] };
            const word = model.getWordUntilPosition(position);
            const range = new monaco.Range(
                position.lineNumber, word.startColumn,
                position.lineNumber, word.endColumn,
            );
            try {
                const res = await ctx.client.request('textDocument/completion', {
                    textDocument: { uri: ctx.uri },
                    position: positionToLsp(position),
                });
                const items = Array.isArray(res) ? res : (res?.items || []);
                return {
                    suggestions: items.map((item) => ({
                        label: item.label,
                        kind: lspCompletionKindToMonaco(item.kind || 1, monaco),
                        insertText: item.insertText || item.label,
                        detail: item.detail,
                        documentation: item.documentation?.value
                            ? { value: item.documentation.value, isTrusted: false }
                            : (typeof item.documentation === 'string'
                                ? item.documentation : undefined),
                        sortText: item.sortText,
                        range,
                    })),
                };
            } catch (e) {
                return { suggestions: [] };
            }
        },
    });

    monaco.languages.registerHoverProvider('python', {
        provideHover: async (model, position) => {
            const ctx = lookup(model);
            if (!ctx) return null;
            try {
                const res = await ctx.client.request('textDocument/hover', {
                    textDocument: { uri: ctx.uri },
                    position: positionToLsp(position),
                });
                if (!res || !res.contents) return null;
                const parts = Array.isArray(res.contents) ? res.contents : [res.contents];
                return {
                    contents: parts.map((p) =>
                        typeof p === 'string'
                            ? { value: p }
                            : { value: p.value || '' }),
                };
            } catch (e) {
                return null;
            }
        },
    });

    monaco.languages.registerSignatureHelpProvider('python', {
        signatureHelpTriggerCharacters: ['(', ','],
        provideSignatureHelp: async (model, position) => {
            const ctx = lookup(model);
            if (!ctx) return null;
            try {
                const res = await ctx.client.request('textDocument/signatureHelp', {
                    textDocument: { uri: ctx.uri },
                    position: positionToLsp(position),
                });
                if (!res || !res.signatures) return null;
                return {
                    value: {
                        signatures: res.signatures.map((s) => ({
                            label: s.label,
                            documentation: s.documentation?.value || s.documentation,
                            parameters: (s.parameters || []).map((p) => ({
                                label: p.label,
                                documentation: p.documentation?.value || p.documentation,
                            })),
                        })),
                        activeSignature: res.activeSignature || 0,
                        activeParameter: res.activeParameter || 0,
                    },
                    dispose: () => {},
                };
            } catch (e) {
                return null;
            }
        },
    });

    monaco.languages.registerDefinitionProvider('python', {
        provideDefinition: async (model, position) => {
            const ctx = lookup(model);
            if (!ctx) return null;
            try {
                const res = await ctx.client.request('textDocument/definition', {
                    textDocument: { uri: ctx.uri },
                    position: positionToLsp(position),
                });
                if (!res) return null;
                const arr = Array.isArray(res) ? res : [res];
                // Same-document only for Sprint 61 — cross-file
                // navigation would need a model-by-uri resolver we
                // don't have yet.
                return arr
                    .filter((loc) => loc.uri === ctx.uri)
                    .map((loc) => ({
                        uri: model.uri,
                        range: {
                            startLineNumber: loc.range.start.line + 1,
                            startColumn: loc.range.start.character + 1,
                            endLineNumber: loc.range.end.line + 1,
                            endColumn: loc.range.end.character + 1,
                        },
                    }));
            } catch (e) {
                return null;
            }
        },
    });
}
